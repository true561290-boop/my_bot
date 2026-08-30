import json
from pathlib import Path
import requests

# مسار الملف الذي سيتم إنشاؤه
OUTPUT_FILE = Path(__file__).with_name("anime_characters.json")
RM_API_URL = "https://rickandmortyapi.com/api/character"
TARGET_COUNT = 100

def main():
    characters = []
    page = 1

    print("🚀 البدء بجلب شخصيات ريك ومورتي...")

    while len(characters) < TARGET_COUNT:
        print(f"جلب الصفحة {page}... ({len(characters)}/{TARGET_COUNT})")
        try:
            # جلب البيانات من واجهة ريك ومورتي
            response = requests.get(f"{RM_API_URL}?page={page}", timeout=15)
            response.raise_for_status()
            data = response.json().get('results', [])
            
            if not data:
                break

            for item in data:
                name = item.get('name')
                image_url = item.get('image')
                # تمييز الآيدي بـ rm_ تحسباً لو أردت إضافة أنمي لاحقاً
                char_id = f"rm_{item.get('id')}" 
                source_url = item.get('url')

                if name and image_url:
                    characters.append({
                        "id": char_id,
                        "name": name,
                        "answers": [name], # الاسم بالإنجليزي فقط بدون ترجمة
                        "image_url": image_url,
                        "source_url": source_url,
                    })
                    
                    if len(characters) >= TARGET_COUNT:
                        break
            page += 1

        except Exception as e:
            print(f"⚠️ حدث خطأ أثناء الجلب: {e}")
            break

    # إنشاء الملف وحفظ البيانات فيه
    OUTPUT_FILE.write_text(
        json.dumps(characters, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    
    print(f"\n✅ تم الانتهاء بنجاح! تم حفظ {len(characters)} شخصية من ريك ومورتي في الملف الجديد.")

if __name__ == "__main__":
    main()