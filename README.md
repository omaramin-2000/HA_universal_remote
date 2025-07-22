# Home Assistant Universal Remote

[![hacs badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/)

A Home Assistant custom integration for controlling universal IR/RF remotes using ESPHome or Tasmota devices via MQTT.

---

## Overview

**Universal Remote** brings seamless integration of IR and RF remote capabilities into Home Assistant. With support for ESPHome and Tasmota-based hardware, this integration allows you to send, receive, and automate IR/RF signals from a wide range of remotes, making it ideal for smart TVs, air conditioners, and other appliances.

---

## Features

- Works with ESPHome and Tasmota-based universal remotes.
- Sends IR and RF commands via Home Assistant services or automations.
- Supports both protocol-based and raw data IR/RF commands.
- YAML configuration for multiple remotes and backends.
- Compatible with MQTT for Tasmota devices.
- HACS-friendly for easy installation and updates.
- Learns and stores IR/RF codes for reuse.

---

## Installation

### 1. HACS (Recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=omaramin-2000&repository=HA_universal_remote&category=integration)

1. Go to **HACS → Integrations → Custom repositories**.
2. Add your repo URL (e.g., `https://github.com/omaramin-2000/universal_remote`).
3. Set category as **Integration** and add.
4. Find "Universal Remote" in HACS integrations and install.
5. Restart Home Assistant.

### 2. Manual Installation

1. Download the `universal_remote` integration from this repository.
2. Copy the `custom_components/universal_remote` folder into your Home Assistant `custom_components` directory.
3. Restart Home Assistant.

---

## Configuration

This integration supports both **Tasmota** and **ESPHome** devices as universal remotes.  
Below you'll find detailed instructions for each platform, including how to configure learning indicators and example Home Assistant configurations.

---

### 1. ESPHome Configuration

ESPHome-based devices communicate directly with Home Assistant and can be customized via YAML.

#### Example ESPHome YAML Snippet

Below is a **generic example** for ESPHome that allows sending and learning any IR or RF code, without requiring a specific protocol.  
This approach works with most IR/RF devices and is compatible with the universal remote integration.

```yaml
remote_transmitter:
  pin: GPIOXX
  carrier_duty_percent: 50%

remote_receiver:
  pin: GPIOXX
  dump: all
  buffer_size: 4kb
  on_raw:
    then:
      - homeassistant.event:
          event: esphome.universal_remote_ir_received
          data:
            code: !lambda |-
              // Build a comma‑separated list of the raw timings
              std::string out;
              for (size_t i = 0; i < x.size(); i++) {
                if (i != 0) out += ",";
                out += to_string(x[i]);
              }
              return out;

output:
  - platform: gpio
    pin: GPIOXX
    id: status_led_output

light:
  - platform: binary
    name: "Status LED"
    output: status_led_output
    id: led_indicator

api:
  services:
    - service: learning_started
      then:
        - light.turn_on: led_indicator
    - service: learning_ended
      then:
        - light.turn_off: led_indicator
    - service: send
      variables:
        command: string
      then:
        - remote_transmitter.transmit_raw:
            code: !lambda |-
              std::vector<uint32_t> out;
              for (auto s : split(command, ',')) {
                out.push_back(parse_number<uint32_t>(s));
              }
              return out;
    - service: learn
      then:
        # Optionally, you can add actions here if needed when learning starts
        - logger.log: "Learning mode started"
```

- **Sending:**  
  The `send` service expects a comma-separated string of raw timings (as learned or provided by your integration).
- **Learning:**  
  The `learn` service can be used to trigger an indicator (like an LED) or any other action you want when learning mode is started from Home Assistant.  
  **Note:** ESPHome automatically dumps received IR/RF codes to the logs when `dump: all` is set. You can view these codes in the ESPHome logs and use them in Home Assistant.

> Adjust the `pin` numbers and actions to match your hardware.  
> For advanced protocol support, see the [ESPHome Remote Transmitter docs](https://esphome.io/components/remote_transmitter.html).

#### Example Home Assistant Configuration

```yaml
remote:
  - platform: universal_remote
    name: "Living Room Remote"
    backend: esphome
    device: livingroom_ir
```

---

### 2. Tasmota Configuration

Tasmota-based devices communicate via MQTT and can send/receive IR or RF commands.  
To use a Tasmota device as a universal remote in Home Assistant, follow these steps:

#### How to Find Your Tasmota MQTT Topic

To control your Tasmota device, you need to know its **MQTT Topic**:

1. Open your Tasmota device’s web UI in your browser.
2. Go to **Information**.
3. Look for the field labeled **MQTT Topic**.

This is the value you should use for `mqtt_topic` in your Home Assistant configuration.

**Example screenshot:**

![How to find your Tasmota MQTT Topic](./examples/TASMOTA-MQTT-Topic.png)

In this example, the MQTT Topic is `Esp8266_universal_remote`.

Use this value in your configuration:

```yaml
remote:
  - platform: universal_remote
    name: "Bedroom Remote"
    backend: tasmota
    mqtt_topic: Esp8266_universal_remote
    led_entity_id: light.bedroom_remote_led  # Optional: entity to turn on during learning    
```

---

#### Using a Tasmota GPIO LED as a Learning Indicator

Tasmota does not expose onboard LEDs as `light` entities in Home Assistant by default.  
To use an onboard LED (or any GPIO-connected LED) as a learning indicator with this integration, you should configure that GPIO as a **Relay** in Tasmota. This will expose it as a `switch` entity in Home Assistant, which the integration can control during learning mode.

##### How to Configure

1. **Open your Tasmota device’s web UI.**
2. Go to **Configuration → Configure Module**.
3. Find the GPIO pin connected to your LED (for example, GPIO5).
4. Set its function to **Relay** (e.g., `Relay1`, `Relay2`, etc.).
5. Click **Save** and let the device restart.

This will expose the LED as a `switch` entity in Home Assistant (e.g., `switch.yourdevice_relay`).

##### Example Home Assistant Configuration

```yaml
remote:
  - platform: universal_remote
    name: "Bedroom Remote"
    backend: tasmota
    mqtt_topic: Esp8266_universal_remote
    led_entity_id: switch.bedroom_remote_relay  # Use the switch entity for the LED indicator
```

##### How It Works

- When you start learning mode, the integration will turn on the `switch` (LED on).
- When learning ends, the integration will turn off the `switch` (LED off).

**Tip:**  
You can still use other relays for actual relays (e.g., controlling power), just pick a free relay number for your LED.

> If you want to use a `light` entity instead, you can use a template light in Home Assistant that wraps the relay switch.

**This method ensures your LED can be controlled by Home Assistant and used as a learning indicator.**

---

### Configuration Options

| Option         | Required | Description                                                                 |
|----------------|----------|-----------------------------------------------------------------------------|
| `platform`     | Yes      | Must be `universal_remote`                                                  |
| `name`         | Yes      | Friendly name for your remote                                               |
| `backend`      | Yes      | Either `esphome` or `tasmota`                                               |
| `device`       | Yes\*    | ESPHome device name (required for ESPHome backend)                          |
| `mqtt_topic`   | Yes\*    | MQTT topic for Tasmota device (required for Tasmota backend)                |
| `led_entity_id`| No       | Optional LED entity to indicate remote status (for learning indicator)      |

\* Only one of `device` or `mqtt_topic` is required, depending on the backend.

---

## Usage

### Sending Commands

You can send IR or RF commands using the `remote.send_command` service in Home Assistant.

#### For Tasmota

- **IR Example (protocol-based):**

  ```yaml
  service: remote.send_command
  target:
    entity_id: remote.bedroom_remote
  data:
    command:
      - '{"Protocol":"SAMSUNG","Bits":32,"Data":"0xE0E040BF"}'
  ```

- **IR Example (raw):**

  ```yaml
  service: remote.send_command
  target:
    entity_id: remote.bedroom_remote
  data:
    command:
      - '9000,4500,560,560,560,560,560,1690,560,560,560,560,560,560,560,560,560,560'
  ```

- **RF Example (protocol-based):**

  ```yaml
  service: remote.send_command
  target:
    entity_id: remote.bedroom_remote
  data:
    command:
      - '{"RfSync":12340,"RfLow":420,"RfHigh":1240,"RfCode":"0x123456"}'
  ```

#### For ESPHome

- **IR or RF Example:**

  ```yaml
  service: remote.send_command
  target:
    entity_id: remote.living_room_remote
  data:
    command:
      - "0xE0E040BF"
  ```

  > The format and interpretation of the command depend on your ESPHome YAML configuration.  
  > You can pass protocol-based or raw codes as strings, but your ESPHome device must be set up to handle them.

---

### Learning Commands

You can use the `remote.learn_command` service to learn IR or RF codes. The learned codes are stored in `/config/.storage/universal_remote_LEARNED_codes` and can be reused.

#### Example:

```yaml
service: remote.learn_command
target:
  entity_id: remote.bedroom_remote
data:
  command:
    - "power"
```

- Follow your device's instructions to put it in learning mode (e.g., point your remote and press the button).
- The code will be saved and can be sent later using `remote.send_command`.

---

## Notes & Tips

- **Tasmota:**  
  - The integration automatically detects whether to use `IRSend` or `RfSend` based on your command payload.
  - You do **not** need to specify the topic; just provide the correct JSON or raw string.

- **ESPHome:**
  - ESPHome functionality is still in development.
  - You must define the corresponding `send` and `learn` services in your ESPHome YAML.
  - The integration passes the command string to ESPHome; your ESPHome config must know how to interpret it.

- **Multiple Remotes:**  
  - You can define as many remotes as you want, each with its own backend and configuration.

- **Supported Formats:**  
  - Protocol-based (e.g., NEC, SAMSUNG, etc.) and raw data for both IR and RF are supported.
  - For Tasmota, see [Tasmota IR Docs](https://tasmota.github.io/docs/Tasmota-IR/) and [Tasmota RF Docs](https://tasmota.github.io/docs/RF-Protocol/).

---

## Troubleshooting

- If commands are not working, check your device logs and ensure your payload matches what your hardware expects.
- For ESPHome, verify your YAML configuration for the remote transmitter/receiver.
- For Tasmota, ensure your device is online and the MQTT topic is correct.

---

## Questions?

Open an issue on [GitHub issue tracker](https://github.com/omaramin-2000/HA_universal_remote/issues) or ask in the [Home Assistant Community](https://community.home-assistant.io/)
