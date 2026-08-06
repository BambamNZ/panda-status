# Custom integration to integrate panda_status with Home Assistant
#
# For more details about this integration, please refer to
# Copyright (c) 2024 Mitchell (github.com/ping-localhost/panda-status)
# Copyright (c) 2026 Your Name (github.com/BambamNZ/panda-status)
#
# SPDX-License-Identifier: MIT

"""Select platform for Panda Status integration."""

from __future__ import annotations

import asyncio
from enum import Enum
import json
import logging
from typing import TYPE_CHECKING, Any

from custom_components.panda_status import tools
from custom_components.panda_status.coordinator import PandaStatusDataUpdateCoordinator
from custom_components.panda_status.data import PandaStatusConfigEntry
from custom_components.panda_status.entity import PandaStatusEntity
from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import callback

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import PandaStatusDataUpdateCoordinator
    from .data import PandaStatusConfigEntry

_LOGGER = logging.getLogger(__name__)


class LightEffectMode(Enum):
    """
    An enumeration representing different light effect modes.

    Members:
        STATIC (int): Solid/static colour, value 0.
        BREATHING (int): Breathing fade effect, value 1.
        STROBING (int): Strobe effect, value 2.
        MARQUEE (int): Marquee/chase effect, value 3.
        COLOR_CYCLE (int): Colour cycle effect, value 4.
        RAINBOW (int): Rainbow effect, value 5.
        WARNING_HOT (int): Warning/hot indicator effect, value 6.
        H2D_STYLE (int): H2D style effect, value 7.
    """

    STATIC = 0
    BREATHING = 1
    STROBING = 2
    MARQUEE = 3
    COLOR_CYCLE = 4
    RAINBOW = 5
    WARNING_HOT = 6
    H2D_STYLE = 7

    @classmethod
    def from_value(cls, value: int) -> LightEffectMode:
        """Return the LightEffectMode corresponding to the given integer value."""
        for mode in cls:
            if mode.value == value:
                return mode

        _LOGGER.warning(
            "Value %d does not match any LightEffectMode, defaulting to STATIC", value
        )
        return cls.STATIC

    @classmethod
    def display_names(cls) -> dict[LightEffectMode, str]:
        """Return a mapping of LightEffectMode to display names."""
        return {
            cls.STATIC: "Static",
            cls.BREATHING: "Breathing",
            cls.STROBING: "Strobing",
            cls.MARQUEE: "Marquee",
            cls.COLOR_CYCLE: "Color Cycle",
            cls.RAINBOW: "Rainbow",
            cls.WARNING_HOT: "Warning Hot",
            cls.H2D_STYLE: "H2D Style",
        }

    @property
    def display_name(self) -> str:
        """Return the display name for this LightEffectMode."""
        return self.display_names().get(self, self.name)

    @classmethod
    def from_display_name(cls, value: str) -> LightEffectMode:
        """Return the LightEffectMode corresponding to a display name."""
        for mode, display_name in cls.display_names().items():
            if display_name.lower() == value.lower():
                return mode

        _LOGGER.warning(
            "Display name %s does not match any LightEffectMode, defaulting to STATIC",
            value,
        )
        return cls.STATIC

    @classmethod
    def names(cls) -> list[str]:
        """Return a list of display names for each LightEffectMode."""
        return [mode.display_name for mode in cls]


# Only these effect modes accept a custom colour from the user - the rest
# (Color Cycle, Rainbow, Warning Hot, H2D Style) are fully device-driven
# and have no rgb_rgba concept. Shared with light.py, which defines the
# actual colour picker; this lives here alongside the enum it describes
# to avoid a circular import (light.py already imports LightEffectMode
# from this module).
COLOR_CAPABLE_MODES = {
    LightEffectMode.STATIC.value,
    LightEffectMode.BREATHING.value,
    LightEffectMode.STROBING.value,
    LightEffectMode.MARQUEE.value,
}


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: PandaStatusConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the panda_status select platform."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        [
            LightEffectSelect(
                coordinator=coordinator,
                entity_description=SelectEntityDescription(
                    key="light_effect_mode",
                    name="Light Effect Mode",
                    icon="mdi:lightning-bolt",
                    entity_category=EntityCategory.CONFIG,
                ),
            ),
        ]
    )


class LightEffectSelect(PandaStatusEntity, SelectEntity):
    """Select to choose Light Effect mode."""

    def __init__(
        self,
        coordinator: PandaStatusDataUpdateCoordinator,
        entity_description: SelectEntityDescription,
    ) -> None:
        """
        Initialize the Light Effect Select entity.

        Args:
            coordinator: The data update coordinator for panda_status.
            entity_description: Description of the select entity.

        """
        super().__init__(coordinator, entity_description)
        self.entity_description = entity_description
        self._current_mode = self._get_state_from_data()

    @property
    def options(self) -> list[str]:
        """Returns a list of available light effect mode names."""
        return LightEffectMode.names()

    @property
    def current_option(self) -> str:
        """Return the currently selected light effect mode."""
        return self._current_mode.display_name

    async def async_select_option(self, option: str) -> None:
        """Change the selected light effect mode.

        The device remembers colour independently per effect mode -
        confirmed via testing: setting Static to blue, then switching to
        Breathing, shows Breathing's own last-remembered colour rather
        than carrying blue over. That reads as inconsistent from a human
        perspective, so this bundles runtime_data.last_rgb_color (the
        colour last picked from HA, shared with the light entity) into
        the same mode-change payload whenever the new mode is
        colour-capable. That overrides the device's per-mode memory with
        whatever HA last showed, making mode switches WYSIWYG. If no
        colour has been picked from HA yet this session, last_rgb_color
        is None and this falls back to the old behaviour - just changing
        mode and leaving colour untouched.
        """
        mode = LightEffectMode.from_display_name(option)
        settings: dict[str, Any] = {"rgb_info_mode": mode.value}

        last_color = self.coordinator.config_entry.runtime_data.last_rgb_color
        if mode.value in COLOR_CAPABLE_MODES and last_color is not None:
            settings["rgb_rgba"] = tools.rgb_to_hex(last_color)

        await self.coordinator.config_entry.runtime_data.client.async_send(
            json.dumps({"settings": settings})
        )
        self._current_mode = mode
        self.async_write_ha_state()

        # This entity's own optimistic state is written above, but other
        # entities (e.g. the Follow Printer Light switch) read
        # settings.current_mode straight off coordinator.data, and won't
        # see this change until the coordinator's data actually refreshes.
        # Without kicking a refresh here, they'd be stuck showing stale
        # state until the next scheduled 60s poll. Same delay-then-refresh
        # pattern as PandaStatusRGBIdleLight - give the device a moment to
        # settle before reading back, rather than racing it.
        self.hass.async_create_task(self._async_reconcile_after_delay())

    async def _async_reconcile_after_delay(self) -> None:
        """Refresh the coordinator shortly after sending a mode change.

        Each command opens a brand new WebSocket connection with no
        guarantee the device has finished applying it before that
        connection closes, so a short delay avoids reading back stale data.
        """
        await asyncio.sleep(1)
        await self.coordinator.async_request_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._current_mode = self._get_state_from_data()
        self.async_write_ha_state()

    def _get_state_from_data(self) -> LightEffectMode:
        """Get the current state from coordinator data."""
        mode = tools.extract_value(self.coordinator.data, "settings.current_mode")
        if mode is not None:
            return LightEffectMode.from_value(mode)

        return LightEffectMode.STATIC
