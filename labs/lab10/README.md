# Lab 09 — Data Processing on Edge Devices

**Student:** anastasis | 12345678

---

## Part A — Setup & Run

### Directory Structure

```
lab10/
├── README.md
├── requirements.txt
├── asyncapi.yml
├── docker-compose.yml
├── Dockerfile
├── mosquitto.conf
├── train_model.py
├── virtual_sensor_ml.py
├── virtual_sensor_rules.py
├── docs/
│   └── Ontology
├── models_v_s/
│   └── busy_predictor.joblib
├── models/
│   ├── context.jsonld
│   ├── environment.jsonld
│   ├── sensor.jsonld
│   └── wastebin.jsonld
├── flows.json
├── screenshots/
│  
└── src/
    ├── api.py
    ├── consumer.py
    ├── producer.py
    └── pirlib/
        ├── __init__.py
        ├── interpreter.py
        └── sampler.py```
``` 
### Run

**Start the MQTT broker, API, Producer and Consumer:**
```bash
docker compose up --build 
```

### Node-RED Setup

**Install Node-RED on your Raspberry Pi**
```bash
bash <(curl -sL https://raw.githubusercontent.com/node-red/linux-installers/master/deb/update-nodejs-and-nodered)
```

**Start Node-RED**
```bash
node-red-start
```

**To view Node-RED editor visit: `http://<your-pi-ip>:1880`**

### Lab Structure
```mermaid
flowchart LR
    PIR["PIR"] --> Producer["producer"]
    Producer --> MQTT["MQTT"]

    MQTT --> Python["Python consumer<br/>(JSONL logger)"]
    MQTT --> NodeRED["Node-RED<br/>(visual flows)<br/>• dashboard<br/>• alerts<br/>• data routing"]
    MQTT --> HA["Home Assistant"]                              
```

## Part B

## Getting started

**RQ1: How does Node-RED differ from writing a Python script? What is the “unit of work” in each? (In Python it is a function or a class. In Node-RED it is…?)**



**RQ2: What is the Node-RED message object? What is msg.payload and why does every node use it?**



**RQ3: What does the Deploy button do? Why do you need to click it after making changes?**


---

## Building flows

**RQ4: Show a screenshot of your usage monitor flow. Label each node and explain what it does.**

**RQ5: In the counting Function node, you might have used flow.set and flow.get. What do these do? How is this similar to and different from a Python variable?**

**RQ6: How does the Switch node compare to a Python if statement? What advantages does the visual version have?**

**RQ7: You built a branching flow (count → publish + alert if high). In Python, this would be an if-else block. In Node-RED, it is visible wiring. Which is easier to understand at a glance? Which is easier to test?**

---

## Integration

**RQ8: Your Python consumer and your Node-RED flow both subscribe to the same MQTT topic. How is this possible? Do they interfere with each other?**

**RQ9: You could build the usage monitor as a Python script (Lab 09) or as a Node-RED flow (this lab). Compare the two approaches: lines of code vs number of nodes, ease of modification, ease of testing, who can work with each.**

**RQ10: Could Node-RED replace your Python producer (the script that reads the PIR sensor)? Why or why not?**

---

## Node-RED in the ecosystem

**RQ11: Where does Node-RED fit in your overall system architecture? Draw or describe how it sits alongside the producer, consumer, Home Assistant, and REST API.**

**RQ12: A facilities manager (non-programmer) wants to add a new rule: “if no motion is detected for 6 hours during business hours, mark the bin as possibly blocked.” Could they build this in Node-RED without help? What nodes would they need?**

**RQ13: What are the limitations of Node-RED that the lecture mentioned? Did you encounter any of them in this lab?**

---

## Export and reproducibility

**RQ14: You exported your flows as flows.json. A teammate imports it into their Node-RED instance. What will they need to configure manually? (Hint: think about the MQTT broker connection.)**

**RQ15: Compare flows.json with a Python script in terms of version control. If two teammates edit the flow at the same time, what happens when they try to merge?**

---

## Reflection

**RQ16: After building the same logic in Python (Lab 09) and Node-RED (this lab), which did you find faster to build? Which would you trust more in production? Why?**

**RQ17: The lecture argued that low-code platforms let more people contribute to the system. After this lab, do you agree? Who in your project team could use Node-RED that could not write the Python equivalent?**

**RQ18: If you were designing the Smart Wastebin system from scratch, which parts would you build in Python and which in Node-RED? Explain your reasoning.**