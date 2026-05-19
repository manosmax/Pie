import paho.mqtt.client as mqtt
import json
import time
import argparse
import joblib
import numpy as np
from datetime import datetime, timezone


def load_model(path):
    return joblib.load(path)


def predict_next_hour(model):
    now = datetime.now()

    next_hour = (now.hour + 1) % 24
    day_of_week = now.weekday()  
    is_weekend = 1 if day_of_week in (5, 6) else 0

    features = np.array([[day_of_week, next_hour, is_weekend]])

    prediction = model.predict(features)[0]
    proba = model.predict_proba(features)[0]
    classes = list(model.classes_)
    confidence = proba[classes.index(prediction)]

    return prediction, confidence, next_hour


def main():
    parser = argparse.ArgumentParser(description="ML Virtual Sensor — predicts busy/quiet")
    parser.add_argument("--broker",        default="localhost",                    help="MQTT broker hostname or IP address")
    parser.add_argument("--port",          type=int, default=1883,                 help="MQTT broker port")
    parser.add_argument("--publish-topic", default="smartbin/bin-01/prediction",  help="MQTT topic where predictions will be published")
    parser.add_argument("--model-path",    default="models_v_s/busy_predictor.joblib", help="File path of the trained ML model")
    parser.add_argument("--interval",      type=int, default=60,                   help="Prediction interval in seconds")
    parser.add_argument("--bin-id",        default="bin-01",                       help="Identifier for the smart bin")
    args = parser.parse_args()

    model = load_model(args.model_path)
    print(f"[ML] Model loaded from {args.model_path}")

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "virtual-sensor-ml")
    client.connect(args.broker, args.port)
    client.loop_start()

    print(f"[ML] Publishing to '{args.publish_topic}' every {args.interval}s")

    try:
        while True:
            prediction, confidence, next_hour = predict_next_hour(model)

            now = datetime.now()
            timestamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

            payload = json.dumps({
                "prediction": prediction,
                "confidence": round(float(confidence), 3),
                "predicted_hour": next_hour,
                "timestamp": timestamp,
                "model": "busy_predictor.joblib",
                "features": {
                    "day_of_week": now.weekday(),
                    "predicted_hour": next_hour,
                    "is_weekend": 1 if now.weekday() in (5, 6) else 0,
                },
            })

            client.publish(args.publish_topic, payload, qos=1, retain=True)

            print(
                f"[ML] Hour {next_hour:02d}:00 → {prediction.upper()} "
                f"(confidence: {confidence * 100:.1f}%)"
            )

            time.sleep(args.interval)

    except KeyboardInterrupt:
        print("\n[ML] Stopping...")
        client.disconnect()


if __name__ == "__main__":
    main()
