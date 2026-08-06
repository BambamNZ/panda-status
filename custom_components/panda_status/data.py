# Custom integration to integrate panda_status with Home Assistant
#
# For more details about this integration, please refer to
# Copyright (c) 2024 Mitchell (github.com/ping-localhost/panda-status)
# Copyright (c) 2026 Your Name (github.com/BambamNZ/panda-status)
#
# SPDX-License-Identifier: MIT

"""Custom types for panda_status."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

    from .coordinator import PandaStatusDataUpdateCoordinator
    from .websocket import PandaStatusWebSocket


type PandaStatusConfigEntry = ConfigEntry[PandaStatusData]


@dataclass
class PandaStatusData:
    """Data for the PandaStatus integration."""

    client: PandaStatusWebSocket
    coordinator: PandaStatusDataUpdateCoordinator

    # Shared between the light and select entities so a mode switch can
    # carry the last colour HA sent along with it. The device remembers
    # colour independently per effect mode (confirmed via testing -
    # setting Static to blue then switching to Breathing does not carry
    # blue over, it shows Breathing's own last-remembered colour), which
    # reads as inconsistent from a human perspective. Overriding that by
    # re-sending this value on every mode change makes HA the source of
    # truth for colour instead of the device's per-mode memory. None
    # until the first colour is picked from HA in this session - see
    # light.py's PandaStatusRGBIdleLight for why this can never be seeded
    # from the device itself.
    last_rgb_color: tuple[int, int, int] | None = None
