import os
import json
import requests
from ddgs import DDGS

# ============================== CONFIGURATION ==============================
BASE_DIR = "dataset/train"
HAZARD_DIR = os.path.join(BASE_DIR, "not_safe")
ARTICLES_DIR = os.path.join(BASE_DIR, "articles")

os.makedirs(HAZARD_DIR, exist_ok=True)
os.makedirs(ARTICLES_DIR, exist_ok=True)

TOTAL_IMAGES = 50          # total dangerous (dust) images to collect
MAX_PER_QUERY = 7          # cap per query so the set stays varied
MIN_BYTES = 5_000          # skip tiny/broken downloads

# Focus: the dust itself (plumes, kicked-up dust, explosion-like clouds),
# NOT hazardous terrain like craters, slopes, or boulders.
DUST_QUERIES = [
    "lunar dust plume kicked up by rover wheel moon",
    "Apollo lunar rover rooster tail dust moon surface",
    "lunar module landing engine plume blowing regolith dust",
    "astronaut boot print dust cloud moon surface",
    "moon impact explosion flash lunar surface",
    "volcanic ash plume eruption explosion cloud",
    "dust explosion plume dirt cloud blast",
    "car wheels kicking up dust cloud dirt road",
    "flying lunar dust levitating regolith cloud",
]

def load_lunar_resources():
    """Keep an existing curated reference_links.json instead of shrinking it on rebuild."""
    path = os.path.join(ARTICLES_DIR, "reference_links.json")
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as handle:
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
# ===========================================================================

EXT_BY_TYPE = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


def save_articles_section():
    path = os.path.join(ARTICLES_DIR, "reference_links.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(load_lunar_resources(), f, indent=4)
    print(f"📄 Saved article links to: {path}")


def next_index(target_dir):
    """Continue numbering after existing files so nothing gets overwritten."""
    existing = [f for f in os.listdir(target_dir) if f.startswith("dust_")]
    return len(existing) + 1


def try_download(img_url, target_dir, index):
    """Download one image; return saved path or None."""
    try:
        resp = requests.get(img_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=6)
        if resp.status_code != 200:
            return None
        ctype = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
        ext = EXT_BY_TYPE.get(ctype)
        if ext is None or len(resp.content) < MIN_BYTES:
            return None
        path = os.path.join(target_dir, f"dust_{index:03d}{ext}")
        with open(path, "wb") as f:
            f.write(resp.content)
        return path
    except Exception:
        return None


def build_hazard_images():
    seen_urls = set()
    saved = 0
    index = next_index(HAZARD_DIR)

    for query in DUST_QUERIES:
        if saved >= TOTAL_IMAGES:
            break
        print(f"🔍 Query: '{query}'")
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

                    path = try_download(img_url, HAZARD_DIR, index)
                    if path:
                        index += 1
                        saved += 1
                        query_count += 1
                        print(f"   Saved [{saved}/{TOTAL_IMAGES}]: {path}")
        except Exception as e:
            print(f"⚠️ Error during search for '{query}': {e}")

    print(f"✅ Collected {saved} dust-hazard images in {HAZARD_DIR}")
    if saved < TOTAL_IMAGES:
        print("ℹ️ Fewer than the target were found; re-run to top up (numbering continues).")


if __name__ == "__main__":
    print("🚀 Starting ZeroPoint Lunar dust-image builder...")
    save_articles_section()
    build_hazard_images()
    print("\n✨ Done!")