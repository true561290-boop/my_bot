from upstash_redis import Redis

# الاتصال بـ Upstash
redis = Redis.from_env()

def get_balance(user_id: int) -> int:
    bal = redis.get(f"balance:{user_id}")
    return int(bal) if bal is not None else 0

def add_balance(user_id: int, amount: int):
    return redis.incrby(f"balance:{user_id}", amount)

def remove_balance(user_id: int, amount: int):
    return redis.decrby(f"balance:{user_id}", amount)

# ترك هذه الدالة فارغة حتى لا يعطي main.py خطأ إذا كان يستدعيها عند التشغيل
def fetch_latest_balances_from_github():
    pass