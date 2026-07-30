import re
import asyncio
import base64
import datetime
import io
import json
import os
import random
from threading import Thread
import typing

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask
from PIL import Image, ImageDraw, ImageFont
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
bot = commands.Bot(command_prefix=".", intents=intents)

GITHUB_TOKEN = "ghp_2v2m8IXKyh0YQxZRrQnjbl08gmEH5C4E7P3b"
REPO_OWNER = "true561290-boop"
REPO_NAME = "my_bot"
FILE_PATH = "user_balances.json"

LEVEL_50_ROLE_ID = 1515396547473309712
AVATAR_CHANNEL_ID = 1515396548392128671
OWNER_ROLE_ID = 1515396547528102131

BACKGROUND_IMAGE_URL = "https://i.ibb.co/6R2N29S/vintage-paper-bg.png"

FONT_PATH = "arabic_font.ttf"


def ensure_arabic_font():
  if not os.path.exists(FONT_PATH):
    font_url = "https://github.com/google/fonts/raw/main/ofl/amiri/Amiri-Bold.ttf"
    try:
      r = requests.get(font_url)
      if r.status_code == 200:
        with open(FONT_PATH, "wb") as f:
          f.write(r.content)
        print("✅ تم تحميل الخط العربي بنجاح!")
    except Exception as e:
      print(f"❌ فشل تنزيل الخط العربي: {e}")


ensure_arabic_font()


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


# --- 3. المتجر التفاعلي ورسم الصور باستخدام خلفية الورقة القديمة ---

SHOP_VIP_ROLES = {
    "lvl_25": {
        "name": "Level 25 (إرسال صور)",
        "price": 1000,
        "id": 1515396547473309710,
    },
    "lvl_35": {
        "name": "Level 35 (إرسال صور وستيكرات من سيرفر آخر)",
        "price": 2000,
        "id": 1515396547473309711,
    },
    "lvl_50": {
        "name": "Level 50 (كل ما سبق + ميزة الخط الكبير)",
        "price": 3500,
        "id": 1515396547473309712,
    },
    "founder": {
        "name": "⚡ الزنجي المؤسس",
        "price": 5000,
        "id": 1527739093163708548,
    },
}

# تم تعديل جميع أسعار الألوان إلى 500
SHOP_COLOR_ROLES = {
    "c_red": {"name": "أحمر", "price": 500, "id": 1515396547536355469},
    "c_blue": {"name": "أزرق", "price": 500, "id": 1515396547528102135},
    "c_green": {"name": "أخضر", "price": 500, "id": 1515396547528102136},
    "c_purple": {"name": "بنفسجي", "price": 500, "id": 1515396547528102134},
    "c_yellow": {"name": "أصفر", "price": 500, "id": 1515396547528102137},
    "c_gray": {"name": "رمادي", "price": 500, "id": 1515487581138190376},
    "c_skin": {"name": "Skin", "price": 500, "id": 1515480359553335441},
}


def make_card_with_text(unused_url, title_text, main_text, sub_text=""):
  width, height = 800, 550

  if os.path.exists("bg_paper.png"):
    try:
      img = Image.open("bg_paper.png").convert("RGBA").resize((width, height))
    except Exception as e:
      print(f"خطأ في قراءة الصورة المحلية: {e}")
      img = Image.new("RGBA", (width, height), color=(235, 220, 195, 255))
  else:
    try:
      res = requests.get(
          "https://raw.githubusercontent.com/true561290-boop/my_bot/main/bg_paper.png"
      )
      if res.status_code == 200:
        img = (
            Image.open(io.BytesIO(res.content))
            .convert("RGBA")
            .resize((width, height))
        )
      else:
        img = Image.new("RGBA", (width, height), color=(235, 220, 195, 255))
    except Exception as e:
      print(f"لم يتم جلب الصورة، الاعتماد على لون احتياطي: {e}")
      img = Image.new("RGBA", (width, height), color=(235, 220, 195, 255))

  draw = ImageDraw.Draw(img)

  font_large = ImageFont.load_default()
  font_med = ImageFont.load_default()
  font_sub = ImageFont.load_default()

  if os.path.exists(FONT_PATH):
    try:
      font_large = ImageFont.truetype(FONT_PATH, 44)
      font_med = ImageFont.truetype(FONT_PATH, 34)
      font_sub = ImageFont.truetype(FONT_PATH, 22)
    except Exception as e:
      print(f"Font error: {e}")

  TEXT_COLOR_TITLE = (80, 20, 10, 255)
  TEXT_COLOR_MAIN = (30, 20, 10, 255)
  TEXT_COLOR_SUB = (90, 60, 40, 255)

  if title_text:
    draw.text(
        (width // 2, 130),
        title_text,
        font=font_large,
        fill=TEXT_COLOR_TITLE,
        anchor="mm",
    )
    draw.line(
        [(width // 2 - 130, 165), (width // 2 + 130, 165)],
        fill=(120, 70, 40, 255),
        width=2,
    )

  if main_text:
    draw.text(
        (width // 2, 260),
        main_text,
        font=font_med,
        fill=TEXT_COLOR_MAIN,
        anchor="mm",
    )

  if sub_text:
    draw.text(
        (width // 2, 380),
        sub_text,
        font=font_sub,
        fill=TEXT_COLOR_SUB,
        anchor="mm",
    )

  buf = io.BytesIO()
  img.save(buf, format="PNG")
  buf.seek(0)
  return buf


class TimedSubView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=60)
    self.message = None

  async def on_timeout(self):
    for item in self.children:
      item.disabled = True
    if self.message:
      try:
        await self.message.edit(view=self)
      except Exception:
        pass


class BackToMainButton(discord.ui.Button):

  def __init__(self):
    super().__init__(
        label="رجوع للمتجر", style=discord.ButtonStyle.secondary, emoji="🔙"
    )

  async def callback(self, interaction: discord.Interaction):
    img_buf = make_card_with_text(
        None,
        "المتجر الملكي",
        "خزانة البلاط ومراسيمه",
        "اختر القسم للتنقل والشراء",
    )
    file = discord.File(fp=img_buf, filename="shop.png")
    view = MainShopView()
    await interaction.response.edit_message(attachments=[file], view=view)
    view.message = interaction.message


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
        placeholder="اختر لوناً للشراء...",
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
          f"⚠️ أنت تملك رتبة **{role.name}** بالفعل", ephemeral=True
      )
      return

    if get_balance(user.id) < item["price"]:
      await interaction.response.send_message(
          f"❌ رصيدك غير كافٍ، تحتاج إلى **{item['price']}** طولار.",
          ephemeral=True,
      )
      return

    all_color_ids = [c["id"] for c in SHOP_COLOR_ROLES.values()]
    roles_to_remove = [r for r in user.roles if r.id in all_color_ids]
    if roles_to_remove:
      await user.remove_roles(*roles_to_remove)

    remove_balance(user.id, item["price"])
    await user.add_roles(role)

    for child in self.view.children:
      child.disabled = True
    await interaction.message.edit(view=self.view)

    await interaction.response.send_message(
        f" **تم الشراء بنجاح،** تم منحك رتبة **{role.name}** بمبلغ"
        f" **{item['price']}** طولار.\n*(تم إغلاق المتجر)*",
        ephemeral=True,
    )


# --- 4. نظام الرد التلقائي + تكبير الإيموجي/الستيكر + منع الخط الكبير (#) ---
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # =============================================================
    # أ) ميزة تكبير الإيموجي والستيكر في روم الأفاتار فقط
    # =============================================================
    if message.channel.id == AVATAR_CHANNEL_ID:
        # 1. التكبير في حالة الستيكرات (Stickers)
        if message.stickers:
            sticker = message.stickers[0]
            await message.channel.send(sticker.url)
            return

        # 2. التكبير في حالة الإيموجيات المخصصة (Custom Emojis)
        emoji_match = re.search(r'<(a)?:(\w+):(\d+)>', message.content)
        if emoji_match:
            is_animated = emoji_match.group(1)
            emoji_id = emoji_match.group(3)
            extension = "gif" if is_animated else "png"
            emoji_url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{extension}?size=1024"
            await message.channel.send(emoji_url)
            return

    # تنظيف النص وإزالة النقطة والمسافات الزائدة من البداية
    raw_content = message.content.strip()
    clean_content = raw_content[1:].strip() if raw_content.startswith(".") else raw_content

    # =============================================================
    # ب) قائمة الكلمات والردود التلقائية
    # =============================================================
    auto_responses = {
        "السلام عليكم": f"وعليكم السلام ورحمة الله وبركاته {message.author.mention}",
        "السلام عليكم ورحمة الله وبركاته": f"وعليكم السلام ورحمة الله وبركاته {message.author.mention}",
        "سلام عليكم": f"وعليكم السلام ورحمة الله وبركاته {message.author.mention}",
        "باك": f"ولكم باك {message.author.mention}"
    }

    user_msg = clean_content if clean_content in auto_responses else raw_content
    if user_msg in auto_responses:
        await message.channel.send(
            auto_responses[user_msg],
            allowed_mentions=discord.AllowedMentions(users=False)
        )
        return

    # =============================================================
    # ج) نظام منع الخط الكبير (#) بدون رتبة Level 50
    # =============================================================
    if message.content.startswith("# "):
        level_50_role = message.guild.get_role(LEVEL_50_ROLE_ID)
        if level_50_role and level_50_role not in message.author.roles:
            try:
                await message.delete()
                warning = await message.channel.send(
                    f"⚠️ يا {message.author.mention}، لا يمكنك الكتابة بخط كبير `#` لأنك لا تملك رتبة **Level 50** يمكنك شراؤها من المتجر.",
                    allowed_mentions=discord.AllowedMentions(users=False)
                )
                await asyncio.sleep(2)
                await warning.delete()
                return
            except Exception as e:
                print(f"خطأ أثناء حذف الرسالة: {e}")

    # =============================================================
    # د) معالجة باقي أوامر البوت
    # =============================================================
    await bot.process_commands(message)


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
        placeholder="اختر رتبة للشراء...",
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
          f"⚠️ أنت تملك رتبة **{role.name}** بالفعل", ephemeral=True
      )
      return

    if get_balance(user.id) < item["price"]:
      await interaction.response.send_message(
          f"❌ رصيدك غير كاف، تحتاج إلى **{item['price']}** طولار.",
          ephemeral=True,
      )
      return

    remove_balance(user.id, item["price"])
    await user.add_roles(role)

    for child in self.view.children:
      child.disabled = True
    await interaction.message.edit(view=self.view)

    await interaction.response.send_message(
        f" **تم الشراء بنجاح،** تم منحك رتبة **{role.name}** بمبلغ"
        f" **{item['price']}** طولار.\n*(تم إغلاق المتجر)*",
        ephemeral=True,
    )


class MainCategorySelect(discord.ui.Select):

  def __init__(self):
    options = [
        discord.SelectOption(
            label="الرتب", value="cat_vip", description="عرض الرتب والخصائص"
        ),
        discord.SelectOption(
            label="ألوان الأسماء",
            value="cat_colors",
            description="عرض قائمة الألوان ",
        ),
    ]
    super().__init__(
        placeholder="تصفح أقسام المتجر...",
        min_values=1,
        max_values=1,
        options=options,
    )

  async def callback(self, interaction: discord.Interaction):
    if self.values[0] == "cat_vip":
      view = TimedSubView()
      view.add_item(VIPSelect())
      view.add_item(BackToMainButton())
      img_buf = make_card_with_text(None, "قسم الرتب", "الرتب المتاحة")
      file = discord.File(fp=img_buf, filename="vip.png")
      await interaction.response.edit_message(attachments=[file], view=view)
      view.message = interaction.message

    elif self.values[0] == "cat_colors":
      view = TimedSubView()
      view.add_item(ColorSelect())
      view.add_item(BackToMainButton())
      img_buf = make_card_with_text(
          None, "لون ثابت", "اختر مرسومك من القائمة بالأسفل"
      )
      file = discord.File(fp=img_buf, filename="colors.png")
      await interaction.response.edit_message(attachments=[file], view=view)
      view.message = interaction.message


class MainShopView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=60)
    self.add_item(MainCategorySelect())
    self.message = None

  async def on_timeout(self):
    for item in self.children:
      item.disabled = True
    if self.message:
      try:
        await self.message.edit(view=self)
      except Exception:
        pass


@bot.command(name="متجر", aliases=["اقتصاد"])
async def shop_command(ctx):
  img_buf = make_card_with_text(
      None,
      "المتجر الملكي",
      "خزانة البلاط ومراسيمه",
      "اختر القسم للتنقل والشراء",
  )
  file = discord.File(fp=img_buf, filename="shop.png")
  view = MainShopView()
  msg = await ctx.send(file=file, view=view)
  view.message = msg


# --- 5. نظام الألعاب والأسئلة ---

QUESTIONS = [
    {"q": "ما هي عاصمة أستراليا؟", "a": ["كانبرا", "كانبيرا"]},
    {"q": "ما هي أصغر دولة في العالم من حيث المساحة؟", "a": ["الفاتيكان"]},
    {"q": "ما هو العنصر الكيميائي الذي رمزه 'Fe'؟", "a": ["الحديد", "حديد"]},
    {"q": "ما هي أكبر صحراء في العالم؟", "a": ["الصحراء الكبرى"]},
    {"q": "في أي عام وقعت معركة حطين؟", "a": ["1187", "١١٨٧", "1187m"]},
    {"q": "ما هو أطول نهر في العالم؟", "a": ["النيل", "نهر النيل"]},
    {"q": "ما هي عاصمة كندا؟", "a": ["أوتاوا", "اوتاوا"]},
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
    {"q": "كم عدد قلوب الأخطبوط؟", "a": ["3", "ثلاثة", "٣"]},
    {
        "q": "من هو مخترع المصباح الكهربائي؟",
        "a": ["توماس أديسون", "اديسون", "أديسون"],
    },
    {"q": "ما هي أصغر عظمة في جسم الإنسان؟", "a": ["الركاب", "عظمة الركاب"]},
    {"q": "ما هي عاصمة فرنسا؟", "a": ["باريس"]},
    {"q": "في أي قارة تقع مصر؟", "a": ["أفريقيا", "افريقيا"]},
    {
        "q": "ما هو أكبر محيط في العالم؟",
        "a": ["المحيط الهادي", "المحيط الهادئ"],
    },
    {"q": "كم عدد أضلاع المثلث؟", "a": ["3", "ثلاثة", "٣"]},
    {"q": "ما هو المكون الرئيسي للزجاج؟", "a": ["الرمل", "الريمال"]},
    {"q": "ما هي عاصمة ألمانيا؟", "a": ["برلين"]},
    {
        "q": "من هو الشاعر الملقب بـ 'أمير الشعراء'؟",
        "a": ["أحمد شوقي", "احمد شوقي"],
    },
    {"q": "ما هي أكبر عضلة في جسم الإنسان؟", "a": ["عضلة الأرداف", "الأرداف"]},
    {"q": "ما هي عاصمة روسيا؟", "a": ["موسكو"]},
    {"q": "كم عدد العظام في جسم الإنسان البالغ؟", "a": ["206", "٢٠٦"]},
    {
        "q": "ما هو المكون الأساسي للشمس؟",
        "a": ["الهيدروجين", "غاز الهيدروجين"],
    },
    {"q": "ما هي عاصمة إيطاليا؟", "a": ["روما"]},
    {"q": "في أي مدينة توجد منظمة اليونسكو؟", "a": ["باريس"]},
    {"q": "ما هي أكبر بحيرة في العالم؟", "a": ["بحر قزوين"]},
    {
        "q": "من هو عالم الفيزياء صاحب نظريّة النسبية؟",
        "a": ["أينشتاين", "اينشتاين"],
    },
    {"q": "ما هي عاصمة إسبانيا؟", "a": ["مدريد"]},
    {"q": "ما هو الحيوان الذي يُسمى 'سفينة الصحراء'؟", "a": ["الجمل", "جمل"]},
    {
        "q": "ما هي المادة الأكثرصلابة في طبيعة الأرض؟",
        "a": ["الألماس", "الماس"],
    },
    {
        "q": "ما هي الدولة المفترض بها الموطن الأصلي للبيتزا؟",
        "a": ["إيطاليا", "ايطاليا"],
    },
    {"q": "ما هي عاصمة تركيا؟", "a": ["أنقرة", "انقرة"]},
    {"q": "كم عدد الألوان في قوس قزح؟", "a": ["7", "سبعة", "٧"]},
    {"q": "ما هي أطول سلسة جبلية في العالم؟", "a": ["الأنديز", "جبال الأنديز"]},
    {"q": "ما هي عاصمة الأرجنتين؟", "a": ["بوينس آيرس", "بوينس ايرس"]},
    {
        "q": "ما هو الغاز الذي يستعمله النبات في البناء الضوئي؟",
        "a": ["ثاني أكسيد الكربون", "ثاني اكسيد الكربون"],
    },
    {"q": "ما هي عاصمة المغرب؟", "a": ["الرباط"]},
    {"q": "ما هي السورة التي تُسمى 'قلب القرآن'؟", "a": ["يس", "يسن"]},
    {
        "q": "ما هو العلم الذي يهتم بدراسة الأحافير والحيوانات القديمة؟",
        "a": ["الفرع الأحفوري", "الإحاثة", "علم الأحافير"],
    },
    {"q": "ما هي عاصمة السويد؟", "a": ["ستوكهولم"]},
    {"q": "ما هو اسم أعمق نقطة في محيطات الأرض؟", "a": ["خندق ماريانا"]},
    {"q": "ما هي عاصمة مصر؟", "a": ["القاهرة"]},
    {"q": "كم طابق يوجد في برج خليفة تقريباً؟", "a": ["163", "١٦٣"]},
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
    {"q": "ما هي الدولة التي تمتلك أطول خط ساحلي في العالم؟", "a": ["كندا"]},
    {"q": "ما هي عاصمة الأردن؟", "a": ["عمان", "عمّان"]},
    {"q": "ما هي السورة التي لا تبدأ بالبسملة؟", "a": ["التوبة", "سورة التوبة"]},
    {"q": "ما هو اسم أطول بناء في العالم حالياً؟", "a": ["برج خليفة"]},
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
    {"q": "ما هو أطول نهر في أوروبا؟", "a": ["الفولغا", "نهر الفولغا"]},
    {"q": "ما هي عاصمة الهند؟", "a": ["نيودلهي", "دلهي"]},
    {"q": "من هو مؤسس علم الجبر؟", "a": ["الخوارزمي", "الخوارزمي حاسب"]},
    {"q": "ما هي عاصمة النرويج؟", "a": ["أوسلو", "وسلو"]},
    {"q": "ما هو اسم الكوكب الأقرب إلى الأرض؟", "a": ["الزهرة", "كوكب الزهرة"]},
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
    {"q": "ما هي أسرع سمكة في البحر؟", "a": ["سمكة الشراع", "الشراع"]},
    {"q": "ما هي عاصمة بلجيكا؟", "a": ["بروكسل"]},
    {"q": "ما هي الدولة العربية التي يمر بها خط الاستواء؟", "a": ["الصومال"]},
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
    {"q": "شيء كلما أخذت منه كبر، فما هو؟", "a": ["الحفرة", "حفرة"]},
    {
        "q": "يمشي بلا أرجل ويدخل الأذنين فقط، فما هو؟",
        "a": ["الصوت", "صوت"],
    },
    {"q": "ما هو الشيء الذي يكتب ولا يقرأ؟", "a": ["القلم", "قلم"]},
    {"q": "ما هو البيت الذي لا توجد فيه أبواب ولا نوافذ؟", "a": ["بيت الشعر"]},
    {"q": "ما هو الشيء الذي كلما زاد نقص؟", "a": ["العمر", "عمر"]},
    {
        "q": "ما هو الشيء الذي يمكنك إمساكه بدون لمسه؟",
        "a": ["الأعصاب", "أعصابك"],
    },
    {
        "q": "ما هو القفص الذي لا يحبس فيه طائر أو حيوان؟",
        "a": ["القفص الصدري"],
    },
    {"q": "شيء يحترق لكي يضيء للآخرين؟", "a": ["الشمعة", "شمعة"]},
    {"q": "يمشي ويقف وليس له أرجل؟", "a": ["الظلال", "الظل", "الساعة"]},
    {"q": "ما هو الشيء الذي يبرد بالحرارة؟", "a": ["الفلفل", "البيض"]},
    {
        "q": "أنا ذو ثقوب عديدة ولكني أحتفظ بالماء، فمن أنا؟",
        "a": ["الإسفنج", "اسفنج"],
    },
    {"q": "ما هو الشيء الذي إذا صببت عليه الماء لا يبتل؟", "a": ["الظل", "ظلك"]},
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
    {"q": "ما هو الشيء الذي ينبض بلا قلب؟", "a": ["الساعة", "ساعة"]},
    {"q": "ما هو الباب الذي لا يمكن فتحه؟", "a": ["الباب المفتوح"]},
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
    {"q": "له أسنان كثيرة ولكنه لا يعض، فما هو؟", "a": ["المشط", "مشط"]},
    {
        "q": "يحبها الجميع ويعطونها للآخرين ولكن لا أحد يستطيع الاحتفاظ بها؟",
        "a": ["الكلمة", "الوعد"],
    },
    {
        "q": "ما هو الشيء الذي تسمعه ولا تراه، وإذا رأيته لا تسمعه؟",
        "a": ["الطلقة النارية", "الرعد"],
    },
    {"q": "شيء يسير في السماء ويستريح في الأرض؟", "a": ["المطر", "مطر"]},
    {
        "q": "تطير بدون أجنحة وتبكي بدون عيون، فما هي؟",
        "a": ["السحابة", "السحاب"],
    },
    {
        "q": "ما هو الشيء الذي يحتوي على المدن ولكن ليس به بيوت؟",
        "a": ["الخريطة"],
    },
    {"q": "شيء إذا قطعت رأسه طار؟", "a": ["قطار", "القطار"]},
    {"q": "ما هي التي تملك عيوناً ولا ترى؟", "a": ["الإبرة", "إبرة"]},
    {"q": "له أوراق كثيرة ولكنه ليس بشجرة؟", "a": ["الكتاب", "كتاب"]},
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
    {"q": "ما هو الشيء الذي ينكسر بمجرد تسميته؟", "a": ["الصمت"]},
    {"q": "يتحدث كل لغات العالم بدون أن يتكلم؟", "a": ["الصدى"]},
    {
        "q": "ما هو الشيء الذي تصنعه ولكن لا تراه؟",
        "a": ["الضوضاء", "الرقام"],
    },
    {"q": "إذا أطعمته ينمو، وإذا سقيته يموت؟", "a": ["النار"]},
    {"q": "يمتلك رقبة ولكن ليس له رأس؟", "a": ["الزجاجة", "قميص"]},
    {
        "q": "ما هو الذي يستطيع الضوء اختراقه والماء المضيء فيه؟",
        "a": ["الزجاج"],
    },
    {"q": "شيء بينك وبين السماء، فما هو؟", "a": ["الكاف", "حرف الكاف"]},
    {
        "q": "ما هو الشارع الذي يمشي فيه الناس بلا أقدام؟",
        "a": ["شارع الخريطة"],
    },
    {
        "q": "ما هو العضو الوحيد الذي لا يصله الدم؟",
        "a": ["قرنية العين", "القرنية"],
    },
    {"q": "ما هي الشيء الذي يولد كبيراً ويموت صغيراً؟", "a": ["الشمعة"]},
    {"q": "يوجد في منتصف باريس فما هو؟", "a": ["حرف الراء"]},
    {
        "q": "ما هو الشيء الذي إذا أكلته كله استفدت منه، وإذا أكلت نصفه مِت؟",
        "a": ["سمسم"],
    },
    {"q": "ما هو الذي يملك عين واحدة ولكنه لا يرى بها؟", "a": ["الإبرة"]},
    {"q": "ما هو الشيء الذي إذا نام لا يستيقظ؟", "a": ["الرماد"]},
    {"q": "له يد ولكن لا يستطيع التصفيق؟", "a": ["الساعة"]},
    {"q": "ما هو الشيء الذي يصعد ولا ينزل أبداً؟", "a": ["العمر"]},
    {"q": "أخت خالتك وليست خالتك فمن تكون؟", "a": ["أمك", "امي"]},
    {"q": "يمشي بدون قدمين ولا يدخل إلا بالأذنين؟", "a": ["الصوت"]},
    {"q": "تأكل منه ولكن لا يمكنك أن تأكله؟", "a": ["الصحن", "الطبق"]},
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
    {"q": "ما هو الشيء الذي لا يتكلم وإذا جاع كذب؟", "a": ["الساعة"]},
    {"q": "أين يقع البحر الذي ليس به ماء؟", "a": ["على الخريطة"]},
    {
        "q": "يمتلك كل العيون ولكنه لا يرى شيئاً؟",
        "a": ["شاطئ البطاطس", "البطاطس"],
    },
    {"q": "ما هو الشهر الذي فيه 28 يوماً؟", "a": ["كل الشهور", "جميع الشهور"]},
    {"q": "ما هو أصلح شيء للرؤية في الظلام التام؟", "a": ["لا شيء"]},
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
    {"q": "ما هو القادم الذي لا يصل أبداً؟", "a": ["غداً", "الغد"]},
    {
        "q": "أنا بداية النهاية ونهاية الزمان والمكان فمن أنا؟",
        "a": ["حرف النون"],
    },
    {"q": "ما هو الشيء الذي إذا غسلت به يظل متسخاً؟", "a": ["الماء"]},
    {
        "q": "ما هو الشيء الذي يطير بدون أجنحة ويدخل العيون بدون استئذان؟",
        "a": ["الغبار"],
    },
    {"q": "يتحرك باستمرار وبلا توقف ولكن لا يتعب؟", "a": ["القلب"]},
    {
        "q": "ما هي المادة التي يفرزها الجسم وتصلح لبناء العظام؟",
        "a": ["الكالسيوم"],
    },
    {"q": "ما هو الشيء الذي ينقص كلما أخذت منه أكثر؟", "a": ["الحفرة"]},
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
    {"q": "ما هو القماش الذي لا يمكنك ارتداؤه؟", "a": ["قماش العنكبوت"]},
    {"q": "شيء إذا لمسته صرخ؟", "a": ["جرس الباب", "الجرس"]},
    {"q": "ما هو العقرب الذي لا يلذغ؟", "a": ["عقرب الساعة"]},
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
    {"q": "ما هو السلم الذي لا يصعد عليه أحد؟", "a": ["سلم الرواتب"]},
    {"q": "تسير في كل أرجاء الغرفة لكنها لا تتحرك أبداً؟", "a": ["الجدران"]},
    {"q": "تلبس الثوب بالكامل لكنها تظل عارية؟", "a": ["إبرة الخياطة"]},
    {
        "q": "ما هو الشيء الذي يسير بلا أقدام ولا يرجع للخلف أبداً؟",
        "a": ["الوقت", "العمر"],
    },
    {"q": "إذاوضعتني في ماء حار أصبح صلباً؟", "a": ["البيض", "بيضة"]},
    {"q": "ما هو الشيء الذي يحك أذنه بأنفه؟", "a": ["الفيل"]},
    {"q": "ما هو الشيء الذي تحمله ويحملك في نفس الوقت؟", "a": ["الحذاء"]},
]


# --- أمر المسابقة (الأسئلة) ---
@bot.command(name="سؤال", aliases=["quiz", "اسئلة"])
async def quiz_game(ctx, rounds: int = 1):
  if rounds < 1 or rounds > 10:
    await ctx.send(
        "❌ يرجى تحديد عدد جولات بين **1** و **10** فقط", delete_after=3
    )
    return

  for round_num in range(1, rounds + 1):
    q_data = random.choice(QUESTIONS)

    embed = discord.Embed(
        title=f"❓ الجولة {round_num}",
        description=(
            f"يا {ctx.author.mention}، أجب عن السؤال التالي كسباً لـ **40**"
            f" طولار:\n\n❓ **{q_data['q']}**"
        ),
        color=discord.Color.blue(),
    )
    embed.set_footer(text="⏱️ لديك 10 ثوانٍ للإجابة على هذا السؤال")

    await ctx.send(
        embed=embed, allowed_mentions=discord.AllowedMentions(users=False)
    )

    def check(m):
      return m.author == ctx.author and m.channel == ctx.channel

    try:
      msg = await bot.wait_for("message", timeout=10.0, check=check)
      if msg.content.strip().lower() in [ans.lower() for ans in q_data["a"]]:
        add_balance(ctx.author.id, 40)
        await ctx.send(
            f"🎉 **إجابة صحيحة،** تم إضافة 40 طولار إلى حسابك يا"
            f" {ctx.author.mention}",
            allowed_mentions=discord.AllowedMentions(users=False),
        )
      else:
        await ctx.send(
            f"❌ **إجابة خاطئة،** الإجابة الصحيحة هي: **{q_data['a'][0]}**"
        )
    except asyncio.TimeoutError:
      await ctx.send(
          f"⏰ **انتهى الوقت** الإجابة الصحيحة كانت: **{q_data['a'][0]}**"
      )

    if round_num < rounds:
      await asyncio.sleep(1)


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
  await ctx.send(
      embed=embed, allowed_mentions=discord.AllowedMentions(users=False)
  )

  def check(m):
    return m.author == member and m.channel == ctx.channel

  try:
    msg = await bot.wait_for("message", timeout=15.0, check=check)
    if msg.content.strip().lower() in [ans.lower() for ans in riddle["a"]]:
      add_balance(member.id, 40)
      await ctx.send(
          f"🔓 **نجحت في الهروب!** أجب لغز السجن بنجاح وتمت مكافأتك بـ 40"
          f" طولار يا {member.mention}!",
          allowed_mentions=discord.AllowedMentions(users=False),
      )
    else:
      await ctx.send(
          f"🔒 **إجابة خاطئة!** {member.mention} يبقى في السجن! الإجابة كانت:"
          f" **{riddle['a'][0]}**.",
          allowed_mentions=discord.AllowedMentions(users=False),
      )
  except asyncio.TimeoutError:
    await ctx.send(
        f"🔒 **انتهى الوقت!** {member.mention} لم يجب خلال 15 ثانية ويبقى"
        " محبوساً",
        allowed_mentions=discord.AllowedMentions(users=False),
    )


# --- لعبة حجر ورقة مقص ضد البوت بالأزرار ---
class RPSView(discord.ui.View):

  def __init__(self, author):
    super().__init__(timeout=30)
    self.author = author

  async def interaction_check(self, interaction: discord.Interaction) -> bool:
    if interaction.user != self.author:
      await interaction.response.send_message(
          "❌ هذه اللعبة ليست لك، يمكنك بدء لعبتك الخاصة عبر كتابة `.حجر`",
          ephemeral=True,
      )
      return False
    return True

  async def play_game(
      self, interaction: discord.Interaction, player_choice: str
  ):
    bot_choice = random.choice(["حجرة", "ورقة", "مقص"])

    if player_choice == bot_choice:
      result = "🤝 **تعادل!** لم يفز أحد."
      color = discord.Color.gold()
    elif (
        (player_choice == "حجرة" and bot_choice == "مقص")
        or (player_choice == "ورقة" and bot_choice == "حجرة")
        or (player_choice == "مقص" and bot_choice == "ورقة")
    ):
      add_balance(self.author.id, 40)
      result = "🎉 ** فزت على البوت وحصلت على 40 طولار**"
      color = discord.Color.green()
    else:
      result = "**خسرت، فاز البوت عليك **"
      color = discord.Color.red()

    embed = discord.Embed(title="🎮 لعبة حجرة ورقة مقص", color=color)
    embed.add_field(name="اختيارك", value=player_choice, inline=True)
    embed.add_field(name="اختيار البوت", value=bot_choice, inline=True)
    embed.add_field(name="النتيجة", value=result, inline=False)

    for item in self.children:
      item.disabled = True

    await interaction.response.edit_message(embed=embed, view=self)

  @discord.ui.button(label="حجرة 🪨", style=discord.ButtonStyle.primary)
  async def rock_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await self.play_game(interaction, "حجرة")

  @discord.ui.button(label="ورقة 📄", style=discord.ButtonStyle.primary)
  async def paper_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await self.play_game(interaction, "ورقة")

  @discord.ui.button(label="مقص ✂️", style=discord.ButtonStyle.primary)
  async def scissors_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await self.play_game(interaction, "مقص")


@bot.command(name="حجر", aliases=["حجرة", "rps"])
async def rps_game(ctx):
  embed = discord.Embed(
      title="🎮 لعبة حجرة ورقة مقص",
      description=(
          f"يا {ctx.author.mention}، اختر أحد الأزرار بالأسفل للعب ضد البوت\nإذا"
          " فزت ستكسب **40 طولار** 💵"
      ),
      color=discord.Color.blue(),
  )
  view = RPSView(ctx.author)
  await ctx.send(
      embed=embed,
      view=view,
      allowed_mentions=discord.AllowedMentions(users=False),
  )


# --- لعبة توصيل الكرات 4 التفاعلية (Connect 4) ذكاء اصطناعي خارق ---
class Connect4Button(discord.ui.Button):

  def __init__(self, col: int, row_idx: int):
    super().__init__(
        style=discord.ButtonStyle.primary,
        label=str(col + 1),
        custom_id=f"c4_col_{col}",
        row=row_idx,
    )
    self.col = col

  async def callback(self, interaction: discord.Interaction):
    view: Connect4View = self.view

    if interaction.user != view.current_player:
      await interaction.response.send_message("❌ ليس دورك الآن", ephemeral=True)
      return

    placed_row = view.drop_piece(self.col, view.current_emoji)
    if placed_row == -1:
      await interaction.response.send_message(
          " هذا العامود ممتلئ، اختر عاموداً آخر.", ephemeral=True
      )
      return

    if view.check_winner(placed_row, self.col, view.current_emoji):
      winner = view.current_player
      add_balance(winner.id, 60)
      for child in view.children:
        child.disabled = True
      await interaction.response.edit_message(
          content=(
              f"🎉 ** {winner.mention}** لقد فزت في لعبة **توصيل الكرات"
              " 4** وحصلت على **60 طولار**💵\n\n"
              + view.get_board_string()
          ),
          view=view,
      )
      view.stop()
      return

    if view.is_board_full():
      for child in view.children:
        child.disabled = True
      await interaction.response.edit_message(
          content=(
              "🤝 **تعادل** امتلأت اللوحة دون فائز.\n\n"
              + view.get_board_string()
          ),
          view=view,
      )
      view.stop()
      return

    if not view.is_vs_bot:
      view.current_player = (
          view.player2
          if view.current_player == view.player1
          else view.player1
      )
      view.current_emoji = "🟡" if view.current_emoji == "🔴" else "🔴"
      await interaction.response.edit_message(
          content=(
              f" **لعبة توصيل الكرات 4**\nدور: {view.current_player.mention}"
              f" ({view.current_emoji})\nالجائزة: **60 طولار** للفائز\n\n"
              + view.get_board_string()
          ),
          view=view,
      )
    else:
      bot_col, bot_row = view.bot_move()
      if bot_row != -1 and view.check_winner(bot_row, bot_col, "🟡"):
        for child in view.children:
          child.disabled = True
        await interaction.response.edit_message(
            content=(
                f"🤖 ** لعب البوت رقم {bot_col + 1} وفاز في توصيل الكرات"
                " 4**\n\n"
                + view.get_board_string()
            ),
            view=view,
        )
        view.stop()
        return

      if view.is_board_full():
        for child in view.children:
          child.disabled = True
        await interaction.response.edit_message(
            content=(
                " **تعادل** امتلأت اللوحة دون فائز.\n\n"
                + view.get_board_string()
            ),
            view=view,
        )
        view.stop()
        return

      await interaction.response.edit_message(
          content=(
              f" **لعبة توصيل الكرات 4** \nلعب البوت رقم {bot_col + 1} حان"
              f" دورك: {view.player1.mention} (🔴)\n\n"
              + view.get_board_string()
          ),
          view=view,
      )


class Connect4View(discord.ui.View):

  def __init__(self, player1: discord.User, player2: discord.User = None):
    super().__init__(timeout=60)
    self.player1 = player1
    self.player2 = player2
    self.is_vs_bot = player2 is None
    self.current_player = player1
    self.current_emoji = "🔴"
    self.message = None

    self.rows = 6
    self.cols = 7
    self.board = [["⚪" for _ in range(self.cols)] for _ in range(self.rows)]

    for col in range(self.cols):
      row_idx = 0 if col < 5 else 1
      self.add_item(Connect4Button(col, row_idx))

  async def on_timeout(self):
    for child in self.children:
      child.disabled = True
    if self.message:
      try:
        await self.message.edit(
            content=(
                f"⏰ **انتهت اللعبة لعدم التفاعل خلال دقيقة واحدة**\n\n"
                + self.get_board_string()
            ),
            view=self,
        )
      except Exception:
        pass

  def get_board_string(self) -> str:
    board_str = ""
    for r in range(self.rows):
      board_str += "".join(self.board[r]) + "\n"
    board_str += "1️⃣2️⃣3️⃣4️⃣5️⃣6️⃣7️⃣"
    return board_str

  def drop_piece(self, col: int, emoji: str) -> int:
    for r in range(self.rows - 1, -1, -1):
      if self.board[r][col] == "⚪":
        self.board[r][col] = emoji
        return r
    return -1

  def is_board_full(self) -> bool:
    return all(self.board[0][c] != "⚪" for c in range(self.cols))

  def check_winner(self, r: int, c: int, emoji: str) -> bool:
    count = 0
    for col in range(self.cols):
      if self.board[r][col] == emoji:
        count += 1
        if count >= 4:
          return True
      else:
        count = 0

    count = 0
    for row in range(self.rows):
      if self.board[row][c] == emoji:
        count += 1
        if count >= 4:
          return True
      else:
        count = 0

    for row in range(self.rows - 3):
      for col in range(self.cols - 3):
        if (
            self.board[row][col] == emoji
            and self.board[row + 1][col + 1] == emoji
            and self.board[row + 2][col + 2] == emoji
            and self.board[row + 3][col + 3] == emoji
        ):
          return True

    for row in range(3, self.rows):
      for col in range(self.cols - 3):
        if (
            self.board[row][col] == emoji
            and self.board[row - 1][col + 1] == emoji
            and self.board[row - 2][col + 2] == emoji
            and self.board[row - 3][col + 3] == emoji
        ):
          return True

    return False

  def score_position(self, piece: str) -> int:
    score = 0
    opp_piece = "🔴" if piece == "🟡" else "🟡"

    center_array = [self.board[r][self.cols // 2] for r in range(self.rows)]
    center_count = center_array.count(piece)
    score += center_count * 4

    def evaluate_window(window, p):
      win_score = 0
      opp_p = "🔴" if p == "🟡" else "🟡"
      if window.count(p) == 4:
        win_score += 10000
      elif window.count(p) == 3 and window.count("⚪") == 1:
        win_score += 100
      elif window.count(p) == 2 and window.count("⚪") == 2:
        win_score += 10

      if window.count(opp_p) == 3 and window.count("⚪") == 1:
        win_score -= 120
      return win_score

    for r in range(self.rows):
      row_array = self.board[r]
      for c in range(self.cols - 3):
        window = row_array[c : c + 4]
        score += evaluate_window(window, piece)

    for c in range(self.cols):
      col_array = [self.board[r][c] for r in range(self.rows)]
      for r in range(self.rows - 3):
        window = col_array[r : r + 4]
        score += evaluate_window(window, piece)

    for r in range(self.rows - 3):
      for c in range(self.cols - 3):
        window = [self.board[r + i][c + i] for i in range(4)]
        score += evaluate_window(window, piece)

    for r in range(3, self.rows):
      for c in range(self.cols - 3):
        window = [self.board[r - i][c + i] for i in range(4)]
        score += evaluate_window(window, piece)

    return score

  def minimax(
      self, depth: int, alpha: int, beta: int, maximizingPlayer: bool
  ) -> tuple:
    valid_cols = [c for c in range(self.cols) if self.board[0][c] == "⚪"]
    is_terminal = self.is_board_full()

    if depth == 0 or is_terminal:
      return None, self.score_position("🟡")

    if maximizingPlayer:
      value = -9999999
      best_col = random.choice(valid_cols)
      for col in valid_cols:
        row = self.drop_piece(col, "🟡")
        if self.check_winner(row, col, "🟡"):
          self.board[row][col] = "⚪"
          return col, 10000000
        _, new_score = self.minimax(depth - 1, alpha, beta, False)
        self.board[row][col] = "⚪"
        if new_score > value:
          value = new_score
          best_col = col
        alpha = max(alpha, value)
        if alpha >= beta:
          break
      return best_col, value
    else:
      value = 9999999
      best_col = random.choice(valid_cols)
      for col in valid_cols:
        row = self.drop_piece(col, "🔴")
        if self.check_winner(row, col, "🔴"):
          self.board[row][col] = "⚪"
          return col, -10000000
        _, new_score = self.minimax(depth - 1, alpha, beta, True)
        self.board[row][col] = "⚪"
        if new_score < value:
          value = new_score
          best_col = col
        beta = min(beta, value)
        if alpha >= beta:
          break
      return best_col, value

  def bot_move(self) -> tuple:
    valid_cols = [c for c in range(self.cols) if self.board[0][c] == "⚪"]
    if not valid_cols:
      return -1, -1

    for col in valid_cols:
      row = self.drop_piece(col, "🟡")
      if self.check_winner(row, col, "🟡"):
        return col, row
      self.board[row][col] = "⚪"

    for col in valid_cols:
      row = self.drop_piece(col, "🔴")
      if self.check_winner(row, col, "🔴"):
        self.board[row][col] = "⚪"
        bot_row = self.drop_piece(col, "🟡")
        return col, bot_row
      self.board[row][col] = "⚪"

    best_col, _ = self.minimax(4, -9999999, 9999999, True)
    if best_col is None or best_col not in valid_cols:
      best_col = random.choice(valid_cols)

    row = self.drop_piece(best_col, "🟡")
    return best_col, row


@bot.command(name="توصيل", aliases=["توصيل4", "connect4", "كرات4", "أربعة"])
async def connect4_game(ctx, opponent: discord.Member = None):
  if opponent and opponent.bot:
    await ctx.send(
        "❌ لا يمكنك تحدي بوت آخر، استخدم الأمر بدون منشن للعب ضد هذا البوت."
    )
    return

  if opponent and opponent == ctx.author:
    await ctx.send("❌ لا يمكنك تحدي نفسك")
    return

  if opponent:
    view = Connect4View(player1=ctx.author, player2=opponent)
    msg = await ctx.send(
        f"**بدأت لعبة توصيل الكرات 4** بين {ctx.author.mention} (🔴) و"
        f" {opponent.mention} (🟡)\nالجائزة: **60 طولار** للفائز\nدور:"
        f" {ctx.author.mention}\n\n"
        + view.get_board_string(),
        view=view,
        allowed_mentions=discord.AllowedMentions(users=False),
    )
    view.message = msg
  else:
    view = Connect4View(player1=ctx.author)
    msg = await ctx.send(
        f"**بدأت لعبة توصيل الكرات 4** بين"
        f" {ctx.author.mention} (🔴) و البوت (🟡)\nالجائزة: **60 طولار**"
        f" للفائز!\nدور: {ctx.author.mention}\n\n"
        + view.get_board_string(),
        view=view,
        allowed_mentions=discord.AllowedMentions(users=False),
    )
    view.message = msg


@bot.command(name="طولاري")
async def balance_command(ctx, member: discord.Member = None):
  target = member or ctx.author
  bal = get_balance(target.id)

  img_buf = make_card_with_text(
      None,
      "خزانة الرصيد",
      f"{bal} طولار",
      f"حفظت الخزانة الملكية رصيدك يا {target.display_name}",
  )
  file = discord.File(fp=img_buf, filename="balance.png")
  await ctx.send(file=file)


def in_channel(channel_id: int):

  async def predicate(ctx):
    if ctx.channel.id != channel_id:
      await ctx.send(
          f"❌ هذا الأمر يعمل فقط في الروم المخصص: <#{channel_id}>",
          delete_after=3,
      )
      return False
    return True

  return commands.check(predicate)


@bot.command(name="ض")
@commands.has_role(OWNER_ROLE_ID)
async def add_money(ctx, member: discord.Member, amount: int):
  if amount <= 0:
    await ctx.send("❌ يرجى إدخال مبلغ صحيح أكبر من 0.")
    return

  add_balance(member.id, amount)
  await ctx.send(
      f" تم إضافة **{amount}** طولار إلى حساب {member.mention} بنجاح\n"
      f" رصيده الجديد: **{get_balance(member.id)}** طولار.",
      allowed_mentions=discord.AllowedMentions.none(),
  )


@add_money.error
async def add_money_error(ctx, error):
  if isinstance(error, commands.MissingRole):
    await ctx.send("❌ هذا الأمر مخصص لصاحب رتبة الاونر فقط")
  elif isinstance(error, commands.MissingRequiredArgument):
    await ctx.send(
        "**طريقة الاستخدام الصحيحة:**\n"
        "`اضافة @العضو المبلغ`\n"
        "مثال: `.اضافة @User 500`"
    )
  elif isinstance(error, commands.BadArgument):
    await ctx.send("❌ يرجى منشن عضو صحيح وكتابة المبلغ بالأرقام.")


# --- أمر تحويل الطولارات ---
@bot.command(name="ت", aliases=["transfer", "pay"])
async def transfer_money(ctx, member: discord.Member = None, amount: int = None):
    if not member or amount is None:
        await ctx.send(" **طريقة الاستخدام الصحيحة:**\n`.تحويل @العضو المبلغ`\nمثال: `.تحويل @User 100`", delete_after=5)
        return

    if member.bot:
        await ctx.send("❌ لا يمكنك تحويل الطولارات للبوتات", delete_after=3)
        return

    if member == ctx.author:
        await ctx.send("❌ لا يمكنك تحويل الطولارات لنفسك", delete_after=3)
        return

    if amount <= 0:
        await ctx.send("❌ يرجى إدخال مبلغ صحيح أكبر من **0**", delete_after=3)
        return

    sender_balance = get_balance(ctx.author.id)
    if sender_balance < amount:
        await ctx.send(f"❌ رصيدك غير كاف رصيدك الحالي هو **{sender_balance}** طولار.", delete_after=5)
        return

    remove_balance(ctx.author.id, amount)
    add_balance(member.id, amount)

    await ctx.send(
        f" **تم التحويل بنجاح**\n"
        f"قمـت بـتحـويـل **{amount}** طولار إلى {member.mention}.\n"
        f" رصيدك المتبقي: **{get_balance(ctx.author.id)}** طولار.",
        allowed_mentions=discord.AllowedMentions(users=False)
    )

@transfer_money.error
async def transfer_money_error(ctx, error):
    if isinstance(error, commands.BadArgument):
        await ctx.send("❌ يرجى منشن عضو صحيح وكتابة المبلغ بالأرقام.", delete_after=3)


@bot.command(name="ايدي")
async def get_id(
    ctx,
    target: typing.Union[
        discord.TextChannel, discord.Member, discord.Role, str
    ] = None,
):
  if not target:
    await ctx.send(f"🆔 الآيدي الخاص بك: `{ctx.author.id}`")
    return

  if ctx.message.role_mentions:
    role = ctx.message.role_mentions[0]
    await ctx.send(f"🆔 آيدي الرتبة **{role.name}**: `{role.id}`")
    return

  if isinstance(target, discord.TextChannel):
    await ctx.send(f"🆔 آيدي الروم {target.mention}: `{target.id}`")
    return

  if ctx.message.mentions:
    member = ctx.message.mentions[0]
    await ctx.send(f"🆔 آيدي العضو {member.mention}: `{member.id}`")
    return

  member = discord.utils.find(
      lambda m: m.name == target or m.display_name == target, ctx.guild.members
  )
  if member:
    await ctx.send(f"🆔 آيدي العضو {member.mention}: `{member.id}`")
    return

  role = discord.utils.find(lambda r: r.name == target, ctx.guild.roles)
  if role:
    await ctx.send(f"🆔 آيدي الرتبة **{role.name}**: `{role.id}`")
    return

  await ctx.send("❌ لم يتم العثور على عضو أو رتبة بهذا المنشن/الاسم.")


@bot.command(name="مسح", aliases=["clear", "مسح_الرسائل"])
@commands.has_role(OWNER_ROLE_ID)
async def clear_messages(ctx, amount: int = None):
  if amount is None or amount <= 0:
    await ctx.send(
        "⚠️ يرجى تحديد عدد الرسائل المراد مسحها.\nمثال: `.مسح 10`",
        delete_after=2,
    )
    return

  deleted = await ctx.channel.purge(limit=amount + 1)
  await ctx.send(
      f" تم مسح **{len(deleted) - 1}** رسالة بنجاح", delete_after=1
  )


@clear_messages.error
async def clear_messages_error(ctx, error):
  if isinstance(error, commands.MissingRole):
    await ctx.send("❌ هذا الأمر مخصص للـ اونر فقط", delete_after=2)
  elif isinstance(error, commands.BadArgument):
    await ctx.send(
        "❌ يرجى كتابة عدد الرسائل بالأرقام فقط (مثال: `.مسح 5`).",
        delete_after=1,
    )
  elif isinstance(error, commands.BotMissingPermissions):
    await ctx.send(
        "❌ البوت لا يملك صلاحية `Manage Messages` (إدارة الرسائل) لمسح الشات"
    )


@bot.command(name="افتار", aliases=["avatar", "افتاري"])
@in_channel(1515396548392128671)
async def show_avatar(ctx, member: discord.Member = None):
  target = member or ctx.author
  avatar_url = target.display_avatar.url

  embed = discord.Embed(color=discord.Color.dark_theme())
  embed.set_image(url=avatar_url)

  await ctx.send(embed=embed)


@bot.command(name="بنر", aliases=["banner", "بنري"])
@in_channel(1515396548392128671)
async def show_banner(ctx, member: discord.Member = None):
  target = member or ctx.author

  user = await bot.fetch_user(target.id)

  if not user.banner:
    await ctx.send("❌ هذا الحساب لا يملك بنر", delete_after=2)
    return

  banner_url = user.banner.url

  embed = discord.Embed(color=discord.Color.dark_theme())
  embed.set_image(url=banner_url)

  await ctx.send(embed=embed)


@show_avatar.error
@show_banner.error
async def avatar_banner_error(ctx, error):
  if isinstance(error, commands.BadArgument):
    await ctx.send("❌ لم يتم العثور على هذا العضو أو البوت", delete_after=2)


# --- 6. أمر قائمة الألعاب ---
@bot.command(name="العاب")
async def games_list(ctx):
  embed = discord.Embed(
      title="قائمة الألعاب ",
      description=".سؤال\n.سجن\n.حجر\n.توصيل",
      color=discord.Color.blue(),
  )
  await ctx.send(embed=embed)

# --- 6. أمر قائمة الأوامر ---
@bot.command(name="اوامر")
async def commands_list(ctx):
  embed = discord.Embed(
      title="قائمة الأوامر",
      description=".متجر: شراء الوان ورتب\n.طولاري: يظهر رصيد العضو\n.افتار او بنر: انشاء افتار العضو\n.ت @العضو: لتحويل الطولارات",
      color=discord.Color.blue(),
  )
  await ctx.send(embed=embed)

# --- 7. أوامر الإدارة (باند، ميوت، فك ميوت) ---

@bot.command(
    name="انقلع_يالعبد",
    aliases=["انقلع يالعبد", "انقلع_بالعبد", "انقلع بالعبد", "حظر", "ban"],
)
@commands.has_role(OWNER_ROLE_ID)
async def ban_member(
    ctx, member: discord.Member = None, *, reason: str = "لم يتم ذكر السبب"
):
  if not member:
    await ctx.send(
        "⚠️ **يرجى منشن العضو المراد حظره**\nمثال: `.انقلع_يالعبد @User السبب`",
        delete_after=3,
    )
    return

  if member == ctx.author:
    await ctx.send("❌ لا يمكنك حظر نفسك")
    return

  if member.id == ctx.guild.owner_id:
    await ctx.send("❌ لا يمكنك حظر صاحب السيرفر")
    return

  try:
    await member.ban(reason=f"بواسطة {ctx.author.name} - السبب: {reason}")
    await ctx.send(
        f" تم حظر العضو **{member.mention}** بنجاح\n السبب: `{reason}`"
    )
  except discord.Forbidden:
    await ctx.send(
        "❌ لا أملك صلاحيات كافية لحظر هذا العضو (تأكد من رتبة البوت أعلى من"
        " رتبة العضو)."
    )
  except Exception as e:
    await ctx.send(f"❌ حدث خطأ أثناء الحظر: {e}")


@ban_member.error
async def ban_error(ctx, error):
  if isinstance(error, commands.MissingRole):
    await ctx.send("❌ هذا الأمر مخصص للـ اونر فقط", delete_after=3)


@bot.command(name="ميوت", aliases=["كتم", "mute"])
@commands.has_role(OWNER_ROLE_ID)
async def mute_member(
    ctx,
    member: discord.Member = None,
    minutes: int = 10,
    *,
    reason: str = "لم يتم ذكر السبب",
):
  if not member:
    await ctx.send(
        "⚠️ **يرجى منشن العضو المراد كتمه**\nمثال: `.ميوت @User 15 السبب` (15"
        " دقيقة)",
        delete_after=3,
    )
    return

  if member == ctx.author:
    await ctx.send("❌ لا يمكنك كتم نفسك")
    return

  if minutes <= 0:
    await ctx.send("❌ يرجى إدخال عدد دقائق صحيح أكثر من 0.")
    return

  try:
    duration = datetime.timedelta(minutes=minutes)
    await member.timeout(
        duration, reason=f"بواسطة {ctx.author.name} - السبب: {reason}"
    )
    await ctx.send(
        f" تم كتم العضو **{member.mention}** لمدة **{minutes}** دقيقة\n"
        f" السبب: `{reason}`"
    )
  except discord.Forbidden:
    await ctx.send("❌ لا أملك صلاحيات كافية لكتم هذا العضو")
  except Exception as e:
    await ctx.send(f"❌ حدث خطأ: {e}")


@mute_member.error
async def mute_error(ctx, error):
  if isinstance(error, commands.MissingRole):
    await ctx.send("❌ هذا الأمر مخصص للـ اونر فقط", delete_after=3)


@bot.command(name="فك_ميوت", aliases=["فك_الكتم", "unmute"])
@commands.has_role(OWNER_ROLE_ID)
async def unmute_member(ctx, member: discord.Member = None):
  if not member:
    await ctx.send("⚠️ يرجى منشن العضو لفك الكتم عنه", delete_after=3)
    return

  try:
    await member.timeout(None)
    await ctx.send(f" تم فك الكتم عن العضو **{member.mention}** بنجاح")
  except discord.Forbidden:
    await ctx.send("❌ لا أملك صلاحيات كافية لفك الكتم عن هذا العضو")
  except Exception as e:
    await ctx.send(f"❌ حدث خطأ: {e}")


@unmute_member.error
async def unmute_error(ctx, error):
  if isinstance(error, commands.MissingRole):
    await ctx.send("❌ هذا الأمر مخصص للـ اونر فقط", delete_after=3)


# --- 8. أحداث التشغيل ---
@bot.event
async def on_ready():
  print(f"✅ تم تسجيل الدخول باسم: {bot.user.name}")
  fetch_latest_balances_from_github()


bot.run(os.environ.get("DISCORD_TOKEN"))