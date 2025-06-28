"""Platform for Universal Remote integration."""
import logging
import voluptuous as vol
import asyncio
import json

from homeassistant.components.remote import (
    ATTR_ALTERNATIVE,
    ATTR_COMMAND_TYPE,
    ATTR_DELAY_SECS,
    ATTR_DEVICE,
    ATTR_NUM_REPEATS,
    DEFAULT_DELAY_SECS,
    # DOMAIN as RM_DOMAIN,
    SERVICE_DELETE_COMMAND,
    SERVICE_LEARN_COMMAND,
    SERVICE_SEND_COMMAND,
    RemoteEntity,
    RemoteEntityFeature,
    PLATFORM_SCHEMA,
)

from homeassistant.const import CONF_NAME
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.storage import Store
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from homeassistant.core import callback
from homeassistant.components.mqtt import async_subscribe

_LOGGER = logging.getLogger(__name__)

DOMAIN = "universal_remote"

CONF_BACKEND = "backend"
CONF_DEVICE = "device"
CONF_MQTT_TOPIC = "mqtt_topic"

SUPPORT_UNIVERSAL_REMOTE = 1  # LEARN_COMMAND | SEND_COMMAND

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_BACKEND): vol.In(["esphome", "tasmota"]),
        vol.Optional(CONF_DEVICE): cv.string,
        vol.Optional(CONF_MQTT_TOPIC): cv.string,
    }
)

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the Universal Remote platform."""
    name = config[CONF_NAME]
    backend = config[CONF_BACKEND]
    device = config.get(CONF_DEVICE)
    mqtt_topic = config.get(CONF_MQTT_TOPIC)
    led_entity_id = config.get("led_entity_id")  # <-- add this line

    if backend == "esphome" and not device:
        _LOGGER.error("device must be set when backend is esphome")
        return
    if backend == "tasmota" and not mqtt_topic:
        _LOGGER.error("mqtt_topic must be set when backend is tasmota")
        return

    async_add_entities([UniversalRemote(hass, name, backend, device, mqtt_topic, led_entity_id)])

class UniversalRemote(RemoteEntity):
    """Universal Remote entity."""

    def __init__(self, hass, name, backend, device, mqtt_topic, led_entity_id=None):
        self.hass = hass
        self._attr_name = name
        self._backend = backend
        self._device = device
        self._mqtt_topic = mqtt_topic
        self._led_entity_id = led_entity_id  # <-- add this line
        self._attr_is_on = True
        self._attr_supported_features = (
            RemoteEntityFeature.LEARN_COMMAND
        )
        store_filename = f"universal_remote_LEARNED_codes_{device or mqtt_topic}.json"
        self._store = Store(hass, 1, store_filename)

    @property
    def available(self):
        # You can implement actual state checks here
        return True

    async def async_send_command(self, command, **kwargs):
        """Send a command by name or raw code."""
        if not isinstance(command, list):
            command = [command]
        codes = await self._store.async_load() or {}
        commands_to_send = []
        for cmd in command:
            # If the command is a known name, use the stored code
            if cmd in codes:
                commands_to_send.append(codes[cmd])
            else:
                commands_to_send.append(cmd)
        if self._backend == "esphome":
            for cmd in commands_to_send:
                data = {"command": cmd}
                for key in ("num_repeats", "delay_secs"):
                    value = kwargs.get(key)
                    if value is not None:
                        data[key] = value
                await self.hass.services.async_call(
                    "esphome",
                    f"{self._device}_send",
                    data,
                    blocking=True,
                )
                _LOGGER.debug("Sent '%s' to ESPHome device %s", cmd, self._device)
        elif self._backend == "tasmota":
            for cmd in commands_to_send:
                try:
                    payload = json.loads(cmd)
                    # Detect RF payload by typical RF keys
                    if (
                        "RfSync" in payload
                        or "RfCode" in payload
                        or payload.get("Protocol", "").upper() == "RF"
                    ):
                        topic_cmd = "RfSend"
                    else:
                        topic_cmd = "IRSend"
                except (json.JSONDecodeError, TypeError):
                    # Not JSON, treat as IR code
                    payload = {"Protocol": "IR", "Data": cmd}
                    topic_cmd = "IRSend"
                await self.hass.services.async_call(
                    "mqtt",
                    "publish",
                    {
                        "topic": f"cmnd/{self._mqtt_topic}/{topic_cmd}",
                        "payload": json.dumps(payload)
                    },
                    blocking=True,
                )
                _LOGGER.debug("Sent '%s' to Tasmota MQTT topic %s", cmd, self._mqtt_topic)

    async def async_learn_command(self, command=None, command_type="ir", **kwargs):
        """Learn a command (IR or RF) and save it to storage."""
        if not command:
            _LOGGER.error("No command name provided for learning.")
            return
        if isinstance(command, list):
            command_name = command[0]
        else:
            command_name = command

        learned_code = None

        if self._backend == "esphome":
            # Optionally pass command_type to ESPHome if your YAML supports it
            data = {}
            if command_type:
                data["command_type"] = command_type
            event_type = f"esphome.{self._device}_{command_type}_learned"
            event_future = asyncio.Future()

            def _event_listener(event):
                nonlocal learned_code
                learned_code = event.data.get("code")
                if learned_code and not event_future.done():
                    event_future.set_result(learned_code)

            remove_listener = self.hass.bus.async_listen_once(event_type, _event_listener)

            # Signal ESPHome that learning has started
            await self.hass.services.async_call(
                "esphome",
                f"{self._device}_learning_started",
                {},
                blocking=True,
            )

            await self.hass.services.async_call(
                "esphome",
                f"{self._device}_learn",
                data,
                blocking=True,
            )
            try:
                learned_code = await asyncio.wait_for(event_future, timeout=20)
                _LOGGER.debug("Learned code from ESPHome: %s", learned_code)
            except asyncio.TimeoutError:
                _LOGGER.error("Timeout waiting for ESPHome learned code event.")
                return
            finally:
                remove_listener()
                # Signal ESPHome that learning has ended
                await self.hass.services.async_call(
                    "esphome",
                    f"{self._device}_learning_ended",
                    {},
                    blocking=True,
                )

        elif self._backend == "tasmota":
            topic = f"tele/{self._mqtt_topic}/RESULT"
            event_future = asyncio.Future()

            @callback
            def _mqtt_message_received(msg):
                payload = json.loads(msg.payload)
                code = None
                if command_type == "rf" and "RfReceived" in payload:
                    code = payload["RfReceived"]
                elif command_type == "ir":
                    if "IrReceived" in payload:
                        code = payload["IrReceived"]
                    elif "IrHVAC" in payload:
                        code = payload["IrHVAC"]
                if code and not event_future.done():
                    event_future.set_result(code)

            unsub = None
            try:
                unsub = await async_subscribe(self.hass, topic, _mqtt_message_received)

                # Signal Tasmota LED (or other indicator) that learning has started
                led_entity_id = getattr(self, "_led_entity_id", None)
                if led_entity_id:
                    await self.hass.services.async_call(
                        "light", "turn_on", {"entity_id": led_entity_id}, blocking=True
                    )

                try:
                    learned_code = await asyncio.wait_for(event_future, timeout=20)
                    _LOGGER.debug("Learned code from Tasmota: %s", learned_code)
                except asyncio.TimeoutError:
                    _LOGGER.error("Timeout waiting for Tasmota learned code MQTT message.")
                    return
            finally:
                if unsub is not None:
                    await unsub()
                # Signal Tasmota LED (or other indicator) that learning has ended
                if led_entity_id:
                    await self.hass.services.async_call(
                        "light", "turn_off", {"entity_id": led_entity_id}, blocking=True
                    )

        if learned_code:
            # Load existing codes
            codes = await self._store.async_load() or {}
            codes[command_name] = learned_code
            await self._store.async_save(codes)
            _LOGGER.info("Saved learned code for %s:%s", self._device or self._mqtt_topic, command_name)

    async def async_turn_on(self, **kwargs):
        self._attr_is_on = True

    async def async_turn_off(self, **kwargs):
        self._attr_is_on = False

    async def async_update(self):
        # Optionally implement: update state from device
        pass