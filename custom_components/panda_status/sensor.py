# Custom integration to integrate panda_status with Home Assistant
#
# For more details about this integration, please refer to
# Copyright (c) 2024 Mitchell (github.com/ping-localhost/panda-status)
# Copyright (c) 2026 Your Name (github.com/BambamNZ/panda-status)
#
# SPDX-License-Identifier: MIT

"""Sensor platform for Panda Status integration."""

from __future__ import annotations

from enum import Enum
import logging
from typing import TYPE_CHECKING, Any

from custom_components.panda_status import tools
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import EntityCategory

from .entity import PandaStatusEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import PandaStatusDataUpdateCoordinator
    from .data import PandaStatusConfigEntry

_LOGGER = logging.getLogger(__name__)


class BindingState(Enum):
    """An enumeration representing the binding status between the Panda module.

    Represents the binding status between the Panda module and the printer
    it is paired with, as reported by printer.state.

    Members:
        NOT_BOUND (int): No printer bound / not connected, value 0.
        BINDING_IN_PROGRESS (int): Binding handshake underway, value 2.
        CONNECTED (int): Bound and communicating normally, value 3.
        BINDING_FAILED (int): Binding attempt failed, value 4.
    """

    NOT_BOUND = 0
    BINDING_IN_PROGRESS = 2
    CONNECTED = 3
    BINDING_FAILED = 4

    @classmethod
    def from_value(cls, value: int) -> BindingState | None:
        """Return the BindingState corresponding to the given integer value.

        Unlike LightEffectMode.from_value, this deliberately returns None
        rather than defaulting to a member and logging a warning on every
        poll for an unmapped value - 1 is a known gap (not yet observed on
        hardware) and the coordinator polls every 60s, so a per-poll
        warning for a persistently-unbound value would just be log spam.
        Callers fall back to STATE_UNKNOWN instead.
        """
        for state in cls:
            if state.value == value:
                return state

        return None

    @classmethod
    def display_names(cls) -> dict[BindingState, str]:
        """Return a mapping of BindingState to display names."""
        return {
            cls.NOT_BOUND: "Not Bound",
            cls.BINDING_IN_PROGRESS: "Binding In Progress",
            cls.CONNECTED: "Connected",
            cls.BINDING_FAILED: "Binding Failed",
        }

    @property
    def display_name(self) -> str:
        """Return the display name for this BindingState."""
        return self.display_names().get(self, self.name)

    @classmethod
    def names(cls) -> list[str]:
        """Return a list of display names for each BindingState."""
        return [state.display_name for state in cls]


ENTITY_DESCRIPTIONS = (
    SensorEntityDescription(
        key="ap.ssid",
        name="AP SSID",
        icon="mdi:wifi",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="sta.ip",
        name="Device IP",
        icon="mdi:ip-network",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="sta.hostname",
        name="Hostname",
        icon="mdi:server-network",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="sta.state",
        name="WiFi State",
        icon="mdi:information-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="printer.name",
        name="Printer Name",
        icon="mdi:printer",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="printer.sn",
        name="Printer S/N",
        icon="mdi:numeric",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="printer.ip",
        name="Printer IP",
        icon="mdi:ip-network-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="printer.state",
        name="Printer Binding Status",
        icon="mdi:link-variant",
        device_class=SensorDeviceClass.ENUM,
        options=BindingState.names(),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: PandaStatusConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    coordinator = entry.runtime_data.coordinator
    entities = [
        PandaStatusSensor(
            coordinator=coordinator,
            entity_description=entity_description,
        )
        for entity_description in ENTITY_DESCRIPTIONS
    ]
    async_add_entities(entities)


class PandaStatusSensor(PandaStatusEntity, SensorEntity):
    """Representation of a Panda Status sensor."""

    def __init__(
        self,
        coordinator: PandaStatusDataUpdateCoordinator,
        entity_description: SensorEntityDescription,
    ) -> None:
        """Initialize a PandaStatusSensor with coordinator and entity description."""
        super().__init__(coordinator, entity_description)
        self.entity_description = entity_description

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        raw_value = tools.extract_value(
            self.coordinator.data, self.entity_description.key
        )

        if self.entity_description.key == "printer.state":
            if raw_value is None:
                return None

            state = BindingState.from_value(raw_value)
            if state is None:
                _LOGGER.debug(
                    "printer.state value %s does not match any known BindingState",
                    raw_value,
                )
                return None

            return state.display_name

        return raw_value
