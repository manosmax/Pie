# TESTING BRANCH FOR DATABASE INTEGRATION 

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

