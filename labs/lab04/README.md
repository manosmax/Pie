# Motion Pipeline Docker Image

## Overview

This README provides instructions for running the Motion Pipeline Docker image using **Docker Compose**.

Suitable for running the PIR motion detection pipeline on Raspberry Pi or compatible hardware with GPIO access.

---

## Prerequisites

### System Requirements
- Docker installed and running
- Access to GPIO devices (`/dev/gpiomem0`, `/dev/gpiochip0`)
- Linux system with proper permissions (may require `sudo`)
- Motion Pipeline Docker image built: `motion-pipeline`

### Device Setup
- Ensure your PIR sensor is connected to GPIO pin 4 (or configure as needed)
- Device must have appropriate GPIO permissions configured

---


### Running Docker Compose

**Build and run:**
```bash
docker compose up --build
```

**Run in background (detached mode):**
```bash
docker compose up --build -d
```

**View logs:**
```bash
docker compose logs -f motion-pipeline
```

**Stop the service:**
```bash
docker-compose down
```

---

## Parameter Reference
|-----------|---------|-------------|
| Parameter | Type | Default               | Description |
|---|---|-----------------------|---|
| `--device-id` | str | *(required)*          | Identifier embedded in every record |
| `--pin` | int | `17`                  | BCM GPIO pin number |
| `--sample-interval` | float | `0.1`                 | Seconds between sensor reads |
| `--cooldown` | float | `5.0`                 | Min seconds between emitted events |
| `--min-high` | float | `0.0`                 | Min seconds signal must stay HIGH to count |
| `--duration` | float | `30.0`                | Total run time in seconds (`0` = run until Ctrl-C) |
| `--out` | str | `motion_events.jsonl` | Output file (append-only) |
| `--verbose` / `-v` | flag | off                   | Print each event to stdout |


---

## Output


**Output file example:** `./output/motion_pipeline.jsonl`

```json
{"timestamp": "2024-03-01T10:30:45.123Z", "device_id": "pir-docker-01", "motion": true, "pin": 4}
{"timestamp": "2024-03-01T10:31:50.456Z", "device_id": "pir-docker-01", "motion": false, "pin": 4}
```


# Part B 

RQ1: What base image did you use and why?

We chose to use the image "python:3.11-slim" because it was recommended.

RQ2: How many layers does your Dockerfile create? Which instructions produce new layers?
The instructions that produce new layers are: FROM,RUN,COPY,ADD so our Dockerfile created 6 layers.

RQ3: What is the size of your built image? 
778 MB

RQ4: Why do we copy requirements.txt and install dependencies before copying the rest of the code? What would happen if we reversed the order? If you copy your code first and then install packages, any small code change forces Docker to reinstall all packages from scratch significantly increasing the time needed it to run.
