"""Configuration flows."""

import errno
import logging
import asyncio
import aiohttp
import time
import io
import base64
from importlib import import_module
from datetime import timedelta

import homeassistant.helpers.config_validation as cv
import homeassistant.helpers.entity_registry as er
import voluptuous as vol
from homeassistant import config_entries, core, exceptions
from homeassistant.const import (
    CONF_DEVICES,
    CONF_ENTITIES,
    CONF_SCAN_INTERVAL,
)
from homeassistant.core import callback
from .hejiaqin import async_get_devices_list
from .const import (
    CONF_USER_INPUT,
    CONF_API_KEY,
    DOMAIN,
)
#from .discovery import discover

_LOGGER = logging.getLogger(__name__)

ENTRIES_VERSION = 1

DEFAULT_SCAN_INTERVAL = 60

CONFIGURE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SCAN_INTERVAL, default=60): int,
    }
)

CLOUD_SETUP_SCHEMA = vol.Schema(
    {    
        vol.Required(CONF_API_KEY): cv.string,
    }
)

def schema_defaults(schema, dps_list=None, **defaults):
    """Create a new schema with default values filled in."""
    copy = schema.extend({})
    for field, field_type in copy.schema.items():
        if isinstance(field_type, vol.In):
            value = None
            for dps in dps_list or []:
                if dps.startswith(f"{defaults.get(field)} "):
                    value = dps
                    break

            if value in field_type.container:
                field.default = vol.default_factory(value)
                continue

        if field.schema in defaults:
            field.default = vol.default_factory(defaults[field])
    return copy

async def attempt_connection(sunlogin, method = 1, *args):
    """Create device."""
    if method == 1:
        res = await sunlogin.async_get_access_token_by_password(*args)
    elif method == 2:
        res = await sunlogin.async_get_access_token_by_sms(*args)
    elif method == 3:
        res = await sunlogin.async_get_access_token_by_qrcode(*args)
    if res != "ok":
        _LOGGER.error("Cloud API connection failed: %s", res)
        return {"reason": "authentication_failed", "msg": res}

    res = await sunlogin.async_get_devices_list()
    if res != "ok":
        _LOGGER.error("Cloud API get_devices_list failed: %s", res)
        return {"reason": "device_list_failed", "msg": res}

    _LOGGER.info("Cloud API connection succeeded.")

    return {}


class HejiaqinConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Hejiaqin integration."""

    VERSION = ENTRIES_VERSION

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get options flow for this handler."""
        return HejiaqinOptionsFlowHandler(config_entry)

    def __init__(self):
        """Initialize a new HejiaqinConfigFlow."""
        self.api = None
        self.device_list = list()

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        placeholders = {}

        if user_input is not None:
            api_key = user_input.get(CONF_API_KEY)
            api_key = api_key.strip()
            user_input[CONF_API_KEY] = api_key
            error, resp = await async_get_devices_list(self.hass, api_key)
            if error is None:
                r_json = resp.json()
                devices = r_json.get(CONF_DEVICES, list())
                if len(devices) > 0:
                    self.device_list = devices
                    return await self._create_entry(user_input)
                
                errors["base"] = 'unknown'
                placeholders = {"msg": "no devices"}
            else:
                errors["base"] = 'unknown'
                placeholders = {"msg": error}

        return self.async_show_form(
            step_id="user",
            data_schema=CLOUD_SETUP_SCHEMA,
            errors=errors,
            description_placeholders=placeholders,
        )

    async def _create_entry(self, user_input):
        """Register new entry."""
        # if self._async_current_entries():
        #     return self.async_abort(reason="already_configured")
        unique_id = user_input[CONF_API_KEY]
        await self.async_set_unique_id(unique_id)

        devices = {}
        for dev in self.device_list:
            device_type = dev.get('type')
            device_id = dev.get('id')

            if device_type is not None and device_id is not None: #and dev.get('connected', True)
                dev[CONF_API_KEY] = user_input[CONF_API_KEY]
                devices[device_id] = dev
        
        user_input[CONF_SCAN_INTERVAL] = DEFAULT_SCAN_INTERVAL
        entry = {
            CONF_USER_INPUT: user_input, 
            CONF_DEVICES: devices, 
        }
        return self.async_create_entry(
            title='hejiaqin',
            data=entry,
        )
        
    async def async_step_import(self, user_input):
        """Handle import from YAML."""
        _LOGGER.error(
            "Configuration via YAML file is no longer supported by this integration."
        )


class HejiaqinOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Hejiaqin integration."""

    def __init__(self, config_entry):
        """Initialize hejiaqin options flow."""
        self.config_entry = config_entry
        # _LOGGER.debug(config_entry.entry_id)

    async def async_step_init(self, user_input=None):
        """Manage basic options."""
        old_scan_interval = self.hass.data[DOMAIN][CONF_SCAN_INTERVAL]
        defaults = {CONF_SCAN_INTERVAL: old_scan_interval}

        if user_input is not None:
            scan_interval = user_input.get(CONF_SCAN_INTERVAL, old_scan_interval)
            self.hass.data[DOMAIN][CONF_SCAN_INTERVAL] = scan_interval
            
            for device in self.hass.data[DOMAIN][SL_DEVICES][self.config_entry.entry_id]:
                await device.async_set_scan_interval(scan_interval)
            
            return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="init",
            data_schema=schema_defaults(CONFIGURE_SCHEMA, **defaults),
        )


    async def async_step_add_device(self, user_input=None):
        scan_interval = user_input.get(CONF_SCAN_INTERVAL)
        _LOGGER.debug("scan_interval: ", scan_interval)


    async def async_step_yaml_import(self, user_input=None):
        """Manage YAML imports."""
        _LOGGER.error(
            "Configuration via YAML file is no longer supported by this integration."
        )
        # if user_input is not None:
        #     return self.async_create_entry(title="", data={})
        # return self.async_show_form(step_id="yaml_import")

    @property
    def current_entity(self):
        """Existing configuration for entity currently being edited."""
        return self.entities[len(self.device_data[CONF_ENTITIES])]


class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(exceptions.HomeAssistantError):
    """Error to indicate there is invalid auth."""


class EmptyDpsList(exceptions.HomeAssistantError):
    """Error to indicate no datapoints found."""
