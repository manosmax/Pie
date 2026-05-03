# Lab 07 — Smart Bin & Home Assistant

**Student:** anastasis | 12345678

---

## Part A — Setup & Run

### Wiring (Raspberry Pi)

| Sensor Pin | Pi Physical Pin | BCM Name |
|------------|-----------------|----------|
| `VCC`      | 2               | 5V       |
| `GND`      | 6               | GND      |
| `OUT`      | 11              | GPIO17   |

### Build

```bash
docker compose build
```

### Run

**1. Start the MQTT broker:**
```bash
docker compose up
```

**2. First-time Home Assistant setup:**
```bash
docker run -d \
  --name homeassistant \
  --restart unless-stopped \
  -v ~/homeassistant/config:/config \
  -v /run/dbus:/run/dbus:ro \
  --network host \
  ghcr.io/home-assistant/home-assistant:stable
```

**3. Subsequent starts:**
```bash
docker start homeassistant
```

---

## Home Assistant Basics

**RQ1: What is Home Assistant and what problem does it solve? Why use it instead of building a custom dashboard?**

Home Assistant is an open-source home automation platform with built-in dashboards, device management, automations, and history. We use it to avoid building a custom dashboard from scratch — we just connect it to our existing MQTT pipeline.

**RQ2: What is the difference between the "Home Assistant OS" and "Home Assistant Container" installation methods? Why did we use the Container method?**

Home Assistant OS replaces the entire OS, while the Container method installs only Home Assistant Core inside Docker. We chose the Container method to keep our existing Raspberry Pi OS.

**RQ3: What is an entity in Home Assistant? Give three examples of entities in your setup and their current states.**

An entity is anything in Home Assistant that has a state. Examples from our setup: the PIR sensor (`detected` / `clear`), the bin fill level (`0% full`), and a motion event counter (`42 total events`).

---

## MQTT Integration

**RQ4: How does Home Assistant learn about your sensors? Explain the MQTT discovery mechanism, what topic do you publish to, and what does the payload contain?**

Home Assistant supports MQTT Discovery — sensors self-register by publishing a config message to `homeassistant/binary_sensor/pir_01_motion/config`. The payload defines the sensor name, state topic, on/off payloads, device class, unique ID, and device metadata.

**RQ5: Why should discovery messages be published with the retain flag (`-r`)?**

So Home Assistant picks up the config message even if it restarts after the message was originally published.

**RQ6: What is the device block in a discovery message? What happens in the Home Assistant UI when multiple entities share the same `device.identifiers`?**

The `device` block tells Home Assistant that the entity belongs to a physical device. Entities sharing the same `device.identifiers` are grouped together under one device in the UI.

**RQ7: What is the difference between a `state_topic` and a `json_attributes_topic`? When would you use each?**

`state_topic` updates the main state (e.g. `detected`/`clear`), while `json_attributes_topic` carries extra metadata. We'd use `state_topic` for motion and `json_attributes_topic` for things like battery level or firmware version.

---

## Entity Design

**RQ8: List all the entities you created. For each one, give: the entity type, the state topic (if MQTT-based), and why you chose that type.**

| Entity | Type | State Topic | Reason |
|--------|------|-------------|--------|
| PIR Motion Sensor | `binary_sensor` | `smartbin/bin-01/pir-01/motion` | Binary on/off motion state |
| Bin Fill Level | `sensor` | `smartbin/bin-01/fill-level` | Numeric percentage value |
| Motion Event Counter | `counter` | — (HA helper) | Tracks cumulative motion events |

**RQ9: What `device_class` did you use for your motion sensor? What does the device class affect in the Home Assistant UI?**

We used `device_class: motion`. It sets the icon, default labels (`Detected`/`Clear`), and groups the entity correctly in the UI.

**RQ10: What additional entities did you create beyond the minimum? Why did you choose those?**

We added a fill-level sensor and a motion counter — the fill level gives useful bin status at a glance, and the counter helps track usage patterns over time.

**RQ11: How did you group your entities under devices? Draw or describe the device → entity hierarchy.**

```
Smart Bin 01
├── PIR Sensor 01 (binary_sensor — motion)
├── Fill Level    (sensor — percentage)
└── Motion Count  (counter — helper)
```

---

## Automations and Counter

**RQ12: How does the Home Assistant Counter helper work? What services can you call on it?**

The counter helper stores an integer state. You can call `counter.increment`, `counter.decrement`, and `counter.reset` on it.

**RQ13: Paste the YAML of your "Count motion events" automation. Explain each part (trigger, condition, action).**

```yaml
alias: Count motion events
trigger:
  - platform: state
    entity_id: binary_sensor.pir_motion_sensor
    to: "on"           # fires when motion is detected
condition: []          # no condition — always runs
action:
  - service: counter.increment
    target:
      entity_id: counter.motion_events
```

**RQ14: What other automation(s) did you create? Paste the YAML and explain the trigger, condition (if any), and action.**

```yaml
alias: Notify bin full
trigger:
  - platform: numeric_state
    entity_id: sensor.bin_fill_level
    above: 90          # fires when fill level exceeds 90%
condition: []
action:
  - service: notify.persistent_notification
    data:
      message: "Bin 01 is over 90% full — empty it soon."
```

**RQ15: Give one example of an automation that would be useful in a real Smart Wastebin deployment that involves a condition.**

Trigger: bin fill level goes above 80%. Condition: current time is between 08:00–20:00 (working hours). Action: send a notification to the cleaning team. This avoids sending alerts overnight when no one can act on them.

---

## Pipeline Integration

**RQ16: Your producer now publishes to two kinds of topics: the data topic (full JSON events for the consumer) and the HA state topics (simple values for Home Assistant). Why not use the same topic for both?**

The consumer expects full JSON payloads for processing, while Home Assistant expects simple scalar values (e.g. `detected`). Using separate topics keeps each subscriber decoupled and avoids parsing mismatches.

**RQ17: Show a screenshot of your Home Assistant dashboard with your wastebin entities visible.**

*(screenshot here)*

**RQ18: What happens in Home Assistant when the producer is stopped? Does the motion sensor show "unavailable", "clear", or something else? How could you improve this?**

The sensor stays in its last known state (e.g. `clear`) — it does not go `unavailable` unless an availability topic is configured. This can be improved by adding an `availability_topic` to the discovery config and having the producer publish `online`/`offline` messages using MQTT's Last Will feature.

---

## Reflection

**RQ19: Compare the effort of building a custom web dashboard vs. using Home Assistant. What do you gain? What do you give up?**

Home Assistant gives us dashboards, history, automations, and MQTT integration out of the box, saving significant development time. We give up full control over the UI and are constrained by what Home Assistant natively supports.

**RQ20: Home Assistant runs locally on the Pi, no cloud needed. Why does this matter for an edge IoT deployment?**

Local operation means no latency, no dependency on internet connectivity, and no third-party data exposure — all critical for a reliable edge deployment.

**RQ21: If your project had 10 wastebins with 3 sensors each, how would the MQTT discovery approach scale compared to manually configuring 30 entities?**

With MQTT discovery each device registers itself automatically on startup — adding a new bin requires no changes to Home Assistant config. Manual YAML configuration for 30 entities would be tedious and error-prone.