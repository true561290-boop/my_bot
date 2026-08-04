import base64
import json
import os
import requests

GITHUB_TOKEN = "ghp_2v2m8IXKyh0YQxZRrQnjbl08gmEH5C4E7P3b"
REPO_OWNER = "true561290-boop"
REPO_NAME = "my_bot"
FILE_PATH = "user_balances.json"


def fetch_latest_balances_from_github():
    raw_url = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/main/{FILE_PATH}"
    try:
        response = requests.get(raw_url)
        if response.status_code == 200:
            data = response.json()
            with open(FILE_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            print("✅ تم جلب أحدث نسخة أرصدة من GitHub بنجاح!")
        else:
            print("⚠️ لم يتم العثور على الملف في GitHub أو هو فارغ حالياً.")
    except Exception as e:
        print(f"❌ خطأ أثناء جلب الأرصدة من GitHub: {e}")


def load_balances():
    if os.path.exists(FILE_PATH):
        with open(FILE_PATH, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.DecodeError:
                return {}
    return {}


def save_balances_local_and_cloud(balances):
    with open(FILE_PATH, "w", encoding="utf-8") as f:
        json.dump(balances, f, ensure_ascii=False, indent=4)

    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{FILE_PATH}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }

    get_res = requests.get(url, headers=headers)
    sha = get_res.json().get("sha") if get_res.status_code == 200 else None

    content_str = json.dumps(balances, ensure_ascii=False, indent=4)
    encoded_content = base64.b64encode(content_str.encode("utf-8")).decode(
        "utf-8"
    )

    data = {
        "message": "🔄 تحديث أرصدة الأعضاء تلقائياً",
        "content": encoded_content,
    }
    if sha:
        data["sha"] = sha

    put_res = requests.put(url, headers=headers, json=data)
    if put_res.status_code in [200, 201]:
        print("☁️ تم تحديث الأرصدة سحابياً على GitHub بنجاح!")
    else:
        print(f"❌ فشل تحديث GitHub: {put_res.text}")


# تحميل الأرصدة عند التشغيل
user_balances = load_balances()


def get_balance(user_id):
    return user_balances.get(str(user_id), 0)


def add_balance(user_id, amount):
    uid = str(user_id)
    user_balances[uid] = user_balances.get(uid, 0) + amount
    save_balances_local_and_cloud(user_balances)


def remove_balance(user_id, amount):
    uid = str(user_id)
    current = user_balances.get(uid, 0)
    if current >= amount:
        user_balances[uid] = current - amount
        save_balances_local_and_cloud(user_balances)
        return True
    return False