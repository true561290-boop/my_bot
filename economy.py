import os
from upstash_redis import Redis

url = os.getenv("UPSTASH_REDIS_REST_URL")
token = os.getenv("UPSTASH_REDIS_REST_TOKEN")

if not url or not token:
    print("⚠️ تنبيه: لم يتم العثور على مفاتيح Upstash!")
    redis = None
else:
    try:
        redis = Redis(url=url, token=token)
        print("✅ تم الاتصال بـ Upstash بنجاح!")
    except Exception as e:
        print(f"❌ خطأ أثناء الاتصال بـ Upstash: {e}")
        redis = None

def _extract_id(user_input) -> int:
    """استخراج المعرف الرقمي سواء كان المدخل رقم أو كائن عضو من ديسكورد"""
    if hasattr(user_input, 'id'):
        return user_input.id
    return int(user_input)

def get_balance(user_id) -> int:
    if not redis:
        return 0
    try:
        uid = _extract_id(user_id)
        bal = redis.get(f"balance:{uid}")
        return int(bal) if bal is not None else 0
    except Exception as e:
        print(f"❌ خطأ في get_balance: {e}")
        return 0

def add_balance(user_id, amount: int) -> int:
    if not redis:
        return 0
    try:
        uid = _extract_id(user_id)
        new_bal = redis.incrby(f"balance:{uid}", int(amount))
        print(f"✅ تم إضافة {amount} للمستخدم {uid}. الرصيد الجديد: {new_bal}")
        return int(new_bal)
    except Exception as e:
        print(f"❌ خطأ في add_balance: {e}")
        return 0

def remove_balance(user_id, amount: int) -> int:
    if not redis:
        return 0
    try:
        uid = _extract_id(user_id)
        new_bal = redis.decrby(f"balance:{uid}", int(amount))
        print(f"✅ تم خصم {amount} من المستخدم {uid}. الرصيد الجديد: {new_bal}")
        return int(new_bal)
    except Exception as e:
        print(f"❌ خطأ في remove_balance: {e}")
        return 0

def fetch_latest_balances_from_github():
    pass