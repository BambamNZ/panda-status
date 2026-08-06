# Custom integration to integrate panda_status with Home Assistant
#
# For more details about this integration, please refer to
# Copyright (c) 2024 Mitchell (github.com/ping-localhost/panda-status)
# Copyright (c) 2026 Your Name (github.com/BambamNZ/panda-status)
#
# SPDX-License-Identifier: MIT

"""Constants for panda_status."""

from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

DOMAIN = "panda_status"

INVALID_URL_FORMAT = "invalid_url_format"
