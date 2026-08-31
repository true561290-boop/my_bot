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
from pathlib import Path
import aiohttp
import discord
from discord.ext import commands
from flask import Flask
from PIL import Image, ImageDraw, ImageFont
import requests

# Run PIL/economy heavy operations in a separate thread to avoid blocking the event loop
async def _run_bg(func, *args):
    return await asyncio.to_thread(func, *args)


# ==========================================
# ⚡ Fast in‑memory cache with TTL and max size
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


# We don't cache balances for long to avoid showing old balances.
# The cache here is for images and drawing results, with a short TTL for final results.
_SHOP_HOME_CACHE = _TTLCache(maxsize=1, ttl=1800)
_SHOP_CATEGORY_CACHE = _TTLCache(maxsize=64, ttl=300)
_BALANCE_AVATAR_CACHE = _TTLCache(maxsize=512, ttl=300)
_BALANCE_CARD_CACHE = _TTLCache(maxsize=512, ttl=10)
_ROULETTE_LOBBY_CACHE = _TTLCache(maxsize=128, ttl=300)
_ROULETTE_WHEEL_CACHE = _TTLCache(maxsize=256, ttl=300)


async def _cache_cleanup_loop():
    """Periodically clean expired caches without blocking the event loop."""
    while True:
        try:
            await asyncio.sleep(300)  # every 5 minutes
            for cache in (
                _SHOP_HOME_CACHE,
                _SHOP_CATEGORY_CACHE,
                _BALANCE_AVATAR_CACHE,
                _BALANCE_CARD_CACHE,
            ):
                cache.cleanup()

            # The role icon cache is a plain dict; only clear if it grows abnormally.
            visual_cache = globals().get("_SHOP_VISUAL_CACHE")
            if isinstance(visual_cache, dict) and len(visual_cache) > 512:
                # keep the most recent 512 entries instead of clearing everything
                for key in list(visual_cache)[:-512]:
                    visual_cache.pop(key, None)

            gc.collect()
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"⚠️ Cache cleanup error: {e}")

# Import the separate economy system
from economy import (
    add_balance,
    fetch_latest_balances_from_github,
    get_balance,
    remove_balance,
)

# --- 1. Web server to keep the bot alive 24/7 ---
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

# --- 2. Bot configuration and data ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True


class BILBot(commands.Bot):
    async def setup_hook(self):
        # BetCog is defined later in this file, but setup_hook runs only after
        # the module has finished loading, so the class is available here.
        await self.add_cog(BetCog(self))
        self._cache_cleanup_task = asyncio.create_task(_cache_cleanup_loop())


bot = BILBot(command_prefix="", intents=intents, max_messages=None)
bot.remove_command("help")

WELCOME_CHANNEL_ID = 1515396548392128670
LEVEL_50_ROLE_ID = 1515396547473309712
AVATAR_CHANNEL_ID = 1515396548392128671
OWNER_ROLE_ID = 1515396547528102131
GAMES_CHANNEL_ID = 1515416733102379100
THEFT_CHANNEL_ID = 1532648660997771335
SHOPPING_CHANNEL_ID = 1532645480373420142
AMENDMENTS_CHANNEL_ID = 1541143390224130209
TICKET_CHANNEL_ID = 1515709356723798177

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
                f"❌ This command only works in the designated channel: <#{channel_id}>",
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
                print("✅ Arabic font downloaded successfully!")
        except Exception as e:
            print(f"❌ Failed to download Arabic font: {e}")


ensure_arabic_font()
fetch_latest_balances_from_github()

# ==========================================
# 🎬 Direct Instagram / TikTok video download
# ==========================================
# Uses yt‑dlp to download the video itself, not just change the link.
# Make sure to add yt‑dlp to requirements.txt on the host.
try:
    import yt_dlp
    YTDLP_AVAILABLE = True
except ImportError:
    yt_dlp = None
    YTDLP_AVAILABLE = False
    print("⚠️ yt‑dlp is not installed. Add yt‑dlp to requirements.txt and restart the bot.")

_SOCIAL_VIDEO_RE = re.compile(
    r"https?://(?:www\.)?(?:"
    r"instagram\.com/(?:reel|reels|p|tv|stories)/[^\s<>]+"
    r"|tiktok\.com/[^\s<>]+"
    r"|vm\.tiktok\.com/[^\s<>]+"
    r"|vt\.tiktok\.com/[^\s<>]+"
    r")",
    re.IGNORECASE,
)

_VIDEO_DOWNLOAD_SEMAPHORE = asyncio.Semaphore(2)
_VIDEO_CACHE = _TTLCache(maxsize=24, ttl=180)


def _clean_social_url(url: str) -> str:
    """Clean the URL from punctuation that the user may have added."""
    return url.strip().strip("<>").rstrip(".,!?؛،")


def _download_social_video(url: str):
    """Download a single video in a thread to avoid freezing the Discord event loop."""
    if not YTDLP_AVAILABLE:
        raise RuntimeError("yt‑dlp not installed")

    import tempfile

    with tempfile.TemporaryDirectory(prefix="social_video_") as tmp:
        output_template = os.path.join(tmp, "%(id)s.%(ext)s")

        ydl_opts = {
            "outtmpl": output_template,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "restrictfilenames": True,
            "socket_timeout": 20,
            "retries": 3,
            "fragment_retries": 3,
            "concurrent_fragment_downloads": 4,
            "nocheckcertificate": True,
            "geo_bypass": True,
            "http_headers": {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/145.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
            },
            # Choose a single ready‑to‑use file to avoid ffmpeg dependency.
            # 720p is usually enough for quick delivery to Discord.
            "format": (
                "best[ext=mp4][height<=720]/"
                "best[height<=720]/"
                "best[ext=mp4]/best"
            ),
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

            # Some sites may change the extension after format selection.
            if not os.path.isfile(filename):
                base = os.path.splitext(filename)[0]
                candidates = [
                    filename,
                    base + ".mp4",
                    base + ".webm",
                    base + ".mkv",
                    base + ".mov",
                ]
                filename = next(
                    (candidate for candidate in candidates if os.path.isfile(candidate)),
                    None,
                )

            if not filename:
                files = [p for p in Path(tmp).glob("*") if p.is_file()]
                filename = str(files[0]) if files else None

            if not filename:
                raise FileNotFoundError("yt‑dlp finished without creating a video file")

            data = Path(filename).read_bytes()
            if len(data) > 24 * 1024 * 1024:
                raise ValueError("Video is larger than 24MB")

            ext = Path(filename).suffix.lower().lstrip(".") or "mp4"
            return data, ext


async def _download_and_send_social_video(message: discord.Message, url: str) -> bool:
    """Download the video and upload it to Discord."""
    if not YTDLP_AVAILABLE:
        await message.reply(
            "❌ Instagram/TikTok download feature is not enabled because yt‑dlp is not installed.",
            mention_author=False,
        )
        return False

    url = _clean_social_url(url)

    try:
        async with _VIDEO_DOWNLOAD_SEMAPHORE:
            cached = _VIDEO_CACHE.get(url)
            if cached is None:
                cached = await asyncio.to_thread(_download_social_video, url)
                _VIDEO_CACHE.set(url, cached)

        data, ext = cached
        buf = io.BytesIO(data)
        await message.reply(
            file=discord.File(buf, filename=f"social_video.{ext}"),
            mention_author=False,
        )
        return True

    except Exception as e:
        # Log the real reason to the console so we know if it's Instagram,
        # TikTok, file size, or yt‑dlp version.
        print(f"[SOCIAL VIDEO ERROR] {type(e).__name__}: {e}")
        await message.reply(
            "❌ Failed to download the video. If the video is public and the issue persists, "
            "check the Render console for the specific error.",
            mention_author=False,
        )
        return False

# --- 3. Interactive shop and image drawing ---

SHOP_DATA_FILE = os.path.join(BASE_DIR if "BASE_DIR" in globals() else os.path.dirname(os.path.abspath(__file__)), "shop_data.json")
DEFAULT_COLOR_PRICE = 800
DEFAULT_VIP_PRICE = 1000

# Default values currently in the shop. They will be saved later in shop_data.json
_DEFAULT_SHOP_VIP_ROLES = {}
_DEFAULT_SHOP_COLOR_ROLES = {}

# Shop data version. Incrementing this will reset the shop items once,
# without deleting the roles themselves from the server.
SHOP_DATA_VERSION = 2


SHOP_REDIS_KEY = "shop_data"

def _redis_command(command, *args):
    """Execute an Upstash REST command to persistently store shop data."""
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
    # Any old data without the current version is ignored, so the shop starts empty.
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

    # Primary source: Upstash Redis.
    try:
        result = _redis_command("GET", SHOP_REDIS_KEY)
        if result:
            loaded = _normalize(json.loads(result))
            if loaded is not None:
                return loaded
    except Exception as e:
        print(f"❌ Failed to load shop data from Redis: {e}")

    # Fallback to the local file for compatibility, but we don't restore old items after a version change.
    if os.path.exists(SHOP_DATA_FILE):
        try:
            with open(SHOP_DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            loaded = _normalize(data)
            if loaded is not None:
                return loaded
        except Exception as e:
            print(f"❌ Failed to load shop_data.json: {e}")

    # Start with an empty shop; items are added only through manage_shop.
    vip, colors = {}, {}
    _save_shop_data(vip, colors)
    return vip, colors

def _save_shop_data(vip=None, colors=None):
    vip = SHOP_VIP_ROLES if vip is None else vip
    colors = SHOP_COLOR_ROLES if colors is None else colors
    payload = json.dumps({"version": SHOP_DATA_VERSION, "vip": vip, "colors": colors}, ensure_ascii=False, indent=4)

    # Save to Redis first because it's the persistent storage on the host.
    redis_saved = _redis_command("SET", SHOP_REDIS_KEY, payload)

    # Also save a local copy for when the bot is run locally.
    try:
        with open(SHOP_DATA_FILE, "w", encoding="utf-8") as f:
            f.write(payload)
        local_saved = True
    except Exception as e:
        print(f"❌ Failed to save shop data locally: {e}")
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
                print(f"❌ Failed to open shop background mtgr.png: {e}")
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

    # Title inside the big red box.
    _shop_text(draw, (683, 112), "Royal Shop", 58, fill=(242, 205, 126, 255), max_width=650)

    # Section names inside the two original boxes.
    _shop_text(draw, (458, 260), "Roles", 43, fill=(74, 43, 27, 255), max_width=430)
    _shop_text(draw, (980, 260), "Wavy Colors", 38, fill=(74, 43, 27, 255), max_width=470)

    out = io.BytesIO()
    base.save(out, format="PNG", optimize=False, compress_level=3)
    out.seek(0)
    data = out.getvalue()
    _SHOP_HOME_CACHE.set("home", data)
    base.close()
    return io.BytesIO(data)


def _draw_wavy_swatch(draw, box, rgb):
    # A slightly larger rectangle to display the role color without the outer wavy lines.
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
        print(f"❌ Failed to draw role badge: {e}")


def draw_shop_category(kind, items, page=0, per_page=6):
    base = _open_shop_background()
    draw = ImageDraw.Draw(base)

    title = "Roles" if kind == "vip" else "Wavy Colors"
    _shop_text(draw, (683, 112), title, 52, fill=(242, 205, 126, 255), max_width=650)

    # A dark overlay over the card area to keep them readable against the background.
    draw.rounded_rectangle((45, 185, 1320, 735), radius=28, fill=(28, 23, 18, 120), outline=(205, 159, 86, 150), width=3)

    # _render_shop_category passes only the items for the current page,
    # so we don't slice again here. Reusing 'page' here would make page 2+ empty.
    visible = items
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
            # The badge appears inside the card if the role has one.
            _paste_role_badge(base, visual.get("badge"), (x1 + 72, center_y), 82)
            name_x = x1 + 330
        else:
            rgb = visual.get("rgb", (128, 128, 128))
            _draw_wavy_swatch(draw, (x1 + 30, center_y - 38, x1 + 140, center_y + 38), rgb)
            name_x = x1 + 330

        _shop_text(draw, (name_x, center_y - 19), item["name"], 31, fill=(69, 42, 27, 255), max_width=360)
        _shop_text(draw, (name_x, center_y + 34), f"{int(item['price']):,} Tolar", 25, fill=(100, 60, 31, 255), max_width=330)

    if not visible:
        _shop_text(draw, (683, 450), "No items added yet", 38, fill=(242, 205, 126, 255))

    out = io.BytesIO()
    base.save(out, format="PNG", optimize=False, compress_level=3)
    out.seek(0)
    base.close()
    return out


# Cache for role icons to avoid reloading them when navigating shop pages.
# Value: (current icon URL, image data or None)
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

    # If the icon is already cached and hasn't changed, use it directly.
    cached = _SHOP_VISUAL_CACHE.get(cache_key)
    if cached is not None and cached[0] == icon_url:
        return {"badge": cached[1], "rgb": rgb}

    if icon_url:
        try:
            # 3 seconds is enough for a small image; we don't want to wait 8 seconds per role.
            timeout = aiohttp.ClientTimeout(total=3)
            async with session.get(icon_url, timeout=timeout) as resp:
                if resp.status == 200:
                    badge = await resp.read()
        except Exception as e:
            print(f"⚠️ Failed to load badge for role {role.id}: {e}")

    # Store even the failure so we don't repeat the request on every click.
    _SHOP_VISUAL_CACHE[cache_key] = (icon_url, badge)
    return {"badge": badge, "rgb": rgb}


async def _fetch_shop_visuals(guild, items):
    # Load role images in parallel instead of waiting for each one sequentially.
    async with aiohttp.ClientSession() as session:
        return await asyncio.gather(
            *(_fetch_one_shop_visual(session, guild, item) for item in items)
        )


async def _render_shop_category(guild, kind, page=0):
    data = SHOP_VIP_ROLES if kind == "vip" else SHOP_COLOR_ROLES
    items = list(data.values())
    start = page * 6
    page_items = items[start:start + 6]

    # The cache key automatically changes when a role's name/price/id/color changes.
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
# 🎨 PIL helpers – updated bet command
# ==========================================

# Bet system backgrounds – read from the same folder as the bot so it works both locally and on the host
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHALLENGE_BASE_IMG = os.path.join(BASE_DIR, "bet_challenge_2.jpg")
RESULT_BASE_IMG = os.path.join(BASE_DIR, "bet_result_2.jpg")

# Russian roulette game files
RUSSIAN_ROULETTE_GUN_GIF = os.path.join(BASE_DIR, "gun.gif")
RUSSIAN_ROULETTE_RESULT_GIF = os.path.join(BASE_DIR, "rolet2.gif")
RUSSIAN_ROULETTE_BACKGROUND = os.path.join(BASE_DIR, "roulette_background.jpg")
RUSSIAN_ROULETTE_STEP = 50
RUSSIAN_ROULETTE_CHAMBERS = 6

# Balance card background
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
        print(f"[BET] Failed to open background {path}: {e}")
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
    """Choose the largest font size that allows the text to fit within the given width."""
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
    Draws a balance card at the original background resolution 1640x656:
    - Avatar centered inside the black circle without covering the decorative frame.
    - Balance centered inside the rectangle provided in the design.
    - Member name inside the name box above the avatar.
    """
    # Original background 1640x656, so we use its coordinates directly
    base = _open_base(BALANCE_BASE_IMG, (1640, 656)).resize(
        (1640, 656), Image.Resampling.LANCZOS
    )
    draw = ImageDraw.Draw(base)

    # =========================
    # Avatar – real circle center in the background
    # =========================
    avatar_size = 296
    avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")

    # Crop a square from the middle of the avatar to avoid distortion
    side = min(avatar.width, avatar.height)
    left = (avatar.width - side) // 2
    top = (avatar.height - side) // 2
    avatar = avatar.crop((left, top, left + side, top + side))
    avatar = avatar.resize((avatar_size, avatar_size), Image.Resampling.LANCZOS)

    avatar_mask = Image.new("L", (avatar_size, avatar_size), 0)
    ImageDraw.Draw(avatar_mask).ellipse(
        (0, 0, avatar_size - 1, avatar_size - 1), fill=255
    )

    # Center of the black circle in mora-card-Dragon.jpg
    circle_center = (291, 328)
    avatar_x = circle_center[0] - avatar_size // 2
    avatar_y = circle_center[1] - avatar_size // 2
    base.paste(avatar, (avatar_x, avatar_y), avatar_mask)

    # =========================
    # Member name box
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

    clean_name = str(member_name).strip() or "Member"
    name_font = _fit_font(clean_name, 350, start_size=42, min_size=22)
    draw.text(
        ((name_box[0] + name_box[2]) // 2, (name_box[1] + name_box[3]) // 2),
        clean_name,
        fill=(232, 198, 106, 255),
        font=name_font,
        anchor="mm",
    )

    # =========================
    # Balance – inside the original rectangle
    # =========================
    balance_text = f"{balance:,} Tolar"
    balance_font = _fit_font(balance_text, 500, start_size=43, min_size=22)

    # Approximate center of the rectangle in the design: (968, 274)
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
    # Circle centers in bet_challenge_2.jpg
    base.paste(av1, (104, 116), av1)
    base.paste(av2, (719, 116), av2)
    draw = ImageDraw.Draw(base)
    name_font = _font(25)
    amount_font = _font(25)
    draw.text((203, 337), p1_name[:18], fill="white", font=name_font, anchor="mm")
    draw.text((818, 337), p2_name[:18], fill="white", font=name_font, anchor="mm")
    draw.text((512, 345), f"Bet: {amount:,} Tolar", fill="#E8C66A", font=amount_font, anchor="mm")
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
    draw.text((503, 74), "Bet Result", fill="white", font=box_font, anchor="mm")
    draw.text((801, 118), "Winner", fill="#E8C66A", font=box_font, anchor="mm")
    draw.text((193, 337), loser_name[:18], fill="white", font=name_font, anchor="mm")
    draw.text((801, 337), winner_name[:18], fill="#E8C66A", font=name_font, anchor="mm")
    draw.text((512, 262), f"Prize: {prize:,} Tolar", fill="#E8C66A", font=title_font, anchor="mm")
    draw.text((193, 399), f"Balance: {loser_bal:,}", fill="#E57373", font=info_font, anchor="mm")
    draw.text((801, 399), f"Balance: {winner_bal:,}", fill="#81C784", font=info_font, anchor="mm")
    out = io.BytesIO()
    base.save(out, format="PNG")
    out.seek(0)
    base.close()
    return out

def generate_wheel_gif(p1_name, p2_name, winner_index):
    # Fully self‑contained wheel: half blue, half red, no external image.
    size = 600
    center = (300, 300)
    radius = 245
    frames = []
    total_frames = 20
    # Fixed pointer at the top; we rotate the two wedges beneath it.
    # PIL: 270° = top. Place the winner wedge centre under the pointer.
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
        # Wheel centre
        d.ellipse((245,245,355,355), fill="#151922", outline="#E8C66A", width=5)
        d.text(center, "VS", fill="#E8C66A", font=_font(34), anchor="mm")
        # Fixed names inside the wedges, rotating with the wheel
        for text, mid, fill in ((p1_name[:14], a+90, "white"), (p2_name[:14], a+270, "white")):
            rad = math.radians(mid)
            x = center[0] + 145 * math.cos(rad)
            y = center[1] + 145 * math.sin(rad)
            d.text((x, y), text, fill=fill, font=name_font, anchor="mm")
        # Top pointer
        d.polygon([(284,18),(316,18),(300,48)], fill="#E8C66A")
        frames.append(frame.convert("P", palette=Image.Palette.ADAPTIVE))

    out = io.BytesIO()
    frames[0].save(out, format="GIF", 
save_all=True, append_images=frames[1:], duration=50, loop=0, disposal=2)
    out.seek(0)
    
    # Free all frames from RAM
    for f in frames:
        f.close()
        
    return out

# ==========================================
# 🎮 Interactive challenge buttons (View)
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
            return await interaction.response.send_message("❌ This challenge is not for you", ephemeral=True)

        self.accepted = True
        # We don't delete the message here; the bet command will turn the same message into the wheel.
        # Deleting it here would cause msg.edit to fail after acceptance.
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="Decline ✖️", style=discord.ButtonStyle.red)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.opponent.id:
            return await interaction.response.send_message("❌ This challenge is not for you", ephemeral=True)
        self.accepted = False
        self.stop()
        await interaction.response.send_message(f"❌ {self.opponent.mention} declined the challenge.")


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
        super().__init__(label="Back to Shop", style=discord.ButtonStyle.secondary, emoji="🔙")

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
        start = page * 6
        page_items = items[start:start + 6]
        options = [
            discord.SelectOption(
                label=str(item["name"])[:100],
                value=key,
                description=f"Price: {int(item['price']):,} Tolar",
            )
            for key, item in page_items
        ]
        if not options:
            options = [discord.SelectOption(label="No colors added", value="none")]
        super().__init__(placeholder="Choose a color to buy...", min_values=1, max_values=1, options=options, disabled=not page_items)

    async def callback(self, interaction: discord.Interaction):
        selected_key = self.values[0]
        if selected_key == "none":
            return await interaction.response.send_message("ℹ️ No colors are currently available.", ephemeral=True)
        item = SHOP_COLOR_ROLES.get(selected_key)
        if not item:
            return await interaction.response.send_message("❌ This color is no longer in the shop.", ephemeral=True)
        user = interaction.user
        guild = interaction.guild
        role = guild.get_role(int(item["id"]))
        if not role:
            return await interaction.response.send_message("❌ The role does not exist on the server, please contact an admin.", ephemeral=True)
        if role in user.roles:
            return await interaction.response.send_message(f"⚠️ You already have the **{role.name}** role.", ephemeral=True)
        if get_balance(user.id) < item["price"]:
            return await interaction.response.send_message(f"❌ You don't have enough Tolar, you need **{item['price']}** Tolar.", ephemeral=True)

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
            f"✅ **Purchase successful!** You received the **{role.name}** role for **{item['price']}** Tolar.\n*(The shop has been closed)*",
            ephemeral=True,
        )


class VIPSelect(discord.ui.Select):
    def __init__(self, page=0):
        self.page = page
        items = list(SHOP_VIP_ROLES.items())
        start = page * 6
        page_items = items[start:start + 6]
        options = [
            discord.SelectOption(
                label=str(item["name"])[:100],
                value=key,
                description=f"Price: {int(item['price']):,} Tolar",
            )
            for key, item in page_items
        ]
        if not options:
            options = [discord.SelectOption(label="No roles added", value="none")]
        super().__init__(placeholder="Choose a role to buy...", min_values=1, max_values=1, options=options, disabled=not page_items)

    async def callback(self, interaction: discord.Interaction):
        selected_key = self.values[0]
        if selected_key == "none":
            return await interaction.response.send_message("ℹ️ No roles are currently available.", ephemeral=True)
        item = SHOP_VIP_ROLES.get(selected_key)
        if not item:
            return await interaction.response.send_message("❌ This role is no longer in the shop.", ephemeral=True)
        user = interaction.user
        guild = interaction.guild
        role = guild.get_role(int(item["id"]))
        if not role:
            return await interaction.response.send_message("❌ The role does not exist on the server, please contact an admin.", ephemeral=True)
        if role in user.roles:
            return await interaction.response.send_message(f"⚠️ You already have the **{role.name}** role.", ephemeral=True)
        if get_balance(user.id) < item["price"]:
            return await interaction.response.send_message(f"❌ You don't have enough Tolar, you need **{item['price']}** Tolar.", ephemeral=True)
        remove_balance(user.id, item["price"])
        await user.add_roles(role)
        for child in self.view.children:
            child.disabled = True
        await interaction.message.edit(view=self.view)
        await interaction.response.send_message(
            f"✅ **Purchase successful!** You received the **{role.name}** role for **{item['price']}** Tolar.\n*(The shop has been closed)*",
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
            prev = discord.ui.Button(label="Previous", style=discord.ButtonStyle.secondary, emoji="◀️", disabled=self.page <= 0, row=1)
            next_btn = discord.ui.Button(label="Next", style=discord.ButtonStyle.secondary, emoji="▶️", disabled=self.page >= total_pages - 1, row=1)

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
            discord.SelectOption(label="Roles", value="cat_vip", description="View roles added to the shop"),
            discord.SelectOption(label="Wavy Colors", value="cat_colors", description="View wavy colors added to the shop"),
        ]
        super().__init__(placeholder="Choose a shop section...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        # We must acknowledge the interaction within seconds.
        # defer() prevents the "didn't respond in time" error while the shop image is being prepared.
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
# 🛠️ Dynamic shop management
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
        title="🛠️ Shop Management",
        description="Add roles to the shop and they will automatically appear in the shop cards with price and badge/color.",
        color=discord.Color.gold(),
    )
    vip_lines = []
    for item in SHOP_VIP_ROLES.values():
        role = guild.get_role(int(item["id"]))
        vip_lines.append(f"{role.mention if role else '❌ Deleted role'} — **{int(item['price']):,}** Tolar")
    color_lines = []
    for item in SHOP_COLOR_ROLES.values():
        role = guild.get_role(int(item["id"]))
        color_lines.append(f"{role.mention if role else '❌ Deleted role'} — **{int(item['price']):,}** Tolar")
    embed.add_field(name=f"👑 Roles ({len(SHOP_VIP_ROLES)})", value="\n".join(vip_lines)[:1024] or "No roles in the shop.", inline=False)
    embed.add_field(name=f"🎨 Wavy Colors ({len(SHOP_COLOR_ROLES)})", value="\n".join(color_lines)[:1024] or "No colors in the shop.", inline=False)
    embed.set_footer(text="The add button asks for a role mention and price. Roles are not deleted from the server, only removed from the shop.")
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
            role_type = "Color" if kind == "color" else "Role"
            options.append(discord.SelectOption(label=str(item["name"])[:100], value=f"{kind}|{key}", description=f"{role_type} • {int(item['price']):,} Tolar"[:100]))
        if not options:
            options = [discord.SelectOption(label="No items to delete", value="none")]
        super().__init__(placeholder="Choose a role or color to delete...", min_values=1, max_values=1, options=options, disabled=not page_items)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.manager_id:
            return await interaction.response.send_message("❌ This menu is not for you.", ephemeral=True)
        value = self.values[0]
        if value == "none":
            return await interaction.response.send_message("ℹ️ There are no items in the shop to delete.", ephemeral=True)
        kind, key = value.split("|", 1)
        data = SHOP_COLOR_ROLES if kind == "color" else SHOP_VIP_ROLES
        item = data.get(key)
        if not item:
            return await interaction.response.send_message("❌ This item no longer exists in the shop.", ephemeral=True)
        role = interaction.guild.get_role(int(item["id"]))
        type_name = "color" if kind == "color" else "role"
        role_name = role.mention if role else f"**{item['name']}**"
        view = ShopDeleteConfirmView(self.manager_id, kind, key, role_name, item["name"], type_name, self.page)
        embed = discord.Embed(title="⚠️ Confirm Deletion", description=f"Are you sure you want to delete the {type_name} {role_name} from the shop?\n\n**The role will not be deleted from the server.**", color=discord.Color.red())
        await interaction.response.edit_message(embed=embed, view=view)


class ShopAddTypeView(discord.ui.View):
    def __init__(self, manager_id: int):
        super().__init__(timeout=60)
        self.manager_id = manager_id
        self.message = None

    async def _start_add(self, interaction: discord.Interaction, kind: str):
        if interaction.user.id != self.manager_id:
            return await interaction.response.send_message("❌ This button is not for you.", ephemeral=True)
        type_name = "role" if kind == "vip" else "wavy color"
        await interaction.response.send_message(
            f"📌 **Mention the {type_name} and write the price in the same message.**\n"
            f"Example: `@{type_name} 2000`\n"
            f"It will be saved in the **{type_name}** section. If the Discord role has a Badge/Role Icon, it will automatically appear in the shop card.",
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
                return await interaction.followup.send("❌ The price must be greater than zero.", ephemeral=True)
            if role.is_default():
                return await interaction.followup.send("❌ Cannot add the @everyone role to the shop.", ephemeral=True)
            if role.managed:
                return await interaction.followup.send("❌ Cannot add a Managed role to the shop.", ephemeral=True)
            for data in (SHOP_VIP_ROLES, SHOP_COLOR_ROLES):
                if any(int(x["id"]) == role.id for x in data.values()):
                    return await interaction.followup.send(f"⚠️ The role {role.mention} is already in the shop.", ephemeral=True)

            data = SHOP_COLOR_ROLES if kind == "color" else SHOP_VIP_ROLES
            key = _shop_item_key(role.id, kind)
            data[key] = {"name": role.name, "price": price, "id": role.id}
            if not _save_shop_data():
                data.pop(key, None)
                return await interaction.followup.send("❌ Failed to save shop data.", ephemeral=True)
            try:
                await message.delete()
            except Exception:
                pass
            await interaction.followup.send(f"✅ Saved {type_name} {role.mention} in the shop for **{price:,}** Tolar.", ephemeral=True)
            if self.message:
                view = ShopManagementView(self.manager_id)
                await self.message.edit(embed=_shop_management_embed(interaction.guild), view=view)
                view.message = self.message
        except asyncio.TimeoutError:
            await interaction.followup.send("⏰ Time expired. No item was added.", ephemeral=True)
            if self.message:
                view = ShopManagementView(self.manager_id)
                await self.message.edit(embed=_shop_management_embed(interaction.guild), view=view)
                view.message = self.message

    @discord.ui.button(label="Role", style=discord.ButtonStyle.primary, emoji="👑")
    async def add_vip(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._start_add(interaction, "vip")

    @discord.ui.button(label="Wavy Color", style=discord.ButtonStyle.primary, emoji="🎨")
    async def add_color(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._start_add(interaction, "color")

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="↩️", row=1)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.manager_id:
            return await interaction.response.send_message("❌ This button is not for you.", ephemeral=True)
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
        super().__init__(label="Add Role / Wavy Color", style=discord.ButtonStyle.success, emoji="➕")

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.manager_id:
            return await interaction.response.send_message("❌ This button is not for you.", ephemeral=True)
        embed = discord.Embed(title="➕ Add to Shop", description="Choose the section to add the role to.\n\n👑 **Role** – appears with its name, price, and badge if available.\n🎨 **Wavy Color** – appears in a special card with a matching color box.", color=discord.Color.gold())
        embed.set_footer(text="After choosing the section, mention the role and write the price in the same message.")
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
        delete_button = discord.ui.Button(label=f"Delete {type_name}", style=discord.ButtonStyle.danger, emoji="🗑️")
        delete_button.callback = self.delete_callback
        self.add_item(delete_button)
        back_button = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="↩️")
        back_button.callback = self.back_callback
        self.add_item(back_button)

    async def delete_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.manager_id:
            return await interaction.response.send_message("❌ This button is not for you.", ephemeral=True)
        data = SHOP_COLOR_ROLES if self.kind == "color" else SHOP_VIP_ROLES
        item = data.pop(self.key, None)
        if not item:
            return await interaction.response.send_message("❌ The item no longer exists in the shop.", ephemeral=True)
        if not _save_shop_data():
            data[self.key] = item
            return await interaction.response.send_message("❌ Failed to save deletion.", ephemeral=True)
        view = ShopManagementView(self.manager_id, page=self.page)
        await interaction.response.edit_message(embed=_shop_management_embed(interaction.guild), view=view)
        view.message = interaction.message

    async def back_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.manager_id:
            return await interaction.response.send_message("❌ This button is not for you.", ephemeral=True)
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
            prev = discord.ui.Button(label="Previous", style=discord.ButtonStyle.secondary, emoji="◀️", disabled=page <= 0)
            next_btn = discord.ui.Button(label="Next", style=discord.ButtonStyle.secondary, emoji="▶️", disabled=page >= total_pages - 1)
            async def prev_callback(interaction):
                if interaction.user.id != self.manager_id:
                    return await interaction.response.send_message("❌ This menu is not for you.", ephemeral=True)
                new_view = ShopManagementView(self.manager_id, self.page - 1)
                await interaction.response.edit_message(embed=_shop_management_embed(interaction.guild), view=new_view)
                new_view.message = interaction.message
            async def next_callback(interaction):
                if interaction.user.id != self.manager_id:
                    return await interaction.response.send_message("❌ This menu is not for you.", ephemeral=True)
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


@bot.command(name="manage_shop")
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
        await ctx.send("❌ This command is only for the Owner role.", delete_after=3)


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


@bot.command(name="shop", aliases=["economy"])
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


# --- 5. Games and quizzes ---

class RPSView(discord.ui.View):

    def __init__(self, player1: discord.Member, player2: discord.Member = None):
        super().__init__(timeout=10)  # ⏱️ 1. Changed timeout to 10 seconds
        self.player1 = player1
        self.player2 = player2
        self.p1_choice = None
        self.p2_choice = None
        self.is_vs_bot = player2 is None
        self.message = None  # 📌 Save the message to update on timeout

    async def on_timeout(self):
        # ⏱️ 2. What happens after 10 seconds without a choice?
        for item in self.children:
            item.disabled = True

        if self.message:
            embed = discord.Embed(
                title="⏰ Time expired",
                description="Game ended because no choice was made within 10 seconds.",
                color=discord.Color.red(),
            )
            await self.message.edit(content=None, embed=embed, view=self)

    async def check_choices(self, interaction: discord.Interaction):
        if self.is_vs_bot:
            self.p2_choice = random.choice(["Rock", "Paper", "Scissors"])
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
                    f"🎮 **Rock Paper Scissors**\n"
                    f"✅ {who_chose} has chosen, waiting for {who_waiting}..."
                )
            )

    async def end_game(self, interaction: discord.Interaction):
        c1, c2 = self.p1_choice, self.p2_choice

        if c1 == c2:
            result = "🤝 **Draw** – no winner."
            color = discord.Color.gold()
        elif (
            (c1 == "Rock" and c2 == "Scissors")
            or (c1 == "Paper" and c2 == "Rock")
            or (c1 == "Scissors" and c2 == "Paper")
        ):
            add_balance(self.player1.id, 40)
            p2_name = "the bot" if self.is_vs_bot else self.player2.mention
            result = f"🎉 **{self.player1.mention} wins against {p2_name} and earns 40 Tolar**"
            color = discord.Color.green()
        else:
            if not self.is_vs_bot:
                add_balance(self.player2.id, 40)
                result = f"🎉 **{self.player2.mention} wins against {self.player1.mention} and earns 40 Tolar**"
                color = discord.Color.green()
            else:
                result = "❌ **You lost – the bot wins.**"
                color = discord.Color.red()

        embed = discord.Embed(title="🎮 Rock Paper Scissors Result", color=color)
        embed.add_field(
            name=f"{self.player1.display_name}'s choice", value=c1, inline=True
        )
        embed.add_field(
            name=f"{'Bot' if self.is_vs_bot else self.player2.display_name}'s choice",
            value=c2,
            inline=True,
        )
        embed.add_field(name="Result", value=result, inline=False)

        for item in self.children:
            item.disabled = True

        await interaction.message.edit(content=None, embed=embed, view=self)
        self.stop()  # Stop the timeout after a normal end

    async def process_player_choice(
        self, interaction: discord.Interaction, choice: str
    ):
        if interaction.user != self.player1 and (
            self.is_vs_bot or interaction.user != self.player2
        ):
            return await interaction.response.send_message(
                "❌ This game is not for you", ephemeral=True
            )

        if interaction.user == self.player1:
            if self.p1_choice:
                return await interaction.response.send_message(
                    "⚠️ You have already chosen", ephemeral=True
                )
            self.p1_choice = choice
            await interaction.response.send_message(
                f"✅ Your choice: **{choice}**", ephemeral=True
            )

        elif interaction.user == self.player2:
            if self.p2_choice:
                return await interaction.response.send_message(
                    "⚠️ You have already chosen", ephemeral=True
                )
            self.p2_choice = choice
            await interaction.response.send_message(
                f"✅ Your choice: **{choice}**", ephemeral=True
            )

        await self.check_choices(interaction)

    @discord.ui.button(label="Rock 🪨", style=discord.ButtonStyle.primary)
    async def rock_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self.process_player_choice(interaction, "Rock")

    @discord.ui.button(label="Paper 📄", style=discord.ButtonStyle.primary)
    async def paper_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self.process_player_choice(interaction, "Paper")

    @discord.ui.button(label="Scissors ✂️", style=discord.ButtonStyle.primary)
    async def scissors_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self.process_player_choice(interaction, "Scissors")


@bot.command(name="rps", aliases=["rockpaperscissors"])
@in_channel(GAMES_CHANNEL_ID)
async def rps_game(ctx, opponent: discord.Member = None):
    if opponent and opponent.bot:
        return await ctx.send(
            "❌ You cannot challenge bots this way; use `.rps` without a mention to play against the bot."
        )

    if opponent and opponent == ctx.author:
        return await ctx.send("❌ You cannot challenge yourself")

    if opponent:
        embed = discord.Embed(
            title="🎮 Rock Paper Scissors (Challenge)",
            description=(
                f"Match between {ctx.author.mention} and {opponent.mention}!\n\n"
                "⏱️ **You both have 10 seconds to choose!**\n"
                "Press the buttons below to make your move."
            ),
            color=discord.Color.blue(),
        )
    else:
        embed = discord.Embed(
            title="🎮 Rock Paper Scissors (vs Bot)",
            description=(
                f"{ctx.author.mention}, choose one of the buttons within 10 seconds.\n"
                "If you win, you earn **40 Tolar** 💵"
            ),
            color=discord.Color.blue(),
        )

    view = RPSView(player1=ctx.author, player2=opponent)
    # 📌 3. Bind the sent message to the view
    msg = await ctx.send(
        embed=embed,
        view=view,
        allowed_mentions=discord.AllowedMentions(users=False),
    )
    view.message = msg


# --- 6. Interactive Tic‑Tac‑Toe game ---
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
                "❌ It's not your turn", ephemeral=True
            )
            return

        idx = self.y * 3 + self.x
        if view.board[idx] != " ":
            await interaction.response.send_message(
                "❌ This square is already taken", ephemeral=True
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
                    f"**{view.current_player.mention} ({view.current_mark}) wins the Tic‑Tac‑Toe game!**\n"
                    f"💵 **50 Tolar** added to their balance"
                ),
                view=view,
            )
            view.stop()
            return

        if " " not in view.board:
            for child in view.children:
                child.disabled = True
            await interaction.response.edit_message(
                content=" **Draw – game ended with no winner.**", view=view
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
                    f"❌⭕ **Tic‑Tac‑Toe (XO)**\n"
                    f"Current turn: {view.current_player.mention} ({view.current_mark})\n"
                    f"Prize: **50 Tolar** for the winner"
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
                        content="🤖 **The bot won the Tic‑Tac‑Toe game.**",
                        view=view,
                    )
                    view.stop()
                    return

                if " " not in view.board:
                    for child in view.children:
                        child.disabled = True
                    await interaction.response.edit_message(
                        content=" **Draw – game ended with no winner.**", view=view
                    )
                    view.stop()
                    return

            await interaction.response.edit_message(
                content=(
                    f"❌⭕ **Tic‑Tac‑Toe (XO)**\n"
                    f"The bot played its turn. Your turn, {view.player1.mention} (❌)\n"
                    f"Prize: **50 Tolar** if you win"
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
                    content="⏰ **Game ended due to inactivity.**", view=self
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


@bot.command(name="tictactoe", aliases=["xo"])
@in_channel(GAMES_CHANNEL_ID)
async def xo_game(ctx, opponent: discord.Member = None):
    if opponent and opponent.bot:
        await ctx.send(
            "❌ You cannot challenge another bot; use the command without a mention to play against this bot."
        )
        return

    if opponent and opponent == ctx.author:
        await ctx.send("❌ You cannot challenge yourself")
        return

    if opponent:
        view = XOView(player1=ctx.author, player2=opponent)
        msg = await ctx.send(
            f"❌⭕ **Tic‑Tac‑Toe (XO) started**\n"
            f"Match between {ctx.author.mention} (❌) and {opponent.mention} (⭕)\n"
            f"Current turn: {ctx.author.mention}\n"
            f"Prize: **50 Tolar** for the winner",
            view=view,
            allowed_mentions=discord.AllowedMentions(users=False),
        )
        view.message = msg
    else:
        view = XOView(player1=ctx.author)
        msg = await ctx.send(
            f"❌⭕ **Tic‑Tac‑Toe (XO) vs Bot**\n"
            f"You play as (❌), the bot plays as (⭕)\n"
            f"Current turn: {ctx.author.mention}\n"
            f"Prize: **50 Tolar** if you win",
            view=view,
            allowed_mentions=discord.AllowedMentions(users=False),
        )
        view.message = msg


# --- 7. Connect 4 game ---
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
            await interaction.response.send_message("❌ It's not your turn", ephemeral=True)
            return

        placed_row = view.drop_piece(self.col, view.current_emoji)
        if placed_row == -1:
            await interaction.response.send_message(
                " This column is full, choose another column.", ephemeral=True
            )
            return

        if view.check_winner(placed_row, self.col, view.current_emoji):
            winner = view.current_player
            add_balance(winner.id, 60)
            for child in view.children:
                child.disabled = True
            await interaction.response.edit_message(
                content=(
                    f"🎉 **{winner.mention}** won the **Connect 4** game and earned **60 Tolar**💵\n\n"
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
                    "🤝 **Draw** – the board is full without a winner.\n\n"
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
                    f" **Connect 4**\nTurn: {view.current_player.mention}"
                    f" ({view.current_emoji})\nPrize: **60 Tolar** for the winner\n\n"
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
                        f"🤖 **The bot played column {bot_col + 1} and won the Connect 4 game**\n\n"
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
                        " **Draw** – the board is full without a winner.\n\n"
                        + view.get_board_string()
                    ),
                    view=view,
                )
                view.stop()
                return

            await interaction.response.edit_message(
                content=(
                    f" **Connect 4**\nBot played column {bot_col + 1}, your turn: {view.player1.mention} (🔴)\n\n"
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
                        f"⏰ **Game ended after one minute of inactivity**\n\n"
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


@bot.command(name="connect4", aliases=["c4"])
@in_channel(GAMES_CHANNEL_ID)
async def connect4_game(ctx, opponent: discord.Member = None):
    if opponent and opponent.bot:
        await ctx.send(
            "❌ You cannot challenge another bot; use the command without a mention to play against this bot."
        )
        return

    if opponent and opponent == ctx.author:
        await ctx.send("❌ You cannot challenge yourself")
        return

    if opponent:
        view = Connect4View(player1=ctx.author, player2=opponent)
        msg = await ctx.send(
            f"**Connect 4 game started** between {ctx.author.mention} (🔴) and"
            f" {opponent.mention} (🟡)\nPrize: **60 Tolar** for the winner\nTurn:"
            f" {ctx.author.mention}\n\n"
            + view.get_board_string(),
            view=view,
            allowed_mentions=discord.AllowedMentions(users=False),
        )
        view.message = msg
    else:
        view = Connect4View(player1=ctx.author)
        msg = await ctx.send(
            f"**Connect 4 vs Bot** – {ctx.author.mention} (🔴) vs"
            " the bot (🟡)\nPrize: **60 Tolar** for the winner!\nTurn:"
            f" {ctx.author.mention}\n\n"
            + view.get_board_string(),
            view=view,
            allowed_mentions=discord.AllowedMentions(users=False),
        )
        view.message = msg


# --- Anime Guess game settings ---
ACTIVE_ANIME_GAMES = {}
ANIME_REWARD = 20  # Reward in Tolar per correct answer
ANIME_DATABASE_FILE = os.path.join(BASE_DIR, "anime_characters.json")

def load_anime_characters():
    """Load anime character database from JSON file and return only valid characters."""
    try:
        with open(ANIME_DATABASE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            print("[ANIME] anime_characters.json must contain a list of characters.")
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
        print(f"[ANIME] Character database file not found: {ANIME_DATABASE_FILE}")
        return []
    except json.JSONDecodeError as e:
        print(f"[ANIME] Invalid JSON in anime_characters.json: {e}")
        return []
    except Exception as e:
        print(f"[ANIME] Failed to load character database: {e}")
        return []


def is_correct_anime_answer(user_answer, valid_answers):
    # Clean user input
    user_input = user_answer.strip().lower()
    
    if not user_input:
        return False

    for answer in valid_answers:
        clean_answer = answer.strip().lower()
        
        # 1. Exact match
        if user_input == clean_answer:
            return True
            
        # 2. Partial match (first or last name)
        words = clean_answer.split()
        for word in words:
            if len(word) > 2 and user_input == word:
                return True

        # 3. Tolerance for typos (one or two characters off)
        overall_similarity = SequenceMatcher(None, user_input, clean_answer).ratio()
        if overall_similarity >= 0.75:  
            return True

        for word in words:
            if len(word) > 2:
                word_similarity = SequenceMatcher(None, user_input, word).ratio()
                if word_similarity >= 0.75:
                    return True

    return False


@bot.command(name="guess")
@in_channel(GAMES_CHANNEL_ID)
async def anime_guess_command(ctx, rounds: int = 1):
    if rounds < 1 or rounds > 10:
        await ctx.send(
            "❌ The number of rounds must be between **1 and 10**.",
            allowed_mentions=discord.AllowedMentions(users=False),
        )
        return

    user_id = ctx.author.id

    if user_id in ACTIVE_ANIME_GAMES:
        await ctx.send(
            f"⚠️ {ctx.author.mention} you already have a guess game running.",
            allowed_mentions=discord.AllowedMentions(users=False),
        )
        return

    available_characters = load_anime_characters()
    if not available_characters:
        await ctx.send(
            "❌ No valid characters found in `anime_characters.json`.\n"
            "Make sure the file exists and contains `image_url` and `answers` for each character.",
            allowed_mentions=discord.AllowedMentions(users=False),
        )
        return

    if rounds > len(available_characters):
        rounds = len(available_characters)
        await ctx.send(
            f"⚠️ Rounds reduced to **{rounds}** because there aren't enough characters without repetition.",
            allowed_mentions=discord.AllowedMentions(users=False),
        )

    chosen_characters = random.sample(available_characters, rounds)

    # Register the game
    ACTIVE_ANIME_GAMES[user_id] = True

    correct_count = 0
    total_reward = 0

    await ctx.send(
        f"**🎮 Guess Game started**\n"
        f"👤 Player┃{ctx.author.mention}\n"
        f"🎯 Rounds┃**{rounds}**\n"
        f"💰 Reward┃**{ANIME_REWARD} Tolar** per correct answer.\n"
        f"⏱️ You have **15 seconds** to answer each round.",
        allowed_mentions=discord.AllowedMentions(users=False),
    )

    try:
        for round_number, character in enumerate(chosen_characters, start=1):
            image_url = character["image_url"]

            # Create the Embed (without image yet)
            embed = discord.Embed(
                description=f"** Round {round_number}/{rounds}**\nWho is this character?",
                color=discord.Color.blue(),
            )
            if character.get("source_url"):
                embed.url = character["source_url"]

            # Try to download the image and send it as an attachment
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
                            raise Exception("Fast download failed")
            except Exception:
                # Download failed -> send the image via URL (only once)
                embed.set_image(url=image_url)
                await ctx.send(
                    embed=embed,
                    allowed_mentions=discord.AllowedMentions(users=False)
                )

            # Wait for the answer
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
                    f"✅ **Correct answer!**\n💰 You earned **+{ANIME_REWARD} Tolar**.",
                    allowed_mentions=discord.AllowedMentions(users=False),
                )

            except asyncio.TimeoutError:
                correct_answer = character["answers"][0]
                await ctx.send(
                    f"⏰ Time up, {ctx.author.mention}.\n"
                    f"❌ The correct answer was: **{correct_answer}**",
                    allowed_mentions=discord.AllowedMentions(users=False),
                )

            if round_number < rounds:
                await asyncio.sleep(1)

    finally:
        # Remove the game key after it ends (whether completed or errored)
        ACTIVE_ANIME_GAMES.pop(user_id, None)

    # Final result
    current_balance = get_balance(user_id)
    await ctx.send(
        f"**🏁 Guess Game finished**\n"
        f"👤 Player┃{ctx.author.mention}\n"
        f"📊 Rounds┃**{rounds}**\n"
        f"✅ Correct answers┃**{correct_count}/{rounds}**\n"
        f"💰 Total reward┃**{total_reward} Tolar**\n"
        f"💳 Your current balance┃**{current_balance:,} Tolar**",
        allowed_mentions=discord.AllowedMentions(users=False),
    )


@bot.command(name="balance", aliases=["bal"])
@in_channel(SHOPPING_CHANNEL_ID)
async def balance_command(ctx, member: discord.Member = None):
    target = member or ctx.author

    # Balance is fetched fresh; avatar is cached for 5 minutes.
    avatar_url = str(target.display_avatar.url)
    avatar_bytes = _BALANCE_AVATAR_CACHE.get(avatar_url)
    if avatar_bytes is None:
        avatar_bytes = await target.display_avatar.read()
        _BALANCE_AVATAR_CACHE.set(avatar_url, avatar_bytes)

    bal = await _run_bg(get_balance, target.id)

    # If the name/balance/avatar haven't changed, send the cached image.
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

@bot.command(name="add")
@commands.has_role(OWNER_ROLE_ID)
@in_channel(SHOPPING_CHANNEL_ID)
async def add_money(ctx, member: discord.Member, amount: int):
    if amount <= 0:
        await ctx.send("❌ Please enter a valid amount greater than 0.")
        return

    add_balance(member.id, amount)
    await ctx.send(
        f"✅ Added **{amount}** Tolar to {member.mention}'s account.\n"
        f"💰 New balance: **{get_balance(member.id)}** Tolar.",
        allowed_mentions=discord.AllowedMentions.none(),
    )


@add_money.error
async def add_money_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("❌ This command is only for the Owner role.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(
            "**Correct usage:**\n"
            "`add @member amount`\n"
        )
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❌ Please mention a valid member and write the amount in numbers.")


@bot.command(name="remove")
@commands.has_role(OWNER_ROLE_ID)
@in_channel(SHOPPING_CHANNEL_ID)
async def remove_money(ctx, member: discord.Member, amount: int):
    if amount <= 0:
        await ctx.send("❌ Please enter a valid amount greater than 0.")
        return

    current_balance = get_balance(member.id)
    if current_balance < amount:
        await ctx.send(f"❌ The member's current balance (**{current_balance}** Tolar) is less than the amount to deduct.")
        return

    remove_balance(member.id, amount)
    await ctx.send(
        f"✅ Deducted **{amount}** Tolar from {member.mention}'s account.\n"
        f"💰 New balance: **{get_balance(member.id)}** Tolar.",
        allowed_mentions=discord.AllowedMentions.none(),
    )

@remove_money.error
async def remove_money_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("❌ This command is only for the Owner role.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(
            "**Correct usage:**\n"
            "`remove @member amount`\n"
        )
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❌ Please mention a valid member and write the amount in numbers.")


@bot.command(name="transfer", aliases=["pay"])
@in_channel(SHOPPING_CHANNEL_ID)
async def transfer_money(
    ctx, member: discord.Member = None, amount: int = None
):
    if not member or amount is None:
        await ctx.send(
            " **Correct usage:**\n"
            "`.transfer @member amount`\n",
            delete_after=5,
        )
        return

    if member.bot:
        await ctx.send("❌ You cannot transfer Tolar to bots.", delete_after=3)
        return

    if member == ctx.author:
        await ctx.send("❌ You cannot transfer Tolar to yourself.", delete_after=3)
        return

    if amount <= 0:
        await ctx.send("❌ Please enter a valid amount greater than **0**.", delete_after=3)
        return

    sender_balance = get_balance(ctx.author.id)
    if sender_balance < amount:
        await ctx.send(
            f"❌ You don't have enough Tolar. Your current balance is **{sender_balance}** Tolar.",
            delete_after=5,
        )
        return

    remove_balance(ctx.author.id, amount)
    add_balance(member.id, amount)

    await ctx.send(
        " ✅ Transfer successful!\n"
        f"You transferred **{amount}** Tolar to {member.mention}.\n"
        f" Your remaining balance: **{get_balance(ctx.author.id)}** Tolar.",
        allowed_mentions=discord.AllowedMentions(users=False),
    )


@transfer_money.error
async def transfer_money_error(ctx, error):
    if isinstance(error, commands.BadArgument):
        await ctx.send(
            "❌ Please mention a valid member and write the amount in numbers.", delete_after=3
        )


# ==========================================
# 🚀 Main bet command – updated
# ==========================================

class BetCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="bet", aliases=["wheel"])
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
                "❌ **Correct usage:**\n`.bet @member amount`\nExample: `.bet @User 500`"
            )

        if opponent.bot or opponent == ctx.author:
            return await ctx.send("❌ You cannot bet against yourself or bots")

        if amount <= 0:
            return await ctx.send("❌ Please enter a valid bet amount")

        # Check balances before starting
        # Fetch both balances in parallel, and avatars in parallel.
        author_bal_task = asyncio.create_task(_run_bg(get_balance, ctx.author.id))
        opponent_bal_task = asyncio.create_task(_run_bg(get_balance, opponent.id))
        p1_avatar_task = asyncio.create_task(ctx.author.display_avatar.read())
        p2_avatar_task = asyncio.create_task(opponent.display_avatar.read())
        author_bal, opponent_bal, p1_bytes, p2_bytes = await asyncio.gather(
            author_bal_task, opponent_bal_task, p1_avatar_task, p2_avatar_task
        )

        if author_bal < amount:
            return await ctx.send(f"❌ You don't have enough Tolar. Your balance: **{author_bal}** Tolar.")
        if opponent_bal < amount:
            return await ctx.send(f"❌ {opponent.mention} doesn't have enough Tolar for this bet.")

        # Generate the challenge image outside the event loop.
        challenge_img = await _run_bg(
            draw_challenge_card, p1_bytes, p2_bytes,
            ctx.author.display_name, opponent.display_name, amount
        )
        file_challenge = discord.File(challenge_img, filename="challenge.png")

        view = ChallengeView(ctx.author, opponent, amount)
        msg = await ctx.send(
            content=(
                f"⚔️ **New bet challenge**\n{opponent.mention} you have 30 seconds to accept "
                f"{ctx.author.mention}'s challenge for **${amount:,}** Tolar"
            ),
            file=file_challenge,
            view=view,
        )

        await view.wait()
        if not view.accepted:
            # If not accepted, delete the message
            try:
                await msg.delete()
            except:
                pass
            return

        # Re‑check balances after acceptance (in case they changed during 30 seconds)
        author_bal, opponent_bal = await asyncio.gather(
            _run_bg(get_balance, ctx.author.id),
            _run_bg(get_balance, opponent.id),
        )
        if author_bal < amount or opponent_bal < amount:
            return await ctx.send("❌ One party no longer has enough Tolar to cover the bet. Challenge cancelled.")

        # 2. Determine winner and generate the animated wheel GIF.
        winner_idx = random.choice([0, 1])  # 0 = blue, 1 = red
        winner = ctx.author if winner_idx == 0 else opponent
        loser = opponent if winner_idx == 0 else ctx.author

        # Send the wheel in a new independent message, without editing the challenge message.
        try:
            gif_buffer = await _run_bg(
                generate_wheel_gif,
                ctx.author.display_name, opponent.display_name, winner_idx
            )
            gif_file = discord.File(gif_buffer, filename="wheel.gif")
            await ctx.send(
                content="🎰 **Spinning the wheel of fate...**",
                file=gif_file,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except Exception as e:
            print(f"[BET] Wheel error: {type(e).__name__}: {e}")
            return await ctx.send("❌ An error occurred while generating the wheel. Check the bot console.")

        # Short display time; heavy processing is already outside the event loop.
        await asyncio.sleep(0.5)

        # 3. Execute the economic transfer outside the event loop.
        await _run_bg(remove_balance, loser.id, amount)
        await _run_bg(add_balance, winner.id, amount)

        winner_bal_after, loser_bal_after = await asyncio.gather(
            _run_bg(get_balance, winner.id),
            _run_bg(get_balance, loser.id),
        )

        # 4. Prepare the result image.
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
                f"🎉 **Congratulations to the winner** {winner.mention} earned **${amount:,}** Tolar,\n"
                "⚠️ The result image couldn't be generated, but the bet has been processed."
            )

        # 5. Send the result in a new independent message.
        try:
            await ctx.send(
                content=(
                    f"🎉 **Congratulations to the winner** {winner.mention} won the wheel of fate "
                    f"and earned **{amount:,}** Tolar from their opponent"
                ),
                file=result_file,
                allowed_mentions=discord.AllowedMentions(users=[winner]),
            )
        except Exception as e:
            print(f"[BET] Result message send error: {type(e).__name__}: {e}")
            try:
                await ctx.send(
                    "⚠️ Bet processed, but the result image couldn't be sent. "
                    f"Error: `{type(e).__name__}: {e}`"
                )
            except Exception:
                pass

@bot.command(name="id")
async def get_id(
    ctx,
    target: typing.Union[
        discord.TextChannel, discord.Member, discord.Role, str
    ] = None,
):
    if not target:
        await ctx.send(f"🆔 Your ID: `{ctx.author.id}`")
        return

    if ctx.message.role_mentions:
        role = ctx.message.role_mentions[0]
        await ctx.send(f"🆔 Role **{role.name}** ID: `{role.id}`")
        return

    if isinstance(target, discord.TextChannel):
        await ctx.send(f"🆔 Channel {target.mention} ID: `{target.id}`")
        return

    if ctx.message.mentions:
        member = ctx.message.mentions[0]
        await ctx.send(f"🆔 Member {member.mention} ID: `{member.id}`")
        return

    member = discord.utils.find(
        lambda m: m.name == target or m.display_name == target, ctx.guild.members
    )
    if member:
        await ctx.send(f"🆔 Member {member.mention} ID: `{member.id}`")
        return

    role = discord.utils.find(lambda r: r.name == target, ctx.guild.roles)
    if role:
        await ctx.send(f"🆔 Role **{role.name}** ID: `{role.id}`")
        return

    await ctx.send("❌ No member or role found with that mention/name.")


@bot.command(name="clear")
@commands.has_role(OWNER_ROLE_ID)
async def clear_messages(ctx, amount: int = None):
    if amount is None or amount <= 0:
        await ctx.send(
            "⚠️ Please specify the number of messages to clear.\nExample: `.clear 10`",
            delete_after=2,
        )
        return

    deleted = await ctx.channel.purge(limit=amount + 1)
    await ctx.send(f" ✅ Cleared **{len(deleted) - 1}** messages.", delete_after=1)


@clear_messages.error
async def clear_messages_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("❌ This command is for the Owner role only.", delete_after=2)
    elif isinstance(error, commands.BadArgument):
        await ctx.send(
            "❌ Please enter the number of messages as a number (e.g. `.clear 5`).",
            delete_after=1,
        )
    elif isinstance(error, commands.BotMissingPermissions):
        await ctx.send(
            "❌ The bot lacks the `Manage Messages` permission to clear the chat."
        )


@bot.command(name="avatar", aliases=["av"])
@in_channel(AVATAR_CHANNEL_ID)
async def show_avatar(ctx, member: discord.Member = None):
    target = member or ctx.author
    avatar_url = target.display_avatar.url

    embed = discord.Embed(color=discord.Color.dark_theme())
    embed.set_image(url=avatar_url)

    await ctx.send(embed=embed)


@bot.command(name="banner")
@in_channel(AVATAR_CHANNEL_ID)
async def show_banner(ctx, member: discord.Member = None):
    target = member or ctx.author
    user = await bot.fetch_user(target.id)

    if not user.banner:
        await ctx.send("❌ This account does not have a banner.", delete_after=2)
        return

    banner_url = user.banner.url

    embed = discord.Embed(color=discord.Color.dark_theme())
    embed.set_image(url=banner_url)

    await ctx.send(embed=embed)


@show_avatar.error
async def avatar_error(ctx, error):
    if isinstance(error, commands.BadArgument):
        await ctx.send("❌ Could not find that member or bot.", delete_after=2)


@show_banner.error
async def banner_error(ctx, error):
    if isinstance(error, commands.BadArgument):
        await ctx.send("❌ Could not find that member or bot.", delete_after=2)


@bot.command(name="change")
@commands.has_permissions(administrator=True)
@in_channel(AVATAR_CHANNEL_ID)
async def change_profile(ctx):
    await ctx.send("What do you want to change? Type **avatar** or **banner**.")

    def check_choice(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content in ["avatar", "banner"]

    try:
        choice_msg = await bot.wait_for("message", check=check_choice, timeout=30.0)
        choice = choice_msg.content

        await ctx.send(f"You chose **{choice}**. Please send the image as an attachment now.")

        def check_image(m):
            return m.author == ctx.author and m.channel == ctx.channel and len(m.attachments) > 0

        img_msg = await bot.wait_for("message", check=check_image, timeout=60.0)
        image_url = img_msg.attachments[0].url

        async with aiohttp.ClientSession() as session:
            async with session.get(image_url) as resp:
                if resp.status != 200:
                    return await ctx.send("Failed to download the image, please try again.")
                image_data = await resp.read()

        if choice == "avatar":
            await bot.user.edit(avatar=image_data)
            await ctx.send("Avatar changed successfully ✅")
        elif choice == "banner":
            await bot.user.edit(banner=image_data)
            await ctx.send("Banner changed successfully! ✅")

    except asyncio.TimeoutError:
        await ctx.send("You took too long, operation cancelled.")
    except discord.HTTPException as e:
        await ctx.send(f"An error occurred while updating: {e}")


@change_profile.error
async def change_profile_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("Sorry, this command is for administrators only ❌")


# --- 9. Game lists, commands, and help ---

# Basic commands are categorised here so that .commands and .help are consistent.
# Owner commands (OWNER_ROLE_ID) are hidden from .commands but appear in .help.
OWNER_ONLY_COMMANDS = {
    "manage_shop", "add", "remove", "clear",
    "ban", "mute", "unmute",
    "ban_by_mention", "unban", "lock", "unlock",
    "ticket", "manage_replies",
}

ADMIN_COMMANDS = {"change"}

GAME_COMMANDS = {
    ".guess [rounds]": "General knowledge quiz from 1 to 10 rounds.",
    ".rps [@member]": "Rock Paper Scissors against the bot or challenge another member.",
    ".tictactoe [@member]": "Tic‑Tac‑Toe (XO) against the bot or another member.",
    ".connect4 [@member]": "Connect 4 against the bot or another member.",
    ".guess [rounds]": "Anime character guessing game from 1 to 10 rounds.",
    ".roulette [amount]": "Group roulette; you can add a prize amount.",
}

GAME_AUTO_FEATURES = [
    "`🧠 Single emoji message` — Automatically starts a memory game where you have to remember the emoji's position.",
]

PUBLIC_COMMAND_FIELDS = [
    (
        "💰 Economy and Shop",
        [
            (".shop", "Open the Royal Shop to buy roles and colors."),
            (".balance [@member]", "Show your Tolar balance or another member's."),
            (".transfer @member amount", "Transfer Tolar to another member."),
            (".bet @member [amount]", "Bet using the wheel of fate against another member."),
        ],
    ),
    (
        "🖼️ Profile and Avatar",
        [
            (".avatar [@member]", "Display the profile picture."),
            (".banner [@member]", "Display the account banner."),
            (".change", "Change the bot's avatar or banner – admins only."),
        ],
    ),
    (
        "⚙️ General",
        [
            (".id [channel/role/member]", "Get the ID of a channel, role, or member."),
            (".commands", "Show available commands for members, excluding owner commands."),
            (".help", "Show the full guide of all bot commands."),
            (".games", "Show the complete list of games."),
        ],
    ),
]

# Separate lists for the help command so owner commands are included.
ALL_COMMANDS = [
    ("💰 Economy and Shop", [
        (".shop", "Open the Royal Shop to buy roles and colors.", False),
        (".manage_shop", "Manage roles and colors in the shop.", True),
        (".balance [@member]", "Show Tolar balance.", False),
        (".add @member amount", "Add Tolar to a member.", True),
        (".remove @member amount", "Deduct Tolar from a member.", True),
        (".transfer @member amount", "Transfer Tolar to another member.", False),
        (".bet @member [amount]", "Bet using the wheel of fate against another member.", False),
    ]),
    ("🎮 Games", [
        (command, description, False) for command, description in GAME_COMMANDS.items()
    ]),
    ("🖼️ Profile and Avatar", [
        (".avatar [@member]", "Display profile picture.", False),
        (".banner [@member]", "Display account banner.", False),
        (".change", "Change bot's avatar or banner.", False),
    ]),
    ("⚙️ General and Administration", [
        (".id [channel/role/member]", "Get an ID.", False),
        (".clear [number]", "Clear a number of messages.", True),
        (".ban @member [reason]", "Ban a member.", True),
        (".mute @member [minutes] [reason]", "Timeout a member for a specified duration.", True),
        (".unmute @member", "Remove timeout from a member.", True),
        (".ban_by_mention @member [reason]", "Ban a member using a mention.", True),
        (".unban @member/id [reason]", "Unban a member.", True),
        (".lock", "Lock the current channel.", True),
        (".unlock", "Unlock the current channel.", True),
        (".ticket", "Open the ticket system panel.", True),
        (".manage_replies", "Manage automatic replies.", True),
        (".commands", "Show available commands for members.", False),
        (".help", "Show the full guide of all commands.", False),
        (".games", "Show the complete list of games.", False),
    ]),
]

def _add_command_fields(embed, fields, include_owner=True):
    """Add ordered command fields to an Embed."""
    for field_name, commands_list in fields:
        lines = []
        for command_name, description, *restricted in commands_list:
            is_owner = bool(restricted and restricted[0])
            if is_owner and not include_owner:
                continue
            marker = " 🔒" if is_owner else ""
            if command_name == ".change":
                marker = " 🔐"
            lines.append(f"• `{command_name}`{marker} — {description}")
        if lines:
            embed.add_field(
                name=field_name,
                value="\n".join(lines),
                inline=False,
            )

@bot.command(name="games")
async def games_list(ctx):
    embed = discord.Embed(
        title="🎮 Game List",
        description="All bot games are listed here in a concise and clear way:",
        color=discord.Color.blue(),
    )

    game_lines = [
        f"• `{command}` — {description}"
        for command, description in GAME_COMMANDS.items()
    ]
    embed.add_field(
        name="🕹️ Games",
        value="\n".join(game_lines),
        inline=False,
    )
    embed.add_field(
        name="🧠 Automatic Game",
        value=GAME_AUTO_FEATURES[0],
        inline=False,
    )
    embed.set_footer(text="Games work in the designated games channel.")
    await ctx.send(embed=embed)


@bot.command(name="commands")
async def commands_list(ctx):
    """Display available commands for members, excluding owner commands."""
    embed = discord.Embed(
        title="⚙️ Bot Commands",
        description="Commands available to members, excluding owner commands 🔒.",
        color=discord.Color.blurple(),
    )

    _add_command_fields(embed, ALL_COMMANDS, include_owner=False)

    embed.set_footer(text=f"Requested by {ctx.author.display_name}")
    await ctx.send(embed=embed)


@bot.command(name="help", aliases=["guide"])
async def help_command(ctx):
    """Full guide of all bot commands, including owner commands."""
    embed = discord.Embed(
        title="📜 Complete Bot Command Guide",
        description=(
            "All commands are organised by section.\n"
            "🔒 = Owner only.\n"
            "🔐 = Admin only."
        ),
        color=discord.Color.gold(),
    )

    _add_command_fields(embed, ALL_COMMANDS, include_owner=True)

    embed.add_field(
        name="🧠 Automatic Features",
        value="• `Sending a single emoji` — Automatically starts the memory game.",
        inline=False,
    )

    embed.set_footer(
        text=f"Requested by {ctx.author.display_name}",
        icon_url=ctx.author.display_avatar.url,
    )
    await ctx.send(embed=embed)


# --- 10. Administration commands ---

@bot.command(name="ban")
@commands.has_role(OWNER_ROLE_ID)
async def ban_member(
    ctx, member: discord.Member = None, *, reason: str = "No reason provided"
):
    if not member:
        await ctx.send(
            "⚠️ **Please mention the member to ban**\nExample: `.ban @User reason`",
            delete_after=3,
        )
        return

    if member == ctx.author:
        await ctx.send("❌ You cannot ban yourself.")
        return

    if member.id == ctx.guild.owner_id:
        await ctx.send("❌ You cannot ban the server owner.")
        return

    try:
        await member.ban(reason=f"By {ctx.author.name} - Reason: {reason}")
        await ctx.send(
            f"✅ Member **{member.mention}** banned successfully.\n Reason: `{reason}`"
        )
    except discord.Forbidden:
        await ctx.send(
            "❌ I don't have enough permissions to ban this member (ensure my role is higher than theirs)."
        )
    except Exception as e:
        await ctx.send(f"❌ An error occurred while banning: {e}")


@ban_member.error
async def ban_member_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("❌ This command is for the Owner role only.", delete_after=3)


@bot.command(name="mute")
@commands.has_role(OWNER_ROLE_ID)
async def mute_member(
    ctx,
    member: discord.Member = None,
    minutes: int = 10,
    *,
    reason: str = "No reason provided",
):
    if not member:
        await ctx.send(
            "⚠️ **Please mention the member to mute**\nExample: `.mute @User 15 reason` (15 minutes)",
            delete_after=3,
        )
        return

    if member == ctx.author:
        await ctx.send("❌ You cannot mute yourself.")
        return

    if member.is_timed_out():
        await ctx.send("❌ **This member is already timed out.**")
        return

    if minutes <= 0:
        await ctx.send("❌ Please enter a valid number of minutes greater than 0.")
        return

    try:
        duration = datetime.timedelta(minutes=minutes)
        await member.timeout(
            duration, reason=f"By {ctx.author.name} - Reason: {reason}"
        )
        await ctx.send(
            f"✅ Member **{member.mention}** muted for **{minutes}** minutes.\n Reason: `{reason}`"
        )
    except discord.Forbidden:
        await ctx.send("❌ I don't have enough permissions to mute this member.")
    except Exception as e:
        await ctx.send(f"❌ An error occurred: {e}")


@mute_member.error
async def mute_member_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("❌ This command is for the Owner role only.", delete_after=3)


@bot.command(name="unmute")
@commands.has_role(OWNER_ROLE_ID)
async def unmute_member(ctx, member: discord.Member):
    if not member:
        await ctx.send(
            "⚠️ **Please mention the member to unmute**\nExample: `.unmute @User`",
            delete_after=3,
        )
        return

    if not member.is_timed_out():
        await ctx.send("❌ **This member is not currently timed out.**")
        return

    try:
        await member.edit(timed_out_until=None)
        await ctx.send(f"✅ Unmuted **{member.mention}** successfully.")
    except discord.Forbidden:
        await ctx.send("❌ I don't have enough permissions to unmute this member.")
    except Exception as e:
        await ctx.send(f"❌ An error occurred: {e}")


@unmute_member.error
async def unmute_member_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("❌ This command is for the Owner role only.", delete_after=3)


# ==========================================
# Ban / Unban commands with local images
# ==========================================

BAN_IMAGE_PATH = os.path.join(os.path.dirname(__file__), "ban.png")
UNBAN_IMAGE_PATH = os.path.join(os.path.dirname(__file__), "unban.png")


async def send_embed_with_image(ctx, title, description, image_path, color=discord.Color.green()):
    """Send an Embed with a local image file."""
    embed = discord.Embed(title=title, description=description, color=color)
    
    if os.path.exists(image_path):
        file = discord.File(image_path, filename=os.path.basename(image_path))
        embed.set_image(url=f"attachment://{os.path.basename(image_path)}")
        await ctx.send(embed=embed, file=file)
    else:
        await ctx.send(embed=embed)


@bot.command(name="ban_by_mention")
@commands.has_role(OWNER_ROLE_ID)
async def ban_member_by_mention(ctx, member: discord.Member = None, *, reason: str = "No reason provided"):
    """Bans a member using a mention and sends an Embed with a local image."""
    if not member:
        await ctx.send(
            "⚠️ **Please mention the member to ban**\nExample: `.ban_by_mention @User reason`",
            delete_after=3,
        )
        return
    if member == ctx.author:
        await ctx.send("❌ You cannot ban yourself.")
        return
    if member.id == ctx.guild.owner_id:
        await ctx.send("❌ You cannot ban the server owner.")
        return

    try:
        await member.ban(reason=f"By {ctx.author.name} - Reason: {reason}")
        title = "🚫 Member Banned"
        description = (
            f"**Member:** {member.mention} (`{member.id}`)\n"
            f"**Reason:** {reason}\n"
            f"**By:** {ctx.author.mention}"
        )
        await send_embed_with_image(ctx, title, description, BAN_IMAGE_PATH, color=discord.Color.red())
    except discord.Forbidden:
        await ctx.send("❌ I don't have enough permissions to ban this member (ensure my role is higher than theirs).")
    except Exception as e:
        await ctx.send(f"❌ An error occurred while banning: {e}")


@ban_member_by_mention.error
async def ban_member_by_mention_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("❌ This command is for the Owner role only.", delete_after=3)


@bot.command(name="unban")
@commands.has_role(OWNER_ROLE_ID)
async def unban_member(ctx, user: discord.User = None, *, reason: str = "No reason provided"):
    """Unbans a member and sends them an invite link via DM."""
    if user is None:
        args = ctx.message.content.split()
        if len(args) >= 2:
            try:
                user_id = int(args[1])
                user = await bot.fetch_user(user_id)
            except:
                await ctx.send("❌ Please enter a valid mention or numeric ID.\nExample: `.unban @user` or `.unban 123456789`")
                return
        else:
            await ctx.send("❌ Please mention the user to unban or provide their ID.\nExample: `.unban @user` or `.unban 123456789`")
            return

    try:
        # Directly unban without fetching the ban list – avoids compatibility issues.
        await ctx.guild.unban(user, reason=f"By {ctx.author.name} - Reason: {reason}")

        # Create an invite link and send it to the user in DM
        invite_sent = False
        try:
            invite = await ctx.channel.create_invite(
                max_age=0,
                max_uses=1,
                reason=f"To re‑invite {user.name} after unban"
            )
            await user.send(
                f"✅ You have been unbanned from **{ctx.guild.name}**. "
                f"You can rejoin using this link:\n{invite.url}"
            )
            invite_sent = True
        except discord.Forbidden:
            pass
        except Exception as e:
            print(f"Failed to send invite: {e}")

        title = "✅ Unbanned"
        dm_status = "Invite link sent via DM." if invite_sent else "Unbanned, but couldn't send an invite link."
        description = (
            f"**User:** {user.name} (`{user.id}`)\n"
            f"**Reason:** {reason}\n"
            f"**By:** {ctx.author.mention}\n"
            f"{dm_status}"
        )
        await send_embed_with_image(
            ctx, title, description, UNBAN_IMAGE_PATH, color=discord.Color.green()
        )

    except discord.NotFound:
        await ctx.send(f"❌ User {user.name} is not banned in this server.")
    except discord.Forbidden:
        await ctx.send("❌ I don't have enough permissions to unban. Make sure I have the Ban Members permission.")
    except Exception as e:
        await ctx.send(f"❌ An error occurred while unbanning: {e}")


# ==========================================
# 🔒 Lock / Unlock channels (Owner only)
# ==========================================

@bot.command(name="lock")
@commands.has_role(OWNER_ROLE_ID)
async def lock_channel(ctx):
    """Locks the current channel (prevents members from sending messages)."""
    channel = ctx.channel
    default_perms = channel.permissions_for(ctx.guild.default_role)
    if not default_perms.send_messages:
        await ctx.send("🔒 This channel is already locked.")
        return
    overwrite = channel.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = False
    await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
    await ctx.send("🔒 Channel locked.")

@bot.command(name="unlock")
@commands.has_role(OWNER_ROLE_ID)
async def unlock_channel(ctx):
    """Unlocks the current channel (allows members to send messages)."""
    channel = ctx.channel
    default_perms = channel.permissions_for(ctx.guild.default_role)
    if default_perms.send_messages:
        await ctx.send("🔓 This channel is already unlocked.")
        return
    overwrite = channel.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = True
    await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
    await ctx.send("🔓 Channel unlocked.")

@lock_channel.error
@unlock_channel.error
async def lock_unlock_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("❌ This command is for the Owner role only.", delete_after=3)


# Set the category ID for tickets (0 = no category)
TICKET_CATEGORY_ID = 0


class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Open",
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
                "❌ Cannot open a ticket outside a server.",
                ephemeral=True
            )
            return

        # Find the category safely
        category = None

        if TICKET_CATEGORY_ID:
            category = guild.get_channel(TICKET_CATEGORY_ID)

            if category is not None and not isinstance(
                category,
                discord.CategoryChannel
            ):
                category = None

        # Create a safe and unique ticket name
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

        # Permissions
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

        # Give the Owner role access
        owner_role = guild.get_role(OWNER_ROLE_ID)

        if owner_role:
            overwrites[owner_role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True
            )

        # Create the channel
        try:
            channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                reason=f"Ticket opened by {interaction.user}"
            )

        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I don't have permission to create channels. Make sure I have **Manage Channels** permission.",
                ephemeral=True
            )
            return

        except Exception as e:
            print(f"[TICKET ERROR] {e}")

            await interaction.response.send_message(
                f"❌ An error occurred while creating the ticket:\n`{e}`",
                ephemeral=True
            )
            return

        # Ticket message
        embed = discord.Embed(
            title="🎫 New Ticket",
            description=(
                f"{interaction.user.mention}\n\n"
                "Write your issue or question here, and the administration will respond.\n\n"
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
                f"❌ Ticket created but an error occurred while sending its message:\n`{e}`",
                ephemeral=True
            )
            return

        # Confirm ticket opening
        await interaction.response.send_message(
            f"✅ Ticket opened successfully: {channel.mention}",
            ephemeral=True
        )


class TicketDeleteView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Delete",
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
                "❌ This button is for the Owner role only.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            "🗑️ Deleting ticket...",
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
# Ticket panel creation command
# ==========================================

@bot.command(name="ticket")
@commands.has_role(OWNER_ROLE_ID)
@in_channel(TICKET_CHANNEL_ID)
async def ticket_command(ctx):

    try:
        await ctx.message.delete()
    except:
        pass

    embed = discord.Embed(
        title="🎫 Ticket System",
        description=(
            "• Press the button below to open a ticket.\n"
            "• Opening a ticket without a valid reason may result in a 1h mute."
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
            "❌ This command is for the Owner role only.",
            delete_after=3
        )


# ==========================================
# 🤖 Automatic reply system (Owner only) – supports mentions and keywords
# ==========================================

REPLIES_FILE = os.path.join(BASE_DIR, "replies.json")
REPLIES_REDIS_KEY = "bot_replies"
_next_id = 1

def _normalize_replies(data):
    """Normalise the reply data structure and ensure required sections exist."""
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
    Load replies from Redis first so they don't get lost when the bot is redeployed/updated.
    If no data exists in Redis, use replies.json as a legacy fallback,
    then push it to Redis to become the permanent version.
    """
    try:
        result = _redis_command("GET", REPLIES_REDIS_KEY)
        if result:
            return _normalize_replies(json.loads(result))
    except Exception as e:
        print(f"❌ Failed to load replies from Redis: {e}")

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
                print(f"⚠️ Failed to migrate replies to Redis: {e}")
            return data
        except Exception as e:
            print(f"❌ Failed to read replies.json: {e}")

    return {"member": {}, "word": []}

def save_replies(data):
    """Save replies persistently to Redis with a local backup."""
    data = _normalize_replies(data)
    payload = json.dumps(data, ensure_ascii=False, indent=2)

    redis_saved = False
    try:
        redis_saved = _redis_command("SET", REPLIES_REDIS_KEY, payload) == "OK"
    except Exception as e:
        print(f"❌ Failed to save replies to Redis: {e}")

    try:
        with open(REPLIES_FILE, "w", encoding="utf-8") as f:
            f.write(payload)
        local_saved = True
    except Exception as e:
        print(f"❌ Failed to save local replies backup: {e}")
        local_saved = False

    if not redis_saved and not local_saved:
        raise RuntimeError("Failed to save replies to both Redis and local file.")
    return True

def generate_id():
    global _next_id
    max_id = 0
    for replies in replies_cache["member"].values():
        for r in replies:
            if r.get("id", 0) > max_id:
                max_id = r["id"]
    for r in replies_cache["word"]:
        if r.get("id", 0) > max_id:
            max_id = r["id"]
    _next_id = max_id + 1
    return _next_id

# Global variable
replies_cache = load_replies()

# ==========================================
# Input Modals
# ==========================================

class AddReplyModal(discord.ui.Modal, title="Add Text Reply (on mention)"):
    user_id = discord.ui.TextInput(
        label="User ID",
        placeholder="Enter the number",
        required=True,
        style=discord.TextStyle.short
    )
    reply_text = discord.ui.TextInput(
        label="The text the bot will reply",
        placeholder="Write the reply",
        required=True,
        style=discord.TextStyle.paragraph
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            uid = int(self.user_id.value.strip())
        except ValueError:
            await interaction.response.send_message("❌ The ID must be a number.", ephemeral=True)
            return
        text = self.reply_text.value.strip()
        if not text:
            await interaction.response.send_message("❌ The text cannot be empty.", ephemeral=True)
            return

        uid_str = str(uid)
        if uid_str not in replies_cache["member"]:
            replies_cache["member"][uid_str] = []
        new_reply = {"id": generate_id(), "type": "text", "value": text}
        replies_cache["member"][uid_str].append(new_reply)
        save_replies(replies_cache)
        await interaction.response.send_message(
            f"✅ Added text reply for user `{uid}` (reply ID {new_reply['id']})",
            ephemeral=True
        )

class AddReactionModal(discord.ui.Modal, title="Add Reaction Reply (on mention)"):
    user_id = discord.ui.TextInput(
        label="User ID",
        placeholder="Enter the number",
        required=True,
        style=discord.TextStyle.short
    )
    emoji_id = discord.ui.TextInput(
        label="Emoji ID or regular emoji",
        placeholder="e.g. <:name:id> or 👍",
        required=True,
        style=discord.TextStyle.short
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            uid = int(self.user_id.value.strip())
        except ValueError:
            await interaction.response.send_message("❌ The ID must be a number.", ephemeral=True)
            return
        emoji = self.emoji_id.value.strip()
        if not emoji:
            await interaction.response.send_message("❌ The emoji cannot be empty.", ephemeral=True)
            return

        uid_str = str(uid)
        if uid_str not in replies_cache["member"]:
            replies_cache["member"][uid_str] = []
        new_reply = {"id": generate_id(), "type": "reaction", "value": emoji}
        replies_cache["member"][uid_str].append(new_reply)
        save_replies(replies_cache)
        await interaction.response.send_message(
            f"✅ Added reaction reply for user `{uid}` (reply ID {new_reply['id']})",
            ephemeral=True
        )

class AddWordReplyModal(discord.ui.Modal, title="Add Keyword Reply (text)"):
    trigger = discord.ui.TextInput(
        label="Keyword",
        placeholder="e.g. hello",
        required=True,
        style=discord.TextStyle.short
    )
    reply_text = discord.ui.TextInput(
        label="Text reply",
        placeholder="Write the reply",
        required=True,
        style=discord.TextStyle.paragraph
    )

    async def on_submit(self, interaction: discord.Interaction):
        trigger = self.trigger.value.strip().lower()
        reply = self.reply_text.value.strip()
        if not trigger or not reply:
            await interaction.response.send_message("❌ Fields cannot be empty.", ephemeral=True)
            return
        new_reply = {"id": generate_id(), "type": "text", "trigger": trigger, "value": reply}
        replies_cache["word"].append(new_reply)
        save_replies(replies_cache)
        await interaction.response.send_message(
            f"✅ Added keyword text reply for `{trigger}` (reply ID {new_reply['id']})",
            ephemeral=True
        )

class AddWordReactionModal(discord.ui.Modal, title="Add Keyword Reply (reaction)"):
    trigger = discord.ui.TextInput(
        label="Keyword",
        placeholder="e.g. thanks",
        required=True,
        style=discord.TextStyle.short
    )
    emoji_id = discord.ui.TextInput(
        label="Emoji (ID or regular)",
        placeholder="e.g. <:name:id> or 👍",
        required=True,
        style=discord.TextStyle.short
    )

    async def on_submit(self, interaction: discord.Interaction):
        trigger = self.trigger.value.strip().lower()
        emoji = self.emoji_id.value.strip()
        if not trigger or not emoji:
            await interaction.response.send_message("❌ Fields cannot be empty.", ephemeral=True)
            return
        new_reply = {"id": generate_id(), "type": "reaction", "trigger": trigger, "value": emoji}
        replies_cache["word"].append(new_reply)
        save_replies(replies_cache)
        await interaction.response.send_message(
            f"✅ Added keyword reaction reply for `{trigger}` (reply ID {new_reply['id']})",
            ephemeral=True
        )

# ==========================================
# Edit / Delete replies
# ==========================================

class EditReplyModal(discord.ui.Modal, title="Edit Reply"):
    def __init__(self, reply_id: int, current_value: str, reply_type: str, category: str, extra=None):
        super().__init__()
        self.reply_id = reply_id
        self.category = category  # "member" or "word"
        self.extra = extra  # for member we need uid
        self.reply_type = reply_type

        if category == "word":
            # Add a trigger field
            self.trigger_input = discord.ui.TextInput(
                label="Keyword",
                default=extra,
                required=True,
                style=discord.TextStyle.short
            )
            self.add_item(self.trigger_input)

        self.new_value = discord.ui.TextInput(
            label="New value",
            default=current_value,
            required=True,
            style=discord.TextStyle.paragraph if reply_type == "text" else discord.TextStyle.short
        )
        self.add_item(self.new_value)

    async def on_submit(self, interaction: discord.Interaction):
        new_val = self.new_value.value.strip()
        if not new_val:
            await interaction.response.send_message("❌ Value cannot be empty.", ephemeral=True)
            return

        if self.category == "member":
            uid = self.extra
            if uid in replies_cache["member"]:
                for reply in replies_cache["member"][uid]:
                    if reply["id"] == self.reply_id:
                        reply["value"] = new_val
                        save_replies(replies_cache)
                        await interaction.response.send_message(f"✅ Reply ID {self.reply_id} updated successfully.", ephemeral=True)
                        return
            await interaction.response.send_message("❌ Reply not found.", ephemeral=True)
        else:  # word
            new_trigger = self.trigger_input.value.strip().lower() if hasattr(self, 'trigger_input') else None
            for reply in replies_cache["word"]:
                if reply["id"] == self.reply_id:
                    reply["value"] = new_val
                    if new_trigger:
                        reply["trigger"] = new_trigger
                    save_replies(replies_cache)
                    await interaction.response.send_message(f"✅ Reply ID {self.reply_id} updated successfully.", ephemeral=True)
                    return
            await interaction.response.send_message("❌ Reply not found.", ephemeral=True)

class DeleteReplyView(discord.ui.View):
    def __init__(self, reply_id: int, category: str, extra=None):
        super().__init__(timeout=60)
        self.reply_id = reply_id
        self.category = category
        self.extra = extra

    @discord.ui.button(label="Yes, delete", style=discord.ButtonStyle.danger)
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
                    await interaction.response.send_message(f"✅ Reply ID {self.reply_id} deleted successfully.", ephemeral=True)
                    return
        else:  # word
            old_len = len(replies_cache["word"])
            replies_cache["word"] = [r for r in replies_cache["word"] if r["id"] != self.reply_id]
            if len(replies_cache["word"]) != old_len:
                save_replies(replies_cache)
                await interaction.response.send_message(f"✅ Reply ID {self.reply_id} deleted successfully.", ephemeral=True)
                return
        await interaction.response.send_message("❌ Reply not found.", ephemeral=True)
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Cancelled.", ephemeral=True)
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)

# ==========================================
# Dropdown to view all replies
# ==========================================

class RepliesSelect(discord.ui.Select):
    def __init__(self):
        options = []
        # Member replies
        for uid, replies in replies_cache["member"].items():
            for reply in replies:
                label = f"👤 User {uid}"
                desc = f"{reply['type']}: {reply['value'][:30]} (id:{reply['id']})"
                options.append(discord.SelectOption(
                    label=label,
                    value=f"member|{uid}|{reply['id']}",
                    description=desc
                ))
        # Keyword replies
        for reply in replies_cache["word"]:
            label = f" Keyword: {reply['trigger']}"
            desc = f"{reply['type']}: {reply['value'][:30]} (id:{reply['id']})"
            options.append(discord.SelectOption(
                label=label,
                value=f"word|{reply['id']}",
                description=desc
            ))
        if not options:
            options.append(discord.SelectOption(
                label="No replies",
                value="none",
                description="Add a new reply"
            ))
        super().__init__(
            placeholder="Choose a reply to edit or delete...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message("No replies to display.", ephemeral=True)
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
                await interaction.response.send_message("❌ This reply does not exist.", ephemeral=True)
                return
            embed = discord.Embed(
                title=f"✏️ User {uid} Reply – ID {rid}",
                description=f"**Type:** {reply['type']}\n**Value:** {reply['value']}",
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
                await interaction.response.send_message("❌ This reply does not exist.", ephemeral=True)
                return
            embed = discord.Embed(
                title=f"✏️ Keyword: {reply['trigger']} – ID {rid}",
                description=f"**Type:** {reply['type']}\n**Value:** {reply['value']}",
                color=discord.Color.blue()
            )
            view = discord.ui.View()
            view.add_item(EditReplyButton(rid, reply["value"], reply["type"], "word", extra=reply["trigger"]))
            view.add_item(DeleteReplyButton(rid, "word"))
            await interaction.response.edit_message(embed=embed, view=view)

class EditReplyButton(discord.ui.Button):
    def __init__(self, reply_id: int, current_value: str, reply_type: str, category: str, extra=None):
        super().__init__(label="✏️ Edit", style=discord.ButtonStyle.primary)
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
        super().__init__(label="🗑️ Delete", style=discord.ButtonStyle.danger)
        self.reply_id = reply_id
        self.category = category
        self.extra = extra

    async def callback(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="⚠️ Confirm Deletion",
            description=f"Are you sure you want to delete reply ID {self.reply_id}?",
            color=discord.Color.red()
        )
        view = DeleteReplyView(self.reply_id, self.category, self.extra)
        await interaction.response.edit_message(embed=embed, view=view)

# ==========================================
# Main management panel with add options
# ==========================================

class RepliesManagementView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(RepliesSelect())

    @discord.ui.button(label="➕ Add Reply", style=discord.ButtonStyle.primary)
    async def add_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="Choose reply type",
            description="Select one of the options below",
            color=discord.Color.blue()
        )
        view = AddChoiceView()
        await interaction.response.edit_message(embed=embed, view=view)

class AddChoiceView(discord.ui.View):
    @discord.ui.button(label="📝 Text reply (on mention)", style=discord.ButtonStyle.success)
    async def text_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddReplyModal())

    @discord.ui.button(label="👍 Reaction reply (on mention)", style=discord.ButtonStyle.success)
    async def reaction_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddReactionModal())

    @discord.ui.button(label="📝 Keyword reply (text)", style=discord.ButtonStyle.primary)
    async def word_text_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddWordReplyModal())

    @discord.ui.button(label="👍 Keyword reply (reaction)", style=discord.ButtonStyle.primary)
    async def word_reaction_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddWordReactionModal())

    @discord.ui.button(label="🔙 Back", style=discord.ButtonStyle.secondary)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="⚙️ Auto‑Reply Management Panel",
            description="• Choose a reply from the dropdown to edit or delete.\n• Press **Add Reply** to create a new reply.",
            color=discord.Color.gold()
        )
        view = RepliesManagementView()
        await interaction.response.edit_message(embed=embed, view=view)

# ==========================================
# Main command
# ==========================================

@bot.command(name="manage_replies")
@commands.has_role(OWNER_ROLE_ID)
@in_channel(AMENDMENTS_CHANNEL_ID)
async def manage_replies(ctx):
    embed = discord.Embed(
        title="⚙️ Auto‑Reply Management Panel",
        description="• Choose a reply from the dropdown to edit or delete.\n• Press **Add Reply** to create a new reply.",
        color=discord.Color.gold()
    )
    view = RepliesManagementView()
    await ctx.send(embed=embed, view=view)

# ==========================================
# Message listener – executes replies
# ==========================================
async def enlarge_and_send(channel, url, type_str):
    """Download an image from a URL, enlarge it 2x, and send it as a file."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return
                img_data = await resp.read()
                img = Image.open(io.BytesIO(img_data))
                
                new_size = (img.width * 2, img.height * 2)
                buf = io.BytesIO()

                # Check if it's animated (GIF)
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
                    # Static image – save as PNG
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
# 🎡 Group Roulette game
# ==========================================

# Each game is independent with its own message and prize; prevents a user from joining more than one.
ACTIVE_GROUP_ROULETTE = {}
ACTIVE_GROUP_ROULETTE_USERS = set()

GROUP_ROULETTE_MAX_PLAYERS = 10
GROUP_ROULETTE_MIN_PLAYERS = 2
GROUP_ROULETTE_TIMEOUT = 600


def _roulette_number(text):
    """Convert a bet amount from text to integer, supporting Arabic and English separators."""
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
    """Open the roulette background and crop it to fit the embed with a slight dim overlay."""
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
                print(f"⚠️ Failed to open roulette background: {e}")
                _ROULETTE_BG_CACHE = Image.new("RGBA", size, (13, 17, 29, 255))
        return _ROULETTE_BG_CACHE.copy()


def draw_group_roulette_lobby(amount, players, host):
    """A beautiful lobby card with player count, instructions, and names."""
    width, height = 1200, 700
    base = _open_roulette_background((width, height))
    d = ImageDraw.Draw(base)

    # Gold decorative rings
    for r in (530, 500, 470):
        d.ellipse(
            (width//2-r, 350-r, width//2+r, 350+r),
            outline=(184, 145, 55, 35),
            width=2,
        )

    # Title
    d.rounded_rectangle(
        (70, 35, width-70, 145),
        radius=30,
        fill=(26, 31, 48, 245),
        outline=(232, 198, 106, 255),
        width=4,
    )
    d.text(
        (width//2, 88),
        "🎡 Group Roulette",
        font=_font(52),
        fill=(232, 198, 106, 255),
        anchor="mm",
    )

    # Player count box
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
        "Players",
        font=_font(22),
        fill=(180, 184, 198, 255),
        anchor="mm",
    )

    # Bet info and host
    d.rounded_rectangle(
        (70, 175, 790, 285),
        radius=24,
        fill=(26, 31, 48, 235),
        outline=(80, 91, 120, 200),
        width=2,
    )
    prize_text = f"Prize: {amount:,} Tolar" if amount > 0 else "No prize"
    d.text(
        (430, 212),
        prize_text,
        font=_fit_font(prize_text, 620, 34, 22),
        fill=(232, 198, 106, 255),
        anchor="mm",
    )
    d.text(
        (430, 258),
        f"Host: {host.display_name[:28]}",
        font=_fit_font(f"Host: {host.display_name[:28]}", 620, 24, 18),
        fill=(220, 223, 233, 255),
        anchor="mm",
    )

    # Instructions
    d.rounded_rectangle(
        (70, 315, 1130, 455),
        radius=26,
        fill=(7, 10, 18, 205),
        outline=(70, 82, 110, 180),
        width=2,
    )
    d.text(
        (600, 350),
        "Press the buttons to join",
        font=_font(35),
        fill=(255, 255, 255, 255),
        anchor="mm",
    )
    d.text(
        (600, 405),
        "One player is randomly chosen to eliminate another, and so on",
        font=_fit_font(
            "One player is randomly chosen to eliminate another, and so on",
            950, 30, 19
        ),
        fill=(194, 199, 214, 255),
        anchor="mm",
    )

    # Player names at the bottom
    d.text(
        (600, 490),
        "Participants",
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
            name = "— Empty —"
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
    """Return a lobby image from cache, or draw and cache it once."""
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
    """Cache the roulette wheel GIF; same players and same index return the same GIF."""
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
    """Generate a GIF of a multi‑segment wheel with the arrow pointing to the winner."""
    size = 720
    center = (size // 2, size // 2)
    radius = 285
    n = len(players)
    span = 360.0 / n
    frames = []
    total_frames = 34

    # Final winner segment centre under the top arrow (270° in PIL).
    winner_center = winner_index * span + span / 2
    target_offset = (270.0 - winner_center) % 360.0
    total_rotation = 6 * 360 + target_offset

    # Slightly lighter palette than the previous design, maintaining contrast.
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

        # Glow behind the wheel
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

        # Centre and inner ring
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

        # Fixed arrow at the top
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
        # Registration remains open, but if no extra player joins within 20 seconds,
        # the game is cancelled. One extra player is enough to cancel this condition.
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
            # The host is counted as the first player, so we look for an additional player.
            if len(game["players"]) > 1:
                return

            ACTIVE_GROUP_ROULETTE.pop(self.game_id, None)
            if game["amount"] > 0:
                add_balance(game["host"].id, game["amount"])
            for member in game["players"]:
                ACTIVE_GROUP_ROULETTE_USERS.discard(member.id)

            if self.message:
                try:
                    content = "⏰ Roulette cancelled because no extra player joined within 20 seconds."
                    if game["amount"] > 0:
                        content += " The prize amount has been returned to the host."
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

    @discord.ui.button(label="Join", style=discord.ButtonStyle.success, emoji="🎟️")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = self._game()
        if not game:
            return await interaction.response.send_message("❌ Game ended.", ephemeral=True)

        uid = interaction.user.id
        if uid in game["players"]:
            return await interaction.response.send_message("⚠️ You are already in the game.", ephemeral=True)
        if len(game["players"]) >= GROUP_ROULETTE_MAX_PLAYERS:
            return await interaction.response.send_message("❌ Game is full (10/10).", ephemeral=True)
        if uid in ACTIVE_GROUP_ROULETTE_USERS:
            return await interaction.response.send_message("❌ You are already in another roulette game.", ephemeral=True)

        game["players"].append(interaction.user)
        ACTIVE_GROUP_ROULETTE_USERS.add(uid)
        await interaction.response.defer()
        await self._refresh(interaction)

    @discord.ui.button(label="Leave", style=discord.ButtonStyle.secondary, emoji="🚪")
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = self._game()
        if not game:
            return await interaction.response.send_message("❌ Game ended.", ephemeral=True)

        uid = interaction.user.id
        if uid not in [m.id for m in game["players"]]:
            return await interaction.response.send_message("⚠️ You are not in the game.", ephemeral=True)
        if game["started"]:
            return await interaction.response.send_message("❌ Cannot leave after the game has started.", ephemeral=True)

        game["players"] = [m for m in game["players"] if m.id != uid]
        ACTIVE_GROUP_ROULETTE_USERS.discard(uid)

        # If the host leaves: cancel and refund the prize.
        if uid == game["host"].id:
            remove_game = ACTIVE_GROUP_ROULETTE.pop(self.game_id, None)
            if remove_game:
                if game["amount"] > 0:
                    add_balance(game["host"].id, game["amount"])
                for member in game["players"]:
                    ACTIVE_GROUP_ROULETTE_USERS.discard(member.id)
            await interaction.response.edit_message(
                content="❌ Roulette cancelled because the host left; the prize has been refunded.",
                attachments=[],
                view=None,
            )
            self.stop()
            return

        await interaction.response.defer()
        await self._refresh(interaction)

    @discord.ui.button(label="Start Game", style=discord.ButtonStyle.primary, emoji="🎡")
    async def start_game(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = self._game()
        if not game:
            return await interaction.response.send_message("❌ Game ended.", ephemeral=True)
        if interaction.user.id != game["host"].id:
            return await interaction.response.send_message("❌ Only the host can start the game.", ephemeral=True)
        if len(game["players"]) < GROUP_ROULETTE_MIN_PLAYERS:
            return await interaction.response.send_message(
                f"❌ At least {GROUP_ROULETTE_MIN_PLAYERS} players are required.", ephemeral=True
            )
        if game["started"]:
            return await interaction.response.send_message("⚠️ The game has already started.", ephemeral=True)

        game["started"] = True
        game["round"] = 0
        game["message"] = interaction.message
        await interaction.response.defer()

        view = GroupRouletteRoundView(self.game_id)
        img_buf = None
        try:
            # Randomly pick the first player to start the elimination round.
            selected = random.choice(game["players"])
            game["selected_id"] = selected.id
            embed = discord.Embed(
                title="🎡 Group Roulette",
                description=(
                    f"🎯 **{selected.mention}** choose a player to eliminate or press **Random**.\n\n"
                    + (
                        f"💰 Prize: **{game['amount']:,} Tolar**\n"
                        if game["amount"] > 0
                        else "🎁 **No prize**\n"
                    )
                    + f"👥 Remaining: **{len(game['players'])}**"
                ),
                color=discord.Color.from_rgb(184, 145, 55),
            )
            selected_index = game["players"].index(selected)
            # If only two players remain, the wheel picks the winner immediately.
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

            # When the game starts, leave the registration message as is, and send a new message for the round.
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
                    content="⏰ Registration time expired, the prize has been refunded to the host.",
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
                description="Eliminate this player",
            )
            for member in players
        ]
        if not options:
            options = [discord.SelectOption(label="No players", value="none")]
        super().__init__(
            placeholder="Choose a player to eliminate...",
            min_values=1,
            max_values=1,
            options=options[:25],
        )

    async def callback(self, interaction: discord.Interaction):
        game = ACTIVE_GROUP_ROULETTE.get(self.game_id)
        if not game or not game["started"]:
            return await interaction.response.send_message("❌ Game unavailable.", ephemeral=True)

        if interaction.user.id != game["selected_id"]:
            return await interaction.response.send_message(
                "❌ It's not your turn.", ephemeral=True
            )

        value = self.values[0]
        if value == "none":
            return await interaction.response.send_message("❌ No player to choose.", ephemeral=True)

        target_id = int(value)
        if target_id == game["selected_id"]:
            return await interaction.response.send_message(
                "❌ You cannot eliminate yourself.", ephemeral=True
            )

        target = next((m for m in game["players"] if m.id == target_id), None)
        if not target:
            return await interaction.response.send_message("❌ That player is no longer in the game.", ephemeral=True)

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

        # When only two players remain, the wheel picks the winner automatically.
        if len(game["players"]) <= 2:
            winner_index = random.randrange(len(game["players"]))
            winner = game["players"][winner_index]
            await GroupRouletteRoundView.finish_game(interaction, game_id, winner, winner_index)
            return

        # Randomly pick a new player for the next turn.
        selected = random.choice(game["players"])
        game["selected_id"] = selected.id

        view = GroupRouletteRoundView(game_id)
        embed = discord.Embed(
            title="🎡 Group Roulette",
            description=(
                f"🎯 **{selected.mention}** choose someone to eliminate or press **Random**.\n\n"
                + (
                    f"💰 Prize: **{game['amount']:,} Tolar**\n"
                    if game["amount"] > 0
                    else "🎁 **No prize**\n"
                )
                + f"👥 Remaining: **{len(game['players'])}**"
            ),
            color=discord.Color.from_rgb(184, 145, 55),
        )
        # The wheel shows the selected player and then stops on their name.
        selected_index = game["players"].index(selected)
        img_buf = None
        try:
            img_buf = await _get_cached_roulette_wheel(
                game["players"],
                selected_index,
            )
            file = discord.File(img_buf, filename="roulette_wheel.gif")
            embed.set_image(url="attachment://roulette_wheel.gif")

            # Each new round appears in a separate message instead of editing the previous round's message.
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

    @discord.ui.button(label="Random", style=discord.ButtonStyle.success, emoji="🎲")
    async def random_kick(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = ACTIVE_GROUP_ROULETTE.get(self.game_id)
        if not game or not game["started"]:
            return await interaction.response.send_message("❌ Game unavailable.", ephemeral=True)

        if interaction.user.id != game["selected_id"]:
            return await interaction.response.send_message("❌ It's not your turn.", ephemeral=True)

        candidates = [m for m in game["players"] if m.id != game["selected_id"]]
        if not candidates:
            return await interaction.response.send_message("❌ No player to eliminate.", ephemeral=True)

        target = random.choice(candidates)
        await interaction.response.defer()
        await self.eliminate_and_continue(interaction, self.game_id, target)

    @staticmethod
    async def finish_game(interaction, game_id, winner, winner_index):
        game = ACTIVE_GROUP_ROULETTE.pop(game_id, None)
        if not game:
            return

        for member in game["players"]:
            ACTIVE_GROUP_ROULETTE_USERS.discard(member.id)

        if game["amount"] > 0:
            add_balance(winner.id, game["amount"])

        embed = discord.Embed(
            title="🏆 Group Roulette Finished",
            description=(
                f"🎉 **You won, {winner.mention}!**\n\n"
                + (
                    f"💰 **{game['amount']:,} Tolar** have been added to your balance."
                    if game["amount"] > 0
                    else "🎁 **The game ended with no monetary prize.**"
                )
            ),
            color=discord.Color.from_rgb(232, 198, 106),
        )
        embed.set_footer(text=f"Final number of participants: {len(game['players'])}")

        img_buf = None
        try:
            img_buf = await _get_cached_roulette_wheel(
                game["players"],
                winner_index,
            )
            file = discord.File(img_buf, filename="roulette_winner.gif")
            embed.set_image(url="attachment://roulette_winner.gif")

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
        # The game had started, so we refund the prize only if it hasn't finished.
        ACTIVE_GROUP_ROULETTE.pop(self.game_id, None)
        if game["amount"] > 0:
            add_balance(game["host"].id, game["amount"])
        for member in game["players"]:
            ACTIVE_GROUP_ROULETTE_USERS.discard(member.id)
        if self.message:
            try:
                await self.message.edit(
                    content="⏰ Game ended due to inactivity; the prize has been refunded to the host.",
                    attachments=[],
                    view=None,
                )
            except Exception:
                pass


@bot.command(name="roulette")
@in_channel(GAMES_CHANNEL_ID)
async def group_roulette_game(ctx, amount_text=None):
    """Usage: roulette or roulette 1000. Without an amount, the game has no prize."""
    if amount_text is None:
        amount = 0
    else:
        amount = _roulette_number(amount_text)
        if amount is None:
            await ctx.send(
                "❌ Correct usage: `roulette` or `roulette 1000` – the amount must be a number greater than zero.",
                delete_after=5,
            )
            return

    host_id = ctx.author.id
    if host_id in ACTIVE_GROUP_ROULETTE_USERS:
        await ctx.send("❌ You already have an active roulette game.", delete_after=4)
        return

    balance = get_balance(host_id)
    if amount > 0 and balance < amount:
        await ctx.send(
            f"❌ You don't have enough Tolar. You need **{amount:,}** Tolar "
            f"but your balance is **{balance:,}** Tolar.",
            delete_after=5,
        )
        return

    # If a prize amount is given, reserve it from the host.
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
# 🧠 Emoji Memory Game
# ==========================================

EMOJI_MEMORY_ACTIVE = set()

# Common emoji ranges for colourful/symbolic emojis.
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
    """Check if at least one Unicode emoji is present."""
    return any(
        (start <= ord(ch) <= end) or ord(ch) in _EMOJI_EXTRA
        for ch in value
    )


def _is_single_emoji_message(content: str) -> bool:
    """
    Only start the game if the message is exactly one emoji
    (allowing variation selectors, ZWJ, skin tones).
    Also supports Discord custom emojis.
    """
    content = content.strip()
    if not content:
        return False

    # Custom emoji: <:name:id> or <a:name:id>
    if re.fullmatch(r"<a?:\w+:\d+>", content):
        return True

    # Unicode emoji: strip common adornments and check for a single emoji base.
    base_chars = [
        ch for ch in content
        if ord(ch) not in {0xFE0E, 0xFE0F, 0x200D}
        and not (0x1F3FB <= ord(ch) <= 0x1F3FF)
    ]
    if len(base_chars) == 1:
        return _contains_unicode_emoji(base_chars[0])

    # Some emojis are two regional indicators (flags).
    if len(base_chars) == 2 and all(0x1F1E6 <= ord(ch) <= 0x1F1FF for ch in base_chars):
        return True

    return False


def _emoji_button_data(emoji: str):
    """Return the appropriate data for a Discord button, whether Unicode or Custom Emoji."""
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
                "❌ This game is not for you.",
                ephemeral=True,
            )
            return

        if self.answered:
            await interaction.response.send_message(
                "ℹ️ You already answered this round.",
                ephemeral=True,
            )
            return

        self.answered = True
        self.stop()
        EMOJI_MEMORY_ACTIVE.discard(self.player_id)

        correct = index == self.target_index
        if correct:
            add_balance(self.player_id, 30)
            title = "🎉 Correct!"
            description = (
                f"Well done! **{self.target_emoji}** was at position **{self.target_index + 1}**.\n"
                "💰 You earned **30 Tolar**."
            )
            color = discord.Color.green()
        else:
            # Do not let balance go below zero.
            current_balance = get_balance(self.player_id)
            penalty = min(10, max(0, current_balance))
            if penalty:
                remove_balance(self.player_id, penalty)

            title = "❌ Wrong!"
            description = (
                f"**{self.target_emoji}** was at position **{self.target_index + 1}**.\n"
                f"💸 **{penalty} Tolar** deducted from your balance."
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
            name="Target Emoji",
            value=self.target_emoji,
            inline=True,
        )
        embed.add_field(
            name="Correct Position",
            value=f"Button **{self.target_index + 1}**",
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
                title="⏰ Time's up!",
                description=(
                    f"**{self.target_emoji}** was at position **{self.target_index + 1}**.\n"
                    f"💸 **{penalty} Tolar** deducted from your balance."
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

    # If no specific emoji is given, pick a random one.
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
        title="🧠 Try to remember the emoji positions",
        description=(
            "Memorise the positions of the emojis well!\n\n"
            "After **3 seconds**, the emojis will disappear, and I'll ask you where the emoji you typed is."
        ),
        color=discord.Color.blurple(),
    )
    embed.add_field(
        name="Emojis",
        value="  ".join(f"**{i + 1}.** {emoji}" for i, emoji in enumerate(cells)),
        inline=False,
    )
    embed.set_footer(text="⏳ Memorise the positions...")

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

        # After 3 seconds: hide the emojis from the buttons, keep only numbers
        for child in view.children:
            if isinstance(child, discord.ui.Button):
                child.emoji = None
                child.label = str(
                    int(child.custom_id.rsplit(":", 1)[-1]) + 1
                )

        question_embed = discord.Embed(
            title="🧠 Where is the emoji?",
            description=(
                f"Where was the **{target}** emoji?\n\n"
                "Choose the correct position from the buttons below."
            ),
            color=discord.Color.gold(),
        )
        question_embed.set_footer(text="⏱️ You have 30 seconds to answer")

        await sent.edit(embed=question_embed, view=view)

    except Exception:
        EMOJI_MEMORY_ACTIVE.discard(player_id)
        raise


@bot.event
async def on_message(message):
    """Process automatic replies, emojis/stickers, and then pass the message to commands.

    Important: process_commands must be called even if an error occurs in any part
    of the message handling, otherwise @bot.command commands won't work.
    """
    if message.author.bot:
        await bot.process_commands(message)
        return

    try:
        # 🎬 Instagram / TikTok download as soon as the link arrives
        social_match = _SOCIAL_VIDEO_RE.search(message.content)
        if social_match:
            await _download_and_send_social_video(message, social_match.group(0))
            return

        # Emoji memory game: triggered when the user types exactly "emoji".
        # The target emoji is chosen randomly inside the game.
        if message.content.strip().lower() == "emoji":
            await start_emoji_memory_game(message)
            return

        # 1. Keyword replies
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

        # 2. Member replies (on mention)
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
                    break  # Only handle the first mentioned member

        # 3. Enlarge emojis and stickers in the avatar channel
        if message.channel.id == THEFT_CHANNEL_ID:
            # Extract custom emojis from the message content using Discord's standard format
            custom_emojis = re.findall(
                r"<(?P<animated>a?):(?P<name>\w+):(?P<id>\d+)>",
                message.content,
            )

            if custom_emojis:
                animated, _name, emoji_id = custom_emojis[0]
                extension = "gif" if animated else "png"
                emoji_url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{extension}"
                await enlarge_and_send(message.channel, emoji_url, "emoji")

            # Handle stickers
            if message.stickers:
                sticker = message.stickers[0]
                await enlarge_and_send(message.channel, sticker.url, "sticker")

    except Exception as e:
        # Do not let errors in auto‑replies or emojis prevent commands.
        print(f"[ON_MESSAGE ERROR] {type(e).__name__}: {e}")
    finally:
        # This call is required because we have a custom on_message.
        await bot.process_commands(message)


# Update cache on startup/reconnect.
@bot.event
async def on_ready():
    global replies_cache
    replies_cache = load_replies()
    print(
        f"✅ Bot is ready! Logged in as {bot.user} "
        f"| Loaded {len(replies_cache['member'])} members and {len(replies_cache['word'])} keyword replies."
    )
    bot.add_view(TicketView())
    bot.add_view(TicketDeleteView())


# Run the bot using an environment variable on Render.
# Do not put the token directly in the file to avoid leaking it.
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
if not DISCORD_TOKEN:
    raise RuntimeError(
        "❌ DISCORD_TOKEN not found. "
        "Add the environment variable DISCORD_TOKEN in Render > Environment."
    )

bot.run(DISCORD_TOKEN)