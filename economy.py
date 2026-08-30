import os
from upstash_redis import Redis

# جلب المتغيرات وتنظيفها من أي مسافات زائدة
url = (os.getenv("UPSTASH_REDIS_REST_URL") or "").strip()
token = (os.getenv("UPSTASH_REDIS_REST_TOKEN") or "").strip()

# التأكد من وجود رابط صحيح
if url and not url.startswith("http"):
    url = f"https://{url}"

redis = None

if not url or not token:
    print("⚠️ تنبيه: لم يتم العثور على مفاتيح Upstash في Environment Variables!", flush=True)
else:
    try:
        # إنشاء الاتصال واختباره فعلياً
        client = Redis(url=url, token=token)
        client.ping()  # اختبار إرسال واستقبال بيانات من Upstash
        redis = client
        print("✅ تم الاتصال الفعلي بـ Upstash بنجاح وشغال 100%!", flush=True)
    except Exception as e:
        print(f"❌ فشل الاتصال الفعلي بـ Upstash: {e}", flush=True)
        print(f"🔗 الرابط المستعمل: {url}", flush=True)
        redis = None

def _extract_id(user_input) -> int:
    if hasattr(user_input, 'id'):
        return user_input.id
    return int(user_input)

def get_balance(user_id) -> int:
    if not redis:
        print("⚠️ جلب الرصيد فشل: لا يوجد اتصال بـ Upstash", flush=True)
        return 0
    try:
        uid = _extract_id(user_id)
        bal = redis.get(f"bot2_balance:{uid}")
        return int(bal) if bal is not None else 0
    except Exception as e:
        print(f"❌ خطأ في get_bot2_balance: {e}", flush=True)
        return 0

def add_balance(user_id, amount: int) -> int:
    if not redis:
        print("⚠️ إضافة الرصيد فشلت: لا يوجد اتصال بـ Upstash", flush=True)
        return 0
    try:
        uid = _extract_id(user_id)
        new_bal = redis.incrby(f"bot2_balance:{uid}", int(amount))
        print(f"✅ تم إضافة {amount} للمستخدم {uid}. الرصيد الجديد: {new_bal}", flush=True)
        return int(new_bal)
    except Exception as e:
        print(f"❌ خطأ في add_bot2_balance: {e}", flush=True)
        return 0

def remove_balance(user_id, amount: int) -> int:
    if not redis:
        print("⚠️ خصم الرصيد فشل: لا يوجد اتصال بـ Upstash", flush=True)
        return 0
    try:
        uid = _extract_id(user_id)
        new_bal = redis.decrby(f"bot2_balance:{uid}", int(amount))
        print(f"✅ تم خصم {amount} من المستخدم {uid}. الرصيد الجديد: {new_bal}", flush=True)
        return int(new_bal)
    except Exception as e:
        print(f"❌ خطأ في remove_bot2_balance: {e}", flush=True)
        return 0

def fetch_latest_balances_from_github():
    pass