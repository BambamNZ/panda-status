# Custom integration to integrate panda_status with Home Assistant
#
# For more details about this integration, please refer to
# Copyright (c) 2024 Mitchell (github.com/ping-localhost/panda-status)
# Copyright (c) 2026 Your Name (github.com/BambamNZ/panda-status)
#
# SPDX-License-Identifier: MIT

"""Switch platform for Panda Status integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from custom_components.panda_status import tools
from homeassistant.components.switch import (
    SwitchDeviceClass,
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import callback

from .entity import PandaStatusEntity
from .select import LightEffectMode

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import PandaStatusDataUpdateCoordinator
    from .data import PandaStatusConfigEntry

_LOGGER = logging.getLogger(__name__)

# H2D Style (mode 7) is a fully device-driven effect and doesn't take a
# "follow printer light" setting - only modes 0-6 do.
_FOLLOW_UNSUPPORTED_MODE = LightEffectMode.H2D_STYLE.value


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: PandaStatusConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the panda_status switch platform."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        [
            PandaStatusAPSwitch(
                coordinator=coordinator,
                entity_description=SwitchEntityDescription(
                    key="ap",
                    name="AP Enabled",
                    icon="mdi:toggle-switch",
                    entity_category=EntityCategory.CONFIG,
                    device_class=SwitchDeviceClass.SWITCH,
                ),
            ),
            PandaStatusFollowPrinterLightSwitch(
                coordinator=coordinator,
                entity_description=SwitchEntityDescription(
                    key="follow_printer_light",
                    name="Follow Printer Light",
                    icon="mdi:printer-3d-sync",
                    entity_category=EntityCategory.CONFIG,
                    device_class=SwitchDeviceClass.SWITCH,
                ),
            ),
        ]
    )


class PandaStatusAPSwitch(PandaStatusEntity, SwitchEntity):
    """Representation of the AP Switch."""

    def __init__(
        self,
        coordinator: PandaStatusDataUpdateCoordinator,
        entity_description: SwitchEntityDescription,
    ) -> None:
        """
        Initialize the AP Switch entity.

        Args:
            coordinator: The data update coordinator for panda_status.
            entity_description: Description of the switch entity.

        """
        super().__init__(coordinator, entity_description)
        self.entity_description = entity_description
        self._attr_is_on = self._get_state_from_data()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._attr_is_on = self._get_state_from_data()
        self.async_write_ha_state()

    def _get_state_from_data(self) -> bool | None:
        """Get the current state from coordinator data."""
        last_msg = tools.extract_value(self.coordinator.data, "ap.on")
        if last_msg is not None:
            return last_msg == 1
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Turn on the AP."""
        await self.coordinator.config_entry.runtime_data.client.async_send(
            '{"ap":{"on":1}}'
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Turn off the AP."""
        await self.coordinator.config_entry.runtime_data.client.async_send(
            '{"ap":{"on":0}}'
        )
        await self.coordinator.async_request_refresh()


class PandaStatusFollowPrinterLightSwitch(PandaStatusEntity, SwitchEntity):
    """Representation of the Follow Printer Light switch.

    When enabled, the RGB idle light follows the printer's own screen/light
    state (e.g. turns off when the printer display sleeps). Only meaningful
    for light effect modes 0-6 - H2D Style (mode 7) is fully device-driven
    and doesn't take a follow setting, so this entity greys itself out
    whenever that mode is active.
    """

    def __init__(
        self,
        coordinator: PandaStatusDataUpdateCoordinator,
        entity_description: SwitchEntityDescription,
    ) -> None:
        """
        Initialize the Follow Printer Light switch entity.

        Args:
            coordinator: The data update coordinator for panda_status.
            entity_description: Description of the switch entity.

        """
        super().__init__(coordinator, entity_description)
        self.entity_description = entity_description
        self._attr_is_on = self._get_state_from_data()

    @property
    def available(self) -> bool:
        """Unavailable while H2D Style is active - it has no follow setting."""
        return super().available and self._current_mode() != _FOLLOW_UNSUPPORTED_MODE

    @callback
    def _handle_coordinator_update(self) -> None:
        self._attr_is_on = self._get_state_from_data()
        self.async_write_ha_state()

    def _get_state_from_data(self) -> bool | None:
        """Get the current follow state from coordinator data."""
        follow = tools.extract_value(self.coordinator.data, "settings.follow")
        if follow is not None:
            return bool(follow)
        return None

    def _current_mode(self) -> int:
        """Get the currently active rgb_info_mode, defaulting to 0."""
        mode = tools.extract_value(self.coordinator.data, "settings.current_mode")
        return mode if mode is not None else 0

    async def async_turn_on(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Turn on Follow Printer Light."""
        await self.coordinator.config_entry.runtime_data.client.async_send(
            '{"settings":{"rgb_info_mode":'
            + str(self._current_mode())
            + ',"follow":1}}'
        )
        self._attr_is_on = True
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Turn off Follow Printer Light."""
        await self.coordinator.config_entry.runtime_data.client.async_send(
            '{"settings":{"rgb_info_mode":'
            + str(self._current_mode())
            + ',"follow":0}}'
        )
        self._attr_is_on = False
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()
