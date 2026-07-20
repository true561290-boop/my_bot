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
REPO_OWNER = "true561290-boop"
REPO_NAME = "my_bot"
FILE_PATH = "bank.json"

ADMIN_ROLE_ID = 1515396547528102131  # رتبة اونر لامر الاضافة والمسح

# --- 🧠 بنك الأسئلة المدمج داخل الكود مباشرة ---
QUESTIONS_POOL = {
    "ما هو أول مسجد بني في الإسلام؟": "مسجد قباء",
    "ما هو أطول نهر في العالم؟": "نهر النيل",
    "كم عدد الكواكب في المجموعة الشمسية؟": "8",
    "ما هو الطائر الذي يضع أكبر بيضة في العالم؟": "النعامة",
    "عاصمة المملكة العربية السعودية هي؟": "الرياض",
    "ما هو الشيء الذي كلما أخذت منه كبر؟": "الحفرة",
    "ما هو الكائن الحي الذي يملك 3 قلوب؟": "الأخطبوط"
}

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

bot.user_bank = {}

# --- 🔄 دالات الحفظ السحابي عبر GitHub API ---
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
                    bot.user_bank = json.loads(file_data)
                    print("✅ [GitHub Cloud] تم تحميل بيانات البنك بنجاح!")
                else:
                    bot.user_bank = {}
        except Exception as e:
            print(f"⚠️ [GitHub Cloud] فشل تحميل البيانات: {e}")
            bot.user_bank = {}

async def async_update_balance(user_id, amount):
    uid = str(user_id)
    import base64
    
    if uid not in bot.user_bank:
        bot.user_bank[uid] = 200
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
                "message": "🔄 تحديث تلقائي لرصيد البنك عبر البوت",
                "content": encoded
            }
            if sha:
                payload["sha"] = sha
                
            async with session.put(url, headers=headers, json=payload) as r_put:
                if r_put.status in [200, 201]:
                    print("✅ [GitHub Cloud] تم حفظ الرصيد الجديد سحابياً!")
        except Exception as e:
            print(f"⚠️ [GitHub Cloud] فشل حفظ الرصيد سحابياً: {e}")

def get_balance(user_id):
    uid = str(user_id)
    if uid not in bot.user_bank:
        bot.user_bank[uid] = 200
    return bot.user_bank[uid]

# --- 🔄 ميزة المناداة الذاتية ---
@tasks.loop(minutes=5)
async def auto_ping():
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get("https://my-bot-r8fk.onrender.com") as response:
                print(f"⏰ [Self-Ping] الحالة: {response.status}")
        except Exception as e:
            print(f"⚠️ [Self-Ping] خطأ: {e}")

# --- 🎮 واجهات الألعاب والمتجر التفاعلية الجديدة ---
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
            await async_update_balance(self.author.id, 50)
            await interaction.response.edit_message(content=f"🎉 **نجوت!** قطعت السلك الصحيح ({chosen_wire}) وربحت **50 دولار**! رصيدك: {get_balance(self.author.id)}.", view=None)
        else:
            await async_update_balance(self.author.id, -20)
            await interaction.response.edit_message(content=f"💥 **طرااااخ!** انفجرت القنبلة! السلك الصحيح كان ({self.correct_wire}). خسرت **20 دولار**.", view=None)

    @discord.ui.button(label="أحمر 🔴", style=discord.ButtonStyle.danger)
    async def red_wire(self, interaction: discord.Interaction, button: discord.ui.Button): await self.process_choice(interaction, "أحمر")
    @discord.ui.button(label="أزرق 🔵", style=discord.ButtonStyle.primary)
    async def blue_wire(self, interaction: discord.Interaction, button: discord.ui.Button): await self.process_choice(interaction, "أزرق")
    @discord.ui.button(label="أخضر 🟢", style=discord.ButtonStyle.success)
    async def green_wire(self, interaction: discord.Interaction, button: discord.ui.Button): await self.process_choice(interaction, "أخضر")

# القائمة المنسدلة المخصصة لشراء الغرض المختار
class ItemPurchaseSelect(discord.ui.Select):
    def __init__(self, author, items_dict, placeholder_text, is_color_shop=False):
        self.author = author
        self.items_dict = items_dict
        self.is_color_shop = is_color_shop
        options = []
        for key, item in items_dict.items():
            options.append(discord.SelectOption(label=item["name"], description=f"السعر: {item['price']} دولار", value=key))
        super().__init__(placeholder=placeholder_text, options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user != self.author: return
        chosen_key = self.values[0]
        item = self.items_dict[chosen_key]
        
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
            # 🎨 إذا كان المتجر هو متجر ألوان، نقوم بحذف أي لون قديم يمتلكه العضو من ألوان المتجر
            if self.is_color_shop:
                for col_key, col_val in COLORS_SHOP.items():
                    old_role = interaction.guild.get_role(col_val["role_id"])
                    if old_role and old_role in interaction.user.roles:
                        await interaction.user.remove_roles(old_role)
            
            # إعطاء الرتبة الجديدة وخصم الفلوس
            await interaction.user.add_roles(role)
            await async_update_balance(self.author.id, -item["price"])
            await interaction.response.send_message(f"🎉 مبروك! تم شراء **{item['name']}** وخصم **{item['price']} دولار** 💸!", ephemeral=True)
        except:
            await interaction.response.send_message("❌ البوت لا يملك صلاحية الرتب أو ترتيبه أقل من الرتبة المشتراة.", ephemeral=True)

class ItemPurchaseView(discord.ui.View):
    def __init__(self, author, items_dict, placeholder_text, is_color_shop=False):
        super().__init__(timeout=60.0)
        self.author = author
        self.add_item(ItemPurchaseSelect(author, items_dict, placeholder_text, is_color_shop))

    @discord.ui.button(label="⬅️ العودة للقائمة الرئيسية", style=discord.ButtonStyle.danger, row=4)
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
            embed = discord.Embed(title="👑 قسم الرتب المتاحة للشراء", description="اختر الرتبة التي ترغب بشرائها من القائمة المنسدلة بالأسفل:", color=discord.Color.purple())
            for key, det in ROLES_SHOP.items(): embed.add_field(name=det["name"], value=f"السعر: **{det['price']} دولار**", inline=False)
            await interaction.response.edit_message(embed=embed, view=ItemPurchaseView(self.author, ROLES_SHOP, "👑 اختر رتبة لشراؤها...", is_color_shop=False))
        elif self.values[0] == "colors":
            embed = discord.Embed(title="🎨 قسم ألوان الأسماء المتاحة للشراء", description="اختر اللون الذي ترغب بشرائه من القائمة المنسدلة بالأسفل:\n*ملاحظة: شراء لون جديد يزيل اللون القديم تلقائياً!*", color=discord.Color.blue())
            for key, det in COLORS_SHOP.items(): embed.add_field(name=det["name"], value=f"السعر: **{det['price']} دولار**", inline=False)
            await interaction.response.edit_message(embed=embed, view=ItemPurchaseView(self.author, COLORS_SHOP, "🎨 اختر لوناً لشراؤه...", is_color_shop=True))

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
    q, a = random.choice(list(QUESTIONS_POOL.items()))
    embed = discord.Embed(title="🧠 سؤال تحدي ذكاء (سريع)", description=f"**{q}**", color=discord.Color.dark_red())
    embed.set_footer(text="لديك 8 ثوانٍ فقط للإجابة الصحيحة! 🔥")
    await ctx.send(embed=embed)
    
    def check(m): return m.channel == ctx.channel and m.content.strip().lower() == a.strip().lower()
    try:
        msg = await bot.wait_for('message', check=check, timeout=8.0)
        await async_update_balance(msg.author.id, 50)
        await ctx.send(embed=discord.Embed(title="🎉 إجابة صحيحة وسريعة!", description=f"مبروك {msg.author.mention}! ربحت **50 دولار** 💵.", color=discord.Color.green()))
    except asyncio.TimeoutError:
        await ctx.send(embed=discord.Embed(title="⏱️ انتهى الوقت سريعاً!", description=f"العوض في الجايات! الإجابة الصحيحة هي: **{a}** 💡", color=discord.Color.orange()))

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
    await async_update_balance(ctx.author.id, -amount)
    await async_update_balance(member.id, amount)
    await ctx.send(f"💸 تم تحويل {amount} دولار بنجاح إلى {member.mention} ✅!")

@bot.command(name="اضافة")
async def add_money(ctx, member: discord.Member, amount: int):
    owner_role = ctx.guild.get_role(ADMIN_ROLE_ID)
    if not owner_role or owner_role not in ctx.author.roles:
        await ctx.send("❌ هذا الأمر خاص بالأونر فقط!")
        return
    await async_update_balance(member.id, amount)
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
    print("🤖 B✰IL bot is checking database...")
    await load_data_from_github()
    print(f"Logged in as {bot.user.name} with Clean Colors Policy!")
    try:
        auto_ping.start()
    except: pass

bot.run(os.environ.get('DISCORD_TOKEN'))