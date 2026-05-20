FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# FIX: was "COPY /src ." (absolute path — wrong syntax).
#      "COPY src/ ." copies src/ contents into /app so python files are
#      directly at /app/api.py, /app/producer.py, etc.
COPY src/ .

# Copy everything else (models/, models_v_s/, train_model.py, data/ …)
COPY . .

# FIX: train and persist the ML model at build time so virtual_sensor_ml
#      does not crash on startup with FileNotFoundError.
RUN python train_model.py

CMD ["python", "producer.py", "--verbose"]
