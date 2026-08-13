"""Constants for the DWARF mini integration.

Module/message-type/command IDs are taken from DwarfLab's V3 websocket protocol as
documented in dwarfAlp (https://github.com/acocalypso/dwarfAlp, GPLv3), file
src/dwarf_alpaca/proto/protocol.proto. The OperationState values come from the same
project's src/dwarf_alpaca/proto/notify.proto. MODULE_SYSTEM and
CMD_SYSTEM_SET_MASTERLOCK also come from protocol.proto. The focus/GoTo/tracking
constants added for phase 2 also come from protocol.proto and
src/dwarf_alpaca/proto/astro.proto.
"""
from __future__ import annotations

DOMAIN = "dwarf_mini"

DEFAULT_PORT = 9900
CONF_HOST = "host"
CONF_PORT = "port"

# --- WsPacket.type values ---
TYPE_REQUEST = 0
TYPE_REQUEST_RESPONSE = 1
TYPE_NOTIFICATION = 2
TYPE_NOTIFICATION_RESPONSE = 3

# --- ModuleId ---
MODULE_ASTRO = 3
MODULE_NOTIFY = 9
MODULE_SYSTEM = 4

# --- DwarfCMD (only the subset used by v1) ---
CMD_ASTRO_START_CAPTURE_RAW_LIVE_STACKING = 11005
CMD_ASTRO_STOP_CAPTURE_RAW_LIVE_STACKING = 11006
CMD_NOTIFY_ELE = 15201
CMD_NOTIFY_STATE_CAPTURE_RAW_LIVE_STACKING = 15208
CMD_NOTIFY_PROGRASS_CAPTURE_RAW_LIVE_STACKING = 15209
CMD_SYSTEM_SET_MASTERLOCK = 13004

# --- OperationState (notify.proto) ---
STATE_IDLE = 0
STATE_RUNNING = 1
STATE_STOPPING = 2
STATE_STOPPED = 3

OPERATION_STATE_NAMES = {
    STATE_IDLE: "idle",
    STATE_RUNNING: "running",
    STATE_STOPPING: "stopping",
    STATE_STOPPED: "stopped",
}

# --- ModuleId (ergänzt) ---
MODULE_FOCUS = 8

# --- DwarfCMD (Fokus) ---
CMD_FOCUS_START_ASTRO_AUTO_FOCUS = 15004
CMD_NOTIFY_FOCUS = 15257
CMD_V3_NOTIFY_AUTOFOCUS_STATE = 15278
CMD_V3_NOTIFY_AUTOFOCUS_STATE_ALT = 15280

# --- DwarfCMD (GoTo, One-Click) ---
CMD_ASTRO_START_ONE_CLICK_GOTO_DSO = 11013
CMD_ASTRO_START_ONE_CLICK_GOTO_SOLAR_SYSTEM = 11014  # unverified, see design doc
CMD_ASTRO_STOP_ONE_CLICK_GOTO = 11015
CMD_NOTIFY_STATE_ASTRO_ONE_CLICK_GOTO = 15233

# --- AutoFocus state (astro.proto comment: 1=running, 3=complete) ---
AUTOFOCUS_STATE_RUNNING = 1
AUTOFOCUS_STATE_COMPLETE = 3
