"""Schema for KNX entity bridge configuration store."""

import voluptuous as vol

from homeassistant.const import CONF_ENTITY_ID, CONF_PLATFORM, Platform
from homeassistant.core import split_entity_id
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import VolSchemaType

from .entity_store_validation import validate_config_store_data
from .knx_selector import GASelector

CONF_CHANNELS = "channels"

# Each channel maps directly to a group address group. The status group address
# (`write`) carries Home Assistant state to KNX; the command group addresses
# (`state`/`passive`) are listened on to drive the entity. The DPT is fixed per channel
# in `channel.py`, so `valid_dpt` only guides the frontend picker.
SWITCH_BRIDGE_SCHEMA = vol.Schema(
    {
        vol.Required("switch"): GASelector(valid_dpt="1.001"),
    }
)

LIGHT_BRIDGE_SCHEMA = vol.Schema(
    {
        vol.Optional("switch"): GASelector(valid_dpt="1.001"),
        vol.Optional("brightness"): GASelector(valid_dpt="5.001"),
    }
)

# Read-only platform: only a status group address (no command listening).
BINARY_SENSOR_BRIDGE_SCHEMA = vol.Schema(
    {
        vol.Required("state"): GASelector(
            state=False, passive=False, write_required=True, valid_dpt="1.001"
        ),
    }
)

# up_down and stop are command-only (no status feedback); position is bidirectional.
COVER_BRIDGE_SCHEMA = vol.Schema(
    {
        vol.Optional("up_down"): GASelector(write=False, valid_dpt="1.008"),
        vol.Optional("stop"): GASelector(write=False, valid_dpt="1.010"),
        vol.Optional("position"): GASelector(valid_dpt="5.001"),
    }
)

BRIDGE_SCHEMA_FOR_PLATFORM: dict[Platform, VolSchemaType] = {
    Platform.SWITCH: SWITCH_BRIDGE_SCHEMA,
    Platform.LIGHT: LIGHT_BRIDGE_SCHEMA,
    Platform.BINARY_SENSOR: BINARY_SENSOR_BRIDGE_SCHEMA,
    Platform.COVER: COVER_BRIDGE_SCHEMA,
}


def _validate_entity_domain(config: dict) -> dict:
    """Ensure the target entity_id belongs to the configured platform."""
    if split_entity_id(config[CONF_ENTITY_ID])[0] != config[CONF_PLATFORM]:
        raise vol.Invalid(
            f"entity_id {config[CONF_ENTITY_ID]} does not match"
            f" platform {config[CONF_PLATFORM]}",
            path=[CONF_ENTITY_ID],
        )
    return config


ENTITY_BRIDGE_DATA_SCHEMA: VolSchemaType = vol.All(
    vol.Schema(
        {
            vol.Required(CONF_PLATFORM): vol.All(
                vol.Coerce(Platform), vol.In(BRIDGE_SCHEMA_FOR_PLATFORM)
            ),
            vol.Required(CONF_ENTITY_ID): cv.entity_id,
            vol.Required(CONF_CHANNELS): dict,
        },
        extra=vol.REMOVE_EXTRA,
    ),
    cv.key_value_schemas(
        CONF_PLATFORM,
        {
            platform: vol.Schema(
                {vol.Required(CONF_CHANNELS): channels_schema},
                extra=vol.ALLOW_EXTRA,
            )
            for platform, channels_schema in BRIDGE_SCHEMA_FOR_PLATFORM.items()
        },
    ),
    _validate_entity_domain,
)


def validate_entity_bridge_data(data: dict) -> dict:
    """Validate entity bridge data.

    Return validated data or raise EntityStoreValidationException.
    """
    return validate_config_store_data(ENTITY_BRIDGE_DATA_SCHEMA, data)
