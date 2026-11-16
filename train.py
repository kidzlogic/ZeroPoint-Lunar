import json
from pathlib import Path
import numpy as np
import tensorflow as tf
from tensorflow import keras

layers = keras.layers

ROOT_DIR = Path(__file__).resolve().parent
BASE_DIR = ROOT_DIR / "dataset" / "train"
MODEL_DIR = ROOT_DIR / "models"
MODEL_PATH = MODEL_DIR / "zeropoint_model.keras"
CLASS_NAMES_PATH = MODEL_DIR / "zeropoint_classes.json"
IMG_HEIGHT = 180
IMG_WIDTH = 180
BATCH_SIZE = 32
EPOCHS = 10
SUPPORTED_IMAGE_SUFFIXES = {".bmp", ".gif", ".jpeg", ".jpg", ".png"}

MODEL_DIR.mkdir(parents=True, exist_ok=True)
class_names = sorted(
    directory.name
    for directory in BASE_DIR.iterdir()
    if directory.is_dir()
    and any(
        image.is_file() and image.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES
        for image in directory.iterdir()
    )
)
if len(class_names) < 2:
    raise ValueError(
        f"Expected at least two non-empty image classes in {BASE_DIR}; found {class_names}."
    )

print("Loading training and validation datasets...")
train_ds = tf.keras.utils.image_dataset_from_directory(
    BASE_DIR,
    validation_split=0.2,
    subset="training",
    seed=123,
    image_size=(IMG_HEIGHT, IMG_WIDTH),
    batch_size=BATCH_SIZE,
    class_names=class_names,
)

val_ds = tf.keras.utils.image_dataset_from_directory(
    BASE_DIR,
    validation_split=0.2,
    subset="validation",
    seed=123,
    image_size=(IMG_HEIGHT, IMG_WIDTH),
    batch_size=BATCH_SIZE,
    class_names=class_names,
)

print(f"Detected classes: {class_names}")

AUTOTUNE = tf.data.AUTOTUNE
train_ds = train_ds.cache().shuffle(1000).prefetch(buffer_size=AUTOTUNE)
val_ds = val_ds.cache().prefetch(buffer_size=AUTOTUNE)

num_classes = len(class_names)
label_counts = np.zeros(num_classes, dtype=np.int64)
for _, labels in train_ds:
    label_counts += np.bincount(
        labels.numpy().astype(np.int64),
        minlength=num_classes,
    )
class_weights = {
    class_index: float(label_counts.sum() / (num_classes * count))
    for class_index, count in enumerate(label_counts)
}
print(f"Training class weights: {class_weights}")

# Data augmentation helps the model handle different sun/shadow angles
data_augmentation = keras.Sequential([
    layers.RandomFlip("horizontal_and_vertical"),
    layers.RandomRotation(0.2),
    layers.RandomZoom(0.1),
])

model = keras.Sequential([
    keras.Input(shape=(IMG_HEIGHT, IMG_WIDTH, 3)),
    data_augmentation,
    layers.Rescaling(1./255),
    layers.Conv2D(16, 3, padding='same', activation='relu'),
    layers.MaxPooling2D(),
    layers.Conv2D(32, 3, padding='same', activation='relu'),
    layers.MaxPooling2D(),
    layers.Conv2D(64, 3, padding='same', activation='relu'),
    layers.MaxPooling2D(),
    layers.Dropout(0.3),
    layers.Flatten(),
    layers.Dense(128, activation='relu'),
    layers.Dense(num_classes, activation='softmax')
])

model.compile(
    optimizer='adam',
    loss=tf.keras.losses.SparseCategoricalCrossentropy(from_logits=False),
    metrics=['accuracy']
)

model.summary()

print("Starting ZeroPoint Lunar training loop...")
model.fit(
    train_ds,
    validation_data=val_ds,
    epochs=EPOCHS,
    class_weight=class_weights,
    callbacks=[
        keras.callbacks.EarlyStopping(
            monitor="val_loss",
            patience=3,
            restore_best_weights=True,
        )
    ],
)

validation_labels = []
validation_predictions = []
for images, labels in val_ds:
    validation_predictions.extend(
        np.argmax(model.predict(images, verbose=0), axis=1).tolist()
    )
    validation_labels.extend(labels.numpy().astype(np.int64).tolist())

confusion = np.zeros((num_classes, num_classes), dtype=np.int64)
for actual, predicted in zip(validation_labels, validation_predictions):
    confusion[actual, predicted] += 1
class_recall = {
    class_names[index]: float(confusion[index, index] / confusion[index].sum())
    if confusion[index].sum()
    else 0.0
    for index in range(num_classes)
}
class_support = {
    class_names[index]: int(confusion[index].sum())
    for index in range(num_classes)
}
predicted_counts = {
    class_names[index]: int(confusion[:, index].sum())
    for index in range(num_classes)
}
class_precision = {
    class_names[index]: float(confusion[index, index] / confusion[:, index].sum())
    if confusion[:, index].sum()
    else 0.0
    for index in range(num_classes)
}
class_f1 = {
    name: float(2 * class_precision[name] * class_recall[name]
                / (class_precision[name] + class_recall[name]))
    if class_precision[name] + class_recall[name]
    else 0.0
    for name in class_names
}
balanced_accuracy = float(np.mean(list(class_recall.values())))
validation_accuracy = float(np.mean(
    np.asarray(validation_labels) == np.asarray(validation_predictions)
))
print(f"Validation accuracy: {validation_accuracy:.3f}")
print(f"Validation confusion matrix: {confusion.tolist()}")
print(f"Per-class recall: {class_recall}")
print(f"Per-class precision: {class_precision}")
print(f"Per-class F1: {class_f1}")
print(f"Balanced accuracy: {balanced_accuracy:.3f}")

model.save(MODEL_PATH)
with CLASS_NAMES_PATH.open("w", encoding="utf-8") as file:
    json.dump(
        {
            "class_names": class_names,
            "image_size": [IMG_HEIGHT, IMG_WIDTH],
            "training_data": str(BASE_DIR.relative_to(ROOT_DIR)),
            "validation": {
                "accuracy": validation_accuracy,
                "confusion_matrix": confusion.tolist(),
                "class_recall": class_recall,
                "class_support": class_support,
                "predicted_counts": predicted_counts,
                "class_precision": class_precision,
                "class_f1": class_f1,
                "balanced_accuracy": balanced_accuracy,
                "protocol": (
                    "Random 20% holdout from dataset/train; not an independent "
                    "or mission-representative test set."
                ),
            },
        },
        file,
        indent=2,
    )
print(f"\nModel and class labels saved to {MODEL_PATH} and {CLASS_NAMES_PATH}")