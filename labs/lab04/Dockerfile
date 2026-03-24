FROM python:3.11-slim

WORKDIR /lab04

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY pirlib/ pirlib/

COPY run_pipeline.py .

CMD ["python", "run_pipeline.py", "--device-id", "pir-01", "--pin", "17", "--sample-interval", "0.1", "--cooldown", "5.0", "--min-high", "0.2", "--queue-size", "100", "--consumer-delay", "0.5", "--duration", "60", "--out", "motion_slow.jsonl", "--verbose"]