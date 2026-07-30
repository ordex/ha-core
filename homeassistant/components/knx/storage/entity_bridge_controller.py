"""KNX configuration storage controller for entity bridges."""

from typing import Any, NotRequired, TypedDict

from xknx import XKNX

from homeassistant.core import HomeAssistant, callback

from ..entity_bridge import KnxEntityBridge


class KNXEntityBridgeStoreConfigModel(TypedDict):
    """Represent a stored KNX entity bridge configuration."""

    entity_id: str
    platform: str
    channels: dict[str, dict[str, Any]]  # role: channel configuration
    notes: NotRequired[str]


type KNXEntityBridgeStoreModel = dict[
    str, KNXEntityBridgeStoreConfigModel
]  # unique_id: config


class EntityBridgeController:
    """Controller managing UI-configured KNX entity bridges."""

    def __init__(self) -> None:
        """Initialize entity bridge controller."""
        self._bridges: dict[str, KnxEntityBridge] = {}

    @callback
    def stop(self) -> None:
        """Shutdown entity bridge controller."""
        for bridge in self._bridges.values():
            bridge.async_remove()
        self._bridges.clear()

    @callback
    def start(
        self, hass: HomeAssistant, xknx: XKNX, config: KNXEntityBridgeStoreModel
    ) -> None:
        """Set up all configured entity bridges."""
        if self._bridges:
            self.stop()
        for unique_id, bridge_config in config.items():
            self.update_bridge(hass, xknx, unique_id, bridge_config)

    @callback
    def update_bridge(
        self,
        hass: HomeAssistant,
        xknx: XKNX,
        unique_id: str,
        bridge_config: KNXEntityBridgeStoreConfigModel,
    ) -> None:
        """Create or replace an entity bridge."""
        self.remove_bridge(unique_id)
        bridge = KnxEntityBridge(
            hass,
            xknx,
            bridge_config["entity_id"],
            bridge_config["platform"],
            bridge_config["channels"],
        )
        self._bridges[unique_id] = bridge
        bridge.async_register()

    @callback
    def remove_bridge(self, unique_id: str) -> None:
        """Remove an entity bridge."""
        if unique_id in self._bridges:
            self._bridges.pop(unique_id).async_remove()
