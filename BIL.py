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

# --- 🧠 بنك الأسئلة المدمج المكون من 100 سؤال صعب جداً ---
QUESTIONS_POOL = {
    "ما هو أول مسجد بني في الإسلام؟": "مسجد قباء",
    "ما هو أطول نهر في العالم؟": "نهر النيل",
    "كم عدد الكواكب في المجموعة الشمسية؟": "8",
    "ما هو الطائر الذي يضع أكبر بيضة في العالم؟": "النعامة",
    "عاصمة المملكة العربية السعودية هي؟": "الرياض",
    "ما هو الشيء الذي كلما أخذت منه كبر؟": "الحفرة",
    "ما هو الكائن الحي الذي يملك 3 قلوب？": "الأخطبوط",
    "ما هي عاصمة فرنسا؟": "باريس",
    "من هو الصحابي الملقب بالفاروق؟": "عمر بن الخطاب",
    "ما هو معدن السائل الوحيد؟": "الزئبق",
    "كم عدد سجدات التلاوة في القرآن الكريم؟": "15",
    "ما هو أسرع كائن حي على الأرض؟": "الفهد",
    "في أي مدينة توجد ساعة بيغ بين الشهيرة؟": "لندن",
    "ما هو أكبر المحيطات في العالم؟": "المحيط الهادئ",
    "ما هو الشيء الذي يمشي بلا أرجل ويبكي بلا أعين؟": "السحاب",
    "من هو كليم الله من الأنبياء؟": "موسى",
    "كم عدد قلوب حيوان الحبار؟": "3",
    "ما هي عاصمة اليابان؟": "طوكيو",
    "ما هو الكوكب الملقب بالكوكب الأحمر؟": "المريخ",
    "ما هو الغاز المشهور بغاز الضحك؟": "أكسيد النيتروز",
    "كم عدد عظام الجسم البشري للبالغين؟": "206",
    "ما هو الطائر الملقب بالهدهد؟": "الهدهد",
    "ما هي دولة التي تقع فيها أهرامات الجيزة؟": "مصر",
    "ما هو الشيء الذي يتحدث جميع اللغات؟": "صدى الصوت",
    "ما هي أصغر دولة في العالم؟": "الفاتيكان",
    "ما هو أقرب كوكب إلى الشمس؟": "عطارد",
    "من هو مكتشف الجاذبية الأرضية؟": "نيوتن",
    "ما هو الفيتامين الذي نحصل عليه من الشمس؟": "فيتامين د",
    "ما هو الحيوان الذي لا يشرب الماء طوال حياته؟": "الجرذ الكنغري",
    "ما هي عاصمة مصر؟": "القاهرة",
    "كم عدد ألوان قوس قزح؟": "7",
    "ما هو أكبر حيوان على وجه الأرض؟": "الحوت الأزرق",
    "من هو النبي الذي ابتلعه الحوت؟": "يونس",
    "ما هو الشيء الذي تملكه ويستخدمه الآخرون أكثر منك؟": "اسمك",
    "كم عدد لاعبي فريق كرة القدم في الملعب؟": "11",
    "ما هو العضو المسؤول عن ضخ الدم في الجسم؟": "القلب",
    "ما هي عاصمة إيطاليا؟": "روما",
    "ما هو أصغر كواكب المجموعة الشمسية حجماً؟": "عطارد",
    "ما هو الشيء الذي يوجد وسط باريس؟": "حرف الراء",
    "من هو أول من صعد إلى الفضاء؟": "يوري غاغارين",
    "ما هو أثقل حيوان بري؟": "الفيل الأفريقي",
    "كم عدد أسنان الشخص البالغ؟": "32",
    "ما هي عاصمة إسبانيا؟": "مدريد",
    "ما هو الغاز الأساسي الذي تنفسه الكائنات الحية؟": "الأكسجين",
    "ما هو الشيء الذي له أسنان ولا يعض؟": "المشط",
    "من هو مؤسس الدولة الأموية؟": "معاوية بن أبي سفيان",
    "ما هو أعلى جبل في العالم؟": "إفرست",
    "كم عدد شهور السنة الهجرية؟": "12",
    "ما هي عاصمة دولة الإمارات؟": "أبوظبي",
    "ما هو الكائن الذي يملك أكبر عدد من الأرجل؟": "أم أربعة وأربعين",
    "ما هو الشيء الذي يخترق الزجاج ولا يكسره؟": "الضوء",
    "من هو النبي الذي صنع السفينة؟": "نوح",
    "ما هي أكبر قارة في العالم من حيث المساحة؟": "آسيا",
    "كم عدد ولايات الولايات المتحدة الأمريكية؟": "50",
    "ما هي عاصمة العراق؟": "بغداد",
    "ما هو أصلب مادة طبيعية على الأرض؟": "الألماس",
    "ما هو الشيء الذي كلما زاد نقص؟": "العمر",
    "من هو الشاعر المقب بأمير الشعراء؟": "أحمد شوقي",
    "ما هو البحر الذي لا يغرق فيه أحد لشدة ملوحته؟": "البحر الميت",
    "كم عدد أضلاع المثلث؟": "3",
    "ما هي عاصمة المغرب؟": "الرباط",
    "ما هو أسرع الأسماك في المحيط؟": "سمكة الشراع",
    "ما هو الشيء الذي يكتب ولا يقرأ؟": "القلم",
    "من هو أول رئيس للولايات المتحدة؟": "جورج واشنطن",
    "ما هي الدولة التي تشتهر بوجود حيوان الكنغر؟": "أستـراليا",
    "كم عدد الكلي في جسم الإنسان الطبيعي؟": "2",
    "ما هي عاصمة الأردن？": "عمان",
    "ما هو العنصر الكيميائي الرمز له بـ H؟": "الهيدروجين",
    "ما هو الشيء الذي له رجل واحدة وثلاث عيون؟": "إشارة المرور",
    "من هي أم البشر؟": "حواء",
    "ما هي أطول سورة في القرآن الكريم؟": "البقرة",
    "كم يساوي ربع المائة؟": "25",
    "ما هي عاصمة تركيا؟": "أنقرة",
    "ما هو الحيوان الذكي الملقب بصديق الإنسان؟": "الكلب",
    "ما هو الشيء الذي يمكنه الجري بدون أرجل؟": "الماء",
    "من هو القائد المسلم الذي فتح الأندلس؟": "طارق بن زياد",
    "ما هي أكبر دولة مساحة في العالم؟": "روسيا",
    "كم عدد الكروموسومات في الخلية البشرية؟": "46",
    "ما هي عاصمة الكويت؟": "الكويت",
    "ما هو المعدن المستخدم في صناعة المسامير بكثرة؟": "الحديد",
    "ما هو الشيء الذي يحترق ليدير الضوء للآخرين؟": "الشمعة",
    "من هو النبي الملقب بذو النون؟": "يونس",
    "ما هو النهر الذي يمر عبر لندن؟": "التايمز",
    "كم عدد أصابع اليدين والقدمين معاً للإنسان؟": "20",
    "ما هي عاصمة قطر؟": "الدوحة",
    "ما هو الغاز الذي تمتصه النباتات لتصنع الغذاء؟": "ثاني أكسيد الكربون",
    "ما هو الشيء الذي إذا غليته جمد؟": "البيض",
    "من هو مخترع الهاتف؟": "ألكسندر غراهام بيل",
    "ما هي الدولة التي يمر بها خط الاستواء وتسمى باسمه؟": "الإكوادور",
    "كم عدد فقرات عنق الزرافة؟": "7",
    "ما هي عاصمة تونس؟": "تونس",
    "ما هو الطائر الذي لا يطير ويسكن في الجليد؟": "البطريق",
    "ما هو الشيء الذي يملك قشرة ولا يملك عظاماً؟": "المنجا",
    "من هو أول خليفة للمسلمين بعد وفاة النبي؟": "أبو بكر الصديق",
    "ما هو الحيوان الذي يسمى سفينة الصحراء؟": "الجمل",
    "كم عدد السعرات الحرارية في الماء؟": "0",
    "ما هي عاصمة لبنان؟": "بيروت",
    "ما هو الكوكب الذي يحتوي على حلقات ضخمة حوله؟": "زحل",
    "ما هو الشيء الذي يدور حول الغرفة دون أن يتحرك؟": "الحائط",
    "من هو العالم العربي مؤسس علم الجبر؟": "الخوارزمي",
    "ما هي أصغر قارة في العالم؟": "أستراليا",
    "كم عدد الغرف في قلب الإنسان؟": "4",
    "ما هي عاصمة سوريا؟": "دمشق",
    "ما هو الحيوان الذي يغير لونه ليتخفى؟": "الحرباء",
    "ما هو الشيء الذي تراه في الليل 3 مرات وفي النهار مرة واحدة؟": "حرف الراء"
}

# --- 🧠 بنك ألغاز لعبة الهروب ---
ESCAPE_RIDDLES = [
    {"q": "أنا موجود في الشتاء وغير موجود في الصيف، ومن 4 حروف، ما أنا؟", "a": "مطر"},
    {"q": "يسير بلا رجلين ولا يدخل إلا بالأذنين، ما هو؟", "a": "الصوت"},
    {"q": "كلما كثرت قلّت قيمتي، وكلما ندرت زادت، ما أنا؟", "a": "الأسرار"},
    {"q": "شيء تملكه ويستخدمه الناس أكثر منك بدون إذنك؟", "a": "اسمك"},
    {"q": "له عين واحدة لكنه لا يرى بها شيئاً؟", "a": "الإبرة"}
]

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

# --- 🎛️ واجهات وتفاعلات الألعاب والسرقة ---

class HeistJoinView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=20.0)  # خفضنا مدة الانتظار للتجربة السريعة إلى 20 ثانية
        self.participants = []

    @discord.ui.button(label="🕶️ انضمام للعصابة", style=discord.ButtonStyle.grey)
    async def join_heist(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user in self.participants:
            await interaction.response.send_message("🎒 أنت بالفعل داخل العصابة ومستعد لتنفيذ العملية!", ephemeral=True)
            return
        self.participants.append(interaction.user)
        await interaction.response.send_message(f"🔫 تم انضمامك بنجاح للعملية يا {interaction.user.name}!", ephemeral=True)

class HeistBombView(discord.ui.View):
    def __init__(self, target_player, correct_wire):
        super().__init__(timeout=15.0)
        self.target_player = target_player
        self.correct_wire = correct_wire
        self.success = False
        self.answered = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.target_player:
            await interaction.response.send_message("❌ لست أنت المفجر المسؤول عن فتح الخزنة!", ephemeral=True)
            return False
        return True

    async def check_wire(self, interaction: discord.Interaction, chosen: str):
        self.answered = True
        self.stop()
        if chosen == self.correct_wire:
            self.success = True
            await interaction.response.edit_message(content=f"⚡ **كفو!** تم قطع السلك الصحيح ({chosen}) وانفتحت بوابة الخزنة الحديدية بنجاح!", view=None)
        else:
            await interaction.response.edit_message(content=f"💥 **كارثة!** قمت بقطع السلك الخطأ ودق جرس إنذار البنك المركزي!", view=None)

    @discord.ui.button(label="الأصفر 🟡", style=discord.ButtonStyle.secondary)
    async def yellow(self, interaction: discord.Interaction, button: discord.ui.Button): await self.check_wire(interaction, "الأصفر")
    @discord.ui.button(label="الأزرق 🔵", style=discord.ButtonStyle.primary)
    async def blue(self, interaction: discord.Interaction, button: discord.ui.Button): await self.check_wire(interaction, "الأزرق")

class HeistDriverView(discord.ui.View):
    def __init__(self, target_player, correct_way):
        super().__init__(timeout=15.0)
        self.target_player = target_player
        self.correct_way = correct_way
        self.success = False
        self.answered = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.target_player:
            await interaction.response.send_message("❌ لست أنت السائق المسؤول عن الهروب!", ephemeral=True)
            return False
        return True

    async def check_way(self, interaction: discord.Interaction, chosen: str):
        self.answered = True
        self.stop()
        if chosen == self.correct_way:
            self.success = True
            await interaction.response.edit_message(content=f"🚓 **عبقري!** اخترت {chosen} وتجاوزت كمين الشرطة بنجاح صاعق!", view=None)
        else:
            await interaction.response.edit_message(content=f"🚔 **حاصرتكم المدرعات!** دخلت في {chosen} وهو طريق مسدود بالكامل!", view=None)

    @discord.ui.button(label="النفق السفلي 🚇", style=discord.ButtonStyle.danger)
    async def tunnel(self, interaction: discord.Interaction, button: discord.ui.Button): await self.check_way(interaction, "النفق السفلي")
    @discord.ui.button(label="الجسر السريع 🌉", style=discord.ButtonStyle.success)
    async def bridge(self, interaction: discord.Interaction, button: discord.ui.Button): await self.check_way(interaction, "الجسر السريع")


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

class EscapeFinalView(discord.ui.View):
    def __init__(self, author, correct_device):
        super().__init__(timeout=15.0)
        self.author = author
        self.correct_device = correct_device
        self.responded = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.author:
            await interaction.response.send_message("❌ هذه المغامرة ليست لك!", ephemeral=True)
            return False
        return True

    async def handle_choice(self, interaction: discord.Interaction, choice: int):
        self.responded = True
        self.stop()
        if choice == self.correct_device:
            prize = random.randint(200, 500)
            await async_update_balance(self.author.id, prize)
            embed_win = discord.Embed(
                title="🎉 حرية أسطورية ونصر ساحق! 🎉",
                description=f"كفوووو يا أسطورة! انفتحت البوابة الكبرى وخرجت إلى النور والشمس الساطعة! ☀️\n"
                            f"وجدت صندوق مكافأة عند المخرج يحتوي على **{prize} دولار** كاش! 💰\n"
                            f"رصيدك الحالي أصبح: **{get_balance(self.author.id)} دولار**.",
                color=discord.Color.green()
            )
            await interaction.response.edit_message(embed=embed_win, view=None)
        else:
            await async_update_balance(self.author.id, -100)
            await interaction.response.edit_message(content=f"💀 {self.author.mention} **نهاية مأساوية!** ضغطت على الجهاز الخطأ فانفجرت القاعة بالكامل! خسرت **100 دولار**.", embed=None, view=None)

class EscapeRoomOneView(discord.ui.View):
    def __init__(self, author, ctx):
        super().__init__(timeout=15.0)
        self.author = author
        self.ctx = ctx
        self.correct_door = random.randint(1, 3)
        self.responded = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.author:
            await interaction.response.send_message("❌ هذه المغامرة ليست لك!", ephemeral=True)
            return False
        return True

    async def handle_choice(self, interaction: discord.Interaction, choice: int):
        self.responded = True
        self.stop()
        
        if choice != self.correct_door:
            await async_update_balance(self.author.id, -50)
            await interaction.response.edit_message(content=f"💥 {self.author.mention} **فخ قاتل!** فتحت الباب وسقطت في حفرة مليئة بالأشواك السامة! خسرت **50 دولار** تكلفة الإنعاش.", embed=None, view=None)
            return

        riddle = random.choice(ESCAPE_RIDDLES)
        embed_2 = discord.Embed(
            title="🚪 الغرفة المظلمة - المرحلة [2 من 3]",
            description=f"كفو! دخلت من الباب الصحيح ووجدت ممرًا يقودك إلى **غرفة الألغاز السحرية**! ✨\n"
                        "لكي يفتح الجدار السري وتمر للمرحلة الأخيرة، يجب أن تحل هذا اللغز:\n\n"
                        f"📝 **اللغز:** `{riddle['q']}`\n\n"
                        "⏱️ **لديك 20 ثانية للإجابة كتابةً في الشات مباشرة!** (بدون أوامر)",
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed_2, view=None)

        def check_riddle(m):
            return m.author == self.author and m.channel == self.ctx.channel and riddle["a"] in m.content.strip().lower()

        try:
            await bot.wait_for('message', check=check_riddle, timeout=20.0)
            correct_final = random.randint(1, 3)
            view_final = EscapeFinalView(self.author, correct_final)
            
            embed_3 = discord.Embed(
                title="🔥 الغرفة المظلمة - المرحلة الأخيرة [3 من 3]",
                description=f"عبقري يا {self.author.mention}! انفتح الجدار ووصلت إلى قاعة الخروج الكبرى! 🏛️\n"
                            "لكن انتظر.. المخرج مغلق بـ 3 أجهزة فك تشفير رقمية بالأسفل:\n\n"
                            "أحدهم سيفتح بوابة الحرية، والباقي سيفجر المكان! 💥\n"
                            "⏱️ **لديك 15 ثانية أخيرة للاختيار بالضغط على الأزرار!**",
                color=discord.Color.gold()
            )
            final_msg = await self.ctx.send(embed=embed_3, view=view_final)
            await view_final.wait()
            if not view_final.responded:
                await final_msg.edit(content=f"💀 {self.author.mention}، تجمدت في مكانك من الخوف ولم تضغط على أي جهاز! انهار المكان بالكامل فوق رأسك.. **خسرت!**", embed=None, view=None)

        except asyncio.TimeoutError:
            await self.ctx.send(f"⏱️ {self.author.mention}، انتهى الوقت ولم تحل اللغز! انهار السقف فوق رأسك وسحق محاولتك..")

    @discord.ui.button(label="🚪 الباب الحديدي [1]", style=discord.ButtonStyle.danger)
    async def door_1(self, interaction: discord.Interaction, button: discord.ui.Button): await self.handle_choice(interaction, 1)
    @discord.ui.button(label="🚪 الباب الخشبي [2]", style=discord.ButtonStyle.secondary)
    async def door_2(self, interaction: discord.Interaction, button: discord.ui.Button): await self.handle_choice(interaction, 2)
    @discord.ui.button(label="🚪 الباب الزجاجي [3]", style=discord.ButtonStyle.primary)
    async def door_3(self, interaction: discord.Interaction, button: discord.ui.Button): await self.handle_choice(interaction, 3)

# --- 🛒 قائمة المتجر التفاعلية ---
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

# --- 🎮 الأوامر الأساسية والألعاب ---

# 🌟 لعبة السطو الكبرى الجماعية المحدثة والمضمونة التشغيل
@bot.command(name="سرقة")
async def start_heist(ctx):
    view_join = HeistJoinView()
    view_join.participants.append(ctx.author)  # إضافة الشخص الذي أطلق الأمر تلقائياً
    
    embed_lobby = discord.Embed(
        title="🚨 عملية سطو مسلح كبرى على البنك المركزي! 🚨",
        description=f"أعلن **{ctx.author.name}** عن بدء خطة لسرقة خزنة البنك الآن! 💰\n\n"
                    "⚠️ **مطلوب شركاء فوراً!** تحتاج العملية لتضافر الجهود.\n"
                    "اضغط على الزر بالأسفل للانضمام إلى طاقم العصابة.\n"
                    "⏱️ **ينتهي باب الانضمام وتوزيع المهام بعد 20 ثانية!**",
        color=discord.Color.red()
    )
    lobby_msg = await ctx.send(embed=embed_lobby, view=view_join)
    await asyncio.sleep(20)
    view_join.stop()
    
    team = view_join.participants

    await lobby_msg.edit(content=f"🔒 **أُغلق باب الانضمام!** عدد أفراد العصابة المستعدين: `{len(team)}` مجرمين.\nجاري الاتصال بـ المخطط وتوزيع المهام الآن...", embed=None, view=None)
    await asyncio.sleep(3)

    # معالجة ذكية لتوزيع الأدوار لتفادي توقف الكود إذا كان اللاعب وحده أو العدد قليل
    hacker_player = random.choice(team)
    bomber_player = random.choice(team)
    driver_player = random.choice(team)
    
    heist_failed = False

    # --- 1. مهمة المخترق (تعطيل الكاميرات) ---
    secret_code = str(random.randint(1000, 9999))
    embed_hacker = discord.Embed(
        title="🖥️ المرحلة الأولى: إختراق أنظمة الأمان",
        description=f"المخترق المعين: {hacker_player.mention}\n"
                    f"عليك كتابة الكود السري التالي في الشات لتعطيل كاميرات المراقبة بالكامل:\n\n"
                    f"🔑 الكود المطلوب: `{secret_code}`\n\n"
                    "⏱️ **لديك 15 ثانية لتنفيذ المهمة الآن وإلا كُشفت الخطة!**",
        color=discord.Color.blue()
    )
    hacker_msg = await ctx.send(embed=embed_hacker)
    
    def check_hacker(m):
        return m.author == hacker_player and m.channel == ctx.channel and m.content.strip() == secret_code

    try:
        await bot.wait_for('message', check=check_hacker, timeout=15.0)
        await ctx.send("✅ **رائع!** تم اختراق السيرفرات وتعطيل نظام الكاميرات والإنذار المبكر بنجاح!")
    except asyncio.TimeoutError:
        heist_failed = True
        await ctx.send(f"🚨 **انتهى الوقت!** فشل {hacker_player.mention} في إدخال الكود، انطلقت صفارات الإنذار ووصلت قوات مكافحة الشغب! تم إفشال العملية.")

    if heist_failed:
        await finish_heist(ctx, team, success=False)
        return

    await asyncio.sleep(3)

    # --- 2. مهمة المفجر (فتح الخزنة) ---
    correct_wire = random.choice(["الأصفر", "الأزرق"])
    view_bomb = HeistBombView(bomber_player, correct_wire)
    embed_bomb = discord.Embed(
        title="💥 المرحلة الثانية: تفجير أبواب الخزنة الكبرى",
        description=f"المفجر المعين: {bomber_player.mention}\n"
                    "وصلتم إلى باب الخزنة الفولاذي! أمامك جهاز شحنات يحتوي على سلكين.\n"
                    "أحدهما يفتح الباب بسلام، والآخر يطلق فخ الغاز القاتل!\n\n"
                    "⏱️ **أمامك 15 ثانية فقط للاختيار عبر الأزرار بالأسفل!**",
        color=discord.Color.orange()
    )
    bomb_msg = await ctx.send(embed=embed_bomb, view=view_bomb)
    await view_bomb.wait()
    
    if not view_bomb.answered or not view_bomb.success:
        heist_failed = True
        if not view_bomb.answered:
            await bomb_msg.edit(content=f"🚨 **انتهى الوقت!** تجمد {bomber_player.mention} من الرعب ولم يختر سلكاً، حاصرتكم حراس البنك وتم اعتقالكم!", view=None)

    if heist_failed:
        await finish_heist(ctx, team, success=False)
        return

    await asyncio.sleep(3)

    # --- 3. مهمة السائق (الهروب النهائي) ---
    correct_way = random.choice(["النفق السفلي", "الجسر السريع"])
    view_driver = HeistDriverView(driver_player, correct_way)
    embed_driver = discord.Embed(
        title="🚓 المرحلة الثالثة والأخيرة: الهروب الكبير",
        description=f"السائق المعين: {driver_player.mention}\n"
                    "الأموال بحوزتكم الآن وسيارات الشرطة تملأ الأفق وصوت الهليكوبتر فوقكم!\n"
                    "أمامك خيارين سريعين لتوجيه مدرعة الهروب:\n\n"
                    "⏱️ **أمامك 15 ثانية حاسمة للاختيار بالضغط على الأزرار!**",
        color=discord.Color.dark_gold()
    )
    driver_msg = await ctx.send(embed=embed_driver, view=view_driver)
    await view_driver.wait()
    
    if not view_driver.answered or not view_driver.success:
        heist_failed = True
        if not view_driver.answered:
            await driver_msg.edit(content=f"🚨 **انتهى الوقت!** ضاع السائق {driver_player.mention} في الخريطة وأحاطت بكم مدرعات مكافحة الإرهاب!", view=None)

    if heist_failed:
        await finish_heist(ctx, team, success=False)
    else:
        await finish_heist(ctx, team, success=True)

# دالة إنهاء سرقة البنك وحساب الأموال
async def finish_heist(ctx, team, success):
    if success:
        total_loot = random.randint(1500, 3000)
        share = total_loot // len(team)
        
        for member in team:
            await async_update_balance(member.id, share)
            
        embed_win = discord.Embed(
            title="🏆 تم نصر العملية والهروب الأسطوري بنجاح! 🏆",
            description=f"كفوووو يا أبطال السطو! نجحت الخطة بالكامل وتمت سرقة البنك المركزي بنجاح ساحق!\n\n"
                        f"💰 **إجمالي الغنيمة الكبرى:** `{total_loot} دولار`\n"
                        f"💸 **نصيب كل فرد مشارك بالعصابة:** `{share} دولار` كاش في حسابه السحابي!\n\n"
                        "عاش الفريق الأسطوري! 😎🕶️",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed_win)
    else:
        penalty = 150
        for member in team:
            await async_update_balance(member.id, -penalty)
            
        embed_lose = discord.Embed(
            title="💀 فشلت العملية وتم زجكم في السجن خلف القضبان! 💀",
            description=f"للأسف تم القبض على أفراد العصابة بالكامل من قبل قوات النخبة.\n\n"
                        f"❌ تم تغريم كل لاعب شارك في العملية مبلغ **{penalty} دولار** كغرامة كفالة للخروج من السجن.\n"
                        "حاولوا المرة القادمة بتنسيق وتوقيت أسرع! 🚔",
            color=discord.Color.dark_grey()
        )
        await ctx.send(embed=embed_lose)


@bot.command(name="العاب")
async def list_games(ctx):
    embed = discord.Embed(
        title="🎮 قائمة ألعاب بوت B✰IL التفاعلية",
        description="إليك الألعاب المتاحة حالياً داخل البوت لتجميع الأموال وتحدي أصدقائك! 💸🔥",
        color=discord.Color.purple()
    )
    embed.add_field(
        name="🚨 1. عملية السطو الكبرى (`!سرقة`) [🔥 نادرة وجديدة]",
        value="• **الوصف:** لعبة تعاونية جماعية تتطلب سرعة وتوزيع أدوار (مخترق، مفجر، سائق).\n"
              "• **طريقة اللعب:** اكتب `!سرقة` وانضم للعصابة، ثم نفذ مهمتك خلال **15 ثانية** عند طلبها.\n"
              "• **النتيجة:** نصر يوزع من **1500 إلى 3000 دولار** على الفريق! وفشل يسجنكم بغرامة. 💰🕶️",
        inline=False
    )
    embed.add_field(
        name="🧠 2. فعالية الأسئلة (`!سؤال`)",
        value="• **الوصف:** أسئلة ثقافية وتحديات صعبة وسريعة في الشات.\n"
              "• **طريقة اللعب:** اكتب `!سؤال` أو `!سؤال [عدد الجولات]` (مثال: `!سؤال 5`).\n"
              "• **الجائزة:** **50 دولار** لكل إجابة صحيحة وسريعة! ⏱️",
        inline=False
    )
    embed.add_field(
        name="💥 3. لعبة تفكيك القنبلة (`!قنبلة`)",
        value="• **الوصف:** قنبلة موقوتة تحتوي على 3 أسلاك ملونة وعليك اختيار السلك الصحيح.\n"
              "• **طريقة اللعب:** اكتب `!قنبلة` وااضغط على الزر الملون.\n"
              "• **النتيجة:** نصر يعطيك **50 دولار**، وانفجار يخصم منك **20 دولار**! 🔴🔵🟢",
        inline=False
    )
    embed.add_field(
        name="🚪 4. مغامرة الهروب من الغرفة المظلمة (`!هروب`)",
        value="• **الوصف:** لعبة مغامرة ورعب مكونة من 3 مراحل تعتمد على الأزرار والذكاء الذاتي.\n"
              "• **طريقة اللعب:** اكتب `!هروب` واتبع التعليمات بالضغط على الأزرار وحل اللغز المكتوب.\n"
              "• **النتيجة:** الهروب الناجح يمنحك جائزة كبرى من **200 إلى 500 دولار**! والخسارة تكلفك خصم رصيد. 💀🏆",
        inline=False
    )
    embed.set_footer(text=f"طلب بواسطة: {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
    await ctx.send(embed=embed)

@bot.command(name="سؤال")
async def game_quiz(ctx, rounds: int = 1):
    if rounds < 1: rounds = 1
    elif rounds > 10:
        await ctx.send("⚠️ | الحد الأقصى للجولات في المرة الواحدة هو 10 جولات فقط!")
        rounds = 10

    await ctx.send(f"🎮 | **ستبدأ الآن فعالية الأسئلة المكونة من ({rounds}) جولات! استعدوا...** 🔥")
    await asyncio.sleep(2)

    for r in range(1, rounds + 1):
        q, a = random.choice(list(QUESTIONS_POOL.items()))
        embed = discord.Embed(title=f"🧠 الجولة [{r} من {rounds}]", description=f"**{q}**", color=discord.Color.dark_red())
        embed.set_footer(text="لديك 8 ثوانٍ فقط للإجابة الصحيحة! 🔥")
        await ctx.send(embed=embed)
        
        def check(m): return m.channel == ctx.channel and m.content.strip().lower() == a.strip().lower() and not m.author.bot
        try:
            msg = await bot.wait_for('message', check=check, timeout=8.0)
            await async_update_balance(msg.author.id, 50)
            await ctx.send(embed=discord.Embed(title="🎉 إجابة صحيحة وسريعة!", description=f"كفو {msg.author.mention}! ربح **50 دولار** 💵.", color=discord.Color.green()))
        except asyncio.TimeoutError:
            await ctx.send(embed=discord.Embed(title="⏱️ انتهى الوقت!", description=f"الإجابة الصحيحة: **{a}** 💡", color=discord.Color.orange()))
        if r < rounds:
            await asyncio.sleep(3)
    await ctx.send("🏁 | **انتهت جميع الجولات!**")

@bot.command(name="قنبلة")
async def game_bomb(ctx):
    correct_wire = random.choice(["أحمر", "أزرق", "أخضر"])
    view = BombButtons(author=ctx.author, correct_wire=correct_wire)
    msg = await ctx.send("💥 **بدأت لعبة القنبلة!** اختر سلكاً لتقطيعه:", view=view)
    await view.wait()
    if not view.answered: await msg.edit(content="⏱️ انتهى الوقت! انفجرت القنبلة.", view=None)

@bot.command(name="هروب")
async def start_escape(ctx):
    view = EscapeRoomOneView(ctx.author, ctx)
    
    embed = discord.Embed(
        title="👁️ الغرفة المظلمة - المرحلة [1 من 3]",
        description=f"استيقظت يا {ctx.author.mention} لتجد نفسك محبوساً في مكان مرعب تفوح منه رائحة الغبار..\n"
                    "تسمع أصوات خطوات غريبة تقترب منك بسرعة! 👣\n\n"
                    "أمامك 3 أبواب غامضة بالأسفل:\n"
                    "🚪 **[1]** باب حديدي يخرج من أسفله ضوء أحمر خافت.\n"
                    "🚪 **[2]** باب خشبي قديم يصدر صريراً مرعباً.\n"
                    "🚪 **[3]** باب زجاجي ملطخ بالدماء.\n\n"
                    "⏱️ **لديك 15 ثانية فقط للاختيار بالضغط على الأزرار المرفقة!**",
        color=discord.Color.dark_purple()
    )
    msg = await ctx.send(embed=embed, view=view)
    
    await view.wait()
    if not view.responded:
        await msg.edit(content=f"💀 {ctx.author.mention}، تأخرت كثيراً في اتخاذ القرار! ظهر الكيان المظلم من خلفك وقام بتصفيتك.. **انتهت اللعبة!**", embed=None, view=None)

# --- باقي الأوامر الخدمية الأساسية ---
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
    print(f"Logged in as {bot.user.name} with The Heist Game Fixed!")
    try:
        auto_ping.start()
    except: pass

bot.run(os.environ.get('DISCORD_TOKEN'))