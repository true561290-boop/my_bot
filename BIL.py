import asyncio
import base64
import json
import os
import random
from threading import Thread

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
import typing
from flask import Flask
import requests

# --- 1. خادم الويب للحفاظ على استمرار التشغيل 24/7 ---
app = Flask("")


@app.route("/")
def home():
  return "B✰IL Bot is Online!"


def run_web():
  port = int(os.environ.get("PORT", 8080))
  app.run(host="0.0.0.0", port=port)


def keep_alive():
  t = Thread(target=run_web)
  t.daemon = True
  t.start()


keep_alive()

# --- 2. إعدادات البوت والبيانات ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

GITHUB_TOKEN = "ghp_2v2m8IXKyh0YQxZRrQnjbl08gmEH5C4E7P3b"
REPO_OWNER = "true561290-boop"
REPO_NAME = "my_bot"
FILE_PATH = "user_balances.json"

# آيدي رتبة ليفل 50 لمنع الخط الكبير #
LEVEL_50_ROLE_ID = 1515396547473309712


# --- دالة جلب أحدث الأرصدة من GitHub عند التشغيل ---
def fetch_latest_balances_from_github():
  raw_url = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/main/{FILE_PATH}"
  try:
    response = requests.get(raw_url)
    if response.status_code == 200:
      data = response.json()
      with open(FILE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
      print("✅ تم جلب أحدث نسخة أرصدة من GitHub بنجاح!")
    else:
      print("⚠️ لم يتم العثور على الملف في GitHub أو هو فارغ حالياً.")
  except Exception as e:
    print(f"❌ خطأ أثناء جلب الأرصدة من GitHub: {e}")


fetch_latest_balances_from_github()


def load_balances():
  if os.path.exists(FILE_PATH):
    with open(FILE_PATH, "r", encoding="utf-8") as f:
      try:
        return json.load(f)
      except json.JSONDecodeError:
        return {}
  return {}


def save_balances_local_and_cloud(balances):
  with open(FILE_PATH, "w", encoding="utf-8") as f:
    json.dump(balances, f, ensure_ascii=False, indent=4)

  url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{FILE_PATH}"
  headers = {
      "Authorization": f"token {GITHUB_TOKEN}",
      "Accept": "application/vnd.github.v3+json",
  }

  get_res = requests.get(url, headers=headers)
  sha = get_res.json().get("sha") if get_res.status_code == 200 else None

  content_str = json.dumps(balances, ensure_ascii=False, indent=4)
  encoded_content = base64.b64encode(content_str.encode("utf-8")).decode(
      "utf-8"
  )

  data = {
      "message": "🔄 تحديث أرصدة الأعضاء تلقائياً",
      "content": encoded_content,
  }
  if sha:
    data["sha"] = sha

  put_res = requests.put(url, headers=headers, json=data)
  if put_res.status_code in [200, 201]:
    print("☁️ تم تحديث الأرصدة سحابياً على GitHub بنجاح!")
  else:
    print(f"❌ فشل تحديث GitHub: {put_res.text}")


user_balances = load_balances()


def get_balance(user_id):
  return user_balances.get(str(user_id), 0)


def add_balance(user_id, amount):
  uid = str(user_id)
  user_balances[uid] = user_balances.get(uid, 0) + amount
  save_balances_local_and_cloud(user_balances)


def remove_balance(user_id, amount):
  uid = str(user_id)
  current = user_balances.get(uid, 0)
  if current >= amount:
    user_balances[uid] = current - amount
    save_balances_local_and_cloud(user_balances)
    return True
  return False


# --- 3. المتجر التفاعلي وقوائم الشراء ---

# رتب المستويات والفي آي بي
SHOP_VIP_ROLES = {
    "lvl_25": {
        "name": " Level 25(ارسال صور)",
        "price": 1000,
        "id":1515396547473309710,
    },
    "lvl_35": {
        "name": " Level 35(ارسال صور وستيكرات من سيرفر اخر)",
        "price": 2000,
        "id":1515396547473309711,
    },
    "lvl_50": {
        "name": " Level 50 (كل ما سبق+ ميزة الخط الكبير)",
        "price": 3500,
        "id":1515396547473309712,
    },
    "founder": {
        "name": "⚡ الزنجي المؤسس",
        "price": 5000,
        "id":1527739093163708548,
    },
    

}

# ألوان الأسماء السبعة
SHOP_COLOR_ROLES = {
    "c_red": {"name": " أحمر", "price": 300, "id":1515396547536355469},
    "c_blue": {"name": " أزرق", "price": 300, "id":1515396547528102135},
    "c_green": {"name": " أخضر", "price": 300, "id":1515396547528102136},
    "c_purple": {"name": " بنفسجي", "price": 300, "id":1515396547528102134},
    "c_yellow": {"name": " أصفر", "price": 300, "id":1515396547528102137},
    "c_gray": {"name": " رمادي", "price": 300, "id":1515487581138190376},
    "c_skin": {"name": " Skin", "price": 300, "id":1515480359553335441},
}


# زر العودة للقائمة الرئيسية
class BackToMainButton(discord.ui.Button):

  def __init__(self):
    super().__init__(
        label="رجوع للقائمة الرئيسية",
        style=discord.ButtonStyle.secondary,
        emoji="🔙",
    )

  async def callback(self, interaction: discord.Interaction):
    embed = discord.Embed(
        title=" المتجر ",
        description=(
            f"أهلاً بك يا {interaction.user.mention} في المتجر!\n"
            f"💳 رصيدك الحالي: **{get_balance(interaction.user.id)}** طولار\n\n"
            "اختر القسم الذي تريد تصفحه من القائمة أدناه:"
        ),
        color=discord.Color.purple(),
    )
    view = MainShopView()
    await interaction.response.edit_message(embed=embed, view=view)


class ColorSelect(discord.ui.Select):

  def __init__(self):
    options = [
        discord.SelectOption(
            label=item["name"],
            value=key,
            description=f"السعر: {item['price']} طولار",
        )
        for key, item in SHOP_COLOR_ROLES.items()
    ]
    super().__init__(
        placeholder=" اختر اللون ",
        min_values=1,
        max_values=1,
        options=options,
    )

  async def callback(self, interaction: discord.Interaction):
    selected_key = self.values[0]
    item = SHOP_COLOR_ROLES[selected_key]
    user = interaction.user
    guild = interaction.guild
    role = guild.get_role(item["id"])

    if not role:
      await interaction.response.send_message(
          "❌ الرتبة غير موجودة في السيرفر، يرجى مراجعة الإدارة.",
          ephemeral=True,
      )
      return

    if role in user.roles:
      await interaction.response.send_message(
          f"⚠️ أنت تملك رتبة **{role.name}** بالفعل!", ephemeral=True
      )
      return

    if get_balance(user.id) < item["price"]:
      await interaction.response.send_message(
          f"❌ رصيدك غير كافٍ! تحتاج إلى **{item['price']}** طولار.",
          ephemeral=True,
      )
      return

    # إزالة الألوان القديمة إن وجدت
    all_color_ids = [c["id"] for c in SHOP_COLOR_ROLES.values()]
    roles_to_remove = [r for r in user.roles if r.id in all_color_ids]
    if roles_to_remove:
      await user.remove_roles(*roles_to_remove)

    remove_balance(user.id, item["price"])
    await user.add_roles(role)

    embed = discord.Embed(
        title="🎨 تم شراء اللون بنجاح!",
        description=(
            f" {user.mention}! تم منحك رتبة **{role.name}** وتجهيزها"
            f" كولونك الجديد.\n💰 المخصوم: **{item['price']}** طولار."
        ),
        color=discord.Color.green(),
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


class VIPSelect(discord.ui.Select):

  def __init__(self):
    options = [
        discord.SelectOption(
            label=item["name"],
            value=key,
            description=f"السعر: {item['price']} طولار",
        )
        for key, item in SHOP_VIP_ROLES.items()
    ]
    super().__init__(
        placeholder=" اختر الرتبة ",
        min_values=1,
        max_values=1,
        options=options,
    )

  async def callback(self, interaction: discord.Interaction):
    selected_key = self.values[0]
    item = SHOP_VIP_ROLES[selected_key]
    user = interaction.user
    guild = interaction.guild
    role = guild.get_role(item["id"])

    if not role:
      await interaction.response.send_message(
          "❌ الرتبة غير موجودة في السيرفر، يرجى مراجعة الإدارة.",
          ephemeral=True,
      )
      return

    if role in user.roles:
      await interaction.response.send_message(
          f"⚠️ أنت تملك رتبة **{role.name}** بالفعل!", ephemeral=True
      )
      return

    if get_balance(user.id) < item["price"]:
      await interaction.response.send_message(
          f"❌ رصيدك غير كافٍ! تحتاج إلى **{item['price']}** طولار.",
          ephemeral=True,
      )
      return

    remove_balance(user.id, item["price"])
    await user.add_roles(role)

    embed = discord.Embed(
        title="تم شراء الرتبة بنجاح!",
        description=(
            f" يا {user.mention}! تم منحك رتبة **{role.name}**"
            f" بنجاح.\n💰 المخصوم: **{item['price']}** طولار."
        ),
        color=discord.Color.gold(),
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


class MainCategorySelect(discord.ui.Select):

  def __init__(self):
    options = [
        discord.SelectOption(
            label=" الرتب ",
            value="cat_vip",
            description="عرض الرتب ",
        ),
        discord.SelectOption(
            label="🎨 ألوان الأسماء",
            value="cat_colors",
            description="عرض قائمة ألوان الأسماء السبعة",
        ),
    ]
    super().__init__(
        placeholder="🛒 اختر القسم الذي تريد تصفحه...",
        min_values=1,
        max_values=1,
        options=options,
    )

  async def callback(self, interaction: discord.Interaction):
    if self.values[0] == "cat_vip":
      view = discord.ui.View()
      view.add_item(VIPSelect())
      view.add_item(BackToMainButton())
      embed = discord.Embed(
          title="قسم الرتب ",
          description=(
              "اختر الرتبة التي تريد شراءها من القائمة التالية:\n(ملاحظة: شراء"
              " Level 50 يمنحك ميزة الخط الكبير `#`)"
          ),
          color=discord.Color.gold(),
      )
      await interaction.response.edit_message(embed=embed, view=view)
    elif self.values[0] == "cat_colors":
      view = discord.ui.View()
      view.add_item(ColorSelect())
      view.add_item(BackToMainButton())
      embed = discord.Embed(
          title="🎨 قسم ألوان الأسماء",
          description=(
              "اختر اللون الذي يناسبك"
          ),
          color=discord.Color.blue(),
      )
      await interaction.response.edit_message(embed=embed, view=view)


class MainShopView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)
    self.add_item(MainCategorySelect())


@bot.command(name="متجر")
async def shop_command(ctx):
  embed = discord.Embed(
      title="المتجر ",
      description=(
          f"أهلاً بك يا {ctx.author.mention} في المتجر\n"
          f"💳 رصيدك الحالي: **{get_balance(ctx.author.id)}** طولار\n\n"
          "استخدم القائمة أدناه للتنقل بين الأقسام والشراء بسهولة."
      ),
      color=discord.Color.purple(),
  )
  view = MainShopView()
  await ctx.send(embed=embed, view=view)


# --- 4. نظام منع الخط الكبير (#) بدون رتبة Level 50 ---
@bot.event
async def on_message(message):
  if message.author.bot:
    return

  # التحقق مما إذا كانت الرسالة تبدأ بـ # للكتابة بخط كبير
  if message.content.startswith("# "):
    level_50_role = message.guild.get_role(1515396547473309712)
    if level_50_role and level_50_role not in message.author.roles:
      try:
        await message.delete()
        warning = await message.channel.send(
            f"⚠️ يا {message.author.mention}، لا يمكنك الكتابة بخط كبير `#` لأنك"
            " لا تملك رتبة **Level 50**! يمكنك شراؤها من المتجر (`!متجر`)."
        )
        delete_after=(2)
        await asyncio.sleep()
        await warning.delete()
        return
      except Exception as e:
        print(f"خطأ أثناء حذف الرسالة: {e}")

  await bot.process_commands(message)


# --- 5. نظام الألعاب والأسئلة (100 سؤال و100 لغز صعبة) ---

QUESTIONS = [
    {"q": "ما هي عاصمة أستراليا؟", "a": ["كانبرا", "كانبيرا"]},
    {"q": "ما هي أصغر دولة في العالم من حيث المساحة؟", "a": ["الفاتيكان"]},
    {
        "q": "ما هو العنصر الكيميائي الذي رمزه 'Fe'؟",
        "a": ["الحديد", "حديد"],
    },
    {"q": "ما هي أكبر صحراء في العالم؟", "a": ["الصحراء الكبرى"]},
    {
        "q": "في أي عام وقعت معركة حطين؟",
        "a": ["1187", "١١٨٧", "1187m"],
    },
    {"q": "ما هو أطول نهر في العالم؟", "a": ["النيل", "نهر النيل"]},
    {
        "q": "ما هي عاصمة كندا؟",
        "a": ["أوتاوا", "اوتاوا"],
    },
    {
        "q": "من هو الملقب بـ 'سيف الله المسلول'؟",
        "a": ["خالد بن الوليد", "خالد ابن الوليد"],
    },
    {
        "q": "ما هو أثقل كوكب في المجموعة الشمسية؟",
        "a": ["المشتري", "كوكب المشتري"],
    },
    {
        "q": "ما هو الغاز الأكثر وجوداً في الغلاف الجوي؟",
        "a": ["النيتروجين", "نيتروجين"],
    },
    {"q": "ما هي الدولة الأكثر سكاناً في العالم؟", "a": ["الهند"]},
    {"q": "ما هي أكبر قارة في العالم من حيث المساحة؟", "a": ["آسيا", "اسيا"]},
    {"q": "ما هو اسم أسرع حيوان بري في العالم؟", "a": ["الفهد", "فهد"]},
    {
        "q": "ما هو أصلح معركة حدثت في التاريخ الإسلامي وكانت فتحاً مبيناً؟",
        "a": ["فتح مكة"],
    },
    {
        "q": "من هو القائد المسلم الذي فتح الأندلس؟",
        "a": ["طارق بن زياد", "طارق ابن زياد"],
    },
    {"q": "ما هي عاصمة اليابان؟", "a": ["طوكيو"]},
    {
        "q": "ما هي الوحدة المستخدمة لقياس الشدة الصوتية؟",
        "a": ["ديسيبل", "الديسيبل"],
    },
    {
        "q": "ما هو الكوكب الملقب بالكوكب الأحمر؟",
        "a": ["المريخ", "كوكب المريخ"],
    },
    {"q": "ما هي عاصمة البرازيل؟", "a": ["برازيليا"]},
    {
        "q": "كم عدد قلوب الأخطبوط؟",
        "a": ["3", "ثلاثة", "٣"],
    },
    {
        "q": "من هو مخترع المصباح الكهربائي؟",
        "a": ["توماس أديسون", "اديسون", "أديسون"],
    },
    {
        "q": "ما هي أصغر عظمة في جسم الإنسان؟",
        "a": ["الركاب", "عظمة الركاب"],
    },
    {"q": "ما هي عاصمة فرنسا؟", "a": ["باريس"]},
    {"q": "في أي قارة تقع مصر؟", "a": ["أفريقيا", "افريقيا"]},
    {
        "q": "ما هو أكبر محيط في العالم؟",
        "a": ["المحيط الهادي", "المحيط الهادئ"],
    },
    {
        "q": "كم عدد أضلاع المثلث؟",
        "a": ["3", "ثلاثة", "٣"],
    },
    {"q": "ما هو المكون الرئيسي للزجاج؟", "a": ["الرمل", "الريمال"]},
    {
        "q": "ما هي عاصمة ألمانيا؟",
        "a": ["برلين"],
    },
    {
        "q": "من هو الشاعر الملقب بـ 'أمير الشعراء'؟",
        "a": ["أحمد شوقي", "احمد شوقي"],
    },
    {
        "q": "ما هي أكبر عضلة في جسم الإنسان؟",
        "a": ["عضلة الأرداف", "الأرداف"],
    },
    {"q": "ما هي عاصمة روسيا؟", "a": ["موسكو"]},
    {"q": "كم عدد العظام في جسم الإنسان البالغ؟", "a": ["206", "٢٠٦"]},
    {
        "q": "ما هو المكون الأساسي للشمس؟",
        "a": ["الهيدروجين", "غاز الهيدروجين"],
    },
    {"q": "ما هي عاصمة إيطاليا؟", "a": ["روما"]},
    {"q": "في أي مدينة توجد منظمة اليونسكو؟", "a": ["باريس"]},
    {
        "q": "ما هي أكبر بحيرة في العالم؟",
        "a": ["بحر قزوين"],
    },
    {"q": "من هو عالم الفيزياء صاحب نظريّة النسبية؟", "a": ["أينشتاين", "اينشتاين"]},
    {"q": "ما هي عاصمة إسبانيا؟", "a": ["مدريد"]},
    {"q": "ما هو الحيوان الذي يُسمى 'سفينة الصحراء'؟", "a": ["الجمل", "جمل"]},
    {
        "q": "ما هي المادة الأكثر صلابة في طبيعة الأرض؟",
        "a": ["الألماس", "الماس"],
    },
    {
        "q": "ما هي الدولة المفترض بها الموطن الأصلي للبيتزا؟",
        "a": ["إيطاليا", "ايطاليا"],
    },
    {"q": "ما هي عاصمة تركيا؟", "a": ["أنقرة", "انقرة"]},
    {"q": "كم عدد الألوان في قوس قزح؟", "a": ["7", "سبعة", "٧"]},
    {
        "q": "ما هي أطول سلسة جبلية في العالم؟",
        "a": ["الأنديز", "جبال الأنديز"],
    },
    {"q": "ما هي عاصمة الأرجنتين؟", "a": ["بوينس آيرس", "بوينس ايرس"]},
    {
        "q": "ما هو الغاز الذي يستعمله النبات في البناء الضوئي؟",
        "a": ["ثاني أكسيد الكربون", "ثاني اكسيد الكربون"],
    },
    {"q": "ما هي عاصمة المغرب؟", "a": ["الرباط"]},
    {
        "q": "ما هي السورة التي تُسمى 'قلب القرآن'؟",
        "a": ["يس", "يسن"],
    },
    {
        "q": "ما هو العلم الذي يهتم بدراسة الأحافير والحيوانات القديمة؟",
        "a": ["الفرع الأحفوري", "الإحاثة", "علم الأحافير"],
    },
    {"q": "ما هي عاصمة السويد؟", "a": ["ستوكهولم"]},
    {"q": "ما هو اسم أعمق نقطة في محيطات الأرض؟", "a": ["خندق ماريانا"]},
    {"q": "ما هي عاصمة مصر؟", "a": ["القاهرة"]},
    {
        "q": "كم طابق يوجد في برج خليفة تقريباً؟",
        "a": ["163", "١٦٣"],
    },
    {
        "q": "ما هو الهرمون المسؤول عن تنظيم مستوى السكر في الدم؟",
        "a": ["الأنسولين", "الانسولين"],
    },
    {"q": "ما هي عاصمة المملكة العربية السعودية؟", "a": ["الرياض"]},
    {"q": "ما هي عاصمة الصين؟", "a": ["بكين"]},
    {
        "q": "ما هو معدن السيولة العالية الفضي السائل في حرارة الغرفة؟",
        "a": ["الزئبق"],
    },
    {"q": "ما هي عاصمة العراق؟", "a": ["بغداد"]},
    {"q": "من هو أول إنسان صعد إلى الفضاء؟", "a": ["يوري جاجارين", "جاجارين"]},
    {
        "q": "ما هي الدولة التي تمتلك أطول خط ساحلي في العالم؟",
        "a": ["كندا"],
    },
    {"q": "ما هي عاصمة الأردن؟", "a": ["عمان", "عمّان"]},
    {
        "q": "ما هي السورة التي لا تبدأ بالبسملة؟",
        "a": ["التوبة", "سورة التوبة"],
    },
    {
        "q": "ما هو اسم أطول بناء في العالم حالياً؟",
        "a": ["برج خليفة"],
    },
    {"q": "ما هي عاصمة اليونان؟", "a": ["أثينا", "اثينا"]},
    {"q": "كم عدد طبقات الغلاف الجوي الرئيسيّة؟", "a": ["5", "خمسة", "٥"]},
    {"q": "ما هو أصل لغة إسبانيا؟", "a": ["اللاتينية"]},
    {"q": "ما هي عاصمة كوريا الجنوبية؟", "a": ["سيول", "سول"]},
    {
        "q": "من هو مكتشف البنسلين؟",
        "a": ["ألكسندر فلمنج", "فلمنج", "الكسندر فلمنج"],
    },
    {"q": "ما هي عاصمة هولندا؟", "a": ["أمستردام", "امستردام"]},
    {"q": "ما هي أكبر جزيرة في العالم؟", "a": ["جرينلاند"]},
    {"q": "ما هي عاصمة الجزائر؟", "a": ["الجزائر"]},
    {"q": "كم عدد صمامات قلب الإنسان؟", "a": ["4", "أربعة", "arba'a", "٤"]},
    {
        "q": "ما هو أطول نهر في أوروبا؟",
        "a": ["الفولغا", "نهر الفولغا"],
    },
    {"q": "ما هي عاصمة الهند؟", "a": ["نيودلهي", "دلهي"]},
    {
        "q": "من هو مؤسس علم الجبر؟",
        "a": ["الخوارزمي", "الخوارزمي حاسب"],
    },
    {"q": "ما هي عاصمة النرويج؟", "a": ["أوسلو", "وسلو"]},
    {
        "q": "ما هو اسم الكوكب الأقرب إلى الأرض؟",
        "a": ["الزهرة", "كوكب الزهرة"],
    },
    {"q": "ما هي عاصمة المكسيك؟", "a": ["مكسيكو سيتي", "مكسيكو"]},
    {
        "q": "ما هي السورة التي ذكرت فيها البسملة مرتين؟",
        "a": ["النمل", "سورة النمل"],
    },
    {"q": "ما هي عاصمة السودان؟", "a": ["الخرطوم"]},
    {"q": "كم عدد أحرف اللغة العربية؟", "a": ["28", "٢٨"]},
    {"q": "ما هو اسم طائر لا يستطيع الطيران ويستمتع بالثلج؟", "a": ["البطريق"]},
    {"q": "ما هي عاصمة الدنمارك؟", "a": ["كوبنهاجن"]},
    {
        "q": "ما هي السلسلة الجبلية الفاصلة بين قارتي آسيا وأوروبا؟",
        "a": ["أورال", "جبال الأورال"],
    },
    {"q": "ما هي عاصمة سوريا؟", "a": ["دمشق"]},
    {
        "q": "ما هي أسرع سمكة في البحر؟",
        "a": ["سمكة الشراع", "الشراع"],
    },
    {"q": "ما هي عاصمة بلجيكا؟", "a": ["بروكسل"]},
    {
        "q": "ما هي الدولة العربية التي يمر بها خط الاستواء؟",
        "a": ["الصومال"],
    },
    {"q": "ما هي عاصمة تونس؟", "a": ["تونس"]},
    {
        "q": "ما هو اسم النهر الوحيد الذي يمر بالعديد من الدول الأوربية؟",
        "a": ["الدانوب", "نهر الدانوب"],
    },
    {"q": "ما هي عاصمة البرتغال؟", "a": ["لشبونة"]},
    {
        "q": "من هو الصحابي الجليل الملقب بـ 'ترجمان القرآن'؟",
        "a": ["عبدالله بن عباس", "عبد الله بن عباس"],
    },
    {"q": "ما هي عاصمة النمسا؟", "a": ["فيينا"]},
    {"q": "ما هو اسم أطول حيوان في العالم؟", "a": ["الزرافة", "زرافة"]},
    {"q": "ما هي عاصمة اليمن؟", "a": ["صنعاء"]},
    {"q": "ما هو أصل لعبة الشطرنج؟", "a": ["الهند"]},
    {"q": "ما هي عاصمة سويسرا؟", "a": ["برن"]},
    {
        "q": "ما هو الغاز الذي ينبعث من أشجار الغابات ليلةً؟",
        "a": ["ثاني أكسيد الكربون"],
    },
    {"q": "ما هي عاصمة قطر؟", "a": ["الدوحة"]},
]

RIDDLES = [
    {
        "q": "شيء كلما أخذت منه كبر، فما هو؟",
        "a": ["الحفرة", "حفرة"],
    },
    {
        "q": "يمشي بلا أرجل ويدخل الأذنين فقط، فما هو؟",
        "a": ["الصوت", "صوت"],
    },
    {
        "q": "ما هو الشيء الذي يكتب ولا يقرأ؟",
        "a": ["القلم", "قلم"],
    },
    {
        "q": "ما هو البيت الذي لا توجد فيه أبواب ولا نوافذ؟",
        "a": ["بيت الشعر"],
    },
    {
        "q": "ما هو الشيء الذي كلما زاد نقص؟",
        "a": ["العمر", "عمر"],
    },
    {
        "q": "ما هو الشيء الذي يمكنك إمساكه بدون لمسه؟",
        "a": ["الأعصاب", "أعصابك"],
    },
    {
        "q": "ما هو القفص الذي لا يحبس فيه طائر أو حيوان؟",
        "a": ["القفص الصدري"],
    },
    {
        "q": "شيء يحترق لكي يضيء للآخرين؟",
        "a": ["الشمعة", "شمعة"],
    },
    {
        "q": "يمشي ويقف وليس له أرجل؟",
        "a": ["الظلال", "الظل", "الساعة"],
    },
    {
        "q": "ما هو الشيء الذي يبرد بالحرارة؟",
        "a": ["الفلفل", "البيض"],
    },
    {
        "q": "أنا ذو ثقوب عديدة ولكني أحتفظ بالماء، فمن أنا؟",
        "a": ["الإسفنج", "اسفنج"],
    },
    {
        "q": "ما هو الشيء الذي إذا صببت عليه الماء لا يبتل؟",
        "a": ["الظل", "ظلك"],
    },
    {
        "q": "ما هو الشارع الذي لم يسير فيه أحد؟",
        "a": ["شارع الرسم", "الشارع على الخريطة", "الخريطة"],
    },
    {
        "q": "ما هو الشيء الذي يقرأ كل الأوراق وبلا عيون؟",
        "a": ["المسح الضوئي", "الضوء"],
    },
    {
        "q": "ما هو الذي يمر عبر الزجاج ولكن لا يكسره؟",
        "a": ["الضوء", "ضوء"],
    },
    {
        "q": "له رأس واحد وله أربعة أرجل ولكن لا يسير؟",
        "a": ["السرير", "سرير"],
    },
    {"q": "شيء يأكل ولا يشبع، وإذا شرب الماء يموت؟", "a": ["النار"]},
    {
        "q": "تراه في الليل ثلاث مرات وفي النهار مرة واحدة، فما هو؟",
        "a": ["حرف اللام"],
    },
    {
        "q": "ما هو الشيء الذي ينبض بلا قلب؟",
        "a": ["الساعة", "ساعة"],
    },
    {
        "q": "ما هو الباب الذي لا يمكن فتحه؟",
        "a": ["الباب المفتوح"],
    },
    {
        "q": "هو ابن أمك وأبيك وليس بأخيك ولا أختك، فمن هو؟",
        "a": ["أنت", "انت"],
    },
    {
        "q": "تكون طويلة في شبابها وقصيرة في كبر سنها، فما هي؟",
        "a": ["الشمعة"],
    },
    {
        "q": "ماهي الأشياء التي تسير بلا قدمين وتصيح بلا فم؟",
        "a": ["الرياح", "رياح"],
    },
    {
        "q": "له أسنان كثيرة ولكنه لا يعض، فما هو؟",
        "a": ["المشط", "مشط"],
    },
    {
        "q": "يحبها الجميع ويعطونها للآخرين ولكن لا أحد يستطيع الاحتفاظ بها؟",
        "a": ["الكلمة", "الوعد"],
    },
    {
        "q": "ما هو الشيء الذي تسمعه ولا تراه، وإذا رأيته لا تسمعه؟",
        "a": ["الطلقة النارية", "الرعد"],
    },
    {
        "q": "شيء يسير في السماء ويستريح في الأرض؟",
        "a": ["المطر", "مطر"],
    },
    {
        "q": "تطير بدون أجنحة وتبكي بدون عيون، فما هي؟",
        "a": ["السحابة", "السحاب"],
    },
    {
        "q": "ما هو الشيء الذي يحتوي على المدن ولكن ليس به بيوت؟",
        "a": ["الخريطة"],
    },
    {
        "q": "شيء إذا قطعت رأسه طار؟",
        "a": ["قطار", "القطار"],
    },
    {
        "q": "ما هي التي تملك عيوناً ولا ترى؟",
        "a": ["الإبرة", "إبرة"],
    },
    {
        "q": "له أوراق كثيرة ولكنه ليس بشجرة؟",
        "a": ["الكتاب", "كتاب"],
    },
    {
        "q": "أسود عندما تشتريه، وأحمر عندما تستخدمه، وأبيض عندما ترميه؟",
        "a": ["الفحم"],
    },
    {
        "q": "ما هو الشيء الذي يجري ولكن لا يستطيع المشي؟",
        "a": ["الماء", "النهر"],
    },
    {
        "q": "يمتلك كل مفاتيح العالم ولكنه لا يستطيع فتح أي باب؟",
        "a": ["البيانو"],
    },
    {
        "q": "ما هو الشيء الذي ينكسر بمجرد تسميته؟",
        "a": ["الصمت"],
    },
    {
        "q": "يتحدث كل لغات العالم بدون أن يتكلم؟",
        "a": ["الصدى"],
    },
    {
        "q": "ما هو الشيء الذي تصنعه ولكن لا تراه؟",
        "a": ["الضوضاء", "الرقام"],
    },
    {"q": "إذا أطعمته ينمو، وإذا سقيته يموت؟", "a": ["النار"]},
    {
        "q": "يمتلك رقبة ولكن ليس له رأس؟",
        "a": ["الزجاجة", "قميص"],
    },
    {
        "q": "ما هو الذي يستطيع الضوء اختراقه والماء المضيء فيه؟",
        "a": ["الزجاج"],
    },
    {
        "q": "شيء بينك وبين السماء، فما هو؟",
        "a": ["الكاف", "حرف الكاف"],
    },
    {
        "q": "ما هو الشارع الذي يمشي فيه الناس بلا أقدام؟",
        "a": ["شارع الخريطة"],
    },
    {
        "q": "ما هو العضو الوحيد الذي لا يصله الدم؟",
        "a": ["قرنية العين", "القرنية"],
    },
    {
        "q": "ما هي الشيء الذي يولد كبيراً ويموت صغيراً؟",
        "a": ["الشمعة"],
    },
    {
        "q": "يوجد في منتصف باريس فما هو؟",
        "a": ["حرف الراء"],
    },
    {"q": "ما هو الشيء الذي إذا أكلته كله استفدت منه، وإذا أكلت نصفه مِت؟", "a": ["سمسم"]},
    {
        "q": "ما هو الذي يملك عين واحدة ولكنه لا يرى بها؟",
        "a": ["الإبرة"],
    },
    {
        "q": "ما هو الشيء الذي إذا نام لا يستيقظ؟",
        "a": ["الرماد"],
    },
    {
        "q": "له يد ولكن لا يستطيع التصفيق؟",
        "a": ["الساعة"],
    },
    {"q": "ما هو الشيء الذي يصعد ولا ينزل أبداً؟", "a": ["العمر"]},
    {
        "q": "أخت خالتك وليست خالتك فمن تكون؟",
        "a": ["أمك", "امي"],
    },
    {
        "q": "يمشي بدون قدمين ولا يدخل إلا بالأذنين؟",
        "a": ["الصوت"],
    },
    {
        "q": "تأكل منه ولكن لا يمكنك أن تأكله؟",
        "a": ["الصحن", "الطبق"],
    },
    {
        "q": "يحتاج دائماً إلى إجابة ولكنه لا يطرح أي سؤال؟",
        "a": ["الهاتف", "الجرس"],
    },
    {
        "q": "ما هو الشيء الذي يسير أمامك ولا تستطيع الوصول إليه؟",
        "a": ["المستقبل"],
    },
    {
        "q": "ما هو الشيء الذي يملك أقداماً ثلاث ولا يمشي؟",
        "a": ["المنصة", "الطاولة"],
    },
    {"q": "إذا أردت أن تستخدمه يجب عليك رميه أولاً؟", "a": ["شبكة الصيد"]},
    {
        "q": "ما هو الشيء الذي لا يتكلم وإذا جاع كذب؟",
        "a": ["الساعة"],
    },
    {
        "q": "أين يقع البحر الذي ليس به ماء؟",
        "a": ["على الخريطة"],
    },
    {
        "q": "يمتلك كل العيون ولكنه لا يرى شيئاً؟",
        "a": ["شاطئ البطاطس", "البطاطس"],
    },
    {
        "q": "ما هو الشهر الذي فيه 28 يوماً؟",
        "a": ["كل الشهور", "جميع الشهور"],
    },
    {
        "q": "ما هو أصلح شيء للرؤية في الظلام التام؟",
        "a": ["لا شيء"],
    },
    {
        "q": "ما هو الشيء الذي يملك ذراعين وليس لديه أصابع؟",
        "a": ["الكرسي"],
    },
    {
        "q": "أين يمكنك إيجاد الجمعة قبل الخميس؟",
        "a": ["في المعجم", "القاموس"],
    },
    {
        "q": "إذا كان هناك 3 تفاحات وأخذت 2، فكم تفاحة لديك؟",
        "a": ["2", "تفاحتان"],
    },
    {
        "q": "ما هو القادم الذي لا يصل أبداً؟",
        "a": ["غداً", "الغد"],
    },
    {
        "q": "أنا بداية النهاية ونهاية الزمان والمكان فمن أنا؟",
        "a": ["حرف النون"],
    },
    {
        "q": "ما هو الشيء الذي إذا غسلت به يظل متسخاً؟",
        "a": ["الماء"],
    },
    {
        "q": "ما هو الشيء الذي يطير بدون أجنحة ويدخل العيون بدون استئذان؟",
        "a": ["الغبار"],
    },
    {"q": "يتحرك باستمرار وبلا توقف ولكن لا يتعب؟", "a": ["القلب"]},
    {
        "q": "ما هي المادة التي يفرزها الجسم وتصلح لبناء العظام؟",
        "a": ["الكالسيوم"],
    },
    {
        "q": "ما هو الشيء الذي ينقص كلما أخذت منه أكثر؟",
        "a": ["الحفرة"],
    },
    {
        "q": "ما هي الشجرة التي ليس لها ظل وليس لها أوراق؟",
        "a": ["شجرة العائلة"],
    },
    {
        "q": "ما هو أصلح مكان لبناء بيت بدون جدران؟",
        "a": ["الإنترنت", "العقل"],
    },
    {
        "q": "ما هي الكلمة التي تُنطق دائماً بشكل غير صحيح؟",
        "a": ["غير صحيح"],
    },
    {
        "q": "يمتلك ريشاً ولكنه لا يطير ولديه أرقام فقط؟",
        "a": ["سهم الدرجات", "القلم"],
    },
    {"q": "ما هي العروس التي لا تبكي عند زفافها؟", "a": ["عروس البحر"]},
    {
        "q": "ما هو القماش الذي لا يمكنك ارتداؤه؟",
        "a": ["قماش العنكبوت"],
    },
    {
        "q": "شيء إذا لمسته صرخ؟",
        "a": ["جرس الباب", "الجرس"],
    },
    {
        "q": "ما هو العقرب الذي لا يلذغ؟",
        "a": ["عقرب الساعة"],
    },
    {
        "q": "ما هو العضو الذي يستمر في النمو طوال حياة الإنسان؟",
        "a": ["الأنف والأذن", "الأنف"],
    },
    {
        "q": "ما هو السؤال الذي لا يمكنك الإجابة عليه بنعم أبداً؟",
        "a": ["هل أنت نائم؟"],
    },
    {"q": "ما هي الكلمة الوحيدة في القاموس التي كُتبت خطأ؟", "a": ["خطأ"]},
    {"q": "من هو الشخص الذي يرى عدوه وصديقه بعين واحدة؟", "a": ["الأعور"]},
    {
        "q": "ما هو الشيء الذي لا يبتل حتى لو نزل في أغزر مياه؟",
        "a": ["الظل"],
    },
    {"q": "له أسنان عديدة لكنه لا يستطيع العض بها؟", "a": ["المشط"]},
    {
        "q": "يمتلك زجاجاً ولكنه ليس بنوافذ، ويتصل بالشبكة؟",
        "a": ["الهاتف الذكي"],
    },
    {
        "q": "ما هو الماء الذي لا يخرج من الأرض ولا ينزل من السماء؟",
        "a": ["العرق", "دموع العين"],
    },
    {
        "q": "من هو الشخص الذي يقتل مئات الأشخاص يومياً بدون أن يعاقبه أحد؟",
        "a": ["الحلاق"],
    },
    {
        "q": "ما هي العروس التي لا يراها أحد إلا زوجها؟",
        "a": ["عروسة اللعبة"],
    },
    {
        "q": "يمتلك شوكة واحدة وأحياناً أربعة ولا يأكل أبداً؟",
        "a": ["شوكة الطعام"],
    },
    {
        "q": "ما هو السلم الذي لا يصعد عليه أحد؟",
        "a": ["سلم الرواتب"],
    },
    {
        "q": "تسير في كل أرجاء الغرفة لكنها لا تتحرك أبداً؟",
        "a": ["الجدران"],
    },
    {
        "q": "تلبس الثوب بالكامل لكنها تظل عارية؟",
        "a": ["إبرة الخياطة"],
    },
    {
        "q": "ما هو الشيء الذي يسير بلا أقدام ولا يرجع للخلف أبداً؟",
        "a": ["الوقت", "العمر"],
    },
    {
        "q": "إذا وضعتني في ماء حار أصبح صلباً؟",
        "a": ["البيض", "بيضة"],
    },
    {
        "q": "ما هو الشيء الذي يحك أذنه بأنفه؟",
        "a": ["الفيل"],
    },
    {
        "q": "ما هو الشيء الذي تحمله ويحملك في نفس الوقت؟",
        "a": ["الحذاء"],
    },
]


@bot.command(name="سؤال")
async def quiz_game(ctx, rounds: int = 1):
	if rounds < 1 or rounds > 10:
        await ctx.send(
            "❌ يرجى تحديد عدد جولات بين **1** و **10** فقط!", delete_after=2
        )
        return
async def question_game(ctx):
  selected_questions = random.sample(
        questions_bank, min(rounds, len(questions_bank))
    )

    for round_num, item in enumerate(
        selected_questions, 1
  q_data = random.choice(QUESTIONS)
  embed = discord.Embed(
      title="🧠 سؤال جديد!",
      description=(
          f"يا {ctx.author.mention}، أجب عن السؤال التالي كسباً لـ **40**"
          f" طولار:\n\n❓ **{q_data['q']}**"
      ),
      color=discord.Color.blue(),
  )
  embed.set_footer(text="⏱️ لديك 10 ثوانٍ للإجابة على هذا السؤال!")
  await ctx.send(embed=embed)

  def check(m):
    return m.author == ctx.author and m.channel == ctx.channel

  try:
    msg = await bot.wait_for("message", timeout=10.0, check=check)
    if msg.content.strip().lower() in [ans.lower() for ans in q_data["a"]]:
      add_balance(ctx.author.id, 40)
      await ctx.send(
          f"🎉 **إجابة صحيحة!** تم إضافة 40 طولار إلى حسابك يا"
          f" {ctx.author.mention}. رصيدك الجديد: **{get_balance(ctx.author.id)}**"
          " طولار.",allowed_mentions=discord.AllowedMentions(users=False)
          )
      
    else:
      await ctx.send(
          f"❌ **إجابة خاطئة!** الإجابة الصحيحة كانت:"
          f" **{q_data['a'][0]}**."
      )
  except asyncio.TimeoutError:
    await ctx.send(
        f"⏰ **انتهى الوقت!** لم تجب خلال 10 ثانية يا {ctx.author.mention}."‚allowed_mentions=discord.AllowedMentions.none())
    

@bot.command(name="سجن")
async def jail_game(ctx, member: discord.Member = None):
  if not member:
    member = ctx.author

  riddle = random.choice(RIDDLES)
  embed = discord.Embed(
      title="🚔 لقد دخلت السجن بنفسك!",
      description=(
          f"يا {member.mention}، لقد تم سجنك! للهروب، يجب أن تحل اللغز التالي"
          f" بسرعة خلال **15 ثانية** فقط:\n\n🧩 **{riddle['q']}**"
      ),
      color=discord.Color.dark_red(),
  )
  await ctx.send(embed=embed)

  def check(m):
    return m.author == member and m.channel == ctx.channel

  try:
    msg = await bot.wait_for("message", timeout=15.0, check=check)
    if msg.content.strip().lower() in [ans.lower() for ans in riddle["a"]]:
      add_balance(member.id, 40)
      await ctx.send(
          f"🔓 **نجحت في الهروب!** أجب لغز السجن بنجاح وتمت مكافأتك بـ 40"
          f" طولار يا {member.mention}!"‚allowed_mentions=discord.AllowedMentions(users=False)
          )
      
    else:
      await ctx.send(
          f"🔒 **إجابة خاطئة!** {member.mention} يبقى في السجن! الإجابة كانت:"
          f" **{riddle['a'][0]}**."‚allowed_mentions=discord.AllowedMentions(users=False)
      
  except asyncio.TimeoutError:
    await ctx.send(
        f"🔒 **انتهى الوقت!** {member.mention} لم يجب خلال 15 ثانية ويبقى"
        " محبوساً!"‚allowed_mentions=discord.AllowedMentions(users=False)
        )
   


@bot.command(name="طولاري")
async def balance_command(ctx, member: discord.Member = None):
  target = member or ctx.author
  bal = get_balance(target.id)
  await ctx.send(f"💳 رصيد {target.mention} الحالي هو: **{bal}** طولار."‚allowed_mentions=discord.AllowedMentions(users=False)
  
  )

  
  # أداة لتحديد روم معين لكل أمر
def in_channel(channel_id: int):
    async def predicate(ctx):
        if ctx.channel.id != channel_id:
            # يرسل رسالة تحتوي على رابط/منشن الروم المخصص وتنحذف بعد 3 ثوانٍ
            await ctx.send(
                f"❌ هذا الأمر يعمل فقط في الروم المخصص: <#{channel_id}>",
                delete_after=3,
            )
            return False
        return True

    return commands.check(predicate)
  
  # --- أمر إضافة رصيد (خاص برتبة الاونر عبر الـ ID) ---
OWNER_ROLE_ID =1515396547528102131 # أيدي رتبة الاونر


@bot.command(name="اضافة")
@in_channel(AVATAR_CHANNEL_ID)
@commands.has_role(OWNER_ROLE_ID)  # التحقق بآيدي الرتبة
async def add_money(ctx, member: discord.Member, amount: int):
    if amount <= 0:
        await ctx.send("❌ يرجى إدخال مبلغ صحيح أكبر من 0.")
        return

    add_balance(member.id, amount)
    await ctx.send(
        f"✅ تم إضافة **{amount}** طولار إلى حساب {member.mention} بنجاح!\n"
        f"💳 رصيده الجديد: **{get_balance(member.id)}** طولار.", allowed_mentions=discord.AllowedMentions.none()
    )


# التعامل مع الأخطاء الخاصة بالأمر
@add_money.error
async def add_money_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("❌ هذا الأمر مخصص لصاحب رتبة الاونر فقط!")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(
            "⚠️ **طريقة الاستخدام الصحيحة:**\n"
            "`!اضافة @العضو المبلغ`\n"
            "مثال: `!اضافة @User 500`"
        )
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❌ يرجى منشن عضو صحيح وكتابة المبلغ بالأرقام.")
        
    
  # --- أمر معرفة الآيدي (للأعضاء والرتب) ---
@bot.command(name="ايدي")
async def get_id(
    ctx,
    target: typing.Union[
        discord.TextChannel, discord.Member, discord.Role, str
    ] = None,
):
    # 1. إذا لم يُرسل المستخدم أي شيء (عرض آيدي صاحب الأمر)
    if not target:
        await ctx.send(f"🆔 الآيدي الخاص بك: `{ctx.author.id}`")
        return

    # 2. إذا تم منشن رتبة
    if ctx.message.role_mentions:
        role = ctx.message.role_mentions[0]
        await ctx.send(f"🆔 آيدي الرتبة **{role.name}**: `{role.id}`")
        return
        
        if isinstance(target, discord.TextChannel):
        await ctx.send(f"🆔 آيدي الروم {target.mention}: `{target.id}`")
        return

    # 3. إذا تم منشن عضو
    if ctx.message.mentions:
        member = ctx.message.mentions[0]
        await ctx.send(f"🆔 آيدي العضو {member.mention}: `{member.id}`")
        return

    # 4. إذا قام بإدخال اسم بدون منشن صريح (محاولة البحث)
    member = discord.utils.find(lambda m: m.name == target or m.display_name == target, ctx.guild.members)
    if member:
        await ctx.send(f"🆔 آيدي العضو {member.mention}: `{member.id}`")
        return

    role = discord.utils.find(lambda r: r.name == target, ctx.guild.roles)
    if role:
        await ctx.send(f"🆔 آيدي الرتبة **{role.name}**: `{role.id}`")
        return

    await ctx.send("❌ لم يتم العثور على عضو أو رتبة بهذا المنشن/الاسم.")
    
    # --- أمر مسح الرسائل (خاص برتبة الاونر عبر الـ ID) ---
OWNER_ROLE_ID =1515396547528102131 # أيدي رتبة الاونر


@bot.command(name="مسح", aliases=["clear", "مسح_الرسائل"])
@commands.has_role(OWNER_ROLE_ID)
async def clear_messages(ctx, amount: int = None):
    if amount is None or amount <= 0:
        await ctx.send(
            "⚠️ يرجى تحديد عدد الرسائل المراد مسحها.\nمثال: `!مسح 10`",
            delete_after=2,
        )
        return

    # مسح الرسائل (مع إضافة 1 لحذف رسالة الأمر نفسه)
    deleted = await ctx.channel.purge(limit=amount + 1)

    # إرسال رسالة تأكيد وحذفها بعد 2 ثوانٍ
    await ctx.send(
        f"🧹 تم مسح **{len(deleted) - 1}** رسالة بنجاح!", delete_after=1
    )


# التعامل مع الأخطاء الخاصة بأمر المسح
@clear_messages.error
async def clear_messages_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send(
            "❌ هذا الأمر مخصص  للـ اونر فقط!", delete_after=2
        )
    elif isinstance(error, commands.BadArgument):
        await ctx.send(
            "❌ يرجى كتابة عدد الرسائل بالأرقام فقط (مثال: `!مسح 5`).",
            delete_after=1,
        )
    elif isinstance(error, commands.BotMissingPermissions):
        await ctx.send(
            "❌ البوت لا يملك صلاحية `Manage Messages` (إدارة الرسائل) لمسح الشات!"
        )
        
        # --- أمر الأفتار (صورة فقط بحجم كبير) ---
@bot.command(name="افتار",
@in_channel(1515396548392128671)
 aliases=["avatar", "افتاري"])
async def show_avatar(ctx, member: discord.Member = None):
    target = member or ctx.author
    avatar_url = target.display_avatar.url

    # إرسال الصورة فقط داخل إمبيد بدون أي عنوان أو نصوص
    embed = discord.Embed(color=discord.Color.dark_theme())
    embed.set_image(url=avatar_url)

    await ctx.send(embed=embed)


# --- أمر البنر (بنر فقط بحجم كبير) ---
@bot.command(name="بنر",
@in_channel(1515396548392128671)
 aliases=["banner", "بنري"])
async def show_banner(ctx, member: discord.Member = None):
    target = member or ctx.author

    # جلب بيانات العضو الكاملة للحصول على البنر
    user = await bot.fetch_user(target.id)

    if not user.banner:
        await ctx.send("❌ هذا الحساب لا يملك بنر!", delete_after=2)
        return

    banner_url = user.banner.url

    # إرسال البنر فقط داخل إمبيد بدون أي كتابة
    embed = discord.Embed(color=discord.Color.dark_theme())
    embed.set_image(url=banner_url)

    await ctx.send(embed=embed)


# التعامل مع أخطاء المنشن
@show_avatar.error
@show_banner.error
async def avatar_banner_error(ctx, error):
    if isinstance(error, commands.BadArgument):
        await ctx.send("❌ لم يتم العثور على هذا العضو أو البوت!", delete_after=2)


# --- 7. أحداث التشغيل ---
@bot.event
async def on_ready():
    print(f"✅ تم تسجيل الدخول باسم: {bot.user.name}")
    await load_data_from_github()
    

bot.run(os.environ.get('DISCORD_TOKEN'))