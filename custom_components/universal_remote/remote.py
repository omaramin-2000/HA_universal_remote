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
    SERVICE_DELETE_COMMAND,
    SERVICE_LEARN_COMMAND,
    SERVICE_SEND_COMMAND,
    RemoteEntity,
    RemoteEntityFeature,
    PLATFORM_SCHEMA,
)

from homeassistant.const import CONF_NAME
from homeassistant.const import ATTR_COMMAND, STATE_OFF
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.storage import Store
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from homeassistant.core import callback
from homeassistant.components.mqtt import async_subscribe
from homeassistant.components import persistent_notification
from datetime import timedelta

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
        vol.Optional("led_entity_id"): cv.string,
        vol.Optional("text_sensor_entity_id"): cv.string, 
    }
)

LEARNING_TIMEOUT = timedelta(seconds=60)

COMMAND_TYPE_IR = "ir"
COMMAND_TYPE_RF = "rf"
COMMAND_TYPES = [COMMAND_TYPE_IR, COMMAND_TYPE_RF]

COMMAND_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_COMMAND): vol.All(
            cv.ensure_list, [vol.All(cv.string, vol.Length(min=1))], vol.Length(min=1)
        ),
    },
    extra=vol.ALLOW_EXTRA,
)

SERVICE_SEND_SCHEMA = COMMAND_SCHEMA.extend(
    {
        vol.Optional(ATTR_DELAY_SECS, default=DEFAULT_DELAY_SECS): vol.Coerce(float),
    }
)

SERVICE_LEARN_SCHEMA = COMMAND_SCHEMA.extend(
    {
        vol.Required(ATTR_DEVICE): vol.All(cv.string, vol.Length(min=1)),
        vol.Optional(ATTR_COMMAND_TYPE, default=COMMAND_TYPE_IR): vol.In(COMMAND_TYPES),
        vol.Optional(ATTR_ALTERNATIVE, default=False): cv.boolean,
    }
)

SERVICE_DELETE_SCHEMA = COMMAND_SCHEMA.extend(
    {vol.Required(ATTR_DEVICE): vol.All(cv.string, vol.Length(min=1))}
)

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the Universal Remote platform."""
    name = config[CONF_NAME]
    backend = config[CONF_BACKEND]
    device = config.get(CONF_DEVICE)
    mqtt_topic = config.get(CONF_MQTT_TOPIC)
    led_entity_id = config.get("led_entity_id")
    text_sensor_entity_id = config.get("text_sensor_entity_id")  

    if backend == "esphome" and not device:
        _LOGGER.error("device must be set when backend is esphome")
        return
    if backend == "tasmota" and not mqtt_topic:
        _LOGGER.error("mqtt_topic must be set when backend is tasmota")
        return

    async_add_entities([UniversalRemote(hass, name, backend, device, mqtt_topic, led_entity_id, text_sensor_entity_id)])

class UniversalRemote(RemoteEntity):
    """Universal Remote entity."""

    def __init__(self, hass, name, backend, device, mqtt_topic, led_entity_id, text_sensor_entity_id=None):
        self.hass = hass
        self._attr_name = name
        self._backend = backend
        self._device = device
        self._mqtt_topic = mqtt_topic
        self._led_entity_id = led_entity_id
        self._text_sensor_entity_id = text_sensor_entity_id  
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

    async def async_send_command(self, command, device=None, **kwargs):
        """Send a command by name or raw code."""
        if not device:
            _LOGGER.error("No device name provided for sending.")
            return
        if not isinstance(command, list):
            command = [command]
    
        # Load the stored commands from the JSON file
        codes = await self._store.async_load() or {}
        device_codes = codes.get(device, {})
        commands_to_send = []

        for cmd in command:
            # If the command is a known name, use the stored raw code
            if cmd in device_codes:
                commands_to_send.append(device_codes[cmd])
            else:
                commands_to_send.append(cmd)  # Assume it's already a raw code

        if self._backend == "esphome":
            num_repeats = kwargs.get("num_repeats", 1)
            delay_secs = kwargs.get("delay_secs", 0)
            hold_secs = kwargs.get("hold_secs", 0)

            for cmd in commands_to_send:
                # Ensure the command is a list of integers
                if isinstance(cmd, str):
                    try:
                        cmd = [int(x) for x in cmd.split(",")]
                    except ValueError:
                        _LOGGER.error("Invalid command format for ESPHome: %s", cmd)
                        continue
                elif not isinstance(cmd, list):
                    _LOGGER.error("Invalid command format for ESPHome: %s", cmd)
                    continue

                for i in range(num_repeats):
                    # Call the ESPHome service with the list of integers
                    await self.hass.services.async_call(
                        "esphome",
                        f"{self._device}_send",
                        {"command": cmd},
                        blocking=True,
                    )
                    _LOGGER.debug("Sent raw command '%s' to ESPHome device %s", cmd, self._device)
                    # Hold the button if requested (simulate long press)
                    if hold_secs and hold_secs > 0:
                        await asyncio.sleep(hold_secs)

                    # Delay between repeats, except after the last one
                    if i < num_repeats - 1 and delay_secs:
                        await asyncio.sleep(delay_secs)
        elif self._backend == "tasmota":
            num_repeats = kwargs.get("num_repeats", 1)
            delay_secs = kwargs.get("delay_secs", 0)
            for cmd in commands_to_send:
                for i in range(num_repeats):
                    # If the command is a dict, use it directly; if string, try to parse as JSON, else wrap as IR
                    if isinstance(cmd, dict):
                        payload = cmd
                        if (
                            "RfSync" in payload
                            or "RfCode" in payload
                            or payload.get("Protocol", "").upper() == "RF"
                        ):
                            topic_cmd = "RfSend"
                        else:
                            topic_cmd = "IRSend"
                    else:
                        try:
                            payload = json.loads(cmd)
                            if (
                                "RfSync" in payload
                                or "RfCode" in payload
                                or payload.get("Protocol", "").upper() == "RF"
                            ):
                                topic_cmd = "RfSend"
                            else:
                                topic_cmd = "IRSend"
                        except (json.JSONDecodeError, TypeError):
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
                    if i < num_repeats - 1 and delay_secs:
                        await asyncio.sleep(delay_secs)

    async def async_learn_command(self, command=None, command_type="ir", device=None, timeout=None, **kwargs):
        """Learn one or more commands and save them under the specified device."""
        if not device:
            _LOGGER.error("No device name provided for learning.")
            return
        if not command:
            _LOGGER.error("No command name(s) provided for learning.")
            return

        # Support both single string and list of commands
        if isinstance(command, str):
            command_names = [command]
        else:
            command_names = list(command)

        # Use custom timeout if provided
        learning_timeout = timedelta(seconds=timeout) if timeout else LEARNING_TIMEOUT

        # Load or create the storage file for this remote
        codes = await self._store.async_load() or {}
        device_codes = codes.get(device, {})

        for cmd_name in command_names:
            notification_id = f"learn_command_{device}_{cmd_name}".replace(" ", "_").lower()
            persistent_notification.async_create(
                self.hass,
                f"Press the '{cmd_name}' button on your '{device}' remote now.",
                title="Learn command",
                notification_id=notification_id,
            )

            learned_code = None

            if self._backend == "esphome":
                # Prepare to catch the next IR event
                event_type = f"esphome.{self._device}_ir_received"
                event_future = asyncio.get_running_loop().create_future()  # Ensure event_future is created properly

                @callback
                def event_listener(event):
                    code = event.data.get("code")
                    if code and not event_future.done():
                        event_future.set_result(code)

                remove_listener = None
                try:
                    # Register the listener
                    remove_listener = self.hass.bus.async_listen_once(event_type, event_listener)

                    # Signal ESPHome that learning has started
                    await self.hass.services.async_call(
                        "esphome", f"{self._device}_learning_started", {}, blocking=True
                    )
                    await self.hass.services.async_call(
                        "esphome", f"{self._device}_learn", {"command_type": command_type}, blocking=True
                    )

                    # Wait for the event to be set
                    learned_code = await asyncio.wait_for(event_future, timeout=learning_timeout.total_seconds())
                    _LOGGER.debug("Learned code from ESPHome: %s", learned_code)

                except asyncio.TimeoutError:
                    _LOGGER.error("Timeout waiting for ESPHome learned code event.")
                    persistent_notification.async_create(
                        self.hass,
                        f"Timeout: No code received for '{cmd_name}' on '{device}'.",
                        title="Learn command",
                        notification_id=notification_id,
                    )
                    continue

                finally:
                    # Ensure the listener is removed only if it was registered
                    if remove_listener:
                        remove_listener()
                    await self.hass.services.async_call(
                        "esphome",
                        f"{self._device}_learning_ended",
                        {},
                        blocking=True,
                    )
                    persistent_notification.async_dismiss(self.hass, notification_id)

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

                unsub = await async_subscribe(self.hass, topic, _mqtt_message_received)

                # Signal Tasmota LED (or other indicator) that learning has started
                led_entity_id = getattr(self, "_led_entity_id", None)
                domain = led_entity_id.split(".")[0]
                if led_entity_id:                    
                    await self.hass.services.async_call(
                        domain, "turn_on", {"entity_id": led_entity_id}, blocking=True
                    )

                try:
                    learned_code = await asyncio.wait_for(event_future, timeout=learning_timeout.total_seconds())
                    _LOGGER.debug("Learned code from Tasmota: %s", learned_code)
                except asyncio.TimeoutError:
                    _LOGGER.error("Timeout waiting for Tasmota learned code MQTT message.")
                    persistent_notification.async_create(
                        self.hass,
                        f"Timeout: No code received for '{cmd_name}' on '{device}'.",
                        title="Learn command",
                        notification_id=notification_id,
                    )
                    continue
                finally:
                    if unsub:
                        if asyncio.iscoroutinefunction(unsub):
                            await unsub()
                        else:
                            unsub()
                    if led_entity_id:
                        await self.hass.services.async_call(
                            domain, "turn_off", {"entity_id": led_entity_id}, blocking=True
                        )
                    persistent_notification.async_dismiss(self.hass, notification_id)

            if learned_code:
                device_codes[cmd_name] = learned_code
                _LOGGER.info("Saved learned code for %s:%s", device, cmd_name)

        # Save all learned codes for this device
        codes[device] = device_codes
        await self._store.async_save(codes)

    async def async_turn_on(self, **kwargs):
        self._attr_is_on = True

    async def async_turn_off(self, **kwargs):
        self._attr_is_on = False

    async def async_update(self):
        # Optionally implement: update state from device
        pass

    async def async_delete_command(self, command=None, device=None, **kwargs):
        """Delete one or more commands from the storage."""
        if not device:
            _LOGGER.error("No device name provided for deleting commands.")
            return
        if not command:
            _LOGGER.error("No command name(s) provided for deletion.")
            return

        # Support both single string and list of commands
        if isinstance(command, str):
            command_names = [command]
        else:
            command_names = list(command)

        # Load the storage file
        codes = await self._store.async_load() or {}
        device_codes = codes.get(device, {})

        # Delete the specified commands
        for cmd_name in command_names:
            if cmd_name in device_codes:
                del device_codes[cmd_name]
                _LOGGER.info("Deleted command '%s' for device '%s'", cmd_name, device)
            else:
                _LOGGER.warning("Command '%s' not found for device '%s'", cmd_name, device)

        # Save the updated codes back to storage
        codes[device] = device_codes
        await self._store.async_save(codes)
