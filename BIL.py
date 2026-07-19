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

# --- ⚙️ إعدادات سلع المتجر والأدمن ---
# ⚠️ استبدل الـ ID أدناه بـ ID الرتبة المسموح لها باستخدام أمر !اضافة
ADMIN_ROLE_ID = 111222333444555666 

ROLES_SHOP = {
    "role_1": {"name": "رتبة مميز ✨", "price": 500, "role_id": 111222333444555666},
    "role_2": {"name": "رتبة VIP 🔥", "price": 1500, "role_id": 777888999000111222},
    "role_3": {"name": "رتبة الملك 👑", "price": 5000, "role_id": 333444555666777888}
}

COLORS_SHOP = {
    "color_red": {"name": "اللون الأحمر 🔴", "price": 300, "role_id": 444555666777888999},
    "color_blue": {"name": "اللون الأزرق 🔵", "price": 300, "role_id": 111555666777888999},
    "color_green": {"name": "اللون الأخضر 🟢", "price": 300, "role_id": 222555666777888999}
}

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

# --- 🛒 كلاسات واجهة المتجر التفاعلية ---
class ItemPurchaseView(discord.ui.View):
    def __init__(self, author, items_dict, is_roles=True):
        super().__init__(timeout=60.0)
        self.author = author
        self.items_dict = items_dict
        
        for key, item in self.items_dict.items():
            button = discord.ui.Button(label=f"شراء: {item['name'].split()[0]}", style=discord.ButtonStyle.secondary, custom_id=key)
            button.callback = self.make_callback(item)
            self.add_item(button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.author:
            await interaction.response.send_message("❌ هذا المتجر تصفحه شخص آخر!", ephemeral=True)
            return False
        return True

    def make_callback(self, item):
        async def button_callback(interaction: discord.Interaction):
            user_balance = get_balance(self.author.id)
            if user_balance < item["price"]:
                await interaction.response.send_message(f"⚠️ | رصيدك غير كافٍ! تحتاج إلى **{item['price'] - user_balance} دولار** إضافية.", ephemeral=True)
                return

            role = interaction.guild.get_role(item["role_id"])
            if not role:
                await interaction.response.send_message("❌ | خطأ: لم يتم العثور على الرتبة في السيرفر.", ephemeral=True)
                return

            if role in interaction.user.roles:
                await interaction.response.send_message(f"🎒 | أنت تمتلك هذه الميزة بالفعل!", ephemeral=True)
                return

            try:
                await interaction.user.add_roles(role)
                update_balance(self.author.id, -item["price"])
                await interaction.response.send_message(f"🎉 | مبروك! تم شراء **{item['name']}** بنجاح وخصم **{item['price']} دولار** من رصيدك 💸!", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message("❌ | البوت لا يملك صلاحية إعطاء الرتب.", ephemeral=True)
        return button_callback

    @discord.ui.button(label="⬅️ العودة للقائمة الرئيسية", style=discord.ButtonStyle.danger, row=4)
    async def back_to_main(self, interaction: discord.Interaction, button: discord.ui.Button):
        main_embed = discord.Embed(title="🛒 متجر السيرفر التفاعلي للبوت B✰IL", color=discord.Color.gold(), description="اختر القسم الذي تريد تصفحه من القائمة المنسدلة أدناه:")
        main_embed.set_footer(text=f"رصيدك الحالي: {get_balance(self.author.id)} دولار.")
        await interaction.response.edit_message(embed=main_embed, view=MainShopView(self.author))

class ShopSelect(discord.ui.Select):
    def __init__(self, author):
        self.author = author
        options = [
            discord.SelectOption(label="قسم الرتب مخصصة 👑", description="تصفح واشترِ الرتب الإدارية والمميزة", value="roles"),
            discord.SelectOption(label="قسم ألوان الشات 🎨", description="تصفح واشترِ ألواناً مخصصة لاسمك", value="colors")
        ]
        super().__init__(placeholder="🛒 اختر قسم المتجر من هنا...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user != self.author:
            await interaction.response.send_message("❌ هذا المتجر تصفحه شخص آخر!", ephemeral=True)
            return

        if self.values[0] == "roles":
            embed = discord.Embed(title="👑 قسم الرتب المتاحة للشراء", color=discord.Color.purple())
            for key, details in ROLES_SHOP.items():
                embed.add_field(name=details["name"], value=f"السعر: **{details['price']} دولار** 💵", inline=False)
            embed.set_footer(text=f"رصيدك الحالي: {get_balance(self.author.id)} دولار.")
            await interaction.response.edit_message(embed=embed, view=ItemPurchaseView(self.author, ROLES_SHOP, is_roles=True))

        elif self.values[0] == "colors":
            embed = discord.Embed(title="🎨 قسم ألوان الأسماء المتاحة للشراء", color=discord.Color.blue())
            for key, details in COLORS_SHOP.items():
                embed.add_field(name=details["name"], value=f"السعر: **{details['price']} دولار** 💵", inline=False)
            embed.set_footer(text=f"رصيدك الحالي: {get_balance(self.author.id)} دولار.")
            await interaction.response.edit_message(embed=embed, view=ItemPurchaseView(self.author, COLORS_SHOP, is_roles=False))

class MainShopView(discord.ui.View):
    def __init__(self, author):
        super().__init__(timeout=60.0)
        self.add_item(ShopSelect(author))

# --- 🎮 أوامر الألعاب والبنك الأساسية ---

@bot.command(name="قنبلة")
async def game_bomb(ctx):
    correct_wire = random.choice(["أحمر", "أزرق", "أخضر"])
    view = BombButtons(author=ctx.author, correct_wire=correct_wire)
    msg = await ctx.send("💥 **بدأت لعبة القنبلة!** اختر سلكاً لتقطيعه:", view=view)
    await view.wait()
    if not view.answered:
        await msg.edit(content="⏱️ **انتهى الوقت!** انفجرت القنبلة لأنك تأخرت.", view=None)

@bot.command(name="سؤال")
async def game_quiz(ctx):
    questions = {"ما هي عاصمة السعودية؟": "الرياض", "كم عدد قارات العالم؟": "7", "ما هو أسرع حيوان بري؟": "الفهد"}
    q, a = random.choice(list(questions.items()))
    await ctx.send(f"🧠 **سؤال:** {q}")
    def check(m): return m.channel == ctx.channel and m.content.strip() == a
    try:
        msg = await bot.wait_for('message', check=check, timeout=30.0)
        update_balance(msg.author.id, 30)
        await ctx.send(f"🎉 إجابة صحيحة من {msg.author.mention}! ربحت **30 دولار** 💵.")
    except asyncio.TimeoutError:
        await ctx.send(f"⏱️ انتهى الوقت! الإجابة الصحيحة كانت: {a}")

@bot.command(name="فلوس")
async def check_wallet(ctx):
    balance = get_balance(ctx.author.id)
    await ctx.send(f"💳 | رصيدك الحالي يا {ctx.author.mention} هو: **{balance} دولار** 💵.")

@bot.command(name="متجر")
async def show_shop(ctx):
    embed = discord.Embed(title="🛒 متجر السيرفر التفاعلي للبوت B✰IL", color=discord.Color.gold(), description="اختر القسم الذي تريد تصفحه من القائمة المنسدلة:")
    embed.set_footer(text=f"رصيدك الحالي: {get_balance(ctx.author.id)} دولار.")
    await ctx.send(embed=embed, view=MainShopView(ctx.author))

# --- 🔄 أمر التحويل المالي (متاح للجميع) ---
@bot.command(name="تحويل")
async def transfer_money(ctx, member: discord.Member, amount: int):
    """أمر تحويل الدولارات بين الأعضاء: !تحويل @شخص 100"""
    if member.id == ctx.author.id:
        await ctx.send("❌ | لا يمكنك تحويل الأموال لنفسك!")
        return
    
    if amount <= 0:
        await ctx.send("❌ | يرجى إدخال مبلغ صحيح أكبر من صفر!")
        return

    author_balance = get_balance(ctx.author.id)
    if author_balance < amount:
        await ctx.send(f"⚠️ | رصيدك غير كافٍ! رصيدك الحالي هو **{author_balance} دولار** فقط.")
        return

    # تنفيذ الحوالة
    update_balance(ctx.author.id, -amount)
    update_balance(member.id, amount)
    
    await ctx.send(f"💸 | تم بنجاح تحويل **{amount} دولار** من {ctx.author.mention} إلى {member.mention} ✅!")

# --- ➕ أمر إضافة الأموال (خاص بالإدارة والرتب المحددة) ---
@bot.command(name="اضافة")
async def add_money(ctx, member: discord.Member, amount: int):
    """أمر إدارة لإعطاء فلوس: !اضافة @شخص 500"""
    # التحقق من أن الشخص يملك رتبة الإدارة المحددة فوق
    admin_role = ctx.guild.get_role(ADMIN_ROLE_ID)
    if admin_role not in ctx.author.roles:
        await ctx.send("❌ | ليس لديك صلاحية استخدام هذا الأمر! (خاص بالإدارة المعتمدة)")
        return

    if amount <= 0:
        await ctx.send("❌ | يرجى إدخال مبلغ صحيح لإضافته!")
        return

    update_balance(member.id, amount)
    await ctx.send(f"💰 | قامت الإدارة بإضافة **{amount} دولار** إلى حساب {member.mention} 🌟!\nرصيده الجديد أصبح: {get_balance(member.id)} دولار.")

# --- إقلاع وتجهيز البوت ---
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

bot.run(os.environ.get('DISCORD_TOKEN'))