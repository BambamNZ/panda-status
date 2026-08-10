# Custom integration to integrate panda_status with Home Assistant
#
# For more details about this integration, please refer to
# Copyright (c) 2024 Mitchell (github.com/ping-localhost/panda-status)
# Copyright (c) 2026 Your Name (github.com/BambamNZ/panda-status)
#
# SPDX-License-Identifier: MIT

"""WebSocket Client."""

from __future__ import annotations

import asyncio
import json
import logging

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, InvalidStatus

_LOGGER = logging.getLogger(__name__)

# Command acknowledgements (e.g. {"response": {"type": "set_ap", "ok": 1}})
# can be waiting on the socket right after a command is sent. A poll that
# lands on one of these instead of a real state push would otherwise hand
# the coordinator an envelope with none of the usual top-level keys,
# flapping every entity to unavailable/unknown until the next scheduled
# poll. Skip a bounded number of these per call and keep reading for the
# actual state message.
_MAX_ACK_SKIPS_PER_POLL = 3


def _is_command_ack(data: object) -> bool:
    """Return True if a message is a command acknowledgement, not state."""
    return isinstance(data, dict) and set(data.keys()) == {"response"}


class PandaStatusWebsocketError(Exception):
    """Exception to indicate a general WebSocket error."""


class PandaStatusWebsocketTimeoutError(
    PandaStatusWebsocketError,
):
    """Exception to indicate a timeout error."""


class PandaStatusWebsocketCommunicationError(
    PandaStatusWebsocketError,
):
    """Exception to indicate a communication error."""


class PandaStatusWebSocket:
    """WebSocket Client for Panda Status."""

    _url: str
    _session: ClientConnection

    def __init__(self, url: str, session: ClientConnection | None) -> None:
        """
        Initialize the WebSocket client.

        Args:
            url: The WebSocket URL.
            session: An optional existing ClientConnection.

        """
        self._url = url

        if session is None:
            self._session = connect(self._url)  # pyright: ignore[reportAttributeAccessIssue]
        else:
            self._session = session

    async def async_get_data(self) -> dict:
        """
        Fetch data from the WebSocket.

        Returns:
            Parsed JSON data from the WebSocket.

        Raises:
            PandaStatusWebsocketError: If JSON is invalid or connection fails.

        """
        try:
            # 1 second was workable when this connection only ever happened
            # right after a user action; now that the coordinator polls
            # periodically, that budget is regularly too tight for the
            # device's own connect+respond time and was causing frequent
            # false-negative "unavailable" flaps.
            async with asyncio.timeout(5):
                async with self._session as websocket:
                    for _ in range(_MAX_ACK_SKIPS_PER_POLL):
                        data = json.loads(await websocket.recv())
                        if not _is_command_ack(data):
                            break
                        _LOGGER.debug(
                            "Skipping command acknowledgement: %s",
                            json.dumps(data),
                        )
                    else:
                        msg = "Only received command acknowledgements, no state"
                        raise PandaStatusWebsocketTimeoutError(msg)  # noqa: TRY301
        except TimeoutError as e:
            msg = f"Timeout error getting data - {e}"
            raise PandaStatusWebsocketTimeoutError(msg) from e
        except (OSError, ConnectionClosed, TypeError, InvalidStatus) as e:
            msg = f"Communication error - {e}"
            raise PandaStatusWebsocketCommunicationError(msg) from e
        except PandaStatusWebsocketTimeoutError:
            raise
        except Exception as e:
            msg = f"Unexpected error parsing data payload - {e}"
            raise PandaStatusWebsocketError(msg) from e

        _LOGGER.debug("Latest data received: %s", json.dumps(data))

        return data

    async def async_send(self, payload: str) -> None:
        """
        Send a payload to the WebSocket.

        Args:
            payload: The string payload to send.

        Raises:
            PandaStatusWebsocketCommunicationError: On communication errors.
            PandaStatusWebsocketError: On unexpected errors.

        """
        try:
            _LOGGER.debug("Sending payload: %s", payload)
            async with asyncio.timeout(5):
                async with self._session as websocket:
                    await websocket.send(payload)
                    _LOGGER.debug("Payload sent: %s", payload)
        except TimeoutError as e:
            msg = f"Timeout error sending payload - {e}"
            raise PandaStatusWebsocketCommunicationError(msg) from e
        except (OSError, ConnectionClosed, TypeError) as e:
            msg = f"Communication error - {e}"
            raise PandaStatusWebsocketCommunicationError(msg) from e
        except Exception as e:
            msg = f"Unexpected error sending payload - {e}"
            raise PandaStatusWebsocketError(msg) from e
