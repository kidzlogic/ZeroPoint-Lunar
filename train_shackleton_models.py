"""Train the five Shackleton traverse models and write their held-out scores."""
import json

import numpy as np
import tensorflow as tf
from tensorflow import keras

from shackleton_models import MODEL_DIR, MODEL_SPECS, REPORT_PATH, training_tables

EPOCHS = 40
BATCH = 32


def _split(count, seed=42):
    order = np.arange(count)
    rng = np.random.default_rng(seed)
    rng.shuffle(order)
    cut = int(count * 0.8)
    return order[:cut], order[cut:]


def _fit_one(features, labels, train_index, val_index):
    model = keras.Sequential([
        keras.layers.Input(shape=(features.shape[1],)),
        keras.layers.Dense(32, activation="relu"),
        keras.layers.Dense(16, activation="relu"),
        keras.layers.Dense(1, activation="sigmoid"),
    ])
    model.compile(optimizer="adam", loss="binary_crossentropy", metrics=["accuracy"])
    train_labels = labels[train_index]
    positives = float(train_labels.sum())
    negatives = float(len(train_labels) - positives)
    weight_for_one = negatives / max(positives, 1.0)
    model.fit(
        features[train_index],
        train_labels,
        validation_data=(features[val_index], labels[val_index]),
        epochs=EPOCHS,
        batch_size=BATCH,
        class_weight={0: 1.0, 1: weight_for_one},
        verbose=0,
    )
    held_out = model.predict(features[val_index], verbose=0).reshape(-1)
    truth = labels[val_index]
    accuracy = float(np.mean((held_out >= 0.5) == (truth >= 0.5)))
    return model, accuracy, positives, float(truth.mean())


def main():
    features, labels, spacing, records = training_tables()
    mean = features.mean(axis=0)
    scale = features.std(axis=0)
    scale[scale < 1e-6] = 1.0
    scaled = (features - mean) / scale
    train_index, val_index = _split(len(records))
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    trained = []
    for name, question, rule in MODEL_SPECS:
        model, accuracy, positives, val_rate = _fit_one(scaled, labels[name], train_index, val_index)
        model.save(MODEL_DIR / f"{name}.keras")
        trained.append({
            "id": name,
            "file": f"{name}.keras",
            "question": question,
            "rule": rule,
            "held_out_accuracy": round(accuracy, 3),
            "train_positive_cells": int(positives),
            "held_out_positive_rate": round(val_rate, 3),
        })
        print(f"{name}: held-out accuracy {accuracy:.3f}")
    report = {
        "source": "NASA LOLA LDEM 16, NASA Scientific Visualization Studio lunar elevation.",
        "center": {"name": "Shackleton rim", "lat": -89.5, "lon": 0.0},
        "radius_km": 40.0,
        "spacing_km": round(spacing, 2),
        "train_cells": int(len(train_index)),
        "held_out_cells": int(len(val_index)),
        "feature_mean": [round(float(value), 6) for value in mean],
        "feature_scale": [round(float(value), 6) for value in scale],
        "models": trained,
        "note": (
            "Each model sees the eight neighboring LOLA heights plus latitude and longitude. "
            "It does not see the center slope. Held-out accuracy is cells from this same crater "
            "that were left out of training. LDEM 16 is about 1.9 km per pixel, so a cell is not a footstep. "
            "These models do not detect water ice."
        ),
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote {REPORT_PATH}")


if __name__ == "__main__":
    main()
