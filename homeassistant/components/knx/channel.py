"""Channel registry for KNX entity bridges.

A channel maps one controllable aspect of a Home Assistant entity (e.g. a switch's
on/off state) to a KNX datapoint with a fixed DPT and a predictable Home Assistant
service call. Channel behaviour is defined statically per platform here; the UI only
picks the group addresses. This keeps encode/decode symmetric (no value templates).
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from xknx import XKNX
from xknx.remote_value import RemoteValue, RemoteValueScaling, RemoteValueSwitch

from homeassistant.components.cover import ATTR_CURRENT_POSITION, ATTR_POSITION
from homeassistant.components.light import ATTR_BRIGHTNESS
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_CLOSE_COVER,
    SERVICE_OPEN_COVER,
    SERVICE_SET_COVER_POSITION,
    SERVICE_STOP_COVER,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    Platform,
)
from homeassistant.core import State


@dataclass(slots=True)
class BridgeServiceCall:
    """A Home Assistant service call resolved from an incoming KNX telegram."""

    domain: str
    service: str
    data: dict[str, Any]


@dataclass(frozen=True)
class ChannelDefinition:
    """Static definition of a bridge channel role for a platform.

    The status group address (``status_ga``, HA state -> KNX) and the command group
    addresses (``command_gas``, KNX -> HA action) are supplied per configuration.
    """

    remote_value_factory: Callable[[XKNX, str | None, list[str]], RemoteValue]
    read_state: Callable[[State], Any | None]
    to_service_call: Callable[[str, Any], BridgeServiceCall | None]


def _switch_remote_value(
    xknx: XKNX, status_ga: str | None, command_gas: list[str]
) -> RemoteValueSwitch:
    return RemoteValueSwitch(
        xknx,
        group_address=status_ga,
        group_address_state=command_gas or None,
        sync_state=False,
    )


def _switch_read_state(state: State) -> bool | None:
    if state.state == STATE_ON:
        return True
    if state.state == STATE_OFF:
        return False
    return None


def _switch_service_call(entity_id: str, value: bool) -> BridgeServiceCall:
    return BridgeServiceCall(
        domain=Platform.SWITCH,
        service=SERVICE_TURN_ON if value else SERVICE_TURN_OFF,
        data={ATTR_ENTITY_ID: entity_id},
    )


def _no_service_call(entity_id: str, value: object) -> None:
    """Read-only channel: never driven from the bus."""
    return


def _no_read_state(state: State) -> None:
    """Command-only channel: nothing to send to the bus."""
    return


def _light_switch_remote_value(
    xknx: XKNX, status_ga: str | None, command_gas: list[str]
) -> RemoteValueSwitch:
    return RemoteValueSwitch(
        xknx,
        group_address=status_ga,
        group_address_state=command_gas or None,
        sync_state=False,
    )


def _light_switch_service_call(entity_id: str, value: bool) -> BridgeServiceCall:
    return BridgeServiceCall(
        domain=Platform.LIGHT,
        service=SERVICE_TURN_ON if value else SERVICE_TURN_OFF,
        data={ATTR_ENTITY_ID: entity_id},
    )


def _brightness_remote_value(
    xknx: XKNX, status_ga: str | None, command_gas: list[str]
) -> RemoteValueScaling:
    # HA brightness (0-255) maps 1:1 to the DPT 5.001 raw byte
    return RemoteValueScaling(
        xknx,
        group_address=status_ga,
        group_address_state=command_gas or None,
        sync_state=False,
        range_from=0,
        range_to=255,
    )


def _brightness_read_state(state: State) -> int | None:
    return state.attributes.get(ATTR_BRIGHTNESS)


def _brightness_service_call(entity_id: str, value: int) -> BridgeServiceCall:
    return BridgeServiceCall(
        domain=Platform.LIGHT,
        service=SERVICE_TURN_ON,
        data={ATTR_ENTITY_ID: entity_id, ATTR_BRIGHTNESS: value},
    )


def _cover_updown_service_call(entity_id: str, value: bool) -> BridgeServiceCall:
    # DPT 1.008 UpDown: 0 = up (open), 1 = down (close)
    return BridgeServiceCall(
        domain=Platform.COVER,
        service=SERVICE_CLOSE_COVER if value else SERVICE_OPEN_COVER,
        data={ATTR_ENTITY_ID: entity_id},
    )


def _cover_stop_service_call(entity_id: str, value: bool) -> BridgeServiceCall | None:
    if not value:
        return None
    return BridgeServiceCall(
        domain=Platform.COVER,
        service=SERVICE_STOP_COVER,
        data={ATTR_ENTITY_ID: entity_id},
    )


def _cover_position_remote_value(
    xknx: XKNX, status_ga: str | None, command_gas: list[str]
) -> RemoteValueScaling:
    # KNX 0% = open maps to Home Assistant position 100 (open)
    return RemoteValueScaling(
        xknx,
        group_address=status_ga,
        group_address_state=command_gas or None,
        sync_state=False,
        range_from=100,
        range_to=0,
    )


def _cover_position_read_state(state: State) -> int | None:
    return state.attributes.get(ATTR_CURRENT_POSITION)


def _cover_position_service_call(entity_id: str, value: int) -> BridgeServiceCall:
    return BridgeServiceCall(
        domain=Platform.COVER,
        service=SERVICE_SET_COVER_POSITION,
        data={ATTR_ENTITY_ID: entity_id, ATTR_POSITION: value},
    )


CHANNELS: dict[Platform, dict[str, ChannelDefinition]] = {
    Platform.SWITCH: {
        "switch": ChannelDefinition(
            remote_value_factory=_switch_remote_value,
            read_state=_switch_read_state,
            to_service_call=_switch_service_call,
        ),
    },
    Platform.LIGHT: {
        "switch": ChannelDefinition(
            remote_value_factory=_light_switch_remote_value,
            read_state=_switch_read_state,
            to_service_call=_light_switch_service_call,
        ),
        "brightness": ChannelDefinition(
            remote_value_factory=_brightness_remote_value,
            read_state=_brightness_read_state,
            to_service_call=_brightness_service_call,
        ),
    },
    Platform.BINARY_SENSOR: {
        "state": ChannelDefinition(
            remote_value_factory=_switch_remote_value,
            read_state=_switch_read_state,
            to_service_call=_no_service_call,
        ),
    },
    Platform.COVER: {
        "up_down": ChannelDefinition(
            remote_value_factory=_switch_remote_value,
            read_state=_no_read_state,
            to_service_call=_cover_updown_service_call,
        ),
        "stop": ChannelDefinition(
            remote_value_factory=_switch_remote_value,
            read_state=_no_read_state,
            to_service_call=_cover_stop_service_call,
        ),
        "position": ChannelDefinition(
            remote_value_factory=_cover_position_remote_value,
            read_state=_cover_position_read_state,
            to_service_call=_cover_position_service_call,
        ),
    },
}
