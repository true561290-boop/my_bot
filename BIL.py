import os
import re
from threading import Thread
import discord
from discord.ext import commands
from flask import Flask

# --- 1. خادم الويب للحفاظ على استمرار التشغيل 24/7 ---
app = Flask("")

@app.route("/")
def home():
    return "Anime Tracker Bot is Online!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.daemon = True
    t.start()

keep_alive()

# --- 2. إعدادات البوت والبيانات الأساسية ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=".", intents=intents)
bot.remove_command("help")

@bot.event
async def on_ready():
    print(f"✅ تم تسجيل الدخول بنجاح باسم {bot.user}")

# --- 3. نظام متابعة وتحميل الأنمي ---
@bot.command(name="انمي", aliases=["anime", "حلقة"])
async def anime_search(ctx, *, query: str = None):
    """
    أمر لمتابعة وحفظ روابط حلقات الأنمي بجودات متعددة ومباشرة.
    """
    if not query:
        embed = discord.Embed(
            title="⚠️ طريقة الاستخدام الصحيحة",
            description="اكتب اسم الأنمي مع الموسم والحلقة.\n**مثال:** `.انمي sakamoto days الموسم 1 الحلقة 7`",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed, delete_after=15)
        return

    # تحليل الطلب لاستخراج الموسم والحلقة باستخدام (Regex)
    season_match = re.search(r'الموسم\s*(\d+)', query)
    episode_match = re.search(r'الحلقة\s*(\d+)', query)

    season = season_match.group(1) if season_match else "1"
    episode = episode_match.group(1) if episode_match else "1"

    # استخراج اسم الأنمي وتنظيفه من كلمة "الموسم" و "الحلقة"
    anime_name = re.sub(r'(الموسم\s*\d+|الحلقة\s*\d+)', '', query).strip()
    anime_slug = anime_name.replace(" ", "-").lower()

    # تجهيز الروابط المباشرة للمواقع السريعة
    # 1. محاولة بناء رابط مباشر لموقع Witanime
    witanime_direct = f"https://witanime.pics/episode/{anime_slug}-الموسم-{season}-الحلقة-{episode}/"
    
    # 2. روابط بحث دقيقة في مواقع سريعة لا تقطع (XSAnime و AnimeSlayer)
    search_query = f"{anime_name} الموسم {season} الحلقة {episode}".replace(" ", "+")
    xsanime_search = f"https://xsanime.com/?s={search_query}"
    google_search = f"https://www.google.com/search?q={search_query}+مترجم+موقع+ويتانمي+او+انمي+سلاير"

    # تصميم رسالة البوت (Embed)
    embed = discord.Embed(
        title=f"🎬 {anime_name.title()}",
        description=f"**الموسم:** {season} | **الحلقة:** {episode}",
        color=discord.Color.from_rgb(46, 139, 87)
    )

    embed.add_field(
        name="📺 روابط المشاهدة (سيرفرات سريعة):",
        value=(
            f"🔗 **[رابط ويتانمي المباشر (قد يحتاج VPN ببعض الدول)]({witanime_direct})**\n"
            f"🔗 **[بحث سريع في XSAnime (بدون تقطيع)]({xsanime_search})**\n"
            f"🔗 **[بحث شامل للجودات العالية (Google)]({google_search})**"
        ),
        inline=False
    )
    
    avatar_url = ctx.author.display_avatar.url if ctx.author.display_avatar else None
    embed.set_footer(
        text=f"طلب بواسطة {ctx.author.display_name} | مشاهدة ممتعة بدون تقطيع 🍿",
        icon_url=avatar_url
    )

    await ctx.send(embed=embed)

bot.run(os.environ.get("DISCORD_TOKEN"))