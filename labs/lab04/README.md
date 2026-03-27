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

**RQ1: What base image did you use and why?**
We chose to use the image "python:3.11-slim" because it was recommended.

**RQ2: How many layers does your Dockerfile create? Which instructions produce new layers?**
The instructions that produce new layers are: FROM,RUN,COPY,ADD so our Dockerfile created 6 layers.

**RQ3: What is the size of your built image?**
The size of the built image is 778 MB.

**RQ4: Why do we copy requirements.txt and install dependencies before copying the rest of the code? What would happen if we reversed the order?**
If you copy your code first and then install packages, any small code change forces Docker to reinstall all packages from scratch significantly increasing the time needed it to run.

**RQ5: What does --device /dev/gpiomem do and why is it needed?**
--device /dev/gpiomem is a flag that passes the GPIO memory device into the container so the PIR sensor is readable by the sampler. If this was not included, permission or file-not-found errors would arise.

**RQ6: What happens to the JSONL output if you run the container without a volume mount (-v)?**
If the container is run without a volume mount we would lose the JSONL output as soon as the container stopped working. By using this bind volume mount (-v) we ensure that data survives even after the container stops.

**RQ7: Did the pipeline behave the same inside Docker as it did running directly on the Pi in Lab 03? Any differences?**
The pipeline behaves almost exactly as it did in lab03 with one difference. The events that were produced or consumed were displayed all together at the end of the run and we did not get a constant update of when a new event would be produced or consumed.

**RQ8: What happened when you set --memory=32m? Does this work on the PI? Why yes, why not?**

**RQ9: Why are resource limits important on edge devices in general?**
Edge devices in general have a lower amount of memory, so they more often crash from a runaway process that can consume a lot of the system's memory.

**RQ10: What is the advantage of writing a docker-compose.yml instead of using docker run with flags?**
Using a docker-compose.yml allows the entire configuration to be run with a single command instead of having to run long commands with several flags. In sort, single commands are fine for quick tests but they can be very time consuming, so loading everything in a single-command-runnable configuration file gives a speed advantage.

**RQ11: What is the difference between a bind mount (-v $(pwd)/output:/data) and a named volume (pipeline-data:/data)?**
When using a bind mount the output is maped localy. However using a named volume allows Docker to decide where the data gets stored on the disk. If we ned to acess the files in a named volume we need to use "docker volume inspect" command.

**RQ12: What does restart: unless-stopped do and why does it matter for an edge device?**
restart: unless-stopped:restarts the container automatically after crashes or reboots, but stays stopped if you manually stop it. This matters on edge devices because they frequently lose power or reboot unexpectedly, so online service comes back up without human intervention. Also it allows a container to be stopped intentionally for maintenance without it restarting itself.

**RQ13: What does a virtual environment isolate, and what does it not isolate?**
A virtual environment isolates Python packages and dependencies. Each project gets its own versions of libraries, independent of other projects or the system Python. It does not isolate the Python interpreter , system-level libraries, environment variables, or OS resources.

**RQ14: Give one concrete example where a requirements.txt and a venv would not be enough to reproduce your Lab 03 setup on a different machine.**

**RQ15: Give one scenario where a virtual environment is perhaps a better choice than Docker.**
For a lightweight Python script on a resource-constrained edge device a virtual environment is better than Docker because it has near-zero overhead with no container runtime to run. Docker's daemon can consume significant memory and CPU power on a constrained machine. A venv allows for a clean dependency isolation without the cost.

**RQ16: In the context of the Smart Wastebin project, which approach (venv or Docker) would you prefer to use for a final deployment, and why?**
