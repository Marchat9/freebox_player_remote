"""Blocking client for the Freebox Player Foils HID remote-control protocol.

This follows a "blocking thread" strategy: keep the network code as plain
blocking sockets running in a background thread, and let Home Assistant talk
to it via ``hass.async_add_executor_job``. A native asyncio port could replace
this module later without changing the public API used by
``__init__.py``/``config_flow.py``.

Wire format (RUDP header, Foils HID header, device-new payload, key codes) is
taken verbatim from the verified Foils HID/librudp protocol specification
(see dev.freebox.fr). The retransmission/ACK bookkeeping below is a
straightforward implementation of the header semantics documented there (the
reference implementation's internal peer.py was not copied line by line, only
the wire format was used) -- this is the part most worth double-checking
against a real Freebox Player.
"""
from __future__ import annotations

import asyncio
import logging
import random
import socket
import struct
import threading
import time

from .const import (
    ACTION_TIMEOUT,
    DEVICE_VERSION,
    DROP_TIMEOUT,
    FOILS_HID_DATA,
    FOILS_HID_DEVICE_NEW,
    RUDP_CMD_APP,
    RUDP_CMD_CLOSE,
    RUDP_CMD_CONN_REQ,
    RUDP_CMD_NOOP,
    RUDP_CMD_CONN_RSP,
    RUDP_CMD_PING,
    RUDP_CMD_PONG,
    RUDP_OPT_ACK,
    RUDP_OPT_RELIABLE,
    RUDP_OPT_RETRANSMITTED,
    UNICODE_REPORT_DESCRIPTOR,
    ZEROCONF_SERVICE_TYPE,
    FBX_REMOTE_KEYS,
)

_LOGGER = logging.getLogger(__name__)

_RUDP_HEADER = struct.Struct("!BBHHH")
_DEVICE_NEW_STRUCT = struct.Struct("!64s32sHHHHHHHH")

_SEND_RETRIES = 5
_ACK_TIMEOUT = 1.0  # seconds between retransmissions of an un-acked reliable packet
_RECV_POLL_TIMEOUT = 0.5  # socket timeout used by the background receive loop


def _round_up(value: int) -> int:
    """Round up to the next multiple of 4."""
    return (value + 3) & ~3


class FoilsHidError(Exception):
    """Base error for the Foils HID client."""


class InvalidHost(FoilsHidError):
    """The host is not a valid/resolvable IP address."""


class CannotConnect(FoilsHidError):
    """The host could not be reached (network/route error)."""


class ConnectionRefused(FoilsHidError):
    """The remote host actively refused the connection."""


class ConnectionTimeout(FoilsHidError):
    """No response was received from the Freebox Player in time."""


class UnknownKey(FoilsHidError):
    """The requested remote key is not in FBX_REMOTE_KEYS."""


class FreeboxPlayerHidClient:
    """Blocking RUDP + Foils HID client, meant to run off the event loop."""

    def __init__(self, host: str, port: int, device_name: str = "Home Assistant Remote") -> None:
        self._host = host
        self._port = port
        self._device_name = device_name

        self._sock: socket.socket | None = None
        self._lock = threading.RLock()
        # Separate from _lock (which only ever guards short, non-blocking
        # bookkeeping/socket-write sections): serializes whole connect()/
        # disconnect() sequences against each other so two threads can't
        # both reconnect at once. Never held across a wait that depends on
        # the recv thread also needing _lock, to avoid deadlocking it.
        self._connect_lock = threading.RLock()
        self._connected = False

        self._local_reliable = 0
        self._local_unreliable = 0
        self._remote_reliable: int | None = None

        self._pending_acks: dict[int, threading.Event] = {}
        self._last_send_monotonic = 0.0
        self._last_recv_monotonic = 0.0

        self._stop_event = threading.Event()
        self._recv_thread: threading.Thread | None = None
        self._keepalive_thread: threading.Thread | None = None

    # -- public API, all blocking, meant to be called via an executor -------------

    def connect(self, timeout: float = 7.0) -> None:
        """Perform the RUDP handshake then register our HID device."""
        with self._connect_lock:
            try:
                ip_bytes = socket.inet_aton(self._host)  # raises OSError if not a dotted IPv4
            except OSError as err:
                raise InvalidHost(f"'{self._host}' is not a valid IPv4 address") from err
            del ip_bytes

            if self._sock is not None:
                # Reconnecting after a drop: shed the old socket/threads first.
                self.disconnect()

            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                sock.connect((self._host, self._port))
            except OSError as err:
                sock.close()
                raise CannotConnect(f"cannot reach {self._host}:{self._port}: {err}") from err

            self._sock = sock
            self._local_reliable = random.randint(0, 0xFFFF)
            self._local_unreliable = 0
            self._remote_reliable = None
            self._stop_event.clear()

            try:
                self._handshake(timeout)
            except (TimeoutError, socket.timeout) as err:
                self._close_socket()
                raise ConnectionTimeout(
                    f"no reply from {self._host}:{self._port} (Foils HID service down or wrong port?)"
                ) from err
            except (ConnectionRefusedError, ConnectionResetError) as err:
                # UDP "port unreachable" surfaces as ConnectionRefusedError on
                # Linux but as ConnectionResetError (WSAECONNRESET) on Windows.
                self._close_socket()
                raise ConnectionRefused(
                    f"{self._host}:{self._port} refused the connection: {err}"
                ) from err
            except FoilsHidError:
                # _handshake can itself raise our own ConnectionTimeout (e.g.
                # on an unexpected reply command) -- make sure that still
                # closes the socket instead of leaking it.
                self._close_socket()
                raise
            except OSError as err:
                self._close_socket()
                raise CannotConnect(f"cannot reach {self._host}:{self._port}: {err}") from err

            self._connected = True
            self._sock.settimeout(_RECV_POLL_TIMEOUT)
            self._recv_thread = threading.Thread(
                target=self._recv_loop, name="freebox_player_remote-recv", daemon=True
            )
            self._recv_thread.start()
            self._keepalive_thread = threading.Thread(
                target=self._keepalive_loop, name="freebox_player_remote-keepalive", daemon=True
            )
            self._keepalive_thread.start()

            try:
                self._send_device_new(timeout)
            except (TimeoutError, socket.timeout) as err:
                self.disconnect()
                raise ConnectionTimeout("Freebox Player did not acknowledge DEVICE_NEW") from err
            except FoilsHidError:
                # _send_reliable raises its own ConnectionTimeout once retries
                # are exhausted -- that isn't a socket.timeout, so it would
                # otherwise skip disconnect() and leak the just-started
                # recv/keepalive threads plus the open socket.
                self.disconnect()
                raise

    def disconnect(self) -> None:
        with self._connect_lock:
            self._stop_event.set()
            if self._sock is not None:
                try:
                    self._raw_send(
                        RUDP_CMD_CLOSE, RUDP_OPT_ACK if self._remote_reliable is not None else 0, b""
                    )
                except OSError:
                    pass
            for thread in (self._recv_thread, self._keepalive_thread):
                if thread is not None and thread.is_alive():
                    thread.join(timeout=2.0)
            self._close_socket()
            self._connected = False

    def press(self, key: str) -> None:
        """Send a key press followed by its release."""
        if key not in FBX_REMOTE_KEYS:
            raise UnknownKey(f"unknown remote key: {key!r}")

        with self._connect_lock:
            if not self._connected:
                self.connect()

        target, code, size_bits = FBX_REMOTE_KEYS[key]
        header = struct.pack("!II", 0, target)

        def _encode(value: int) -> bytes:
            if size_bits == 16:
                return struct.pack("<H", value)
            if size_bits == 8:
                return struct.pack("!B", value)
            return struct.pack("<I", value)

        command = RUDP_CMD_APP + FOILS_HID_DATA
        try:
            self._send_reliable(command, header + _encode(code))
        finally:
            # Always send the "released" report -- even if the press report
            # above timed out -- otherwise the Player thinks the button is
            # held down indefinitely.
            self._send_reliable(command, header + _encode(0))

    @property
    def connected(self) -> bool:
        return self._connected

    # -- handshake / device registration ------------------------------------------

    def _handshake(self, timeout: float) -> None:
        assert self._sock is not None
        self._sock.settimeout(max(timeout / 3, 1.0))
        payload = struct.pack("!I", 0)
        last_err: Exception | None = None
        for _attempt in range(3):
            header = _RUDP_HEADER.pack(
                RUDP_CMD_CONN_REQ, RUDP_OPT_RELIABLE, 0, self._local_reliable, 0
            )
            self._sock.send(header + payload)
            self._last_send_monotonic = time.monotonic()
            try:
                data = self._sock.recv(2048)
            except (TimeoutError, socket.timeout) as err:
                last_err = err
                continue
            command, _opt, _reliable_ack, reliable, _unreliable = _RUDP_HEADER.unpack(data[:8])
            if command != RUDP_CMD_CONN_RSP:
                last_err = ConnectionTimeout("unexpected reply during handshake")
                continue
            self._remote_reliable = reliable
            self._last_recv_monotonic = time.monotonic()
            return
        raise last_err or ConnectionTimeout("handshake failed")

    def _send_device_new(self, timeout: float) -> None:
        name = self._device_name.encode("utf-8")[:63]
        serial = b""
        descriptor = UNICODE_REPORT_DESCRIPTOR
        physical = b""
        strings = b""

        # Descriptor_offset = 112, the fixed size of the "device new"
        # struct itself (offsets are relative to the start of that struct, the
        # preceding 8-byte Foils HID device_id/report_id header is not counted).
        descriptor_offset = _DEVICE_NEW_STRUCT.size
        descriptor_size = len(descriptor)
        physical_offset = _round_up(descriptor_offset + descriptor_size)
        physical_size = len(physical)
        strings_offset = _round_up(physical_offset + physical_size)
        strings_size = len(strings)

        body = _DEVICE_NEW_STRUCT.pack(
            name,
            serial,
            0,
            DEVICE_VERSION,
            descriptor_offset,
            descriptor_size,
            physical_offset,
            physical_size,
            strings_offset,
            strings_size,
        )

        blob = descriptor.ljust(_round_up(len(descriptor)), b"\x00")
        blob += physical.ljust(_round_up(len(physical)), b"\x00")
        blob += strings.ljust(_round_up(len(strings)), b"\x00")

        foils_header = struct.pack("!II", 0, 0)  # device_id=0, report_id=0
        payload = foils_header + body + blob

        self._send_reliable(RUDP_CMD_APP + FOILS_HID_DEVICE_NEW, payload, timeout=timeout, retries=3)

    # -- reliable/unreliable send helpers -------------------------------------------

    def _raw_send(self, command: int, opt: int, payload: bytes, reliable: int | None = None) -> None:
        with self._lock:
            if self._sock is None:
                raise CannotConnect("socket is closed")
            if reliable is None:
                reliable = self._local_reliable
            reliable_ack = self._remote_reliable or 0
            header = _RUDP_HEADER.pack(command, opt, reliable_ack, reliable, self._local_unreliable)
            self._sock.send(header + payload)
            self._last_send_monotonic = time.monotonic()

    def _send_reliable(
        self, command: int, payload: bytes, timeout: float = _ACK_TIMEOUT, retries: int = _SEND_RETRIES
    ) -> None:
        with self._lock:
            self._local_reliable = (self._local_reliable + 1) & 0xFFFF
            seq = self._local_reliable
            opt = RUDP_OPT_RELIABLE | (RUDP_OPT_ACK if self._remote_reliable is not None else 0)
            event = threading.Event()
            self._pending_acks[seq] = event
            self._raw_send(command, opt, payload, reliable=seq)

        acked = event.wait(timeout)
        attempt = 0
        while not acked and attempt < retries:
            with self._lock:
                if self._stop_event.is_set():
                    break
                retrans_opt = opt | RUDP_OPT_RETRANSMITTED
                self._raw_send(command, retrans_opt, payload, reliable=seq)
            acked = event.wait(timeout)
            attempt += 1

        with self._lock:
            self._pending_acks.pop(seq, None)

        if not acked:
            raise ConnectionTimeout(f"Freebox Player never acked command 0x{command:02x}")

    def _send_unreliable(self, command: int, payload: bytes = b"") -> None:
        with self._lock:
            opt = RUDP_OPT_ACK if self._remote_reliable is not None else 0
            self._local_unreliable = (self._local_unreliable + 1) & 0xFFFF
            self._raw_send(command, opt, payload)

    # -- background threads ---------------------------------------------------------

    def _recv_loop(self) -> None:
        assert self._sock is not None
        while not self._stop_event.is_set():
            try:
                data = self._sock.recv(4096)
            except (TimeoutError, socket.timeout):
                continue
            except OSError:
                if self._stop_event.is_set():
                    return
                _LOGGER.debug("freebox_player_remote: socket error in recv loop", exc_info=True)
                continue
            if len(data) < 8:
                continue

            command, opt, reliable_ack, reliable, _unreliable = _RUDP_HEADER.unpack(data[:8])
            self._last_recv_monotonic = time.monotonic()
            self._remote_reliable = reliable

            if opt & RUDP_OPT_ACK:
                with self._lock:
                    event = self._pending_acks.get(reliable_ack)
                if event is not None:
                    event.set()

            try:
                if command == RUDP_CMD_PING:
                    self._send_unreliable(RUDP_CMD_PONG)
                elif opt & RUDP_OPT_RELIABLE:
                    # Acknowledge any reliable packet initiated by the Player
                    # itself (opt=ACK is already added by _send_unreliable).
                    self._send_unreliable(RUDP_CMD_NOOP)
            except (OSError, FoilsHidError):
                # The socket may be mid-teardown from a concurrent
                # disconnect()/reconnect -- don't let that kill this thread.
                _LOGGER.debug("freebox_player_remote: failed to send from recv loop", exc_info=True)

    def _keepalive_loop(self) -> None:
        while not self._stop_event.wait(1.0):
            now = time.monotonic()
            if self._last_recv_monotonic and now - self._last_recv_monotonic > DROP_TIMEOUT:
                _LOGGER.warning(
                    "freebox_player_remote: no data from %s:%s for %.0fs, connection may be dead",
                    self._host,
                    self._port,
                    DROP_TIMEOUT,
                )
                self._connected = False
            if now - self._last_send_monotonic >= ACTION_TIMEOUT:
                try:
                    self._send_unreliable(RUDP_CMD_PING)
                except (OSError, FoilsHidError):
                    _LOGGER.debug("freebox_player_remote: failed to send keepalive ping", exc_info=True)

    def _close_socket(self) -> None:
        with self._lock:
            if self._sock is not None:
                try:
                    self._sock.close()
                finally:
                    self._sock = None


def test_connection(host: str, port: int, timeout: float = 7.0) -> None:
    """Blocking connection test used by the config flow. Raises on failure."""
    client = FreeboxPlayerHidClient(host, port)
    try:
        client.connect(timeout=timeout)
    finally:
        client.disconnect()


async def async_discover_device(
    hass, host: str | None = None, timeout: float = 8.0
) -> tuple[str, int] | None:
    """Best-effort mDNS discovery of a Freebox Player's Foils HID host/port.

    If `host` is given, only that address is considered and its advertised
    port is returned -- used when the user filled in the IP but left the port
    empty. If `host` is None, the first Foils HID service found on the
    network is used, returning both its IP and port -- used for fully
    automatic setup when the user leaves both fields empty.

    This is not part of the confirmed protocol spec (the port itself is not
    fixed, only the service type is documented). If this fails for any reason
    we simply return None so the user can fall back to entering the host/port
    manually -- never raise from here.
    """
    try:
        from homeassistant.components import zeroconf as ha_zeroconf
        from zeroconf import ServiceStateChange
        from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo
    except ImportError:
        _LOGGER.debug("freebox_player_remote: zeroconf not available, skipping discovery")
        return None

    aiozc = await ha_zeroconf.async_get_async_instance(hass)
    found = asyncio.Event()
    result: dict[str, tuple[str, int]] = {}

    async def _resolve(zc, service_type: str, name: str) -> None:
        info = AsyncServiceInfo(service_type, name)
        if not await info.async_request(zc, 3000):
            return
        addresses = info.parsed_addresses()
        if not info.port or not addresses:
            return
        if host is not None:
            if host in addresses:
                result["device"] = (host, info.port)
                found.set()
        else:
            result["device"] = (addresses[0], info.port)
            found.set()

    def _on_change(
        zeroconf,
        service_type: str,
        name: str,
        state_change: "ServiceStateChange",
    ) -> None:
        # AsyncServiceBrowser calls its handlers with keyword arguments
        # matching this exact parameter list (zeroconf/service_type/name/
        # state_change) -- a differently-named first parameter (e.g. `zc`)
        # raises "got an unexpected keyword argument 'zeroconf'".
        #
        # Home Assistant's shared Zeroconf instance is typically already
        # running and may have this service cached from before our browser
        # attached -- in that case the first event we see is "Updated", not
        # "Added". Handle both (mirrors add_service/update_service both being
        # wired to the same handler in a plain zeroconf.ServiceBrowser).
        if state_change not in (ServiceStateChange.Added, ServiceStateChange.Updated):
            return
        hass.async_create_task(_resolve(zeroconf, service_type, name))

    browser = AsyncServiceBrowser(aiozc.zeroconf, ZEROCONF_SERVICE_TYPE, handlers=[_on_change])
    try:
        await asyncio.wait_for(found.wait(), timeout)
    except asyncio.TimeoutError:
        pass
    finally:
        await browser.async_cancel()

    return result.get("device")
