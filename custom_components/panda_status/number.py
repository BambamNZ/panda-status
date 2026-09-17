# Custom integration to integrate panda_status with Home Assistant
#
# For more details about this integration, please refer to
# Copyright (c) 2024 Mitchell (github.com/ping-localhost/panda-status)
# Copyright (c) 2026 Your Name (github.com/BambamNZ/panda-status)
#
# SPDX-License-Identifier: MIT

"""Number platform for Panda Status integration."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from custom_components.panda_status import tools
from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import callback

from .entity import PandaStatusEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import PandaStatusDataUpdateCoordinator
    from .data import PandaStatusConfigEntry

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: PandaStatusConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the panda_status number platform."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        [
            PandaStatusSoundVolumeNumber(
                coordinator=coordinator,
                entity_description=NumberEntityDescription(
                    key="sound_volume",
                    name="Sound Volume",
                    icon="mdi:volume-high",
                    entity_category=EntityCategory.CONFIG,
                    native_min_value=0,
                    native_max_value=100,
                    native_step=1,
                    native_unit_of_measurement=PERCENTAGE,
                    mode=NumberMode.SLIDER,
                ),
            ),
        ]
    )


class PandaStatusSoundVolumeNumber(PandaStatusEntity, NumberEntity):
    """Representation of the Sound Volume slider.

    Payload confirmed via WebSocket capture: {"sound":{"volume":22}} etc,
    0-100 range, device default of 50 before any value has been set. Sent
    as a volume-only partial update, matching the capture exactly rather
    than assuming the full "sound" object (on + volume) needs to be
    resent together - unlike the "ap" object's ssid/ip/password fields,
    nothing so far suggests volume and on are coupled in the same way.

    Only settable while Sound Effects is on, same dependency as the
    Preview switch.
    """

    def __init__(
        self,
        coordinator: PandaStatusDataUpdateCoordinator,
        entity_description: NumberEntityDescription,
    ) -> None:
        """
        Initialize the Sound Volume number entity.

        Args:
            coordinator: The data update coordinator for panda_status.
            entity_description: Description of the number entity.

        """
        super().__init__(coordinator, entity_description)
        self.entity_description = entity_description
        self._attr_native_value = self._get_value_from_data()

    @property
    def available(self) -> bool:
        """Only settable while Sound Effects is on."""
        return super().available and bool(
            tools.extract_value(self.coordinator.data, "sound.on")
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        self._attr_native_value = self._get_value_from_data()
        self.async_write_ha_state()

    def _get_value_from_data(self) -> float | None:
        """Get the current volume from coordinator data."""
        return tools.extract_value(self.coordinator.data, "sound.volume")

    async def async_set_native_value(self, value: float) -> None:
        """Push a new volume to the device."""
        payload = json.dumps({"sound": {"volume": int(value)}})
        await self.coordinator.config_entry.runtime_data.client.async_send(payload)
        self._attr_native_value = value
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()
