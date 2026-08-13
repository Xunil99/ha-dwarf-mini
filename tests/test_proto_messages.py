# tests/test_proto_messages.py
from custom_components.dwarf_mini.proto_messages import (
    ComResWithInt,
    ReqAstroAutoFocus,
    ReqCaptureRawLiveStacking,
    ReqOneClickGotoDSO,
    ReqOneClickGotoSolarSystem,
    ReqStopCaptureRawLiveStacking,
    ReqStopOneClickGoto,
    ResNotifyFocus,
    ResNotifyOneClickGotoState,
    ResNotifyProgressCaptureRawLiveStacking,
    ResOneClickGoto,
    V3ResNotifyAutoFocusState,
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


def test_req_astro_auto_focus_roundtrip():
    msg = ReqAstroAutoFocus(mode=1)
    parsed = ReqAstroAutoFocus()
    parsed.ParseFromString(msg.SerializeToString())
    assert parsed.mode == 1


def test_res_notify_focus_roundtrip():
    msg = ResNotifyFocus(focus=1234)
    parsed = ResNotifyFocus()
    parsed.ParseFromString(msg.SerializeToString())
    assert parsed.focus == 1234


def test_req_stop_one_click_goto_has_no_fields():
    # Should not raise for an empty message.
    ReqStopOneClickGoto()


def test_req_one_click_goto_dso_roundtrip():
    msg = ReqOneClickGotoDSO(
        ra=10.5,
        dec=-5.25,
        target_name="M42",
        lon=13.405,
        lat=52.52,
        shooting_mode=1,
        goto_only=True,
    )
    parsed = ReqOneClickGotoDSO()
    parsed.ParseFromString(msg.SerializeToString())
    assert parsed.ra == 10.5
    assert parsed.dec == -5.25
    assert parsed.target_name == "M42"
    assert parsed.lon == 13.405
    assert parsed.lat == 52.52
    assert parsed.shooting_mode == 1
    assert parsed.goto_only is True


def test_res_notify_one_click_goto_state_roundtrip_with_nested_message():
    msg = ResNotifyOneClickGotoState(state=1)
    msg.phase_2.state = 1
    msg.phase_2.target_name = "phase2"
    msg.goto_state.state = 3
    msg.goto_state.target_name = "goto"
    msg.tracking_state.state = 1
    msg.tracking_state.target_name = "M31"

    parsed = ResNotifyOneClickGotoState()
    parsed.ParseFromString(msg.SerializeToString())

    assert parsed.state == 1
    assert parsed.phase_2.state == 1
    assert parsed.phase_2.target_name == "phase2"
    assert parsed.goto_state.state == 3
    assert parsed.goto_state.target_name == "goto"
    assert parsed.tracking_state.state == 1
    assert parsed.tracking_state.target_name == "M31"


def test_res_one_click_goto_roundtrip():
    msg = ResOneClickGoto(step=2, code=0, all_end=False)
    parsed = ResOneClickGoto()
    parsed.ParseFromString(msg.SerializeToString())
    assert parsed.step == 2
    assert parsed.code == 0
    assert parsed.all_end is False


def test_v3_res_notify_autofocus_state_roundtrip():
    msg = V3ResNotifyAutoFocusState(state=3)
    parsed = V3ResNotifyAutoFocusState()
    parsed.ParseFromString(msg.SerializeToString())
    assert parsed.state == 3


def test_req_one_click_goto_solar_system_roundtrip():
    msg = ReqOneClickGotoSolarSystem(
        index=9, lon=13.4, lat=52.5, target_name="Sonne",
        shooting_mode=2, force_start=False,
    )
    parsed = ReqOneClickGotoSolarSystem()
    parsed.ParseFromString(msg.SerializeToString())
    assert parsed.index == 9
    assert parsed.target_name == "Sonne"
    assert parsed.force_start is False
