anastasis 12345678

# Home Assistant basics

**RQ1: What is Home Assistant and what problem does it solve? Why use it instead of building a custom dashboard?**

Home Assistant is an open-source home automation platform that allows the developers of a project to easily make an informational dashboard for non-technical people to view, or for people who dont have access to the logs. It includes, device management,dashboards,automations and history. We chose to use Home Assistant as an easier and quicker alternative instead of building it from scratch. Using this free tool we just need to connecting to our existing pipeline.  

**RQ2: What is the difference between the “Home Assistant OS” and “Home Assistant Container” installation methods? Why did we use the Container method?**

Home Assistant OS is a whole operating system instead of Home Assistant Container which is an installation method that gives us the Home Assistant Core. We chose this method to avoid replacing our Pi operating system.

**RQ3: What is an entity in Home Assistant? Give three examples of entities in your setup and their current states.**

An entity is used by Home Assistant as a way to organize anything that has a state. For example in our setup, the sensor is an entity, that can be either `on (motion detected)` or `clear`. Also our bin is an entity and its capacity has a state `(0% full)`.


# MQTT integration

**RQ4: How does Home Assistant learn about your sensors? Explain the MQTT discovery mechanism, what topic do you publish to, and what does the payload contain?**

Home Assistant supports MQTT Discovery. This means that sensors can announce themselves with a special configuration message instead of being manually configures in YAML files.

**RQ5: Why should discovery messages be published with the retain flag (-r)?**

Discovery messages should be retained so the Home Assistant can pick it up even if it restarts after the message was published.

**RQ6: What is the device block in a discovery message? What happens in the Home Assistant UI when multiple entities share the same device.identifiers?**

The Device block is important as it informs Home Assistant that this entity is a physical device. If multiple entities share the same device.identifiers they will appear grouped together under the device name in the UI. 

**RQ7: What is the difference between a state_topic and a json_attributes_topic? When would you use each?**



# Entity design

**RQ8: List all the entities you created. For each one, give: the entity type (binary_sensor, sensor, counter, etc.), the state topic (if MQTT-based), and why you chose that type.**

**RQ9: What device_class did you use for your motion sensor? What does the device class affect in the Home Assistant UI?**

**RQ10: What additional entities did you create beyond the minimum? Why did you choose those?**

**RQ11: How did you group your entities under devices? Draw or describe the device → entity hierarchy.**

# Automations and counter

**RQ12: How does the Home Assistant Counter helper work? What services can you call on it?**

**RQ13: Paste the YAML of your “Count motion events” automation. Explain each part (trigger, condition, action).**

**RQ14: What other automation(s) did you create? Paste the YAML and explain the trigger, condition (if any), and action.**

**RQ15: Give one example of an automation that would be useful in a real Smart Wastebin deployment that involves a condition (not just trigger → action). Describe the trigger, the condition, and the action.**

# Pipeline integration

**RQ16: Your producer now publishes to two kinds of topics: the data topic (full JSON events for the consumer) and the HA state topics (simple values for Home Assistant). Why not use the same topic for both?**

**RQ17: Show a screenshot of your Home Assistant dashboard with your wastebin entities visible.**

**RQ18: What happens in Home Assistant when the producer is stopped? Does the motion sensor show “unavailable”, “clear”, or something else? How could you improve this?**

# Reflection

**RQ19: Compare the effort of building a custom web dashboard vs. using Home Assistant. What do you gain? What do you give up?**

**RQ20: Home Assistant runs locally on the Pi, no cloud needed. Why does this matter for an edge IoT deployment?**

**RQ21: If your project had 10 wastebins with 3 sensors each, how would the MQTT discovery approach scale compared to manually configuring 30 entities?**
