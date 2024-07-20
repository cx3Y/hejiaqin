"""The SunLogin integration."""

import asyncio
import logging
import time
import requests
from datetime import timedelta

import homeassistant.helpers.config_validation as cv
import homeassistant.helpers.entity_registry as er
import voluptuous as vol
from aiohttp import web
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_DEVICE_ID,
    CONF_DEVICES,
    CONF_ENTITIES,
    CONF_PLATFORM,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_IP_ADDRESS,
    EVENT_HOMEASSISTANT_STOP,
    SERVICE_RELOAD,
)
from homeassistant.core import HomeAssistant
from homeassistant.components.http import HomeAssistantView
from homeassistant.exceptions import HomeAssistantError, Unauthorized
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.event import async_track_time_interval

from .hejiaqin import DNSUpdateManger, get_hejiaqin_device, device_filter, async_get_devices_list
# from .common import TuyaDevice, async_config_entry_by_device_id
from .config_flow import ENTRIES_VERSION
from .const import (
    CONFIG,
    CONF_USER_INPUT,
    CONF_TOKEN,
    CONF_ACCESS_TOKEN,
    CONF_REFRESH_TOKEN,
    CONF_REFRESH_EXPIRE,
    CONF_CONFIGURATION_UPDATE,
    CONF_DNS_UPDATE,
    CONF_RELOAD_FLAG,
    CONF_DEVICE_ADDRESS,
    CONF_API_KEY,
    CONF_SMARTPLUG,
    CONF_DEVICE_MODEL,
    CONF_DEVICE_NAME,
    CONF_DEVICE_SN,
    SL_DEVICES,
    CLOUD_DATA,
    DOMAIN,
    PLUG_DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

UNSUB_LISTENER = "unsub_listener"

RECONNECT_INTERVAL = timedelta(seconds=60)

# CONFIG_SCHEMA = config_schema()

CONF_DP = "dp"
CONF_VALUE = "value"


SERVICE_SET_DP = "set_dp"
SERVICE_SET_DP_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_DEVICE_ID): cv.string,
        vol.Required(CONF_DP): int,
        vol.Required(CONF_VALUE): object,
    }
)

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the LocalTuya integration component."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][CONFIG] = {}
    hass.data[DOMAIN][CONF_RELOAD_FLAG] = []


    async def _handle_set_dp(event):
        scan_interval = event.data[CONF_SCAN_INTERVAL]
        _LOGGER.debug("scan_interval: ", scan_interval)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up LocalTuya integration from a config entry."""
    # if entry.version < ENTRIES_VERSION:
    #     _LOGGER.debug(
    #         "Skipping setup for entry %s since its version (%s) is old",
    #         entry.entry_id,
    #         entry.version,
    #     )
    #     return

    _LOGGER.debug(entry.entry_id)
    _LOGGER.debug(entry.data)
    _LOGGER.debug(hass.data[DOMAIN][CONF_RELOAD_FLAG])
    if entry.entry_id in hass.data[DOMAIN][CONF_RELOAD_FLAG]:
        await async_hejiaqin_reload_entry(hass, entry)

    # dns_update = DNSUpdateManger(hass)
    config = {
        SL_DEVICES: list(),
    }
    hass.data[DOMAIN][CONFIG][entry.entry_id] = config
    hass.data[DOMAIN][CONF_SCAN_INTERVAL] = entry.data[CONF_USER_INPUT][CONF_SCAN_INTERVAL]
    # hass.data[DOMAIN][CONF_DNS_UPDATE] = dns_update
    # dns_update.dns.set_domain(PLUG_DOMAIN)
    # dns_update.devices = config[SL_DEVICES]

    async def setup_entities(device_ids):
        for dev_id in device_ids:
            device_config = entry.data[CONF_DEVICES][dev_id]
            device = await get_hejiaqin_device(hass, device_config)
            if device is None: continue
            config[SL_DEVICES].append(device)
            # await device.async_setup()


        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_setup(entry, platform)
                for platform in ['switch','sensor']
            ]
        )

        # await dns_update.coordinator.async_config_entry_first_refresh()
        for device in config[SL_DEVICES]:
            await device.async_setup()
        # await config_update.coordinator.async_config_entry_first_refresh()
        #await hass.config_entries.async_reload(entry.entry_id)

    
    hass.async_create_task(setup_entities(entry.data[CONF_DEVICES].keys()))
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an esphome config entry."""
    _LOGGER.debug("async_unload_entry")
    _LOGGER.debug(entry.entry_id)
    _LOGGER.debug(entry.data)
    config = hass.data[DOMAIN][CONFIG].pop(entry.entry_id)
    for device in config[SL_DEVICES]:
        await device.update_manager.coordinator.async_shutdown()
    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, component)
                for component in ['switch','sensor']
            ]
        )
    )
    if entry.entry_id not in hass.data[DOMAIN][CONF_RELOAD_FLAG]:
        hass.data[DOMAIN][CONF_RELOAD_FLAG].append(entry.entry_id)
    return unload_ok



async def async_hejiaqin_reload_entry(hass: HomeAssistant, entry: ConfigEntry):
    api_key = entry.data[CONF_USER_INPUT][CONF_API_KEY]
    error, resp = await async_get_devices_list(hass, api_key)
    if error is not None:
        pass
    
    update_flag = False
    r_json = resp.json()
    devices_list = r_json.get(CONF_DEVICES, list())
    devices = device_filter(devices_list, api_key)
    if len(devices) != len(entry.data[CONF_DEVICES]):
        update_flag = True

    if update_flag:
        devices.update(entry.data[CONF_DEVICES])
        new_data = {**entry.data}
        new_data[CONF_DEVICES] = devices
        hass.config_entries.async_update_entry(entry, data=new_data)

    hass.data[DOMAIN][CONF_RELOAD_FLAG].remove(entry.entry_id)
    _LOGGER.debug(entry.data)
    


# class SunloginQRView(HomeAssistantView):
#     """Display the sunlogin code at a protected url."""

#     url = "/api/sunlogin/loginqr"
#     name = "api:sunlogin:loginqr"
#     requires_auth = False

#     async def get(self, request: web.Request) -> web.Response:
#         """Retrieve the pairing QRCode image."""
#         if not request.query_string:
#             raise Unauthorized()
#         entry_id, secret = request.query_string.split("-")
#         _LOGGER.debug('%s, %s',entry_id, secret)
#         if (
#             entry_id not in request.app["hass"].data[DOMAIN]
#             or secret
#             != request.app["hass"].data[DOMAIN][entry_id][CONF_PAIRING_QR_SECRET]
#         ):
#             raise Unauthorized()
#         return web.Response(
#             body=request.app["hass"].data[DOMAIN][entry_id][CONF_PAIRING_QR],
#             content_type="image/svg+xml",
#         )
