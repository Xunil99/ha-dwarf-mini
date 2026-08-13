# custom_components/dwarf_mini/proto_messages.py
"""Hand-built protobuf message pool for the DWARF mini V3 websocket protocol.

Ported and reduced from dwarfAlp's src/dwarf_alpaca/proto/dwarf_messages.py
(https://github.com/acocalypso/dwarfAlp, GPLv3) — same technique (a DescriptorPool
built at import time) so no protoc build step is required for HACS users. Only the
messages needed for the v1 feature set (battery, live-stacking capture start/stop
and progress) are included; field layouts match dwarfAlp's
proto/base.proto, proto/astro.proto and proto/notify.proto.
"""
from __future__ import annotations

from dataclasses import dataclass

from google.protobuf import descriptor_pb2, descriptor_pool, message_factory
from google.protobuf.message import Message

from .const import (
    TYPE_NOTIFICATION,
    TYPE_NOTIFICATION_RESPONSE,
    TYPE_REQUEST,
    TYPE_REQUEST_RESPONSE,
)

# WsPacket.type values are re-exported here from const.py (single source of
# truth) so callers of this module don't need a separate import for them.
__all__ = [
    "WsPacket",
    "ComResponse",
    "ComResWithInt",
    "ReqCaptureRawLiveStacking",
    "ReqStopCaptureRawLiveStacking",
    "ResNotifyProgressCaptureRawLiveStacking",
    "ReqsetMasterLock",
    "ReqAstroAutoFocus",
    "ResNotifyFocus",
    "V3ResNotifyAutoFocusState",
    "ReqOneClickGotoDSO",
    "ReqOneClickGotoSolarSystem",
    "ResOneClickGoto",
    "ReqStopOneClickGoto",
    "OneClickGotoPhaseState",
    "ResNotifyOneClickGotoState",
    "TYPE_REQUEST",
    "TYPE_REQUEST_RESPONSE",
    "TYPE_NOTIFICATION",
    "TYPE_NOTIFICATION_RESPONSE",
]

F = descriptor_pb2.FieldDescriptorProto


@dataclass(frozen=True)
class _FieldSpec:
    name: str
    number: int
    type: int
    # for TYPE_MESSAGE fields, e.g. "OneClickGotoPhaseState"
    type_name: str | None = None


@dataclass(frozen=True)
class _MessageSpec:
    name: str
    fields: tuple[_FieldSpec, ...]


def _build_pool() -> descriptor_pool.DescriptorPool:
    pool = descriptor_pool.DescriptorPool()
    file_descriptor = descriptor_pb2.FileDescriptorProto()
    file_descriptor.name = "dwarf_mini_messages.proto"
    file_descriptor.package = "dwarf_mini"

    messages = (
        _MessageSpec(
            "WsPacket",
            (
                _FieldSpec("major_version", 1, F.TYPE_UINT32),
                _FieldSpec("minor_version", 2, F.TYPE_UINT32),
                _FieldSpec("device_id", 3, F.TYPE_UINT32),
                _FieldSpec("module_id", 4, F.TYPE_UINT32),
                _FieldSpec("cmd", 5, F.TYPE_UINT32),
                _FieldSpec("type", 6, F.TYPE_UINT32),
                _FieldSpec("data", 7, F.TYPE_BYTES),
                _FieldSpec("client_id", 8, F.TYPE_STRING),
            ),
        ),
        _MessageSpec("ComResponse", (_FieldSpec("code", 1, F.TYPE_INT32),)),
        _MessageSpec(
            "ComResWithInt",
            (
                _FieldSpec("value", 1, F.TYPE_INT32),
                _FieldSpec("code", 2, F.TYPE_INT32),
            ),
        ),
        _MessageSpec(
            "ReqCaptureRawLiveStacking",
            (
                _FieldSpec("ir_index", 1, F.TYPE_INT32),
                _FieldSpec("force_start", 2, F.TYPE_BOOL),
            ),
        ),
        _MessageSpec("ReqStopCaptureRawLiveStacking", ()),
        _MessageSpec(
            "ResNotifyProgressCaptureRawLiveStacking",
            (
                _FieldSpec("total_count", 1, F.TYPE_INT32),
                _FieldSpec("update_count_type", 2, F.TYPE_INT32),
                _FieldSpec("current_count", 3, F.TYPE_INT32),
                _FieldSpec("stacked_count", 4, F.TYPE_INT32),
                _FieldSpec("exp_index", 5, F.TYPE_INT32),
                _FieldSpec("gain_index", 6, F.TYPE_INT32),
                _FieldSpec("target_name", 7, F.TYPE_STRING),
            ),
        ),
        _MessageSpec("ReqsetMasterLock", (_FieldSpec("lock", 1, F.TYPE_BOOL),)),
        _MessageSpec(
            "ReqAstroAutoFocus", (_FieldSpec("mode", 1, F.TYPE_UINT32),)
        ),
        _MessageSpec(
            "ResNotifyFocus", (_FieldSpec("focus", 1, F.TYPE_INT32),)
        ),
        _MessageSpec(
            "V3ResNotifyAutoFocusState", (_FieldSpec("state", 1, F.TYPE_INT32),)
        ),
        _MessageSpec(
            "ReqOneClickGotoDSO",
            (
                _FieldSpec("ra", 1, F.TYPE_DOUBLE),
                _FieldSpec("dec", 2, F.TYPE_DOUBLE),
                _FieldSpec("target_name", 3, F.TYPE_STRING),
                _FieldSpec("lon", 4, F.TYPE_DOUBLE),
                _FieldSpec("lat", 5, F.TYPE_DOUBLE),
                _FieldSpec("shooting_mode", 6, F.TYPE_INT32),
                _FieldSpec("goto_only", 7, F.TYPE_BOOL),
            ),
        ),
        _MessageSpec(
            "ReqOneClickGotoSolarSystem",
            (
                _FieldSpec("index", 1, F.TYPE_INT32),
                _FieldSpec("lon", 2, F.TYPE_DOUBLE),
                _FieldSpec("lat", 3, F.TYPE_DOUBLE),
                _FieldSpec("target_name", 4, F.TYPE_STRING),
                _FieldSpec("shooting_mode", 5, F.TYPE_INT32),
                _FieldSpec("force_start", 6, F.TYPE_BOOL),
            ),
        ),
        _MessageSpec(
            "ResOneClickGoto",
            (
                _FieldSpec("step", 1, F.TYPE_INT32),
                _FieldSpec("code", 2, F.TYPE_INT32),
                _FieldSpec("all_end", 3, F.TYPE_BOOL),
            ),
        ),
        _MessageSpec("ReqStopOneClickGoto", ()),
        _MessageSpec(
            "OneClickGotoPhaseState",
            (
                _FieldSpec("state", 1, F.TYPE_INT32),
                _FieldSpec("target_name", 2, F.TYPE_STRING),
            ),
        ),
        _MessageSpec(
            "ResNotifyOneClickGotoState",
            (
                _FieldSpec("state", 1, F.TYPE_INT32),
                _FieldSpec("phase_2", 2, F.TYPE_MESSAGE, "OneClickGotoPhaseState"),
                _FieldSpec("goto_state", 3, F.TYPE_MESSAGE, "OneClickGotoPhaseState"),
                _FieldSpec(
                    "tracking_state", 4, F.TYPE_MESSAGE, "OneClickGotoPhaseState"
                ),
            ),
        ),
    )

    for spec in messages:
        msg_descriptor = file_descriptor.message_type.add()
        msg_descriptor.name = spec.name
        for field_spec in spec.fields:
            field = msg_descriptor.field.add()
            field.name = field_spec.name
            field.number = field_spec.number
            field.type = field_spec.type
            field.label = F.LABEL_OPTIONAL
            if field_spec.type_name:
                field.type_name = f".dwarf_mini.{field_spec.type_name}"

    pool.Add(file_descriptor)
    return pool


_POOL = _build_pool()


def _message_class(name: str) -> type[Message]:
    descriptor = _POOL.FindMessageTypeByName(f"dwarf_mini.{name}")
    return message_factory.GetMessageClass(descriptor)


WsPacket = _message_class("WsPacket")
ComResponse = _message_class("ComResponse")
ComResWithInt = _message_class("ComResWithInt")
ReqCaptureRawLiveStacking = _message_class("ReqCaptureRawLiveStacking")
ReqStopCaptureRawLiveStacking = _message_class("ReqStopCaptureRawLiveStacking")
ResNotifyProgressCaptureRawLiveStacking = _message_class(
    "ResNotifyProgressCaptureRawLiveStacking"
)
ReqsetMasterLock = _message_class("ReqsetMasterLock")
ReqAstroAutoFocus = _message_class("ReqAstroAutoFocus")
ResNotifyFocus = _message_class("ResNotifyFocus")
V3ResNotifyAutoFocusState = _message_class("V3ResNotifyAutoFocusState")
ReqOneClickGotoDSO = _message_class("ReqOneClickGotoDSO")
ReqOneClickGotoSolarSystem = _message_class("ReqOneClickGotoSolarSystem")
ResOneClickGoto = _message_class("ResOneClickGoto")
ReqStopOneClickGoto = _message_class("ReqStopOneClickGoto")
OneClickGotoPhaseState = _message_class("OneClickGotoPhaseState")
ResNotifyOneClickGotoState = _message_class("ResNotifyOneClickGotoState")
