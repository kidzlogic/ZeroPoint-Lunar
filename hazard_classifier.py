"""TensorFlow inference for the locally trained lunar terrain image classifier."""
import json
from functools import lru_cache
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
MODEL_PATH = ROOT_DIR / "models" / "zeropoint_model.keras"
CLASS_NAMES_PATH = ROOT_DIR / "models" / "zeropoint_classes.json"
RULES_PATH = ROOT_DIR / "dataset" / "articles" / "hazard_rules.json"
IMG_HEIGHT = 180
IMG_WIDTH = 180


def load_rules():
    if RULES_PATH.exists():
        with RULES_PATH.open("r", encoding="utf-8") as file:
            return json.load(file)
    return {
        "safe": {
            "status": "EXPERIMENTAL IMAGE LABEL",
            "description": "The model assigned its experimental 'safe' label. This is not a terrain safety finding or traversal clearance.",
        },
        "not_safe": {
            "status": "EXPERIMENTAL IMAGE LABEL",
            "description": "The model assigned its experimental 'not_safe' label. This is not a validated hazard determination.",
        },
    }


@lru_cache(maxsize=1)
def _load_model():
    import tensorflow as tf

    if not MODEL_PATH.is_file():
        raise FileNotFoundError(
            "The lunar image model is missing. Run python train.py to create it."
        )
    if not CLASS_NAMES_PATH.is_file():
        raise FileNotFoundError(
            "Model class labels are missing. Run python train.py to retrain and label the model."
        )

    with CLASS_NAMES_PATH.open("r", encoding="utf-8") as file:
        metadata = json.load(file)
    class_names = metadata.get("class_names")
    if not isinstance(class_names, list) or not all(
        isinstance(name, str) for name in class_names
    ):
        raise ValueError(f"Invalid class labels in {CLASS_NAMES_PATH}.")

    model = tf.keras.models.load_model(MODEL_PATH, compile=False)
    if model.output_shape[-1] != len(class_names):
        raise ValueError(
            "The saved model output does not match its class labels. "
            "Run python train.py to retrain the classifier."
        )
    return model, class_names


def available_model_classes():
    if not CLASS_NAMES_PATH.is_file():
        return []
    with CLASS_NAMES_PATH.open("r", encoding="utf-8") as file:
        metadata = json.load(file)
    class_names = metadata.get("class_names", [])
    if not isinstance(class_names, list) or not all(
        isinstance(name, str) for name in class_names
    ):
        raise ValueError(f"Invalid class labels in {CLASS_NAMES_PATH}.")
    return class_names


def model_validation_summary():
    if not CLASS_NAMES_PATH.is_file():
        return "Validation metrics unavailable; retrain the image model."
    with CLASS_NAMES_PATH.open("r", encoding="utf-8") as file:
        metadata = json.load(file)
    validation = metadata.get("validation", {})
    accuracy = validation.get("accuracy")
    recall = validation.get("class_recall")
    if not isinstance(accuracy, (int, float)) or not isinstance(recall, dict):
        return "Validation metrics unavailable; retrain the image model."
    class_names = metadata.get("class_names")
    confusion = validation.get("confusion_matrix")
    valid_confusion = (
        isinstance(class_names, list)
        and len(class_names) > 0
        and all(isinstance(name, str) for name in class_names)
        and isinstance(confusion, list)
        and len(confusion) == len(class_names)
        and all(
            isinstance(row, list)
            and len(row) == len(class_names)
            and all(isinstance(value, int) and value >= 0 for value in row)
            for row in confusion
        )
    )
    if valid_confusion:
        supports = [sum(row) for row in confusion]
        predicted_counts = [
            sum(confusion[row][column] for row in range(len(class_names)))
            for column in range(len(class_names))
        ]
        observed_recalls = [
            confusion[index][index] / supports[index]
            for index in range(len(class_names))
            if supports[index]
        ]
        balanced_accuracy = sum(observed_recalls) / len(observed_recalls)
        recalls = ", ".join(
            f"{name}: {confusion[index][index] / supports[index]:.0%} "
            f"({confusion[index][index]}/{supports[index]})"
            if supports[index]
            else f"{name}: unavailable (0 samples)"
            for index, name in enumerate(class_names)
        )
        predictions = ", ".join(
            f"{name}: {predicted_counts[index]}"
            for index, name in enumerate(class_names)
        )
        precisions = ", ".join(
            f"{name}: {confusion[index][index] / predicted_counts[index]:.0%} "
            f"({confusion[index][index]}/{predicted_counts[index]})"
            if predicted_counts[index]
            else f"{name}: unavailable (0 predictions)"
            for index, name in enumerate(class_names)
        )
        evidence = (
            f"Balanced accuracy {balanced_accuracy:.0%}. "
            f"Class recall -- {recalls}. Class precision -- {precisions}. "
            f"Predicted labels -- {predictions}."
        )
    else:
        recalls = ", ".join(
            f"{name}: {float(value):.0%}" for name, value in recall.items()
        )
        evidence = f"Class recall -- {recalls}."
    protocol = validation.get(
        "protocol",
        "Random 20% holdout from dataset/train; not an independent or "
        "mission-representative test set.",
    )
    return (
        f"Validation accuracy {float(accuracy):.0%}. {evidence} "
        f"{protocol} Image-source provenance is not recorded."
    )


def classify_image(image_path: str):
    import tensorflow as tf

    model, class_names = _load_model()
    image = tf.keras.utils.load_img(
        image_path, target_size=(IMG_HEIGHT, IMG_WIDTH)
    )
    image_array = tf.keras.utils.img_to_array(image)
    predictions = model.predict(tf.expand_dims(image_array, 0), verbose=0)[0]
    if predictions.shape[0] != len(class_names):
        raise ValueError("The classifier returned an unexpected number of scores.")

    scores = {
        name: round(100 * float(predictions[index]), 2)
        for index, name in enumerate(class_names)
    }
    predicted_class = class_names[int(predictions.argmax())]
    rule_info = load_rules().get(predicted_class, {})
    reason = rule_info.get(
        "description",
        "No description is available for this model class.",
    )
    return predicted_class, scores[predicted_class], reason, scores
