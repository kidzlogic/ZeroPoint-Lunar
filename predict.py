import sys
import os
import json
import tensorflow as tf
from tensorflow import keras
import numpy as np

IMG_HEIGHT = 180
IMG_WIDTH = 180
MODEL_PATH = "models/zeropoint_model.keras"
BASE_DIR = "dataset/train"
RULES_PATH = "dataset/articles/hazard_rules.json"

def load_rules():
    if os.path.exists(RULES_PATH):
        with open(RULES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def predict_image(image_path):
    if not os.path.exists(image_path):
        print(f"❌ Error: Image path '{image_path}' does not exist.")
        return

    if not os.path.exists(MODEL_PATH):
        print(f"❌ Error: Model file '{MODEL_PATH}' not found. Please run train.py first.")
        return

    print("Loading model and guidance rules...")
    model = keras.models.load_model(MODEL_PATH)
    rules = load_rules()
    print("Model loaded successfully!\n")

    # Load and preprocess image
    img = tf.keras.utils.load_img(
        image_path, target_size=(IMG_HEIGHT, IMG_WIDTH)
    )
    img_array = tf.keras.utils.img_to_array(img)
    img_array = tf.expand_dims(img_array, 0)

    # Predict
    predictions = model.predict(img_array)
    probabilities = predictions[0]
    
    predicted_class_idx = np.argmax(probabilities)
    confidence = 100 * np.max(probabilities)

    # Get class names alphabetically matching directory structure
    if os.path.exists(BASE_DIR):
        class_names = sorted([d for d in os.listdir(BASE_DIR) if os.path.isdir(os.path.join(BASE_DIR, d))])
    else:
        class_names = ["not_safe", "safe"]

    predicted_class = class_names[predicted_class_idx] if predicted_class_idx < len(class_names) else str(predicted_class_idx)

    # Fetch reason from rules json if available
    rule_info = rules.get(predicted_class, {})
    status_text = rule_info.get("status", predicted_class.upper())
    reason = rule_info.get("description", "No specific description provided in rules file.")

    print("----------------------------------------")
    if predicted_class.lower() == "safe":
        print(f"🟢 {status_text} (Confidence: {confidence:.2f}%)")
    else:
        print(f"🔴 {status_text} (Confidence: {confidence:.2f}%)")
    
    print(f"\n📝 **Analysis / Reason:**")
    print(f"{reason}")
    print("----------------------------------------")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python predict.py <path_to_image>")
    else:
        predict_image(sys.argv[1])