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
