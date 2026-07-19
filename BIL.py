import discord
from discord.ext import commands
import random
import asyncio
import json
import os

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# --- 1. نظام الحفظ الأبدي باستخدام ملف JSON ---
FILE_PATH = "bank.json"

def load_data():
    """دالة لقراءة البيانات من الملف عند تشغيل البوت"""
    if not os.path.exists(FILE_PATH):
        return {}  # إذا كان الملف غير موجود، نرجع قاموساً فارغاً
    try:
        with open(FILE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_data(data):
    """دالة لحفظ البيانات داخل الملف فوراً عند أي تغيير"""
    with open(FILE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# تحميل البيانات المخزنة فور بدء التشغيل
user_bank = load_data()

def add_dollars(user_id, amount):
    """دالة إضافة الطولارات مع حفظها تلقائياً في الملف"""
    str_id = str(user_id)  # ملفات JSON تحول الأرقام إلى نصوص تلقائياً
    if str_id not in user_bank:
        user_bank[str_id] = 0
    user_bank[str_id] += amount
    save_data(user_bank)  # حفظ التعديل فوراً للأبد!

# --- 2. بنك الألعاب ---
QUESTIONS = [
    {"سؤال": "ما هو أطول نهر في العالم؟", "إجابة": "النيل"},
    {"سؤال": "ما هي عاصمة اليابان؟", "إجابة": "طوكيو"},
    {"سؤال": "كم عدد كواكب المجموعة الشمسية؟", "إجابة": "8"}
]

ANIME_CHARACTERS = [
    {"صورة": "https://img.abc185.com/luffy.jpg", "اسم": "لوفي"},
    {"صورة": "https://img.abc185.com/naruto.jpg", "اسم": "ناروتو"},
    {"صورة": "https://img.abc185.com/goku.jpg", "اسم": "غوكو"}
]

@bot.event
async def on_ready():
    print(f"✅ البوت متصل وجاهز ونظام الحفظ الأبدي مفعّل: {bot.user}")

@bot.event
async def on_message(message):
    if message.author == bot.user: return
    await bot.process_commands(message)

# --- 3. أمر فحص المحفظة ---
@bot.command(name="فلوس", aliases=["طولارات", "رصيدي"])
async def check_balance(ctx):
    balance = user_bank.get(str(ctx.author.id), 0)
    await ctx.send(f"💳 | محفظة **{ctx.author.display_name}** تحتوي على: **{balance} طولار** 💵")

# --- كود أزرار لعبة القنبلة ---
class BombView(discord.ui.View):
    def __init__(self, author_id):
        super().__init__(timeout=30.0)
        self.author_id = author_id
        self.winning_wire = random.randint(1, 3)

    async def disable_all_buttons(self, interaction: discord.Interaction, result_text: str):
        for item in self.children:
            item.disabled = True
            item.style = discord.ButtonStyle.secondary
        await interaction.response.edit_message(content=result_text, view=self)

    @discord.ui.button(label="🔴 الأحمر", style=discord.ButtonStyle.danger)
    async def red_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id: return await interaction.response.send_message("❌ ليست لعبتك!", ephemeral=True)
        if self.winning_wire == 1: 
            add_dollars(interaction.user.id, 100)
            await self.disable_all_buttons(interaction, "🎉 كفو! فككت القنبلة بنجاح! وربحت 100 طولار! 💵")
        else: 
            await self.disable_all_buttons(interaction, "💥 بوم! انفجرت القنبلة! 💀")

    @discord.ui.button(label="🔵 الأزرق", style=discord.ButtonStyle.primary)
    async def blue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id: return await interaction.response.send_message("❌ ليست لعبتك!", ephemeral=True)
        if self.winning_wire == 2: 
            add_dollars(interaction.user.id, 100)
            await self.disable_all_buttons(interaction, "🎉 كفو! فككت القنبلة بنجاح! وربحت 100 طولار! 💵")
        else: 
            await self.disable_all_buttons(interaction, "💥 بوم! انفجرت القنبلة! 💀")

    @discord.ui.button(label="🟢 الأخضر", style=discord.ButtonStyle.success)
    async def green_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id: return await interaction.response.send_message("❌ ليست لعبتك!", ephemeral=True)
        if self.winning_wire == 3: 
            add_dollars(interaction.user.id, 100)
            await self.disable_all_buttons(interaction, "🎉 كفو! فككت القنبلة بنجاح! وربحت 100 طولار! 💵")
        else: 
            await self.disable_all_buttons(interaction, "💥 بوم! انفجرت القنبلة! 💀")

# --- القائمة المنسدلة الذكية ---
class GamesDropdown(discord.ui.Select):
    def __init__(self, author_id):
        self.author_id = author_id
        options = [
            discord.SelectOption(label="لعبة القنبلة 💣", description="تفكيك القنبلة يعطيك 100 طولار!", value="bomb"),
            discord.SelectOption(label="لعبة الأسئلة 🕒", description="الجواب الصحيح يعطيك 100 طولار!", value="quiz"),
            discord.SelectOption(label="خمن شخصية الأنمي 👤", description="التخمين الصحيح يعطيك 100 طولار!", value="guess_anime")
        ]
        super().__init__(placeholder="🎮 اختر اللعبة التي تريدها من هنا...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("❌ اكتب `!العاب` لتختار بنفسك!", ephemeral=True)

        if self.values[0] == "bomb":
            view = BombView(self.author_id)
            await interaction.response.edit_message(content="💣 **لقد اخترت لعبة القنبلة!**\nأمامك 3 أسلاك، اختر السلك الصحيح لتكسب الطولارات:", view=view)

        elif self.values[0] == "quiz":
            quiz_item = random.choice(QUESTIONS)
            question = quiz_item["سؤال"]
            correct_answer = quiz_item["إجابة"]
            await interaction.response.edit_message(content=f"🕒 **لقد اخترت لعبة الأسئلة! لديك 10 ثوانٍ للإجابة!**\n\n**السؤال هو:** {question}", view=None)

            def check_quiz(m):
                return m.channel == interaction.channel and m.content.strip() == correct_answer

            try:
                msg = await bot.wait_for('message', check=check_quiz, timeout=10.0)
                add_dollars(msg.author.id, 100)
                await interaction.channel.send(f"🎉 كفوووو يا {msg.author.mention}! إجابتك صحيحة وربحت **100 طولار**! 💵🥳")
            except asyncio.TimeoutError:
                await interaction.channel.send(f"⏰ **انتهى الوقت!** الإجابة الصحيحة كانت: **{correct_answer}** 🤓")

        elif self.values[0] == "guess_anime":
            char_item = random.choice(ANIME_CHARACTERS)
            char_image = char_item["صورة"]
            char_name = char_item["اسم"]

            await interaction.response.edit_message(content="👤 **لقد اخترت لعبة خمن شخصية الأنمي!**\nأمامكم **15 ثانية** لمعرفة الاسم وكسب الطولارات! 👇", view=None)
            await interaction.channel.send(char_image)

            def check_anime(m):
                return m.channel == interaction.channel and m.content.strip() == char_name

            try:
                msg = await bot.wait_for('message', check=check_anime, timeout=15.0)
                add_dollars(msg.author.id, 100)
                await interaction.channel.send(f"🔥 **أوووووه حريقة!** {msg.author.mention} عرف الشخصية وهي **({char_name})** وربح **100 طولار**! 💵🎉")
            except asyncio.TimeoutError:
                await interaction.channel.send(f"⏰ **انتهى الوقت!** الشخصية كانت: **{char_name}** 🤫")

class GamesDropdownView(discord.ui.View):
    def __init__(self, author_id):
        super().__init__(timeout=60.0)
        self.add_item(GamesDropdown(author_id))

@bot.command(name="العاب")
async def games(ctx):
    view = GamesDropdownView(ctx.author.id)
    await ctx.send("🎮 **مرحباً بك في قائمة الألعاب المتنوعة!**\nاختر لعبتك المفضلة واجمع الطولارات 💵:", view=view)

# ضع توكن بوتك هنا
bot.run("MTUyODA4MjM0NzgzOTMyNDIwMg.Gn4YH4.7iSGD7iptkXZuyawHveOFeVAcquatZOm1tsU8s")