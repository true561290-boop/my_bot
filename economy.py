import os
from upstash_redis import Redis

try:
    redis = Redis.from_env()
except Exception as e:
    print(f"Upstash Connection Error: {e}")
    redis = None

def get_balance(user_id: int) -> int:
    if not redis:
        return 0
    try:
        bal = redis.get(f"balance:{user_id}")
        return int(bal) if bal is not None else 0
    except Exception as e:
        print(f"Error getting balance: {e}")
        return 0

def add_balance(user_id: int, amount: int):
    if not redis:
        return 0
    try:
        return redis.incrby(f"balance:{user_id}", int(amount))
    except Exception as e:
        print(f"Error adding balance: {e}")
        return 0

def remove_balance(user_id: int, amount: int):
    if not redis:
        return 0
    try:
        return redis.decrby(f"balance:{user_id}", int(amount))
    except Exception as e:
        print(f"Error removing balance: {e}")
        return 0

def fetch_latest_balances_from_github():
    pass