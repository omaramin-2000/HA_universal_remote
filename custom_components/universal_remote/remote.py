from homeassistant.components.remote import RemoteEntity
from homeassistant.const import CONF_NAME
from homeassistant.helpers import entity_platform
import voluptuous as vol

DOMAIN = "universal_remote"

CONF_BACKEND = "backend"
CONF_DEVICE = "device"
CONF_MQTT_TOPIC = "mqtt_topic"

PLATFORM_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): str,
        vol.Required(CONF_BACKEND): vol.In(["esphome", "tasmota"]),
        vol.Optional(CONF_DEVICE): str,
        vol.Optional(CONF_MQTT_TOPIC): str,
    }
)

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    name = config[CONF_NAME]
    backend = config[CONF_BACKEND]
    device = config.get(CONF_DEVICE)
    mqtt_topic = config.get(CONF_MQTT_TOPIC)
    async_add_entities([UniversalRemote(hass, name, backend, device, mqtt_topic)])

class UniversalRemote(RemoteEntity):
    def __init__(self, hass, name, backend, device, mqtt_topic):
        self.hass = hass
        self._attr_name = name
        self._backend = backend
        self._device = device
        self._mqtt_topic = mqtt_topic
        self._attr_supported_features = 1  # LEARN_COMMAND | SEND_COMMAND

    async def async_send_command(self, command, **kwargs):
        if self._backend == "esphome":
            await self.hass.services.async_call(
                "esphome",
                f"{self._device}_send",
                {"command": command},
                blocking=True
            )
        elif self._backend == "tasmota":
            # Example for IR; extend for RF as needed
            payload = {"Protocol": "IR", "Data": command[0]}
            await self.hass.services.async_call(
                "mqtt",
                "publish",
                {
                    "topic": f"cmnd/{self._mqtt_topic}/IRSend",
                    "payload": payload
                },
                blocking=True
            )

    async def async_learn_command(self, **kwargs):
        if self._backend == "esphome":
            await self.hass.services.async_call(
                "esphome",
                f"{self._device}_learn",
                {},
                blocking=True
            )
        elif self._backend == "tasmota":
            # Tasmota learning is limited, but you can implement as needed
            pass