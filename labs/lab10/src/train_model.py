import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
import joblib
import os


def generate_training_data(days=30, seed=42):
    rng = np.random.default_rng(seed)
    rows = []

    for day in range(days):
        day_of_week = day % 7 

        for hour in range(24):
            if day_of_week in (5, 6):       
                base_rate = 2
            elif 8 <= hour <= 10:           
                base_rate = 15
            elif 11 <= hour <= 14:           
                base_rate = 25
            elif 15 <= hour <= 17:           
                base_rate = 12
            elif 18 <= hour <= 20:          
                base_rate = 8
            else:                            
                base_rate = 1

            event_count = int(rng.normal(base_rate, base_rate * 0.3))
            if event_count < 0:
                event_count = 0

            label = "busy" if event_count > 10 else "quiet"

            rows.append({
                "day_of_week": day_of_week,
                "hour": hour,
                "is_weekend": 1 if day_of_week in (5, 6) else 0,
                "event_count": event_count,
                "label": label,
            })

    return pd.DataFrame(rows)


def train_and_save(output_dir="models_v_s"):
    os.makedirs(output_dir, exist_ok=True)

    df = generate_training_data()

    X = df[["day_of_week", "hour", "is_weekend"]]
    y = df["label"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    clf = RandomForestClassifier(n_estimators=50, random_state=42)
    clf.fit(X_train, y_train)

    y_pred = clf.predict(X_test)

    print("Model evaluation:")
    print(classification_report(y_test, y_pred))

    model_path = os.path.join(output_dir, "busy_predictor.joblib")
    joblib.dump(clf, model_path)
    print(f"Model saved to {model_path}")

    return clf


if __name__ == "__main__":
    train_and_save()
