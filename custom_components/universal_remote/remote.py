"""Platform for Universal Remote integration."""
import logging
import voluptuous as vol

from homeassistant.components.remote import RemoteEntity, PLATFORM_SCHEMA, RemoteEntityFeature
from homeassistant.const import CONF_NAME
import homeassistant.helpers.config_validation as cv

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

    if backend == "esphome" and not device:
        _LOGGER.error("device must be set when backend is esphome")
        return
    if backend == "tasmota" and not mqtt_topic:
        _LOGGER.error("mqtt_topic must be set when backend is tasmota")
        return

    async_add_entities([UniversalRemote(hass, name, backend, device, mqtt_topic)])

class UniversalRemote(RemoteEntity):
    """Universal Remote entity."""

    def __init__(self, hass, name, backend, device, mqtt_topic):
        self.hass = hass
        self._attr_name = name
        self._backend = backend
        self._device = device
        self._mqtt_topic = mqtt_topic
        self._attr_is_on = True
        self._attr_supported_features = (
            RemoteEntityFeature.LEARN_COMMAND
            | RemoteEntityFeature.SEND_COMMAND
            | RemoteEntityFeature.DELETE_COMMAND
            | RemoteEntityFeature.TOGGLE
            | RemoteEntityFeature.TURN_ON
            | RemoteEntityFeature.TURN_OFF
        )

    @property
    def available(self):
        # You can implement actual state checks here
        return True

    async def async_send_command(self, command, **kwargs):
        """Send a command."""
        if not isinstance(command, list):
            command = [command]
        if self._backend == "esphome":
            await self.hass.services.async_call(
                "esphome",
                f"{self._device}_send",
                {"command": command[0]},
                blocking=True,
            )
            _LOGGER.debug("Sent '%s' to ESPHome device %s", command[0], self._device)
        elif self._backend == "tasmota":
            payload = {"Protocol": "IR", "Data": command[0]}
            await self.hass.services.async_call(
                "mqtt",
                "publish",
                {
                    "topic": f"cmnd/{self._mqtt_topic}/IRSend",
                    "payload": self.hass.helpers.json.dumps(payload)
                },
                blocking=True,
            )
            _LOGGER.debug("Sent '%s' to Tasmota MQTT topic %s", command[0], self._mqtt_topic)

    async def async_learn_command(self, **kwargs):
        """Learn a command."""
        if self._backend == "esphome":
            await self.hass.services.async_call(
                "esphome",
                f"{self._device}_learn",
                {},
                blocking=True,
            )
            _LOGGER.debug("Triggered learn on ESPHome device %s", self._device)
        elif self._backend == "tasmota":
            _LOGGER.warning("Tasmota learning not implemented.")

    async def async_turn_on(self, **kwargs):
        self._attr_is_on = True

    async def async_turn_off(self, **kwargs):
        self._attr_is_on = False

    async def async_update(self):
        # Optionally implement: update state from device
        pass