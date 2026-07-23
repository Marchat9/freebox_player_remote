# Freebox Player Remote for Home Assistant

[![GitHub release](https://img.shields.io/github/v/release/Marchat9/freebox_player_remote?style=for-the-badge)](https://github.com/Marchat9/freebox_player_remote)
[![](https://img.shields.io/github/license/Marchat9/freebox_player_remote?style=for-the-badge)](https://github.com/Marchat9/freebox_player_remote/blob/main/LICENSE)

Home Assistant custom integration that fully remote-controls a **Freebox Player** over the local network, using Free's own **Foils HID** protocol.

Unlike the HTTP remote-control API (`/pub/remote_control`, blocked by Free with a 403) or the authenticated REST API (volume/play-pause only), this integration exposes the **full remote**: navigation, power, numeric keypad, channel change, media transport controls, app-launch shortcuts (Netflix, YouTube, Canal VOD...), and more — 54 keys in total.

## Disclaimer

This integration relies on Free's Foils HID network protocol, reverse-engineered from the public [dev.freebox.fr](https://dev.freebox.fr) SDK documentation and a third-party reference implementation (see [Credits](#credits)). It is not an official Free product, is not affiliated with or endorsed by Free, and is not published on the default HACS store — it's a personal/local project, installable via HACS only as a custom repository (see [Installation](#installation)).

**Tested hardware:**   Freebox Player: **_Revolution && [Devialet](https://forum.hacf.fr/t/integration-hacs-freebox-player-remote-telecommande-complete-pour-le-freebox-player/82051/8)_**. — feedback from owners of other models is welcome.

The protocol has no authentication, and the port it listens on is not fixed (only discoverable via mDNS or manually). The retransmission/keepalive logic in `client.py` is an original implementation built from the documented wire format, not a line-for-line port of any existing project — some edge cases may need adjustment against real hardware.

This integration was entirely built using [Claude](https://claude.ai) (Anthropic) — every line of code, from the protocol client to the config flow, was written by Claude.

## Compatibility

Only Players that speak the **Foils HID** network protocol can be controlled by this integration. Newer Players with a Bluetooth remote use a completely different mechanism and are out of scope.

| Player model | Protocol  | Status  | Notes |
| ------------------------------------------------ | --------------------------- | ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Revolution**  | Foils HID (network)  | ✅ Tested | Full remote confirmed working, except `System Sleep` / `System Wakeup` and all 11 app-launch keys (`Launch Netflix app` etc.): the codes are accepted (no error) but have no observable effect on real hardware — the Revolution's remote/firmware doesn't have these buttons/apps, so this isn't too surprising. |
| **Devialet** | Foils HID (network)  | ✅ Tested | [Confirmed working by a user](https://forum.hacf.fr/t/integration-hacs-freebox-player-remote-telecommande-complete-pour-le-freebox-player/82051/8). Some playback buttons and VOD service shortcuts aren't handled by the player (codes accepted but no observable effect) — the rest of the remote works normally. |
| **Crystal** | Foils HID (network) | ⚠️ Untested | Same protocol per Free's SDK docs, believed to work identically — not yet verified on real hardware. Feedback welcome. |
| **Pop / Ultra / Mini 4k** | Bluetooth LE remote  | ❌ Not supported | Free explicitly documents Pop/Ultra as needing a different, third-party app mechanism — not the same network remote. Use Home Assistant's native [`androidtv`](https://www.home-assistant.io/integrations/androidtv/) (ADB) integration instead. |

### App-launch shortcuts

11 vendor-specific app-launch codes, documented on the current (unversioned) [dev.freebox.fr codes page](https://dev.freebox.fr/sdk/freebox_player_codes.html) — added by Free in 2020 ([FS#30276](https://dev.freebox.fr/bugs/task/30276)), absent from every earlier versioned page (1.1.1/1.1.2/1.1.4).
All 11 are included in `FBX_REMOTE_KEYS`.

| Key                    | Status                                                              |
| ---------------------- | ------------------------------------------------------------------- |
| `Launch Netflix app`   | ❌ No effect on Revolution nor Devialet — may work on other players |
| `Launch YouTube app`   | ❌ No effect on Revolution nor Devialet — may work on other players |
| `Launch Canal VOD app` | ❌ No effect on Revolution nor Devialet — may work on other players |
| `Launch TV app`        | ❌ No effect on Revolution nor Devialet — may work on other players |
| `Launch Replay app`    | ❌ No effect on Revolution nor Devialet — may work on other players |
| `Launch Videoclub app` | ❌ No effect on Revolution nor Devialet — may work on other players |
| `Show TV guide`        | ❌ No effect on Revolution nor Devialet — may work on other players |
| `Show TV records`      | ❌ No effect on Revolution nor Devialet — may work on other players |
| `Launch file browser`  | ❌ No effect on Revolution nor Devialet — may work on other players |
| `Launch Radios app`    | ❌ No effect on Revolution nor Devialet — may work on other players |
| `Toggle PiP on TV`     | ❌ No effect on Revolution nor Devialet — may work on other players |

The codes are accepted without error but have no observable effect on the Revolution nor Devialet — its remote/firmware doesn't have these buttons/apps, so this isn't too surprising. Feedback from other Freebox player owners welcome.

No code exists for **Prime Video** (feature request explicitly rejected by Free, [FS#30484](https://dev.freebox.fr/bugs/task/30484) — use home-screen favorites instead) or **Disney+** (undocumented anywhere in the SDK; only on the Pop's Bluetooth remote, out of scope here).

## Installation

### HACS (custom repository)

Click the button to open your Home Assistant instance with this repository pre-filled:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Marchat9&repository=freebox_player_remote&category=integration)

_or add it manually_

1. Open HACS in Home Assistant
2. Click the three dots menu (top right) > **Custom repositories**
3. Add `https://github.com/Marchat9/freebox_player_remote` with category **Integration**
4. Search for "Freebox Player Remote" and install
5. Restart Home Assistant

### Manual

1. Copy the `custom_components/freebox_player_remote/` folder into your Home Assistant config directory, next to `configuration.yaml`:

    | Install type                   | Target path                                        |
    | ------------------------------ | -------------------------------------------------- |
    | Home Assistant OS / Supervised | `/config/custom_components/freebox_player_remote/` |
    | Docker                         | the volume mounted on `/config`                    |
    | Core (venv)                    | the folder passed to `hass -c <path>`              |

2. **Restart Home Assistant** (a fresh custom component requires a full restart, not just a YAML reload).

## Removal

1. Go to **Settings > Devices & Services**
2. Find **Freebox Player Remote** and click the three dots menu
3. Click **Delete**
4. Delete the `custom_components/freebox_player_remote/` folder (skip this step if installed via HACS — remove it from HACS instead after deleting the config entry)
5. Restart Home Assistant

## Configuration

1. Go to **Settings > Devices & Services > + Add Integration**
2. Search for **"Freebox Player Remote"**
3. Leave both fields empty to let Home Assistant find the Player automatically via mDNS, or fill in the IP address and/or port manually (see [Parameters](#parameters))

The config flow performs a **real connection test** (an actual RUDP handshake), not just an IP format check, and reports a specific error for each failure case: invalid IP format, unreachable host, connection refused, timeout, or discovery failure.

### Parameters

Both fields are optional -- if left empty, Home Assistant discovers the corresponding value automatically via mDNS.

| Parameter | Required | Description                                                                                                                                                                                                                                                                                                                                                                                                                       |
| --------- | -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Host**  | No       | IPv4 address of the Freebox Player, e.g. `192.168.1.10`. Leave empty to auto-discover the Player itself (finds the first Foils HID device on the network). Find it manually in the Freebox OS web UI at `mafreebox.freebox.fr` (_Réglages > Freebox Player_) or in your Freebox's DHCP client list. A **DHCP reservation** for the Player is strongly recommended, otherwise the integration breaks the next time its IP changes. |
| **Port**  | No       | Foils HID port. Leave empty to let Home Assistant discover it automatically via mDNS (`_hid._udp.local.`). Only fill it in manually if discovery fails (see [Troubleshooting](#troubleshooting)).                                                                                                                                                                                                                                 |

## Services

The integration exposes a single service/action:

```yaml
service: freebox_player_remote.press
data:
    key: Power
```

| Field        | Required | Description                                                                                                                                                                                              |
| ------------ | -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **key**      | Yes      | Dropdown selector listing all 54 supported remote keys (see `custom_components/freebox_player_remote/const.py`, `FBX_REMOTE_KEYS`), navigable in **Developer Tools > Actions** — no raw strings to type. |
| **entry_id** | No       | Targets a specific Player if you have more than one configured (see [Multiple Players](#multiple-players)).                                                                                              |

Note: no color-button keys (red/green/yellow/blue) are available — no HID code for them is documented in the Foils HID protocol.

## Pre-made Lovelace card

`lovelace_freebox_remote_card.yaml` (project root) is a ready-to-paste dashboard card covering 51 of the 54 keys (all except `AV`, `Context Menu`, and the combined `Play/Pause` key — separate `Play`/`Pause` buttons are included instead), laid out like a physical remote: power/sleep/wake, a merged navigation+menu pad, volume/channel, numeric keypad, playback controls, and an "Applications" section for the app-launch shortcuts.

To install it:

1. Open a dashboard, **Edit Dashboard > + Add Card**
2. Scroll to the bottom, choose **"Manual"**
3. Paste the contents of `lovelace_freebox_remote_card.yaml`

Four buttons (Back/Search/Menu/Info) use `card_mod` to reproduce the Freebox remote's button colors (red/blue/green/yellow), and the "Free" button is styled to look like the Free logo (bold italic red text). These require the [card-mod](https://github.com/thomasloven/lovelace-card-mod) HACS frontend module — without it, the card still works (every button still calls the service), it just won't show the custom colors/font.

## Multiple Players

Each Freebox Player is added as a separate config entry. If you configure more than one, the `press` service requires the `entry_id` field to pick which Player receives the key (with a single Player configured, it's used automatically and `entry_id` can be omitted).

## Requirements

- Home Assistant.
- A Freebox Player reachable on the same local network as Home Assistant.
- _Optional_, for the pre-made dashboard card's colored buttons: the [card-mod](https://github.com/thomasloven/lovelace-card-mod) HACS frontend module.

## Troubleshooting

- **"This is not a valid IPv4 address"** — check the host field for typos; hostnames aren't supported, only dotted IPv4.
- **"The host could not be reached"** — check the IP address and that the Player is on the same network as Home Assistant.
- **"The connection was actively refused"** — check the port, and that the Player's network remote-control feature is enabled.
- **"No response from the Freebox Player within the timeout"** — check that the Player is powered on and that the IP/port are correct.
- **"No host/port was given and automatic discovery did not find one"**:
    - If Home Assistant runs in Docker **without** `network_mode: host`, mDNS multicast usually can't reach the container — this is a networking limitation, not a bug in the integration.
    - `freebox_udp_finder.py` (project root) is a standalone diagnostic script you can run from any machine on the same LAN (not from Home Assistant) to check whether the Player advertises the `_hid._udp.local.` service at all, and on which port:

        ```bash
        pip install zeroconf
        python freebox_udp_finder.py
        ```

        If it finds your Player's IP with a port, enter that port manually in the config flow. If it finds nothing, check that the Player's network remote control setting is enabled, and that mDNS multicast isn't blocked between Home Assistant and the Player (AP isolation, VLANs, etc.).

- **Service call succeeds but the Player doesn't react** — check **Settings > System > Logs** filtered by `freebox_player_remote` with debug logging enabled:

    ```yaml
    logger:
        default: warning
        logs:
            custom_components.freebox_player_remote: debug
    ```

## Credits

- Protocol documentation: [dev.freebox.fr](https://dev.freebox.fr) — librudp ([SDK doc](https://dev.freebox.fr/sdk/librudp/), [source](https://github.com/fbx/librudp)) and [Foils HID SDK doc](https://dev.freebox.fr/sdk/foils_hid/).
- Protocol reference implementation: [MaximeCheramy/remotefreebox](https://github.com/MaximeCheramy/remotefreebox) (BSD-2-Clause) — used as a behavioral reference for the RUDP/Foils HID wire format; the Home Assistant integration code itself (`client.py`, `config_flow.py`, `__init__.py`, etc.) is an original async/thread-based implementation written for this project, not a direct port.
- Entirely built using [Claude](https://claude.ai) (Anthropic).

## License

MIT — see [LICENSE](https://github.com/Marchat9/freebox_player_remote/blob/main/LICENSE) .
