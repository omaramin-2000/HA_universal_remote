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
- YAML configuration for multiple remotes and backends.
- Compatible with MQTT for Tasmota devices.
- HACS-friendly for easy installation and updates.

---

## Installation

### 1. HACS (Recommended)

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

Add your remote setup to `configuration.yaml`:

```yaml
remote:
  - platform: universal_remote
    name: "Living Room Remote"
    backend: esphome
    device: livingroom_ir

  - platform: universal_remote
    name: "Bedroom Remote"
    backend: tasmota
    mqtt_topic: Esp8266_universal_remote
