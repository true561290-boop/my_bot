import json
import time
from pathlib import Path

import requests

API_URL = "https://api.jikan.moe/v4/top/characters"
OUTPUT_FILE = Path(__file__).with_name("anime_characters.json")
TARGET_COUNT = 1000
PER_PAGE = 25


def fetch_page(page: int):
    response = requests.get(API_URL, params={"page": page}, timeout=30)
    response.raise_for_status()
    return response.json().get("data", [])


def main():
    characters = []
    seen_ids = set()
    page = 1

    while len(characters) < TARGET_COUNT:
        print(f"جلب الصفحة {page}... ({len(characters)}/{TARGET_COUNT})")
        data = fetch_page(page)
        if not data:
            break

        for item in data:
            mal_id = item.get("mal_id")
            name = item.get("name")
            images = item.get("images") or {}
            jpg = images.get("jpg") or {}
            image_url = jpg.get("large_image_url") or jpg.get("image_url")
            source_url = item.get("url")

            if not mal_id or not name or not image_url or mal_id in seen_ids:
                continue

            seen_ids.add(mal_id)
            characters.append({
                "id": mal_id,
                "name": name,
                "answers": [name],
                "image_url": image_url,
                "source_url": source_url,
            })

            if len(characters) >= TARGET_COUNT:
                break

        page += 1
        # Jikan يسمح بحد أقصى 3 طلبات/ثانية و60 طلباً/دقيقة.
        time.sleep(1.05)

    characters = characters[:TARGET_COUNT]
    OUTPUT_FILE.write_text(
        json.dumps(characters, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\nتم إنشاء {OUTPUT_FILE.name} وفيه {len(characters)} شخصية.")
    if len(characters) < TARGET_COUNT:
        print("تحذير: لم يتم الوصول إلى 1000 شخصية بسبب انتهاء البيانات أو خطأ في API.")


if __name__ == "__main__":
    main()
