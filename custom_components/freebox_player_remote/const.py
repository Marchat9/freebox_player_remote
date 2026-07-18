"""Constants for the Freebox Player HID integration.

Protocol values below (RUDP header, Foils HID commands, HID report descriptor,
key -> HID code table) come verbatim from the verified Foils HID/librudp
protocol specification (see dev.freebox.fr). Do not alter them without
re-checking that spec: the Freebox Player firmware expects these exact bytes.
"""

DOMAIN = "freebox_player_remote"

DEFAULT_DEVICE_NAME = "Home Assistant Remote"
DEVICE_VERSION = 0x100

# Foils HID service advertised over mDNS by the Freebox Player.
ZEROCONF_SERVICE_TYPE = "_hid._udp.local."

# --- librudp header -------------------------------------------------

RUDP_CMD_NOOP = 0
RUDP_CMD_CLOSE = 1
RUDP_CMD_CONN_REQ = 2
RUDP_CMD_CONN_RSP = 3
RUDP_CMD_PING = 4
RUDP_CMD_PONG = 5
RUDP_CMD_APP = 0x10  # application commands = RUDP_CMD_APP + foils_hid_code

RUDP_OPT_RELIABLE = 1
RUDP_OPT_ACK = 2
RUDP_OPT_RETRANSMITTED = 4

# Keepalive / drop timeouts (seconds), per the librudp connection spec.
ACTION_TIMEOUT = 5.0
DROP_TIMEOUT = 10.0

# --- Foils HID application commands --------------------------------

FOILS_HID_DEVICE_NEW = 0
FOILS_HID_DEVICE_DROPPED = 1
FOILS_HID_DEVICE_OPEN = 2
FOILS_HID_DEVICE_CLOSE = 3
FOILS_HID_FEATURE = 4
FOILS_HID_DATA = 5
FOILS_HID_GRAB = 6
FOILS_HID_RELEASE = 7
FOILS_HID_FEATURE_SOLLICIT = 8

# --- HID report targets ---------------------------------------

TARGET_UNICODE = 1
TARGET_KEYBOARD = 2
TARGET_CONSUMER = 3
TARGET_DESKTOP = 4

# HID report descriptor, copied verbatim from the Foils HID spec. Defines 4 reports:
# 1 = unicode, 2 = keyboard, 3 = consumer control, 4 = desktop/system.
UNICODE_REPORT_DESCRIPTOR = bytes([
    0x05, 0x01, 0x09, 0x06, 0xA1, 0x01, 0x85, 0x01, 0x05, 0x10, 0x08,
    0x95, 0x01, 0x75, 0x20, 0x14, 0x27, 0xFF, 0xFF, 0xFF, 0x81, 0x62, 0xC0,
    0xA1, 0x01, 0x85, 0x02, 0x95, 0x01, 0x75, 0x08, 0x15, 0x00,
    0x26, 0xFF, 0x00, 0x05, 0x07, 0x19, 0x00, 0x2A, 0xFF, 0x00, 0x80, 0xC0,
    0x05, 0x0C, 0x09, 0x01, 0xA1, 0x01, 0x85, 0x03, 0x95, 0x01, 0x75, 0x10,
    0x19, 0x00, 0x2A, 0x8C, 0x02, 0x15, 0x00, 0x26, 0x8C, 0x02, 0x80, 0xC0,
    0x05, 0x01, 0x0a, 0x80, 0x00, 0xA1, 0x01, 0x85, 0x04, 0x75, 0x01, 0x95, 0x04,
    0x1a, 0x81, 0x00, 0x2a, 0x84, 0x00, 0x81, 0x02, 0x75, 0x01, 0x95, 0x04, 0x81, 0x01, 0xC0,
])

# Key name -> (report_id/target, hid_code, code size in bits).
# Copied verbatim from the verified Foils HID key table.
FBX_REMOTE_KEYS = {
    "Power":            (TARGET_CONSUMER, 0x30, 16),
    "AV":               (TARGET_CONSUMER, 0x63, 16),
    "0":                (TARGET_KEYBOARD, 0x62, 8),
    "1":                (TARGET_KEYBOARD, 0x59, 8),
    "2":                (TARGET_KEYBOARD, 0x5A, 8),
    "3":                (TARGET_KEYBOARD, 0x5B, 8),
    "4":                (TARGET_KEYBOARD, 0x5C, 8),
    "5":                (TARGET_KEYBOARD, 0x5D, 8),
    "6":                (TARGET_KEYBOARD, 0x5E, 8),
    "7":                (TARGET_KEYBOARD, 0x5F, 8),
    "8":                (TARGET_KEYBOARD, 0x60, 8),
    "9":                (TARGET_KEYBOARD, 0x61, 8),
    "Up":               (TARGET_KEYBOARD, 0x52, 8),
    "Down":             (TARGET_KEYBOARD, 0x51, 8),
    "Left":             (TARGET_KEYBOARD, 0x50, 8),
    "Right":            (TARGET_KEYBOARD, 0x4F, 8),
    "Enter":            (TARGET_KEYBOARD, 0x28, 8),   # = OK
    "Back":             (TARGET_CONSUMER, 0x204, 16),
    "Search":           (TARGET_CONSUMER, 0x221, 16),
    "Menu":             (TARGET_CONSUMER, 0x40, 16),
    "Info":             (TARGET_CONSUMER, 0x209, 16),
    "Free":             (TARGET_CONSUMER, 0x18f, 16),  # "Free" / task manager button
    "Vol-":             (TARGET_CONSUMER, 0xea, 16),
    "Vol+":             (TARGET_CONSUMER, 0xe9, 16),
    "Mute":             (TARGET_CONSUMER, 0xe2, 16),
    "Record":           (TARGET_CONSUMER, 0xb2, 16),
    "Chan+":            (TARGET_CONSUMER, 0x9c, 16),
    "Chan-":            (TARGET_CONSUMER, 0x9d, 16),
    "Rewind":           (TARGET_CONSUMER, 0xb4, 16),
    "Play/Pause":       (TARGET_CONSUMER, 0xcd, 16),
    "Fast Forward":     (TARGET_CONSUMER, 0xb3, 16),
    "Backspace":        (TARGET_KEYBOARD, 0x2A, 8),
    "Stop":             (TARGET_CONSUMER, 0xb7, 16),
    "Play":             (TARGET_CONSUMER, 0xb0, 16),
    "Pause":            (TARGET_CONSUMER, 0xb1, 16),
    "Random Play":      (TARGET_CONSUMER, 0xb9, 16),
    "Previous track":   (TARGET_CONSUMER, 0xb6, 16),
    "Next track":       (TARGET_CONSUMER, 0xb5, 16),
    "Eject":            (TARGET_CONSUMER, 0xb8, 16),
    "Tab":              (TARGET_KEYBOARD, 0x2B, 8),
    "Context Menu":     (TARGET_DESKTOP, 0x08, 8),
    "System Sleep":     (TARGET_DESKTOP, 0x02, 8),
    "System Wakeup":    (TARGET_DESKTOP, 0x04, 8),

    # Vendor-specific app-launch shortcuts (Consumer page 0xc), added to the
    # Freebox Player HID codes by Free in 2020 (see dev.freebox.fr bug
    # FS#30276) and present on the Player Devialet's touchscreen remote.
    "Launch TV app":         (TARGET_CONSUMER, 0xf01, 16),
    "Launch Replay app":     (TARGET_CONSUMER, 0xf02, 16),
    "Launch Videoclub app":  (TARGET_CONSUMER, 0xf03, 16),
    "Show TV guide":         (TARGET_CONSUMER, 0xf04, 16),
    "Show TV records":       (TARGET_CONSUMER, 0xf05, 16),
    "Launch file browser":   (TARGET_CONSUMER, 0xf06, 16),
    "Launch YouTube app":    (TARGET_CONSUMER, 0xf07, 16),
    "Launch Radios app":     (TARGET_CONSUMER, 0xf08, 16),
    "Launch Canal VOD app":  (TARGET_CONSUMER, 0xf09, 16),
    "Toggle PiP on TV":      (TARGET_CONSUMER, 0xf0a, 16),
    "Launch Netflix app":    (TARGET_CONSUMER, 0xf0b, 16),
}

SERVICE_PRESS = "press"
ATTR_KEY = "key"
