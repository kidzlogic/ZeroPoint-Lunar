import os
from PIL import Image

BASE_DIR = "dataset/train"

def clean_images(directory):
    print(f"🧹 Scanning directory: {directory}")
    removed_count = 0
    if not os.path.exists(directory):
        print(f"Directory not found: {directory}")
        return
        
    for root, dirs, files in os.walk(directory):
        for file in files:
            file_path = os.path.join(root, file)
            try:
                with Image.open(file_path) as img:
                    img.verify()
            except Exception as e:
                print(f"❌ Removing corrupted/invalid image: {file_path} ({e})")
                os.remove(file_path)
                removed_count += 1
                
    print(f"✨ Finished cleaning {directory}. Removed {removed_count} bad files.\n")

if __name__ == "__main__":
    print("🚀 Starting dataset image validation and cleanup...")
    for subdir in os.listdir(BASE_DIR):
        sub_path = os.path.join(BASE_DIR, subdir)
        if os.path.isdir(sub_path):
            clean_images(sub_path)
    print("All done! You can now re-run your training script.")