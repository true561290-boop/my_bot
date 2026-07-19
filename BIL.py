import discord
from discord.ext import commands
import random
import json
import os
import asyncio

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# --- نظام الحفظ الأوتوماتيكي للبيانات (البنك) ---
FILE_PATH = "bank.json"

def load_data():
    if not os.path.exists(FILE_PATH):
        return {}
    try:
        with open(FILE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_data(data):
    with open(FILE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

bot.user_bank = load_data()

def get_balance(user_id):
    uid = str(user_id)
    if uid not in bot.user_bank:
        bot.user_bank[uid] = 200
        save_data(bot.user_bank)
    return bot.user_bank[uid]

def update_balance(user_id, amount):
    uid = str(user_id)
    current = get_balance(user_id)
    bot.user_bank[uid] = current + amount
    save_data(bot.user_bank)

# --- واجهة أزرار لعبة القنبلة ---
class BombButtons(discord.ui.View):
    def __init__(self, author, correct_wire):
        super().__init__(timeout=30.0)
        self.author = author
        self.correct_wire = correct_wire
        self.answered = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.author:
            await interaction.response.send_message("❌ هذه اللعبة ليست لك! اكتب `!قنبلة` لتبدأ لعبتك الخاصة.", ephemeral=True)
            return False
        return True

    async def process_choice(self, interaction: discord.Interaction, chosen_wire: str):
        self.answered = True
        self.stop()

        if chosen_wire == self.correct_wire:
            update_balance(self.author.id, 50)
            await interaction.response.edit_message(
                content=f"🎉 **كفو!** نجوت من الانفجار وقطعت السلك الصحيح ({chosen_wire}) وربحت **50 دولار** 💵!\nرصيدك الحالي: {get_balance(self.author.id)} دولار.",
                view=None
            )
        else:
            update_balance(self.author.id, -20)
            await interaction.response.edit_message(
                content=f"💥 **طرااااخ!** انفجرت القنبلة! السلك الصحيح كان ({self.correct_wire}). خسرت **20 دولار** 💸.\nرصيدك الحالي: {get_balance(self.author.id)} دولار.",
                view=None
            )

    @discord.ui.button(label="أحمر 🔴", style=discord.ButtonStyle.danger)
    async def red_wire(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_choice(interaction, "أحمر")

    @discord.ui.button(label="أزرق 🔵", style=discord.ButtonStyle.primary)
    async def blue_wire(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_choice(interaction, "أزرق")

    @discord.ui.button(label="أخضر 🟢", style=discord.ButtonStyle.success)
    async def green_wire(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_choice(interaction, "أخضر")

# --- أوامر الألعاب المباشرة ---

@bot.command(name="قنبلة")
async def game_bomb(ctx):
    correct_wire = random.choice(["أحمر", "أزرق", "أخضر"])
    view = BombButtons(author=ctx.author, correct_wire=correct_wire)
    msg = await ctx.send("💥 **بدأت لعبة القنبلة!** اختر سلكاً لتقطيعه بالضغط على أحد الأزرار أدناه:", view=view)
    await view.wait()
    if not view.answered:
        await msg.edit(content="⏱️ **انتهى الوقت!** انفجرت القنبلة لأنك تأخرت في الضغط على الزر.", view=None)

@bot.command(name="سؤال")
async def game_quiz(ctx):
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

@bot.command(name="فلوس")
async def check_wallet(ctx):
    balance = get_balance(ctx.author.id)
    await ctx.send(f"💳 | رصيدك الحالي يا {ctx.author.mention} هو: **{balance} دولار** 💵.")

# --- الطريقة الصحيحة والمحدثة لتحميل الملفات الخارجية (Cogs) ---
@bot.event
async def setup_hook():
    try:
        await bot.load_extension("moderation")
        print("Successfully loaded moderation commands!")
    except Exception as e:
        print(f"Failed to load moderation setup: {e}")

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name}")
    
    # في ملف BIL.py عند إنشاء البوت:
bot = commands.Bot(
    command_prefix="!", 
    intents=intents, 
    allowed_mentions=discord.AllowedMentions(users=False, roles=False, everyone=False)
)
    

bot.run(os.environ.get('DISCORD_TOKEN'))