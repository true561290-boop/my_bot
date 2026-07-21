import discord
from discord.ext import commands, tasks
import random
import json
import os
import asyncio
import aiohttp
from threading import Thread
from flask import Flask
from PIL import Image, ImageDraw, ImageFont
import io

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

ADMIN_ROLE_ID = 1515396547528102131
LEVEL_50_ROLE_ID = 1515396547473309712

# --- 🧠 بنك الأسئلة المكون من 100 سؤال وجواب ---
QUESTIONS_POOL = {
    "ما هو أول مسجد بني في الإسلام؟": "مسجد قباء",
    "ما هو أطول نهر في العالم؟": "نهر النيل",
    "كم عدد الكواكب في المجموعة الشمسية؟": "8",
    "ما هو الطائر الذي يضع أكبر بيضة في العالم؟": "النعامة",
    "عاصمة المملكة العربية السعودية هي؟": "الرياض",
    "ما هو الشيء الذي كلما أخذت منه كبر؟": "الحفرة",
    "ما هو الكائن الحي الذي يملك 3 قلوب؟": "الأخطبوط",
    "ما هي عاصمة فرنسا؟": "باريس",
    "من هو الصحابي الملقب بالفاروق؟": "عمر بن خطاب",
    "ما هو معدن السائل الوحيد؟": "الزئبق",
    "ما هو أكبر محيط في العالم؟": "المحيط الهادئ",
    "كم عدد سُور القرآن الكريم؟": "114",
    "ما هي عاصمة اليابان؟": "طوكيو",
    "ما هو الحيوان الملقب بسفينة الصحراء؟": "الجمل",
    "ما هو أسرع حيوان بري في العالم؟": "الفهد",
    "من هو مخترع المصباح الكهربائي؟": "توماس ايديسون",
    "ما هي عاصمة مصر؟": "القاهرة",
    "كم عدد أضلاع المثلث؟": "3",
    "ما هي أصغر دولة في العالم؟": "الفاتيكان",
    "ما هو الغاز الذي نلتهمه للتنفس؟": "الأكسجين",
    "ما هو اسم أكبر كوكب في المجموعة الشمسية؟": "المشتري",
    "كم عدد القارات في العالم؟": "7",
    "ما هي عاصمة الإمارات العربية المتحدة؟": "أبوظبي",
    "ما هي عاصمة إيطاليا؟": "روما",
    "ما هو أثقل عضو في جسم الإنسان؟": "الجلد",
    "من هو مؤسس شركة أبل؟": "ستيف جوبز",
    "ما هي عاصمة إسبانيا؟": "مدريد",
    "ما هو أسرع طائر في العالم؟": "الصقر",
    "ما هو الغاز الأكبر نسبة في الجو؟": "النيتروجين",
    "ما هي الدولة الأكثر سكاناً في العالم؟": "الصين",
    "كم عدد أسنان الإنسان البالغ؟": "32",
    "ما هي عاصمة ألمانيا؟": "برلين",
    "ما هو أطول حيوان في العالم؟": "الزرافة",
    "ما هو المكون الأساسي للزجاج؟": "الرمل",
    "من هو العالم الذي اكتشف الجاذبية؟": "نيوتن",
    "ما هي عاصمة تركيا؟": "أنقرة",
    "ما هي عاصمة المملكة المتحدة؟": "لندن",
    "ما هو الحيوان الذي يُسمى ملك الغابة؟": "الأسد",
    "كم عدد ألوان قوس قزح؟": "7",
    "ما هي عاصمة روسيا؟": "موسكو",
    "ما هو أقرب كوكب إلى الشمس؟": "عطارد",
    "من الذي بنى الكعبة المشرفة مع إسماعيل؟": "إبراهيم",
    "ما هي عاصمة المغرب؟": "الرباط",
    "ما هو أبرد كوكب في المجموعة الشمسية؟": "أورانوس",
    "ما هي الدولة ذات أطول خط ساحلي؟": "كندا",
    "كم عدد الأحرف في اللغة العربية؟": "28",
    "ما هي أكبر جزر العالم مساحة؟": "جرينلاند",
    "ما هي عاصمة الكويت؟": "الكويت",
    "ما هي عاصمة قطر؟": "الدوحة",
    "ما هو العنصر الكيميائي الممرمز بـ Au؟": "الذهب",
    "ما هو أكبر عضو داخلي في جسم الإنسان؟": "الكبد",
    "ما هي عاصمة الأردن؟": "عمان",
    "ما هو أسرع كائن بحري؟": "سمك سمك الشراع",
    "ما هي عاصمة العراق؟": "بغداد",
    "كم عدد لاعبي فريق كرة القدم في الملعب؟": "11",
    "ما هي السورة التي تُسمى عروس القرآن؟": "الرحمن",
    "من هو مكتشف البنسلين؟": "ألكسندر فلمنج",
    "ما هي عاصمة الجزائر؟": "الجزائر",
    "ما هي أطول سلسلة جبال في العالم؟": "الأنديز",
    "ما هي عاصمة لبنان؟": "بيروت",
    "كم عدد دقات قلب الإنسان الطبيعي تقريباً في الدقيقة؟": "70",
    "ما هو الحيوان الذي لا يموت إلا حرقاً أو بالمرض؟": "النسر",
    "ما هو أكبر بحر مغلق في العالم؟": "بحر قزوين",
    "ما هي عاصمة السودان؟": "الخرطوم",
    "من هو أول رئيس للولايات المتحدة؟": "جورج واشنطن",
    "ما هي عاصمة سلطنة عمان؟": "مسقط",
    "ما هو أصلح خط لتحديد الوقت في العالم؟": "غرينتش",
    "كم عدد طبقات الغلاف الجوي؟": "5",
    "ما هو اسم النهر الذي يمر بدولة بغداد؟": "دجلة",
    "ما هي عاصمة تونس؟": "تونس",
    "ما هي عاصمة كوريا الجنوبية؟": "سول",
    "ما هو الجزء الذي يتحكم في التوازن في الجسم؟": "المخيخ",
    "ما هي الدولة التي تمتلك أكبر عدد من الأهرامات؟": "السودان",
    "ما هي عاصمة سوريا؟": "دمشق",
    "ما هي أكبر صحراء في العالم؟": "القارة القطبيية الجنوبية",
    "كم عدد صمامات القلب؟": "4",
    "ما هي عاصمة اليونان؟": "أثينا",
    "ما هو أقسى عنصر طبيعي في الأرض؟": "الألماس",
    "ما هي عاصمة هولندا؟": "أمستردام",
    "من هو قائد معركة القادسية؟": "سعد بن أبي وقاص",
    "ما هي عاصمة البحرين؟": "المنامة",
    "ما هي السورة التي تعادل ثلث القرآن؟": "الإخلاص",
    "ما هو الحيوان الوحيد الذي لا يستطيع القفز؟": "الفيل",
    "ما هي عاصمة كندا؟": "أوتاوا",
    "ما هي أعمق نقطة في المحيطات؟": "خندق ماريانا",
    "ما هو الغاز المستخدم في إطفاء الحرائق؟": "ثاني أكسيد الكربون",
    "ما هي عاصمة البرازيل؟": "برازيليا",
    "كم عدد عظام جسم الإنسان البالغ؟": "206",
    "ما هي عاصمة الصين؟": "بكين",
    "ما هي الدولة التي تحيط بها إيطاليا بالكامل؟": "سان مارينو",
    "ما هو الطائر الذي يستطيع الطيران إلى الخلف؟": "الطنان",
    "ما هي عاصمة أستراليا؟": "كانبرا",
    "ما هي عاصمة السويد؟": "ستوكهولم",
    "ما هو النهر الذي يُعرف بالبحر الأعظم؟": "الأمازون",
    "ما هي عاصمة الهند؟": "نيودلهي",
    "كم عدد الأيام في السنة الكبيسة؟": "366",
    "ما هي عاصمة فلسطين؟": "القدس",
    "من هو الصحابي الملقب بسيف الله المسلول؟": "خالد بن الوليد",
    "ما هو الكوكب الملقب بالكوكب الأحمر؟": "المريخ",
    "ما هي الدولة العربية الأكبر من حيث المساحة؟": "الجزائر"
}

# --- 🧩 ألغاز السجن والهروب ---
ESCAPE_RIDDLES = [
    {"q": "أنا موجود في الشتاء وغير موجود في الصيف، ومن 4 حروف، ما أنا؟", "a": "مطر"},
    {"q": "يسير بلا رجلين ولا يدخل إلا بالأذنين، ما هو؟", "a": "الصوت"},
    {"q": "ما هو الشيء الذي يتكلم جميع اللغات ولكنه لا ينطق؟", "a": "الصدى"},
    {"q": "شيء يملك أسناناً كثيرة ولكنه لا يعض، ما هو؟", "a": "المشط"},
    {"q": "كلما أخذت منه كبر وكلما أضفت إليه صغر، ما هو؟", "a": "الحفرة"}
]

# --- 🛒 قوائم المتجر ---
ROLES_SHOP = {
    "role_1": {"name": "Level 25", "price": 1000, "role_id": 1515396547473309710, "desc": "تستطيع ارسال صور"},
    "role_2": {"name": "Level 35", "price": 2000, "role_id": 1515396547473309711, "desc": "تستطيع ارسال صور وارسال ستيكر وايموجي"},
    "role_3": {"name": "Level 50", "price": 3500, "role_id": 1515396547473309712, "desc": "كل ما سبق اضافة تستطيع ارسال خط بحجم كبير (#)"}
}

COLORS_SHOP = {
    "color_red": {"name": "اللون الأحمر 🔴", "price": 300, "role_id": 1515396547536355469},
    "color_blue": {"name": "اللون الأزرق 🔵", "price": 300, "role_id": 1515396547528102135}
}

bot.user_bank = {}

# --- 🔄 دالات الحفظ السحابي (GitHub Storage) ---
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

# --- 🖼️ دالة توليد بطاقة الرصيد صورة (Image Generation) ---
def create_wallet_card(user_name, balance):
    width, height = 600, 250
    img = Image.new("RGB", (width, height), color=(15, 23, 42))
    draw = ImageDraw.Draw(img)

    # إطار زينة
    draw.rectangle([15, 15, width - 15, height - 15], outline=(59, 130, 246), width=3)
    draw.rectangle([20, 20, width - 20, height - 20], outline=(147, 51, 234), width=1)

    font_large = ImageFont.load_default()

    draw.text((40, 40), "B✰IL BANK CARD", fill=(234, 179, 8), font=font_large)
    draw.text((40, 80), f"User: {user_name}", fill=(255, 255, 255), font=font_large)
    draw.text((40, 130), f"Balance: ${balance:,} USD", fill=(34, 197, 94), font=font_large)
    draw.text((40, 180), "Status: VIP Member", fill=(148, 163, 184), font=font_large)

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer

# --- 🎨 دالة توليد صورة المتجر (Shop Image) ---
def create_shop_card():
    width, height = 700, 400
    img = Image.new("RGB", (width, height), color=(24, 24, 27))
    draw = ImageDraw.Draw(img)

    draw.rectangle([15, 15, width - 15, height - 15], outline=(234, 179, 8), width=3)
    
    font = ImageFont.load_default()
    draw.text((230, 30), "=== B✰IL SERVER SHOP ===", fill=(234, 179, 8), font=font)
    
    y = 80
    draw.text((40, y), "[ ROLES SHOP ]", fill=(168, 85, 247), font=font)
    y += 30
    for k, item in ROLES_SHOP.items():
        draw.text((60, y), f"• {item['name']} -> Price: ${item['price']} | {item['desc']}", fill=(255, 255, 255), font=font)
        y += 25

    y += 20
    draw.text((40, y), "[ COLORS SHOP ]", fill=(59, 130, 246), font=font)
    y += 30
    for k, item in COLORS_SHOP.items():
        draw.text((60, y), f"• {item['name']} -> Price: ${item['price']}", fill=(255, 255, 255), font=font)
        y += 25

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer

# --- 🛡️ نظام حماية الشات من الحجم الكبيرة ---
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.content.strip().startswith("# "):
        has_role = any(role.id == LEVEL_50_ROLE_ID for role in message.author.roles)
        if not has_role:
            try:
                await message.delete()
                await message.channel.send(
                    f"⚠️ | عذراً {message.author.mention}، لا يمكنك إرسال خط بحجم كبير! هذه الميزة خاصة بأصحاب رتبة **Level 50** فقط. 👑", 
                    delete_after=5
                )
            except:
                pass
            return

    await bot.process_commands(message)

# --- 💳 أمر !فلوس لإرسال الصورة ---
@bot.command(name="فلوس")
async def check_wallet(ctx):
    balance = get_balance(ctx.author.id)
    img_buffer = create_wallet_card(ctx.author.name, balance)
    file = discord.File(fp=img_buffer, filename="wallet.png")
    await ctx.send(content=f"💳 | بطاقة البنك الخاصة بك يا {ctx.author.mention}:", file=file)

# --- 🛒 أمر !متجر لإرسال الصورة والقائمة ---
@bot.command(name="متجر")
async def show_shop(ctx):
    img_buffer = create_shop_card()
    file = discord.File(fp=img_buffer, filename="shop.png")
    await ctx.send(content="🛒 **إليك قائمة المتجر الحالية:**", file=file, view=MainShopView(ctx.author))

# --- 🛒 القوائم التفاعلية للمتجر ---
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
            if self.is_color_shop:
                for col_key, col_val in COLORS_SHOP.items():
                    old_role = interaction.guild.get_role(col_val["role_id"])
                    if old_role and old_role in interaction.user.roles:
                        await interaction.user.remove_roles(old_role)
            
            await interaction.user.add_roles(role)
            await async_update_balance(self.author.id, -item["price"])
            await interaction.response.send_message(f"🎉 مبروك! تم شراء **{item['name']}** وخصم **{item['price']} دولار** 💸!", ephemeral=True)
        except:
            await interaction.response.send_message("❌ البوت لا يملك صلاحية الرتب.", ephemeral=True)

class ItemPurchaseView(discord.ui.View):
    def __init__(self, author, items_dict, placeholder_text, is_color_shop=False):
        super().__init__(timeout=60.0)
        self.author = author
        self.add_item(ItemPurchaseSelect(author, items_dict, placeholder_text, is_color_shop))

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
            await interaction.response.send_message("👑 اختر الرتبة المراد شراؤها:", view=ItemPurchaseView(self.author, ROLES_SHOP, "👑 اختر رتبة...", is_color_shop=False), ephemeral=True)
        elif self.values[0] == "colors":
            await interaction.response.send_message("🎨 اختر اللون المراد شاؤه:", view=ItemPurchaseView(self.author, COLORS_SHOP, "🎨 اختر لوناً...", is_color_shop=True), ephemeral=True)

class MainShopView(discord.ui.View):
    def __init__(self, author):
        super().__init__(timeout=60.0)
        self.add_item(ShopSelect(author))

# --- 🎮 أمر !سؤال مع دعم متعدد الجولات ---
@bot.command(name="سؤال")
async def ask_question(ctx, rounds: int = 1):
    if rounds < 1 or rounds > 10:
        await ctx.send("❌ يرجى اختيار عدد جولات بين 1 و 10 فقط!")
        return

    used_questions = []
    
    for round_num in range(1, rounds + 1):
        available = [q for q in QUESTIONS_POOL.keys() if q not in used_questions]
        if not available:
            available = list(QUESTIONS_POOL.keys())

        question = random.choice(available)
        answer = QUESTIONS_POOL[question]
        used_questions.append(question)

        embed = discord.Embed(
            title=f"❓ سؤال الجولة {round_num} من {rounds}",
            description=f"**{question}**\n\n⏰ لديك **15 ثانية** للإجابة الصحيحة!",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)

        def check(m):
            return m.channel == ctx.channel and not m.author.bot and m.content.strip().lower() == answer.lower()

        try:
            msg = await bot.wait_for('message', timeout=15.0, check=check)
            await async_update_balance(msg.author.id, 100)
            
            win_embed = discord.Embed(
                title="🎉 إجابة صحيحة!",
                description=f"كفو يا {msg.author.mention}! الإجابة هي **{answer}**.\nفزت بـ **100 دولار** 💸!",
                color=discord.Color.green()
            )
            await ctx.send(embed=win_embed)
        except asyncio.TimeoutError:
            fail_embed = discord.Embed(
                title="⏰ انتهى الوقت!",
                description=f"للأسف محد عرف الإجابة الصحيحة!\nالإجابة هي: **{answer}**",
                color=discord.Color.red()
            )
            await ctx.send(embed=fail_embed)

        if round_num < rounds:
            await asyncio.sleep(2)

# --- 🚨 لعبة السجن والهروب ---
@bot.command(name="سجن")
async def jail_user(ctx, member: discord.Member = None):
    if not member:
        await ctx.send("⚠️ يرجى تحديد العضو! مثال: `!سجن @اسم_العضو`")
        return

    riddle = random.choice(ESCAPE_RIDDLES)
    
    embed = discord.Embed(
        title="🚔 لقد تم إدخالك السجن!",
        description=f"يا {member.mention}، تم سجنك! للهروب، يجب أن تحل هذا اللغز خلال **30 ثانية**:\n\n🧩 **{riddle['q']}**",
        color=discord.Color.dark_red()
    )
    await ctx.send(embed=embed)

    def check(m):
        return m.author == member and m.channel == ctx.channel and riddle['a'] in m.content.strip().lower()

    try:
        await bot.wait_for('message', timeout=30.0, check=check)
        await ctx.send(f"🔓 **مبروك!** {member.mention} أجاب بشكل صحيح ونجح في الهروب من السجن!")
    except asyncio.TimeoutError:
        await ctx.send(f"🔒 **انتهى الوقت!** {member.mention} فشل في الهروب ويبقى في السجن!")

# --- 💸 أمر تحويل الأموال ---
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
        await ctx.send(f"⚠️ رصيدك غير كافٍ! رصيدك الحالي: **{sender_bal} دولار**")
        return

    await async_update_balance(ctx.author.id, -amount)
    await async_update_balance(member.id, amount)

    await ctx.send(f"✅ تم تحويل **{amount} دولار** بنجاح إلى {member.mention} 💸!")

# --- 👑 أمر إعطاء الأموال للأدمن ---
@bot.command(name="اعطاء")
async def give_money(ctx, member: discord.Member = None, amount: int = None):
    has_admin = any(role.id == ADMIN_ROLE_ID for role in ctx.author.roles)
    if not has_admin and not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ ليس لديك صلاحية لاستخدام هذا الأمر!")
        return

    if not member or not amount:
        await ctx.send("⚠️ الاستخدام الصحيح: `!اعطاء @العضو المبلغ`")
        return

    await async_update_balance(member.id, amount)
    await ctx.send(f"👑 تم إضافة **{amount} دولار** إلى حساب {member.mention} بنجاح!")

# --- 🚀 تشغيل البوت وجلب البيانات ---
@bot.event
async def on_ready():
    print("🤖 B✰IL bot is checking database...")
    await load_data_from_github()
    print(f"Logged in as {bot.user.name}!")

bot.run(os.environ.get('DISCORD_TOKEN'))