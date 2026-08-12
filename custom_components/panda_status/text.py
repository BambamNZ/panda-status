# Custom integration to integrate panda_status with Home Assistant
#
# For more details about this integration, please refer to
# Copyright (c) 2024 Mitchell (github.com/ping-localhost/panda-status)
# Copyright (c) 2026 David Venter (github.com/BambamNZ/panda-status)
#
# SPDX-License-Identifier: MIT

"""Text platform for Panda Status integration."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from custom_components.panda_status import tools
from homeassistant.components.text import TextEntity, TextEntityDescription, TextMode
from homeassistant.const import EntityCategory
from homeassistant.core import callback

from .entity import PandaStatusEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import PandaStatusDataUpdateCoordinator
    from .data import PandaStatusConfigEntry

_LOGGER = logging.getLogger(__name__)

# Good enough to stop obviously malformed input in the HA UI - the device
# itself is the final authority on whether an address actually works as
# its own AP IP.
_IPV4_PATTERN = r"^(\d{1,3}\.){3}\d{1,3}$"

# Field names inside the device's "ap" websocket object.
_AP_FIELDS = ("ssid", "ip", "password")

ENTITY_DESCRIPTIONS = (
    TextEntityDescription(
        key="ap.ssid",
        name="AP SSID",
        icon="mdi:wifi",
        entity_category=EntityCategory.CONFIG,
        native_min=1,
        native_max=32,
        mode=TextMode.TEXT,
    ),
    TextEntityDescription(
        key="ap.ip",
        name="AP IP Address",
        icon="mdi:ip-network",
        entity_category=EntityCategory.CONFIG,
        pattern=_IPV4_PATTERN,
        native_max=15,
        mode=TextMode.TEXT,
    ),
    TextEntityDescription(
        key="ap.password",
        name="AP Password",
        icon="mdi:wifi-lock",
        entity_category=EntityCategory.CONFIG,
        native_min=8,
        native_max=63,
        mode=TextMode.PASSWORD,
        # Plaintext WiFi credential - the entity's state (and its history in
        # the recorder) holds the raw value regardless of the masked
        # "password" display mode, so keep it opt-in rather than on by
        # default for every install.
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: PandaStatusConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the text platform."""
    coordinator = entry.runtime_data.coordinator
    entities = [
        PandaStatusAPText(
            coordinator=coordinator,
            entity_description=entity_description,
        )
        for entity_description in ENTITY_DESCRIPTIONS
    ]
    async_add_entities(entities)


class PandaStatusAPText(PandaStatusEntity, TextEntity):
    """Editable AP field - SSID, IP address, or password.

    Only meaningful while the AP is switched on (see PandaStatusAPSwitch in
    switch.py) - the device doesn't report these fields with the AP off, and
    there's nothing to have confirmed the device accepts changes to an AP
    that isn't currently running, so this stays unavailable until it is.
    """

    def __init__(
        self,
        coordinator: PandaStatusDataUpdateCoordinator,
        entity_description: TextEntityDescription,
    ) -> None:
        """
        Initialize a PandaStatusAPText entity.

        Args:
            coordinator: The data update coordinator for panda_status.
            entity_description: Description of the text entity.

        """
        super().__init__(coordinator, entity_description)
        self.entity_description = entity_description
        # The field name inside the "ap" websocket object, e.g. "ssid" from
        # a key of "ap.ssid".
        self._ap_field = entity_description.key.split(".", 1)[1]
        self._attr_native_value = self._get_value_from_data()

    @property
    def available(self) -> bool:
        """Only settable while the AP is actually on."""
        if not super().available:
            return False
        return tools.extract_value(self.coordinator.data, "ap.on") == 1

    @callback
    def _handle_coordinator_update(self) -> None:
        self._attr_native_value = self._get_value_from_data()
        self.async_write_ha_state()

    def _get_value_from_data(self) -> str | None:
        """Get the current value from coordinator data."""
        return tools.extract_value(self.coordinator.data, self.entity_description.key)

    async def async_set_value(self, value: str) -> None:
        """Push a new value for this AP field to the device.

        set_ap appears to take the whole "ap" object rather than a partial
        patch - a real capture of a password-only change from the device
        still had ssid and ip present in the same command. So build the
        full object from the last known state and override just the field
        this entity owns, rather than sending it alone and risking the
        other two getting reset/cleared.
        """
        ap_state = {
            field: tools.extract_value(self.coordinator.data, f"ap.{field}")
            for field in _AP_FIELDS
        }
        ap_state[self._ap_field] = value
        payload = json.dumps({"ap": ap_state})
        await self.coordinator.config_entry.runtime_data.client.async_send(payload)
        self._attr_native_value = value
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()
