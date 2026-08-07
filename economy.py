import os
from upstash_redis import Redis

# جلب المتغيرات البيئية
url = os.getenv("UPSTASH_REDIS_REST_URL")
token = os.getenv("UPSTASH_REDIS_REST_TOKEN")

# التحقق من وجود المتغيرات
if not url or not token:
    print("⚠️ تنبيه: لم يتم العثور على مفاتيح Upstash في Environment Variables!")
    redis = None
else:
    try:
        redis = Redis(url=url, token=token)
        print("✅ تم الاتصال بـ Upstash بنجاح!")
    except Exception as e:
        print(f"❌ خطأ أثناء الاتصال بـ Upstash: {e}")
        redis = None

def get_balance(user_id: int) -> int:
    if not redis:
        print("⚠️ الاتصال بـ Upstash غير متوفر (get_balance)")
        return 0
    try:
        bal = redis.get(f"balance:{user_id}")
        return int(bal) if bal is not None else 0
    except Exception as e:
        print(f"❌ خطأ في جلب الرصيد: {e}")
        return 0

def add_balance(user_id: int, amount: int):
    if not redis:
        print("⚠️ الاتصال بـ Upstash غير متوفر (add_balance)")
        return 0
    try:
        new_bal = redis.incrby(f"balance:{user_id}", int(amount))
        print(f"✅ تم إضافة {amount} للمستخدم {user_id}. الرصيد الجديد: {new_bal}")
        return new_bal
    except Exception as e:
        print(f"❌ خطأ في إضافة الرصيد: {e}")
        return 0

def remove_balance(user_id: int, amount: int):
    if not redis:
        print("⚠️ الاتصال بـ Upstash غير متوفر (remove_balance)")
        return 0
    try:
        new_bal = redis.decrby(f"balance:{user_id}", int(amount))
        print(f"✅ تم خصم {amount} من المستخدم {user_id}. الرصيد الجديد: {new_bal}")
        return new_bal
    except Exception as e:
        print(f"❌ خطأ في خصم الرصيد: {e}")
        return 0

def fetch_latest_balances_from_github():
    pass