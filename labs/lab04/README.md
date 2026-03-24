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
docker-compose up --build
```

**Run in background (detached mode):**
```bash
docker-compose up --build -d
```

**View logs:**
```bash
docker-compose logs -f motion-pipeline
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
