import os
import json
import requests
from ddgs import DDGS

# ============================== CONFIGURATION ==============================
BASE_DIR = "dataset/train"
SAFE_DIR = os.path.join(BASE_DIR, "safe")
HAZARD_DIR = os.path.join(BASE_DIR, "not_safe")
ARTICLES_DIR = "dataset/articles"

os.makedirs(SAFE_DIR, exist_ok=True)
os.makedirs(HAZARD_DIR, exist_ok=True)
os.makedirs(ARTICLES_DIR, exist_ok=True)

TOTAL_IMAGES = 60          # Increased to give more variety per class
MAX_PER_QUERY = 10
MIN_BYTES = 5_000

# Safe: Includes smooth plains AND moderately bumpy/gently cratered terrain
SAFE_QUERIES = [
    "flat lunar maria smooth basalt plain moon surface",
    "gentle rolling lunar hills bumpy terrain moon",
    "lunar surface small shallow craters rover traverse",
    "apollo landing site terrain minor rocks bumps moon",
    "moderately cratered lunar plain LROC image",
    "smooth lunar regolith landing zone moon"
]

# Not Safe: Deep steep-walled craters, boulder fields, and violent dust plumes
HAZARD_QUERIES = [
    "deep steep lunar crater wall rim shadow hazard",
    "dense lunar boulder field rocky hazard moon surface",
    "lunar module landing engine plume blowing regolith dust",
    "apollo lunar rover rooster tail dust cloud moon",
    "flying lunar dust levitating regolith plume storm",
    "moon impact ejecta flash dust cloud"
]

def load_lunar_resources():
    """Prefer the curated corpus already on disk so rebuilds do not wipe newer links."""
    links_path = os.path.join(ARTICLES_DIR, "reference_links.json")
    if os.path.isfile(links_path):
        try:
            with open(links_path, encoding="utf-8") as handle:
                payload = json.load(handle)
            if isinstance(payload, list) and payload:
                return payload
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    return [
        {
            "title": "NASA NTRS: Lunar Regolith Characterization",
            "url": "https://ntrs.nasa.gov/api/citations/20080005580/downloads/20080005580.pdf"
        },
        {
            "title": "NASA Science: Moon Dust Hazards",
            "url": "https://science.nasa.gov/biological-physical/what-hazards-are-caused-by-lunar-regolith/"
        },
        {
            "title": "SciOpen: Properties of Lunar Dust and Their Migration on the Moon",
            "url": "https://www.sciopen.com/article/10.34133/space.0142"
        },
        {
            "title": "NASA OCHMO: Lunar Dust Technical Brief",
            "url": "https://www.nasa.gov/wp-content/uploads/2023/03/lunar-dust-technical-brief-ochmo.pdf"
        }
    ]


LUNAR_RESOURCES = load_lunar_resources()

HAZARD_RULES = {
    "safe": {
        "status": "EXPERIMENTAL CLASS LABEL - NOT A CLEARANCE",
        "description": "The image was assigned to the dataset's 'safe' label. The dataset and model are not validated for lunar traverse decisions; this is not a safety finding."
    },
    "not_safe": {
        "status": "EXPERIMENTAL CLASS LABEL - REVIEW REQUIRED",
        "description": "The image was assigned to the dataset's 'not_safe' label. This is not a validated hazard determination; review the image and independent terrain data."
    }
}

EXT_BY_TYPE = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

def save_metadata_files():
    links_path = os.path.join(ARTICLES_DIR, "reference_links.json")
    resources = load_lunar_resources()
    with open(links_path, "w", encoding="utf-8") as f:
        json.dump(resources, f, indent=4)
        
    rules_path = os.path.join(ARTICLES_DIR, "hazard_rules.json")
    with open(rules_path, "w", encoding="utf-8") as f:
        json.dump(HAZARD_RULES, f, indent=4)
    print(f"📄 Saved reference links and hazard rules to: {ARTICLES_DIR}")

def next_index(target_dir, prefix):
    existing = [f for f in os.listdir(target_dir) if f.startswith(prefix)]
    return len(existing) + 1

def try_download(img_url, target_dir, prefix, index):
    try:
        resp = requests.get(img_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=6)
        if resp.status_code != 200:
            return None
        ctype = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
        ext = EXT_BY_TYPE.get(ctype)
        if ext is None or len(resp.content) < MIN_BYTES:
            return None
        path = os.path.join(target_dir, f"{prefix}_{index:03d}{ext}")
        with open(path, "wb") as f:
            f.write(resp.content)
        return path
    except Exception:
        return None

def build_category_images(queries, target_dir, prefix):
    seen_urls = set()
    saved = 0
    index = next_index(target_dir, prefix)

    for query in queries:
        if saved >= TOTAL_IMAGES:
            break
        print(f"🔍 Query ('{prefix}'): '{query}'")
        query_count = 0
        try:
            with DDGS() as ddgs:
                results = ddgs.images(query, max_results=MAX_PER_QUERY * 4)
                for r in results:
                    if saved >= TOTAL_IMAGES or query_count >= MAX_PER_QUERY:
                        break
                    img_url = r.get("image")
                    if not img_url or img_url in seen_urls:
                        continue
                    seen_urls.add(img_url)

                    path = try_download(img_url, target_dir, prefix, index)
                    if path:
                        index += 1
                        saved += 1
                        query_count += 1
                        print(f"    Saved [{saved}/{TOTAL_IMAGES}]: {path}")
        except Exception as e:
            print(f"⚠️ Error during search for '{query}': {e}")

    print(f"✅ Collected {saved} images in {target_dir}\n")

if __name__ == "__main__":
    print("🚀 Starting ZeroPoint Lunar balanced asset builder...")
    save_metadata_files()
    print("\n--- Collecting Safe Terrain (Flat & Moderately Bumpy/Cratered) ---")
    build_category_images(SAFE_QUERIES, SAFE_DIR, "safe")
    print("\n--- Collecting Hazard Terrain (Deep Craters, Boulders, Plumes) ---")
    build_category_images(HAZARD_QUERIES, HAZARD_DIR, "not_safe")
    print("✨ All data collection finished!")