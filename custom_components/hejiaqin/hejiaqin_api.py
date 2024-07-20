import aiohttp
import asyncio
import requests
import json
import functools
import hashlib
import uuid
import time
import logging
import textwrap
from abc import ABC

from homeassistant import config_entries
from .const import (
    DOMAIN,
    SL_DEVICES,
    CONFIG,
    CONF_REQUESTS_SESSION,
)

_LOGGER = logging.getLogger(__name__)

USER_AGENT = 'zhihuiguanjia/8.4.0 (iPhone; iOS 17.5.1; Scale/3.00);UniApp'
HTTPS_SUFFIX = 'https://'
HTTP_SUFFIX = 'http://'
DEVICE_SUFFIX = '/espapi/v3/cloud/json/family/devices'
BASE_URL = HTTPS_SUFFIX + 'andlink.komect.com'
DEVICES_URL = BASE_URL + DEVICE_SUFFIX + '/list' 
CONTROL_URL = BASE_URL + DEVICE_SUFFIX + '/parameters/control'
DETAIL_URL = BASE_URL + DEVICE_SUFFIX + '/detail/get'
HEAD_AUTH = 'API_KEY'
LANGUAGE = 'zh-Hans_US'
HEADERS = {
    'User-Agent': USER_AGENT,
    'Accept': '*/*',
    'Accept-Language': LANGUAGE,
}

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
DP_ELECTRIC = "electric"
DP_POWER = "power"
DP_CURRENT = "current"
DP_VOLTAGE = "voltage"
DP_ELECTRICITY = "electricity"
DP_ELECTRICITY_HOUR = "electricity_hour"
DP_ELECTRICITY_DAY = "electricity_day"
DP_ELECTRICITY_WEEK = "electricity_week"
DP_ELECTRICITY_MONTH = "electricity_month"
DP_ELECTRICITY_LASTMONTH = "electricity_lastmonth"

def get_session(hass):
    entry_id = None
    session = requests.Session()
    try:
        entry_id = config_entries.current_entry.get().entry_id
    except: pass

    try:
        if entry_id is not None and hass.data[DOMAIN][CONFIG][entry_id][CONF_REQUESTS_SESSION] is not None:
            session = hass.data[DOMAIN][CONFIG][entry_id][CONF_REQUESTS_SESSION]
    except: pass
        
    return session

class HTTPRequest(ABC):
    hass = None
    session = None
    timeout = None

    async def async_make_request_by_requests(self, method, url, data=None, headers=None, verify=None):
        # session = self.session
        if method == "GET":
            func = functools.partial(
                self.session.get, 
                url,
                headers=headers, 
                params=data,
                verify=verify,
                timeout=self.timeout,
            )
        elif method == "POST":
            func = functools.partial(
                self.session.post,
                url,
                headers=headers,
                data=json.dumps(data),
                verify=verify,
                timeout=self.timeout,
            )
        elif method == "PUT":
            func = functools.partial(
                self.session.put,
                url,
                headers=headers,
                data=json.dumps(data),
                verify=verify,
                timeout=self.timeout,
            )

        resp = await self.hass.async_add_executor_job(func)
        return resp

    def make_request_by_requests(self, method, url, data=None, headers={}):
        # session = self.session
        if method == "GET":
            func = functools.partial(
                self.session.get, url, headers=headers, params=data
            )
        elif method == "POST":
            func = functools.partial(
                self.session.post,
                url,
                headers=headers,
                data=json.dumps(data),
            )
        elif method == "PUT":
            func = functools.partial(
                self.session.put,
                url,
                headers=headers,
                data=json.dumps(data),
            )

        resp = func()
        return resp


class CloudAPI(HTTPRequest):
    def __init__(self, hass):
        self.hass = hass
        # self.session = requests.Session()
        self.session = get_session(self.hass)

    async def async_get_devices_list(self, api_key):
        headers = HEADERS.copy()
        headers[HEAD_AUTH] = api_key
        # _LOGGER.debug(headers)
        resp = await self.async_make_request_by_requests("GET", DEVICES_URL, headers=headers)
        # _LOGGER.debug(resp.headers)
        return resp
        #https://andlink.komect.com/espapi/v3/cloud/json/family/devices/parameters/get?deviceId=CMCC-590384-xxxxxx

class PlugAPI(HTTPRequest):

    _api_key = None
    headers = None

    def __init__(self, hass, api_key):
        self.hass = hass
        self.api_key = api_key
        self.session = get_session(self.hass)
    
    @property
    def api_key(self):
        return self._api_key
    
    @api_key.setter
    def api_key(self, api_key):
        if api_key is not None:
            self._api_key = api_key
            self.headers = HEADERS.copy()
            self.headers[HEAD_AUTH] = api_key

    # def set_api_key(self, api_key):
    #     if api_key is not None:
    #         self.headers = HEADERS.copy()
    #         self.headers[HEAD_AUTH] = api_key


    async def async_get_detail(self, decice_id):
        data = {"checkConnected": True, "deviceId": decice_id}

        resp = await self.async_make_request_by_requests("GET", DETAIL_URL, data=data, headers=self.headers)
        return resp

    async def async_set_status(self, decice_id, index, status):
        headers = self.headers.copy()
        headers['Content-Type'] = "application/json"
        data = {"deviceId":decice_id,"parameters":{"param":[{"name": "outletStatus", "index": index, "content": status}]}}

        resp = await self.async_make_request_by_requests("POST", CONTROL_URL, data=data, headers=headers)
        return resp

    async def async_set_led(self, decice_id, status):
        headers = self.headers.copy()
        headers['Content-Type'] = "application/json"
        data = data = {"deviceId":decice_id,"parameters":{"param":[{"name": "signalLight", "content": status}]}}

        resp = await self.async_make_request_by_requests("POST", CONTROL_URL, data=data, headers=headers)
        return resp

    async def async_set_default(self, decice_id, status):
        headers = self.headers.copy()
        headers['Content-Type'] = "application/json"
        data = data = {"deviceId":decice_id,"parameters":{"param":[{"name": "pwCutMemory", "content": status}]}}

        resp = await self.async_make_request_by_requests("POST", CONTROL_URL, data=data, headers=headers)
        return resp
    
    async def async_set_children_lock(self, decice_id, status):
        headers = self.headers.copy()
        headers['Content-Type'] = "application/json"
        data = data = {"deviceId":decice_id,"parameters":{"param":[{"name": "childrenLock", "content": status}]}}

        resp = await self.async_make_request_by_requests("POST", CONTROL_URL, data=data, headers=headers)
        return resp
    
    async def async_set_status_by_name(self, decice_id, name, status):
        headers = self.headers.copy()
        headers['Content-Type'] = "application/json"
        data = data = {"deviceId":decice_id,"parameters":{"param":[{"name": name, "content": status}]}}

        resp = await self.async_make_request_by_requests("POST", CONTROL_URL, data=data, headers=headers)
        return resp

    async def async_add_timer(self, decice_id, timer):
        #{"time": 2023, "repeat": 0, "enable": 1, "action": 0}
        #%257B%2522time%2522%253A2023%252C%2522repeat%2522%253A0%252C%2522enable%2522%253A1%252C%2522action%2522%253A0%257D
        #%7B%22time%22%3A2023%2C%22repeat%22%3A0%2C%22enable%22%3A1%2C%22action%22%3A0%7D
        pass
    
  