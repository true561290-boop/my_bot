import re
import asyncio
import datetime
import io
import os
import random
import math
from threading import Thread
import typing

import aiohttp
import discord
from discord.ext import commands
from flask import Flask
import requests

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
intents.members = True
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
    مثال: .انمي sakamoto days الموسم 1 الحلقة 7
    """
    if not query:
        await ctx.send(
            "⚠️ **طريقة الاستخدام الصحيحة:**
"
            "اكتب اسم الأنمي مع الموسم والحلقة.
"
            "مثال: `.انمي sakamoto days الموسم 1 الحلقة 7`",
            delete_after=10,
        )
        return

    # تحليل الطلب استخراج اسم الأنمي، الموسم، والحلقة إن أمكن
    embed = discord.Embed(
        title="🎬 نتائج البحث عن الحلقة المباشرة",
        description=f"🔍 **الطلب:** `{query}`",
        color=discord.Color.from_rgb(46, 139, 87),
    )

    # توفير روابط موثوقة ومباشرة للبحث والمشاهدة بجودات متعددة بدون تقطيع
    # روابط لمواقع مشاهدة عربية وعالمية شهيرة موثوقة (مثل Witanime, AnimeSlayer, Zoro/AniWatch search links)
    encoded_query = query.replace(" ", "+")
    
    witanime_url = f"https://witanime.io/?search={encoded_query}"
    anime_slayer_search = f"https://www.google.com/search?q={encoded_query}+witanime+عصير_الكتب"
    quality_links = (
        f"🔗 **[منصة Witanime (مشاهدة وتحميل مباشر بجودات متعددة)]( {witanime_url} )**
"
        f"🔗 **[بحث مباشر عن الجودات العالية (FHD / HD)]( https://www.google.com/search?q={encoded_query}+الحلقة+بجودة+عالية )**
"
        f"🔗 **[روابط احتياطية للمشاهدة بدون تقطيع]( https://animetosho.org/search?q={encoded_query} )**"
    )

    embed.add_field(
        name="📺 روابط المشاهدة المباشرة والجودات",
        value=quality_links,
        inline=False,
    )
    embed.set_footer(
        text=f"اطلب بواسطة {ctx.author.display_name} | مشاهدة ممتعة بدون تقطيع 🍿",
        icon_url=ctx.author.display_avatar.url,
    )

    await ctx.send(embed=embed)


@bot.command(name="ايدي")
async def get_id(ctx, target: typing.Union[discord.TextChannel, discord.Member, discord.Role, str] = None):
    if not target:
        await ctx.send(f"🆔 الآيدي الخاص بك: `{ctx.author.id}`")
        return
    if ctx.message.mentions:
        member = ctx.message.mentions[0]
        await ctx.send(f"🆔 آيدي العضو {member.mention}: `{member.id}`")
        return
    await ctx.send("❌ لم يتم العثور على العنصر المطلوب.")


@bot.event
async def on_ready():
    print(f"✅ تم تسجيل الدخول باسم: {bot.user.name}")
    fetch_latest_balances_from_github()


bot.run(os.environ.get("DISCORD_TOKEN"))