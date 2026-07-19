import discord
from discord.ext import commands
import random
import asyncio
import json
import os

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# --- نظام الحفظ الأوتوماتيكي للبيانات (البنك) ---
FILE_PATH = "bank.json"

def load_data():
    """دالة لقراءة البيانات من الملف عند تشغيل البوت"""
    if not os.path.exists(FILE_PATH):
        return {}
    try:
        with open(FILE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_data(data):
    """دالة لحفظ البيانات داخل الملف فوراً عند أي تغيير"""
    with open(FILE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# تحميل البيانات في ذاكرة البوت
bot.user_bank = load_data()

def get_balance(user_id):
    """دالة لجلب رصيد المستخدم، وإذا لم يكن مسجلاً تمنحه 200 دولار كبداية"""
    uid = str(user_id)
    if uid not in bot.user_bank:
        bot.user_bank[uid] = 200
        save_data(bot.user_bank)
    return bot.user_bank[uid]

def update_balance(user_id, amount):
    """دالة لتحديث الرصيد (زيادة أو نقصان) وحفظ التغيير فوراً"""
    uid = str(user_id)
    current = get_balance(user_id)
    bot.user_bank[uid] = current + amount
    save_data(bot.user_bank)

# --- أوامر الألعاب المباشرة ---

@bot.command(name="قنبلة")
async def game_bomb(ctx):
    """أمر لتشغيل لعبة القنبلة مباشرة عبر كتابة !قنبلة"""
    await ctx.send("💥 **بدأت لعبة القنبلة!** اختر سلكاً لتقطيعه: 🔴 احمر | 🔵 ازرق | 🟢 اخضر (اكتب اللون في الشات)")
    
    correct_wire = random.choice(["احمر", "ازرق", "اخضر"])
    
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content in ["احمر", "ازرق", "اخضر", "أحمر", "أزرق", "أخضر"]

    try:
        msg = await bot.wait_for('message', check=check, timeout=30.0)
        user_choice = msg.content.replace("أ", "ا") # توحيد الحروف لتفادي أخطاء الكتابة
        
        if user_choice == correct_wire:
            update_balance(ctx.author.id, 50)
            await ctx.send(f"🎉 كفو! نجوت من الانفجار وربحت **50 دولار** 💵! رصيدك الحالي: {get_balance(ctx.author.id)} دولار.")
        else:
            update_balance(ctx.author.id, -20)
            await ctx.send(f"💥 طرااااخ! انفجرت القنبلة! السلك الصحيح كان {correct_wire}. خسرت **20 دولار** 💸. رصيدك الحالي: {get_balance(ctx.author.id)} دولار.")
    except asyncio.TimeoutError:
        await ctx.send(f"⏱️ انتهى الوقت! انفجرت القنبلة لأنك تأخرت في الاختيار.")

@bot.command(name="سؤال")
async def game_quiz(ctx):
    """أمر لتشغيل لعبة الأسئلة مباشرة عبر كتابة !سؤال"""
    questions = {
        "ما هي عاصمة السعودية؟": "الرياض",
        "كم عدد قارات العالم؟": "7",
        "ما هو أسرع حيوان بري؟": "الفهد"
    }
    q, a = random.choice(list(questions.items()))
    await ctx.send(f"🧠 **سؤال:** {q}")

    def check(m):
        return m.channel == ctx.channel and m.content.strip() == a

    try:
        msg = await bot.wait_for('message', check=check, timeout=30.0)
        update_balance(msg.author.id, 30)
        await ctx.send(f"🎉 إجابة صحيحة من {msg.author.mention}! ربحت **30 دولار** 💵. رصيدك الحالي: {get_balance(msg.author.id)} دولار.")
    except asyncio.TimeoutError:
        await ctx.send(f"⏱️ انتهى الوقت! الإجابة الصحيحة كانت: {a}")

# --- الأوامر العامة ---

@bot.command(name="فلوس")
async def check_wallet(ctx):
    """أمر لمعرفة الرصيد بالدولار"""
    balance = get_balance(ctx.author.id)
    await ctx.send(f"💳 | رصيدك الحالي يا {ctx.author.mention} هو: **{balance} دولار** 💵.")

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name}")

# تشغيل البوت بأمان عبر Render
bot.run(os.environ.get('DISCORD_TOKEN'))