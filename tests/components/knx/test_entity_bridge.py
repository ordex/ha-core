"""Test KNX entity bridge."""

from typing import Any

from homeassistant.const import SERVICE_TURN_OFF, SERVICE_TURN_ON, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant

from .conftest import KNXTestKit

from tests.common import async_mock_service
from tests.typing import WebSocketGenerator

_STATUS_GA = "1/1/1"  # HA state -> KNX (outbound)
_COMMAND_GA = "2/2/2"  # KNX -> HA action (inbound)
_ENTITY_ID = "switch.test"


async def _create_switch_bridge(
    ws_client: Any,
    channels: dict[str, dict[str, Any]],
) -> str:
    """Create a switch entity bridge via websocket and return its unique_id."""
    await ws_client.send_json_auto_id(
        {
            "type": "knx/create_entity_bridge",
            "platform": "switch",
            "entity_id": _ENTITY_ID,
            "channels": channels,
        }
    )
    res = await ws_client.receive_json()
    assert res["success"], res
    return res["result"]["unique_id"]


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
