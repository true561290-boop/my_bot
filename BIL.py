import re
import asyncio
import datetime
import io
import os
import json
from dotenv import load_dotenv

load_dotenv()

UPSTASH_REDIS_REST_URL = os.getenv("UPSTASH_REDIS_REST_URL")
UPSTASH_REDIS_REST_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN")

import string
import random
import math
from threading import Thread, Lock
from collections import OrderedDict
from difflib import SequenceMatcher
import typing
import gc
import aiohttp
import discord
from discord.ext import commands
from flask import Flask
from PIL import Image, ImageDraw, ImageFont
import requests

# تشغيل عمليات PIL/الاقتصاد المتزامنة خارج event loop لتجنب تجميد البوت
async def _run_bg(func, *args):
    return await asyncio.to_thread(func, *args)


# ==========================================
# ⚡ كاش سريع مع TTL وحد أقصى للحجم
# ==========================================
class _TTLCache:
    def __init__(self, maxsize=256, ttl=300):
        self.maxsize = maxsize
        self.ttl = ttl
        self._data = OrderedDict()
        self._lock = Lock()

    def get(self, key):
        now = datetime.datetime.now().timestamp()
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            expires_at, value = item
            if expires_at <= now:
                self._data.pop(key, None)
                return None
            self._data.move_to_end(key)
            return value

    def set(self, key, value, ttl=None):
        expires_at = datetime.datetime.now().timestamp() + (self.ttl if ttl is None else ttl)
        with self._lock:
            self._data[key] = (expires_at, value)
            self._data.move_to_end(key)
            while len(self._data) > self.maxsize:
                self._data.popitem(last=False)

    def clear(self):
        with self._lock:
            self._data.clear()

    def cleanup(self):
        now = datetime.datetime.now().timestamp()
        with self._lock:
            expired = [k for k, (expires_at, _) in self._data.items() if expires_at <= now]
            for key in expired:
                self._data.pop(key, None)


# لا نخزن الرصيد نفسه لفترة طويلة حتى لا يظهر للمستخدم رصيد قديم.
# الكاش هنا للصور ونتائج الرسم فقط، مع TTL قصير للنتيجة النهائية.
_SHOP_HOME_CACHE = _TTLCache(maxsize=1, ttl=1800)
_SHOP_CATEGORY_CACHE = _TTLCache(maxsize=64, ttl=300)
_BALANCE_AVATAR_CACHE = _TTLCache(maxsize=512, ttl=300)
_BALANCE_CARD_CACHE = _TTLCache(maxsize=512, ttl=10)
_ROULETTE_LOBBY_CACHE = _TTLCache(maxsize=128, ttl=300)
_ROULETTE_WHEEL_CACHE = _TTLCache(maxsize=256, ttl=300)


async def _cache_cleanup_loop():
    """تنظيف الكاشات المنتهية بشكل دوري بدون إيقاف event loop."""
    while True:
        try:
            await asyncio.sleep(300)  # كل 5 دقائق
            for cache in (
                _SHOP_HOME_CACHE,
                _SHOP_CATEGORY_CACHE,
                _BALANCE_AVATAR_CACHE,
                _BALANCE_CARD_CACHE,
            ):
                cache.cleanup()

            # كاش صور الرتب عبارة عن dict عادي؛ نحذفه فقط إذا تضخم بشكل غير طبيعي.
            visual_cache = globals().get("_SHOP_VISUAL_CACHE")
            if isinstance(visual_cache, dict) and len(visual_cache) > 512:
                # نحتفظ بآخر 512 عنصرًا تقريبًا بدل مسح الكاش كاملًا.
                for key in list(visual_cache)[:-512]:
                    visual_cache.pop(key, None)

            gc.collect()
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"⚠️ خطأ في تنظيف الكاش: {e}")

# استيراد نظام الأرصدة المنفصل
from economy import (
    add_balance,
    fetch_latest_balances_from_github,
    get_balance,
    remove_balance,
)

# --- 1. خادم الويب للحفاظ على استمرار التشغيل 24/7 ---
app = Flask("")


@app.route("/")
def home():
    return "B✰IL Bot is Online!"


def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)


def keep_alive():
    t = Thread(target=run_web)
    t.daemon = True
    t.start()


keep_alive()

# --- 2. إعدادات البوت والبيانات ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True


class BILBot(commands.Bot):
    async def setup_hook(self):
        # BetCog is defined later in this file, but setup_hook runs only after
        # the module has finished loading, so the class is available here.
        await self.add_cog(BetCog(self))
        self._cache_cleanup_task = asyncio.create_task(_cache_cleanup_loop())


bot = BILBot(command_prefix="-", intents=intents, max_messages=None)
bot.remove_command("help")

WELCOME_CHANNEL_ID = 1515396548392128670
LEVEL_50_ROLE_ID = 1515396547473309712
AVATAR_CHANNEL_ID = 1515396548392128671
OWNER_ROLE_ID = 1515396547528102131
GAMES_CHANNEL_ID = 1515416733102379100
THEFT_CHANNEL_ID = 1532648660997771335
SHOPPING_CHANNEL_ID = 1532645480373420142
AMENDMENTS_CHANNEL_ID = 1541143390224130209
TICKET_CHANNEL_ID =1515709356723798177

BACKGROUND_IMAGE_URL = "https://i.ibb.co/6R2N29S/vintage-paper-bg.png"
FONT_PATH = "arabic_font.ttf"


def in_channel(channel_id: int):
    async def predicate(ctx):
        if ctx.channel.id != channel_id:
            try:
                await ctx.message.delete()
            except Exception:
                pass
            await ctx.send(
                f"This only works in this room: <#{channel_id}>",
                delete_after=3,
            )
            return False
        return True

    return commands.check(predicate)


def ensure_arabic_font():
    if not os.path.exists(FONT_PATH):
        font_url = "https://github.com/google/fonts/raw/main/ofl/amiri/Amiri-Bold.ttf"
        try:
            r = requests.get(font_url)
            if r.status_code == 200:
                with open(FONT_PATH, "wb") as f:
                    f.write(r.content)
                print("✅ تم تحميل الخط العربي بنجاح!")
        except Exception as e:
            print(f"❌ فشل تنزيل الخط العربي: {e}")


ensure_arabic_font()
fetch_latest_balances_from_github()

# --- 3. المتجر التفاعلي ورسم الصور ---

SHOP_DATA_FILE = os.path.join(BASE_DIR if "BASE_DIR" in globals() else os.path.dirname(os.path.abspath(__file__)), "shop_data.json")
DEFAULT_COLOR_PRICE = 800
DEFAULT_VIP_PRICE = 1000

# القيم الافتراضية الموجودة في المتجر حالياً. تُحفظ لاحقاً في shop_data.json
_DEFAULT_SHOP_VIP_ROLES = {}
_DEFAULT_SHOP_COLOR_ROLES = {}

# إصدار بيانات المتجر. رفع الإصدار هنا يؤدي إلى تصفير عناصر المتجر القديمة مرة واحدة،
# بدون حذف الرتب نفسها من السيرفر.
SHOP_DATA_VERSION = 2


SHOP_REDIS_KEY = "shop_data"

def _redis_command(command, *args):
    """تنفيذ أمر Upstash REST لحفظ بيانات المتجر بشكل دائم."""
    if not UPSTASH_REDIS_REST_URL or not UPSTASH_REDIS_REST_TOKEN:
        return None
    try:
        url = UPSTASH_REDIS_REST_URL.rstrip("/")
        headers = {"Authorization": f"Bearer {UPSTASH_REDIS_REST_TOKEN}"}
        response = requests.post(
            url,
            headers=headers,
            json=[command, *args],
            timeout=10,
        )
        if response.ok:
            return response.json().get("result")
    except Exception as e:
        print(f"❌ Redis shop command failed: {e}")
    return None


def _load_shop_data():
    # أي بيانات قديمة لا تحمل الإصدار الحالي يتم تجاهلها حتى يبدأ المتجر فارغاً.
    def _normalize(data):
        if not isinstance(data, dict):
            return None
        if data.get("version") != SHOP_DATA_VERSION:
            return None
        vip = data.get("vip", {})
        colors = data.get("colors", {})
        if isinstance(vip, dict) and isinstance(colors, dict):
            return vip, colors
        return None

    # المصدر الدائم أولاً: Upstash Redis.
    try:
        result = _redis_command("GET", SHOP_REDIS_KEY)
        if result:
            loaded = _normalize(json.loads(result))
            if loaded is not None:
                return loaded
    except Exception as e:
        print(f"❌ تعذر تحميل بيانات المتجر من Redis: {e}")

    # توافق مع الملف المحلي القديم، لكن لا نستعيد العناصر القديمة بعد تغيير الإصدار.
    if os.path.exists(SHOP_DATA_FILE):
        try:
            with open(SHOP_DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            loaded = _normalize(data)
            if loaded is not None:
                return loaded
        except Exception as e:
            print(f"❌ تعذر تحميل shop_data.json: {e}")

    # يبدأ المتجر فارغاً، والإضافة تتم فقط من خلال تحكم_متجر.
    vip, colors = {}, {}
    _save_shop_data(vip, colors)
    return vip, colors

def _save_shop_data(vip=None, colors=None):
    vip = SHOP_VIP_ROLES if vip is None else vip
    colors = SHOP_COLOR_ROLES if colors is None else colors
    payload = json.dumps({"version": SHOP_DATA_VERSION, "vip": vip, "colors": colors}, ensure_ascii=False, indent=4)

    # نحفظ في Redis أولاً لأنه التخزين الدائم على الاستضافة.
    redis_saved = _redis_command("SET", SHOP_REDIS_KEY, payload)

    # نحفظ نسخة محلية أيضاً للاستفادة منها في حال تشغيل البوت محلياً.
    try:
        with open(SHOP_DATA_FILE, "w", encoding="utf-8") as f:
            f.write(payload)
        local_saved = True
    except Exception as e:
        print(f"❌ تعذر حفظ بيانات المتجر محلياً: {e}")
        local_saved = False

    return redis_saved == "OK" or local_saved


SHOP_VIP_ROLES, SHOP_COLOR_ROLES = _load_shop_data()


def get_base_bg(width=800, height=450):
    if os.path.exists("bg_paper.png"):
        try:
            return Image.open("bg_paper.png").convert("RGBA").resize((width, height))
        except Exception:
            pass
    return Image.new("RGBA", (width, height), (30, 25, 45, 255))


SHOP_BASE_IMAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mtgr.png")
SHOP_IMAGE_SIZE = (1365, 768)


_SHOP_BACKGROUND_CACHE = None
_SHOP_BACKGROUND_LOCK = Lock()

def _open_shop_background():
    global _SHOP_BACKGROUND_CACHE
    if _SHOP_BACKGROUND_CACHE is not None:
        return _SHOP_BACKGROUND_CACHE.copy()
    with _SHOP_BACKGROUND_LOCK:
        if _SHOP_BACKGROUND_CACHE is None:
            try:
                _SHOP_BACKGROUND_CACHE = (
                    Image.open(SHOP_BASE_IMAGE)
                    .convert("RGBA")
                    .resize(SHOP_IMAGE_SIZE, Image.Resampling.LANCZOS)
                )
            except Exception as e:
                print(f"❌ تعذر فتح صورة المتجر mtgr.png: {e}")
                _SHOP_BACKGROUND_CACHE = Image.new("RGBA", SHOP_IMAGE_SIZE, (38, 31, 24, 255))
        return _SHOP_BACKGROUND_CACHE.copy()


def _shop_text(draw, xy, text, size, fill=(62, 39, 35, 255), max_width=None):
    text = str(text)
    font = _font(size)
    if max_width:
        font = _fit_font(text, max_width, start_size=size, min_size=max(14, size // 2))
    draw.text(xy, text, font=font, fill=fill, anchor="mm", stroke_width=1, stroke_fill=fill)


def _draw_shop_box(draw, box):
    draw.rounded_rectangle(box, radius=25, fill=(225, 190, 119, 245), outline=(71, 43, 27, 255), width=8)
    inner = (box[0] + 10, box[1] + 10, box[2] - 10, box[3] - 10)
    draw.rounded_rectangle(inner, radius=17, outline=(141, 99, 49, 180), width=2)


def draw_shop_home():
    cached = _SHOP_HOME_CACHE.get("home")
    if cached is not None:
        return io.BytesIO(cached)

    base = _open_shop_background()
    draw = ImageDraw.Draw(base)

    # العنوان داخل المربع الأحمر الكبير.
    _shop_text(draw, (683, 112), " Royal Store", 58, fill=(242, 205, 126, 255), max_width=650)

    # أسماء القسمين داخل المربعين الأصليين في التصميم.
    _shop_text(draw, (458, 260), "Ranks", 43, fill=(74, 43, 27, 255), max_width=430)
    _shop_text(draw, (980, 260), "Wavy Colors ", 38, fill=(74, 43, 27, 255), max_width=470)

    out = io.BytesIO()
    base.save(out, format="PNG", optimize=False, compress_level=3)
    out.seek(0)
    data = out.getvalue()
    _SHOP_HOME_CACHE.set("home", data)
    base.close()
    return io.BytesIO(data)


def _draw_wavy_swatch(draw, box, rgb):
    # مستطيل أكبر قليلاً لعرض لون الرتبة بدون الخطوط/التموجات الخارجية.
    draw.rounded_rectangle(
        box,
        radius=12,
        fill=rgb + (255,),
        outline=(63, 42, 28, 255),
        width=4,
    )


def _paste_role_badge(base, badge_bytes, center, size=74):
    if not badge_bytes:
        return
    try:
        badge = Image.open(io.BytesIO(badge_bytes)).convert("RGBA")
        badge.thumbnail((size, size), Image.Resampling.LANCZOS)
        x = center[0] - badge.width // 2
        y = center[1] - badge.height // 2
        base.paste(badge, (x, y), badge)
    except Exception as e:
        print(f"❌ تعذر رسم بادج الرتبة: {e}")


def draw_shop_category(kind, items, page=0, per_page=6):
    base = _open_shop_background()
    draw = ImageDraw.Draw(base)

    title = "Ranks" if kind == "vip" else "Wavy Colors"
    _shop_text(draw, (683, 112), title, 52, fill=(242, 205, 126, 255), max_width=650)

    # طبقة داكنة خفيفة فوق منطقة البطاقات للمحافظة على وضوحها مع الخلفية الأصلية.
    draw.rounded_rectangle((45, 185, 1320, 735), radius=28, fill=(28, 23, 18, 120), outline=(205, 159, 86, 150), width=3)

    start = page * per_page
    visible = items[start:start + per_page]
    card_w, card_h = 585, 145
    positions = []
    for row in range(3):
        for col in range(2):
            x = 70 + col * 615
            y = 205 + row * 170
            positions.append((x, y, x + card_w, y + card_h))

    for (item, visual), box in zip(visible, positions):
        _draw_shop_box(draw, box)
        x1, y1, x2, y2 = box
        center_y = (y1 + y2) // 2

        if kind == "vip":
            # البادج يظهر داخل البطاقة إن كانت الرتبة تملكه.
            _paste_role_badge(base, visual.get("badge"), (x1 + 72, center_y), 82)
            name_x = x1 + 330
        else:
            rgb = visual.get("rgb", (128, 128, 128))
            _draw_wavy_swatch(draw, (x1 + 30, center_y - 38, x1 + 140, center_y + 38), rgb)
            name_x = x1 + 330

        _shop_text(draw, (name_x, center_y - 19), item["name"], 31, fill=(69, 42, 27, 255), max_width=360)
        _shop_text(draw, (name_x, center_y + 34), f"{int(item['price']):,} mora", 25, fill=(100, 60, 31, 255), max_width=330)

    if not visible:
        _shop_text(draw, (683, 450), " There are no items added at the moment", 38, fill=(242, 205, 126, 255))

    out = io.BytesIO()
    base.save(out, format="PNG", optimize=False, compress_level=3)
    out.seek(0)
    base.close()
    return out


# كاش لأيقونات الرتب لتجنب إعادة تحميلها عند التنقل بين صفحات المتجر.
# القيمة: (رابط الأيقونة الحالي، بيانات الصورة أو None)
_SHOP_VISUAL_CACHE = {}


async def _fetch_one_shop_visual(session, guild, item):
    role = guild.get_role(int(item["id"]))
    badge = None
    rgb = (128, 128, 128)

    if not role:
        return {"badge": None, "rgb": rgb}

    try:
        rgb = role.color.to_rgb()
    except Exception:
        pass

    icon = getattr(role, "icon", None)
    icon_url = str(icon.url) if icon else None
    cache_key = role.id

    # إذا كانت الأيقونة موجودة في الكاش ولم تتغير، نستخدمها مباشرة.
    cached = _SHOP_VISUAL_CACHE.get(cache_key)
    if cached is not None and cached[0] == icon_url:
        return {"badge": cached[1], "rgb": rgb}

    if icon_url:
        try:
            # 3 ثوانٍ كافية لطلب صورة صغيرة؛ والأهم ألا ننتظر 8 ثوانٍ لكل رتبة.
            timeout = aiohttp.ClientTimeout(total=3)
            async with session.get(icon_url, timeout=timeout) as resp:
                if resp.status == 200:
                    badge = await resp.read()
        except Exception as e:
            print(f"⚠️ تعذر تحميل بادج الرتبة {role.id}: {e}")

    # نخزن حتى نتيجة عدم وجود الأيقونة، حتى لا نكرر الطلب في كل ضغطة.
    _SHOP_VISUAL_CACHE[cache_key] = (icon_url, badge)
    return {"badge": badge, "rgb": rgb}


async def _fetch_shop_visuals(guild, items):
    # تحميل صور الرتب بالتوازي بدل الانتظار لكل رتبة على حدة.
    async with aiohttp.ClientSession() as session:
        return await asyncio.gather(
            *(_fetch_one_shop_visual(session, guild, item) for item in items)
        )


async def _render_shop_category(guild, kind, page=0):
    data = SHOP_VIP_ROLES if kind == "vip" else SHOP_COLOR_ROLES
    items = list(data.values())
    start = page * 6
    page_items = items[start:start + 6]

    # المفتاح يتغير تلقائياً عند تغيير اسم/سعر/رتبة/لون أحد العناصر.
    signature = tuple(
        (str(item.get("id")), str(item.get("name")), int(item.get("price", 0)))
        for item in page_items
    )
    cache_key = (getattr(guild, "id", 0), kind, page, signature)
    cached = _SHOP_CATEGORY_CACHE.get(cache_key)
    if cached is not None:
        return io.BytesIO(cached)

    visuals = await _fetch_shop_visuals(guild, page_items)
    pairs = list(zip(page_items, visuals))
    img_buf = await _run_bg(draw_shop_category, kind, pairs, page)
    try:
        data_bytes = img_buf.getvalue()
    finally:
        img_buf.close()
    _SHOP_CATEGORY_CACHE.set(cache_key, data_bytes)
    return io.BytesIO(data_bytes)


# ==========================================
# 🎨 أدوات المعالجة والتصميم (PIL Helper Functions) - أمر الرهان المحدث
# ==========================================

# خلفيات نظام الرهان — تُقرأ من نفس مجلد ملف البوت حتى تعمل سواء شغّلته محلياً أو على الاستضافة
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHALLENGE_BASE_IMG = os.path.join(BASE_DIR, "bet_challenge_2.jpg")
RESULT_BASE_IMG = os.path.join(BASE_DIR, "bet_result_2.jpg")

# ملفات لعبة الروليت الروسي
RUSSIAN_ROULETTE_GUN_GIF = os.path.join(BASE_DIR, "gun.gif")
RUSSIAN_ROULETTE_RESULT_GIF = os.path.join(BASE_DIR, "rolet2.gif")
RUSSIAN_ROULETTE_BACKGROUND = os.path.join(BASE_DIR, "roulette_background.jpg")
RUSSIAN_ROULETTE_STEP = 50
RUSSIAN_ROULETTE_CHAMBERS = 6

# خلفية بطاقة أمر طولاري
BALANCE_BASE_IMG = os.path.join(BASE_DIR, "mora-card-Dragon.jpg")

_BALANCE_BACKGROUND_CACHE = None
_BALANCE_BACKGROUND_LOCK = Lock()

def _open_base(path, size):
    global _BALANCE_BACKGROUND_CACHE
    if path == BALANCE_BASE_IMG and _BALANCE_BACKGROUND_CACHE is not None:
        return _BALANCE_BACKGROUND_CACHE.copy()
    try:
        image = Image.open(path).convert("RGBA")
        if path == BALANCE_BASE_IMG:
            with _BALANCE_BACKGROUND_LOCK:
                if _BALANCE_BACKGROUND_CACHE is None:
                    _BALANCE_BACKGROUND_CACHE = image.copy()
        return image
    except Exception as e:
        print(f"[BET] تعذر فتح الخلفية {path}: {e}")
        return Image.new("RGBA", size, (16, 19, 27, 255))

def get_circle_avatar(avatar_bytes, size=(200, 200)):
    avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
    avatar.thumbnail(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    canvas.paste(avatar, ((size[0]-avatar.width)//2, (size[1]-avatar.height)//2), avatar)
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size[0]-1, size[1]-1), fill=255)
    result = Image.new("RGBA", size, (0, 0, 0, 0))
    result.paste(canvas, (0, 0), mask)
    return result

_FONT_CACHE = {}
_FONT_CACHE_LOCK = Lock()

def _font(size):
    cached = _FONT_CACHE.get(size)
    if cached is not None:
        return cached
    for path in (
        os.path.join(BASE_DIR, FONT_PATH),
        FONT_PATH,
        "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "arial.ttf",
    ):
        try:
            font = ImageFont.truetype(path, size)
            with _FONT_CACHE_LOCK:
                _FONT_CACHE[size] = font
            return font
        except Exception:
            pass
    font = ImageFont.load_default()
    with _FONT_CACHE_LOCK:
        _FONT_CACHE[size] = font
    return font

def _fit_font(text, max_width, start_size=28, min_size=14):
    """اختيار أكبر حجم خط يسمح ببقاء النص داخل العرض المحدد."""
    size = start_size
    while size > min_size:
        font = _font(size)
        bbox = font.getbbox(text)
        if (bbox[2] - bbox[0]) <= max_width:
            return font
        size -= 1
    return _font(min_size)


def draw_balance_card(avatar_bytes, member_name, balance):
    """
    يرسم بطاقة طولاري على دقة الخلفية الأصلية 1640x656:
    - الأفاتار متمركز داخل الدائرة السوداء بدون تغطية الإطار الزخرفي.
    - الرصيد متمركز داخل المستطيل الموجود في التصميم.
    - اسم العضو داخل مستطيل الاسم فوق الأفاتار.
    """
    # الخلفية الأصلية 1640x656، لذلك نستخدم إحداثياتها مباشرة
    base = _open_base(BALANCE_BASE_IMG, (1640, 656)).resize(
        (1640, 656), Image.Resampling.LANCZOS
    )
    draw = ImageDraw.Draw(base)

    # =========================
    # الأفاتار — مركز الدائرة الحقيقي في الخلفية
    # =========================
    avatar_size = 296
    avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")

    # قص مربع من منتصف الأفاتار حتى لا يتم تشويه الصورة
    side = min(avatar.width, avatar.height)
    left = (avatar.width - side) // 2
    top = (avatar.height - side) // 2
    avatar = avatar.crop((left, top, left + side, top + side))
    avatar = avatar.resize((avatar_size, avatar_size), Image.Resampling.LANCZOS)

    avatar_mask = Image.new("L", (avatar_size, avatar_size), 0)
    ImageDraw.Draw(avatar_mask).ellipse(
        (0, 0, avatar_size - 1, avatar_size - 1), fill=255
    )

    # مركز الدائرة السوداء في mora-card-Dragon.jpg
    circle_center = (291, 328)
    avatar_x = circle_center[0] - avatar_size // 2
    avatar_y = circle_center[1] - avatar_size // 2
    base.paste(avatar, (avatar_x, avatar_y), avatar_mask)

    # =========================
    # صندوق اسم العضو
    # =========================
    box_outline = (117, 91, 35, 190)
    box_fill = (8, 8, 8, 65)

    name_box = (100, 46, 500, 128)
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rounded_rectangle(
        name_box,
        radius=24,
        fill=box_fill,
        outline=box_outline,
        width=3,
    )
    base = Image.alpha_composite(base, overlay)
    draw = ImageDraw.Draw(base)

    clean_name = str(member_name).strip() or "member"
    name_font = _fit_font(clean_name, 350, start_size=42, min_size=22)
    draw.text(
        ((name_box[0] + name_box[2]) // 2, (name_box[1] + name_box[3]) // 2),
        clean_name,
        fill=(232, 198, 106, 255),
        font=name_font,
        anchor="mm",
    )

    # =========================
    # الرصيد — داخل المستطيل الأصلي
    # =========================
    balance_text = f"{balance:,} mora"
    balance_font = _fit_font(balance_text, 500, start_size=43, min_size=22)

    # مركز المستطيل الموجود في التصميم تقريباً: (968, 274)
    draw.text(
        (968, 274),
        balance_text,
        fill=(232, 198, 106, 255),
        font=balance_font,
        anchor="mm",
    )

    out = io.BytesIO()
    base.save(out, format="PNG")
    out.seek(0)
    base.close()
    return out

def draw_challenge_card(p1_avatar_bytes, p2_avatar_bytes, p1_name, p2_name, amount):
    base = _open_base(CHALLENGE_BASE_IMG, (1024, 463))
    av_size = (198, 198)
    av1 = get_circle_avatar(p1_avatar_bytes, av_size)
    av2 = get_circle_avatar(p2_avatar_bytes, av_size)
    # مراكز الدوائر في bet_challenge_2.jpg
    base.paste(av1, (104, 116), av1)
    base.paste(av2, (719, 116), av2)
    draw = ImageDraw.Draw(base)
    name_font = _font(25)
    amount_font = _font(25)
    draw.text((203, 337), p1_name[:18], fill="white", font=name_font, anchor="mm")
    draw.text((818, 337), p2_name[:18], fill="white", font=name_font, anchor="mm")
    draw.text((512, 345), f"gamboge: {amount:,} mora", fill="#E8C66A", font=amount_font, anchor="mm")
    out = io.BytesIO()
    base.save(out, format="PNG")
    out.seek(0)
    base.close()
    return out

def draw_result_card(winner_avatar_bytes, loser_avatar_bytes, winner_name, loser_name, prize, winner_bal, loser_bal):
    base = _open_base(RESULT_BASE_IMG, (1024, 501))
    loser = get_circle_avatar(loser_avatar_bytes, (165, 165))
    winner = get_circle_avatar(winner_avatar_bytes, (165, 165))
    base.paste(loser, (110, 146), loser)
    base.paste(winner, (719, 146), winner)
    draw = ImageDraw.Draw(base)
    name_font = _font(24)
    info_font = _font(20)
    title_font = _font(27)
    box_font = _font(22)
    draw.text((503, 74), "End of bet ", fill="white", font=box_font, anchor="mm")
    draw.text((801, 118), "winner", fill="#E8C66A", font=box_font, anchor="mm")
    draw.text((193, 337), loser_name[:18], fill="white", font=name_font, anchor="mm")
    draw.text((801, 337), winner_name[:18], fill="#E8C66A", font=name_font, anchor="mm")
    draw.text((512, 262), f"prize: {prize:,} mora", fill="#E8C66A", font=title_font, anchor="mm")
    draw.text((193, 399), f"mora: {loser_bal:,}", fill="#E57373", font=info_font, anchor="mm")
    draw.text((801, 399), f"mora: {winner_bal:,}", fill="#81C784", font=info_font, anchor="mm")
    out = io.BytesIO()
    base.save(out, format="PNG")
    out.seek(0)
    base.close()
    return out

def generate_wheel_gif(p1_name, p2_name, winner_index):
    # عجلة مستقلة بالكامل: نصف أزرق ونصف أحمر، دون الاعتماد على صورة خارجية.
    size = 600
    center = (300, 300)
    radius = 245
    frames = []
    total_frames = 20
    # مؤشر ثابت في الأعلى؛ نحرّك قطاعي العجلة تحته.
    # PIL: 270 درجة = الأعلى. نضع مركز القطاع الفائز تحت المؤشر.
    winner_center = 270 if winner_index == 0 else 90
    start_target = winner_center - 90
    total_angle = 4 * 360 + start_target
    name_font = _font(21)

    for i in range(total_frames):
        t = i / (total_frames - 1)
        eased = 1 - (1 - t) ** 3
        angle = total_angle * eased
        frame = Image.new("RGBA", (size, size), (12, 15, 22, 255))
        d = ImageDraw.Draw(frame)
        a = angle % 360
        box = (center[0]-radius, center[1]-radius, center[0]+radius, center[1]+radius)
        d.pieslice(box, a, a + 180, fill="#1976D2", outline="#E8C66A", width=4)
        d.pieslice(box, a + 180, a + 360, fill="#D32F4F", outline="#E8C66A", width=4)
        # مركز العجلة
        d.ellipse((245,245,355,355), fill="#151922", outline="#E8C66A", width=5)
        d.text(center, "VS", fill="#E8C66A", font=_font(34), anchor="mm")
        # أسماء ثابتة داخل القطاعين، تدور مع العجلة
        for text, mid, fill in ((p1_name[:14], a+90, "white"), (p2_name[:14], a+270, "white")):
            rad = math.radians(mid)
            x = center[0] + 145 * math.cos(rad)
            y = center[1] + 145 * math.sin(rad)
            d.text((x, y), text, fill=fill, font=name_font, anchor="mm")
        # المؤشر العلوي
        d.polygon([(284,18),(316,18),(300,48)], fill="#E8C66A")
        frames.append(frame.convert("P", palette=Image.Palette.ADAPTIVE))

    out = io.BytesIO()
    frames[0].save(out, format="GIF", 
save_all=True, append_images=frames[1:], duration=50, loop=0, disposal=2)
    out.seek(0)
    
    # تفريغ جميع الإطارات من الرام
    for f in frames:
        f.close()
        
    return out

# ==========================================
# 🎮 واجهة أزرار التحدي (Interactive View)
# ==========================================

class ChallengeView(discord.ui.View):
    def __init__(self, challenger, opponent, amount):
        super().__init__(timeout=30)
        self.challenger = challenger
        self.opponent = opponent
        self.amount = amount
        self.accepted = None

    @discord.ui.button(label="Accept Challenge ⚔️", style=discord.ButtonStyle.green)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.opponent.id:
            return await interaction.response.send_message("❌ This challenge is not directed at you.", ephemeral=True)

        self.accepted = True
        # لا نحذف الرسالة هنا؛ أمر الرهان سيحوّل نفس الرسالة إلى العجلة.
        # حذفها من callback كان يجعل msg.edit يفشل بعد قبول التحدي.
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="Rejection ✖️", style=discord.ButtonStyle.red)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.opponent.id:
            return await interaction.response.send_message("❌ This challenge is not directed at you.", ephemeral=True)
        self.accepted = False
        self.stop()
        await interaction.response.send_message(f"❌ Reject {self.opponent.mention} Challenge .")


class TimedSubView(discord.ui.View):
    def __init__(self, timeout=60):
        super().__init__(timeout=timeout)
        self.message = None

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass


class BackToMainButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="return to shop", style=discord.ButtonStyle.secondary, emoji="🔙")

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()

        img_buf = None
        try:
            img_buf = await _run_bg(draw_shop_home)
            file = discord.File(fp=img_buf, filename="shop.png")
            view = MainShopView()
            await interaction.edit_original_response(attachments=[file], view=view)
            view.message = interaction.message
        finally:
            if img_buf is not None:
                img_buf.close()


class ColorSelect(discord.ui.Select):
    def __init__(self, page=0):
        self.page = page
        items = list(SHOP_COLOR_ROLES.items())
        start = page * 25
        page_items = items[start:start + 25]
        options = [
            discord.SelectOption(
                label=str(item["name"])[:100],
                value=key,
                description=f"price: {int(item['price']):,} mora",
            )
            for key, item in page_items
        ]
        if not options:
            options = [discord.SelectOption(label="No colors added", value="none")]
        super().__init__(placeholder="  Choose a color to buy...", min_values=1, max_values=1, options=options, disabled=not page_items)

    async def callback(self, interaction: discord.Interaction):
        selected_key = self.values[0]
        if selected_key == "none":
            return await interaction.response.send_message("ℹ️ There are no colors added at the moment.", ephemeral=True)
        item = SHOP_COLOR_ROLES.get(selected_key)
        if not item:
            return await interaction.response.send_message("❌ هذا اللون لم يعد موجوداً في المتجر.", ephemeral=True)
        user = interaction.user
        guild = interaction.guild
        role = guild.get_role(int(item["id"]))
        if not role:
            return await interaction.response.send_message("❌ الرتبة غير موجودة في السيرفر، يرجى مراجعة الإدارة.", ephemeral=True)
        if role in user.roles:
            return await interaction.response.send_message(f"⚠️ You already have a rank**{role.name}** ", ephemeral=True)
        if get_balance(user.id) < item["price"]:
            return await interaction.response.send_message(f"❌Your balance is insufficient You need to **{item['price']}** mora.", ephemeral=True)

        all_color_ids = [int(c["id"]) for c in SHOP_COLOR_ROLES.values()]
        roles_to_remove = [r for r in user.roles if r.id in all_color_ids and r.id != role.id]
        if roles_to_remove:
            await user.remove_roles(*roles_to_remove)
        remove_balance(user.id, item["price"])
        await user.add_roles(role)

        for child in self.view.children:
            child.disabled = True
        await interaction.message.edit(view=self.view)
        await interaction.response.send_message(
            f"✅ **Purchase Successful،**You have been awarded the rank of **{role.name}** amount **{item['price']}** mora.\n*(Store closed)*",
            ephemeral=True,
        )


class VIPSelect(discord.ui.Select):
    def __init__(self, page=0):
        self.page = page
        items = list(SHOP_VIP_ROLES.items())
        start = page * 25
        page_items = items[start:start + 25]
        options = [
            discord.SelectOption(
                label=str(item["name"])[:100],
                value=key,
                description=f"price: {int(item['price']):,} mora",
            )
            for key, item in page_items
        ]
        if not options:
            options = [discord.SelectOption(label="No Ranks Added", value="none")]
        super().__init__(placeholder="  Select a Rank to Buy...", min_values=1, max_values=1, options=options, disabled=not page_items)

    async def callback(self, interaction: discord.Interaction):
        selected_key = self.values[0]
        if selected_key == "none":
            return await interaction.response.send_message("ℹ️ There are no added ranks at the moment.", ephemeral=True)
        item = SHOP_VIP_ROLES.get(selected_key)
        if not item:
            return await interaction.response.send_message("❌ هذه الرتبة لم تعد موجودة في المتجر.", ephemeral=True)
        user = interaction.user
        guild = interaction.guild
        role = guild.get_role(int(item["id"]))
        if not role:
            return await interaction.response.send_message("❌ الرتبة غير موجودة في السيرفر، يرجى مراجعة الإدارة.", ephemeral=True)
        if role in user.roles:
            return await interaction.response.send_message(f"⚠️ You already have a rank**{role.name}** ", ephemeral=True)
        if get_balance(user.id) < item["price"]:
            return await interaction.response.send_message(f"❌،  Your balance is insufficient You need to **{item['price']}** mora.", ephemeral=True)
        remove_balance(user.id, item["price"])
        await user.add_roles(role)
        for child in self.view.children:
            child.disabled = True
        await interaction.message.edit(view=self.view)
        await interaction.response.send_message(
            f"✅ **Purchase Successful،**You have been awarded the rank of،** تم منحك رتبة **{role.name}** بمبلغ **{item['price']}** طولار.\n*(تم إغلاق المتجر)*",
            ephemeral=True,
        )


class ShopCategoryView(TimedSubView):
    def __init__(self, kind: str, page: int = 0):
        super().__init__(timeout=60)
        self.kind = kind
        self.page = page
        self._build()

    def _build(self):
        self.clear_items()
        if self.kind == "vip":
            self.add_item(VIPSelect(self.page))
        else:
            self.add_item(ColorSelect(self.page))
        self.add_item(BackToMainButton())

        total_pages = max(1, (len(SHOP_VIP_ROLES if self.kind == "vip" else SHOP_COLOR_ROLES) + 5) // 6)
        if total_pages > 1:
            prev = discord.ui.Button(label="السابق", style=discord.ButtonStyle.secondary, emoji="◀️", disabled=self.page <= 0, row=1)
            next_btn = discord.ui.Button(label="التالي", style=discord.ButtonStyle.secondary, emoji="▶️", disabled=self.page >= total_pages - 1, row=1)

            async def prev_callback(interaction: discord.Interaction):
                await interaction.response.defer()

                new_page = max(0, self.page - 1)
                new_view = ShopCategoryView(self.kind, new_page)
                img_buf = None

                try:
                    img_buf = await _render_shop_category(interaction.guild, self.kind, new_page)
                    file = discord.File(fp=img_buf, filename=f"shop_{self.kind}.png")
                    await interaction.edit_original_response(attachments=[file], view=new_view)
                    new_view.message = interaction.message
                finally:
                    if img_buf is not None:
                        img_buf.close()

            async def next_callback(interaction: discord.Interaction):
                await interaction.response.defer()

                total = max(1, (len(SHOP_VIP_ROLES if self.kind == "vip" else SHOP_COLOR_ROLES) + 5) // 6)
                new_page = min(total - 1, self.page + 1)
                new_view = ShopCategoryView(self.kind, new_page)
                img_buf = None

                try:
                    img_buf = await _render_shop_category(interaction.guild, self.kind, new_page)
                    file = discord.File(fp=img_buf, filename=f"shop_{self.kind}.png")
                    await interaction.edit_original_response(attachments=[file], view=new_view)
                    new_view.message = interaction.message
                finally:
                    if img_buf is not None:
                        img_buf.close()

            prev.callback = prev_callback
            next_btn.callback = next_callback
            self.add_item(prev)
            self.add_item(next_btn)


class MainCategorySelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="الرتب", value="cat_vip", description="عرض الرتب المضافة للمتجر"),
            discord.SelectOption(label="الالوان المموجة", value="cat_colors", description="عرض الالوان المموجة المضافة"),
        ]
        super().__init__(placeholder="اختر قسم المتجر...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        # يجب تأكيد الـ Interaction خلال ثوانٍ قليلة.
        # defer() يمنع ظهور "didn't respond in time" أثناء تجهيز صورة المتجر.
        await interaction.response.defer()

        kind = "vip" if self.values[0] == "cat_vip" else "color"
        view = ShopCategoryView(kind, 0)
        img_buf = None

        try:
            img_buf = await _render_shop_category(interaction.guild, kind, 0)
            file = discord.File(fp=img_buf, filename=f"shop_{kind}.png")
            await interaction.edit_original_response(attachments=[file], view=view)
            view.message = interaction.message
        finally:
            if img_buf is not None:
                img_buf.close()


# ==========================================
# 🛠️ التحكم الديناميكي بالمتجر
# ==========================================

def _shop_item_key(role_id: int, kind: str) -> str:
    return f"{kind}_{role_id}"


def _shop_items():
    items = []
    for key, item in SHOP_VIP_ROLES.items():
        items.append(("vip", key, item))
    for key, item in SHOP_COLOR_ROLES.items():
        items.append(("color", key, item))
    return items


def _shop_management_embed(guild):
    embed = discord.Embed(
        title="🛠️ التحكم بالمتجر",
        description="أضف الرتب للمتجر ثم ستظهر تلقائياً داخل بطاقات المتجر مع السعر والبادج/اللون.",
        color=discord.Color.gold(),
    )
    vip_lines = []
    for item in SHOP_VIP_ROLES.values():
        role = guild.get_role(int(item["id"]))
        vip_lines.append(f"{role.mention if role else '❌ رتبة محذوفة'} — **{int(item['price']):,}** طولار")
    color_lines = []
    for item in SHOP_COLOR_ROLES.values():
        role = guild.get_role(int(item["id"]))
        color_lines.append(f"{role.mention if role else '❌ رتبة محذوفة'} — **{int(item['price']):,}** طولار")
    embed.add_field(name=f"👑 الرتب ({len(SHOP_VIP_ROLES)})", value="\n".join(vip_lines)[:1024] or "لا توجد رتب في المتجر.", inline=False)
    embed.add_field(name=f"🎨 الالوان المموجة ({len(SHOP_COLOR_ROLES)})", value="\n".join(color_lines)[:1024] or "لا توجد ألوان في المتجر.", inline=False)
    embed.set_footer(text="زر الإضافة يطلب منشن الرتبة والسعر. لا يتم حذف الرتبة من السيرفر، بل تُحذف من المتجر فقط.")
    return embed


class ShopDeleteSelect(discord.ui.Select):
    def __init__(self, manager_id: int, page: int = 0):
        self.manager_id = manager_id
        self.page = page
        items = _shop_items()
        start = page * 25
        page_items = items[start:start + 25]
        options = []
        for kind, key, item in page_items:
            role_type = "لون" if kind == "color" else "رتبة"
            options.append(discord.SelectOption(label=str(item["name"])[:100], value=f"{kind}|{key}", description=f"{role_type} • {int(item['price']):,} طولار"[:100]))
        if not options:
            options = [discord.SelectOption(label="لا توجد عناصر للحذف", value="none")]
        super().__init__(placeholder="اختر رتبة أو لوناً لحذفه...", min_values=1, max_values=1, options=options, disabled=not page_items)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.manager_id:
            return await interaction.response.send_message("❌ هذه القائمة ليست لك.", ephemeral=True)
        value = self.values[0]
        if value == "none":
            return await interaction.response.send_message("ℹ️ لا توجد عناصر في المتجر لحذفها.", ephemeral=True)
        kind, key = value.split("|", 1)
        data = SHOP_COLOR_ROLES if kind == "color" else SHOP_VIP_ROLES
        item = data.get(key)
        if not item:
            return await interaction.response.send_message("❌ هذا العنصر لم يعد موجوداً في المتجر.", ephemeral=True)
        role = interaction.guild.get_role(int(item["id"]))
        type_name = "اللون" if kind == "color" else "الرتبة"
        role_name = role.mention if role else f"**{item['name']}**"
        view = ShopDeleteConfirmView(self.manager_id, kind, key, role_name, item["name"], type_name, self.page)
        embed = discord.Embed(title="⚠️ تأكيد الحذف", description=f"هل أنت متأكد من حذف {type_name} {role_name} من المتجر؟\n\n**لن يتم حذف الرتبة من السيرفر.**", color=discord.Color.red())
        await interaction.response.edit_message(embed=embed, view=view)


class ShopAddTypeView(discord.ui.View):
    def __init__(self, manager_id: int):
        super().__init__(timeout=60)
        self.manager_id = manager_id
        self.message = None

    async def _start_add(self, interaction: discord.Interaction, kind: str):
        if interaction.user.id != self.manager_id:
            return await interaction.response.send_message("❌ هذا الزر ليس لك.", ephemeral=True)
        type_name = "الرتبة" if kind == "vip" else "اللون المموج"
        await interaction.response.send_message(
            f"📌 **منشن {type_name} واكتب السعر في نفس الرسالة.**\n"
            f"مثال: `@{type_name} 2000`\n"
            f"سيتم حفظها ضمن قسم **{type_name}**. إذا كانت رتبة Discord تحتوي على Badge/Role Icon فسيظهر تلقائياً في بطاقة المتجر.",
            ephemeral=True,
        )

        def check(message):
            if message.author.id != self.manager_id or message.channel.id != interaction.channel.id:
                return False
            if len(message.role_mentions) != 1:
                return False
            parts = message.content.split()
            if len(parts) != 2:
                return False
            return parts[1].replace(",", "").replace("٬", "").strip().isdigit()

        try:
            message = await bot.wait_for("message", timeout=60.0, check=check)
            role = message.role_mentions[0]
            price_text = message.content.split()[1].replace(",", "").replace("٬", "").strip()
            price = int(price_text)
            if price <= 0:
                return await interaction.followup.send("❌ يجب أن يكون السعر أكبر من صفر.", ephemeral=True)
            if role.is_default():
                return await interaction.followup.send("❌ لا يمكن إضافة رتبة @everyone إلى المتجر.", ephemeral=True)
            if role.managed:
                return await interaction.followup.send("❌ لا يمكن إضافة رتبة Managed إلى المتجر.", ephemeral=True)
            for data in (SHOP_VIP_ROLES, SHOP_COLOR_ROLES):
                if any(int(x["id"]) == role.id for x in data.values()):
                    return await interaction.followup.send(f"⚠️ الرتبة {role.mention} موجودة بالفعل في المتجر.", ephemeral=True)

            data = SHOP_COLOR_ROLES if kind == "color" else SHOP_VIP_ROLES
            key = _shop_item_key(role.id, kind)
            data[key] = {"name": role.name, "price": price, "id": role.id}
            if not _save_shop_data():
                data.pop(key, None)
                return await interaction.followup.send("❌ تعذر حفظ بيانات المتجر.", ephemeral=True)
            try:
                await message.delete()
            except Exception:
                pass
            await interaction.followup.send(f"✅ تم حفظ {type_name} {role.mention} في قسم المتجر بسعر **{price:,}** طولار.", ephemeral=True)
            if self.message:
                view = ShopManagementView(self.manager_id)
                await self.message.edit(embed=_shop_management_embed(interaction.guild), view=view)
                view.message = self.message
        except asyncio.TimeoutError:
            await interaction.followup.send("⏰ انتهى الوقت. لم تتم إضافة أي عنصر.", ephemeral=True)
            if self.message:
                view = ShopManagementView(self.manager_id)
                await self.message.edit(embed=_shop_management_embed(interaction.guild), view=view)
                view.message = self.message

    @discord.ui.button(label="رتبة", style=discord.ButtonStyle.primary, emoji="👑")
    async def add_vip(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._start_add(interaction, "vip")

    @discord.ui.button(label="لون مموج", style=discord.ButtonStyle.primary, emoji="🎨")
    async def add_color(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._start_add(interaction, "color")

    @discord.ui.button(label="إلغاء", style=discord.ButtonStyle.secondary, emoji="↩️", row=1)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.manager_id:
            return await interaction.response.send_message("❌ هذا الزر ليس لك.", ephemeral=True)
        view = ShopManagementView(self.manager_id)
        await interaction.response.edit_message(embed=_shop_management_embed(interaction.guild), view=view)
        view.message = interaction.message

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass


class ShopAddButton(discord.ui.Button):
    def __init__(self, manager_id: int):
        self.manager_id = manager_id
        super().__init__(label="إضافة رتبة / لون مموج", style=discord.ButtonStyle.success, emoji="➕")

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.manager_id:
            return await interaction.response.send_message("❌ هذا الزر ليس لك.", ephemeral=True)
        embed = discord.Embed(title="➕ إضافة إلى المتجر", description="اختر القسم الذي تريد إضافة الرتبة إليه.\n\n👑 **رتبة** — تظهر مع اسمها وسعرها والبادج إن وجد.\n🎨 **لون مموج** — يظهر داخل بطاقة خاصة مع مربع اللون المطابق للرتبة.", color=discord.Color.gold())
        embed.set_footer(text="بعد اختيار القسم، منشن الرتبة واكتب السعر في نفس الرسالة.")
        view = ShopAddTypeView(self.manager_id)
        await interaction.response.edit_message(embed=embed, view=view)
        view.message = interaction.message


class ShopDeleteConfirmView(discord.ui.View):
    def __init__(self, manager_id, kind, key, role_name, item_name, type_name, page):
        super().__init__(timeout=60)
        self.manager_id = manager_id
        self.kind = kind
        self.key = key
        self.role_name = role_name
        self.item_name = item_name
        self.type_name = type_name
        self.page = page
        delete_button = discord.ui.Button(label=f"حذف {type_name}", style=discord.ButtonStyle.danger, emoji="🗑️")
        delete_button.callback = self.delete_callback
        self.add_item(delete_button)
        back_button = discord.ui.Button(label="إلغاء", style=discord.ButtonStyle.secondary, emoji="↩️")
        back_button.callback = self.back_callback
        self.add_item(back_button)

    async def delete_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.manager_id:
            return await interaction.response.send_message("❌ هذا الزر ليس لك.", ephemeral=True)
        data = SHOP_COLOR_ROLES if self.kind == "color" else SHOP_VIP_ROLES
        item = data.pop(self.key, None)
        if not item:
            return await interaction.response.send_message("❌ العنصر غير موجود أصلاً في المتجر.", ephemeral=True)
        if not _save_shop_data():
            data[self.key] = item
            return await interaction.response.send_message("❌ تعذر حفظ عملية الحذف.", ephemeral=True)
        view = ShopManagementView(self.manager_id, page=self.page)
        await interaction.response.edit_message(embed=_shop_management_embed(interaction.guild), view=view)
        view.message = interaction.message

    async def back_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.manager_id:
            return await interaction.response.send_message("❌ هذا الزر ليس لك.", ephemeral=True)
        view = ShopManagementView(self.manager_id, page=self.page)
        await interaction.response.edit_message(embed=_shop_management_embed(interaction.guild), view=view)
        view.message = interaction.message


class ShopManagementView(discord.ui.View):
    def __init__(self, manager_id: int, page: int = 0):
        super().__init__(timeout=60)
        self.manager_id = manager_id
        self.page = page
        self.message = None
        self.add_item(ShopAddButton(manager_id))
        self.add_item(ShopDeleteSelect(manager_id, page))
        total_pages = max(1, (len(_shop_items()) + 24) // 25)
        if total_pages > 1:
            prev = discord.ui.Button(label="السابق", style=discord.ButtonStyle.secondary, emoji="◀️", disabled=page <= 0)
            next_btn = discord.ui.Button(label="التالي", style=discord.ButtonStyle.secondary, emoji="▶️", disabled=page >= total_pages - 1)
            async def prev_callback(interaction):
                if interaction.user.id != self.manager_id:
                    return await interaction.response.send_message("❌ هذه القائمة ليست لك.", ephemeral=True)
                new_view = ShopManagementView(self.manager_id, self.page - 1)
                await interaction.response.edit_message(embed=_shop_management_embed(interaction.guild), view=new_view)
                new_view.message = interaction.message
            async def next_callback(interaction):
                if interaction.user.id != self.manager_id:
                    return await interaction.response.send_message("❌ هذه القائمة ليست لك.", ephemeral=True)
                new_view = ShopManagementView(self.manager_id, self.page + 1)
                await interaction.response.edit_message(embed=_shop_management_embed(interaction.guild), view=new_view)
                new_view.message = interaction.message
            prev.callback = prev_callback
            next_btn.callback = next_callback
            self.add_item(prev)
            self.add_item(next_btn)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass


@bot.command(name="تحكم_متجر")
@commands.has_role(OWNER_ROLE_ID)
@in_channel(AMENDMENTS_CHANNEL_ID)
async def shop_management(ctx):
    embed = _shop_management_embed(ctx.guild)
    view = ShopManagementView(ctx.author.id)
    msg = await ctx.send(embed=embed, view=view)
    view.message = msg


@shop_management.error
async def shop_management_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("❌ هذا الأمر مخصص لصاحب رتبة الاونر فقط.", delete_after=3)


class MainShopView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(MainCategorySelect())
        self.message = None

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass


@bot.command(name="متجر", aliases=["اقتصاد"])
@in_channel(SHOPPING_CHANNEL_ID)
async def shop_command(ctx):
    img_buf = await _run_bg(draw_shop_home)
    try:
        file = discord.File(fp=img_buf, filename="shop.png")
        view = MainShopView()
        msg = await ctx.send(file=file, view=view)
        view.message = msg
    finally:
        img_buf.close()


# --- 5. نظام الألعاب والأسئلة ---

QUESTIONS = [
    {"q": "ما هي عاصمة أستراليا؟", "a": ["كانبرا", "كانبيرا"]},
    {"q": "ما هي أصغر دولة في العالم من حيث المساحة؟", "a": ["الفاتيكان"]},
    {"q": "ما هو العنصر الكيميائي الذي رمزه 'Fe'؟", "a": ["الحديد", "حديد"]},
    {"q": "ما هي أكبر صحراء في العالم؟", "a": ["الصحراء الكبرى"]},
    {"q": "في أي عام وقعت معركة حطين؟", "a": ["1187", "١١٨٧", "1187m"]},
    {"q": "ما هو أطول نهر في العالم؟", "a": ["النيل", "نهر النيل"]},
    {"q": "ما هي عاصمة كندا؟", "a": ["أوتاوا", "اوتاوا"]},
    {
        "q": "من هو الملقب بـ 'سيف الله المسلول'؟",
        "a": ["خالد بن الوليد", "خالد ابن الوليد"],
    },
    {
        "q": "ما هو أثقل كوكب في المجموعة الشمسية؟",
        "a": ["المشتري", "كوكب المشتري"],
    },
    {
        "q": "ما هو الغاز الأكثر وجوداً في الغلاف الجوي؟",
        "a": ["النيتروجين", "نيتروجين"],
    },
    {"q": "ما هي الدولة الأكثر سكاناً في العالم؟", "a": ["الهند"]},
    {"q": "ما هي أكبر قارة في العالم من حيث المساحة؟", "a": ["آسيا", "اسيا"]},
    {"q": "ما هو اسم أسرع حيوان بري في العالم؟", "a": ["الفهد", "فهد"]},
    {
        "q": "ما هو أصلح معركة حدثت في التاريخ الإسلامي وكانت فتحاً مبيناً؟",
        "a": ["فتح مكة"],
    },
    {
        "q": "من هو القائد المسلم الذي فتح الأندلس؟",
        "a": ["طارق بن زياد", "طارق ابن زياد"],
    },
    {"q": "ما هي عاصمة اليابان؟", "a": ["طوكيو"]},
    {
        "q": "ما هي الوحدة المستخدمة لقياس الشدة الصوتية؟",
        "a": ["ديسيبل", "الديسيبل"],
    },
    {
        "q": "ما هو الكوكب الملقب بالكوكب الأحمر؟",
        "a": ["المريخ", "كوكب المريخ"],
    },
    {"q": "ما هي عاصمة البرازيل؟", "a": ["برازيليا"]},
    {"q": "كم عدد قلوب الأخطبوط؟", "a": ["3", "ثلاثة", "٣"]},
    {
        "q": "من هو مخترع المصباح الكهربائي؟",
        "a": ["توماس أديسون", "اديسون", "أديسون"],
    },
    {"q": "ما هي أصغر عظمة في جسم الإنسان؟", "a": ["الركاب", "عظمة الركاب"]},
    {"q": "ما هي عاصمة فرنسا؟", "a": ["باريس"]},
    {"q": "في أي قارة تقع مصر؟", "a": ["أفريقيا", "افريقيا"]},
    {
        "q": "ما هو أكبر محيط في العالم؟",
        "a": ["المحيط الهادي", "المحيط الهادئ"],
    },
    {"q": "كم عدد أضلاع المثلث؟", "a": ["3", "ثلاثة", "٣"]},
    {"q": "ما هو المكون الرئيسي للزجاج؟", "a": ["الرمل", "الريمال"]},
    {"q": "ما هي عاصمة ألمانيا؟", "a": ["برلين"]},
    {
        "q": "من هو الشاعر الملقب بـ 'أمير الشعراء'؟",
        "a": ["أحمد شوقي", "احمد شوقي"],
    },
    {"q": "ما هي أكبر عضلة في جسم الإنسان؟", "a": ["عضلة الأرداف", "الأرداف"]},
    {"q": "ما هي عاصمة روسيا؟", "a": ["موسكو"]},
    {"q": "كم عدد العظام في جسم الإنسان البالغ؟", "a": ["206", "٢٠٦"]},
    {
        "q": "ما هو المكون الأساسي للشمس؟",
        "a": ["الهيدروجين", "غاز الهيدروجين"],
    },
    {"q": "ما هي عاصمة إيطاليا؟", "a": ["روما"]},
    {"q": "في أي مدينة توجد منظمة اليونسكو؟", "a": ["باريس"]},
    {"q": "ما هي أكبر بحيرة في العالم؟", "a": ["بحر قزوين"]},
    {
        "q": "من هو عالم الفيزياء صاحب نظريّة النسبية؟",
        "a": ["أينشتاين", "اينشتاين"],
    },
    {"q": "ما هي عاصمة إسبانيا؟", "a": ["مدريد"]},
    {"q": "ما هو الحيوان الذي يُسمى 'سفينة الصحراء'؟", "a": ["الجمل", "جمل"]},
    {
        "q": "ما هي المادة الأكثرصلابة في طبيعة الأرض؟",
        "a": ["الألماس", "الماس"],
    },
    {
        "q": "ما هي الدولة المفترض بها الموطن الأصلي للبيتزا؟",
        "a": ["إيطاليا", "ايطاليا"],
    },
    {"q": "ما هي عاصمة تركيا؟", "a": ["أنقرة", "انقرة"]},
    {"q": "كم عدد الألوان في قوس قزح؟", "a": ["7", "سبعة", "٧"]},
    {"q": "ما هي أطول سلسة جبلية في العالم؟", "a": ["الأنديز", "جبال الأنديز"]},
    {"q": "ما هي عاصمة الأرجنتين؟", "a": ["بوينس آيرس", "بوينس ايرس"]},
    {
        "q": "ما هو الغاز الذي يستعمله النبات في البناء الضوئي؟",
        "a": ["ثاني أكسيد الكربون", "ثاني اكسيد الكربون"],
    },
    {"q": "ما هي عاصمة المغرب؟", "a": ["الرباط"]},
    {"q": "ما هي السورة التي تُسمى 'قلب القرآن'؟", "a": ["يس", "يسن"]},
    {
        "q": "ما هو العلم الذي يهتم بدراسة الأحافير والحيوانات القديمة؟",
        "a": ["الفرع الأحفوري", "الإحاثة", "علم الأحافير"],
    },
    {"q": "ما هي عاصمة السويد؟", "a": ["ستوكهولم"]},
    {"q": "ما هو اسم أعمق نقطة في محيطات الأرض؟", "a": ["خندق ماريانا"]},
    {"q": "ما هي عاصمة مصر؟", "a": ["القاهرة"]},
    {"q": "كم طابق يوجد في برج خليفة تقريباً؟", "a": ["163", "١٦٣"]},
    {
        "q": "ما هو الهرمون المسؤول عن تنظيم مستوى السكر في الدم؟",
        "a": ["الأنسولين", "الانسولين"],
    },
    {"q": "ما هي عاصمة المملكة العربية السعودية؟", "a": ["الرياض"]},
    {"q": "ما هي عاصمة الصين؟", "a": ["بكين"]},
    {
        "q": "ما هو معدن السيولة العالية الفضي السائل في حرارة الغرفة؟",
        "a": ["الزئبق"],
    },
    {"q": "ما هي عاصمة العراق؟", "a": ["بغداد"]},
    {"q": "من هو أول إنسان صعد إلى الفضاء؟", "a": ["يوري جاجارين", "جاجارين"]},
    {"q": "ما هي الدولة التي تمتلك أطول خط ساحلي في العالم؟", "a": ["كندا"]},
    {"q": "ما هي عاصمة الأردن؟", "a": ["عمان", "عمّان"]},
    {"q": "ما هي السورة التي لا تبدأ بالبسملة؟", "a": ["التوبة", "سورة التوبة"]},
    {"q": "ما هو اسم أطول بناء في العالم حالياً؟", "a": ["برج خليفة"]},
    {"q": "ما هي عاصمة اليونان؟", "a": ["أثينا", "اثينا"]},
    {"q": "كم عدد طبقات الغلاف الجوي الرئيسيّة؟", "a": ["5", "خمسة", "٥"]},
    {"q": "ما هو أصل لغة إسبانيا؟", "a": ["اللاتينية"]},
    {"q": "ما هي عاصمة كوريا الجنوبية؟", "a": ["سيول", "سول"]},
    {
        "q": "من هو مكتشف البنسلين؟",
        "a": ["ألكسندر فلمنج", "فلمنج", "الكسندر فلمنج"],
    },
    {"q": "ما هي عاصمة هولندا؟", "a": ["أمستردام", "امستردام"]},
    {"q": "ما هي أكبر جزيرة في العالم؟", "a": ["جرينلاند"]},
    {"q": "ما هي عاصمة الجزائر؟", "a": ["الجزائر"]},
    {"q": "كم عدد صمامات قلب الإنسان؟", "a": ["4", "أربعة", "arba'a", "٤"]},
    {"q": "ما هو أطول نهر في أوروبا؟", "a": ["الفولغا", "نهر الفولغا"]},
    {"q": "ما هي عاصمة الهند؟", "a": ["نيودلهي", "دلهي"]},
    {"q": "من هو مؤسس علم الجبر؟", "a": ["الخوارزمي", "الخوارزمي حاسب"]},
    {"q": "ما هي عاصمة النرويج؟", "a": ["أوسلو", "وسلو"]},
    {"q": "ما هو اسم الكوكب الأقرب إلى الأرض؟", "a": ["الزهرة", "كوكب الزهرة"]},
    {"q": "ما هي عاصمة المكسيك؟", "a": ["مكسيكو سيتي", "مكسيكو"]},
    {
        "q": "ما هي السورة التي ذكرت فيها البسملة مرتين؟",
        "a": ["النمل", "سورة النمل"],
    },
    {"q": "ما هي عاصمة السودان؟", "a": ["الخرطوم"]},
    {"q": "كم عدد أحرف اللغة العربية؟", "a": ["28", "٢٨"]},
    {"q": "ما هو اسم طائر لا يستطيع الطيران ويستمتع بالثلج؟", "a": ["البطريق"]},
    {"q": "ما هي عاصمة الدنمارك؟", "a": ["كوبنهاجن"]},
    {
        "q": "ما هي السلسلة الجبلية الفاصلة بين قارتي آسيا وأوروبا؟",
        "a": ["أورال", "جبال الأورال"],
    },
    {"q": "ما هي عاصمة سوريا؟", "a": ["دمشق"]},
    {"q": "ما هي أسرع سمكة في البحر؟", "a": ["سمكة الشراع", "الشراع"]},
    {"q": "ما هي عاصمة بلجيكا؟", "a": ["بروكسل"]},
    {"q": "ما هي الدولة العربية التي يمر بها خط الاستواء؟", "a": ["الصومال"]},
    {"q": "ما هي عاصمة تونس؟", "a": ["تونس"]},
    {
        "q": "ما هو اسم النهر الوحيد الذي يمر بالعديد من الدول الأوربية؟",
        "a": ["الدانوب", "نهر الدانوب"],
    },
    {"q": "ما هي عاصمة البرتغال؟", "a": ["لشبونة"]},
    {
        "q": "من هو الصحابي الجليل الملقب بـ 'ترجمان القرآن'؟",
        "a": ["عبدالله بن عباس", "عبد الله بن عباس"],
    },
    {"q": "ما هي عاصمة النمسا؟", "a": ["فيينا"]},
    {"q": "ما هو اسم أطول حيوان في العالم؟", "a": ["الزرافة", "زرافة"]},
    {"q": "ما هي عاصمة اليمن؟", "a": ["صنعاء"]},
    {"q": "ما هو أصل لعبة الشطرنج؟", "a": ["الهند"]},
    {"q": "ما هي عاصمة سويسرا؟", "a": ["برن"]},
    {
        "q": "ما هو الغاز الذي ينبعث من أشجار الغابات ليلةً؟",
        "a": ["ثاني أكسيد الكربون"],
    },
    {"q": "ما هي عاصمة قطر؟", "a": ["الدوحة"]},
]

RIDDLES = [
    {"q": "شيء كلما أخذت منه كبر، فما هو؟", "a": ["الحفرة", "حفرة"]},
    {
        "q": "يمشي بلا أرجل ويدخل الأذنين فقط، فما هو؟",
        "a": ["الصوت", "صوت"],
    },
    {"q": "ما هو الشيء الذي يكتب ولا يقرأ؟", "a": ["القلم", "قلم"]},
    {"q": "ما هو البيت الذي لا توجد فيه أبواب ولا نوافذ؟", "a": ["بيت الشعر"]},
    {"q": "ما هو الشيء الذي كلما زاد نقص؟", "a": ["العمر", "عمر"]},
    {
        "q": "ما هو الشيء الذي يمكنك إمساكه بدون لمسه؟",
        "a": ["الأعصاب", "أعصابك"],
    },
    {
        "q": "ما هو القفص الذي لا يحبس فيه طائر أو حيوان؟",
        "a": ["القفص الصدري"],
    },
    {"q": "شيء يحترق لكي يضيء للآخرين؟", "a": ["الشمعة", "شمعة"]},
    {"q": "يمشي ويقف وليس له أرجل؟", "a": ["الظلال", "الظل", "الساعة"]},
    {"q": "ما هو الشيء الذي يبرد بالحرارة؟", "a": ["الفلفل", "البيض"]},
    {
        "q": "أنا ذو ثقوب عديدة ولكني أحتفظ بالماء، فمن أنا؟",
        "a": ["الإسفنج", "اسفنج"],
    },
    {"q": "ما هو الشيء الذي إذا صببت عليه الماء لا يبتل؟", "a": ["الظل", "ظلك"]},
    {
        "q": "ما هو الشارع الذي لم يسير فيه أحد؟",
        "a": ["شارع الرسم", "الشارع على الخريطة", "الخريطة"],
    },
    {
        "q": "ما هو الشيء الذي يقرأ كل الأوراق وبلا عيون؟",
        "a": ["المسح الضوئي", "الضوء"],
    },
    {
        "q": "ما هو الذي يمر عبر الزجاج ولكن لا يكسره؟",
        "a": ["الضوء", "ضوء"],
    },
    {
        "q": "له رأس واحد وله أربعة أرجل ولكن لا يسير؟",
        "a": ["السرير", "سرير"],
    },
    {"q": "شيء يأكل ولا يشبع، وإذا شرب الماء يموت؟", "a": ["النار"]},
    {
        "q": "تراه في الليل ثلاث مرات وفي النهار مرة واحدة، فما هو؟",
        "a": ["حرف اللام"],
    },
    {"q": "ما هو الشيء الذي ينبض بلا قلب؟", "a": ["الساعة", "ساعة"]},
    {"q": "ما هو الباب الذي لا يمكن فتحه؟", "a": ["الباب المفتوح"]},
    {
        "q": "هو ابن أمك وأبيك وليس بأخيك ولا أختك، فمن هو؟",
        "a": ["أنت", "انت"],
    },
    {
        "q": "تكون طويلة في شبابها وقصيرة في كبر سنها، فما هي؟",
        "a": ["الشمعة"],
    },
    {
        "q": "ماهي الأشياء التي تسير بلا قدمين وتصيح بلا فم؟",
        "a": ["الرياح", "رياح"],
    },
    {"q": "له أسنان كثيرة ولكنه لا يعض، فما هو؟", "a": ["المشط", "مشط"]},
    {
        "q": "يحبها الجميع ويعطونها للآخرين ولكن لا أحد يستطيع الاحتفاظ بها؟",
        "a": ["الكلمة", "الوعد"],
    },
    {
        "q": "ما هو الشيء الذي تسمعه ولا تراه، وإذا رأيته لا تسمعه؟",
        "a": ["الطلقة النارية", "الرعد"],
    },
    {"q": "شيء يسير في السماء ويستريح في الأرض؟", "a": ["المطر", "مطر"]},
    {
        "q": "تطير بدون أجنحة وتبكي بدون عيون، فما هي؟",
        "a": ["السحابة", "السحاب"],
    },
    {
        "q": "ما هو الشيء الذي يحتوي على المدن ولكن ليس به بيوت؟",
        "a": ["الخريطة"],
    },
    {"q": "شيء إذا قطعت رأسه طار؟", "a": ["قطار", "القطار"]},
    {"q": "ما هي التي تملك عيوناً ولا ترى؟", "a": ["الإبرة", "إبرة"]},
    {"q": "له أوراق كثيرة ولكنه ليس بشجرة؟", "a": ["الكتاب", "كتاب"]},
    {
        "q": "أسود عندما تشتريه، وأحمر عندما تستخدمه، وأبيض عندما ترميه؟",
        "a": ["الفحم"],
    },
    {
        "q": "ما هو الشيء الذي يجري ولكن لا يستطيع المشي؟",
        "a": ["الماء", "النهر"],
    },
    {
        "q": "يمتلك كل مفاتيح العالم ولكنه لا يستطيع فتح أي باب؟",
        "a": ["البيانو"],
    },
    {"q": "ما هو الشيء الذي ينكسر بمجرد تسميته؟", "a": ["الصمت"]},
    {"q": "يتحدث كل لغات العالم بدون أن يتكلم؟", "a": ["الصدى"]},
    {
        "q": "ما هو الشيء الذي تصنعه ولكن لا تراه؟",
        "a": ["الضوضاء", "الرقام"],
    },
    {"q": "إذا أطعمته ينمو، وإذا سقيته يموت؟", "a": ["النار"]},
    {"q": "يمتلك رقبة ولكن ليس له رأس؟", "a": ["الزجاجة", "قميص"]},
    {
        "q": "ما هو الذي يستطيع الضوء اختراقه والماء المضيء فيه؟",
        "a": ["الزجاج"],
    },
    {"q": "شيء بينك وبين السماء، فما هو؟", "a": ["الكاف", "حرف الكاف"]},
    {
        "q": "ما هو الشارع الذي يمشي فيه الناس بلا أقدام؟",
        "a": ["شارع الخريطة"],
    },
    {
        "q": "ما هو العضو الوحيد الذي لا يصله الدم؟",
        "a": ["قرنية العين", "القرنية"],
    },
    {"q": "ما هي الشيء الذي يولد كبيراً ويموت صغيراً؟", "a": ["الشمعة"]},
    {"q": "يوجد في منتصف باريس فما هو؟", "a": ["حرف الراء"]},
    {
        "q": "ما هو الشيء الذي إذا أكلته كله استفدت منه، وإذا أكلت نصفه مِت؟",
        "a": ["سمسم"],
    },
    {"q": "ما هو الذي يملك عين واحدة ولكنه لا يرى بها؟", "a": ["الإبرة"]},
    {"q": "ما هو الشيء الذي إذا نام لا يستيقظ؟", "a": ["الرماد"]},
    {"q": "له يد ولكن لا يستطيع التصفيق؟", "a": ["الساعة"]},
    {"q": "ما هو الشيء الذي يصعد ولا ينزل أبداً؟", "a": ["العمر"]},
    {"q": "أخت خالتك وليست خالتك فمن تكون؟", "a": ["أمك", "امي"]},
    {"q": "يمشي بدون قدمين ولا يدخل إلا بالأذنين؟", "a": ["الصوت"]},
    {"q": "تأكل منه ولكن لا يمكنك أن تأكله؟", "a": ["الصحن", "الطبق"]},
    {
        "q": "يحتاج دائماً إلى إجابة ولكنه لا يطرح أي سؤال؟",
        "a": ["الهاتف", "الجرس"],
    },
    {
        "q": "ما هو الشيء الذي يسير أمامك ولا تستطيع الوصول إليه؟",
        "a": ["المستقبل"],
    },
    {
        "q": "ما هو الشيء الذي يملك أقداماً ثلاث ولا يمشي؟",
        "a": ["المنصة", "الطاولة"],
    },
    {"q": "إذا أردت أن تستخدمه يجب عليك رميه أولاً؟", "a": ["شبكة الصيد"]},
    {"q": "ما هو الشيء الذي لا يتكلم وإذا جاع كذب؟", "a": ["الساعة"]},
    {"q": "أين يقع البحر الذي ليس به ماء؟", "a": ["على الخريطة"]},
    {
        "q": "يمتلك كل العيون ولكنه لا يرى شيئاً؟",
        "a": ["شاطئ البطاطس", "البطاطس"],
    },
    {"q": "ما هو الشهر الذي فيه 28 يوماً؟", "a": ["كل الشهور", "جميع الشهور"]},
    {"q": "ما هو أصلح شيء للرؤية في الظلام التام؟", "a": ["لا شيء"]},
    {
        "q": "ما هو الشيء الذي يملك ذراعين وليس لديه أصابع؟",
        "a": ["الكرسي"],
    },
    {
        "q": "أين يمكنك إيجاد الجمعة قبل الخميس؟",
        "a": ["في المعجم", "القاموس"],
    },
    {
        "q": "إذا كان هناك 3 تفاحات وأخذت 2، فكم تفاحة لديك؟",
        "a": ["2", "تفاحتان"],
    },
    {"q": "ما هو القادم الذي لا يصل أبداً؟", "a": ["غداً", "الغد"]},
    {
        "q": "أنا بداية النهاية ونهاية الزمان والمكان فمن أنا؟",
        "a": ["حرف النون"],
    },
    {"q": "ما هو الشيء الذي إذا غسلت به يظل متسخاً؟", "a": ["الماء"]},
    {
        "q": "ما هو الشيء الذي يطير بدون أجنحة ويدخل العيون بدون استئذان؟",
        "a": ["الغبار"],
    },
    {"q": "يتحرك باستمرار وبلا توقف ولكن لا يتعب؟", "a": ["القلب"]},
    {
        "q": "ما هي المادة التي يفرزها الجسم وتصلح لبناء العظام؟",
        "a": ["الكالسيوم"],
    },
    {"q": "ما هو الشيء الذي ينقص كلما أخذت منه أكثر؟", "a": ["الحفرة"]},
    {
        "q": "ما هي الشجرة التي ليس لها ظل وليس لها أوراق؟",
        "a": ["شجرة العائلة"],
    },
    {
        "q": "ما هو أصلح مكان لبناء بيت بدون جدران؟",
        "a": ["الإنترنت", "العقل"],
    },
    {
        "q": "ما هي الكلمة التي تُنطق دائماً بشكل غير صحيح؟",
        "a": ["غير صحيح"],
    },
    {
        "q": "يمتلك ريشاً ولكنه لا يطير ولديه أرقام فقط؟",
        "a": ["سهم الدرجات", "القلم"],
    },
    {"q": "ما هي العروس التي لا تبكي عند زفافها؟", "a": ["عروس البحر"]},
    {"q": "ما هو القماش الذي لا يمكنك ارتداؤه؟", "a": ["قماش العنكبوت"]},
    {"q": "شيء إذا لمسته صرخ؟", "a": ["جرس الباب", "الجرس"]},
    {"q": "ما هو العقرب الذي لا يلذغ؟", "a": ["عقرب الساعة"]},
    {
        "q": "ما هو العضو الذي يستمر في النمو طوال حياة الإنسان؟",
        "a": ["الأنف والأذن", "الأنف"],
    },
    {
        "q": "ما هو السؤال الذي لا يمكنك الإجابة عليه بنعم أبداً؟",
        "a": ["هل أنت نائم؟"],
    },
    {"q": "ما هي الكلمة الوحيدة في القاموس التي كُتبت خطأ؟", "a": ["خطأ"]},
    {"q": "من هو الشخص الذي يرى عدوه وصديقه بعين واحدة؟", "a": ["الأعور"]},
    {
        "q": "ما هو الشيء الذي لا يبتل حتى لو نزل في أغزر مياه؟",
        "a": ["الظل"],
    },
    {"q": "له أسنان عديدة لكنه لا يستطيع العض بها؟", "a": ["المشط"]},
    {
        "q": "يمتلك زجاجاً ولكنه ليس بنوافذ، ويتصل بالشبكة؟",
        "a": ["الهاتف الذكي"],
    },
    {
        "q": "ما هو الماء الذي لا يخرج من الأرض ولا ينزل من السماء؟",
        "a": ["العرق", "دموع العين"],
    },
    {
        "q": "من هو الشخص الذي يقتل مئات الأشخاص يومياً بدون أن يعاقبه أحد؟",
        "a": ["الحلاق"],
    },
    {
        "q": "ما هي العروس التي لا يراها أحد إلا زوجها؟",
        "a": ["عروسة اللعبة"],
    },
    {
        "q": "يمتلك شوكة واحدة وأحياناً أربعة ولا يأكل أبداً؟",
        "a": ["شوكة الطعام"],
    },
    {"q": "ما هو السلم الذي لا يصعد عليه أحد؟", "a": ["سلم الرواتب"]},
    {"q": "تسير في كل أرجاء الغرفة لكنها لا تتحرك أبداً؟", "a": ["الجدران"]},
    {"q": "تلبس الثوب بالكامل لكنها تظل عارية؟", "a": ["إبرة الخياطة"]},
    {
        "q": "ما هو الشيء الذي يسير بلا أقدام ولا يرجع للخلف أبداً؟",
        "a": ["الوقت", "العمر"],
    },
    {"q": "إذاوضعتني في ماء حار أصبح صلباً؟", "a": ["البيض", "بيضة"]},
    {"q": "ما هو الشيء الذي يحك أذنه بأنفه؟", "a": ["الفيل"]},
    {"q": "ما هو الشيء الذي تحمله ويحملك في نفس الوقت؟", "a": ["الحذاء"]},
]


@bot.command(name="سؤال", aliases=["quiz", "اسئلة"])
@in_channel(GAMES_CHANNEL_ID)
async def quiz_game(ctx, rounds: int = 1):
    if rounds < 1 or rounds > 10:
        await ctx.send(
            "❌ يرجى تحديد عدد جولات بين **1** و **10** فقط", delete_after=3
        )
        return

    for round_num in range(1, rounds + 1):
        q_data = random.choice(QUESTIONS)

        embed = discord.Embed(
            title=f"❓ الجولة {round_num}",
            description=(
                f"يا {ctx.author.mention}، أجب عن السؤال التالي كسباً لـ **40**"
                f" طولار:\n\n❓ **{q_data['q']}**"
            ),
            color=discord.Color.blue(),
        )
        embed.set_footer(text="⏱️ لديك 10 ثوانٍ للإجابة على هذا السؤال")

        await ctx.send(
            embed=embed, allowed_mentions=discord.AllowedMentions(users=False)
        )

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            msg = await bot.wait_for("message", timeout=10.0, check=check)
            if msg.content.strip().lower() in [ans.lower() for ans in q_data["a"]]:
                add_balance(ctx.author.id, 40)
                await ctx.send(
                    f"🎉 **إجابة صحيحة،** تم إضافة 40 طولار إلى حسابك يا"
                    f" {ctx.author.mention}",
                    allowed_mentions=discord.AllowedMentions(users=False),
                )
            else:
                await ctx.send(
                    f"❌ **إجابة خاطئة،** الإجابة الصحيحة هي: **{q_data['a'][0]}**"
                )
        except asyncio.TimeoutError:
            await ctx.send(
                f"⏰ **انتهى الوقت** الإجابة الصحيحة كانت: **{q_data['a'][0]}**"
            )

        if round_num < rounds:
            await asyncio.sleep(1)


@bot.command(name="لغز", aliases=["الغاز", "riddle"])
@in_channel(GAMES_CHANNEL_ID)
async def riddle_game(ctx, rounds: int = 1):
    if rounds < 1 or rounds > 10:
        await ctx.send(
            "❌ يرجى تحديد عدد جولات بين **1** و **10** فقط", delete_after=3
        )
        return

    for round_num in range(1, rounds + 1):
        riddle = random.choice(RIDDLES)

        embed = discord.Embed(
            title=f"🧩 الجولة {round_num}",
            description=(
                f"يا {ctx.author.mention}، حل اللغز التالي كسباً لـ **40**"
                f" طولار:\n\n🧩 **{riddle['q']}**"
            ),
            color=discord.Color.gold(),
        )
        embed.set_footer(text="⏱️ لديك 15 ثانية للإجابة على هذا اللغز")

        await ctx.send(
            embed=embed, allowed_mentions=discord.AllowedMentions(users=False)
        )

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            msg = await bot.wait_for("message", timeout=15.0, check=check)
            if msg.content.strip().lower() in [ans.lower() for ans in riddle["a"]]:
                add_balance(ctx.author.id, 40)
                await ctx.send(
                    f"🎉 **إجابة صحيحة،** تم إضافة 40 طولار إلى حسابك يا"
                    f" {ctx.author.mention}",
                    allowed_mentions=discord.AllowedMentions(users=False),
                )
            else:
                await ctx.send(
                    f"❌ **إجابة خاطئة** الإجابة الصحيحة كانت:"
                    f" **{riddle['a'][0]}**.",
                    allowed_mentions=discord.AllowedMentions(users=False),
                )
        except asyncio.TimeoutError:
            await ctx.send(
                f"⏰ **انتهى الوقت** الإجابة الصحيحة كانت: **{riddle['a'][0]}**",
                allowed_mentions=discord.AllowedMentions(users=False),
            )

        if round_num < rounds:
            await asyncio.sleep(1)


class RPSView(discord.ui.View):

    def __init__(self, player1: discord.Member, player2: discord.Member = None):
        super().__init__(timeout=10)  # ⏱️ 1. تغيير الوقت إلى 10 ثوانٍ
        self.player1 = player1
        self.player2 = player2
        self.p1_choice = None
        self.p2_choice = None
        self.is_vs_bot = player2 is None
        self.message = None  # 📌 حفظ الرسالة لتحديثها عند التايم أوت

    async def on_timeout(self):
        # ⏱️ 2. ماذا يحدث عند انتهاء الـ 10 ثوانٍ دون اختيار؟
        for item in self.children:
            item.disabled = True

        if self.message:
            embed = discord.Embed(
                title="⏰ انتهى الوقت",
                description="انتهت اللعبة لعدم إدخال الاختيار خلال 10 ثوانٍ.",
                color=discord.Color.red(),
            )
            await self.message.edit(content=None, embed=embed, view=self)

    async def check_choices(self, interaction: discord.Interaction):
        if self.is_vs_bot:
            self.p2_choice = random.choice(["حجرة", "ورقة", "مقص"])
            await self.end_game(interaction)
            return

        if self.p1_choice and self.p2_choice:
            await self.end_game(interaction)
        else:
            who_chose = (
                self.player1.mention if self.p1_choice else self.player2.mention
            )
            who_waiting = (
                self.player2.mention if self.p1_choice else self.player1.mention
            )
            await interaction.message.edit(
                content=(
                    f"🎮 **لعبة حجرة ورقة مقص**\n"
                    f"✅ اختار {who_chose} حركته بنجاح، وفي انتظار اختيار {who_waiting}..."
                )
            )

    async def end_game(self, interaction: discord.Interaction):
        c1, c2 = self.p1_choice, self.p2_choice

        if c1 == c2:
            result = "🤝 **تعادل** لم يفز أحد."
            color = discord.Color.gold()
        elif (
            (c1 == "حجرة" and c2 == "مقص")
            or (c1 == "ورقة" and c2 == "حجرة")
            or (c1 == "مقص" and c2 == "ورقة")
        ):
            add_balance(self.player1.id, 40)
            p2_name = "البوت" if self.is_vs_bot else self.player2.mention
            result = f"🎉 **فاز {self.player1.mention} على {p2_name} وحصل على 40 طولار**"
            color = discord.Color.green()
        else:
            if not self.is_vs_bot:
                add_balance(self.player2.id, 40)
                result = f"🎉 **فاز {self.player2.mention} على {self.player1.mention} وحصل على 40 طولار**"
                color = discord.Color.green()
            else:
                result = "❌ **خسرت، فاز البوت عليك**"
                color = discord.Color.red()

        embed = discord.Embed(title="🎮 نتيجة لعبة حجرة ورقة مقص", color=color)
        embed.add_field(
            name=f"اختيار {self.player1.display_name}", value=c1, inline=True
        )
        embed.add_field(
            name=f"اختيار {'البوت' if self.is_vs_bot else self.player2.display_name}",
            value=c2,
            inline=True,
        )
        embed.add_field(name="النتيجة", value=result, inline=False)

        for item in self.children:
            item.disabled = True

        await interaction.message.edit(content=None, embed=embed, view=self)
        self.stop()  # لإيقاف الـ timeout بعد انتهاء اللعبة طبيعياً

    async def process_player_choice(
        self, interaction: discord.Interaction, choice: str
    ):
        if interaction.user != self.player1 and (
            self.is_vs_bot or interaction.user != self.player2
        ):
            return await interaction.response.send_message(
                "❌ هذه اللعبة ليست لك", ephemeral=True
            )

        if interaction.user == self.player1:
            if self.p1_choice:
                return await interaction.response.send_message(
                    "⚠️ لقد اخترت بالفعل", ephemeral=True
                )
            self.p1_choice = choice
            await interaction.response.send_message(
                f"✅ تم تسجيل اختيارك: **{choice}**", ephemeral=True
            )

        elif interaction.user == self.player2:
            if self.p2_choice:
                return await interaction.response.send_message(
                    "⚠️ لقد اخترت بالفعل", ephemeral=True
                )
            self.p2_choice = choice
            await interaction.response.send_message(
                f"✅ تم تسجيل اختيارك : **{choice}**", ephemeral=True
            )

        await self.check_choices(interaction)

    @discord.ui.button(label="حجرة 🪨", style=discord.ButtonStyle.primary)
    async def rock_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self.process_player_choice(interaction, "حجرة")

    @discord.ui.button(label="ورقة 📄", style=discord.ButtonStyle.primary)
    async def paper_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self.process_player_choice(interaction, "ورقة")

    @discord.ui.button(label="مقص ✂️", style=discord.ButtonStyle.primary)
    async def scissors_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self.process_player_choice(interaction, "مقص")


@bot.command(name="حجر", aliases=["حجرة", "rps"])
@in_channel(GAMES_CHANNEL_ID)
async def rps_game(ctx, opponent: discord.Member = None):
    if opponent and opponent.bot:
        return await ctx.send(
            "❌ لا يمكنك تحدي البوتات بهذه الطريقة، استخدم `.حجر` بدون منشن للعب ضد البوت."
        )

    if opponent and opponent == ctx.author:
        return await ctx.send("❌ لا يمكنك تحدي نفسك")

    if opponent:
        embed = discord.Embed(
            title="🎮 لعبة حجرة ورقة مقص (تحدي)",
            description=(
                f"المواجهة بين {ctx.author.mention} و {opponent.mention}!\n\n"
                "⏱️ **معكما 10 ثوانٍ للاختيار!**\n"
                "اضغطوا على الأزرار بالأسفل لاختيار الحركة."
            ),
            color=discord.Color.blue(),
        )
    else:
        embed = discord.Embed(
            title="🎮 لعبة حجرة ورقة مقص (ضد البوت)",
            description=(
                f"يا {ctx.author.mention}، اختر أحد الأزرار خلال 10 ثوانٍ\n"
                "إذا فزت ستكسب **40 طولار** 💵"
            ),
            color=discord.Color.blue(),
        )

    view = RPSView(player1=ctx.author, player2=opponent)
    # 📌 3. ربط الرسالة المرسلة بالـ view
    msg = await ctx.send(
        embed=embed,
        view=view,
        allowed_mentions=discord.AllowedMentions(users=False),
    )
    view.message = msg


# --- 6. لعبة إكس أو التفاعلية ---
class XOButton(discord.ui.Button):
    def __init__(self, x: int, y: int):
        super().__init__(
            style=discord.ButtonStyle.secondary, label="‎", row=y
        )
        self.x = x
        self.y = y

    async def callback(self, interaction: discord.Interaction):
        view: XOView = self.view
        if interaction.user != view.current_player:
            await interaction.response.send_message(
                "❌ ليس دورك الآن", ephemeral=True
            )
            return

        idx = self.y * 3 + self.x
        if view.board[idx] != " ":
            await interaction.response.send_message(
                "❌ هذا المربع مشغول بالفعل", ephemeral=True
            )
            return

        view.board[idx] = view.current_mark
        self.label = view.current_mark
        self.style = (
            discord.ButtonStyle.danger
            if view.current_mark == "❌"
            else discord.ButtonStyle.success
        )
        self.disabled = True

        winner = view.check_winner()
        if winner:
            for child in view.children:
                child.disabled = True
            add_balance(view.current_player.id, 50)
            await interaction.response.edit_message(
                content=(
                    f"**فاز {view.current_player.mention} ({view.current_mark}) في لعبة إكس أو**\n"
                    f"💵 تم إضافة **50 طولار** لرصيده"
                ),
                view=view,
            )
            view.stop()
            return

        if " " not in view.board:
            for child in view.children:
                child.disabled = True
            await interaction.response.edit_message(
                content=" **تعادل، انتهت اللعبة بدون فائز.**", view=view
            )
            view.stop()
            return

        if not view.is_vs_bot:
            view.current_player = (
                view.player2
                if view.current_player == view.player1
                else view.player1
            )
            view.current_mark = "⭕" if view.current_mark == "❌" else "❌"
            await interaction.response.edit_message(
                content=(
                    f"❌⭕ **لعبة إكس أو (XO)**\n"
                    f"الدور الحالى: {view.current_player.mention} ({view.current_mark})\n"
                    f"الجائزة: **50 طولار** للفائز"
                ),
                view=view,
            )
        else:
            bot_idx = view.bot_move()
            if bot_idx != -1:
                view.board[bot_idx] = "⭕"
                btn = view.children[bot_idx]
                btn.label = "⭕"
                btn.style = discord.ButtonStyle.success
                btn.disabled = True

                bot_winner = view.check_winner()
                if bot_winner:
                    for child in view.children:
                        child.disabled = True
                    await interaction.response.edit_message(
                        content="🤖 **فاز البوت عليك في لعبة إكس أو.**",
                        view=view,
                    )
                    view.stop()
                    return

                if " " not in view.board:
                    for child in view.children:
                        child.disabled = True
                    await interaction.response.edit_message(
                        content=" **تعادل، انتهت اللعبة بدون فائز.**", view=view
                    )
                    view.stop()
                    return

            await interaction.response.edit_message(
                content=(
                    f"❌⭕ **لعبة إكس أو (XO)**\n"
                    f"لعب البوت دوره، حان دورك يا {view.player1.mention} (❌)\n"
                    f"الجائزة: **50 طولار** عند الفوز"
                ),
                view=view,
            )


class XOView(discord.ui.View):
    def __init__(self, player1: discord.User, player2: discord.User = None):
        super().__init__(timeout=60)
        self.player1 = player1
        self.player2 = player2
        self.is_vs_bot = player2 is None
        self.current_player = player1
        self.current_mark = "❌"
        self.board = [" "] * 9
        self.message = None

        for y in range(3):
            for x in range(3):
                self.add_item(XOButton(x, y))

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(
                    content="⏰ **انتهت اللعبة لعدم التفاعل.**", view=self
                )
            except Exception:
                pass

    def check_winner(self):
        lines = [
            [0, 1, 2],
            [3, 4, 5],
            [6, 7, 8],
            [0, 3, 6],
            [1, 4, 7],
            [2, 5, 8],
            [0, 4, 8],
            [2, 4, 6],
        ]
        for line in lines:
            if (
                self.board[line[0]]
                == self.board[line[1]]
                == self.board[line[2]]
                != " "
            ):
                return self.board[line[0]]
        return None

    def bot_move(self):
        empty_indices = [i for i, val in enumerate(self.board) if val == " "]
        if not empty_indices:
            return -1

        for i in empty_indices:
            self.board[i] = "⭕"
            if self.check_winner() == "⭕":
                return i
            self.board[i] = " "

        for i in empty_indices:
            self.board[i] = "❌"
            if self.check_winner() == "❌":
                self.board[i] = " "
                return i
            self.board[i] = " "

        if 4 in empty_indices:
            return 4

        return random.choice(empty_indices)


@bot.command(name="اكس", aliases=["اكس_او", "xo", "tictactoe"])
@in_channel(GAMES_CHANNEL_ID)
async def xo_game(ctx, opponent: discord.Member = None):
    if opponent and opponent.bot:
        await ctx.send(
            "❌ لا يمكنك تحدي بوت آخر، استخدم الأمر بدون منشن للعب ضد البوت الحالي."
        )
        return

    if opponent and opponent == ctx.author:
        await ctx.send("❌ لا يمكنك تحدي نفسك")
        return

    if opponent:
        view = XOView(player1=ctx.author, player2=opponent)
        msg = await ctx.send(
            f"❌⭕ **بدأت لعبة إكس أو (XO)**\n"
            f"المنافسة بين {ctx.author.mention} (❌) و {opponent.mention} (⭕)\n"
            f"الدور الحالى: {ctx.author.mention}\n"
            f"الجائزة: **50 طولار** للفائز",
            view=view,
            allowed_mentions=discord.AllowedMentions(users=False),
        )
        view.message = msg
    else:
        view = XOView(player1=ctx.author)
        msg = await ctx.send(
            f"❌⭕ **بدأت لعبة إكس أو (XO) ضد البوت**\n"
            f"أنت تلعب بـ (❌) والبوت يلعب بـ (⭕)\n"
            f"الدور الحالى: {ctx.author.mention}\n"
            f"الجائزة: **50 طولار** عند الفوز",
            view=view,
            allowed_mentions=discord.AllowedMentions(users=False),
        )
        view.message = msg


# --- 7. لعبة توصيل الكرات 4 التفاعلية ---
class Connect4Button(discord.ui.Button):
    def __init__(self, col: int, row_idx: int):
        super().__init__(
            style=discord.ButtonStyle.primary,
            label=str(col + 1),
            custom_id=f"c4_col_{col}",
            row=row_idx,
        )
        self.col = col

    async def callback(self, interaction: discord.Interaction):
        view: Connect4View = self.view

        if interaction.user != view.current_player:
            await interaction.response.send_message("❌ ليس دورك الآن", ephemeral=True)
            return

        placed_row = view.drop_piece(self.col, view.current_emoji)
        if placed_row == -1:
            await interaction.response.send_message(
                " هذا العامود ممتلئ، اختر عاموداً آخر.", ephemeral=True
            )
            return

        if view.check_winner(placed_row, self.col, view.current_emoji):
            winner = view.current_player
            add_balance(winner.id, 60)
            for child in view.children:
                child.disabled = True
            await interaction.response.edit_message(
                content=(
                    f"🎉 ** {winner.mention}** لقد فزت في لعبة **توصيل الكرات"
                    " 4** وحصلت على **60 طولار**💵\n\n"
                    + view.get_board_string()
                ),
                view=view,
            )
            view.stop()
            return

        if view.is_board_full():
            for child in view.children:
                child.disabled = True
            await interaction.response.edit_message(
                content=(
                    "🤝 **تعادل** امتلأت اللوحة دون فائز.\n\n"
                    + view.get_board_string()
                ),
                view=view,
            )
            view.stop()
            return

        if not view.is_vs_bot:
            view.current_player = (
                view.player2
                if view.current_player == view.player1
                else view.player1
            )
            view.current_emoji = "🟡" if view.current_emoji == "🔴" else "🔴"
            await interaction.response.edit_message(
                content=(
                    f" **لعبة توصيل الكرات 4**\nدور: {view.current_player.mention}"
                    f" ({view.current_emoji})\nالجائزة: **60 طولار** للفائز\n\n"
                    + view.get_board_string()
                ),
                view=view,
            )
        else:
            bot_col, bot_row = view.bot_move()
            if bot_row != -1 and view.check_winner(bot_row, bot_col, "🟡"):
                for child in view.children:
                    child.disabled = True
                await interaction.response.edit_message(
                    content=(
                        f"🤖 ** لعب البوت رقم {bot_col + 1} وفاز في توصيل الكرات"
                        " 4**\n\n"
                        + view.get_board_string()
                    ),
                    view=view,
                )
                view.stop()
                return

            if view.is_board_full():
                for child in view.children:
                    child.disabled = True
                await interaction.response.edit_message(
                    content=(
                        " **تعادل** امتلأت اللوحة دون فائز.\n\n"
                        + view.get_board_string()
                    ),
                    view=view,
                )
                view.stop()
                return

            await interaction.response.edit_message(
                content=(
                    f" **لعبة توصيل الكرات 4** \nلعب البوت رقم {bot_col + 1} حان"
                    f" دورك: {view.player1.mention} (🔴)\n\n"
                    + view.get_board_string()
                ),
                view=view,
            )


class Connect4View(discord.ui.View):
    def __init__(self, player1: discord.User, player2: discord.User = None):
        super().__init__(timeout=60)
        self.player1 = player1
        self.player2 = player2
        self.is_vs_bot = player2 is None
        self.current_player = player1
        self.current_emoji = "🔴"
        self.message = None

        self.rows = 6
        self.cols = 7
        self.board = [["⚪" for _ in range(self.cols)] for _ in range(self.rows)]

        for col in range(self.cols):
            row_idx = 0 if col < 5 else 1
            self.add_item(Connect4Button(col, row_idx))

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(
                    content=(
                        f"⏰ **انتهت اللعبة لعدم التفاعل خلال دقيقة واحدة**\n\n"
                        + self.get_board_string()
                    ),
                    view=self,
                )
            except Exception:
                pass

    def get_board_string(self) -> str:
        board_str = ""
        for r in range(self.rows):
            board_str += "".join(self.board[r]) + "\n"
        board_str += "1️⃣2️⃣3️⃣4️⃣5️⃣6️⃣7️⃣"
        return board_str

    def drop_piece(self, col: int, emoji: str) -> int:
        for r in range(self.rows - 1, -1, -1):
            if self.board[r][col] == "⚪":
                self.board[r][col] = emoji
                return r
        return -1

    def is_board_full(self) -> bool:
        return all(self.board[0][c] != "⚪" for c in range(self.cols))

    def check_winner(self, r: int, c: int, emoji: str) -> bool:
        count = 0
        for col in range(self.cols):
            if self.board[r][col] == emoji:
                count += 1
                if count >= 4:
                    return True
            else:
                count = 0

        count = 0
        for row in range(self.rows):
            if self.board[row][c] == emoji:
                count += 1
                if count >= 4:
                    return True
            else:
                count = 0

        for row in range(self.rows - 3):
            for col in range(self.cols - 3):
                if (
                    self.board[row][col] == emoji
                    and self.board[row + 1][col + 1] == emoji
                    and self.board[row + 2][col + 2] == emoji
                    and self.board[row + 3][col + 3] == emoji
                ):
                    return True

        for row in range(3, self.rows):
            for col in range(self.cols - 3):
                if (
                    self.board[row][col] == emoji
                    and self.board[row - 1][col + 1] == emoji
                    and self.board[row - 2][col + 2] == emoji
                    and self.board[row - 3][col + 3] == emoji
                ):
                    return True

        return False

    def score_position(self, piece: str) -> int:
        score = 0

        center_array = [self.board[r][self.cols // 2] for r in range(self.rows)]
        center_count = center_array.count(piece)
        score += center_count * 4

        def evaluate_window(window, p):
            win_score = 0
            opp_p = "🔴" if p == "🟡" else "🟡"
            if window.count(p) == 4:
                win_score += 10000
            elif window.count(p) == 3 and window.count("⚪") == 1:
                win_score += 100
            elif window.count(p) == 2 and window.count("⚪") == 2:
                win_score += 10

            if window.count(opp_p) == 3 and window.count("⚪") == 1:
                win_score -= 120
            return win_score

        for r in range(self.rows):
            row_array = self.board[r]
            for c in range(self.cols - 3):
                window = row_array[c : c + 4]
                score += evaluate_window(window, piece)

        for c in range(self.cols):
            col_array = [self.board[r][c] for r in range(self.rows)]
            for r in range(self.rows - 3):
                window = col_array[r : r + 4]
                score += evaluate_window(window, piece)

        for r in range(self.rows - 3):
            for c in range(self.cols - 3):
                window = [self.board[r + i][c + i] for i in range(4)]
                score += evaluate_window(window, piece)

        for r in range(3, self.rows):
            for c in range(self.cols - 3):
                window = [self.board[r - i][c + i] for i in range(4)]
                score += evaluate_window(window, piece)

        return score

    def minimax(
        self, depth: int, alpha: int, beta: int, maximizingPlayer: bool
    ) -> tuple:
        valid_cols = [c for c in range(self.cols) if self.board[0][c] == "⚪"]
        is_terminal = self.is_board_full()

        if depth == 0 or is_terminal:
            return None, self.score_position("🟡")

        if maximizingPlayer:
            value = -9999999
            best_col = random.choice(valid_cols)
            for col in valid_cols:
                row = self.drop_piece(col, "🟡")
                if self.check_winner(row, col, "🟡"):
                    self.board[row][col] = "⚪"
                    return col, 10000000
                _, new_score = self.minimax(depth - 1, alpha, beta, False)
                self.board[row][col] = "⚪"
                if new_score > value:
                    value = new_score
                    best_col = col
                alpha = max(alpha, value)
                if alpha >= beta:
                    break
            return best_col, value
        else:
            value = 9999999
            best_col = random.choice(valid_cols)
            for col in valid_cols:
                row = self.drop_piece(col, "🔴")
                if self.check_winner(row, col, "🔴"):
                    self.board[row][col] = "⚪"
                    return col, -10000000
                _, new_score = self.minimax(depth - 1, alpha, beta, True)
                self.board[row][col] = "⚪"
                if new_score < value:
                    value = new_score
                    best_col = col
                beta = min(beta, value)
                if alpha >= beta:
                    break
            return best_col, value

    def bot_move(self) -> tuple:
        valid_cols = [c for c in range(self.cols) if self.board[0][c] == "⚪"]
        if not valid_cols:
            return -1, -1

        for col in valid_cols:
            row = self.drop_piece(col, "🟡")
            if self.check_winner(row, col, "🟡"):
                return col, row
            self.board[row][col] = "⚪"

        for col in valid_cols:
            row = self.drop_piece(col, "🔴")
            if self.check_winner(row, col, "🔴"):
                self.board[row][col] = "⚪"
                bot_row = self.drop_piece(col, "🟡")
                return col, bot_row
            self.board[row][col] = "⚪"

        best_col, _ = self.minimax(4, -9999999, 9999999, True)
        if best_col is None or best_col not in valid_cols:
            best_col = random.choice(valid_cols)

        row = self.drop_piece(best_col, "🟡")
        return best_col, row


@bot.command(name="توصيل", aliases=["توصيل4", "connect4", "كرات4", "أربعة"])
@in_channel(GAMES_CHANNEL_ID)
async def connect4_game(ctx, opponent: discord.Member = None):
    if opponent and opponent.bot:
        await ctx.send(
            "❌ لا يمكنك تحدي بوت آخر، استخدم الأمر بدون منشن للعب ضد هذا البوت."
        )
        return

    if opponent and opponent == ctx.author:
        await ctx.send("❌ لا يمكنك تحدي نفسك")
        return

    if opponent:
        view = Connect4View(player1=ctx.author, player2=opponent)
        msg = await ctx.send(
            f"**بدأت لعبة توصيل الكرات 4** بين {ctx.author.mention} (🔴) و"
            f" {opponent.mention} (🟡)\nالجائزة: **60 طولار** للفائز\nدور:"
            f" {ctx.author.mention}\n\n"
            + view.get_board_string(),
            view=view,
            allowed_mentions=discord.AllowedMentions(users=False),
        )
        view.message = msg
    else:
        view = Connect4View(player1=ctx.author)
        msg = await ctx.send(
            f"**بدأت لعبة توصيل الكرات 4** بين {ctx.author.mention} (🔴) و"
            " البوت (🟡)\nالجائزة: **60 طولار** للفائز!\nدور:"
            f" {ctx.author.mention}\n\n"
            + view.get_board_string(),
            view=view,
            allowed_mentions=discord.AllowedMentions(users=False),
        )
        view.message = msg


# --- إعدادات وتعاريف لعبة خمن ---
ACTIVE_ANIME_GAMES = {}
ANIME_REWARD = 20  # الجائزة بالطولار لكل إجابة صحيحة
ANIME_DATABASE_FILE = os.path.join(BASE_DIR, "anime_characters.json")

def load_anime_characters():
    """تحميل قاعدة شخصيات الأنمي من ملف JSON وإرجاع الشخصيات الصالحة فقط."""
    try:
        with open(ANIME_DATABASE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            print("[ANIME] ملف anime_characters.json يجب أن يحتوي على قائمة شخصيات.")
            return []

        valid_characters = []
        for character in data:
            if not isinstance(character, dict):
                continue

            image_url = str(character.get("image_url") or "").strip()
            answers = character.get("answers") or []
            name = str(character.get("name") or "").strip()

            if not image_url or not (image_url.startswith("http://") or image_url.startswith("https://")):
                continue

            if not isinstance(answers, list):
                answers = [answers]

            clean_answers = [str(answer).strip() for answer in answers if str(answer).strip()]
            if name and name not in clean_answers:
                clean_answers.append(name)

            if not clean_answers:
                continue

            valid_characters.append({
                **character,
                "name": name or clean_answers[0],
                "answers": clean_answers,
                "image_url": image_url,
            })

        return valid_characters

    except FileNotFoundError:
        print(f"[ANIME] لم يتم العثور على ملف قاعدة الشخصيات: {ANIME_DATABASE_FILE}")
        return []
    except json.JSONDecodeError as e:
        print(f"[ANIME] ملف anime_characters.json غير صالح JSON: {e}")
        return []
    except Exception as e:
        print(f"[ANIME] فشل تحميل قاعدة الشخصيات: {e}")
        return []


def is_correct_anime_answer(user_answer, valid_answers):
    # تنظيف نص المستخدم
    user_input = user_answer.strip().lower()
    
    if not user_input:
        return False

    for answer in valid_answers:
        clean_answer = answer.strip().lower()
        
        # 1. مطابقة كاملة 
        if user_input == clean_answer:
            return True
            
        # 2. مطابقة جزء من الاسم (الاسم الأول أو الأخير)
        words = clean_answer.split()
        for word in words:
            if len(word) > 2 and user_input == word:
                return True

        # 3. التسامح مع الأخطاء الإملائية (حرف أو حرفين)
        overall_similarity = SequenceMatcher(None, user_input, clean_answer).ratio()
        if overall_similarity >= 0.75:  
            return True

        for word in words:
            if len(word) > 2:
                word_similarity = SequenceMatcher(None, user_input, word).ratio()
                if word_similarity >= 0.75:
                    return True

    return False


@bot.command(name="خمن")
@in_channel(GAMES_CHANNEL_ID)
async def anime_guess_command(ctx, rounds: int = 1):
    if rounds < 1 or rounds > 10:
        await ctx.send(
            "❌ عدد الجولات يجب أن يكون من **1 إلى 10**.",
            allowed_mentions=discord.AllowedMentions(users=False),
        )
        return

    user_id = ctx.author.id

    if user_id in ACTIVE_ANIME_GAMES:
        await ctx.send(
            f"⚠️ {ctx.author.mention} لديك لعبة خمن قيد التشغيل بالفعل.",
            allowed_mentions=discord.AllowedMentions(users=False),
        )
        return

    available_characters = load_anime_characters()
    if not available_characters:
        await ctx.send(
            "❌ لم يتم العثور على شخصيات صالحة في `anime_characters.json`.\n"
            "تأكد من وجود الملف وأنه يحتوي على `image_url` و`answers` لكل شخصية.",
            allowed_mentions=discord.AllowedMentions(users=False),
        )
        return

    if rounds > len(available_characters):
        rounds = len(available_characters)
        await ctx.send(
            f"⚠️ تم تعديل عدد الجولات إلى **{rounds}** لعدم توفر شخصيات كافية بدون تكرار.",
            allowed_mentions=discord.AllowedMentions(users=False),
        )

    chosen_characters = random.sample(available_characters, rounds)

    # تسجيل اللعبة
    ACTIVE_ANIME_GAMES[user_id] = True

    correct_count = 0
    total_reward = 0

    await ctx.send(
        f"**🎮 لعبة خمن بدأت**\n"
        f"👤 اللاعب┃{ctx.author.mention}\n"
        f"🎯 عدد الجولات┃**{rounds}**\n"
        f"💰 المكافأة┃**{ANIME_REWARD} طولار** لكل إجابة صحيحة.\n"
        f"⏱️ لديك **15 ثانية** للإجابة في كل جولة.",
        allowed_mentions=discord.AllowedMentions(users=False),
    )

    try:
        for round_number, character in enumerate(chosen_characters, start=1):
            image_url = character["image_url"]

            # إنشاء الـ Embed (بدون صورة حالياً)
            embed = discord.Embed(
                description=f"** الجولة {round_number}/{rounds}**\nمن هذه الشخصية؟",
                color=discord.Color.blue(),
            )
            if character.get("source_url"):
                embed.url = character["source_url"]

            # محاولة تحميل الصورة وإرسالها كملف مرفق
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(image_url) as resp:
                        if resp.status == 200:
                            data = io.BytesIO(await resp.read())
                            file = discord.File(data, filename="anime_char.png")
                            embed.set_image(url="attachment://anime_char.png")

                            await ctx.send(
                                file=file,
                                embed=embed,
                                allowed_mentions=discord.AllowedMentions(users=False)
                            )
                        else:
                            raise Exception("فشل التحميل السريع")
            except Exception:
                # فشل التحميل -> نرسل الصورة عبر الرابط (مرة واحدة فقط)
                embed.set_image(url=image_url)
                await ctx.send(
                    embed=embed,
                    allowed_mentions=discord.AllowedMentions(users=False)
                )

            # انتظار الإجابة
            def check(message):
                return (
                    message.author.id == user_id
                    and message.channel.id == ctx.channel.id
                    and not message.author.bot
                    and is_correct_anime_answer(message.content, character["answers"])
                )

            try:
                await bot.wait_for("message", timeout=15, check=check)
                add_balance(user_id, ANIME_REWARD)
                correct_count += 1
                total_reward += ANIME_REWARD

                await ctx.send(
                    f"✅ **إجابة صحيحة**\n💰 حصلت على **+{ANIME_REWARD} طولار**.",
                    allowed_mentions=discord.AllowedMentions(users=False),
                )

            except asyncio.TimeoutError:
                correct_answer = character["answers"][0]
                await ctx.send(
                    f"⏰ انتهى الوقت يا {ctx.author.mention}.\n"
                    f"❌ الإجابة الصحيحة كانت: **{correct_answer}**",
                    allowed_mentions=discord.AllowedMentions(users=False),
                )

            if round_number < rounds:
                await asyncio.sleep(1)

    finally:
        # حذف المفتاح بعد انتهاء اللعبة (سواء اكتملت أو حدث خطأ)
        ACTIVE_ANIME_GAMES.pop(user_id, None)

    # النتيجة النهائية
    current_balance = get_balance(user_id)
    await ctx.send(
        f"**🏁 انتهت لعبة خمن**\n"
        f"👤 اللاعب┃{ctx.author.mention}\n"
        f"📊 الجولات┃**{rounds}**\n"
        f"✅ الإجابات الصحيحة┃**{correct_count}/{rounds}**\n"
        f"💰 إجمالي المكافأة┃**{total_reward} طولار**\n"
        f"💳 رصيدك الحالي┃**{current_balance:,} طولار**",
        allowed_mentions=discord.AllowedMentions(users=False),
    )


@bot.command(name="طولاري", aliases=["طولار"])
@in_channel(SHOPPING_CHANNEL_ID)
async def balance_command(ctx, member: discord.Member = None):
    target = member or ctx.author

    # الرصيد يُجلب حديثاً، أما صورة الأفاتار فنخزنها 5 دقائق.
    avatar_url = str(target.display_avatar.url)
    avatar_bytes = _BALANCE_AVATAR_CACHE.get(avatar_url)
    if avatar_bytes is None:
        avatar_bytes = await target.display_avatar.read()
        _BALANCE_AVATAR_CACHE.set(avatar_url, avatar_bytes)

    bal = await _run_bg(get_balance, target.id)

    # إذا لم يتغير الاسم/الرصيد/الأفاتار، نرسل الصورة الجاهزة بدلاً من إعادة رسمها.
    card_key = (target.id, avatar_url, target.display_name, int(bal))
    cached_card = _BALANCE_CARD_CACHE.get(card_key)
    if cached_card is not None:
        img_buf = io.BytesIO(cached_card)
    else:
        img_buf = await _run_bg(draw_balance_card, avatar_bytes, target.display_name, bal)
        try:
            card_bytes = img_buf.getvalue()
        finally:
            img_buf.close()
        _BALANCE_CARD_CACHE.set(card_key, card_bytes)
        img_buf = io.BytesIO(card_bytes)
    try:
        file = discord.File(fp=img_buf, filename="balance.png")
        await ctx.send(
            file=file,
            allowed_mentions=discord.AllowedMentions(users=False),
        )
    finally:
        img_buf.close()

@bot.command(name="ض")
@commands.has_role(OWNER_ROLE_ID)
@in_channel(SHOPPING_CHANNEL_ID)
async def add_money(ctx, member: discord.Member, amount: int):
    if amount <= 0:
        await ctx.send("❌ يرجى إدخال مبلغ صحيح أكبر من 0.")
        return

    add_balance(member.id, amount)
    await ctx.send(
        f" تم إضافة **{amount}** طولار إلى حساب {member.mention} بنجاح\n"
        f" رصيده الجديد: **{get_balance(member.id)}** طولار.",
        allowed_mentions=discord.AllowedMentions.none(),
    )


@add_money.error
async def add_money_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("❌ هذا الأمر مخصص لصاحب رتبة الاونر فقط")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(
            "**طريقة الاستخدام الصحيحة:**\n"
            "`اضافة @العضو المبلغ`\n"
        )
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❌ يرجى منشن عضو صحيح وكتابة المبلغ بالأرقام.")


@bot.command(name="ز", aliases=["خصم"])
@commands.has_role(OWNER_ROLE_ID)
@in_channel(SHOPPING_CHANNEL_ID)
async def remove_money(ctx, member: discord.Member, amount: int):
    if amount <= 0:
        await ctx.send("❌ يرجى إدخال مبلغ صحيح أكبر من 0.")
        return

    current_balance = get_balance(member.id)
    if current_balance < amount:
        await ctx.send(f"❌ رصيد العضو الحالي (**{current_balance}** طولار) أقل من المبلغ المراد خصمه.")
        return

    remove_balance(member.id, amount)
    await ctx.send(
        f"✅ تم خصم **{amount}** طولار من حساب {member.mention} بنجاح\n"
        f"💰 رصيده الجديد: **{get_balance(member.id)}** طولار.",
        allowed_mentions=discord.AllowedMentions.none(),
    )

@remove_money.error
async def remove_money_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("❌ هذا الأمر مخصص لصاحب رتبة الاونر فقط.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(
            "**طريقة الاستخدام الصحيحة:**\n"
            "`ز @العضو المبلغ`\n"
        )
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❌ يرجى منشن عضو صحيح وكتابة المبلغ بالأرقام.")


@bot.command(name="ت", aliases=["transfer", "pay"])
@in_channel(SHOPPING_CHANNEL_ID)
async def transfer_money(
    ctx, member: discord.Member = None, amount: int = None
):
    if not member or amount is None:
        await ctx.send(
            " **طريقة الاستخدام الصحيحة:**\n"
            "`.تحويل @العضو المبلغ`\n",
            delete_after=5,
        )
        return

    if member.bot:
        await ctx.send("❌ لا يمكنك تحويل الطولارات للبوتات", delete_after=3)
        return

    if member == ctx.author:
        await ctx.send("❌ لا يمكنك تحويل الطولارات لنفسك", delete_after=3)
        return

    if amount <= 0:
        await ctx.send("❌ يرجى إدخال مبلغ صحيح أكبر من **0**", delete_after=3)
        return

    sender_balance = get_balance(ctx.author.id)
    if sender_balance < amount:
        await ctx.send(
            f"❌ رصيدك غير كاف رصيدك الحالي هو **{sender_balance}** طولار.",
            delete_after=5,
        )
        return

    remove_balance(ctx.author.id, amount)
    add_balance(member.id, amount)

    await ctx.send(
        " **تم التحويل بنجاح**\n"
        f"قمـت بـتحـويـل **{amount}** طولار إلى {member.mention}.\n"
        f" رصيدك المتبقي: **{get_balance(ctx.author.id)}** طولار.",
        allowed_mentions=discord.AllowedMentions(users=False),
    )


@transfer_money.error
async def transfer_money_error(ctx, error):
    if isinstance(error, commands.BadArgument):
        await ctx.send(
            "❌ يرجى منشن عضو صحيح وكتابة المبلغ بالأرقام.", delete_after=3
        )


# ==========================================
# 🚀 أمر الرهان الرئيسي - المحدث
# ==========================================

class BetCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="رهان", aliases=["bet", "عجلة_المصير"])
    @in_channel(SHOPPING_CHANNEL_ID)
    async def bet_game(
        self,
        ctx,
        opponent: typing.Union[discord.Member, int] = None,
        amount: typing.Optional[int] = None,
    ):
        if isinstance(opponent, int):
            amount = opponent
            opponent = None

        if not opponent or amount is None:
            return await ctx.send(
                "❌ **طريقة الاستخدام الصحيحة:**\n`.رهان @العضو المبلغ`\nمثال: `.رهان @User 500`"
            )

        if opponent.bot or opponent == ctx.author:
            return await ctx.send("❌ لا يمكنك رهان نفسك أو البوتات")

        if amount <= 0:
            return await ctx.send("❌ يرجى إدخال مبلغ رهان صحيح")

        # تحقق من الرصيد قبل البدء
        # جلب الرصيدين معًا بدل تكرار get_balance، وتحميل الأفاتارين بالتوازي.
        author_bal_task = asyncio.create_task(_run_bg(get_balance, ctx.author.id))
        opponent_bal_task = asyncio.create_task(_run_bg(get_balance, opponent.id))
        p1_avatar_task = asyncio.create_task(ctx.author.display_avatar.read())
        p2_avatar_task = asyncio.create_task(opponent.display_avatar.read())
        author_bal, opponent_bal, p1_bytes, p2_bytes = await asyncio.gather(
            author_bal_task, opponent_bal_task, p1_avatar_task, p2_avatar_task
        )

        if author_bal < amount:
            return await ctx.send(f"❌ رصيدك غير كاف، رصيدك الحالي هو **{author_bal}** طولار.")
        if opponent_bal < amount:
            return await ctx.send(f"❌ رصيد {opponent.mention} غير كاف لهذا الرهان")

        # إنشاء صورة التحدي خارج event loop.
        challenge_img = await _run_bg(
            draw_challenge_card, p1_bytes, p2_bytes,
            ctx.author.display_name, opponent.display_name, amount
        )
        file_challenge = discord.File(challenge_img, filename="challenge.png")

        view = ChallengeView(ctx.author, opponent, amount)
        msg = await ctx.send(
            content=(
                f"⚔️ **تحدي رهان جديد**\n{opponent.mention} لديك 30 ثانية لقبول"
                f" تحدي {ctx.author.mention} على **${amount:,}** طولار"
            ),
            file=file_challenge,
            view=view,
        )

        await view.wait()
        if not view.accepted:
            # إذا لم يتم قبول التحدي، قم بإزالة الرسالة
            try:
                await msg.delete()
            except:
                pass
            return

        # تحقق من الرصيد مرة أخرى بعد القبول (لضمان عدم تغير الرصيد خلال 30 ثانية)
        # إعادة التحقق بعد القبول، لكن خارج event loop.
        author_bal, opponent_bal = await asyncio.gather(
            _run_bg(get_balance, ctx.author.id),
            _run_bg(get_balance, opponent.id),
        )
        if author_bal < amount or opponent_bal < amount:
            return await ctx.send("❌ لم يتمكن أحد الطرفين من دفع مبلغ الرهان، تم إلغاء المبارزة.")

        # 2. تحديد الفائز وتوليد العجلة المتحركة GIF.
        winner_idx = random.choice([0, 1])  # 0 = أزرق، 1 = أحمر
        winner = ctx.author if winner_idx == 0 else opponent
        loser = opponent if winner_idx == 0 else ctx.author

        # إرسال العجلة في رسالة جديدة مستقلة، دون تعديل رسالة التحدي.
        try:
            gif_buffer = await _run_bg(
                generate_wheel_gif,
                ctx.author.display_name, opponent.display_name, winner_idx
            )
            gif_file = discord.File(gif_buffer, filename="wheel.gif")
            await ctx.send(
                content="🎰 **جاري تدوير عجلة المصير...**",
                file=gif_file,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except Exception as e:
            print(f"[BET] Wheel error: {type(e).__name__}: {e}")
            return await ctx.send("❌ حدث خطأ أثناء تشغيل عجلة الرهان. راجع Console البوت.")

        # مدة العرض قصيرة؛ المعالجة الثقيلة أصبحت خارج event loop.
        await asyncio.sleep(0.5)

        # 3. تنفيذ التحويل الاقتصادي خارج event loop.
        await _run_bg(remove_balance, loser.id, amount)
        await _run_bg(add_balance, winner.id, amount)

        winner_bal_after, loser_bal_after = await asyncio.gather(
            _run_bg(get_balance, winner.id),
            _run_bg(get_balance, loser.id),
        )

        # 4. تجهيز صورة النتيجة.
        try:
            winner_bytes, loser_bytes = await asyncio.gather(
                winner.display_avatar.read(),
                loser.display_avatar.read(),
            )
            result_img = await _run_bg(
                draw_result_card,
                winner_bytes, loser_bytes,
                winner.display_name, loser.display_name,
                amount, winner_bal_after, loser_bal_after,
            )
            result_img.seek(0)
            result_file = discord.File(result_img, filename="bet_result.png")
        except Exception as e:
            print(f"[BET] Result image error: {type(e).__name__}: {e}")
            return await ctx.send(
                f"🎉 **مبروك للفائز** {winner.mention} كسب **${amount:,}** طولار،\n"
                "⚠️ تعذر إنشاء صورة النتيجة، لكن تم احتساب الرهان بنجاح."
            )

        # 5. إرسال النتيجة في رسالة جديدة مستقلة، دون تعديل رسالة التحدي أو رسالة العجلة.
        # نستخدم كائن Member نفسه في AllowedMentions بدل winner.id.
        try:
            await ctx.send(
                content=(
                    f"🎉 **مبروك للفائز** {winner.mention} كسب مبارزة عجلة المصير "
                    f"وحصل على **{amount:,}** طولار من منافسه"
                ),
                file=result_file,
                allowed_mentions=discord.AllowedMentions(users=[winner]),
            )
        except Exception as e:
            print(f"[BET] Result message send error: {type(e).__name__}: {e}")
            # إظهار الخطأ داخل Discord أيضًا حتى لا يفشل الإرسال بصمت.
            try:
                await ctx.send(
                    "⚠️ تم احتساب الرهان، لكن تعذر إرسال صورة النتيجة. "
                    f"الخطأ: `{type(e).__name__}: {e}`"
                )
            except Exception:
                pass

@bot.command(name="ايدي")
async def get_id(
    ctx,
    target: typing.Union[
        discord.TextChannel, discord.Member, discord.Role, str
    ] = None,
):
    if not target:
        await ctx.send(f"🆔 الآيدي الخاص بك: `{ctx.author.id}`")
        return

    if ctx.message.role_mentions:
        role = ctx.message.role_mentions[0]
        await ctx.send(f"🆔 آيدي الرتبة **{role.name}**: `{role.id}`")
        return

    if isinstance(target, discord.TextChannel):
        await ctx.send(f"🆔 آيدي الروم {target.mention}: `{target.id}`")
        return

    if ctx.message.mentions:
        member = ctx.message.mentions[0]
        await ctx.send(f"🆔 آيدي العضو {member.mention}: `{member.id}`")
        return

    member = discord.utils.find(
        lambda m: m.name == target or m.display_name == target, ctx.guild.members
    )
    if member:
        await ctx.send(f"🆔 آيدي العضو {member.mention}: `{member.id}`")
        return

    role = discord.utils.find(lambda r: r.name == target, ctx.guild.roles)
    if role:
        await ctx.send(f"🆔 آيدي الرتبة **{role.name}**: `{role.id}`")
        return

    await ctx.send("❌ لم يتم العثور على عضو أو رتبة بهذا المنشن/الاسم.")


@bot.command(name="مسح", aliases=["clear", "مسح_الرسائل"])
@commands.has_role(OWNER_ROLE_ID)
async def clear_messages(ctx, amount: int = None):
    if amount is None or amount <= 0:
        await ctx.send(
            "⚠️ يرجى تحديد عدد الرسائل المراد مسحها.\nمثال: `.مسح 10`",
            delete_after=2,
        )
        return

    deleted = await ctx.channel.purge(limit=amount + 1)
    await ctx.send(f" تم مسح **{len(deleted) - 1}** رسالة بنجاح", delete_after=1)


@clear_messages.error
async def clear_messages_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("❌ هذا الأمر مخصص للـ اونر فقط", delete_after=2)
    elif isinstance(error, commands.BadArgument):
        await ctx.send(
            "❌ يرجى كتابة عدد الرسائل بالأرقام فقط (مثال: `.مسح 5`).",
            delete_after=1,
        )
    elif isinstance(error, commands.BotMissingPermissions):
        await ctx.send(
            "❌ البوت لا يملك صلاحية `Manage Messages` (إدارة الرسائل) لمسح الشات"
        )


@bot.command(name="افتار", aliases=["avatar", "افتاري"])
@in_channel(AVATAR_CHANNEL_ID)
async def show_avatar(ctx, member: discord.Member = None):
    target = member or ctx.author
    avatar_url = target.display_avatar.url

    embed = discord.Embed(color=discord.Color.dark_theme())
    embed.set_image(url=avatar_url)

    await ctx.send(embed=embed)


@bot.command(name="بنر", aliases=["banner", "بنري"])
@in_channel(AVATAR_CHANNEL_ID)
async def show_banner(ctx, member: discord.Member = None):
    target = member or ctx.author
    user = await bot.fetch_user(target.id)

    if not user.banner:
        await ctx.send("❌ هذا الحساب لا يملك بنر", delete_after=2)
        return

    banner_url = user.banner.url

    embed = discord.Embed(color=discord.Color.dark_theme())
    embed.set_image(url=banner_url)

    await ctx.send(embed=embed)


@show_avatar.error
async def avatar_error(ctx, error):
    if isinstance(error, commands.BadArgument):
        await ctx.send("❌ لم يتم العثور على هذا العضو أو البوت", delete_after=2)


@show_banner.error
async def banner_error(ctx, error):
    if isinstance(error, commands.BadArgument):
        await ctx.send("❌ لم يتم العثور على هذا العضو أو البوت", delete_after=2)


@bot.command(name="تغيير")
@commands.has_permissions(administrator=True)
@in_channel(AVATAR_CHANNEL_ID)
async def change_profile(ctx):
    await ctx.send("ماذا تريد أن تغير؟ اكتب **افتار** أو **بنر**.")

    def check_choice(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content in ["افتار", "بنر"]

    try:
        choice_msg = await bot.wait_for("message", check=check_choice, timeout=30.0)
        choice = choice_msg.content

        await ctx.send(f"تم اختيار **{choice}**. الرجاء إرسال الصورة الآن كملف مرفق.")

        def check_image(m):
            return m.author == ctx.author and m.channel == ctx.channel and len(m.attachments) > 0

        img_msg = await bot.wait_for("message", check=check_image, timeout=60.0)
        image_url = img_msg.attachments[0].url

        async with aiohttp.ClientSession() as session:
            async with session.get(image_url) as resp:
                if resp.status != 200:
                    return await ctx.send("تعذر تحميل الصورة، حاول مرة أخرى.")
                image_data = await resp.read()

        if choice == "افتار":
            await bot.user.edit(avatar=image_data)
            await ctx.send("تم تغيير رمزية (افتار) البوت بنجاح ✅")
        elif choice == "بنر":
            await bot.user.edit(banner=image_data)
            await ctx.send("تم تغيير بنر البوت بنجاح! ✅")

    except asyncio.TimeoutError:
        await ctx.send("تأخرت في الرد، تم إلغاء العملية.")
    except discord.HTTPException as e:
        await ctx.send(f"حدث خطأ أثناء التحديث: {e}")


@change_profile.error
async def change_profile_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("عذراً، هذا الأمر مخصص للمسؤولين  فقط ❌")


# --- 9. قوائم الألعاب والأوامر والأدلة ---

# الأوامر الأساسية مصنفة هنا حتى تكون قوائم .اوامر و .دليل متطابقة مع أوامر البوت.
# أوامر المالك (OWNER_ROLE_ID) لا تظهر في .اوامر، لكنها تظهر في .دليل.
OWNER_ONLY_COMMANDS = {
    "تحكم_متجر", "ض", "ز", "مسح",
    "انقلع_يالعبد", "اصمت", "تحدث",
    "باند", "فك_باند", "ق", "ف",
    "تكت", "تعديل",
}

ADMIN_COMMANDS = {"تغيير"}

GAME_COMMANDS = {
    ".سؤال [عدد الجولات]": "مسابقة أسئلة عامة من 1 إلى 10 جولات.",
    ".لغز [عدد الجولات]": "تحدي ألغاز من 1 إلى 10 جولات.",
    ".حجر [@عضو]": "حجرة ورقة مقص ضد البوت أو تحدي عضو آخر.",
    ".اكس [@عضو]": "لعبة إكس أو (XO) ضد البوت أو عضو آخر.",
    ".توصيل [@عضو]": "لعبة Connect 4 ضد البوت أو عضو آخر.",
    ".خمن [عدد الجولات]": "لعبة تخمين الأنمي من 1 إلى 10 جولات.",
    ".روليت [المبلغ]": "روليت جماعية، ويمكن إضافة مبلغ للجائزة.",
    ".اختباء [المبلغ]": "لعبة اختباء جماعية، ويمكن إضافة مبلغ للجائزة.",
}

GAME_AUTO_FEATURES = [
    "`🧠 إرسال إيموجي منفرد` — لعبة تذكّر مكان الإيموجي تلقائياً.",
]

PUBLIC_COMMAND_FIELDS = [
    (
        "💰 الاقتصاد والمتجر",
        [
            (".متجر", "فتح المتجر الملكي لشراء الرتب والألوان."),
            (".طولاري [@عضو]", "عرض رصيد الطولارات لك أو لعضو آخر."),
            (".ت @العضو المبلغ", "تحويل طولارات إلى عضو آخر."),
            (".رهان @العضو [المبلغ]", "الرهان بالعجلة ضد عضو آخر."),
        ],
    ),
    (
        "🖼️ البروفايل والأفاتار",
        [
            (".افتار [@عضو]", "عرض الصورة الشخصية."),
            (".بنر [@عضو]", "عرض غلاف الحساب."),
            (".تغيير", "تغيير افتار أو بنر البوت — للمسؤولين فقط."),
        ],
    ),
    (
        "⚙️ عامة",
        [
            (".ايدي [روم/رتبة/عضو]", "معرفة الـ ID للروم أو الرتبة أو العضو."),
            (".اوامر", "عرض الأوامر المتاحة للأعضاء، بدون أوامر المالك."),
            (".دليل", "عرض الدليل الكامل لجميع أوامر البوت."),
            (".العاب", "عرض قائمة الألعاب كاملة."),
        ],
    ),
]

# نستخدم قوائم منفصلة للدليل حتى لا نعرض أوامر المالك داخل .اوامر.
ALL_COMMANDS = [
    ("💰 الاقتصاد والمتجر", [
        (".متجر", "فتح المتجر الملكي لشراء الرتب والألوان.", False),
        (".تحكم_متجر", "إدارة الرتب والألوان في المتجر.", True),
        (".طولاري [@عضو]", "عرض رصيد الطولارات.", False),
        (".ض @العضو المبلغ", "إضافة طولارات لعضو.", True),
        (".ز @العضو المبلغ", "خصم طولارات من عضو.", True),
        (".ت @العضو المبلغ", "تحويل طولارات إلى عضو آخر.", False),
        (".رهان @العضو [المبلغ]", "الرهان بالعجلة ضد عضو آخر.", False),
    ]),
    ("🎮 الألعاب", [
        (command, description, False) for command, description in GAME_COMMANDS.items()
    ]),
    ("🖼️ البروفايل والأفاتار", [
        (".افتار [@عضو]", "عرض الصورة الشخصية.", False),
        (".بنر [@عضو]", "عرض غلاف الحساب.", False),
        (".تغيير", "تغيير افتار أو بنر البوت.", False),
    ]),
    ("⚙️ العامة والإدارة", [
        (".ايدي [روم/رتبة/عضو]", "معرفة الـ ID.", False),
        (".مسح [العدد]", "مسح عدد من الرسائل.", True),
        (".انقلع_يالعبد @العضو [السبب]", "حظر عضو.", True),
        (".اصمت @العضو [الدقائق] [السبب]", "كتم عضو لمدة محددة.", True),
        (".تحدث @العضو", "إزالة الكتم عن عضو.", True),
        (".باند @العضو [السبب]", "حظر عضو باستخدام المنشن.", True),
        (".فك_باند @العضو/الايدي [السبب]", "فك حظر عضو.", True),
        (".ق", "قفل الروم الحالي.", True),
        (".ف", "فتح الروم الحالي.", True),
        (".تكت", "فتح لوحة نظام التذاكر.", True),
        (".تعديل", "إدارة الردود التلقائية.", True),
        (".اوامر", "عرض الأوامر المتاحة للأعضاء.", False),
        (".دليل", "عرض الدليل الكامل لجميع الأوامر.", False),
        (".العاب", "عرض قائمة الألعاب.", False),
    ]),
]

def _add_command_fields(embed, fields, include_owner=True):
    """إضافة حقول أوامر مرتبة داخل Embed."""
    for field_name, commands_list in fields:
        lines = []
        for command_name, description, *restricted in commands_list:
            is_owner = bool(restricted and restricted[0])
            if is_owner and not include_owner:
                continue
            marker = " 🔒" if is_owner else ""
            if command_name == ".تغيير":
                marker = " 🔐"
            lines.append(f"• `{command_name}`{marker} — {description}")
        if lines:
            embed.add_field(
                name=field_name,
                value="\n".join(lines),
                inline=False,
            )

@bot.command(name="العاب")
async def games_list(ctx):
    embed = discord.Embed(
        title="🎮 قائمة الألعاب",
        description="جميع ألعاب البوت متوفرة هنا بشكل مختصر وواضح:",
        color=discord.Color.blue(),
    )

    game_lines = [
        f"• `{command}` — {description}"
        for command, description in GAME_COMMANDS.items()
    ]
    embed.add_field(
        name="🕹️ الألعاب",
        value="\n".join(game_lines),
        inline=False,
    )
    embed.add_field(
        name="🧠 لعبة تلقائية",
        value=GAME_AUTO_FEATURES[0],
        inline=False,
    )
    embed.set_footer(text="الألعاب تعمل في روم الألعاب المخصص.")
    await ctx.send(embed=embed)


@bot.command(name="اوامر")
async def commands_list(ctx):
    """عرض الأوامر المتاحة للأعضاء مع استبعاد أوامر المالك."""
    embed = discord.Embed(
        title="⚙️ أوامر البوت",
        description="الأوامر المتاحة للأعضاء، مع استبعاد أوامر المالك 🔒.",
        color=discord.Color.blurple(),
    )

    _add_command_fields(embed, ALL_COMMANDS, include_owner=False)

    embed.set_footer(text=f"طلب بواسطة {ctx.author.display_name}")
    await ctx.send(embed=embed)


@bot.command(name="دليل", aliases=["هيلب", "help", "المساعدة"])
async def help_command(ctx):
    """الدليل الكامل لجميع أوامر البوت، بما فيها أوامر المالك."""
    embed = discord.Embed(
        title="📜 دليل أوامر البوت الشامل",
        description=(
            "جميع الأوامر مرتبة حسب القسم.\n"
            "🔒 = الأمر مخصص لصاحب رتبة الاونر.\n"
            "🔐 = الأمر مخصص للمسؤولين."
        ),
        color=discord.Color.gold(),
    )

    _add_command_fields(embed, ALL_COMMANDS, include_owner=True)

    embed.add_field(
        name="🧠 خصائص تلقائية",
        value="• `إرسال إيموجي منفرد` — تشغيل لعبة تذكّر مكان الإيموجي تلقائياً.",
        inline=False,
    )

    embed.set_footer(
        text=f"طلب بواسطة {ctx.author.display_name}",
        icon_url=ctx.author.display_avatar.url,
    )
    await ctx.send(embed=embed)


# --- 10. أوامر الإدارة ---

@bot.command(name="انقلع_يالعبد", aliases=["حظر", "ban"])
@commands.has_role(OWNER_ROLE_ID)
async def ban_member(
    ctx, member: discord.Member = None, *, reason: str = "لم يتم ذكر السبب"
):
    if not member:
        await ctx.send(
            "⚠️ **يرجى منشن العضو المراد حظره**\nمثال: `.انقلع_يالعبد @User السبب`",
            delete_after=3,
        )
        return

    if member == ctx.author:
        await ctx.send("❌ لا يمكنك حظر نفسك")
        return

    if member.id == ctx.guild.owner_id:
        await ctx.send("❌ لا يمكنك حظر صاحب السيرفر")
        return

    try:
        await member.ban(reason=f"بواسطة {ctx.author.name} - السبب: {reason}")
        await ctx.send(
            f" تم حظر العضو **{member.mention}** بنجاح\n السبب: `{reason}`"
        )
    except discord.Forbidden:
        await ctx.send(
            "❌ لا أملك صلاحيات كافية لحظر هذا العضو (تأكد من رتبة البوت أعلى من"
            " رتبة العضو)."
        )
    except Exception as e:
        await ctx.send(f"❌ حدث خطأ أثناء الحظر: {e}")


@ban_member.error
async def ban_member_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("❌ هذا الأمر مخصص للـ اونر فقط", delete_after=3)


@bot.command(name="اصمت", aliases=["كتم", "mute"])
@commands.has_role(OWNER_ROLE_ID)
async def mute_member(
    ctx,
    member: discord.Member = None,
    minutes: int = 10,
    *,
    reason: str = "لم يتم ذكر السبب",
):
    if not member:
        await ctx.send(
            "⚠️ **يرجى منشن العضو المراد كتمه**\nمثال: `.ميوت @User 15 السبب` (15"
            " دقيقة)",
            delete_after=3,
        )
        return

    if member == ctx.author:
        await ctx.send("❌ لا يمكنك كتم نفسك")
        return

    if member.is_timed_out():
        await ctx.send("❌ **هذا العضو مقيد بالفعل**")
        return

    if minutes <= 0:
        await ctx.send("❌ يرجى إدخال عدد دقائق صحيح أكثر من 0.")
        return

    try:
        duration = datetime.timedelta(minutes=minutes)
        await member.timeout(
            duration, reason=f"بواسطة {ctx.author.name} - السبب: {reason}"
        )
        await ctx.send(
            f" تم كتم العضو **{member.mention}** لمدة **{minutes}** دقيقة\n"
            f" السبب: `{reason}`"
        )
    except discord.Forbidden:
        await ctx.send("❌ لا أملك صلاحيات كافية لكتم هذا العضو")
    except Exception as e:
        await ctx.send(f"❌ حدث خطأ: {e}")


@mute_member.error
async def mute_member_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("❌ هذا الأمر مخصص للـ اونر فقط", delete_after=3)


@bot.command(name="تحدث", aliases=["فك_الكتم", "unmute"])
@commands.has_role(OWNER_ROLE_ID)
async def unmute_member(ctx, member: discord.Member):
    if not member:
        await ctx.send(
            "⚠️ **يرجى منشن العضو المراد فك كتمه**\nمثال: `.فك_ميوت @User`",
            delete_after=3,
        )
        return

    if not member.is_timed_out():
        await ctx.send("❌ **هذا العضو غير مقيد بالفعل**")
        return

    try:
        await member.edit(timed_out_until=None)
        await ctx.send(f" تم فك الكتم عن العضو **{member.mention}** بنجاح")
    except discord.Forbidden:
        await ctx.send("❌ لا أملك صلاحيات كافية لفك كتم هذا العضو")
    except Exception as e:
        await ctx.send(f"❌ حدث خطأ: {e}")


@unmute_member.error
async def unmute_member_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("❌ هذا الأمر مخصص للـ اونر فقط", delete_after=3)


# ==========================================
# أوامر الحظر والفك (باند / فك_باند) مع Embed وصورة محلية
# ==========================================

# مسار الصور المحلية (افترض أنها في نفس مجلد البوت)
BAN_IMAGE_PATH = os.path.join(os.path.dirname(__file__), "ban.png")
UNBAN_IMAGE_PATH = os.path.join(os.path.dirname(__file__), "unban.png")


async def send_embed_with_image(ctx, title, description, image_path, color=discord.Color.green()):
    """ترسل Embed مع صورة محلية (ملف)"""
    embed = discord.Embed(title=title, description=description, color=color)
    
    if os.path.exists(image_path):
        # إنشاء كائن File وإرفاقه
        file = discord.File(image_path, filename=os.path.basename(image_path))
        embed.set_image(url=f"attachment://{os.path.basename(image_path)}")
        await ctx.send(embed=embed, file=file)
    else:
        # إذا لم توجد الصورة، نرسل Embed بدون صورة
        await ctx.send(embed=embed)


@bot.command(name="باند", aliases=["حظر_بالمنشن"])
@commands.has_role(OWNER_ROLE_ID)
async def ban_member_by_mention(ctx, member: discord.Member = None, *, reason: str = "لم يتم ذكر السبب"):
    """يحظر عضواً باستخدام منشن، ويرسل Embed مع صورة محلية."""
    if not member:
        await ctx.send(
            "⚠️ **يرجى منشن العضو المراد حظره**\nمثال: `.باند @User السبب`",
            delete_after=3,
        )
        return
    if member == ctx.author:
        await ctx.send("❌ لا يمكنك حظر نفسك")
        return
    if member.id == ctx.guild.owner_id:
        await ctx.send("❌ لا يمكنك حظر صاحب السيرفر")
        return

    try:
        await member.ban(reason=f"بواسطة {ctx.author.name} - السبب: {reason}")
        title = "🚫 تم حظر العضو"
        description = (
            f"**العضو:** {member.mention} (`{member.id}`)\n"
            f"**السبب:** {reason}\n"
            f"**بواسطة:** {ctx.author.mention}"
        )
        await send_embed_with_image(ctx, title, description, BAN_IMAGE_PATH, color=discord.Color.red())
    except discord.Forbidden:
        await ctx.send("❌ لا أملك صلاحيات كافية لحظر هذا العضو (تأكد من رتبة البوت أعلى من رتبة العضو).")
    except Exception as e:
        await ctx.send(f"❌ حدث خطأ أثناء الحظر: {e}")


@ban_member_by_mention.error
async def ban_member_by_mention_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("❌ هذا الأمر مخصص للأونر فقط.", delete_after=3)


@bot.command(name="فك_باند", aliases=["unban"])
@commands.has_role(OWNER_ROLE_ID)
async def unban_member(ctx, user: discord.User = None, *, reason: str = "لم يتم ذكر السبب"):
    """يفك حظر عضو ويعيده عبر رابط دعوة."""
    if user is None:
        args = ctx.message.content.split()
        if len(args) >= 2:
            try:
                user_id = int(args[1])
                user = await bot.fetch_user(user_id)
            except:
                await ctx.send("❌ يرجى إدخال منشن صحيح أو معرف (ايدي) صحيح بالأرقام.\nمثال: `.فك_باند @user` أو `.فك_باند 123456789`")
                return
        else:
            await ctx.send("❌ يرجى منشن العضو المراد فك حظره أو إدخال معرفه.\nمثال: `.فك_باند @user` أو `.فك_باند 123456789`")
            return

    try:
        # لا نحتاج لجلب قائمة المحظورين. نفّذ فك الحظر مباشرة.
        # هذا يتجنب مشاكل اختلاف إصدارات discord.py مع Guild.bans().
        await ctx.guild.unban(user, reason=f"بواسطة {ctx.author.name} - السبب: {reason}")

        # إنشاء رابط دعوة وإرساله للعضو في الخاص
        invite_sent = False
        try:
            invite = await ctx.channel.create_invite(
                max_age=0,
                max_uses=1,
                reason=f"لإعادة {user.name} بعد فك الحظر"
            )
            await user.send(
                f"✅ تم فك حظرك في سيرفر **{ctx.guild.name}**. "
                f"يمكنك الانضمام مجدداً عبر الرابط:\n{invite.url}"
            )
            invite_sent = True
        except discord.Forbidden:
            pass
        except Exception as e:
            print(f"فشل إرسال رابط الدعوة: {e}")

        title = "✅ تم فك الحظر"
        dm_status = "تم إرسال رابط دعوة للعضو في الخاص." if invite_sent else "تم فك الحظر، لكن تعذر إرسال رابط الدعوة في الخاص."
        description = (
            f"**العضو:** {user.name} (`{user.id}`)\n"
            f"**السبب:** {reason}\n"
            f"**بواسطة:** {ctx.author.mention}\n"
            f"{dm_status}"
        )
        await send_embed_with_image(
            ctx, title, description, UNBAN_IMAGE_PATH, color=discord.Color.green()
        )

    except discord.NotFound:
        await ctx.send(f"❌ المستخدم {user.name} ليس محظوراً في هذا السيرفر.")
    except discord.Forbidden:
        await ctx.send("❌ لا أملك صلاحيات كافية لفك الحظر. تأكد من صلاحية Ban Members.")
    except Exception as e:
        await ctx.send(f"❌ حدث خطأ أثناء فك الحظر: {e}")


# ==========================================
# 🔒 أوامر قفل وفتح الرومات (للأونر فقط)
# ==========================================

@bot.command(name="ق")
@commands.has_role(OWNER_ROLE_ID)
async def lock_channel(ctx):
    """يقفل الروم الحالي (يمنع الأعضاء من الإرسال)"""
    channel = ctx.channel
    # التحقق من الصلاحية الحالية للدور الافتراضي
    default_perms = channel.permissions_for(ctx.guild.default_role)
    if not default_perms.send_messages:
        await ctx.send("🔒 هذا الروم مقفول بالفعل.")
        return
    # تعديل الصلاحية: منع الإرسال
    overwrite = channel.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = False
    await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
    await ctx.send("🔒 تم قفل الروم.")

@bot.command(name="ف")
@commands.has_role(OWNER_ROLE_ID)
async def unlock_channel(ctx):
    """يفتح الروم الحالي (يسمح للأعضاء بالإرسال)"""
    channel = ctx.channel
    # التحقق من الصلاحية الحالية للدور الافتراضي
    default_perms = channel.permissions_for(ctx.guild.default_role)
    if default_perms.send_messages:
        await ctx.send("🔓 هذا الروم مفتوح بالفعل.")
        return
    # تعديل الصلاحية: السماح بالإرسال
    overwrite = channel.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = True
    await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
    await ctx.send("🔓 تم فتح الروم.")

# معالجة الأخطاء (اختياري)
@lock_channel.error
@unlock_channel.error
async def lock_unlock_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("❌ هذا الأمر مخصص للأونر فقط.", delete_after=3)


# ضع ID الكاتيجوري هنا، أو اتركه 0 لإنشاء التذاكر بدون كاتيجوري
TICKET_CATEGORY_ID = 0


class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="فتح",
        style=discord.ButtonStyle.primary,
        emoji="🎫",
        custom_id="persistent_ticket_open"
    )
    async def open_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        guild = interaction.guild

        if guild is None:
            await interaction.response.send_message(
                "❌ لا يمكن فتح تذكرة خارج السيرفر.",
                ephemeral=True
            )
            return

        # البحث عن الكاتيجوري بشكل آمن
        category = None

        if TICKET_CATEGORY_ID:
            category = guild.get_channel(TICKET_CATEGORY_ID)

            if category is not None and not isinstance(
                category,
                discord.CategoryChannel
            ):
                category = None

        # إنشاء اسم آمن وفريد للتذكرة
        base_name = re.sub(
            r"[^a-zA-Z0-9_-]",
            "",
            interaction.user.name
        )[:20]

        if not base_name:
            base_name = "user"

        rand_suffix = "".join(
            random.choices(
                string.ascii_lowercase + string.digits,
                k=4
            )
        )

        channel_name = f"ticket-{base_name}-{rand_suffix}"

        # الصلاحيات
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=False
            ),

            interaction.user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True
            )
        }

        # إعطاء الأونر صلاحية الدخول
        owner_role = guild.get_role(OWNER_ROLE_ID)

        if owner_role:
            overwrites[owner_role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True
            )

        # إنشاء القناة
        try:
            channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                reason=f"Ticket opened by {interaction.user}"
            )

        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ لا أملك صلاحية إنشاء القنوات. تأكد من أن البوت يملك صلاحية **Manage Channels**.",
                ephemeral=True
            )
            return

        except Exception as e:
            print(f"[TICKET ERROR] {e}")

            await interaction.response.send_message(
                f"❌ حدث خطأ أثناء إنشاء التذكرة:\n`{e}`",
                ephemeral=True
            )
            return

        # رسالة التذكرة
        embed = discord.Embed(
            title="🎫 تذكرة جديدة",
            description=(
                f"يو {interaction.user.mention} \n\n"
                "اكتب مشكلتك أو استفسارك هنا، وسيتم الرد عليك من الإدارة.\n\n"
            ),
            color=discord.Color.blue()
        )

        file = None

        try:
            ticket_image = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "ticket.png"
            )

            if os.path.exists(ticket_image):
                file = discord.File(
                    ticket_image,
                    filename="ticket.png"
                )

                embed.set_image(
                    url="attachment://ticket.png"
                )

        except Exception as e:
            print(f"[TICKET IMAGE ERROR] {e}")

        delete_view = TicketDeleteView()

        try:
            if file:
                await channel.send(
                    embed=embed,
                    view=delete_view,
                    file=file
                )
            else:
                await channel.send(
                    embed=embed,
                    view=delete_view
                )

        except Exception as e:
            print(f"[TICKET MESSAGE ERROR] {e}")

            try:
                await channel.delete(
                    reason="Failed to send ticket message"
                )
            except:
                pass

            await interaction.response.send_message(
                f"❌ تم إنشاء التذكرة لكن حدث خطأ أثناء إرسال رسالتها:\n`{e}`",
                ephemeral=True
            )
            return

        # تأكيد فتح التذكرة
        await interaction.response.send_message(
            f"✅ تم فتح تذكرتك بنجاح: {channel.mention}",
            ephemeral=True
        )


class TicketDeleteView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="حذف",
        style=discord.ButtonStyle.danger,
        emoji="🗑️",
        custom_id="persistent_ticket_delete"
    )
    async def delete_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        owner_role = interaction.guild.get_role(OWNER_ROLE_ID)

        if owner_role is None or owner_role not in interaction.user.roles:
            await interaction.response.send_message(
                "❌ هذا الزر متاح للأونر فقط.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            "🗑️ سيتم حذف التذكرة...",
            ephemeral=True
        )

        try:
            await interaction.channel.delete(
                reason=f"Ticket deleted by {interaction.user}"
            )
        except discord.Forbidden:
            pass
        except Exception as e:
            print(f"[TICKET DELETE ERROR] {e}")


# ==========================================
# أمر إنشاء لوحة التذاكر
# ==========================================

@bot.command(name="تكت", aliases=["ticket", "تذكرة"])
@commands.has_role(OWNER_ROLE_ID)
@in_channel(TICKET_CHANNEL_ID)
async def ticket_command(ctx):

    try:
        await ctx.message.delete()
    except:
        pass

    embed = discord.Embed(
        title="🎫 نظام التذاكر",
        description=(
            "• اضغط الزر أدناه لفتح تذكرة.\n"
            "• فتح تكت بدون سبب يؤدي الى ميوت 1h."
        ),
        color=discord.Color.gold()
    )

    file = None

    try:
        ticket_image = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "ticket.png"
        )

        if os.path.exists(ticket_image):
            file = discord.File(
                ticket_image,
                filename="ticket.png"
            )

            embed.set_image(
                url="attachment://ticket.png"
            )

    except Exception as e:
        print(f"[TICKET PANEL IMAGE ERROR] {e}")

    view = TicketView()

    if file:
        await ctx.send(
            embed=embed,
            view=view,
            file=file
        )
    else:
        await ctx.send(
            embed=embed,
            view=view
        )


@ticket_command.error
async def ticket_command_error(ctx, error):

    if isinstance(error, commands.MissingRole):
        try:
            await ctx.message.delete()
        except:
            pass

        await ctx.send(
            "❌ هذا الأمر مخصص للأونر فقط.",
            delete_after=3
        )


# ==========================================
# 🤖 نظام الردود التلقائية (للاونر فقط) – يدعم المنشن والكلمات
# ==========================================

REPLIES_FILE = os.path.join(BASE_DIR, "replies.json")
REPLIES_REDIS_KEY = "bot_replies"
_next_id = 1

def _normalize_replies(data):
    """توحيد شكل بيانات الردود والتأكد من وجود الأقسام المطلوبة."""
    if not isinstance(data, dict):
        data = {}
    if not isinstance(data.get("member"), dict):
        data["member"] = {}
    if not isinstance(data.get("word"), list):
        data["word"] = []
    for uid, replies in list(data["member"].items()):
        if not isinstance(replies, list):
            data["member"][uid] = []
    return data

def load_replies():
    """
    تحميل الردود من Redis أولاً حتى لا تضيع عند إعادة نشر/تحديث ملف البوت.
    إذا لم توجد بيانات في Redis، نستخدم replies.json كنسخة توافق قديمة
    ثم نرفعها إلى Redis لتصبح هي النسخة الدائمة.
    """
    try:
        result = _redis_command("GET", REPLIES_REDIS_KEY)
        if result:
            return _normalize_replies(json.loads(result))
    except Exception as e:
        print(f"❌ تعذر تحميل الردود من Redis: {e}")

    if os.path.exists(REPLIES_FILE):
        try:
            with open(REPLIES_FILE, "r", encoding="utf-8") as f:
                data = _normalize_replies(json.load(f))
            try:
                _redis_command(
                    "SET",
                    REPLIES_REDIS_KEY,
                    json.dumps(data, ensure_ascii=False, indent=2),
                )
            except Exception as e:
                print(f"⚠️ تعذر ترحيل الردود إلى Redis: {e}")
            return data
        except Exception as e:
            print(f"❌ تعذر قراءة replies.json: {e}")

    return {"member": {}, "word": []}

def save_replies(data):
    """حفظ الردود في Redis بشكل دائم مع نسخة محلية احتياطية."""
    data = _normalize_replies(data)
    payload = json.dumps(data, ensure_ascii=False, indent=2)

    redis_saved = False
    try:
        redis_saved = _redis_command("SET", REPLIES_REDIS_KEY, payload) == "OK"
    except Exception as e:
        print(f"❌ تعذر حفظ الردود في Redis: {e}")

    try:
        with open(REPLIES_FILE, "w", encoding="utf-8") as f:
            f.write(payload)
        local_saved = True
    except Exception as e:
        print(f"❌ تعذر حفظ نسخة الردود المحلية: {e}")
        local_saved = False

    if not redis_saved and not local_saved:
        raise RuntimeError("تعذر حفظ الردود في Redis والملف المحلي.")
    return True

def generate_id():
    global _next_id
    max_id = 0
    # نبحث في جميع الردود
    for replies in replies_cache["member"].values():
        for r in replies:
            if r.get("id", 0) > max_id:
                max_id = r["id"]
    for r in replies_cache["word"]:
        if r.get("id", 0) > max_id:
            max_id = r["id"]
    _next_id = max_id + 1
    return _next_id

# متغير عام
replies_cache = load_replies()

# ==========================================
# نماذج الإدخال (Modals)
# ==========================================

class AddReplyModal(discord.ui.Modal, title="إضافة رد نصي (عند المنشن)"):
    user_id = discord.ui.TextInput(
        label="آيدي العضو",
        placeholder="أدخل الرقم",
        required=True,
        style=discord.TextStyle.short
    )
    reply_text = discord.ui.TextInput(
        label="النص الذي سيرده البوت",
        placeholder="أكتب الرد",
        required=True,
        style=discord.TextStyle.paragraph
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            uid = int(self.user_id.value.strip())
        except ValueError:
            await interaction.response.send_message("❌ الآيدي يجب أن يكون رقماً.", ephemeral=True)
            return
        text = self.reply_text.value.strip()
        if not text:
            await interaction.response.send_message("❌ النص لا يمكن أن يكون فارغاً.", ephemeral=True)
            return

        uid_str = str(uid)
        if uid_str not in replies_cache["member"]:
            replies_cache["member"][uid_str] = []
        new_reply = {"id": generate_id(), "type": "text", "value": text}
        replies_cache["member"][uid_str].append(new_reply)
        save_replies(replies_cache)
        await interaction.response.send_message(
            f"✅ تم إضافة رد نصي للعضو `{uid}` (الرد رقم {new_reply['id']})",
            ephemeral=True
        )

class AddReactionModal(discord.ui.Modal, title="إضافة رد رياكشن (عند المنشن)"):
    user_id = discord.ui.TextInput(
        label="آيدي العضو",
        placeholder="أدخل الرقم",
        required=True,
        style=discord.TextStyle.short
    )
    emoji_id = discord.ui.TextInput(
        label="آيدي الإيموجي أو الإيموجي العادي",
        placeholder="مثال: <:اسم الايموجي:ايدي الايموجي> أو 👍",
        required=True,
        style=discord.TextStyle.short
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            uid = int(self.user_id.value.strip())
        except ValueError:
            await interaction.response.send_message("❌ الآيدي يجب أن يكون رقماً.", ephemeral=True)
            return
        emoji = self.emoji_id.value.strip()
        if not emoji:
            await interaction.response.send_message("❌ الإيموجي لا يمكن أن يكون فارغاً.", ephemeral=True)
            return

        uid_str = str(uid)
        if uid_str not in replies_cache["member"]:
            replies_cache["member"][uid_str] = []
        new_reply = {"id": generate_id(), "type": "reaction", "value": emoji}
        replies_cache["member"][uid_str].append(new_reply)
        save_replies(replies_cache)
        await interaction.response.send_message(
            f"✅ تم إضافة رد رياكشن للعضو `{uid}` (الرد رقم {new_reply['id']})",
            ephemeral=True
        )

class AddWordReplyModal(discord.ui.Modal, title="إضافة رد كلمة (نصي)"):
    trigger = discord.ui.TextInput(
        label="الكلمة المطلوبة",
        placeholder="مثال: محمد",
        required=True,
        style=discord.TextStyle.short
    )
    reply_text = discord.ui.TextInput(
        label="الرد النصي",
        placeholder="أكتب الرد",
        required=True,
        style=discord.TextStyle.paragraph
    )

    async def on_submit(self, interaction: discord.Interaction):
        trigger = self.trigger.value.strip().lower()
        reply = self.reply_text.value.strip()
        if not trigger or not reply:
            await interaction.response.send_message("❌ لا يمكن ترك أي حقل فارغاً.", ephemeral=True)
            return
        new_reply = {"id": generate_id(), "type": "text", "trigger": trigger, "value": reply}
        replies_cache["word"].append(new_reply)
        save_replies(replies_cache)
        await interaction.response.send_message(
            f"✅ تم إضافة رد كلمة نصي للكلمة `{trigger}` (الرد رقم {new_reply['id']})",
            ephemeral=True
        )

class AddWordReactionModal(discord.ui.Modal, title="إضافة رد كلمة (رياكشن)"):
    trigger = discord.ui.TextInput(
        label="الكلمة المطلوبة",
        placeholder="مثال: سلام",
        required=True,
        style=discord.TextStyle.short
    )
    emoji_id = discord.ui.TextInput(
        label="الإيموجي (آيدي أو عادي)",
        placeholder="مثال: <:اسم الايموجي:ايدي الايموجي> أو 👍",
        required=True,
        style=discord.TextStyle.short
    )

    async def on_submit(self, interaction: discord.Interaction):
        trigger = self.trigger.value.strip().lower()
        emoji = self.emoji_id.value.strip()
        if not trigger or not emoji:
            await interaction.response.send_message("❌ لا يمكن ترك أي حقل فارغاً.", ephemeral=True)
            return
        new_reply = {"id": generate_id(), "type": "reaction", "trigger": trigger, "value": emoji}
        replies_cache["word"].append(new_reply)
        save_replies(replies_cache)
        await interaction.response.send_message(
            f"✅ تم إضافة رد كلمة رياكشن للكلمة `{trigger}` (الرد رقم {new_reply['id']})",
            ephemeral=True
        )

# ==========================================
# تعديل / حذف الردود
# ==========================================

class EditReplyModal(discord.ui.Modal, title="تعديل الرد"):
    def __init__(self, reply_id: int, current_value: str, reply_type: str, category: str, extra=None):
        super().__init__()
        self.reply_id = reply_id
        self.category = category  # "member" أو "word"
        self.extra = extra  # في حالة member نحتاج uid
        self.reply_type = reply_type

        if category == "word":
            # نضيف حقل الكلمة أيضاً
            self.trigger_input = discord.ui.TextInput(
                label="الكلمة المطلوبة",
                default=extra,
                required=True,
                style=discord.TextStyle.short
            )
            self.add_item(self.trigger_input)

        self.new_value = discord.ui.TextInput(
            label="القيمة الجديدة",
            default=current_value,
            required=True,
            style=discord.TextStyle.paragraph if reply_type == "text" else discord.TextStyle.short
        )
        self.add_item(self.new_value)

    async def on_submit(self, interaction: discord.Interaction):
        new_val = self.new_value.value.strip()
        if not new_val:
            await interaction.response.send_message("❌ القيمة لا يمكن أن تكون فارغة.", ephemeral=True)
            return

        if self.category == "member":
            uid = self.extra
            if uid in replies_cache["member"]:
                for reply in replies_cache["member"][uid]:
                    if reply["id"] == self.reply_id:
                        reply["value"] = new_val
                        save_replies(replies_cache)
                        await interaction.response.send_message(f"✅ تم تحديث الرد رقم {self.reply_id} بنجاح.", ephemeral=True)
                        return
            await interaction.response.send_message("❌ لم يتم العثور على الرد.", ephemeral=True)
        else:  # word
            new_trigger = self.trigger_input.value.strip().lower() if hasattr(self, 'trigger_input') else None
            for reply in replies_cache["word"]:
                if reply["id"] == self.reply_id:
                    reply["value"] = new_val
                    if new_trigger:
                        reply["trigger"] = new_trigger
                    save_replies(replies_cache)
                    await interaction.response.send_message(f"✅ تم تحديث الرد رقم {self.reply_id} بنجاح.", ephemeral=True)
                    return
            await interaction.response.send_message("❌ لم يتم العثور على الرد.", ephemeral=True)

class DeleteReplyView(discord.ui.View):
    def __init__(self, reply_id: int, category: str, extra=None):
        super().__init__(timeout=60)
        self.reply_id = reply_id
        self.category = category
        self.extra = extra

    @discord.ui.button(label="نعم، احذف", style=discord.ButtonStyle.danger)
    async def confirm_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.category == "member":
            uid = self.extra
            if uid in replies_cache["member"]:
                old_len = len(replies_cache["member"][uid])
                replies_cache["member"][uid] = [r for r in replies_cache["member"][uid] if r["id"] != self.reply_id]
                if len(replies_cache["member"][uid]) == 0:
                    del replies_cache["member"][uid]
                if len(replies_cache["member"][uid]) != old_len:
                    save_replies(replies_cache)
                    await interaction.response.send_message(f"✅ تم حذف الرد رقم {self.reply_id} بنجاح.", ephemeral=True)
                    return
        else:  # word
            old_len = len(replies_cache["word"])
            replies_cache["word"] = [r for r in replies_cache["word"] if r["id"] != self.reply_id]
            if len(replies_cache["word"]) != old_len:
                save_replies(replies_cache)
                await interaction.response.send_message(f"✅ تم حذف الرد رقم {self.reply_id} بنجاح.", ephemeral=True)
                return
        await interaction.response.send_message("❌ لم يتم العثور على الرد.", ephemeral=True)
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)

    @discord.ui.button(label="إلغاء", style=discord.ButtonStyle.secondary)
    async def cancel_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("تم الإلغاء.", ephemeral=True)
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)

# ==========================================
# القائمة المنسدلة لعرض جميع الردود
# ==========================================

class RepliesSelect(discord.ui.Select):
    def __init__(self):
        options = []
        # ردود الأعضاء
        for uid, replies in replies_cache["member"].items():
            for reply in replies:
                label = f"👤 عضو {uid}"
                desc = f"{reply['type']}: {reply['value'][:30]} (id:{reply['id']})"
                options.append(discord.SelectOption(
                    label=label,
                    value=f"member|{uid}|{reply['id']}",
                    description=desc
                ))
        # ردود الكلمات
        for reply in replies_cache["word"]:
            label = f" كلمة: {reply['trigger']}"
            desc = f"{reply['type']}: {reply['value'][:30]} (id:{reply['id']})"
            options.append(discord.SelectOption(
                label=label,
                value=f"word|{reply['id']}",
                description=desc
            ))
        if not options:
            options.append(discord.SelectOption(
                label="لا توجد ردود",
                value="none",
                description="أضف رداً جديداً"
            ))
        super().__init__(
            placeholder="اختر رداً لتعديله أو حذفه...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message("لا توجد ردود لعرضها.", ephemeral=True)
            return

        parts = self.values[0].split("|")
        if parts[0] == "member":
            _, uid, rid = parts
            rid = int(rid)
            reply = None
            if uid in replies_cache["member"]:
                for r in replies_cache["member"][uid]:
                    if r["id"] == rid:
                        reply = r
                        break
            if not reply:
                await interaction.response.send_message("❌ هذا الرد غير موجود.", ephemeral=True)
                return
            embed = discord.Embed(
                title=f"✏️ رد العضو {uid} - رقم {rid}",
                description=f"**النوع:** {reply['type']}\n**القيمة:** {reply['value']}",
                color=discord.Color.blue()
            )
            view = discord.ui.View()
            view.add_item(EditReplyButton(rid, reply["value"], reply["type"], "member", extra=uid))
            view.add_item(DeleteReplyButton(rid, "member", extra=uid))
            await interaction.response.edit_message(embed=embed, view=view)

        elif parts[0] == "word":
            _, rid = parts
            rid = int(rid)
            reply = None
            for r in replies_cache["word"]:
                if r["id"] == rid:
                    reply = r
                    break
            if not reply:
                await interaction.response.send_message("❌ هذا الرد غير موجود.", ephemeral=True)
                return
            embed = discord.Embed(
                title=f"✏️ رد كلمة: {reply['trigger']} - رقم {rid}",
                description=f"**النوع:** {reply['type']}\n**القيمة:** {reply['value']}",
                color=discord.Color.blue()
            )
            view = discord.ui.View()
            view.add_item(EditReplyButton(rid, reply["value"], reply["type"], "word", extra=reply["trigger"]))
            view.add_item(DeleteReplyButton(rid, "word"))
            await interaction.response.edit_message(embed=embed, view=view)

class EditReplyButton(discord.ui.Button):
    def __init__(self, reply_id: int, current_value: str, reply_type: str, category: str, extra=None):
        super().__init__(label="✏️ تعديل", style=discord.ButtonStyle.primary)
        self.reply_id = reply_id
        self.current_value = current_value
        self.reply_type = reply_type
        self.category = category
        self.extra = extra

    async def callback(self, interaction: discord.Interaction):
        modal = EditReplyModal(self.reply_id, self.current_value, self.reply_type, self.category, self.extra)
        await interaction.response.send_modal(modal)

class DeleteReplyButton(discord.ui.Button):
    def __init__(self, reply_id: int, category: str, extra=None):
        super().__init__(label="🗑️ حذف", style=discord.ButtonStyle.danger)
        self.reply_id = reply_id
        self.category = category
        self.extra = extra

    async def callback(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="⚠️ تأكيد الحذف",
            description=f"هل أنت متأكد من حذف الرد رقم {self.reply_id}؟",
            color=discord.Color.red()
        )
        view = DeleteReplyView(self.reply_id, self.category, self.extra)
        await interaction.response.edit_message(embed=embed, view=view)

# ==========================================
# اللوحة الرئيسية مع خيارات الإضافة
# ==========================================

class RepliesManagementView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(RepliesSelect())

    @discord.ui.button(label="➕ إضافة رد", style=discord.ButtonStyle.primary)
    async def add_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="اختر نوع الرد",
            description="اختر أحد الخيارات بالأسفل",
            color=discord.Color.blue()
        )
        view = AddChoiceView()
        await interaction.response.edit_message(embed=embed, view=view)

class AddChoiceView(discord.ui.View):
    @discord.ui.button(label="📝 رد نصي (عند المنشن)", style=discord.ButtonStyle.success)
    async def text_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddReplyModal())

    @discord.ui.button(label="👍 رد رياكشن (عند المنشن)", style=discord.ButtonStyle.success)
    async def reaction_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddReactionModal())

    @discord.ui.button(label="📝 رد كلمة (نصي)", style=discord.ButtonStyle.primary)
    async def word_text_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddWordReplyModal())

    @discord.ui.button(label="👍 رد كلمة (رياكشن)", style=discord.ButtonStyle.primary)
    async def word_reaction_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddWordReactionModal())

    @discord.ui.button(label="🔙 رجوع", style=discord.ButtonStyle.secondary)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="⚙️ لوحة إدارة الردود التلقائية",
            description="• اختر رداً من القائمة المنسدلة لتعديله أو حذفه.\n• اضغط **إضافة رد** لإنشاء رد جديد.",
            color=discord.Color.gold()
        )
        view = RepliesManagementView()
        await interaction.response.edit_message(embed=embed, view=view)

# ==========================================
# الأمر الرئيسي
# ==========================================

@bot.command(name="تعديل")
@commands.has_role(OWNER_ROLE_ID)
@in_channel(AMENDMENTS_CHANNEL_ID)
async def manage_replies(ctx):
    embed = discord.Embed(
        title="⚙️ لوحة إدارة الردود التلقائية",
        description="• اختر رداً من القائمة المنسدلة لتعديله أو حذفه.\n• اضغط **إضافة رد** لإنشاء رد جديد.",
        color=discord.Color.gold()
    )
    view = RepliesManagementView()
    await ctx.send(embed=embed, view=view)

# ==========================================
# مستمع الرسائل – ينفذ الردود
# ==========================================
async def enlarge_and_send(channel, url, type_str):
    """تحميل صورة من رابط، تكبيرها 2x ، وإرسالها كملف."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return
                img_data = await resp.read()
                img = Image.open(io.BytesIO(img_data))
                
                new_size = (img.width * 2, img.height * 2)
                buf = io.BytesIO()

                # التحقق مما إذا كانت الصورة متحركة (GIF)
                if getattr(img, "is_animated", False):
                    from PIL import ImageSequence
                    frames = []
                    for frame in ImageSequence.Iterator(img):
                        resized_frame = frame.convert("RGBA").resize(new_size, Image.Resampling.LANCZOS)
                        frames.append(resized_frame)
                    
                    frames[0].save(
                        buf, 
                        format='GIF', 
                        save_all=True, 
                        append_images=frames[1:], 
                         loop=img.info.get('loop', 0), 
                        duration=img.info.get('duration', 40),
                        disposal=2
                    )
                    buf.seek(0)
                    file = discord.File(buf, filename=f"enlarged_{type_str}.gif")
                
                else:
                    # معالجة الصور الثابتة العادية وحفظها كـ PNG
                    img_resized = img.resize(new_size, Image.Resampling.LANCZOS)
                    img_resized.save(buf, format='PNG')
                    buf.seek(0)
                    file = discord.File(buf, filename=f"enlarged_{type_str}.png")
                    img_resized.close()

                await channel.send(file=file)
                img.close()
                
    except Exception as e:
        print(f"[ENLARGE ERROR] {type_str}: {e}")



# ==========================================
# 🎡 لعبة الروليت الجماعية
# ==========================================

# كل لعبة مستقلة برسالتها ومبلغها، وتمنع مشاركة العضو في أكثر من لعبة.
ACTIVE_GROUP_ROULETTE = {}
ACTIVE_GROUP_ROULETTE_USERS = set()

GROUP_ROULETTE_MAX_PLAYERS = 10
GROUP_ROULETTE_MIN_PLAYERS = 2
GROUP_ROULETTE_TIMEOUT = 600


def _roulette_number(text):
    """تحويل مبلغ الأمر إلى رقم مع دعم الفواصل العربية والإنجليزية."""
    if text is None:
        return None
    value = str(text).strip().replace(",", "").replace("٬", "").replace(" ", "")
    if not value.isdigit():
        return None
    amount = int(value)
    return amount if amount > 0 else None


_ROULETTE_BG_CACHE = None
_ROULETTE_BG_LOCK = Lock()


def _open_roulette_background(size):
    """فتح خلفية الروليت وقصّها لتناسب بطاقة الـ embed مع طبقة تعتيم خفيفة."""
    global _ROULETTE_BG_CACHE
    if _ROULETTE_BG_CACHE is not None:
        return _ROULETTE_BG_CACHE.copy()

    with _ROULETTE_BG_LOCK:
        if _ROULETTE_BG_CACHE is None:
            try:
                image = Image.open(RUSSIAN_ROULETTE_BACKGROUND).convert("RGBA")
                image = image.resize(size, Image.Resampling.LANCZOS)
                overlay = Image.new("RGBA", size, (5, 8, 15, 105))
                _ROULETTE_BG_CACHE = Image.alpha_composite(image, overlay)
            except Exception as e:
                print(f"⚠️ تعذر فتح خلفية الروليت: {e}")
                _ROULETTE_BG_CACHE = Image.new("RGBA", size, (13, 17, 29, 255))
        return _ROULETTE_BG_CACHE.copy()


def draw_group_roulette_lobby(amount, players, host):
    """بطاقة Lobby جميلة تحتوي على عدد اللاعبين والتعليمات والأسماء."""
    width, height = 1200, 700
    base = _open_roulette_background((width, height))
    d = ImageDraw.Draw(base)

    # زخارف ذهبية.
    for r in (530, 500, 470):
        d.ellipse(
            (width//2-r, 350-r, width//2+r, 350+r),
            outline=(184, 145, 55, 35),
            width=2,
        )

    # العنوان.
    d.rounded_rectangle(
        (70, 35, width-70, 145),
        radius=30,
        fill=(26, 31, 48, 245),
        outline=(232, 198, 106, 255),
        width=4,
    )
    d.text(
        (width//2, 88),
        "🎡 الروليت الجماعية",
        font=_font(52),
        fill=(232, 198, 106, 255),
        anchor="mm",
    )

    # مربع اللاعبين.
    d.rounded_rectangle(
        (820, 175, 1130, 285),
        radius=24,
        fill=(10, 13, 22, 235),
        outline=(232, 198, 106, 210),
        width=3,
    )
    d.text(
        (975, 213),
        f"{len(players)} / {GROUP_ROULETTE_MAX_PLAYERS}",
        font=_font(46),
        fill=(255, 255, 255, 255),
        anchor="mm",
    )
    d.text(
        (975, 258),
        "عدد اللاعبين",
        font=_font(22),
        fill=(180, 184, 198, 255),
        anchor="mm",
    )

    # معلومات الرهان وصاحب اللعبة.
    d.rounded_rectangle(
        (70, 175, 790, 285),
        radius=24,
        fill=(26, 31, 48, 235),
        outline=(80, 91, 120, 200),
        width=2,
    )
    prize_text = f"الجائزة: {amount:,} طولار" if amount > 0 else "بدون جائزة"
    d.text(
        (430, 212),
        prize_text,
        font=_fit_font(prize_text, 620, 34, 22),
        fill=(232, 198, 106, 255),
        anchor="mm",
    )
    d.text(
        (430, 258),
        f"صاحب اللعبة: {host.display_name[:28]}",
        font=_fit_font(f"صاحب اللعبة: {host.display_name[:28]}", 620, 24, 18),
        fill=(220, 223, 233, 255),
        anchor="mm",
    )

    # التعليمات.
    d.rounded_rectangle(
        (70, 315, 1130, 455),
        radius=26,
        fill=(7, 10, 18, 205),
        outline=(70, 82, 110, 180),
        width=2,
    )
    d.text(
        (600, 350),
        "اضغط على الأزرار للدخول",
        font=_font(35),
        fill=(255, 255, 255, 255),
        anchor="mm",
    )
    d.text(
        (600, 405),
        "يتم اختيار أحد اللاعبين عشوائياً لطرد لاعب من اختياره وهكذا",
        font=_fit_font(
            "يتم اختيار أحد اللاعبين عشوائياً لطرد لاعب من اختياره وهكذا",
            950, 30, 19
        ),
        fill=(194, 199, 214, 255),
        anchor="mm",
    )

    # أسماء اللاعبين في آخر الصورة.
    d.text(
        (600, 490),
        "اللاعبون المشاركون",
        font=_font(28),
        fill=(232, 198, 106, 255),
        anchor="mm",
    )

    slots = []
    for i in range(GROUP_ROULETTE_MAX_PLAYERS):
        row = i // 5
        col = i % 5
        x1 = 70 + col * 210
        y1 = 520 + row * 75
        x2 = x1 + 195
        y2 = y1 + 58
        slots.append((x1, y1, x2, y2))
        if i < len(players):
            member = players[i]
            fill = (34, 42, 62, 245)
            outline = (232, 198, 106, 190)
            name = member.display_name[:20]
        else:
            fill = (20, 24, 36, 180)
            outline = (55, 62, 80, 130)
            name = "— فارغ —"
        d.rounded_rectangle((x1, y1, x2, y2), radius=16, fill=fill, outline=outline, width=2)
        d.text(
            ((x1+x2)//2, (y1+y2)//2),
            name,
            font=_fit_font(name, 170, 22, 15),
            fill=(255, 255, 255, 255) if i < len(players) else (105, 111, 128, 255),
            anchor="mm",
        )

    out = io.BytesIO()
    base.save(out, format="PNG", optimize=False, compress_level=3)
    out.seek(0)
    base.close()
    return out


async def _get_cached_roulette_lobby(amount, players, host):
    """إرجاع صورة Lobby من الكاش، وإن لم توجد تُرسم مرة واحدة فقط."""
    players_key = tuple((int(m.id), str(m.display_name)) for m in players)
    key = (int(amount), players_key, int(host.id), str(host.display_name))
    cached = _ROULETTE_LOBBY_CACHE.get(key)
    if cached is not None:
        return io.BytesIO(cached)

    img_buf = None
    try:
        img_buf = await _run_bg(draw_group_roulette_lobby, amount, players, host)
        data = img_buf.getvalue()
        _ROULETTE_LOBBY_CACHE.set(key, data)
        return io.BytesIO(data)
    finally:
        if img_buf is not None:
            img_buf.close()


async def _get_cached_roulette_wheel(players, selected_index):
    """كاش لصور عجلة الروليت؛ نفس اللاعبين ونفس المؤشر يعيدان نفس GIF."""
    players_key = tuple((int(m.id), str(m.display_name)) for m in players)
    key = (players_key, int(selected_index))
    cached = _ROULETTE_WHEEL_CACHE.get(key)
    if cached is not None:
        return io.BytesIO(cached)

    img_buf = None
    try:
        img_buf = await _run_bg(generate_group_roulette_wheel, players, selected_index)
        data = img_buf.getvalue()
        _ROULETTE_WHEEL_CACHE.set(key, data)
        return io.BytesIO(data)
    finally:
        if img_buf is not None:
            img_buf.close()


def generate_group_roulette_wheel(players, winner_index):
    """إنشاء GIF لعجلة متعددة القطاعات، مع توجيه السهم للفائز."""
    size = 720
    center = (size // 2, size // 2)
    radius = 285
    n = len(players)
    span = 360.0 / n
    frames = []
    total_frames = 34

    # مركز القطاع الفائز النهائي تحت السهم العلوي (270 درجة في PIL).
    winner_center = winner_index * span + span / 2
    target_offset = (270.0 - winner_center) % 360.0
    total_rotation = 6 * 360 + target_offset

    # ألوان أفتح قليلاً من التصميم السابق مع الحفاظ على التباين.
    palette = [
        (70, 125, 180, 255),
        (190, 82, 98, 255),
        (70, 145, 120, 255),
        (145, 105, 180, 255),
        (190, 135, 70, 255),
        (82, 135, 155, 255),
    ]

    for i in range(total_frames):
        t = i / (total_frames - 1)
        eased = 1 - (1 - t) ** 3
        rotation = total_rotation * eased
        frame = _open_roulette_background((size, size))
        d = ImageDraw.Draw(frame)

        # هالة خلف العجلة.
        d.ellipse(
            (center[0]-radius-18, center[1]-radius-18,
             center[0]+radius+18, center[1]+radius+18),
            fill=(17, 22, 35, 255),
            outline=(232, 198, 106, 150),
            width=5,
        )

        for j, member in enumerate(players):
            start_angle = rotation + j * span
            end_angle = start_angle + span
            box = (
                center[0]-radius, center[1]-radius,
                center[0]+radius, center[1]+radius,
            )
            d.pieslice(
                box,
                start_angle,
                end_angle,
                fill=palette[j % len(palette)],
                outline=(232, 198, 106, 210),
                width=3,
            )

            mid = math.radians(start_angle + span / 2)
            text_radius = 185 if n <= 6 else 205
            x = center[0] + text_radius * math.cos(mid)
            y = center[1] + text_radius * math.sin(mid)
            label = member.display_name[:12]
            d.text(
                (x, y),
                label,
                font=_fit_font(label, 125 if n > 7 else 155, 23 if n <= 6 else 19, 13),
                fill=(255, 255, 255, 255),
                anchor="mm",
                stroke_width=2,
                stroke_fill=(0, 0, 0, 180),
            )

        # المركز والحلقة الداخلية.
        d.ellipse(
            (center[0]-70, center[1]-70, center[0]+70, center[1]+70),
            fill=(12, 16, 27, 255),
            outline=(232, 198, 106, 255),
            width=6,
        )
        d.text(
            center,
            "🎡",
            font=_font(42),
            fill=(232, 198, 106, 255),
            anchor="mm",
        )

        # السهم الثابت بالأعلى.
        d.polygon(
            [(center[0]-26, 18), (center[0]+26, 18), (center[0], 70)],
            fill=(232, 198, 106, 255),
            outline=(255, 235, 170, 255),
        )
        frames.append(frame.convert("P", palette=Image.Palette.ADAPTIVE))

    out = io.BytesIO()
    frames[0].save(
        out,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=55,
        loop=0,
        disposal=2,
    )
    out.seek(0)
    for frame in frames:
        frame.close()
    return out


class GroupRouletteLobbyView(discord.ui.View):
    def __init__(self, game_id):
        # التسجيل يبقى متاحاً، لكن إذا لم يدخل أي لاعب إضافي خلال أول 20 ثانية
        # تُلغى اللعبة. دخول لاعب واحد إضافي يكفي لإلغاء هذا الشرط.
        super().__init__(timeout=GROUP_ROULETTE_TIMEOUT)
        self.game_id = game_id
        self.message = None
        self.no_join_task = asyncio.create_task(self._cancel_if_no_join())

    def _game(self):
        return ACTIVE_GROUP_ROULETTE.get(self.game_id)

    async def _cancel_if_no_join(self):
        try:
            await asyncio.sleep(20)
            game = self._game()
            if not game or game["started"]:
                return
            # صاحب اللعبة محسوب كلاعب أول، لذلك نبحث عن لاعب إضافي.
            if len(game["players"]) > 1:
                return

            ACTIVE_GROUP_ROULETTE.pop(self.game_id, None)
            if game["amount"] > 0:
                add_balance(game["host"].id, game["amount"])
            for member in game["players"]:
                ACTIVE_GROUP_ROULETTE_USERS.discard(member.id)

            if self.message:
                try:
                    content = "⏰ تم إلغاء الروليت لعدم دخول أي لاعب خلال 20 ثانية."
                    if game["amount"] > 0:
                        content += " وتمت إعادة مبلغ الجائزة لصاحب اللعبة."
                    await self.message.edit(
                        content=content,
                        attachments=[],
                        view=None,
                    )
                except Exception:
                    pass
            super().stop()
        except asyncio.CancelledError:
            pass

    async def _refresh(self, interaction):
        game = self._game()
        if not game:
            return
        img_buf = None
        try:
            img_buf = await _get_cached_roulette_lobby(
                game["amount"],
                game["players"],
                game["host"],
            )
            file = discord.File(img_buf, filename="group_roulette.png")
            await interaction.message.edit(
                attachments=[file],
                view=self,
                content=None,
            )
        finally:
            if img_buf is not None:
                img_buf.close()

    @discord.ui.button(label="دخول", style=discord.ButtonStyle.success, emoji="🎟️")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = self._game()
        if not game:
            return await interaction.response.send_message("❌ انتهت اللعبة.", ephemeral=True)

        uid = interaction.user.id
        if uid in game["players"]:
            return await interaction.response.send_message("⚠️ أنت داخل اللعبة بالفعل.", ephemeral=True)
        if len(game["players"]) >= GROUP_ROULETTE_MAX_PLAYERS:
            return await interaction.response.send_message("❌ اللعبة مكتملة (10/10).", ephemeral=True)
        if uid in ACTIVE_GROUP_ROULETTE_USERS:
            return await interaction.response.send_message("❌ أنت مشارك في لعبة روليت أخرى بالفعل.", ephemeral=True)

        game["players"].append(interaction.user)
        ACTIVE_GROUP_ROULETTE_USERS.add(uid)
        await interaction.response.defer()
        await self._refresh(interaction)

    @discord.ui.button(label="خروج", style=discord.ButtonStyle.secondary, emoji="🚪")
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = self._game()
        if not game:
            return await interaction.response.send_message("❌ انتهت اللعبة.", ephemeral=True)

        uid = interaction.user.id
        if uid not in [m.id for m in game["players"]]:
            return await interaction.response.send_message("⚠️ أنت لست داخل اللعبة.", ephemeral=True)
        if game["started"]:
            return await interaction.response.send_message("❌ لا يمكن الخروج بعد بدء اللعبة.", ephemeral=True)

        game["players"] = [m for m in game["players"] if m.id != uid]
        ACTIVE_GROUP_ROULETTE_USERS.discard(uid)

        # صاحب اللعبة إذا خرج: إلغاء واسترجاع المبلغ.
        if uid == game["host"].id:
            remove_game = ACTIVE_GROUP_ROULETTE.pop(self.game_id, None)
            if remove_game:
                if game["amount"] > 0:
                    add_balance(game["host"].id, game["amount"])
                for member in game["players"]:
                    ACTIVE_GROUP_ROULETTE_USERS.discard(member.id)
            await interaction.response.edit_message(
                content="❌ تم إلغاء الروليت لأن صاحب اللعبة خرج، وتمت إعادة الجائزة له.",
                attachments=[],
                view=None,
            )
            self.stop()
            return

        await interaction.response.defer()
        await self._refresh(interaction)

    @discord.ui.button(label="بدء اللعبة", style=discord.ButtonStyle.primary, emoji="🎡")
    async def start_game(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = self._game()
        if not game:
            return await interaction.response.send_message("❌ انتهت اللعبة.", ephemeral=True)
        if interaction.user.id != game["host"].id:
            return await interaction.response.send_message("❌ صاحب اللعبة فقط يستطيع البدء.", ephemeral=True)
        if len(game["players"]) < GROUP_ROULETTE_MIN_PLAYERS:
            return await interaction.response.send_message(
                f"❌ يجب دخول {GROUP_ROULETTE_MIN_PLAYERS} لاعبين على الأقل.", ephemeral=True
            )
        if game["started"]:
            return await interaction.response.send_message("⚠️ اللعبة بدأت بالفعل.", ephemeral=True)

        game["started"] = True
        game["round"] = 0
        game["message"] = interaction.message
        await interaction.response.defer()

        view = GroupRouletteRoundView(self.game_id)
        img_buf = None
        try:
            # نختار أول لاعب عشوائياً ليبدأ دورة الطرد.
            selected = random.choice(game["players"])
            game["selected_id"] = selected.id
            embed = discord.Embed(
                title="🎡 الروليت الجماعية",
                description=(
                    f"🎯 **يا {selected.mention}** اختر لاعباً لطرده أو اضغط **عشوائي**.\n\n"
                    + (
                        f"💰 الجائزة: **{game['amount']:,} طولار**\n"
                        if game["amount"] > 0
                        else "🎁 **بدون جائزة**\n"
                    )
                    + f"👥 المتبقون: **{len(game['players'])}**"
                ),
                color=discord.Color.from_rgb(184, 145, 55),
            )
            selected_index = game["players"].index(selected)
            # إذا بدأ اللعب بلاعبين فقط، العجلة تختار الفائز مباشرة.
            if len(game["players"]) == 2:
                winner_index = random.randrange(2)
                winner = game["players"][winner_index]
                await GroupRouletteRoundView.finish_game(
                    interaction, self.game_id, winner, winner_index
                )
                self.stop()
                return

            img_buf = await _get_cached_roulette_wheel(
                game["players"],
                selected_index,
            )
            file = discord.File(img_buf, filename="roulette_wheel.gif")
            embed.set_image(url="attachment://roulette_wheel.gif")

            # عند بدء اللعبة نترك رسالة التسجيل كما هي، ونرسل رسالة جديدة للجولة.
            try:
                await interaction.message.edit(view=None)
            except Exception:
                pass

            new_message = await interaction.followup.send(
                embed=embed,
                file=file,
                view=view,
                wait=True,
            )
            view.message = new_message
            game["message"] = new_message
        finally:
            if img_buf is not None:
                img_buf.close()

        self.stop()

    async def on_timeout(self):
        game = self._game()
        if not game or game["started"]:
            return
        ACTIVE_GROUP_ROULETTE.pop(self.game_id, None)
        if game["amount"] > 0:
            add_balance(game["host"].id, game["amount"])
        for member in game["players"]:
            ACTIVE_GROUP_ROULETTE_USERS.discard(member.id)
        if self.message:
            try:
                await self.message.edit(
                    content="⏰ انتهى وقت التسجيل، وتمت إعادة مبلغ الجائزة لصاحب اللعبة.",
                    attachments=[],
                    view=None,
                )
            except Exception:
                pass


class GroupRouletteKickSelect(discord.ui.Select):
    def __init__(self, game_id):
        self.game_id = game_id
        game = ACTIVE_GROUP_ROULETTE.get(game_id)
        players = game["players"] if game else []
        options = [
            discord.SelectOption(
                label=member.display_name[:100],
                value=str(member.id),
                description="طرد هذا اللاعب",
            )
            for member in players
        ]
        if not options:
            options = [discord.SelectOption(label="لا يوجد لاعبون", value="none")]
        super().__init__(
            placeholder="اختر لاعباً لطرده...",
            min_values=1,
            max_values=1,
            options=options[:25],
        )

    async def callback(self, interaction: discord.Interaction):
        game = ACTIVE_GROUP_ROULETTE.get(self.game_id)
        if not game or not game["started"]:
            return await interaction.response.send_message("❌ اللعبة غير متاحة.", ephemeral=True)

        if interaction.user.id != game["selected_id"]:
            return await interaction.response.send_message(
                "❌ هذا الدور ليس لك.", ephemeral=True
            )

        value = self.values[0]
        if value == "none":
            return await interaction.response.send_message("❌ لا يوجد لاعب للاختيار.", ephemeral=True)

        target_id = int(value)
        if target_id == game["selected_id"]:
            return await interaction.response.send_message(
                "❌ لا يمكنك طرد نفسك.", ephemeral=True
            )

        target = next((m for m in game["players"] if m.id == target_id), None)
        if not target:
            return await interaction.response.send_message("❌ اللاعب لم يعد داخل اللعبة.", ephemeral=True)

        await interaction.response.defer()
        await GroupRouletteRoundView.eliminate_and_continue(
            interaction,
            self.game_id,
            target,
        )


class GroupRouletteRoundView(discord.ui.View):
    def __init__(self, game_id):
        super().__init__(timeout=GROUP_ROULETTE_TIMEOUT)
        self.game_id = game_id
        self.message = None
        self.add_item(GroupRouletteKickSelect(game_id))

    @staticmethod
    async def eliminate_and_continue(interaction, game_id, target):
        game = ACTIVE_GROUP_ROULETTE.get(game_id)
        if not game:
            return

        game["players"] = [m for m in game["players"] if m.id != target.id]
        ACTIVE_GROUP_ROULETTE_USERS.discard(target.id)
        game["round"] += 1

        # عند بقاء لاعبين، العجلة تختار الفائز تلقائياً.
        if len(game["players"]) <= 2:
            winner_index = random.randrange(len(game["players"]))
            winner = game["players"][winner_index]
            await GroupRouletteRoundView.finish_game(interaction, game_id, winner, winner_index)
            return

        # اختيار لاعب جديد عشوائياً للدور التالي.
        selected = random.choice(game["players"])
        game["selected_id"] = selected.id

        view = GroupRouletteRoundView(game_id)
        embed = discord.Embed(
            title="🎡 الروليت الجماعية",
            description=(
                f"🎯 **يا {selected.mention}** اختر أحداً لطرده أو اختر **عشوائياً**.\n\n"
                + (
                    f"💰 الجائزة: **{game['amount']:,} طولار**\n"
                    if game["amount"] > 0
                    else "🎁 **بدون جائزة**\n"
                )
                + f"👥 المتبقون: **{len(game['players'])}**"
            ),
            color=discord.Color.from_rgb(184, 145, 55),
        )
        # العجلة تعرض اختيار اللاعب الذي حصل على الدور، ثم تتوقف عند اسمه.
        selected_index = game["players"].index(selected)
        img_buf = None
        try:
            img_buf = await _get_cached_roulette_wheel(
                game["players"],
                selected_index,
            )
            file = discord.File(img_buf, filename="roulette_wheel.gif")
            embed.set_image(url="attachment://roulette_wheel.gif")

            # كل دور جديد يظهر في رسالة مستقلة بدلاً من تعديل رسالة الدور السابق.
            try:
                await interaction.message.edit(view=None)
            except Exception:
                pass

            new_message = await interaction.followup.send(
                embed=embed,
                file=file,
                view=view,
                wait=True,
            )
            view.message = new_message
            game["message"] = new_message
        finally:
            if img_buf is not None:
                img_buf.close()

    @discord.ui.button(label="عشوائي", style=discord.ButtonStyle.success, emoji="🎲")
    async def random_kick(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = ACTIVE_GROUP_ROULETTE.get(self.game_id)
        if not game or not game["started"]:
            return await interaction.response.send_message("❌ اللعبة غير متاحة.", ephemeral=True)

        if interaction.user.id != game["selected_id"]:
            return await interaction.response.send_message("❌ هذا الدور ليس لك.", ephemeral=True)

        candidates = [m for m in game["players"] if m.id != game["selected_id"]]
        if not candidates:
            return await interaction.response.send_message("❌ لا يوجد لاعب يمكن طرده.", ephemeral=True)

        target = random.choice(candidates)
        await interaction.response.defer()
        await self.eliminate_and_continue(interaction, self.game_id, target)

    @staticmethod
    async def finish_game(interaction, game_id, winner, winner_index):
        game = ACTIVE_GROUP_ROULETTE.pop(game_id, None)
        if not game:
            return

        # لا يمكن أن تصبح الجائزة موجودة مرتين حتى مع تداخل الضغطات.
        for member in game["players"]:
            ACTIVE_GROUP_ROULETTE_USERS.discard(member.id)

        if game["amount"] > 0:
            add_balance(winner.id, game["amount"])

        embed = discord.Embed(
            title="🏆 نهاية الروليت الجماعية",
            description=(
                f"🎉 **لقد فزت يا {winner.mention}!**\n\n"
                + (
                    f"💰 تمت إضافة **{game['amount']:,} طولار** بنجاح إلى رصيدك."
                    if game["amount"] > 0
                    else "🎁 **انتهت اللعبة بدون جائزة مالية.**"
                )
            ),
            color=discord.Color.from_rgb(232, 198, 106),
        )
        embed.set_footer(text=f"عدد المشاركين النهائي: {len(game['players'])}")

        img_buf = None
        try:
            img_buf = await _get_cached_roulette_wheel(
                game["players"],
                winner_index,
            )
            file = discord.File(img_buf, filename="roulette_winner.gif")
            embed.set_image(url="attachment://roulette_winner.gif")

            # النتيجة النهائية أيضاً تُرسل في رسالة جديدة، ولا نستبدل رسالة الجولة السابقة.
            try:
                await interaction.message.edit(view=None)
            except Exception:
                pass

            await interaction.followup.send(
                embed=embed,
                file=file,
                wait=True,
            )
        finally:
            if img_buf is not None:
                img_buf.close()

    async def on_timeout(self):
        game = ACTIVE_GROUP_ROULETTE.get(self.game_id)
        if not game:
            return
        # اللعبة بدأت، لذلك نعيد الجائزة فقط إذا لم تنته بعد.
        ACTIVE_GROUP_ROULETTE.pop(self.game_id, None)
        if game["amount"] > 0:
            add_balance(game["host"].id, game["amount"])
        for member in game["players"]:
            ACTIVE_GROUP_ROULETTE_USERS.discard(member.id)
        if self.message:
            try:
                await self.message.edit(
                    content="⏰ انتهت اللعبة بسبب عدم التفاعل، وتمت إعادة مبلغ الجائزة لصاحب اللعبة.",
                    attachments=[],
                    view=None,
                )
            except Exception:
                pass


@bot.command(name="روليت")
@in_channel(GAMES_CHANNEL_ID)
async def group_roulette_game(ctx, amount_text=None):
    """الاستخدام: روليت أو روليت 1000. بدون مبلغ تبدأ اللعبة بلا جائزة."""
    if amount_text is None:
        amount = 0
    else:
        amount = _roulette_number(amount_text)
        if amount is None:
            await ctx.send(
                "❌ الاستخدام الصحيح: `روليت` أو `روليت 1000` — المبلغ يجب أن يكون رقماً أكبر من صفر.",
                delete_after=5,
            )
            return

    host_id = ctx.author.id
    if host_id in ACTIVE_GROUP_ROULETTE_USERS:
        await ctx.send("❌ لديك لعبة روليت مفتوحة بالفعل.", delete_after=4)
        return

    balance = get_balance(host_id)
    if amount > 0 and balance < amount:
        await ctx.send(
            f"❌ رصيدك غير كافٍ. تحتاج إلى **{amount:,} طولار** "
            f"ورصيدك الحالي **{balance:,}** طولار.",
            delete_after=5,
        )
        return

    # إذا وُجد مبلغ، يحجزه صاحب اللعبة مسبقاً كجائزة.
    if amount > 0:
        remove_balance(host_id, amount)

    game_id = f"{ctx.channel.id}:{ctx.message.id}:{host_id}"
    game = {
        "id": game_id,
        "host": ctx.author,
        "amount": amount,
        "players": [ctx.author],
        "started": False,
        "round": 0,
        "selected_id": None,
        "message": None,
    }
    ACTIVE_GROUP_ROULETTE[game_id] = game
    ACTIVE_GROUP_ROULETTE_USERS.add(host_id)

    view = GroupRouletteLobbyView(game_id)
    img_buf = None
    try:
        img_buf = await _get_cached_roulette_lobby(
            amount,
            game["players"],
            ctx.author,
        )
        file = discord.File(img_buf, filename="group_roulette.png")
        view.message = await ctx.send(
            file=file,
            view=view,
            allowed_mentions=discord.AllowedMentions(users=False),
        )
        game["message"] = view.message
    except Exception:
        ACTIVE_GROUP_ROULETTE.pop(game_id, None)
        ACTIVE_GROUP_ROULETTE_USERS.discard(host_id)
        add_balance(host_id, amount)
        raise
    finally:
        if img_buf is not None:
            img_buf.close()


# ==========================================
# 🕵️ لعبة الاختباء المحسّنة (Hide & Seek Pro)
# ==========================================

ACTIVE_HIDE_PRO_GAMES = {}
ACTIVE_HIDE_PRO_USERS = set()
HIDE_PRO_MAX_PLAYERS = 10
HIDE_PRO_MIN_PLAYERS = 2
HIDE_PRO_NUMBERS = 20          # عدد الأرقام الافتراضي
HIDE_PRO_JOIN_TIMEOUT = 30
HIDE_PRO_GAME_TIMEOUT = 600


def draw_hide_pro_lobby(amount, players, host, number_count):
    """بطاقة الـ Lobby للعبة الاختباء المحسّنة."""
    width, height = 1200, 700
    base = _open_roulette_background((width, height))
    d = ImageDraw.Draw(base)

    # زخارف
    for r in (530, 500, 470):
        d.ellipse(
            (width//2-r, 350-r, width//2+r, 350+r),
            outline=(184, 145, 55, 35),
            width=2,
        )

    # العنوان
    d.rounded_rectangle(
        (70, 35, width-70, 145),
        radius=30,
        fill=(26, 31, 48, 245),
        outline=(232, 198, 106, 255),
        width=4,
    )
    d.text(
        (width//2, 88),
        "🕵️ لعبة الاختباء المحسّنة",
        font=_font(48),
        fill=(232, 198, 106, 255),
        anchor="mm",
    )

    # عدد اللاعبين
    d.rounded_rectangle(
        (820, 175, 1130, 285),
        radius=24,
        fill=(10, 13, 22, 235),
        outline=(232, 198, 106, 210),
        width=3,
    )
    d.text(
        (975, 213),
        f"{len(players)} / {HIDE_PRO_MAX_PLAYERS}",
        font=_font(46),
        fill=(255, 255, 255, 255),
        anchor="mm",
    )
    d.text(
        (975, 258),
        "عدد المشاركين",
        font=_font(22),
        fill=(180, 184, 198, 255),
        anchor="mm",
    )

    # معلومات الجائزة وصاحب اللعبة
    d.rounded_rectangle(
        (70, 175, 790, 285),
        radius=24,
        fill=(26, 31, 48, 235),
        outline=(80, 91, 120, 200),
        width=2,
    )
    prize_text = f"الجائزة: {amount:,} طولار" if amount > 0 else "بدون جائزة"
    d.text(
        (430, 212),
        prize_text,
        font=_fit_font(prize_text, 620, 34, 22),
        fill=(232, 198, 106, 255),
        anchor="mm",
    )
    d.text(
        (430, 258),
        f"صاحب اللعبة: {host.display_name[:28]}",
        font=_fit_font(f"صاحب اللعبة: {host.display_name[:28]}", 620, 24, 18),
        fill=(220, 223, 233, 255),
        anchor="mm",
    )

    # التعليمات
    d.rounded_rectangle(
        (70, 315, 1130, 455),
        radius=26,
        fill=(7, 10, 18, 205),
        outline=(70, 82, 110, 180),
        width=2,
    )
    d.text(
        (600, 350),
        f"اختر رقمك السري من 1 إلى {number_count}",
        font=_font(35),
        fill=(255, 255, 255, 255),
        anchor="mm",
    )
    d.text(
        (600, 405),
        "سيتم اختيار باحث عشوائياً ليبحث عن اللاعبين المختبئين",
        font=_fit_font(
            "سيتم اختيار باحث عشوائياً ليبحث عن اللاعبين المختبئين",
            950, 28, 18
        ),
        fill=(194, 199, 214, 255),
        anchor="mm",
    )

    # أسماء اللاعبين
    d.text(
        (600, 490),
        "اللاعبون المشاركون",
        font=_font(28),
        fill=(232, 198, 106, 255),
        anchor="mm",
    )

    for i in range(HIDE_PRO_MAX_PLAYERS):
        row = i // 5
        col = i % 5
        x1 = 70 + col * 210
        y1 = 520 + row * 75
        x2 = x1 + 195
        y2 = y1 + 58
        if i < len(players):
            member = players[i]
            fill = (34, 42, 62, 245)
            outline = (232, 198, 106, 190)
            name = member.display_name[:20]
        else:
            fill = (20, 24, 36, 180)
            outline = (55, 62, 80, 130)
            name = "— فارغ —"
        d.rounded_rectangle(
            (x1, y1, x2, y2),
            radius=16,
            fill=fill,
            outline=outline,
            width=2,
        )
        d.text(
            ((x1+x2)//2, (y1+y2)//2),
            name,
            font=_fit_font(name, 170, 22, 15),
            fill=(255, 255, 255, 255) if i < len(players) else (105, 111, 128, 255),
            anchor="mm",
        )

    out = io.BytesIO()
    base.save(out, format="PNG", optimize=False, compress_level=3)
    out.seek(0)
    base.close()
    return out


def draw_hide_pro_result(winner_avatar_bytes, winner_name, prize):
    """بطاقة النتيجة النهائية للعبة المحسّنة."""
    width, height = 1024, 501
    base = _open_roulette_background((width, height))
    d = ImageDraw.Draw(base)

    d.rounded_rectangle(
        (65, 35, width-65, 110),
        radius=22,
        fill=(26, 31, 48, 235),
        outline=(232, 198, 106, 220),
        width=3,
    )
    d.text(
        (width//2, 73),
        "🏆 نهاية لعبة الاختباء",
        font=_font(34),
        fill=(232, 198, 106, 255),
        anchor="mm",
    )

    if winner_avatar_bytes:
        try:
            avatar = get_circle_avatar(winner_avatar_bytes, (190, 190))
            base.paste(avatar, (417, 130), avatar)
        except Exception:
            pass

    d.text(
        (512, 350),
        winner_name[:24],
        font=_fit_font(winner_name[:24], 500, 30, 18),
        fill=(255, 255, 255, 255),
        anchor="mm",
    )
    prize_text = f"الجائزة: {prize:,} طولار" if prize > 0 else "انتهت اللعبة بدون جائزة مالية"
    d.text(
        (512, 405),
        prize_text,
        font=_fit_font(prize_text, 700, 27, 18),
        fill=(232, 198, 106, 255),
        anchor="mm",
    )

    out = io.BytesIO()
    base.save(out, format="PNG", optimize=False, compress_level=3)
    out.seek(0)
    base.close()
    return out


class HideProNumberButton(discord.ui.Button):
    """زر يمثل رقمًا في لوحة الأرقام."""
    def __init__(self, game_id, number, row=0, disabled=False):
        self.game_id = game_id
        self.number = number
        super().__init__(
            label=str(number),
            style=discord.ButtonStyle.secondary,
            disabled=disabled,
            row=row,
        )

    async def callback(self, interaction: discord.Interaction):
        game = ACTIVE_HIDE_PRO_GAMES.get(self.game_id)
        if not game:
            return await interaction.response.send_message("❌ انتهت اللعبة.", ephemeral=True)

        # أثناء مرحلة التسجيل: اللاعب يختار رقمه السري
        if not game["started"]:
            uid = interaction.user.id
            if uid not in [m.id for m in game["players"]]:
                return await interaction.response.send_message("❌ يجب أن تدخل اللعبة أولاً.", ephemeral=True)
            if uid in game["choices"]:
                return await interaction.response.send_message(f"⚠️ تم تسجيل اختيارك مسبقاً: **{game['choices'][uid]}**.", ephemeral=True)
            if self.number in game["taken"]:
                return await interaction.response.send_message("❌ هذا الرقم اختاره لاعب آخر، اختر رقماً مختلفاً.", ephemeral=True)

            game["choices"][uid] = self.number
            game["taken"][self.number] = uid
            # تغيير لون الزر إلى أخضر للإشارة إلى أنه تم اختياره
            self.style = discord.ButtonStyle.success
            self.disabled = True
            await interaction.response.edit_message(view=self.view)
            await interaction.followup.send(f"✅ تم تسجيل اختيارك رقم **{self.number}**.", ephemeral=True)
            return

        # أثناء اللعب: الباحث يختار رقمًا للكشف
        if interaction.user.id != game["seeker_id"]:
            return await interaction.response.send_message("❌ هذا الدور ليس لك، أنت لست الباحث.", ephemeral=True)

        state = game["buttons"].get(self.number)
        if state != "open":
            return await interaction.response.send_message("❌ هذا الرقم تم اختياره مسبقاً.", ephemeral=True)

        async with game["lock"]:
            if self.number not in game["buttons"] or game["buttons"][self.number] != "open":
                return await interaction.response.send_message("❌ هذا الرقم تم اختياره مسبقاً.", ephemeral=True)

            target_id = game["taken"].get(self.number)
            # تحديث حالة الزر
            if target_id in game["active_ids"]:
                # تم العثور على لاعب
                game["buttons"][self.number] = "found"
                game["active_ids"].remove(target_id)
                target = game["member_by_id"].get(target_id)
                if target:
                    game["eliminated"].append(target)
                self.style = discord.ButtonStyle.success
                self.disabled = True
                message = f"🔍 وجدت **{target.display_name}** مختبئاً خلف الرقم {self.number}!"
            else:
                # رقم فارغ
                game["buttons"][self.number] = "empty"
                self.style = discord.ButtonStyle.danger
                self.disabled = True
                message = f"❌ الرقم {self.number} فارغ، لم يكن هناك أحد."

            await interaction.response.edit_message(view=self.view)
            await interaction.followup.send(message)

            # هل انتهت اللعبة؟
            if len(game["active_ids"]) <= 1:
                # إنهاء اللعبة
                await HideProGameView.finish_game(self.game_id, interaction)
                return

            # اختيار الباحث التالي (إذا أردنا تغيير الباحث بعد كل كشف) - هنا نبقي نفس الباحث.
            # لكن يمكن جعل الباحث يظل كما هو حتى يجد الجميع.
            # نحدث الـ Embed لإظهار الحالة الجديدة
            view = self.view
            if isinstance(view, HideProGameView):
                await view.update_message(interaction)


class HideProLobbyView(discord.ui.View):
    """واجهة التسجيل والانضمام."""
    def __init__(self, game_id):
        super().__init__(timeout=HIDE_PRO_GAME_TIMEOUT)
        self.game_id = game_id
        self.message = None
        self.no_join_task = asyncio.create_task(self._cancel_if_no_join())

        # أزرار الأرقام (للتسجيل)
        for number in range(1, HIDE_PRO_NUMBERS + 1):
            row = (number - 1) // 5
            self.add_item(HideProNumberButton(game_id, number, row=row))

    def _game(self):
        return ACTIVE_HIDE_PRO_GAMES.get(self.game_id)

    async def _cancel_if_no_join(self):
        try:
            await asyncio.sleep(HIDE_PRO_JOIN_TIMEOUT)
            game = self._game()
            if not game or game["started"] or len(game["players"]) > 1:
                return

            ACTIVE_HIDE_PRO_GAMES.pop(self.game_id, None)
            if game["amount"] > 0:
                add_balance(game["host"].id, game["amount"])
            for member in game["players"]:
                ACTIVE_HIDE_PRO_USERS.discard(member.id)

            if self.message:
                try:
                    await self.message.edit(
                        content="⏰ تم إلغاء اللعبة لعدم دخول لاعبين جدد خلال 30 ثانية."
                        + (" وتمت إعادة مبلغ الجائزة." if game["amount"] > 0 else ""),
                        attachments=[],
                        view=None,
                    )
                except Exception:
                    pass
            self.stop()
        except asyncio.CancelledError:
            pass

    async def _refresh(self, interaction):
        game = self._game()
        if not game:
            return
        img_buf = None
        try:
            img_buf = await _run_bg(
                draw_hide_pro_lobby,
                game["amount"],
                game["players"],
                game["host"],
                HIDE_PRO_NUMBERS,
            )
            file = discord.File(img_buf, filename="hide_pro_lobby.png")
            await interaction.message.edit(
                attachments=[file],
                view=self,
                content=None,
            )
        finally:
            if img_buf is not None:
                img_buf.close()

    @discord.ui.button(label="دخول", style=discord.ButtonStyle.success, emoji="🎟️", row=4)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = self._game()
        if not game:
            return await interaction.response.send_message("❌ انتهت اللعبة.", ephemeral=True)

        uid = interaction.user.id
        if uid in [m.id for m in game["players"]]:
            return await interaction.response.send_message("⚠️ أنت داخل اللعبة بالفعل.", ephemeral=True)
        if len(game["players"]) >= HIDE_PRO_MAX_PLAYERS:
            return await interaction.response.send_message("❌ اللعبة مكتملة (10/10).", ephemeral=True)
        if uid in ACTIVE_HIDE_PRO_USERS:
            return await interaction.response.send_message("❌ أنت مشارك في لعبة اختباء أخرى.", ephemeral=True)

        game["players"].append(interaction.user)
        game["member_by_id"][uid] = interaction.user
        ACTIVE_HIDE_PRO_USERS.add(uid)
        await interaction.response.defer()
        await self._refresh(interaction)

    @discord.ui.button(label="خروج", style=discord.ButtonStyle.secondary, emoji="🚪", row=4)
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = self._game()
        if not game:
            return await interaction.response.send_message("❌ انتهت اللعبة.", ephemeral=True)

        uid = interaction.user.id
        if uid not in [m.id for m in game["players"]]:
            return await interaction.response.send_message("⚠️ أنت لست داخل اللعبة.", ephemeral=True)
        if game["started"]:
            return await interaction.response.send_message("❌ لا يمكن الخروج بعد بدء اللعبة.", ephemeral=True)

        game["players"] = [m for m in game["players"] if m.id != uid]
        game["member_by_id"].pop(uid, None)
        game["choices"].pop(uid, None)
        for number, owner_id in list(game["taken"].items()):
            if owner_id == uid:
                game["taken"].pop(number, None)
        ACTIVE_HIDE_PRO_USERS.discard(uid)

        if uid == game["host"].id:
            ACTIVE_HIDE_PRO_GAMES.pop(self.game_id, None)
            if game["amount"] > 0:
                add_balance(game["host"].id, game["amount"])
            for member in game["players"]:
                ACTIVE_HIDE_PRO_USERS.discard(member.id)
            await interaction.response.edit_message(
                content="❌ تم إلغاء اللعبة لأن صاحب اللعبة خرج، وتمت إعادة الجائزة له.",
                attachments=[],
                view=None,
            )
            self.stop()
            return

        await interaction.response.defer()
        await self._refresh(interaction)

    @discord.ui.button(label="بدء", style=discord.ButtonStyle.primary, emoji="▶️", row=4)
    async def start_game(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = self._game()
        if not game:
            return await interaction.response.send_message("❌ انتهت اللعبة.", ephemeral=True)
        if interaction.user.id != game["host"].id:
            return await interaction.response.send_message("❌ زر بدء اللعبة لصاحب اللعبة فقط.", ephemeral=True)
        if len(game["players"]) < HIDE_PRO_MIN_PLAYERS:
            return await interaction.response.send_message(f"❌ يجب دخول {HIDE_PRO_MIN_PLAYERS} لاعبين على الأقل.", ephemeral=True)
        if len(game["choices"]) != len(game["players"]):
            missing = [m.mention for m in game["players"] if m.id not in game["choices"]]
            return await interaction.response.send_message(
                "❌ يجب أن يختار جميع المشاركين أماكنهم أولاً.\nالمتبقي: " + ", ".join(missing[:10]),
                ephemeral=True,
            )
        if game["started"]:
            return await interaction.response.send_message("⚠️ اللعبة بدأت بالفعل.", ephemeral=True)

        game["started"] = True
        game["active_ids"] = {m.id for m in game["players"]}
        # اختيار باحث عشوائي
        game["seeker_id"] = random.choice(list(game["active_ids"]))
        game["buttons"] = {n: "open" for n in range(1, HIDE_PRO_NUMBERS + 1)}

        await interaction.response.defer()
        # إغلاق رسالة التسجيل
        try:
            await interaction.message.edit(view=None)
        except Exception:
            pass

        view = HideProGameView(self.game_id)
        game["view"] = view
        await view.send_new_round(interaction, first=True)
        self.stop()


class HideProGameView(discord.ui.View):
    """واجهة اللعب الفعلية (بعد البدء)."""
    def __init__(self, game_id):
        super().__init__(timeout=HIDE_PRO_GAME_TIMEOUT)
        self.game_id = game_id
        self.message = None
        for number in range(1, HIDE_PRO_NUMBERS + 1):
            row = (number - 1) // 5
            self.add_item(HideProNumberButton(game_id, number, row=row))

    @staticmethod
    def _embed(game):
        seeker = game["member_by_id"].get(game["seeker_id"])
        active_count = len(game["active_ids"])
        embed = discord.Embed(
            title="🕵️ لعبة الاختباء المحسّنة",
            description=(
                f"🔍 **الباحث:** {seeker.mention if seeker else 'غير معروف'}\n"
                f"👥 المتبقون: **{active_count}** لاعب\n"
                + (f"💰 الجائزة: **{game['amount']:,} طولار**" if game["amount"] > 0 else "🎁 بدون جائزة مالية")
                + "\n\nاختر رقماً لكشف من يختبئ خلفه."
            ),
            color=discord.Color.from_rgb(184, 145, 55),
        )
        return embed

    def _apply_button_states(self):
        """تحديث ألوان الأزرار بناءً على حالة اللعبة."""
        game = ACTIVE_HIDE_PRO_GAMES.get(self.game_id)
        if not game:
            return
        for child in self.children:
            if not isinstance(child, HideProNumberButton):
                continue
            state = game["buttons"].get(child.number)
            if state == "found":
                child.style = discord.ButtonStyle.success
                child.disabled = True
            elif state == "empty":
                child.style = discord.ButtonStyle.danger
                child.disabled = True
            else:
                # أثناء مرحلة اللعب، الأرقام المفتوحة تكون قابلة للضغط
                # لكن الباحث فقط يمكنه الضغط
                child.style = discord.ButtonStyle.secondary
                child.disabled = False

    async def send_new_round(self, interaction, first=False):
        game = ACTIVE_HIDE_PRO_GAMES.get(self.game_id)
        if not game:
            return
        self._apply_button_states()
        embed = self._embed(game)
        # نرسل رسالة جديدة بدلاً من تعديل الرسالة السابقة
        new_message = await interaction.followup.send(
            embed=embed,
            view=self,
            wait=True,
        )
        self.message = new_message
        game["message"] = new_message
        game["view"] = self

    async def update_message(self, interaction):
        game = ACTIVE_HIDE_PRO_GAMES.get(self.game_id)
        if not game:
            return
        self._apply_button_states()
        embed = self._embed(game)
        if self.message is None:
            self.message = interaction.message
        game["message"] = self.message
        game["view"] = self
        await self.message.edit(embed=embed, view=self)

    @staticmethod
    async def finish_game(game_id, interaction):
        game = ACTIVE_HIDE_PRO_GAMES.pop(game_id, None)
        if not game:
            return

        winner_id = next(iter(game["active_ids"]), None)
        winner = game["member_by_id"].get(winner_id)
        if winner is None:
            return

        for member in game["players"]:
            ACTIVE_HIDE_PRO_USERS.discard(member.id)

        if game["amount"] > 0:
            add_balance(winner.id, game["amount"])

        try:
            await interaction.message.edit(view=None)
        except Exception:
            pass

        avatar_bytes = None
        try:
            avatar_bytes = await winner.display_avatar.read()
        except Exception:
            pass

        img_buf = None
        try:
            img_buf = await _run_bg(
                draw_hide_pro_result,
                avatar_bytes,
                winner.display_name,
                game["amount"],
            )
            file = discord.File(img_buf, filename="hide_pro_result.png")
            embed = discord.Embed(
                title="🏆 نهاية لعبة الاختباء",
                description=(
                    f"🎉 **الفائز: {winner.mention}**\n\n"
                    + (f"💰 تمت إضافة **{game['amount']:,} طولار** إلى رصيد الفائز."
                       if game["amount"] > 0 else "🎁 انتهت اللعبة بدون جائزة مالية.")
                ),
                color=discord.Color.from_rgb(232, 198, 106),
            )
            embed.set_image(url="attachment://hide_pro_result.png")
            embed.set_footer(text=f"عدد المشاركين: {len(game['players'])}")
            await interaction.followup.send(embed=embed, file=file, wait=True)
        finally:
            if img_buf is not None:
                img_buf.close()

    async def on_timeout(self):
        game = ACTIVE_HIDE_PRO_GAMES.get(self.game_id)
        if not game or game.get("view") is not self:
            return

        ACTIVE_HIDE_PRO_GAMES.pop(self.game_id, None)
        if game["amount"] > 0:
            add_balance(game["host"].id, game["amount"])
        for member in game["players"]:
            ACTIVE_HIDE_PRO_USERS.discard(member.id)
        if self.message:
            try:
                await self.message.edit(
                    content="⏰ انتهت اللعبة بسبب انتهاء وقت التفاعل."
                    + (" تمت إعادة الجائزة لصاحب اللعبة." if game["amount"] > 0 else ""),
                    embed=None,
                    attachments=[],
                    view=None,
                )
            except Exception:
                pass


@bot.command(name="اختباء_جديد", aliases=["مخابئ", "hidepro"])
@in_channel(GAMES_CHANNEL_ID)
async def hide_pro_game(ctx, amount_text=None):
    """الاستخدام: اختباء_جديد أو اختباء_جديد 1000."""
    if amount_text is None:
        amount = 0
    else:
        amount = _roulette_number(amount_text)
        if amount is None:
            return await ctx.send(
                "❌ الاستخدام: `اختباء_جديد` أو `اختباء_جديد 1000` (المبلغ رقم)",
                delete_after=5,
            )

    host_id = ctx.author.id
    if host_id in ACTIVE_HIDE_PRO_USERS:
        return await ctx.send("❌ لديك لعبة اختباء مفتوحة بالفعل.", delete_after=4)

    balance = get_balance(host_id)
    if amount > 0 and balance < amount:
        return await ctx.send(
            f"❌ رصيدك غير كافٍ. تحتاج **{amount:,} طولار**، رصيدك **{balance:,}**.",
            delete_after=5,
        )

    if amount > 0:
        remove_balance(host_id, amount)

    game_id = f"hidepro:{ctx.channel.id}:{ctx.message.id}:{host_id}"
    game = {
        "id": game_id,
        "host": ctx.author,
        "amount": amount,
        "players": [ctx.author],
        "member_by_id": {host_id: ctx.author},
        "choices": {},
        "taken": {},
        "started": False,
        "seeker_id": None,
        "active_ids": set(),
        "buttons": {},
        "eliminated": [],
        "message": None,
        "view": None,
        "lock": asyncio.Lock(),
    }
    ACTIVE_HIDE_PRO_GAMES[game_id] = game
    ACTIVE_HIDE_PRO_USERS.add(host_id)

    view = HideProLobbyView(game_id)
    img_buf = None
    try:
        img_buf = await _run_bg(
            draw_hide_pro_lobby,
            amount,
            game["players"],
            ctx.author,
            HIDE_PRO_NUMBERS,
        )
        file = discord.File(img_buf, filename="hide_pro_lobby.png")
        view.message = await ctx.send(
            file=file,
            view=view,
            allowed_mentions=discord.AllowedMentions(users=False),
        )
        game["message"] = view.message
    except Exception:
        ACTIVE_HIDE_PRO_GAMES.pop(game_id, None)
        ACTIVE_HIDE_PRO_USERS.discard(host_id)
        if amount > 0:
            add_balance(host_id, amount)
        raise
    finally:
        if img_buf is not None:
            img_buf.close()


# ==========================================
# 🕵️ لعبة الاختباء
# ==========================================
ACTIVE_HIDE_GAMES = {}
ACTIVE_HIDE_USERS = set()

HIDE_MAX_PLAYERS = 10
HIDE_MIN_PLAYERS = 2
HIDE_BUTTONS = 20
HIDE_JOIN_TIMEOUT = 20
HIDE_GAME_TIMEOUT = 600


def draw_hide_lobby(amount, players, host):
    """بطاقة لعبة الاختباء بنفس طابع بطاقة الروليت."""
    width, height = 1200, 700
    base = _open_roulette_background((width, height))
    d = ImageDraw.Draw(base)

    for r in (530, 500, 470):
        d.ellipse(
            (width//2-r, 350-r, width//2+r, 350+r),
            outline=(184, 145, 55, 35),
            width=2,
        )

    d.rounded_rectangle(
        (70, 35, width-70, 145),
        radius=30,
        fill=(26, 31, 48, 245),
        outline=(232, 198, 106, 255),
        width=4,
    )
    d.text(
        (width//2, 88),
        "🕵️ لعبة الاختباء",
        font=_font(52),
        fill=(232, 198, 106, 255),
        anchor="mm",
    )

    # عدد المشاركين
    d.rounded_rectangle(
        (820, 175, 1130, 285),
        radius=24,
        fill=(10, 13, 22, 235),
        outline=(232, 198, 106, 210),
        width=3,
    )
    d.text(
        (975, 213),
        f"{len(players)} / {HIDE_MAX_PLAYERS}",
        font=_font(46),
        fill=(255, 255, 255, 255),
        anchor="mm",
    )
    d.text(
        (975, 258),
        "عدد المشاركين",
        font=_font(22),
        fill=(180, 184, 198, 255),
        anchor="mm",
    )

    # الجائزة
    d.rounded_rectangle(
        (70, 175, 790, 285),
        radius=24,
        fill=(26, 31, 48, 235),
        outline=(80, 91, 120, 200),
        width=2,
    )
    prize_text = f"الجائزة: {amount:,} طولار" if amount > 0 else "بدون جائزة"
    d.text(
        (430, 212),
        prize_text,
        font=_fit_font(prize_text, 620, 34, 22),
        fill=(232, 198, 106, 255),
        anchor="mm",
    )
    d.text(
        (430, 258),
        f"صاحب اللعبة: {host.display_name[:28]}",
        font=_fit_font(f"صاحب اللعبة: {host.display_name[:28]}", 620, 24, 18),
        fill=(220, 223, 233, 255),
        anchor="mm",
    )

    # شرح اللعبة كما طلب المستخدم.
    d.rounded_rectangle(
        (70, 315, 1130, 455),
        radius=26,
        fill=(7, 10, 18, 205),
        outline=(70, 82, 110, 180),
        width=2,
    )
    d.text(
        (600, 350),
        "اضغط على أحد الأزرار للاختباء",
        font=_font(35),
        fill=(255, 255, 255, 255),
        anchor="mm",
    )
    description = "يختار كل لاعب رقماً سرياً من 1 إلى 20، ثم يبدأ الطرد حتى يبقى فائز واحد."
    d.text(
        (600, 405),
        description,
        font=_fit_font(description, 950, 28, 18),
        fill=(194, 199, 214, 255),
        anchor="mm",
    )

    d.text(
        (600, 490),
        "اللاعبون المشاركون",
        font=_font(28),
        fill=(232, 198, 106, 255),
        anchor="mm",
    )

    for i in range(HIDE_MAX_PLAYERS):
        row = i // 5
        col = i % 5
        x1 = 70 + col * 210
        y1 = 520 + row * 75
        x2 = x1 + 195
        y2 = y1 + 58
        if i < len(players):
            member = players[i]
            fill = (34, 42, 62, 245)
            outline = (232, 198, 106, 190)
            name = member.display_name[:20]
        else:
            fill = (20, 24, 36, 180)
            outline = (55, 62, 80, 130)
            name = "— فارغ —"
        d.rounded_rectangle(
            (x1, y1, x2, y2),
            radius=16,
            fill=fill,
            outline=outline,
            width=2,
        )
        d.text(
            ((x1+x2)//2, (y1+y2)//2),
            name,
            font=_fit_font(name, 170, 22, 15),
            fill=(255, 255, 255, 255) if i < len(players) else (105, 111, 128, 255),
            anchor="mm",
        )

    out = io.BytesIO()
    base.save(out, format="PNG", optimize=False, compress_level=3)
    out.seek(0)
    base.close()
    return out


def draw_hide_result(winner_avatar_bytes, winner_name, prize):
    """بطاقة نتيجة نهائية بنفس أسلوب بطاقة الروليت."""
    width, height = 1024, 501
    base = _open_roulette_background((width, height))
    d = ImageDraw.Draw(base)

    d.rounded_rectangle(
        (65, 35, width-65, 110),
        radius=22,
        fill=(26, 31, 48, 235),
        outline=(232, 198, 106, 220),
        width=3,
    )
    d.text(
        (width//2, 73),
        "🏆 نهاية لعبة الاختباء",
        font=_font(34),
        fill=(232, 198, 106, 255),
        anchor="mm",
    )

    if winner_avatar_bytes:
        try:
            avatar = get_circle_avatar(winner_avatar_bytes, (190, 190))
            base.paste(avatar, (417, 130), avatar)
        except Exception:
            pass

    d.text(
        (512, 350),
        winner_name[:24],
        font=_fit_font(winner_name[:24], 500, 30, 18),
        fill=(255, 255, 255, 255),
        anchor="mm",
    )
    prize_text = f"الجائزة: {prize:,} طولار" if prize > 0 else "انتهت اللعبة بدون جائزة مالية"
    d.text(
        (512, 405),
        prize_text,
        font=_fit_font(prize_text, 700, 27, 18),
        fill=(232, 198, 106, 255),
        anchor="mm",
    )

    out = io.BytesIO()
    base.save(out, format="PNG", optimize=False, compress_level=3)
    out.seek(0)
    base.close()
    return out


class HideNumberButton(discord.ui.Button):
    def __init__(self, game_id, number, disabled=False, style=discord.ButtonStyle.secondary, row=None):
        self.game_id = game_id
        self.number = number
        super().__init__(
            label=str(number),
            style=style,
            disabled=disabled,
            row=row,
        )

    async def callback(self, interaction: discord.Interaction):
        game = ACTIVE_HIDE_GAMES.get(self.game_id)
        if not game:
            return await interaction.response.send_message("❌ انتهت اللعبة.", ephemeral=True)

        # في مرحلة التسجيل: الرقم يختاره صاحبه سراً، ولا نغيّر شكل الزر.
        if not game["started"]:
            uid = interaction.user.id
            if uid not in [m.id for m in game["players"]]:
                return await interaction.response.send_message(
                    "❌ يجب أن تدخل اللعبة أولاً.", ephemeral=True
                )
            if uid in game["choices"]:
                return await interaction.response.send_message(
                    f"⚠️ تم تسجيل اختيارك مسبقاً: **{game['choices'][uid]}**.", ephemeral=True
                )
            if self.number in game["taken"]:
                return await interaction.response.send_message(
                    "❌ هذا الرقم اختاره لاعب آخر، اختر رقماً مختلفاً.", ephemeral=True
                )

            game["choices"][uid] = self.number
            game["taken"][self.number] = uid
            await interaction.response.send_message(
                f"✅ تم تسجيل اختيارك رقمك **{self.number}**.", ephemeral=True
            )
            return

        # أثناء اللعب: الزر يحدد مكان اختباء أحد اللاعبين.
        if interaction.user.id != game["selected_id"]:
            return await interaction.response.send_message(
                "❌ هذا الدور ليس لك.", ephemeral=True
            )

        state = game["buttons"].get(self.number)
        if state != "open":
            return await interaction.response.send_message(
                "❌ هذا الزر تم اختياره مسبقاً.", ephemeral=True
            )

        async with game["lock"]:
            # إعادة التحقق بعد الحصول على القفل لمنع ضغطتين متزامنتين.
            if self.number not in game["buttons"] or game["buttons"][self.number] != "open":
                return await interaction.response.send_message(
                    "❌ هذا الزر تم اختياره مسبقاً.", ephemeral=True
                )

            target_id = game["taken"].get(self.number)
            game["buttons"][self.number] = "green" if target_id in game["active_ids"] else "red"

            if target_id in game["active_ids"]:
                game["active_ids"].remove(target_id)
                target = game["member_by_id"].get(target_id)
                if target:
                    game["eliminated"].append(target)

            # انتهت اللعبة إذا بقي لاعب واحد.
            if len(game["active_ids"]) <= 1:
                await interaction.response.defer()
                # إنهاء اللعبة بالدالة الصحيحة (الوسيط الأول هو game_id).
                await HideGameView.finish_game(self.game_id, interaction)
                return

            # الدور التالي عشوائي من اللاعبين المتبقين.
            game["selected_id"] = random.choice(list(game["active_ids"]))
            await interaction.response.defer()

            # أوقف الـ View السابق حتى لا ينتهي Timeout قديم ويُلغي اللعبة
            # أثناء وجود جولة أحدث فعّالة.
            current_view = getattr(self, "view", None)
            if current_view is not None:
                current_view.stop()

            view = HideGameView(self.game_id)
            game["view"] = view
            await view.update_message(interaction)


class HideLobbyView(discord.ui.View):
    def __init__(self, game_id):
        super().__init__(timeout=HIDE_GAME_TIMEOUT)
        self.game_id = game_id
        self.message = None
        self.no_join_task = asyncio.create_task(self._cancel_if_no_join())

        for number in range(1, HIDE_BUTTONS + 1):
            row = (number - 1) // 5
            self.add_item(HideNumberButton(game_id, number, row=row))

    def _game(self):
        return ACTIVE_HIDE_GAMES.get(self.game_id)

    async def _cancel_if_no_join(self):
        try:
            await asyncio.sleep(HIDE_JOIN_TIMEOUT)
            game = self._game()
            if not game or game["started"] or len(game["players"]) > 1:
                return

            ACTIVE_HIDE_GAMES.pop(self.game_id, None)
            if game["amount"] > 0:
                add_balance(game["host"].id, game["amount"])
            for member in game["players"]:
                ACTIVE_HIDE_USERS.discard(member.id)

            if self.message:
                try:
                    await self.message.edit(
                        content="⏰ تم إلغاء لعبة الاختباء لعدم دخول أي لاعب خلال 20 ثانية."
                        + (
                            " وتمت إعادة مبلغ الجائزة لصاحب اللعبة."
                            if game["amount"] > 0 else ""
                        ),
                        attachments=[],
                        view=None,
                    )
                except Exception:
                    pass
            self.stop()
        except asyncio.CancelledError:
            pass

    async def _refresh(self, interaction):
        game = self._game()
        if not game:
            return
        img_buf = None
        try:
            img_buf = await _run_bg(
                draw_hide_lobby,
                game["amount"],
                game["players"],
                game["host"],
            )
            file = discord.File(img_buf, filename="hide_lobby.png")
            await interaction.message.edit(
                attachments=[file],
                view=self,
                content=None,
            )
        finally:
            if img_buf is not None:
                img_buf.close()

    @discord.ui.button(label="دخول", style=discord.ButtonStyle.success, emoji="🎟️", row=4)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = self._game()
        if not game:
            return await interaction.response.send_message("❌ انتهت اللعبة.", ephemeral=True)

        uid = interaction.user.id
        if uid in [m.id for m in game["players"]]:
            return await interaction.response.send_message("⚠️ أنت داخل اللعبة بالفعل.", ephemeral=True)
        if len(game["players"]) >= HIDE_MAX_PLAYERS:
            return await interaction.response.send_message("❌ اللعبة مكتملة (10/10).", ephemeral=True)
        if uid in ACTIVE_HIDE_USERS:
            return await interaction.response.send_message(
                "❌ أنت مشارك في لعبة اختباء أخرى بالفعل.", ephemeral=True
            )

        game["players"].append(interaction.user)
        game["member_by_id"][uid] = interaction.user
        ACTIVE_HIDE_USERS.add(uid)
        await interaction.response.defer()
        await self._refresh(interaction)

    @discord.ui.button(label="خروج", style=discord.ButtonStyle.secondary, emoji="🚪", row=4)
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = self._game()
        if not game:
            return await interaction.response.send_message("❌ انتهت اللعبة.", ephemeral=True)

        uid = interaction.user.id
        if uid not in [m.id for m in game["players"]]:
            return await interaction.response.send_message("⚠️ أنت لست داخل اللعبة.", ephemeral=True)
        if game["started"]:
            return await interaction.response.send_message("❌ لا يمكن الخروج بعد بدء اللعبة.", ephemeral=True)

        game["players"] = [m for m in game["players"] if m.id != uid]
        game["member_by_id"].pop(uid, None)
        game["choices"].pop(uid, None)
        for number, owner_id in list(game["taken"].items()):
            if owner_id == uid:
                game["taken"].pop(number, None)
        ACTIVE_HIDE_USERS.discard(uid)

        if uid == game["host"].id:
            ACTIVE_HIDE_GAMES.pop(self.game_id, None)
            if game["amount"] > 0:
                add_balance(game["host"].id, game["amount"])
            for member in game["players"]:
                ACTIVE_HIDE_USERS.discard(member.id)
            await interaction.response.edit_message(
                content="❌ تم إلغاء لعبة الاختباء لأن صاحب اللعبة خرج، وتمت إعادة الجائزة له.",
                attachments=[],
                view=None,
            )
            self.stop()
            return

        await interaction.response.defer()
        await self._refresh(interaction)

    @discord.ui.button(label="بدء", style=discord.ButtonStyle.primary, emoji="▶️", row=4)
    async def start_game(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = self._game()
        if not game:
            return await interaction.response.send_message("❌ انتهت اللعبة.", ephemeral=True)
        if interaction.user.id != game["host"].id:
            return await interaction.response.send_message(
                "❌ زر بدء اللعبة لصاحب اللعبة فقط.", ephemeral=True
            )
        if len(game["players"]) < HIDE_MIN_PLAYERS:
            return await interaction.response.send_message(
                f"❌ يجب دخول {HIDE_MIN_PLAYERS} لاعبين على الأقل.", ephemeral=True
            )
        if len(game["choices"]) != len(game["players"]):
            missing = [
                m.mention for m in game["players"]
                if m.id not in game["choices"]
            ]
            return await interaction.response.send_message(
                "❌ يجب أن يختار جميع المشاركين مكان اختبائهم أولاً.\n"
                + "المتبقي: " + ", ".join(missing[:10]),
                ephemeral=True,
            )
        if game["started"]:
            return await interaction.response.send_message("⚠️ اللعبة بدأت بالفعل.", ephemeral=True)

        game["started"] = True
        game["active_ids"] = {m.id for m in game["players"]}
        game["selected_id"] = random.choice(list(game["active_ids"]))
        game["buttons"] = {n: "open" for n in range(1, HIDE_BUTTONS + 1)}

        await interaction.response.defer()
        # إغلاق رسالة التسجيل وإرسال رسالة لعب جديدة.
        try:
            await interaction.message.edit(view=None)
        except Exception:
            pass

        view = HideGameView(self.game_id)
        game["view"] = view
        await view.send_new_round(interaction, first=True)
        self.stop()


class HideGameView(discord.ui.View):
    def __init__(self, game_id):
        super().__init__(timeout=HIDE_GAME_TIMEOUT)
        self.game_id = game_id
        self.message = None
        for number in range(1, HIDE_BUTTONS + 1):
            self.add_item(HideNumberButton(game_id, number, row=(number - 1) // 5))

    @staticmethod
    def _embed(game):
        selected = game["member_by_id"].get(game["selected_id"])
        active_count = len(game["active_ids"])
        embed = discord.Embed(
            title="🕵️ لعبة الاختباء",
            description=(
                f"🎯 **يا {selected.mention if selected else 'اللاعب'}** اختر أحد الأزرار لطرد لاعب.\n\n"
                "اضغط على رقم واحد فقط، وإذا كان خلفه لاعب سيتم طرده، "
                "وإذا كان فارغاً يصبح الزر أحمر.\n\n"
                f"👥 المتبقون: **{active_count}**\n"
                + (
                    f"💰 الجائزة: **{game['amount']:,} طولار**"
                    if game["amount"] > 0 else "🎁 **بدون جائزة مالية**"
                )
            ),
            color=discord.Color.from_rgb(184, 145, 55),
        )
        return embed

    def _apply_button_states(self):
        for child in self.children:
            if not isinstance(child, HideNumberButton):
                continue
            state = ACTIVE_HIDE_GAMES.get(self.game_id, {}).get("buttons", {}).get(child.number)
            if state == "green":
                child.style = discord.ButtonStyle.success
                child.disabled = True
            elif state == "red":
                child.style = discord.ButtonStyle.danger
                child.disabled = True
            else:
                child.style = discord.ButtonStyle.secondary
                child.disabled = False

    async def send_new_round(self, interaction, first=False):
        game = ACTIVE_HIDE_GAMES.get(self.game_id)
        if not game:
            return
        self._apply_button_states()
        embed = self._embed(game)
        new_message = await interaction.followup.send(
            embed=embed,
            view=self,
            wait=True,
        )
        self.message = new_message
        game["message"] = new_message
        game["view"] = self

    async def update_message(self, interaction):
        game = ACTIVE_HIDE_GAMES.get(self.game_id)
        if not game:
            return
        self._apply_button_states()
        embed = self._embed(game)
        if self.message is None:
            self.message = interaction.message
        game["message"] = self.message
        game["view"] = self
        await self.message.edit(embed=embed, view=self)

    @staticmethod
    async def finish_game(game_id, interaction):
        game = ACTIVE_HIDE_GAMES.pop(game_id, None)
        if not game:
            return

        winner_id = next(iter(game["active_ids"]), None)
        winner = game["member_by_id"].get(winner_id)
        if winner is None:
            return

        for member in game["players"]:
            ACTIVE_HIDE_USERS.discard(member.id)

        if game["amount"] > 0:
            add_balance(winner.id, game["amount"])

        try:
            await interaction.message.edit(view=None)
        except Exception:
            pass

        avatar_bytes = None
        try:
            avatar_bytes = await winner.display_avatar.read()
        except Exception:
            pass

        img_buf = None
        try:
            img_buf = await _run_bg(
                draw_hide_result,
                avatar_bytes,
                winner.display_name,
                game["amount"],
            )
            file = discord.File(img_buf, filename="hide_result.png")
            embed = discord.Embed(
                title="🏆 نهاية لعبة الاختباء",
                description=(
                    f"🎉 **الفائز: {winner.mention}**\n\n"
                    + (
                        f"💰 تمت إضافة **{game['amount']:,} طولار** إلى رصيد الفائز."
                        if game["amount"] > 0
                        else "🎁 انتهت اللعبة بدون جائزة مالية."
                    )
                ),
                color=discord.Color.from_rgb(232, 198, 106),
            )
            embed.set_image(url="attachment://hide_result.png")
            embed.set_footer(text=f"عدد المشاركين: {len(game['players'])}")
            await interaction.followup.send(embed=embed, file=file, wait=True)
        finally:
            if img_buf is not None:
                img_buf.close()

    async def on_timeout(self):
        # قد تبقى Views قديمة في الذاكرة بعد الانتقال لجولة جديدة.
        # لا نسمح لـ View قديم بإلغاء لعبة ما زالت تعمل.
        game = ACTIVE_HIDE_GAMES.get(self.game_id)
        if not game or game.get("view") is not self:
            return

        ACTIVE_HIDE_GAMES.pop(self.game_id, None)
        if game["amount"] > 0:
            add_balance(game["host"].id, game["amount"])
        for member in game["players"]:
            ACTIVE_HIDE_USERS.discard(member.id)
        if self.message:
            try:
                await self.message.edit(
                    content=(
                        "⏰ انتهت لعبة الاختباء بسبب انتهاء وقت التفاعل."
                        + (
                            " تمت إعادة الجائزة لصاحب اللعبة."
                            if game["amount"] > 0 else ""
                        )
                    ),
                    embed=None,
                    attachments=[],
                    view=None,
                )
            except Exception:
                pass


@bot.command(name="اختباء")
@in_channel(GAMES_CHANNEL_ID)
async def hide_game(ctx, amount_text=None):
    """الاستخدام: اختباء أو اختباء 1000."""
    if amount_text is None:
        amount = 0
    else:
        amount = _roulette_number(amount_text)
        if amount is None:
            return await ctx.send(
                "❌ الاستخدام الصحيح: `اختباء` أو `اختباء 1000` — المبلغ يجب أن يكون رقماً أكبر من صفر.",
                delete_after=5,
            )

    host_id = ctx.author.id
    if host_id in ACTIVE_HIDE_USERS:
        return await ctx.send("❌ لديك لعبة اختباء مفتوحة بالفعل.", delete_after=4)

    balance = get_balance(host_id)
    if amount > 0 and balance < amount:
        return await ctx.send(
            f"❌ رصيدك غير كافٍ. تحتاج إلى **{amount:,} طولار** "
            f"ورصيدك الحالي **{balance:,}** طولار.",
            delete_after=5,
        )

    if amount > 0:
        remove_balance(host_id, amount)

    game_id = f"hide:{ctx.channel.id}:{ctx.message.id}:{host_id}"
    game = {
        "id": game_id,
        "host": ctx.author,
        "amount": amount,
        "players": [ctx.author],
        "member_by_id": {host_id: ctx.author},
        "choices": {},
        "taken": {},
        "started": False,
        "selected_id": None,
        "active_ids": set(),
        "buttons": {},
        "eliminated": [],
        "message": None,
        "view": None,
        "lock": asyncio.Lock(),
    }
    ACTIVE_HIDE_GAMES[game_id] = game
    ACTIVE_HIDE_USERS.add(host_id)

    view = HideLobbyView(game_id)
    img_buf = None
    try:
        img_buf = await _run_bg(
            draw_hide_lobby,
            amount,
            game["players"],
            ctx.author,
        )
        file = discord.File(img_buf, filename="hide_lobby.png")
        view.message = await ctx.send(
            file=file,
            view=view,
            allowed_mentions=discord.AllowedMentions(users=False),
        )
        game["message"] = view.message
    except Exception:
        ACTIVE_HIDE_GAMES.pop(game_id, None)
        ACTIVE_HIDE_USERS.discard(host_id)
        if amount > 0:
            add_balance(host_id, amount)
        raise
    finally:
        if img_buf is not None:
            img_buf.close()


# ==========================================
# 🧠 لعبة تذكّر مكان الإيموجي
# ==========================================

EMOJI_MEMORY_ACTIVE = set()

# نطاقات شائعة للإيموجيات الملوّنة/الرموز التعبيرية.
_EMOJI_RANGES = (
    (0x1F000, 0x1FAFF),
    (0x2300, 0x23FF),
    (0x2600, 0x27BF),
    (0x2B00, 0x2BFF),
    (0x3030, 0x303F),
    (0x3297, 0x3299),
)

_EMOJI_EXTRA = {0x00A9, 0x00AE, 0x203C, 0x2049, 0x2122, 0x2139}


def _contains_unicode_emoji(value: str) -> bool:
    """يتحقق من وجود إيموجي Unicode واحد على الأقل."""
    return any(
        (start <= ord(ch) <= end) or ord(ch) in _EMOJI_EXTRA
        for ch in value
    )


def _is_single_emoji_message(content: str) -> bool:
    """
    لا نبدأ اللعبة إلا إذا كانت الرسالة عبارة عن إيموجي واحد فقط
    (مع السماح بـ variation selector و ZWJ وعلامات ألوان البشرة).
    يدعم أيضاً Custom Emoji بصيغة Discord.
    """
    content = content.strip()
    if not content:
        return False

    # Custom Emoji: <:name:id> أو <a:name:id>
    if re.fullmatch(r"<a?:\w+:\d+>", content):
        return True

    # Unicode Emoji: نحذف الرموز الملحقة المعتادة ثم نتحقق من بقاء
    # قاعدة إيموجي واحدة فقط.
    base_chars = [
        ch for ch in content
        if ord(ch) not in {0xFE0E, 0xFE0F, 0x200D}
        and not (0x1F3FB <= ord(ch) <= 0x1F3FF)
    ]
    if len(base_chars) == 1:
        return _contains_unicode_emoji(base_chars[0])

    # بعض الإيموجيات تتكون من زوج من الرموز مثل أعلام الدول.
    if len(base_chars) == 2 and all(0x1F1E6 <= ord(ch) <= 0x1F1FF for ch in base_chars):
        return True

    return False


def _emoji_button_data(emoji: str):
    """يعيد البيانات اللازمة لزر Discord سواء كان Unicode أو Custom Emoji."""
    if re.fullmatch(r"<a?:\w+:\d+>", emoji):
        match = re.fullmatch(r"<(a?):(\w+):(\d+)>", emoji)
        animated, name, emoji_id = match.groups()
        return discord.PartialEmoji(
            name=name,
            id=int(emoji_id),
            animated=bool(animated),
        )
    return emoji


class EmojiMemoryView(discord.ui.View):
    def __init__(self, player_id: int, target_emoji: str, target_index: int, cells):
        super().__init__(timeout=30)
        self.player_id = player_id
        self.target_emoji = target_emoji
        self.target_index = target_index
        self.cells = cells
        self.message = None
        self.answered = False
        self.revealed = False

        for index, emoji in enumerate(cells):
            button = discord.ui.Button(
                label=str(index + 1),
                style=discord.ButtonStyle.secondary,
                emoji=_emoji_button_data(emoji),
                row=index // 3,
            )
            button.custom_id = f"emoji_memory:{player_id}:{index}"

            async def callback(interaction: discord.Interaction, idx=index):
                await self.choose(interaction, idx)

            button.callback = callback
            self.add_item(button)

    async def choose(self, interaction: discord.Interaction, index: int):
        if interaction.user.id != self.player_id:
            await interaction.response.send_message(
                "❌ هذه اللعبة ليست لك.",
                ephemeral=True,
            )
            return

        if self.answered:
            await interaction.response.send_message(
                "ℹ️ لقد أجبت على هذه الجولة بالفعل.",
                ephemeral=True,
            )
            return

        self.answered = True
        self.stop()
        EMOJI_MEMORY_ACTIVE.discard(self.player_id)

        correct = index == self.target_index
        if correct:
            add_balance(self.player_id, 30)
            title = "🎉 إجابة صحيحة!"
            description = (
                f"أحسنت! كان **{self.target_emoji}** في المكان **{self.target_index + 1}**.\n"
                "💰 حصلت على **30 طولار**."
            )
            color = discord.Color.green()
        else:
            # لا نسمح بانخفاض الرصيد تحت الصفر.
            current_balance = get_balance(self.player_id)
            penalty = min(10, max(0, current_balance))
            if penalty:
                remove_balance(self.player_id, penalty)

            title = "❌ إجابة خاطئة!"
            description = (
                f"كان **{self.target_emoji}** في المكان **{self.target_index + 1}**.\n"
                f"💸 تم خصم **{penalty} طولار** من رصيدك."
            )
            color = discord.Color.red()

        for child in self.children:
            child.disabled = True

        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
        )
        embed.add_field(
            name="الإيموجي المطلوب",
            value=self.target_emoji,
            inline=True,
        )
        embed.add_field(
            name="المكان الصحيح",
            value=f"الزر رقم **{self.target_index + 1}**",
            inline=True,
        )
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        if self.answered:
            return

        self.answered = True
        EMOJI_MEMORY_ACTIVE.discard(self.player_id)

        current_balance = get_balance(self.player_id)
        penalty = min(10, max(0, current_balance))
        if penalty:
            remove_balance(self.player_id, penalty)

        for child in self.children:
            child.disabled = True

        if self.message:
            embed = discord.Embed(
                title="⏰ انتهى الوقت!",
                description=(
                    f"كان **{self.target_emoji}** في المكان **{self.target_index + 1}**.\n"
                    f"💸 تم خصم **{penalty} طولار** من رصيدك."
                ),
                color=discord.Color.red(),
            )
            try:
                await self.message.edit(embed=embed, view=self)
            except Exception:
                pass


async def start_emoji_memory_game(message: discord.Message, target_emoji: str = None):
    player_id = message.author.id

    if player_id in EMOJI_MEMORY_ACTIVE:
        return

    # إذا لم يُحدَّد إيموجي صراحةً، تختار اللعبة إيموجياً عشوائياً.
    emoji_pool = [
        "😀", "😂", "😎", "🥳", "😈", "🤖", "👻", "🐼",
        "🦊", "🐸", "🐵", "🐯", "🦄", "🐙", "🍕", "🍔",
        "⚽", "🏀", "🎮", "🚀", "⭐", "🔥", "💎", "🌙",
        "🍉", "🍓", "🍩", "🎯", "🎲", "🎁",
    ]
    if target_emoji is None:
        target = random.choice(emoji_pool)
    else:
        target = target_emoji.strip()
        if not _is_single_emoji_message(target):
            return

    emoji_pool = [e for e in emoji_pool if e != target]
    EMOJI_MEMORY_ACTIVE.add(player_id)

    random.shuffle(emoji_pool)
    cells = emoji_pool[:8] + [target]
    random.shuffle(cells)
    target_index = cells.index(target)

    view = EmojiMemoryView(
        player_id=player_id,
        target_emoji=target,
        target_index=target_index,
        cells=cells,
    )

    embed = discord.Embed(
        title="🧠 حاول أن تتذكر مكان الإيموجيات",
        description=(
            "احفظ أماكن الإيموجيات جيداً!\n\n"
            "بعد **3 ثوانٍ** ستختفي الإيموجيات، وسأسألك عن مكان الإيموجي الذي كتبته."
        ),
        color=discord.Color.blurple(),
    )
    embed.add_field(
        name="الإيموجيات",
        value="  ".join(f"**{i + 1}.** {emoji}" for i, emoji in enumerate(cells)),
        inline=False,
    )
    embed.set_footer(text="⏳ تذكّر الأماكن...")

    try:
        sent = await message.channel.send(
            embed=embed,
            view=view,
            allowed_mentions=discord.AllowedMentions(users=False),
        )
        view.message = sent

        await asyncio.sleep(3)

        if view.answered:
            return

        # بعد 3 ثوانٍ: نخفي الإيموجيات من نص الأزرار، ونُبقي الأرقام
        # حتى يختار اللاعب مكان الإيموجي الذي كتبه.
        for child in view.children:
            if isinstance(child, discord.ui.Button):
                child.emoji = None
                child.label = str(
                    int(child.custom_id.rsplit(":", 1)[-1]) + 1
                )

        question_embed = discord.Embed(
            title="🧠 أين مكان الإيموجي؟",
            description=(
                f"أين كان الإيموجي **{target}**؟\n\n"
                "اختر رقم المكان الصحيح من الأزرار بالأسفل."
            ),
            color=discord.Color.gold(),
        )
        question_embed.set_footer(text="⏱️ لديك 30 ثانية للإجابة")

        await sent.edit(embed=question_embed, view=view)

    except Exception:
        EMOJI_MEMORY_ACTIVE.discard(player_id)
        raise


@bot.event
async def on_message(message):
    """معالجة الردود التلقائية والإيموجيات/الستيكرات ثم تمرير الرسالة للأوامر.

    مهم: يجب استدعاء process_commands حتى عند حدوث خطأ في أي جزء من
    معالجة الرسالة، وإلا فإن أوامر @bot.command لن تعمل.
    """
    if message.author.bot:
        await bot.process_commands(message)
        return

    try:
        # لعبة تذكّر مكان الإيموجي: تعمل عند كتابة كلمة "ايموجي" بالضبط.
        # يتم اختيار الإيموجي الهدف عشوائياً داخل اللعبة.
        if message.content.strip().lower() == "ايموجي":
            await start_emoji_memory_game(message)
            return

        # 1. ردود الكلمات
        content = message.content.strip()
        for reply in replies_cache["word"]:
            trigger = str(reply.get("trigger", ""))
            if trigger and trigger.lower() in content.lower():
                if reply.get("type") == "text":
                    await message.reply(reply.get("value", ""))
                elif reply.get("type") == "reaction":
                    try:
                        emoji = reply.get("value", "")
                        if str(emoji).isdigit():
                            emoji = discord.PartialEmoji(id=int(emoji))
                        await message.add_reaction(emoji)
                    except Exception as e:
                        print(f"[AUTO-REPLY REACTION ERROR] {type(e).__name__}: {e}")

        # 2. ردود الأعضاء (عند المنشن)
        if message.mentions:
            for member in message.mentions:
                uid = str(member.id)
                if uid in replies_cache["member"]:
                    for reply in replies_cache["member"][uid]:
                        if reply.get("type") == "text":
                            await message.reply(reply.get("value", ""))
                        elif reply.get("type") == "reaction":
                            try:
                                emoji = reply.get("value", "")
                                if str(emoji).isdigit():
                                    emoji = discord.PartialEmoji(id=int(emoji))
                                await message.add_reaction(emoji)
                            except Exception as e:
                                print(f"[AUTO-REPLY MEMBER REACTION ERROR] {type(e).__name__}: {e}")
                    break  # نكتفي بأول عضو تم منشنته

        # 3. تكبير الإيموجيات والستيكرات في روم الافتار
        if message.channel.id == THEFT_CHANNEL_ID:
            # discord.py لا يوفّر message.custom_emojis.
            # نستخرج Custom Emojis من محتوى الرسالة بصيغة Discord القياسية.
            custom_emojis = re.findall(
                r"<(?P<animated>a?):(?P<name>\w+):(?P<id>\d+)>",
                message.content,
            )

            if custom_emojis:
                animated, _name, emoji_id = custom_emojis[0]
                extension = "gif" if animated else "png"
                emoji_url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{extension}"
                await enlarge_and_send(message.channel, emoji_url, "emoji")

            # معالجة الستيكرات
            if message.stickers:
                sticker = message.stickers[0]
                await enlarge_and_send(message.channel, sticker.url, "sticker")

    except Exception as e:
        # لا نسمح لخطأ في الردود التلقائية أو الإيموجيات بمنع الأوامر.
        print(f"[ON_MESSAGE ERROR] {type(e).__name__}: {e}")
    finally:
        # هذا الاستدعاء ضروري لأننا نستخدم on_message مخصصًا.
        await bot.process_commands(message)


# تحديث الكاش عند الإطلاق/إعادة الاتصال.
@bot.event
async def on_ready():
    global replies_cache
    replies_cache = load_replies()
    print(
        f"✅ Bot is ready! Logged in as {bot.user} "
        f"| تم تحميل {len(replies_cache['member'])} عضو و {len(replies_cache['word'])} رد كلمة."
    )
    bot.add_view(TicketView())
    bot.add_view(TicketDeleteView())


# تشغيل البوت باستخدام متغير بيئة على Render.
# لا تضع التوكن داخل الملف حتى لا يتسرب إلى GitHub أو الملفات المرفوعة.
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
if not DISCORD_TOKEN:
    raise RuntimeError(
        "❌ لم يتم العثور على DISCORD_TOKEN. "
        "أضف متغير البيئة DISCORD_TOKEN في Render > Environment."
    )

bot.run(DISCORD_TOKEN)
