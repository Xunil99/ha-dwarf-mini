# tests/test_select.py
import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.dwarf_mini.const import (
    CMD_ASTRO_START_ONE_CLICK_GOTO_DSO,
    CMD_ASTRO_START_ONE_CLICK_GOTO_SOLAR_SYSTEM,
    GOTO_DSO_TARGETS,
    GOTO_SOLAR_SYSTEM_TARGETS,
    MODULE_ASTRO,
)
from custom_components.dwarf_mini.proto_messages import (
    ReqOneClickGotoDSO,
    ReqOneClickGotoSolarSystem,
    ResOneClickGoto,
)


@pytest.mark.asyncio
async def test_select_dso_target_sends_correct_request(
    hass, fake_dwarf_server, connected_client
):
    """Selecting a DSO option sends ReqOneClickGotoDSO with the catalog's
    ra/dec and the current hass.config lat/lon - proving the select reads
    real coordinates rather than hardcoding placeholders."""
    received = []

    def _handler(data: bytes) -> bytes:
        payload = ReqOneClickGotoDSO()
        payload.ParseFromString(data)
        received.append(payload)
        return ResOneClickGoto(step=1, code=0, all_end=False).SerializeToString()

    fake_dwarf_server.app["handlers"][
        (MODULE_ASTRO, CMD_ASTRO_START_ONE_CLICK_GOTO_DSO)
    ] = _handler

    await hass.services.async_call(
        "select",
        "select_option",
        {
            "entity_id": "select.dwarf_mini_goto_target",
            "option": "M31 (Andromedagalaxie)",
        },
        blocking=True,
    )

    assert len(received) == 1
    expected_ra, expected_dec = GOTO_DSO_TARGETS["M31 (Andromedagalaxie)"]
    assert received[0].ra == pytest.approx(expected_ra)
    assert received[0].dec == pytest.approx(expected_dec)
    assert received[0].target_name == "M31 (Andromedagalaxie)"
    assert received[0].lon == pytest.approx(hass.config.longitude)
    assert received[0].lat == pytest.approx(hass.config.latitude)

    state = hass.states.get("select.dwarf_mini_goto_target")
    assert state.state == "M31 (Andromedagalaxie)"


@pytest.mark.asyncio
async def test_select_solar_system_target_sends_correct_request(
    hass, fake_dwarf_server, connected_client
):
    """Selecting a solar-system option sends ReqOneClickGotoSolarSystem with
    the catalog's index (9 for Sonne) and current hass.config lat/lon."""
    received = []

    def _handler(data: bytes) -> bytes:
        payload = ReqOneClickGotoSolarSystem()
        payload.ParseFromString(data)
        received.append(payload)
        return ResOneClickGoto(step=1, code=0, all_end=False).SerializeToString()

    fake_dwarf_server.app["handlers"][
        (MODULE_ASTRO, CMD_ASTRO_START_ONE_CLICK_GOTO_SOLAR_SYSTEM)
    ] = _handler

    await hass.services.async_call(
        "select",
        "select_option",
        {
            "entity_id": "select.dwarf_mini_goto_target",
            "option": "Sonne (experimentell)",
        },
        blocking=True,
    )

    assert len(received) == 1
    assert received[0].index == GOTO_SOLAR_SYSTEM_TARGETS["Sonne (experimentell)"] == 9
    assert received[0].target_name == "Sonne (experimentell)"
    assert received[0].lon == pytest.approx(hass.config.longitude)
    assert received[0].lat == pytest.approx(hass.config.latitude)

    state = hass.states.get("select.dwarf_mini_goto_target")
    assert state.state == "Sonne (experimentell)"


@pytest.mark.asyncio
async def test_solar_system_options_are_labelled_experimental():
    """Every solar-system catalog label (including 'Sonne') must carry an
    '(experimentell)' suffix so the dropdown itself flags these as
    unverified, distinct from the verified DSO targets - a mis-parsed
    unverified GoTo pointed at the Sun is a potential sensor-damage risk,
    not just a cosmetic one."""
    assert GOTO_SOLAR_SYSTEM_TARGETS, "catalog must not be empty"
    for label in GOTO_SOLAR_SYSTEM_TARGETS:
        assert "(experimentell)" in label, f"{label!r} is missing the experimental suffix"

    for label in GOTO_DSO_TARGETS:
        assert "(experimentell)" not in label, f"verified DSO target {label!r} should not be marked experimental"


@pytest.mark.asyncio
async def test_select_succeeds_on_zero_code_with_nonzero_step(
    hass, fake_dwarf_server, connected_client
):
    """Proves ResOneClickGoto (not ComResponse) is used to parse the response.

    ResOneClickGoto's wire layout is {step: 1, code: 2, all_end: 3}. Here
    step=1 (nonzero) and code=0 (success). If the response were mis-parsed
    as ComResponse (whose only field, `code`, sits at wire position 1 - the
    same slot `step` occupies here), that mis-parse would read the `step`
    value (1) as `code`, treat it as non-zero and incorrectly raise. Only
    the correct ResOneClickGoto parse reads the real `code` field (wire
    position 2, value 0) and lets this succeed silently.
    """

    def _handler(data: bytes) -> bytes:
        return ResOneClickGoto(step=1, code=0, all_end=False).SerializeToString()

    fake_dwarf_server.app["handlers"][
        (MODULE_ASTRO, CMD_ASTRO_START_ONE_CLICK_GOTO_DSO)
    ] = _handler

    await hass.services.async_call(
        "select",
        "select_option",
        {
            "entity_id": "select.dwarf_mini_goto_target",
            "option": "M31 (Andromedagalaxie)",
        },
        blocking=True,
    )

    state = hass.states.get("select.dwarf_mini_goto_target")
    assert state.state == "M31 (Andromedagalaxie)"


@pytest.mark.asyncio
async def test_select_raises_with_correct_code_on_rejection(
    hass, fake_dwarf_server, connected_client
):
    """Proves ResOneClickGoto (not ComResponse) is used to parse the response.

    step=1, code=5 (rejection). If mis-parsed as ComResponse, `code` would
    read wire position 1's value (step=1) instead of the real code (5), so
    the raised error would wrongly say "code=1" instead of "code=5" - this
    test's match="5" only passes with the correct ResOneClickGoto parse.
    """

    def _handler(data: bytes) -> bytes:
        return ResOneClickGoto(step=1, code=5, all_end=False).SerializeToString()

    fake_dwarf_server.app["handlers"][
        (MODULE_ASTRO, CMD_ASTRO_START_ONE_CLICK_GOTO_DSO)
    ] = _handler

    with pytest.raises(HomeAssistantError, match="5"):
        await hass.services.async_call(
            "select",
            "select_option",
            {
                "entity_id": "select.dwarf_mini_goto_target",
                "option": "M31 (Andromedagalaxie)",
            },
            blocking=True,
        )


@pytest.mark.asyncio
async def test_select_raises_when_home_location_not_configured(
    hass, fake_dwarf_server, connected_client
):
    """An unconfigured HA home location (HA's own core default: 0.0/0.0,
    see homeassistant.core_config.Config.latitude/longitude) must not be
    silently sent to the device as if it were real coordinates - that would
    produce a plausible-looking but wrong GoTo. Selecting a target in this
    state must raise before any request reaches the device."""
    hass.config.latitude = 0.0
    hass.config.longitude = 0.0

    received = []

    def _handler(data: bytes) -> bytes:
        received.append(data)
        return ResOneClickGoto(step=1, code=0, all_end=False).SerializeToString()

    fake_dwarf_server.app["handlers"][
        (MODULE_ASTRO, CMD_ASTRO_START_ONE_CLICK_GOTO_DSO)
    ] = _handler

    with pytest.raises(HomeAssistantError, match="Heimatort"):
        await hass.services.async_call(
            "select",
            "select_option",
            {
                "entity_id": "select.dwarf_mini_goto_target",
                "option": "M31 (Andromedagalaxie)",
            },
            blocking=True,
        )

    assert received == [], "no GoTo request may reach the device with an unconfigured location"
