import discord
from discord.ext import commands, tasks
import random
import json
import os
import asyncio
import aiohttp
from threading import Thread
from flask import Flask

# --- 🌐 خادم ويب صغير لإبقاء البوت مستيقظاً ---
app = Flask('')

@app.route('/')
def home():
    return "B✰IL Bot is Alive and Running 24/7!"

def run_web():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

keep_alive()

# --- إعدادات البوت الأساسية ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- ⚙️ إعدادات مستودع GitHub وبياناتك الحقيقية ---
GITHUB_TOKEN = "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"
REPO_OWNER = "true561290-boop"  # تم استخراجها تلقائياً من حسابك
REPO_NAME = "my_bot"             # اسم المستودع الخاص بك
FILE_PATH = "bank.json"

ADMIN_ROLE_ID = 1515396547528102131  # رتبة اونر لامر الاضافة والمسح

ROLES_SHOP = {
    "role_1": {"name": "رتبة الزنجي المؤسس 👑", "price": 5000, "role_id": 1527739093163708548}
}

COLORS_SHOP = {
    "color_red": {"name": "اللون الأحمر 🔴", "price": 300, "role_id": 1515396547536355469},
    "color_blue": {"name": "اللون الأزرق 🔵", "price": 300, "role_id": 1515396547528102135},
    "color_green": {"name": "اللون الأخضر 🟢", "price": 300, "role_id": 1515396547528102136},
    "color_purple": {"name": "اللون البنفسجي 🟣", "price": 300, "role_id": 1515396547528102134},
    "color_yellow": {"name": "اللون الأصفر 🟡", "price": 300, "role_id": 1515396547528102137},
    "color_grey": {"name": "اللون الرمادي ⚪", "price": 300, "role_id": 1515487581138190376},
    "color_skin": {"name": "لون skin 🎨", "price": 300, "role_id": 1515480359553335441}
}

# --- 🔄 دالات الحفظ السحابي عبر GitHub API ---
def load_data_from_github():
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{FILE_PATH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    import requests
    import base64
    try:
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            content = r.json()
            file_data = base64.b64decode(content['content']).decode('utf-8')
            return json.loads(file_data)
        return {}
    except:
        return {}

def save_data_to_github(data):
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{FILE_PATH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    import requests
    import base64
    
    sha = None
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        sha = r.json()['sha']
        
    js_bytes = json.dumps(data, ensure_ascii=False, indent=4).encode('utf-8')
    encoded = base64.b64encode(js_bytes).decode('utf-8')
    
    payload = {
        "message": "🔄 تحديث تلقائي لرصيد البنك عبر البوت",
        "content": encoded
    }
    if sha:
        payload["sha"] = sha
        
    requests.put(url, headers=headers, json=payload)

bot.user_bank = load_data_from_github()

def get_balance(user_id):
    uid = str(user_id)
    if uid not in bot.user_bank:
        bot.user_bank[uid] = 200
        save_data_to_github(bot.user_bank)
    return bot.user_bank[uid]

def update_balance(user_id, amount):
    uid = str(user_id)
    current = get_balance(user_id)
    bot.user_bank[uid] = current + amount
    save_data_to_github(bot.user_bank)

# --- 🔄 ميزة المناداة الذاتية ---
@tasks.loop(minutes=5)
async def auto_ping():
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get("https://my-bot-r8fk.onrender.com") as response:
                print(f"⏰ [Self-Ping] الحالة: {response.status}")
        except Exception as e:
            print(f"⚠️ [Self-Ping] خطأ: {e}")

# --- 🎮 كلاسات واجهات الألعاب والمتجر تفاعلية ---
class BombButtons(discord.ui.View):
    def __init__(self, author, correct_wire):
        super().__init__(timeout=30.0)
        self.author = author
        self.correct_wire = correct_wire
        self.answered = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.author:
            await interaction.response.send_message("❌ هذه اللعبة ليست لك!", ephemeral=True)
            return False
        return True

    async def process_choice(self, interaction: discord.Interaction, chosen_wire: str):
        self.answered = True
        self.stop()
        if chosen_wire == self.correct_wire:
            update_balance(self.author.id, 50)
            await interaction.response.edit_message(content=f"🎉 **نجوت!** قطعت السلك الصحيح ({chosen_wire}) وربحت **50 دولار**! الرصيد: {get_balance(self.author.id)}.", view=None)
        else:
            update_balance(self.author.id, -20)
            await interaction.response.edit_message(content=f"💥 **طرااااخ!** انفجرت القنبلة! السلك الصحيح كان ({self.correct_wire}). خسرت **20 دولار**.", view=None)

    @discord.ui.button(label="أحمر 🔴", style=discord.ButtonStyle.danger)
    async def red_wire(self, interaction: discord.Interaction, button: discord.ui.Button): await self.process_choice(interaction, "أحمر")
    @discord.ui.button(label="أزرق 🔵", style=discord.ButtonStyle.primary)
    async def blue_wire(self, interaction: discord.Interaction, button: discord.ui.Button): await self.process_choice(interaction, "أزرق")
    @discord.ui.button(label="أخضر 🟢", style=discord.ButtonStyle.success)
    async def green_wire(self, interaction: discord.Interaction, button: discord.ui.Button): await self.process_choice(interaction, "أخضر")

class ItemPurchaseView(discord.ui.View):
    def __init__(self, author, items_dict):
        super().__init__(timeout=60.0)
        self.author = author
        for key, item in items_dict.items():
            btn = discord.ui.Button(label=f"شراء: {item['name'].split()[0]}", style=discord.ButtonStyle.secondary, custom_id=key)
            btn.callback = self.make_callback(item)
            self.add_item(btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user == self.author

    def make_callback(self, item):
        async def button_callback(interaction: discord.Interaction):
            user_balance = get_balance(self.author.id)
            if user_balance < item["price"]:
                await interaction.response.send_message(f"⚠️ رصيدك غير كافٍ! تحتاج {item['price'] - user_balance} دولار إضافية.", ephemeral=True)
                return
            role = interaction.guild.get_role(item["role_id"])
            if not role:
                await interaction.response.send_message("❌ لم يتم العثور على الرتبة بالسيرفر.", ephemeral=True)
                return
            if role in interaction.user.roles:
                await interaction.response.send_message("🎒 تمتلك هذه الميزة بالفعل!", ephemeral=True)
                return
            try:
                await interaction.user.add_roles(role)
                update_balance(self.author.id, -item["price"])
                await interaction.response.send_message(f"🎉 مبروك! تم شراء **{item['name']}** وخصم **{item['price']} دولار** 💸!", ephemeral=True)
            except:
                await interaction.response.send_message("❌ البوت لا يملك صلاحية الرتب.", ephemeral=True)
        return button_callback

    @discord.ui.button(label="⬅️ العودة للقائمة", style=discord.ButtonStyle.danger, row=4)
    async def back_to_main(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=discord.Embed(title="🛒 متجر السيرفر التفاعلي للبوت B✰IL", color=discord.Color.gold()), view=MainShopView(self.author))

class ShopSelect(discord.ui.Select):
    def __init__(self, author):
        self.author = author
        options = [
            discord.SelectOption(label="قسم الرتب الخاصة 👑", value="roles"),
            discord.SelectOption(label="قسم ألوان الشات 🎨", value="colors")
        ]
        super().__init__(placeholder="🛒 اختر قسم المتجر من هنا...", options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user != self.author: return
        if self.values[0] == "roles":
            embed = discord.Embed(title="👑 قسم الرتب المتاحة للشراء", color=discord.Color.purple())
            for key, det in ROLES_SHOP.items(): embed.add_field(name=det["name"], value=f"السعر: **{det['price']} دولار**", inline=False)
            await interaction.response.edit_message(embed=embed, view=ItemPurchaseView(self.author, ROLES_SHOP))
        elif self.values[0] == "colors":
            embed = discord.Embed(title="🎨 قسم ألوان الأسماء المتاحة للشراء", color=discord.Color.blue())
            for key, det in COLORS_SHOP.items(): embed.add_field(name=det["name"], value=f"السعر: **{det['price']} دولار**", inline=False)
            await interaction.response.edit_message(embed=embed, view=ItemPurchaseView(self.author, COLORS_SHOP))

class MainShopView(discord.ui.View):
    def __init__(self, author):
        super().__init__(timeout=60.0)
        self.add_item(ShopSelect(author))

# --- 🎮 الأوامر ---
@bot.command(name="قنبلة")
async def game_bomb(ctx):
    correct_wire = random.choice(["أحمر", "أزرق", "أخضر"])
    view = BombButtons(author=ctx.author, correct_wire=correct_wire)
    msg = await ctx.send("💥 **بدأت لعبة القنبلة!** اختر سلكاً لتقطيعه:", view=view)
    await view.wait()
    if not view.answered: await msg.edit(content="⏱️ انتهى الوقت! انفجرت القنبلة.", view=None)

@bot.command(name="سؤال")
async def game_quiz(ctx):
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    questions_path = os.path.join(BASE_DIR, "questions.json")
    if not os.path.exists(questions_path):
        await ctx.send("❌ | خطأ: لم يتم العثور على ملف `questions.json`!")
        return
    try:
        with open(questions_path, "r", encoding="utf-8") as f: questions_pool = json.load(f)
    except: return

    q, a = random.choice(list(questions_pool.items()))
    embed = discord.Embed(title="🧠 سؤال تحدي ذكاء (سريع)", description=f"**{q}**", color=discord.Color.dark_red())
    embed.set_footer(text="لديك 8 ثوانٍ فقط للإجابة الصحيحة! 🔥")
    await ctx.send(embed=embed)
    
    def check(m): return m.channel == ctx.channel and m.content.strip().lower() == a.strip().lower()
    try:
        msg = await bot.wait_for('message', check=check, timeout=8.0)
        update_balance(msg.author.id, 50)
        await ctx.send(embed=discord.Embed(title="🎉 إجابة صحيحة وسريعة!", description=f"مبروك {msg.author.mention}! ربحت **50 دولار** 💵.", color=discord.Color.green()))
    except asyncio.TimeoutError:
        await ctx.send(embed=discord.Embed(title="⏱️ انتهى الوقت سريعاً!", description=f"الإجابة الصحيحة هي: **{a}** 💡", color=discord.Color.orange()))

@bot.command(name="فلوس")
async def check_wallet(ctx):
    await ctx.send(f"💳 | رصيدك الحالي يا {ctx.author.mention} هو: **{get_balance(ctx.author.id)} دولار** 💵.")

@bot.command(name="متجر")
async def show_shop(ctx):
    embed = discord.Embed(title="🛒 متجر السيرفر التفاعلي للبوت B✰IL", color=discord.Color.gold(), description="اختر القسم:")
    embed.set_footer(text=f"رصيدك الحالي: {get_balance(ctx.author.id)} دولار.")
    await ctx.send(embed=embed, view=MainShopView(ctx.author))

@bot.command(name="تحويل")
async def transfer_money(ctx, member: discord.Member, amount: int):
    if member.id == ctx.author.id or amount <= 0: return
    if get_balance(ctx.author.id) < amount:
        await ctx.send("⚠️ رصيدك غير كافٍ!")
        return
    update_balance(ctx.author.id, -amount)
    update_balance(member.id, amount)
    await ctx.send(f"💸 تم تحويل {amount} دولار بنجاح إلى {member.mention} ✅!")

@bot.command(name="اضافة")
async def add_money(ctx, member: discord.Member, amount: int):
    owner_role = ctx.guild.get_role(ADMIN_ROLE_ID)
    if not owner_role or owner_role not in ctx.author.roles:
        await ctx.send("❌ هذا الأمر خاص بالأونر فقط!")
        return
    update_balance(member.id, amount)
    await ctx.send(f"💰 تم إضافة **{amount} دولار** إلى {member.mention} 🌟!")

@bot.command(name="مسح")
async def clear_messages(ctx, amount: int):
    owner_role = ctx.guild.get_role(ADMIN_ROLE_ID)
    if not owner_role or owner_role not in ctx.author.roles:
        await ctx.send("❌ هذا الأمر خاص بالأونر فقط!")
        return
    if amount > 0:
        deleted = await ctx.channel.purge(limit=amount + 1)
        await ctx.send(f"🧹 تم مسح {len(deleted) - 1} رسالة!", delete_after=2)

@bot.command(name="ايدي")
async def get_id(ctx, target: str = None):
    if target is None:
        await ctx.send(f"🆔 آيديك: `{ctx.author.id}`")
        return
    if target.startswith("<@") and target.endswith(">"):
        try:
            m = await commands.MemberConverter().convert(ctx, target)
            await ctx.send(f"👤 آيدي العضو: `{m.id}`")
        except: pass
    elif target.startswith("<@&") and target.endswith(">"):
        try:
            r = await commands.RoleConverter().convert(ctx, target)
            await ctx.send(f"👑 آيدي الرتبة: `{r.id}`")
        except: pass

@bot.command(name="افتار")
async def show_avatar(ctx, member: discord.Member = None):
    member = member or ctx.author
    e = discord.Embed(title=f"👤 صورة {member.name}", color=discord.Color.blue())
    e.set_image(url=member.display_avatar.url)
    await ctx.send(embed=e)

@bot.command(name="بنر")
async def show_banner(ctx, member: discord.Member = None):
    member = member or ctx.author
    u = await bot.fetch_user(member.id)
    if u.banner:
        e = discord.Embed(title=f"🖼️ بنر {u.name}", color=discord.Color.purple())
        e.set_image(url=u.banner.url)
        await ctx.send(embed=e)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name} with Cloud Backup and Real IDs!")
    auto_ping.start()

bot.run(os.environ.get('DISCORD_TOKEN'))