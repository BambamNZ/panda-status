# Custom integration to integrate panda_status with Home Assistant
#
# For more details about this integration, please refer to
# Copyright (c) 2024 Mitchell (github.com/ping-localhost/panda-status)
# Copyright (c) 2026 Your Name (github.com/BambamNZ/panda-status)
#
# SPDX-License-Identifier: MIT

"""Light platform for Panda Status integration."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any, ClassVar

from custom_components.panda_status import tools
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
    LightEntityDescription,
)
from homeassistant.core import callback

from .entity import PandaStatusEntity
from .select import COLOR_CAPABLE_MODES

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import PandaStatusDataUpdateCoordinator
    from .data import PandaStatusConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: PandaStatusConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the panda_status light platform."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        [
            PandaStatusRGBIdleLight(
                coordinator=coordinator,
                entity_description=LightEntityDescription(
                    key="rgb_idle_light",
                    name="RGB Idle Light",
                    icon="mdi:led-strip-variant",
                ),
            ),
        ]
    )


class PandaStatusRGBIdleLight(PandaStatusEntity, LightEntity):
    """Representation of the RGB Idle Light.

    Replaces the old rgb_idle_light switch. The device exposes a real
    on/off flag (led.on / settings.on) that is entirely separate from
    brightness (led.brightness / settings.list2[current_mode].brightness),
    so this is modelled as a brightness-only light rather than a switch
    that faked "on" by slamming brightness to 100.

    Confirmed via direct testing against the device: on/off must be sent
    as a single atomic payload including settings.current_mode - the
    device will not turn off without it.
    """

    def __init__(
        self,
        coordinator: PandaStatusDataUpdateCoordinator,
        entity_description: LightEntityDescription,
    ) -> None:
        """
        Initialize the RGB Idle Light entity.

        Args:
            coordinator: The data update coordinator for panda_status.
            entity_description: Description of the light entity.

        """
        super().__init__(coordinator, entity_description)
        self.entity_description = entity_description
        self._attr_is_on = self._get_on_state()
        self._attr_brightness = self._get_brightness()

        # Unlike on/off, brightness, and mode, the device never echoes the
        # active colour back over the WebSocket - confirmed by inspecting
        # the device's own web UI: its colour swatch (#colorButton) is
        # updated purely client-side by the JS click handler when a
        # colour is picked, with no corresponding field coming back in
        # any "settings" push. So there's no server-side truth to
        # reconcile against here; _handle_coordinator_update deliberately
        # never touches this. It seeds from runtime_data.last_rgb_color -
        # the one value shared with the select entity - rather than a
        # hardcoded None, so this entity reflects whatever colour was
        # last picked from HA even if it wasn't this entity that set it.
        self._attr_rgb_color = coordinator.config_entry.runtime_data.last_rgb_color
        self._refresh_color_mode()

    def _refresh_color_mode(self) -> None:
        """Switch between RGB and brightness-only depending on effect mode.

        Only STATIC/BREATHING/STROBING/MARQUEE (0-3) accept a custom
        colour - the rest are device-driven effects with no rgb_rgba
        concept, so the colour wheel is hidden for them rather than left
        showing a control that silently does nothing.
        """
        if self._current_mode() in COLOR_CAPABLE_MODES:
            self._attr_supported_color_modes: ClassVar[set[ColorMode]] = {ColorMode.RGB}
            self._attr_color_mode = ColorMode.RGB
        else:
            self._attr_supported_color_modes: ClassVar[set[ColorMode]] = {
                ColorMode.BRIGHTNESS
            }
            self._attr_color_mode = ColorMode.BRIGHTNESS

    def _get_on_state(self) -> bool | None:
        """Get the current on/off state from the real led.on flag."""
        on_state = tools.extract_value(self.coordinator.data, "led.on")
        if on_state is not None:
            return bool(on_state)
        return None

    def _get_brightness(self) -> int | None:
        """Get current brightness, converted from the device's 0-100 scale."""
        device_brightness = tools.extract_value(self.coordinator.data, "led.brightness")
        if device_brightness is None:
            return None
        return round(device_brightness / 100 * 255)

    def _current_mode(self) -> int:
        """Get the currently active rgb_info_mode, defaulting to 0."""
        mode = tools.extract_value(self.coordinator.data, "settings.current_mode")
        return mode if mode is not None else 0

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_is_on = self._get_on_state()
        self._attr_brightness = self._get_brightness()
        self._refresh_color_mode()
        self.async_write_ha_state()

    async def _async_reconcile_after_delay(self) -> None:
        """Reconcile with the device's real state after it has had time to settle.

        Each command opens a brand new WebSocket connection (see
        websocket.py) with no guarantee the device has finished applying it
        before that connection closes. Refreshing immediately after sending
        a command can therefore read back stale data and stomp the
        optimistic state set in async_turn_on/async_turn_off. Waiting a
        moment first, and running this as a background task rather than
        blocking the service call, avoids that without making the UI feel
        laggy.
        """
        await asyncio.sleep(1)
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the RGB Idle Light, optionally setting brightness/colour."""
        mode = self._current_mode()
        settings: dict[str, Any] = {
            "on": True,
            "current_mode": mode,
        }
        led: dict[str, Any] = {"on": True}

        device_brightness: int | None = None
        if ATTR_BRIGHTNESS in kwargs:
            # HA brightness is 0-255, device wants a 1-100 percentage.
            # Clamp to 1 rather than 0 - a 0% brightness "on" call would
            # visually look off but leave the device in an on/on state
            # mismatched with what the user asked for; turn_off handles
            # actually turning it off.
            #
            # Confirmed via WS sniffing of the device's own web UI: setting
            # brightness requires BOTH settings.rgb_info_brightness (as a
            # string) AND led.brightness (as an int) - the device does not
            # propagate the former into the latter on its own, and
            # led.brightness is the field this entity reads back for
            # display, so sending only the settings side left the UI
            # permanently stale regardless of how long a refresh waited.
            device_brightness = max(1, round(kwargs[ATTR_BRIGHTNESS] / 255 * 100))
            settings["rgb_info_brightness"] = str(device_brightness)
            led["brightness"] = device_brightness

        rgb_color: tuple[int, int, int] | None = None
        if ATTR_RGB_COLOR in kwargs and mode in COLOR_CAPABLE_MODES:
            # rgb_info_mode and rgb_rgba must travel in the same settings
            # payload as a single atomic update - same reasoning as
            # bundling on/off with current_mode above, and as the Follow
            # switch bundling rgb_info_mode with follow. Sending colour and
            # mode as two separate calls risks the device applying the
            # colour against whatever mode it still thinks is active.
            rgb_color = kwargs[ATTR_RGB_COLOR]
            settings["rgb_info_mode"] = mode
            settings["rgb_rgba"] = tools.rgb_to_hex(rgb_color)

        payload = json.dumps({"settings": settings, "led": led})
        await self.coordinator.config_entry.runtime_data.client.async_send(payload)

        # Update local state optimistically - this is the value the UI
        # shows immediately, ahead of the delayed reconciliation below.
        self._attr_is_on = True
        if device_brightness is not None:
            self._attr_brightness = round(device_brightness / 100 * 255)
        if rgb_color is not None:
            self._attr_rgb_color = rgb_color
            # Shared with the select entity so a subsequent mode change
            # carries this colour forward and overrides the device's own
            # per-mode colour memory - see PandaStatusData.last_rgb_color.
            self.coordinator.config_entry.runtime_data.last_rgb_color = rgb_color
        self.async_write_ha_state()

        self.hass.async_create_task(self._async_reconcile_after_delay())

    async def async_turn_off(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Turn off the RGB Idle Light without touching brightness."""
        payload = json.dumps(
            {
                "settings": {"on": False, "current_mode": self._current_mode()},
                "led": {"on": False},
            }
        )
        await self.coordinator.config_entry.runtime_data.client.async_send(payload)

        # See async_turn_on for why this is set optimistically rather than
        # waiting solely on a refresh.
        self._attr_is_on = False
        self.async_write_ha_state()

        self.hass.async_create_task(self._async_reconcile_after_delay())
