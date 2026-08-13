import pytest

from custom_components.dwarf_mini.camera import DwarfMiniCamera


@pytest.mark.asyncio
async def test_tele_camera_stream_source(mock_config_entry):
    camera = DwarfMiniCamera(mock_config_entry, "tele", "ch0", "192.168.2.50")
    assert await camera.stream_source() == "rtsp://192.168.2.50:554/ch0/stream0"


@pytest.mark.asyncio
async def test_wide_camera_stream_source(mock_config_entry):
    camera = DwarfMiniCamera(mock_config_entry, "wide", "ch1", "192.168.2.50")
    assert await camera.stream_source() == "rtsp://192.168.2.50:554/ch1/stream0"


@pytest.mark.asyncio
async def test_camera_entities_set_up(hass, connected_client):
    """Genuine end-to-end wiring: both camera entities exist after real setup.

    Uses the shared `connected_client` fixture (tests/conftest.py): it builds
    the MockConfigEntry against fake_dwarf_server and runs the real
    async_setup_entry, so this proves the camera platform is registered in
    PLATFORMS and both entities are created, not just that the class works
    in isolation.
    """
    await hass.async_block_till_done()
    assert hass.states.get("camera.dwarf_mini_tele") is not None
    assert hass.states.get("camera.dwarf_mini_wide") is not None
