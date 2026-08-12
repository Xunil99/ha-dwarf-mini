# tests/test_proto_messages.py
from custom_components.dwarf_mini.proto_messages import (
    ComResWithInt,
    ReqCaptureRawLiveStacking,
    ReqStopCaptureRawLiveStacking,
    ResNotifyProgressCaptureRawLiveStacking,
    WsPacket,
)


def test_ws_packet_roundtrip():
    packet = WsPacket()
    packet.major_version = 1
    packet.minor_version = 2
    packet.device_id = 1
    packet.module_id = 3
    packet.cmd = 11005
    packet.type = 0
    packet.data = b"\x01\x02"

    raw = packet.SerializeToString()
    parsed = WsPacket()
    parsed.ParseFromString(raw)

    assert parsed.module_id == 3
    assert parsed.cmd == 11005
    assert parsed.data == b"\x01\x02"


def test_com_res_with_int_roundtrip():
    msg = ComResWithInt(value=42, code=0)
    parsed = ComResWithInt()
    parsed.ParseFromString(msg.SerializeToString())
    assert parsed.value == 42


def test_req_capture_roundtrip():
    msg = ReqCaptureRawLiveStacking(ir_index=1, force_start=False)
    parsed = ReqCaptureRawLiveStacking()
    parsed.ParseFromString(msg.SerializeToString())
    assert parsed.ir_index == 1
    assert parsed.force_start is False


def test_req_stop_capture_has_no_fields():
    # Should not raise for an empty message.
    ReqStopCaptureRawLiveStacking()


def test_progress_notification_roundtrip():
    msg = ResNotifyProgressCaptureRawLiveStacking(
        total_count=10,
        current_count=3,
        stacked_count=2,
        exp_index=1,
        gain_index=1,
        target_name="M42",
    )
    parsed = ResNotifyProgressCaptureRawLiveStacking()
    parsed.ParseFromString(msg.SerializeToString())
    assert parsed.stacked_count == 2
    assert parsed.target_name == "M42"
