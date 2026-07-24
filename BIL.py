import discord
from discord.ext import commands
import os
import asyncio
import aiohttp
from threading import Thread
from flask import Flask

# --- 1. خادم الويب والزيارة الذاتية (لإبقاء البوت شغالاً) ---
app = Flask('')

@app.route('/')
def home():
    return "B✰IL Bot is Online!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.daemon = True
    t.start()

keep_alive()

async def self_ping():
    await asyncio.sleep(10)
    render_url = os.environ.get("RENDER_EXTERNAL_URL", "http://127.0.0.1:8080")
    
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(render_url) as resp:
                    print(f"🔄 [Self-Ping] تم زيارة البوت لنفسه! كود الاستجابة: {resp.status}")
            except Exception as e:
                print(f"⚠️ [Self-Ping] خطأ: {e}")
            
            await asyncio.sleep(300)

# --- 2. إعدادات البوت الأساسية ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ تم تسجيل الدخول بنجاح باسم: {bot.user.name}")
    bot.loop.create_task(self_ping())

# تجربة أمر بسيط جداً للتأكد من الاستجابة
@bot.command(name="تجربة")
async def ping(ctx):
    await ctx.send("🏓 البوت يعمل بنجاح وبدون مشاكل!")

# --- 3. التشغيل ---
bot.run(os.environ.get('DISCORD_TOKEN'))