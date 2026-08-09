import os
import re
import urllib.parse
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

    # استخراج الموسم والحلقة بذكاء
    season_match = re.search(r'الموسم\s*(\d+)', query)
    episode_match = re.search(r'الحلقة\s*(\d+)', query)

    season = season_match.group(1) if season_match else "1"
    episode = episode_match.group(1) if episode_match else "1"

    # تنظيف اسم الأنمي من الكلمات الزائدة
    anime_name = re.sub(r'(الموسم\s*\d+|الحلقة\s*\d+)', '', query).strip()
    
    # تجهيز نص بحث دقيق (الاسم + الحلقة) للحصول على أفضل نتيجة داخل المواقع
    clean_search = f"{anime_name} الحلقة {episode}"
    encoded_query = urllib.parse.quote(clean_search)

    # روابط البحث الداخلي المباشرة للمواقع (تتخطى جوجل وتفتح الموقع نفسه)
    witanime_link = f"https://witanime.pics/?s={encoded_query}"
    elif_news_link = f"https://r.elif.news/?s={encoded_query}"
    animearab_link = f"https://animearab.com/?s={encoded_query}"

    # تصميم رسالة البوت (Embed)
    embed = discord.Embed(
        title=f"🎬 {anime_name.title()}",
        description=f"**الموسم:** {season} | **الحلقة:** {episode}",
        color=discord.Color.from_rgb(46, 139, 87)
    )

    embed.add_field(
        name="📺 روابط المشاهدة المباشرة:",
        value=(
            f"🔗 **[مشاهدة عبر Witanime]({witanime_link})**\n"
            f"🔗 **[مشاهدة عبر r.elif.news]({elif_news_link})**\n"
            f"🔗 **[مشاهدة عبر انمي عرب]({animearab_link})**"
        ),
        inline=False
    )
    
    avatar_url = ctx.author.display_avatar.url if ctx.author.display_avatar else None
    embed.set_footer(
        text=f"طلب بواسطة {ctx.author.display_name} | مشاهدة ممتعة 🍿",
        icon_url=avatar_url
    )

    await ctx.send(embed=embed)

bot.run(os.environ.get("DISCORD_TOKEN"))