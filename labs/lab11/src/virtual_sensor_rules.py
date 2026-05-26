import argparse
import json
import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone

import paho.mqtt.client as mqtt



event_times: deque = deque()
event_lock = threading.Lock()



def send_discovery(client, bin_id: str, publish_topic: str) -> None:

    device_info = {
        "identifiers": [bin_id],
        "name": f"Smart Waste Bin {bin_id}",
        "model": "IoT-Bin-v2",
        "manufacturer": "Team 08",
    }

    usage_config = {
        "name": f"Waste Bin {bin_id} Usage Level",
        "state_topic": publish_topic,
        "value_template": "{{ value_json.usage_level }}",
        "icon": "mdi:motion-sensor",
        "unique_id": f"{bin_id}_usage_level",
        "device": device_info,
    }

    count_config = {
        "name": f"Waste Bin {bin_id} Motion Count",
        "state_topic": publish_topic,
        "value_template": "{{ value_json.event_count }}",
        "unit_of_measurement": "events",
        "state_class": "measurement",
        "icon": "mdi:counter",
        "unique_id": f"{bin_id}_motion_count",
        "device": device_info,
    }

    client.publish(
        f"homeassistant/sensor/{bin_id}_usage_level/config",
        json.dumps(usage_config),
        qos=1,
        retain=True,
    )
    client.publish(
        f"homeassistant/sensor/{bin_id}_motion_count/config",
        json.dumps(count_config),
        qos=1,
        retain=True,
    )
    print("[HA] Discovery sent for Usage Level and Motion Count entities.")



def on_connect(client, userdata, flags, reason_code, properties=None):
    subscribe_topic = userdata["subscribe_topic"]
    publish_topic   = userdata["publish_topic"]
    bin_id          = userdata["bin_id"]

    if reason_code == 0:
        print("[MQTT] Connected to broker.")
        client.subscribe(subscribe_topic, qos=1)
        print(f"[MQTT] Subscribed to {subscribe_topic}")
        send_discovery(client, bin_id, publish_topic)
    else:
        print(f"[MQTT] Connection failed with code {reason_code}")


def on_disconnect(client, userdata, disconnect_flags=None, reason_code=None, properties=None):
    if reason_code and reason_code != 0:
        print(f"[MQTT] Unexpected disconnect (reason_code={reason_code}). Will auto-reconnect...")


def on_message(client, userdata, message):

    try:
        data = json.loads(message.payload.decode("utf-8", errors="replace"))
        if data.get("motion_state", "").lower() == "detected":
            with event_lock:
                event_times.append(datetime.now(timezone.utc))

    except (json.JSONDecodeError, AttributeError):
        pass  
    except Exception as exc:
        print(f"[WARN] Could not process message: {exc}")


def evaluate_usage(window_minutes: int = 10) -> tuple[str, int]:

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)

    with event_lock:
        while event_times and event_times[0] < cutoff:
            event_times.popleft()
        count = len(event_times)

    if count == 0:
        return "idle", count
    elif count <= 3:
        return "low", count
    elif count <= 10:
        return "medium", count
    else:
        return "high", count


def main():
    parser = argparse.ArgumentParser(
        description="Virtual sensor: classifies PIR motion events into usage levels."
    )
    parser.add_argument("--broker",          default="localhost",
                        help="MQTT broker hostname (default: localhost)")
    parser.add_argument("--port",            default=1883, type=int,
                        help="MQTT broker port (default: 1883)")
    parser.add_argument("--bin-id",          default="bin-01",
                        help="Bin identifier, used for HA discovery (default: bin-01)")
    parser.add_argument("--subscribe-topic", default="smartbin/bin-01/pir-01/events",
                        help="Topic to consume motion events from")
    parser.add_argument("--publish-topic",   default="smartbin/bin-01/usage",
                        help="Topic to publish usage-level messages to")
    parser.add_argument("--window",          default=10, type=int,
                        help="Rolling time window in minutes (default: 10)")
    parser.add_argument("--interval",        default=30, type=int,
                        help="Seconds between evaluations (default: 30)")
    args = parser.parse_args()

    userdata = {
        "subscribe_topic": args.subscribe_topic,
        "publish_topic":   args.publish_topic,
        "bin_id":          args.bin_id,
    }

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id="virtual-sensor-rules",
        userdata=userdata,
    )
    client.on_connect    = on_connect
    client.on_disconnect = on_disconnect
    client.on_message    = on_message

    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.connect(args.broker, args.port, keepalive=60)
    client.loop_start()

    print(
        f"[INFO] Monitoring  : {args.subscribe_topic}\n"
        f"[INFO] Window      : {args.window} min\n"
        f"[INFO] Interval    : {args.interval} s\n"
        f"[INFO] Publishing  : {args.publish_topic}"
    )

    try:
        while True:
            level, count = evaluate_usage(args.window)

            payload = json.dumps({
                "usage_level":    level,
                "event_count":    count,
                "window_minutes": args.window,
                "evaluated_at":   datetime.now(timezone.utc)
                                      .isoformat(timespec="milliseconds")
                                      .replace("+00:00", "Z"),
            })

            client.publish(args.publish_topic, payload, qos=1, retain=True)

            print(
                f"[USAGE] level={level:6s}  events={count:3d}  "
                f"window={args.window}min  topic={args.publish_topic}"
            )

            time.sleep(args.interval)

    except KeyboardInterrupt:
        print("\n[INFO] Shutting down virtual sensor rules.")
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()