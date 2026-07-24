import discord
from discord.ext import commands
import json
import os
import asyncio
import aiohttp
from threading import Thread
from flask import Flask

# --- 1. خادم الويب والزيارة الذاتية ---
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

# --- 2. إعدادات البوت والبيانات ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# إعدادات الحفظ السحابي على GitHub
GITHUB_TOKEN = "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"
REPO_OWNER = "true561290-boop"
REPO_NAME = "my_bot"
FILE_PATH = "bank.json"

ADMIN_ROLE_ID = 1515396547528102131

bot.user_bank = {}

# --- 3. دالات التعامل مع قاعدة البيانات ---
async def load_data_from_github():
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{FILE_PATH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    import base64
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers) as r:
                if r.status == 200:
                    content = await r.json()
                    file_data = base64.b64decode(content['content']).decode('utf-8')
                    data = json.loads(file_data)
                    bot.user_bank.update(data)
                    print("✅ [GitHub Cloud] تم تحميل بيانات البنك بنجاح!")
                else:
                    print(f"⚠️ [GitHub Cloud] فشل التحميل بكود: {r.status}")
        except Exception as e:
            print(f"⚠️ [GitHub Cloud] خطأ أثناء التحميل: {e}")

async def async_update_balance(user_id, amount):
    uid = str(user_id)
    import base64
    
    if not bot.user_bank:
        await load_data_from_github()

    # بداية الرصيد هي 0
    if uid not in bot.user_bank:
        bot.user_bank[uid] = 0

    bot.user_bank[uid] += amount
    
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{FILE_PATH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    
    async with aiohttp.ClientSession() as session:
        try:
            sha = None
            async with session.get(url, headers=headers) as r:
                if r.status == 200:
                    res_json = await r.json()
                    sha = res_json['sha']
            
            js_bytes = json.dumps(bot.user_bank, ensure_ascii=False, indent=4).encode('utf-8')
            encoded = base64.b64encode(js_bytes).decode('utf-8')
            
            payload = {
                "message": "🔄 تحديث تلقائي لرصيد البنك",
                "content": encoded
            }
            if sha:
                payload["sha"] = sha
                
            async with session.put(url, headers=headers, json=payload) as r_put:
                if r_put.status in [200, 201]:
                    print("✅ [GitHub Cloud] تم حفظ الرصيد بنجاح!")
        except Exception as e:
            print(f"⚠️ [GitHub Cloud] خطأ أثناء الحفظ: {e}")

def get_balance(user_id):
    uid = str(user_id)
    if uid not in bot.user_bank:
        bot.user_bank[uid] = 0
    return bot.user_bank[uid]

# --- 4. أوامر البنك المعدلة ---
@bot.command(name="تجربة")
async def ping(ctx):
    await ctx.send("🏓 البوت يعمل بنجاح وبدون مشاكل!")

# أمر عرض الرصيد الجديد
@bot.command(name="طولاري")
async def check_wallet(ctx):
    balance = get_balance(ctx.author.id)
    embed = discord.Embed(
        title="💳 بطاقة حسابك البنكي",
        color=discord.Color.gold()
    )
    embed.add_field(name="صاحب الحساب", value=ctx.author.mention, inline=False)
    embed.add_field(name="الرصيد الحالي", value=f"**{balance:,}** طولار 💸", inline=False)
    embed.set_footer(text="B✰IL Bank System")
    await ctx.send(embed=embed)

# أمر التحويل المحدث
@bot.command(name="تحويل")
async def transfer_money(ctx, member: discord.Member = None, amount: int = None):
    if not member or not amount:
        await ctx.send("⚠️ الاستخدام الصحيح: `!تحويل @العضو المبلغ`")
        return

    if amount <= 0:
        await ctx.send("⚠️ لا يمكنك تحويل مبلغ أقل من 1!")
        return

    sender_bal = get_balance(ctx.author.id)
    if sender_bal < amount:
        await ctx.send(f"⚠️ رصيدك غير كافٍ! رصيدك الحالي: **{sender_bal} طولار**")
        return

    await async_update_balance(ctx.author.id, -amount)
    await async_update_balance(member.id, amount)
    await ctx.send(f"✅ تم تحويل **{amount} طولار** بنجاح إلى {member.mention} 💸!")

# أمر إضافة الرصيد الخاص بالأدمن (اضافة)
@bot.command(name="اضافة")
async def give_money(ctx, member: discord.Member = None, amount: int = None):
    has_admin = any(role.id == ADMIN_ROLE_ID for role in ctx.author.roles)
    if not has_admin and not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ ليس لديك صلاحية لاستخدام هذا الأمر!")
        return

    if not member or not amount:
        await ctx.send("⚠️ الاستخدام الصحيح: `!اضافة @العضو المبلغ`")
        return

    await async_update_balance(member.id, amount)
    await ctx.send(f"👑 تم إضافة **{amount} طولار** إلى حساب {member.mention} بنجاح!")

# --- 5. أحداث التشغيل ---
@bot.event
async def on_ready():
    print(f"✅ تم تسجيل الدخول باسم: {bot.user.name}")
    await load_data_from_github()
    bot.loop.create_task(self_ping())

# --- 6. التشغيل ---
bot.run(os.environ.get('DISCORD_TOKEN'))