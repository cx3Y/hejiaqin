import functools
import hashlib
import json
import logging
import time
import uuid
import math
import base64
import asyncio
import requests
import pyqrcode
import io
import async_timeout
import aiohttp
from .hejiaqin_api import CloudAPI, PlugAPI
# from .fake_data import GET_PLUG_ELECTRIC_FAKE_DATA_P8, GET_PLUG_STATUS_FAKE_DATA_P8
from .dns_api import DNS
# from .sunlogin_api import PlugAPI_V2 as PlugAPI
from datetime import timedelta, datetime, timezone

from abc import ABC, abstractmethod
from urllib.parse import urlencode
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.restore_state import async_get
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed
)
from homeassistant.util import dt as dt_util
from homeassistant.const import (
    CONF_UNIT_OF_MEASUREMENT,
    CONF_PLATFORM,
    CONF_DEVICES,
)
from homeassistant.components import persistent_notification
from homeassistant import config_entries

from .const import (
    DOMAIN,
    PLUG_DOMAIN,
    PLUG_URL,
    SL_DEVICES,
    BLANK_SN,
    CONFIG,
    CONF_TOKEN,
    CONF_API_KEY,
    CONF_SMARTPLUG,
    CONF_DEVICE_ID,
    CONF_DEVICE_SN,
    CONF_DEVICE_MAC,
    CONF_DEVICE_NAME,
    CONF_DEVICE_DESC,
    CONF_DEVICE_TYPE,
    CONF_DEVICE_MODEL,
    CONF_DEVICE_MEMOS,
    CONF_DEVICE_VERSION,
    CONF_DEVICE_ADDRESS,
    CONF_DEVICE_IP_ADDRESS,
    CONF_ACCESS_TOKEN,
    CONF_REFRESH_TOKEN,
    CONF_REFRESH_EXPIRE,
    CONF_DNS_UPDATE,
    CONF_RELOAD_FLAG,
    HTTP_SUFFIX, 
    LOCAL_PORT,
)


_LOGGER = logging.getLogger(__name__)

UPDATE_FLAG_SN = 'update_flag_sn'
UPDATE_FLAG_IP = 'update_flag_ip'
UPDATE_FLAG_VERSION = 'update_flag_version'

DP_RELAY_0 = "relay0"
DP_RELAY_1 = "relay1"
DP_RELAY_2 = "relay2"
DP_RELAY_3 = "relay3"
DP_RELAY_4 = "relay4"
DP_RELAY_5 = "relay5"
DP_RELAY_6 = "relay6"
DP_RELAY_7 = "relay7"
DP_LED = "led"
DP_DEFAULT = "def_st"
DP_REMOTE = "remote"
DP_RELAY = "response"
DP_CHILDREN_LOCK = "children_lock"
DP_CURRENT_PROTECT = "current_protect"
DP_VOLTAGE_PROTECT = "voltage_protect"
DP_IP_ADDRESS = "ip_address"
DP_ELECTRIC = "electric"
DP_POWER = "power"
DP_CURRENT = "current"
DP_VOLTAGE = "voltage"
DP_POWER_CONSUMPTION = "power_consumption"
DP_ELECTRICITY_HOUR = "electricity_hour"
DP_ELECTRICITY_DAY = "electricity_day"
DP_ELECTRICITY_WEEK = "electricity_week"
DP_ELECTRICITY_MONTH = "electricity_month"
DP_ELECTRICITY_LASTMONTH = "electricity_lastmonth"

PLATFORM_OF_ENTITY = {
    DP_LED: "switch",
    DP_DEFAULT: "switch",
    DP_CHILDREN_LOCK: "switch",
    DP_CURRENT_PROTECT: "switch",
    DP_VOLTAGE_PROTECT: "switch",
    DP_RELAY_0: "switch",
    DP_RELAY_1: "switch",
    DP_RELAY_2: "switch",
    DP_RELAY_3: "switch",
    DP_RELAY_4: "switch",
    DP_RELAY_5: "switch",
    DP_RELAY_6: "switch",
    DP_RELAY_7: "switch",
    DP_REMOTE: "switch",
    DP_ELECTRIC: "sensor",
    DP_POWER: "sensor",
    DP_CURRENT: "sensor",
    DP_VOLTAGE: "sensor",
    DP_POWER_CONSUMPTION: "sensor",
    DP_ELECTRICITY_HOUR: "sensor",
    DP_ELECTRICITY_DAY: "sensor",
    DP_ELECTRICITY_WEEK: "sensor",
    DP_ELECTRICITY_MONTH: "sensor",
    DP_ELECTRICITY_LASTMONTH: "sensor",
    DP_IP_ADDRESS: "sensor",
}
ELECTRIC_ENTITY = [DP_POWER_CONSUMPTION, DP_POWER, DP_CURRENT, DP_VOLTAGE]
SLOT_X_WITHOUT_ELECTRIC = [DP_LED, DP_DEFAULT, DP_CHILDREN_LOCK, DP_RELAY_0, DP_RELAY_1, DP_RELAY_2, DP_RELAY_3, DP_RELAY_4, DP_RELAY_5, DP_RELAY_6, DP_RELAY_7]
SLOT_X_WITH_ELECTRIC = ELECTRIC_ENTITY + SLOT_X_WITHOUT_ELECTRIC


async def async_request_error_process(func, *args):
    error = None
    resp = None
    try:
        resp = await func(*args)
    except requests.exceptions.ConnectionError:
        error = "Request failed, status ConnectionError"
        return error, resp
    
    if not resp.ok:
        try: 
            r_json = resp.json()
        except: 
            error = "Response can't cover to JSON"
            return error, resp
        error = r_json.get('error', 'unkown')
        return error, resp
    
    r_json = resp.json()
    if  r_json.get('resultCode', -1) != 0:
        error = r_json.get('resultCodeDesc', 'unkown')
        return error, resp
    
    return error, resp

async def async_get_devices_list(hass, api_key):
    api = CloudAPI(hass)
    error, resp = await async_request_error_process(api.async_get_devices_list, api_key)
    return error, resp

def device_filter(device_list, api_key):
    devices = dict()
    for dev in device_list:
        device_type = dev.get('type', 'unknow')
        device_id = dev.get('id')

        if device_type is not None and device_id is not None: #and dev.get('connected', True)
            dev[CONF_API_KEY] = api_key
            devices[device_id] = dev

    return devices

async def get_hejiaqin_device(hass, config):
    # model = config.get(CONF_DEVICE_MODEL)
    type_id = config.get(CONF_DEVICE_TYPE)
    if type_id == 590384:
        return X1S(hass, config)
    elif type_id == 590505:
        return SP5F_CNA(hass, config)
    else:
        device = UnkownDevice(hass, config)
        await device.async_get_detail()
        return device

def get_plug_memos(config):
    memos = dict()
    model = config.get(CONF_DEVICE_MODEL)

    for item in config.get(CONF_DEVICE_MEMOS, []):
        index = item.get('number', 0)
        name = item.get('name')
        if name is not None:
            memos.update({f'relay{index}': name})
            if 'P8' in model:
                memos.update({f'sub_power{index}': name})
                memos.update({f'sub_current{index}': name})
                memos.update({f'sub_electricity_hour{index}': name})
                memos.update({f'sub_electricity_day{index}': name})
                memos.update({f'sub_electricity_week{index}': name})
                memos.update({f'sub_electricity_month{index}': name})
                memos.update({f'sub_electricity_lastmonth{index}': name})

    return memos
    

def plug_status_process(data):
    status = dict()
    dp_id = {
        "childrenLock":DP_CHILDREN_LOCK, 
        "signalLight": DP_LED, 
        "pwCutMemory": DP_DEFAULT, 
        "outletStatus": DP_RELAY_0,
        "powerSwitch": DP_RELAY_0,
        "overCurrentProtect": DP_CURRENT_PROTECT,
        "overVoltageProtect": DP_VOLTAGE_PROTECT,
    }
    for dev_status in data.get('parameters', ''):
        name = dev_status.get('name','_')
        value = dev_status.get('value')
        if (key := dp_id.get(name)) is not None and value is not None:
            status[key] = int(value)

    return status

def plug_electric_process(data):
    status = dict()
    dp_id = {
        "powerConsumption": DP_POWER_CONSUMPTION,
        "power": DP_POWER,
        "volts": DP_VOLTAGE,
        "current": DP_CURRENT,
    }
    for dev_status in data.get('parameters', ''):
        name = dev_status.get('name','_')
        value = dev_status.get('value')
        if (key := dp_id.get(name)) is not None and value is not None:
            status[key] = float(value)

    if ((status.get(DP_VOLTAGE) is not None
        and status.get(DP_CURRENT) is not None)
        and status.get(DP_POWER) is None
    ):
        status[DP_POWER] = status[DP_VOLTAGE] * status[DP_CURRENT]
    return status

def plug_info_process(data):
    status = dict()
    dp_id = {
        "ipAddress": DP_IP_ADDRESS,
    }
    for dev_status in data.get('parameters', ''):
        name = dev_status.get('name','_')
        value = dev_status.get('value')
        if (key := dp_id.get(name)) is not None and value is not None:
            status[key] = value

    return status

def plug_power_consumes_process(data, index=0):
    status = dict()
    

    return status

    
class HejiaqinDevice(ABC):
    hass = None
    config = None
    api = None
    update_manager = None
    _entities = None
    _sn = BLANK_SN
    _fw_version = "0.0.0"
        # self.reset_jobs: list[CALLBACK_TYPE] = []

    @property
    def name(self) -> str:
        """Return the name of the device."""
        return self.config.get(CONF_DEVICE_DESC, 'CMCC Device')##

    @property
    def device_type(self) -> str:
        return self.config.get(CONF_DEVICE_TYPE, 'unknow')
    
    @property
    def model(self) -> str:
        return self.config.get(CONF_DEVICE_MODEL, 'CMCC generic')
    
    @property
    def sn(self) -> str:
        return self._sn
    
    @sn.setter
    def sn(self, sn):
        if sn is not None:
            self._sn = sn

    @property
    def unique_id(self) -> str | None:
        """Return the unique id of the device."""
        return self.config.get(CONF_DEVICE_ID)
    
    @property
    def _unique_id(self) -> str | None:
        """Return the unique id of the device."""
        unique_id = self.config.get(CONF_DEVICE_ID)
        if unique_id is not None:
            unique_id.replace('-', '_')
        return unique_id

    @property
    def mac_address(self) -> str:
        """Return the mac address of the device."""
        return self.config.get(CONF_DEVICE_MAC)

    @property
    def available(self) -> bool | None:
        """Return True if the device is available."""
        if self.update_manager is None:
            return False
        return self.update_manager.available

    @property
    def fw_version(self):
        return self._fw_version
    
    @fw_version.setter
    def fw_version(self, fw_version):
        self._fw_version = fw_version

    @staticmethod
    async def async_update(hass, entry) -> None:
        """Update the device and related entities.

        Triggered when the device is renamed on the frontend.
        """
        device_registry = dr.async_get(hass)
        assert entry.unique_id
        device_entry = device_registry.async_get_device(
            identifiers={(DOMAIN, entry.unique_id)}
        )
        assert device_entry
        device_registry.async_update_device(device_entry.id, name=entry.title)
        await hass.config_entries.async_reload(entry.entry_id)

    def _set_scan_interval(self, scan_interval):
        # scan_interval = timedelta(seconds=seconds)
        self.update_manager.coordinator.update_interval = scan_interval

    async def async_unload(self) -> bool:
        """Unload the device and related entities."""
        if self.update_manager is None:
            return True

        while self.reset_jobs:
            self.reset_jobs.pop()()

        return await self.hass.config_entries.async_unload_platforms(
            self.config, ''
        )


class Plug(HejiaqinDevice, ABC):
    
    _ip = None
    _status = None
    _available = None
    new_data = None
    update_manager = None
    update_flag = None
    api_key = None

    def status(self, dp_id):
        return self._status.get(dp_id)
    
    def available(self, dp_id):
        return bool(self._available and self.update_manager.available)

    def get_sersor_remark(self, dp_id):
        return None

    def get_entity(self, unique_id):
        for entity in self._entities:
            if unique_id == entity.unique_id:
                return entity
            
    def get_sn_by_configuration(self):
        return self.config.get(CONF_DEVICE_SN)

    def pop_update_flag(self, flag):
        for index, _flag in enumerate(self.update_flag):
            if _flag == flag:
                self.update_flag.pop(index)
                break

    async def async_set_dp(self, dp_id, status):
        if dp_id == DP_LED:
            resp =  await self.api.async_set_led(self.unique_id, status)
        elif dp_id == DP_DEFAULT:
            resp = await self.api.async_set_default(self.unique_id, status)
        elif dp_id == DP_CHILDREN_LOCK:
            resp = await self.api.async_set_children_lock(self.unique_id, status)
        elif dp_id == DP_CURRENT_PROTECT:
            resp = await self.api.async_set_current_protect(self.unique_id, status)
        elif dp_id == DP_VOLTAGE_PROTECT:
            resp = await self.api.async_set_voltage_protect(self.unique_id, status)
        elif 'relay' in dp_id:
            index = int(dp_id[-1])
            resp = await self.api.async_set_status(self.unique_id, index, status)
        else:
            resp = await self.api.async_set_status_by_name(self.unique_id, dp_id, status)

        r_json = resp.json()
        if not r_json["resultCode"]:
            self._status.update({dp_id: status})

    async def async_set_scan_interval(self, seconds):
        if self.status('remote') or self.status('remote') is None:
            seconds = max(seconds, 60)
        else:
            seconds = max(seconds, 10)
        scan_interval = timedelta(seconds=seconds)
        self.coordinator.update_interval = scan_interval
        self.coordinator.async_set_updated_data(data=self._status)
        return seconds
    
    async def async_update_fw_version(self, r_json):
        try:
            for dev_status in r_json.get('parameters',''):
                name = dev_status.get('name','_')
                value = dev_status.get('value')
                if name == 'firmware' and value is not None:
                    value = value.replace('Version','').replace('version','').replace('V','').replace('v','')
                    self.fw_version = value
                    self.pop_update_flag(UPDATE_FLAG_VERSION)
                    await self.async_update()
        except: 
            if (version := self.config.get(CONF_DEVICE_VERSION)) is not None:
                self.fw_version = version

    async def async_update(self) -> None:
        """Update the device and related entities."""
        device_registry = dr.async_get(self.hass)

        device_entry = device_registry.async_get_device(
            identifiers={(DOMAIN, self._unique_id)}
        )
        assert device_entry
        device_registry.async_update_device(device_entry.id, sw_version=self.fw_version)
        # await self.hass.config_entries.async_reload(entry.entry_id)

    @abstractmethod
    async def async_setup(self) -> bool:
        """Set up the device and related entities."""
    
    @abstractmethod
    async def async_request(self, *args, **kwargs):
        """Send a request to the device."""


class X1S(Plug):

    def __init__(self, hass, config):
        self.hass = hass
        self.config = config
        self.sn = config.get(CONF_DEVICE_SN)
        self._entities = list()
        self._status = dict()
        self.new_data = dict()
        self.update_flag = list()
        self.api_key = config.get(CONF_API_KEY)
        self.api = PlugAPI(self.hass, self.api_key)
        # self.api.api_key = self.api_key
        _LOGGER.debug(self.api_key)
        _LOGGER.debug(self.api.api_key)
        self.update_manager = P1UpdateManager(self)
    
    @property
    def manufacturer(self):
        return "惠桔"
    
    @property
    def model(self):
        return "X1S"

    @property
    def entities(self):
        entities = SLOT_X_WITH_ELECTRIC.copy()
        entities = entities[:-7]
        platform_entities = {}
        
        for dp_id in entities:
            platform = PLATFORM_OF_ENTITY[dp_id]
            if platform_entities.get(platform) is None:
                platform_entities[platform] = [dp_id]
            else:
                platform_entities[platform].append(dp_id)
            
        return platform_entities

    @property
    def memos(self):
        return dict()
        return {DP_RELAY_0: self.name}
    
    async def async_restore_electricity(self):
        _LOGGER.debug("in async_restore_electricity")
        for dp_id in ELECTRIC_ENTITY[:-3]:
            entity = self.get_entity(f"{self._unique_id}_{dp_id}")
            last_state = await entity.async_get_last_state()
            if last_state is not None and isinstance(last_state.state, (int, float)):
                self._status.update({dp_id: last_state.state})
                    
        _LOGGER.debug("out async_restore_electricity")

    async def async_setup(self) -> bool:
        """Set up the device and related entities."""
        # config = self.config
        _LOGGER.debug("in device async_setup")

        await self.async_restore_electricity()
        
        self.update_flag.append(UPDATE_FLAG_VERSION)

        _LOGGER.debug("out device async_setup!!!!")
        return True
    
    async def async_request(self, *args, **kwargs):
        """Send a request to the device."""


class SP5F_CNA(Plug):

    def __init__(self, hass, config):
        self.hass = hass
        self.config = config
        self.sn = config.get(CONF_DEVICE_SN)
        self._entities = list()
        self._status = dict()
        self.new_data = dict()
        self.update_flag = list()
        self.api_key = config.get(CONF_API_KEY)
        self.api = PlugAPI(self.hass, self.api_key)
        self.api.async_set_status = self.api.async_set_power_status
        # self.api.api_key = self.api_key
        _LOGGER.debug(self.api_key)
        _LOGGER.debug(self.api.api_key)
        self.update_manager = P1UpdateManager(self)
    
    @property
    def manufacturer(self):
        return "BroadLink"
    
    @property
    def model(self):
        return "SP5F-CNA"

    @property
    def entities(self):
        entities = SLOT_X_WITH_ELECTRIC.copy()
        entities = [DP_CURRENT_PROTECT, DP_VOLTAGE_PROTECT, DP_IP_ADDRESS] + entities
        entities = entities[:-7]
        platform_entities = {}
        
        for dp_id in entities:
            platform = PLATFORM_OF_ENTITY[dp_id]
            if platform_entities.get(platform) is None:
                platform_entities[platform] = [dp_id]
            else:
                platform_entities[platform].append(dp_id)
            
        return platform_entities

    @property
    def memos(self):
        return dict()
        return {DP_RELAY_0: self.name}
    
    async def async_restore_electricity(self):
        _LOGGER.debug("in async_restore_electricity")
        for dp_id in ELECTRIC_ENTITY[:-3]:
            entity = self.get_entity(f"{self._unique_id}_{dp_id}")
            last_state = await entity.async_get_last_state()
            if last_state is not None and isinstance(last_state.state, (int, float)):
                self._status.update({dp_id: last_state.state})
                    
        _LOGGER.debug("out async_restore_electricity")

    async def async_setup(self) -> bool:
        """Set up the device and related entities."""
        # config = self.config
        _LOGGER.debug("in device async_setup")

        await self.async_restore_electricity()
        
        self.update_flag.append(UPDATE_FLAG_VERSION)

        _LOGGER.debug("out device async_setup!!!!")
        return True
    
    async def async_request(self, *args, **kwargs):
        """Send a request to the device."""

        
class UnkownDevice(Plug):

    def __init__(self, hass, config):
        self.hass = hass
        self.config = config
        self.sn = config.get(CONF_DEVICE_SN)
        self._entities = list()
        self._status = dict()
        self.new_data = dict()
        self.update_flag = list()
        self.api_key = config.get(CONF_API_KEY)
        self.api = PlugAPI(self.hass, self.api_key)
        # self.api.api_key = self.api_key
        _LOGGER.debug(self.api_key)
        _LOGGER.debug(self.api.api_key)
        self.update_manager = P2UpdateManager(self)
    
    @property
    def manufacturer(self):
        return "HEJIAQIN"
    
    @property
    def model(self):
        return self.config.get('deviceModel', 'HJQ generic')

    @property
    def entities(self):       
        return self.config.get('entities', dict())

    @property
    def memos(self):
        return dict()
        return {DP_RELAY_0: self.name}
    
    async def async_get_detail(self):
        resp = await self.api.async_get_detail(self.unique_id)
        r_json = resp.json()
        data = r_json.get('device', dict())
        self.config["deviceModel"] = data.get('deviceModel')
        entities = dict()
        parameters = data.get('parameters', list())
        for param in parameters:
            name = param.get('name')
            value = param.get('value')
            if name in ['XData', 'firmware', 'softVersion'] or name is None or value is None: continue
            value = str(value)
            _LOGGER.debug(value)
            _LOGGER.debug(len(value.split('.')))
            if len(value.split('.')) == 1:
                if entities.get('switch') is None:
                    entities['switch'] = list()
                entities["switch"].append(name)
            else:
                if entities.get('sensor') is None:
                    entities['sensor'] = list()
                entities["sensor"].append(name)
        _LOGGER.debug(entities)
        self.config["entities"] = entities


    async def async_setup(self) -> bool:
        """Set up the device and related entities."""
        # config = self.config
        _LOGGER.debug("in device async_setup")
        
        self.update_flag.append(UPDATE_FLAG_VERSION)

        _LOGGER.debug("out device async_setup!!!!")
        return True
    
    async def async_request(self, *args, **kwargs):
        """Send a request to the device."""

      


class HejiaqinUpdateManager(ABC):
    """Representation of a Broadlink update manager.

    Implement this class to manage fetching data from the device and to
    monitor device availability.
    """
    UPDATE_COUNT = 0
    TICK_N = 6
    UPDATE_INTERVAL = timedelta(seconds=60)
    FIRST_UPDATE_INTERVAL = timedelta(seconds=10)
    CURRENT_UPDATE_INTERVAL = FIRST_UPDATE_INTERVAL
    

    def __init__(self, device):
        """Initialize the update manager."""
        self.device = device
        self.device.api.timeout = (8,8)
        # self.SCAN_INTERVAL = timedelta(seconds=scan_interval)
        self.coordinator = DataUpdateCoordinator(
            device.hass,
            _LOGGER,
            name=f"{device.name} ({device.model} {device.sn})",
            update_method=self.async_update,
            update_interval=self.CURRENT_UPDATE_INTERVAL,
        )
        self.available = None
        self.last_update = dt_util.utcnow()

    def change_update_interval(self):
        if self.coordinator.update_interval == self.FIRST_UPDATE_INTERVAL:
            self.CURRENT_UPDATE_INTERVAL = self.UPDATE_INTERVAL
            self.coordinator.update_interval = self.UPDATE_INTERVAL
            self.coordinator.async_set_updated_data(data=self.device._status)
            _LOGGER.debug(f"{self.device.name} change update interval")

    async def async_update(self):
        """Fetch data from the device and update availability."""
        try:
            # data = None
            # if self.TICK_N == 1 or math.ceil(self.UPDATE_COUNT % self.TICK_N) == 1:
            #     data = await self.async_fetch_data()
            data = await self.async_fetch_data()
            self.change_update_interval()
        except Exception as err:
            if (self.available or self.available is None) and (
                dt_util.utcnow() - self.last_update > self.CURRENT_UPDATE_INTERVAL * 3
            ):
                self.available = False
                self.change_update_interval()
                _LOGGER.warning(
                    "Disconnected from %s (%s at %s)",
                    self.device.name,
                    self.device.model,
                    PLUG_DOMAIN,
                )
            #force update
            self.coordinator.async_update_listeners()
            self.device.api.timeout = None
            raise UpdateFailed(err) from err
        
        if self.available is False:
            _LOGGER.warning(
                "Connected to %s (%s at %s)",
                self.device.name,
                self.device.model,
                PLUG_DOMAIN,
            )
        self.available = True
        self.last_update = dt_util.utcnow()
        self.UPDATE_COUNT += 1
        self.device.api.timeout = None
        return data

    @abstractmethod
    async def async_fetch_data(self):
        """Fetch data from the device."""



class P1UpdateManager(HejiaqinUpdateManager):
    "Plug with electric"

    error_flag = 0

    async def async_process_update_flag(self, *args):
        if UPDATE_FLAG_VERSION in self.device.update_flag:
            await self.device.async_update_fw_version(*args)

    async def async_fetch_data(self):
        """Fetch data from the device."""

        device_id = self.device.unique_id
        api = self.device.api
        status = self.device._status
        # if value := self.coordinator.data is not None:
        #     status.update(value)
        try:
            resp = await api.async_get_detail(device_id)
            _LOGGER.debug(f"{self.device.name} (GET_DETAIL): {resp.text}")
            r_json = resp.json()
            status_data = r_json.get('device', dict())
            status.update(plug_status_process(status_data))
            status.update(plug_electric_process(status_data))
            status.update(plug_info_process(status_data))
            await self.async_process_update_flag(status_data)
            self.device._available = status_data.get('connected')
            # status.update(plug_power_consumes_process(r_json))
        except: 
            self.error_flag += 1
        
        _LOGGER.debug(f"{self.device.name}: {self.device._status}")

        self.UPDATE_COUNT += 1
        if self.error_flag > 0:
            self.error_flag = 0
            raise requests.exceptions.ConnectionError
        return status

class P2UpdateManager(HejiaqinUpdateManager):
    "Plug without electric"

    error_flag = 0

    async def async_process_update_flag(self, *args):
        if UPDATE_FLAG_VERSION in self.device.update_flag:
            await self.device.async_update_fw_version(*args)

    async def async_fetch_data(self):
        """Fetch data from the device."""

        device_id = self.device.unique_id
        api = self.device.api
        status = self.device._status
        # if value := self.coordinator.data is not None:
        #     status.update(value)
        try:
            resp = await api.async_get_detail(device_id)
            _LOGGER.debug(f"{self.device.name} (GET_DETAIL): {resp.text}")
            r_json = resp.json()
            status_data = r_json.get('device', dict())
            parameters = status_data.get('parameters', list())
            for param in parameters:
                name = param.get('name')
                value = param.get('value')
                if name in ['XData', 'firmware', 'softVersion'] or name is None or value is None: continue
                _value = str(value)
                if len(_value.split('.')) == 1:
                    status[name] = int(value)
                elif len(_value.split('.')) == 2:
                    status[name] = float(value)
            await self.async_process_update_flag(status_data)
            self.device._available = status_data.get('connected')
            # status.update(plug_power_consumes_process(r_json))
        except: 
            self.error_flag += 1
        
        _LOGGER.debug(f"{self.device.name}: {self.device._status}")

        self.UPDATE_COUNT += 1
        if self.error_flag > 0:
            self.error_flag = 0
            raise requests.exceptions.ConnectionError
        return status       

class DNSUpdateManger():

    refresh_ttl = timedelta(hours=12)
    server = 'ip33'

    def __init__(self, hass):
        self.hass = hass
        self.dns = DNS(hass, self.server)
        self.devices = list()
        self.coordinator = DataUpdateCoordinator(
            self.hass,
            _LOGGER,
            name=f"DNS Update (query at {self.server})",
            update_method=self.dns.async_update,
            update_interval=self.refresh_ttl,
        )
        self.coordinator.async_add_listener(self.nop)

    def nop(self):
        for device in self.devices:
            if device.api._inject_dns:
                device.api._inject_dns = True

  
