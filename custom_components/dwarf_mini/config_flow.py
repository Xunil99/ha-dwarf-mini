"""Config flow for DWARF mini."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import DwarfMiniClient
from .const import CONF_HOST, CONF_PORT, DEFAULT_PORT, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema({vol.Required(CONF_HOST): str})

# Upper bound on the initial connection test, in seconds. Without this,
# `client.connect()` falls back to aiohttp's own defaults (sock_connect=30s,
# total=300s), so a mistyped IP, a firewall silently dropping SYNs, or a
# powered-off-but-still-routed device would leave the config form hanging
# for up to 30s before failing. Kept as a module-level constant (rather than
# inlined) so tests can shrink it via monkeypatch instead of waiting out a
# real multi-second hang - mirrors the reconnect_initial_delay/
# reconnect_max_delay pattern in client.py.
CONNECT_TIMEOUT = 10


class DwarfMiniConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for DWARF mini."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST]
            await self.async_set_unique_id(host)
            self._abort_if_unique_id_configured()

            session = async_get_clientsession(self.hass)
            client = DwarfMiniClient(
                session=session, ws_url=f"ws://{host}:{DEFAULT_PORT}/"
            )
            try:
                await asyncio.wait_for(client.connect(), timeout=CONNECT_TIMEOUT)
            except (aiohttp.ClientError, OSError, asyncio.TimeoutError):
                # Realistic connect-failure surface only: network/socket
                # errors and our own timeout above. A bare `except Exception`
                # would also swallow real bugs (e.g. an AttributeError from a
                # DwarfMiniClient defect) and mis-report them to the user as
                # "cannot_connect" instead of surfacing/logging them properly.
                _LOGGER.debug("dwarf_mini: connection test failed", exc_info=True)
                errors["base"] = "cannot_connect"
                # Defense in depth: today's known failure paths (ws_connect()
                # itself raising, or our own CONNECT_TIMEOUT firing before the
                # websocket ever connects) never leave anything open here -
                # client.py's connect() now swallows a cancellation that
                # arrives after the websocket is already up (see its
                # docstring), so this except branch is only ever reached
                # while `client.connected` is still False. Closing
                # unconditionally anyway means a future connect() regression
                # can't quietly reintroduce a leaked websocket + reader task
                # behind this branch. close() no-ops cleanly when there is
                # nothing to close.
                await client.close()
            else:
                await client.close()
                return self.async_create_entry(
                    title=f"DWARF mini ({host})",
                    data={CONF_HOST: host, CONF_PORT: DEFAULT_PORT},
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )
