"""Test KNX entity bridge."""

from typing import Any

from homeassistant.components.climate import SERVICE_SET_TEMPERATURE
from homeassistant.const import (
    SERVICE_CLOSE_COVER,
    SERVICE_OPEN_COVER,
    SERVICE_SET_COVER_POSITION,
    SERVICE_STOP_COVER,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import HomeAssistant

from .conftest import KNXTestKit

from tests.common import async_mock_service
from tests.typing import WebSocketGenerator

_STATUS_GA = "1/1/1"  # HA state -> KNX (outbound)
_COMMAND_GA = "2/2/2"  # KNX -> HA action (inbound)
_ENTITY_ID = "switch.test"


async def _create_bridge(
    ws_client: Any,
    platform: str,
    entity_id: str,
    channels: dict[str, dict[str, Any]],
) -> str:
    """Create an entity bridge via websocket and return its unique_id."""
    await ws_client.send_json_auto_id(
        {
            "type": "knx/create_entity_bridge",
            "platform": platform,
            "entity_id": entity_id,
            "channels": channels,
        }
    )
    res = await ws_client.receive_json()
    assert res["success"], res
    return res["result"]["unique_id"]


async def _create_switch_bridge(
    ws_client: Any,
    channels: dict[str, dict[str, Any]],
) -> str:
    """Create a switch entity bridge via websocket and return its unique_id."""
    return await _create_bridge(ws_client, "switch", _ENTITY_ID, channels)


async def test_switch_bridge_outbound(
    hass: HomeAssistant,
    knx: KNXTestKit,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Test a Home Assistant state change is sent to the status group address."""
    await knx.setup_integration()
    ws_client = await hass_ws_client(hass)
    await _create_switch_bridge(
        ws_client, {"switch": {"write": _STATUS_GA, "state": _COMMAND_GA}}
    )

    hass.states.async_set(_ENTITY_ID, STATE_ON)
    await hass.async_block_till_done()
    await knx.assert_write(_STATUS_GA, True)

    hass.states.async_set(_ENTITY_ID, STATE_OFF)
    await hass.async_block_till_done()
    await knx.assert_write(_STATUS_GA, False)


async def test_switch_bridge_inbound(
    hass: HomeAssistant,
    knx: KNXTestKit,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Test an incoming command telegram drives the entity via a service call."""
    await knx.setup_integration()
    ws_client = await hass_ws_client(hass)
    await _create_switch_bridge(
        ws_client, {"switch": {"write": _STATUS_GA, "state": _COMMAND_GA}}
    )
    turn_on = async_mock_service(hass, "switch", SERVICE_TURN_ON)
    turn_off = async_mock_service(hass, "switch", SERVICE_TURN_OFF)

    await knx.receive_write(_COMMAND_GA, True)
    await hass.async_block_till_done()
    assert len(turn_on) == 1
    assert turn_on[0].data == {"entity_id": _ENTITY_ID}

    await knx.receive_write(_COMMAND_GA, False)
    await hass.async_block_till_done()
    assert len(turn_off) == 1


async def test_switch_bridge_no_echo(
    hass: HomeAssistant,
    knx: KNXTestKit,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Test the state change caused by an incoming command is not echoed back."""
    await knx.setup_integration()
    ws_client = await hass_ws_client(hass)
    await _create_switch_bridge(
        ws_client, {"switch": {"write": _STATUS_GA, "state": _COMMAND_GA}}
    )
    async_mock_service(hass, "switch", SERVICE_TURN_ON)

    await knx.receive_write(_COMMAND_GA, True)
    await hass.async_block_till_done()
    # the entity reacts to the command; the resulting state must not be re-sent
    hass.states.async_set(_ENTITY_ID, STATE_ON)
    await hass.async_block_till_done()
    await knx.assert_no_telegram()


async def test_switch_bridge_source_state_only(
    hass: HomeAssistant,
    knx: KNXTestKit,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Test a status-only bridge sends state but does not listen for commands."""
    await knx.setup_integration()
    ws_client = await hass_ws_client(hass)
    await _create_switch_bridge(ws_client, {"switch": {"write": _STATUS_GA}})
    turn_on = async_mock_service(hass, "switch", SERVICE_TURN_ON)

    # no command group address -> incoming writes are ignored
    await knx.receive_write(_STATUS_GA, True)
    await hass.async_block_till_done()
    assert len(turn_on) == 0

    hass.states.async_set(_ENTITY_ID, STATE_ON)
    await hass.async_block_till_done()
    await knx.assert_write(_STATUS_GA, True)


async def test_light_bridge_brightness(
    hass: HomeAssistant,
    knx: KNXTestKit,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Test the light brightness channel in both directions."""
    await knx.setup_integration()
    ws_client = await hass_ws_client(hass)
    await _create_bridge(
        ws_client,
        "light",
        "light.test",
        {"brightness": {"write": _STATUS_GA, "state": _COMMAND_GA}},
    )
    turn_on = async_mock_service(hass, "light", SERVICE_TURN_ON)

    # inbound: KNX brightness -> light.turn_on with brightness
    await knx.receive_write(_COMMAND_GA, (128,))
    await hass.async_block_till_done()
    assert len(turn_on) == 1
    assert turn_on[0].data == {"entity_id": "light.test", "brightness": 128}

    # outbound: brightness attribute -> KNX
    hass.states.async_set("light.test", STATE_ON, {"brightness": 200})
    await hass.async_block_till_done()
    await knx.assert_write(_STATUS_GA, (200,))


async def test_light_bridge_switch(
    hass: HomeAssistant,
    knx: KNXTestKit,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Test the light on/off channel drives light services."""
    await knx.setup_integration()
    ws_client = await hass_ws_client(hass)
    await _create_bridge(
        ws_client, "light", "light.test", {"switch": {"state": _COMMAND_GA}}
    )
    turn_on = async_mock_service(hass, "light", SERVICE_TURN_ON)
    turn_off = async_mock_service(hass, "light", SERVICE_TURN_OFF)

    await knx.receive_write(_COMMAND_GA, True)
    await hass.async_block_till_done()
    assert len(turn_on) == 1
    assert turn_on[0].data == {"entity_id": "light.test"}

    await knx.receive_write(_COMMAND_GA, False)
    await hass.async_block_till_done()
    assert len(turn_off) == 1


async def test_binary_sensor_bridge_outbound(
    hass: HomeAssistant,
    knx: KNXTestKit,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Test a read-only binary_sensor bridge sends state to KNX."""
    await knx.setup_integration()
    ws_client = await hass_ws_client(hass)
    await _create_bridge(
        ws_client,
        "binary_sensor",
        "binary_sensor.test",
        {"state": {"write": _STATUS_GA}},
    )

    hass.states.async_set("binary_sensor.test", STATE_ON)
    await hass.async_block_till_done()
    await knx.assert_write(_STATUS_GA, True)

    hass.states.async_set("binary_sensor.test", STATE_OFF)
    await hass.async_block_till_done()
    await knx.assert_write(_STATUS_GA, False)


async def test_cover_bridge(
    hass: HomeAssistant,
    knx: KNXTestKit,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Test cover up/down, stop and (inverted) position channels."""
    await knx.setup_integration()
    ws_client = await hass_ws_client(hass)
    await _create_bridge(
        ws_client,
        "cover",
        "cover.test",
        {
            "up_down": {"state": "1/0/1"},
            "stop": {"state": "1/0/2"},
            "position": {"write": _STATUS_GA, "state": "1/0/3"},
        },
    )
    open_cover = async_mock_service(hass, "cover", SERVICE_OPEN_COVER)
    close_cover = async_mock_service(hass, "cover", SERVICE_CLOSE_COVER)
    stop_cover = async_mock_service(hass, "cover", SERVICE_STOP_COVER)
    set_position = async_mock_service(hass, "cover", SERVICE_SET_COVER_POSITION)

    # DPT 1.008: 0 -> up (open), 1 -> down (close)
    await knx.receive_write("1/0/1", False)
    await hass.async_block_till_done()
    assert len(open_cover) == 1
    await knx.receive_write("1/0/1", True)
    await hass.async_block_till_done()
    assert len(close_cover) == 1

    # stop only on a set bit
    await knx.receive_write("1/0/2", True)
    await hass.async_block_till_done()
    assert len(stop_cover) == 1
    await knx.receive_write("1/0/2", False)
    await hass.async_block_till_done()
    assert len(stop_cover) == 1

    # inbound position: KNX 100% (raw 255) -> HA position 0 (closed)
    await knx.receive_write("1/0/3", (255,))
    await hass.async_block_till_done()
    assert len(set_position) == 1
    assert set_position[0].data == {"entity_id": "cover.test", "position": 0}

    # outbound position: HA position 100 (open) -> KNX 0% (raw 0)
    hass.states.async_set("cover.test", "open", {"current_position": 100})
    await hass.async_block_till_done()
    await knx.assert_write(_STATUS_GA, (0,))


# DPT 9.001 encoding of 21.0 degrees
_TEMP_21 = (0x0C, 0x1A)


async def test_climate_bridge(
    hass: HomeAssistant,
    knx: KNXTestKit,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Test climate current (read-only) and target temperature channels."""
    await knx.setup_integration()
    ws_client = await hass_ws_client(hass)
    await _create_bridge(
        ws_client,
        "climate",
        "climate.test",
        {
            "current_temperature": {"write": "1/0/1"},
            "target_temperature": {"write": _STATUS_GA, "state": _COMMAND_GA},
        },
    )
    set_temperature = async_mock_service(hass, "climate", SERVICE_SET_TEMPERATURE)

    # inbound target temperature -> climate.set_temperature
    await knx.receive_write(_COMMAND_GA, _TEMP_21)
    await hass.async_block_till_done()
    assert len(set_temperature) == 1
    assert set_temperature[0].data == {"entity_id": "climate.test", "temperature": 21.0}

    # outbound current temperature -> status group address
    hass.states.async_set("climate.test", "heat", {"current_temperature": 21.0})
    await hass.async_block_till_done()
    await knx.assert_write("1/0/1", _TEMP_21)
