import discord
from discord.ext import commands
import random
import json
import os
import asyncio
import aiohttp
from threading import Thread
from flask import Flask

# --- 🌐 خادم ويب صغير لإبقاء البوت مستيقظاً 24/7 ---
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

# --- ⚙️ إعدادات مستودع GitHub والبيانات ---
GITHUB_TOKEN = "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"
REPO_OWNER = "true561290-boop"
REPO_NAME = "my_bot"
FILE_PATH = "bank.json"

ADMIN_ROLE_ID = 1515396547528102131
LEVEL_50_ROLE_ID = 1515396547473309712

# --- 🧠 بنك الأسئلة المكون من 100 سؤال صعب جداً ---
QUESTIONS_POOL = {
    "ما هي أصغر عظمة في جسم الإنسان؟": "الركاب",
    "ما هو العنصر الكيميائي الأكثر وفرة في الكون؟": "الهيدروجين",
    "في أي سنة حدثت كوارث تشيرنوبل؟": "1986",
    "ما هي عاصمة أستراليا؟": "كانبرا",
    "ما هو الغاز الذي يشكل معظم غلاف كوكب الزهرة؟": "ثاني أكسيد الكربون",
    "من هو الفيلسوف الذي كتب كتاب 'الجمهورية'؟": "أفلاطون",
    "ما هي الدولة التي تمتلك أكبر عدد من المناطق الزمنية؟": "فرنسا",
    "ما هو العلم الذي يدرس الأنسجة الحية؟": "الهستولوجيا",
    "ما هي أصغر القارات مساحة؟": "أستراليا",
    "ما هو اسم المجرة الأقرب لمجرتنا درب التبانة؟": " أندروميدا",
    "ما هو العنصر الأكثر كهروسلبية في الجدول الدوري؟": "الفلور",
    "في أي عام سقطت القسطنطينية؟": "1453",
    "ما هو الحيوان صاحب أكبر حجم دماغ مقارنة بجسمه؟": "النملة",
    "من اكتشف الدورة الدموية الصغرى؟": "ابن النفيس",
    "ما هو الاسم العلمي للرصاص المستخدم في أقلام الرصاص؟": "الجرافيت",
    "ما هي أكبر محيطات العالم عمقاً ومساحة؟": "المحيط الهادئ",
    "من هو القائد الذي هزم في معركة واترلو؟": "نابليون بونابرت",
    "ما هي السورة التي تنتهي جميع آياتها بحرف الدال؟": "الإخلاص",
    "ما هو الكوكب الملقب بـ 'توأم الأرض'؟": "الزهرة",
    "ما هي الدولة الوحيدة التي تنتمي لقارتين وتفصل بينهما مضيق البوسفور؟": "تركيا",
    "ما هو أكثر المعادن تواًجداً في قشرة الأرض؟": "الألومنيوم",
    "كم عدد الكروموسومات في خلية الإنسان الطبيعية؟": "46",
    "من هو صاحب نظرية النسبية؟": "ألبرت أينشتاين",
    "ما هي عاصمة كندا؟": "أوتاوا",
    "ما هي أعمق نقطة في محيطات الأرض؟": "خندق ماريانا",
    "ما هو رمز عنصر الذهب في الجدول الدوري؟": "Au",
    "من كتب مسرحية هاملت؟": "ويليام شكسبير",
    "ما هي اكبر صحراء رملية متصلة في العالم؟": "الربع الخالي",
    "ما هو الكوكب الذي يملك أكبر عدد من الأقمار؟": "زحل",
    "ما هي المادة الأكثر صلابة في جسم الإنسان؟": "مينا الأسنان",
    "ما اسم الممر المائي الذي يربط بين البحر الأحمر والبحر الأبيض المتوسط؟": "قناة السويس",
    "ما هي عاصمة البرازيل؟": "برازيليا",
    "في أي معركة استشهد حمزة بن عبد المطلب؟": "أحد",
    "ما هو الغاز المسبب لظاهرة الاحتباس الحراري بشكل رئيسي؟": "ثاني أكسيد الكربون",
    "من اخترع الهاتف؟": "ألكسندر جراهام بيل",
    "ما هو أكبر عضو في جسم الإنسان؟": "الجلد",
    "ما هي الدولة الأولى إنتاجاً للقهوة في العالم؟": "البرازيل",
    "من هو الفاتح الإسلامي لبلاد الأندلس؟": "طارق بن زياد",
    "ما هي عاصمة كازاخستان الحالية؟": "أستانا",
    "ما اسم الشريان الرئيسي الذي يخرج من القلب؟": "الأبهر",
    "ما هي أطول سلسلة جبال فوق مستوى البحر؟": "الأنديز",
    "من القائل 'أنا أفكر إذاً أنا موجود'؟": "رينيه ديكارت",
    "ما هي المدينة الملقبة بمدينة التلال السبعة؟": "روما",
    "ما هو رمز عنصر الفضة في الجدول الدوري؟": "Ag",
    "كم عدد القلوب لدى الأخطبوط؟": "3",
    "ما هي السورة القرآنية التي لا تبدأ بـ 'بسم الله الرحمن الرحيم'؟": "التوبة",
    "ما اسم أول إنسان صعد إلى الفضاء؟": "يوري جاجارين",
    "ما هي أصغر دولة في العالم؟": "الفاتيكان",
    "ما هي الدولة ذات أطول خط ساحلي في العالم؟": "كندا",
    "ما هو الغاز المتواجد بأكبر نسبة في الهواء الجوي؟": "النيتروجين",
    "من هو مؤسس علم الجبر؟": "الخوارزمي",
    "ما هي عاصمة إثيوبيا؟": "أديس أبابا",
    "ما هي وحدة قياس الشدة الضوئية؟": "الكانديلا",
    "ما اسم المعركة التي أنهت حكم الوجود الإسلامي في الأندلس؟": "سقوط غرناطة",
    "ما اسم المركب الكيميائي للصودا المخبوزة؟": "بيكربونات الصوديوم",
    "ما هي أقدم عاصمة مسكونة في التاريخ؟": "دمشق",
    "ما هو الحيوان الثديي الوحيد الذي يستطيع الطيران؟": "الخفاش",
    "من هو مكتشف البنسلين؟": "ألكسندر فلمنج",
    "ما هي الدولة الأكثر إنتاجاً للشاي في العالم؟": "الصين",
    "ما هو أكبر بحر مغلق في العالم؟": "بحر قزوين",
    "كم عدد فقرات العمود الفقري للإنسان؟": "33",
    "ما هو رمز عنصر الحديد في الجدول الدوري؟": "Fe",
    "ما اسم المضيق الذي يربط بين الخليج العربي وبحر عمان؟": "مضيق هرمز",
    "من هو مؤلف كتاب 'القانون في الطب'؟": "ابن سينا",
    "ما هي عاصمة سويسرا؟": "برن",
    "ما هي أطول عظمتين في جسم الإنسان؟": "عظمة الفخذ",
    "من قائد معركة نهاوند الملقبة بفتوح الفتوح؟": "النعمان بن مقرن",
    "ما هي عاصمة نيجيريا؟": "أبوجا",
    "ما هو المكون الأساسي للزجاج؟": "السيليكا",
    "كم عدد صمامات قلب الإنسان؟": "4",
    "ما اسم البركان الذي دمر مدينة بومبي الرومانية؟": "فيزوف",
    "ما هي الدولة التي تحيط بدولة ليسوتو بالكامل؟": "جنوب أفريقيا",
    "من الذي اخترع الديناميت؟": "ألفريد نوبل",
    "ما هو أسرع كائن حي على وجه الأرض (سواء طائر أو بري)؟": "الصقر الشاهين",
    "ما هي السورة التي تسمى عروس القرآن؟": "الرحمن",
    "ما هو الكوكب الأكثر سخونة في المجموعة الشمسية؟": "الزهرة",
    "ما هو الجهاز الذي يقيس الزلازل؟": "السيسموجراف",
    "ما هي عاصمة المغرب؟": "الرباط",
    "من هو الرحالة المسلم الذي جاب العالم في القرن 14؟": "ابن بطوطة",
    "ما هو العلم المختص بدراسة الأحفوريات والمستحثات؟": "الإحاثة",
    "ما هي أبعد نقطة في المجموعة الشمسية وصلتها مسبار بشري؟": "فوياجر 1",
    "ما هي وحدة قياس القوة في النظام الدولي؟": "النيوتن",
    "من هو مؤسس الدولة الأموية؟": "معاوية بن أبي سفيان",
    "ما هي عاصمة أيسلندا؟": "ريكيافيك",
    "ما اسم البروتين الرئيسي في شعر الإنسان وأظافره؟": "اليراتين",
    "ما هي المحافظة الأكبر مساحة في السعودية؟": "المنطقة الشرقية",
    "ما هو العنصر الكيميائي الذي يرمز له بـ Na؟": "الصوديوم",
    "من هو الشاعر الملقب بـ 'أمير الشعراء'؟": "أحمد شوقي",
    "ما هي أكبر جزر البحر الأبيض المتوسط مساحة؟": "صقلية",
    "ما اسم الطبقة الخارجية للجلد؟": "البشرة",
    "من هو قائد معركة حطين؟": "صلاح الدين الأيوبي",
    "ما هي عاصمة فيتنام؟": "هانوي",
    "ما هو الغاز السام المعروف بقاتل الصامت ولا رائحة له؟": "أول أكسيد الكربون",
    "ما هي السورة القرآنية التي تحتوي على سجدتين؟": "الحج",
    "ما هو معدن السائل الوحيد في الدرجات العادية؟": "الزئبق",
    "من كان أول من صمم تلسكوب لرصد النجوم؟": "جاليليو جاليلي",
    "ما هي الدولة التي تمتلك أكبر عدد من الأهرامات في العالم؟": "السودان",
    "ما هي عاصمة نيوزيلندا؟": "ويلينغتون",
    "ما هي اكبر بكتيريا تم اكتشافها وتُرى بالعين المجردة؟": "ناميبيينسيس",
    "ما هو رمز عنصر الكالسيوم؟": "Ca"
}

# --- 🧩 100 لغز صعب للسجن ---
ESCAPE_RIDDLES = [
    {"q": "شيء يملك أسناناً كثيرة ولكنه لا يعض، ما هو؟", "a": "المشط"},
    {"q": "كلما أخذت منه كبر وكلما أضفت إليه صغر، ما هو؟", "a": "الحفرة"},
    {"q": "ما هو الشيء الذي يمشي ويقف وليس له أرجل؟", "a": "الماء"},
    {"q": "ما هو الشيء الذي يتكلم جميع اللغات ولكنه لا ينطق؟", "a": "الصدى"},
    {"q": "شيء يكسو الناس ولكنه عارٍ بدون ملابس؟", "a": "الإبرة"},
    {"q": "ما هو الشيء الذي يقرأ ولا يكتب؟", "a": "القلم"},
    {"q": "يسير بلا رجلين ولا يدخل إلا بالأذنين، ما هو؟", "a": "الصوت"},
    {"q": "ما هو الشيء الذي يخترق الزجاج ولا يكاسره؟", "a": "الضوء"},
    {"q": "ما هو الشيء الذي إذا لمسته صرخ؟", "a": "الجرس"},
    {"q": "بيت بلا أبواب ولا نوافذ، فما هو؟", "a": "البيضة"},
    {"q": "ما هو الشيء الذي يكتب ولا يقرأ؟", "a": "القلم"},
    {"q": "له رأس ولا ينطق، وله عين ولا يرى، ما هو؟", "a": "الدبوس"},
    {"q": "شيء إذا أطعمته كبر وإذا سقيته ماءً مات؟", "a": "النار"},
    {"q": "ما هو الشيء الذي يحمل طعامه فوق رأسه؟", "a": "القلم"},
    {"q": "أنا موجود في الشتاء وغير موجود في الصيف ومن 4 حروف؟", "a": "مطر"},
    {"q": "ما هو الشيء الذي ينبض بلا قلب؟", "a": "الساعة"},
    {"q": "شيء كلما زاد نقص، ما هو؟", "a": "العمر"},
    {"q": "ما هو الشيء الذي لا يمكنك استخدامه إلا بعد كسره؟", "a": "البيض"},
    {"q": "أخت خالك وليست خالتك، فمن تكون؟", "a": "أمك"},
    {"q": "ما هو الشيء الذي يملك عيناً واحدة ولكنه لا يرى بها؟", "a": "الإبرة"},
    {"q": "ما هو الشيء الذي يتبعك أينما ذهبت في النهار وينتفي ليلاً؟", "a": "الظل"},
    {"q": "شيء يتواجد في السماء إذا أضفت إليه حرفاً أصبح في الأرض؟", "a": "نجم"},
    {"q": "ما هو القفص الذي لا يحبس طيراً ولا حيواناً؟", "a": "القفص الصدري"},
    {"q": "ما هو الشيء الذي تحمله ويحملك في نفس الوقت؟", "a": "الحذاء"},
    {"q": "شيء يمر من خلال الماء دون أن يبتل؟", "a": " الضوء"},
    {"q": "ما هي المائدة التي ليس عليها أي طعام؟", "a": "مائدة المفاوضات"},
    {"q": "ما هو الشيء الذي إذا أغليته جمد؟", "a": "البيض"},
    {"q": "شيء يملك أوراقاً وليس بنبات، وله لسان وليس بحيوان؟", "a": "الكتاب"},
    {"q": "ما هو الباب الذي لا يمكن فتحه؟", "a": "الباب المفتوح"},
    {"q": "شيء يبكي بلا عينين ويمشي بلا رجلين؟", "a": "السحابة"},
    {"q": "شيء إذا أصببت عليه الماء لا يبتل؟", "a": "الظل"},
    {"q": "ما هو البحر الذي لا يوجد به ماء؟", "a": "بحر الخريطة"},
    {"q": "شيء أبيض وأسود ويقرأه الجميع في العالم؟", "a": "الجريدة"},
    {"q": "ما هو الذي يدور حول الحديقة دون أن يتحرك؟", "a": "السور"},
    {"q": "شيء يسقط على رأسك ولا يؤلمك؟", "a": "المطر"},
    {"q": "له أقدام ولكن لا يمشي، ما هو؟", "a": "الكرسي"},
    {"q": "ما هو الشيء الذي ليس له بداية ولا نهاية؟", "a": "الدائرة"},
    {"q": "شيء يحتوي على مفاتيح كثيرة ولكنه لا يفتح أي باب؟", "a": "البيانو"},
    {"q": "ما هو الشجر الذي ليس له ظل ولا ثمار؟", "a": "شجرة العائلة"},
    {"q": "شيء إذا حذفت أوله أصبح اسم شخص، وإذا حذفت وسطه أصبح ثلج؟", "a": "دبي"},
    {"q": "ما هو الشيء الذي يقرط أذنك دون أن يعضك؟", "a": "البرد"},
    {"q": "شيء إذا وضعت يدك عليه صرخ، وإذا تركته صمت؟", "a": "الجرس"},
    {"q": "ما هي الكلمة التي تُنطق دائماً بشكل خاطئ؟", "a": "خاطئ"},
    {"q": "شيء يجعلك ترى من خلال الجدار؟", "a": "النافذة"},
    {"q": "ما هو الشيء الذي يملك أرقاماً ولكنه لا يحسب؟", "a": "الساعة"},
    {"q": "شيء يدخل الرطب ويخرج جافاً؟", "a": "الخبز"},
    {"q": "له مدخل واحد و3 مخارج، ما هو؟", "a": "القميص"},
    {"q": "ما هو السؤال الذي لا يمكنك إجابته بنعم أبداً؟", "a": "هل أنت نائم؟"},
    {"q": "شيء يصبح أطول عندما يكون صغيراً، وأقصر عندما يكبر؟", "a": "الشمعة"},
    {"q": "ما هو الشيء الذي يملك الكثير من القلوب ولكنه لا يحب؟", "a": "ورق اللعب"},
    {"q": "شيء يطير بلا أجنحة ويبكي بلا أعيُن؟", "a": "السحاب"},
    {"q": "ما هو الشيء الذي ينتمي إليك ولكن يستخدمه الآخرون أكثر منك؟", "a": "اسمك"},
    {"q": "شيء لا يمشي إلا بالضرب؟", "a": "المسمار"},
    {"q": "ما هو الشيء الذي إذا لمسته يصدر صوتاً رناناً؟", "a": "الوتر"},
    {"q": "من هو الشخص الذي يرى عدوه وصديقه بعين واحدة؟", "a": "الأعور"},
    {"q": "ما هو الشيء الذي يتحرك حولك طوال الوقت ولا تراه؟", "a": "الهواء"},
    {"q": "شيء كلما زاد نقص التفاؤل به؟", "a": "الظلام"},
    {"q": "ما هي التي تأكل ولا تشبع؟", "a": "النار"},
    {"q": "ما هو الشيء الذي إذا أردت استخدامه رميته؟", "a": "شبكة الصيد"},
    {"q": "له وجه ويدان ولا يملك أذرعاً ولا أرجلاً؟", "a": "الساعة"},
    {"q": "شيء يوجد بين السماء والأرض؟", "a": "حرف الواو"},
    {"q": "ما هو البيت الذي لا يسكنه أحد؟", "a": "بيت الشعر"},
    {"q": "ما هو الشيء الذي يزداد حسناً كلما زاد تجعداً؟", "a": "المخ"},
    {"q": "شيء يمشي أمامك ولا يمكنك إمساكه؟", "a": "المستقبل"},
    {"q": "شيء يولد كبيراً ويموت صغيراً؟", "a": "الشمعة"},
    {"q": "ما هو الشيء الذي إذا أكلته كله استفدت، وإذا أكلت نصفه مِت؟", "a": "سمسم"},
    {"q": "شيء في جماد ولكنه ينمو مع الزمن؟", "a": "الحفرة"},
    {"q": "أنا صلب كالحجر وأختفي عند وضعي في الماء؟", "a": "السكر"},
    {"q": "ما هي المادة التي تطفو على الماء وهي صلبة؟", "a": "الثلج"},
    {"q": "شيء يمكنك كسره دون أن تلمسه؟", "a": "الوعد"},
    {"q": "ما هو الشيء الذي يمشي أينما أردت دون أن يتحرك من مكانه؟", "a": "الطريق"},
    {"q": "شيء يسير ببطء شديد ويترك أثراً فضياً خلفه؟", "a": "الحلزون"},
    {"q": "شيء يرتفع ولا ينزل أبداً؟", "a": "العمر"},
    {"q": "ما هو أسرع شيء في الكون؟", "a": "الضوء"},
    {"q": "ما هو الشيء الذي ليس له وزن ولكن يمكنه إغراق سفينة؟", "a": "الثقب"},
    {"q": "شيء يستطيع ملء الغرفة دون أن يشغل أي مساحة؟", "a": "الضوء"},
    {"q": "شيء تصنعه ولا تراه، وتراه ولا تلبسه؟", "a": " الفخ"},
    {"q": "ما هي الكلمة الوحيدة التي تبدأ بحرف 'ح' وتنهي بـ 'ح'؟", "a": "بلح"},
    {"q": "شيء يملك سناماً ولا يملك أرجلاً؟", "a": "التل"},
    {"q": "ما هو الذي يركض في الشوارع بلا أرجل؟", "a": "الماء"},
    {"q": "شيء يحتوي على مدن بلا بيوت وبحار بلا ماء؟", "a": "الخريطة"},
    {"q": "ما هو الشيء الذي يمكنه السفر حول العالم وهو قابع في الزاوية؟", "a": "الطابع"},
    {"q": "ما هو الشيء الذي يملك رقبة وليس له رأس؟", "a": "الزجاجة"},
    {"q": "شيء يحرق نفسه ليوفر الضوء للآخرين؟", "a": "الشمعة"},
    {"q": "ما هو الشيء الذي يصعد المرتفعات ويهبط بلا تحرك؟", "a": "درجة الحرارة"},
    {"q": "شيء له 4 أرجل في الصباح ورجلان في الظهيرة و3 في المساء؟", "a": "الإنسان"},
    {"q": "ما هو الشي الذي يعيش في الماء وإذا خرج منه مات؟", "a": "السمك"},
    {"q": "ما هو الشي الذي إذا قطعت رأسه طار؟", "a": "قطار"},
    {"q": "شيء لا ينفس ولكن له حياة؟", "a": "النبات"},
    {"q": "ما هو أصل الصلابة وأصل الهشاشة؟", "a": "الماس"},
    {"q": "شيء يسير أمامك دائماً ولكنه مخفي؟", "a": "الغد"},
    {"q": "ما هو الشيء الذي ينقص كلما تم مسحه؟", "a": "السبورة"},
    {"q": "شيء تراه في الليل 3 مرات وفي النهار مرة واحدة؟", "a": "حرف اللام"},
    {"q": "ما هي التي تولد من النار وتعيش في النور؟", "a": "الشرارة"},
    {"q": "شيء إذا حذفت أول حرف منه طار؟", "a": "مطار"},
    {"q": "ما هو الشيء الذي يزن كثيراً ولكنه ينفذ بالهواء؟", "a": "البالون"},
    {"q": "شيء يلمع في الليل ولا يستضار به النهار؟", "a": "النجم"},
    {"q": "ما هو الشيء الذي يحمي بيتك ولا يتكلم؟", "a": "القفل"},
    {"q": "شيء تضع أيديك عليه ليعمل، فما هو؟", "a": "المقود"},
    {"q": "ما هو الشيء الذي لا يتكلم وإذا جاع كذب؟", "a": "الساعة"}
]

# --- 🛒 المتجر ---
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

# --- 🔄 دالات GitHub وحماية البيانات ---
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
                    data = json.loads(file_data)
                    bot.user_bank.update(data)
                    print("✅ [GitHub Cloud] تم تحميل البيانات بنجاح ثابتاً!")
                else:
                    print(f"⚠️ [GitHub Cloud] فشل التحميل بكود الحالة: {r.status}")
        except Exception as e:
            print(f"⚠️ [GitHub Cloud] خطأ أثناء تحميل البيانات: {e}")

async def async_update_balance(user_id, amount):
    uid = str(user_id)
    import base64
    
    if not bot.user_bank:
        await load_data_from_github()

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
                "message": "🔄 تحديث تلقائي لرصيد البنك",
                "content": encoded
            }
            if sha:
                payload["sha"] = sha
                
            async with session.put(url, headers=headers, json=payload) as r_put:
                if r_put.status in [200, 201]:
                    print("✅ [GitHub Cloud] تم الحفظ سحابياً بنجاح!")
        except Exception as e:
            print(f"⚠️ [GitHub Cloud] خطأ أثناء الحفظ: {e}")

def get_balance(user_id):
    uid = str(user_id)
    if uid not in bot.user_bank:
        bot.user_bank[uid] = 200
    return bot.user_bank[uid]

# --- 🛡️ نظام حماية الخط الكبير ---
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

# --- 🎮 أمر !العاب المحدث ---
@bot.command(name="العاب")
async def show_games(ctx):
    embed = discord.Embed(
        title="🎮 قائمة الألعاب المتاحة",
        description="إليك اللعبتين المتاحتين حالياً في البوت مع التعديلات الجديدة الصعبة:",
        color=discord.Color.blue()
    )
    embed.add_field(
        name="❓ لعبة الأسئلة: `!سؤال [عدد الجولات]`",
        value="🔥 **أسئلة جديدة معقدة وصعبة!**\n⏱️ لديك **8 ثوانٍ** فقط للإجابة وسرعة البديهة مطلوبة.\n💸 الجائزة: **100 دولار** لكل إجابة صحيحة.",
        inline=False
    )
    embed.add_field(
        name="🚔 لعبة السجن: `!سجن`",
        value="🔓 **تسجن نفسك فوراً بدون الحاجة لمنشن!**\n🧩 يُطرح عليك لغز من أصل **100 لغز صعب**.\n⏱️ لديك **10 ثوانٍ** فقط للحل والهروب قبل إغلاق السجن.\n💸 الجائزة: **30 دولار** عند الهروب بنجاح.",
        inline=False
    )
    embed.set_footer(text="B✰IL Hardcore Gaming System")
    await ctx.send(embed=embed)

# --- 🎮 أمر !سؤال الصعب (8 ثوانٍ) ---
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
            title=f"❓ سؤال الجولة {round_num} من {rounds} (صعب 🔥)",
            description=f"**{question}**\n\n⏰ لديك **8 ثوانٍ فقط** للإجابة الصحيحة!",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)

        def check(m):
            return m.channel == ctx.channel and not m.author.bot and m.content.strip().lower() == answer.lower()

        try:
            msg = await bot.wait_for('message', timeout=8.0, check=check)
            await async_update_balance(msg.author.id, 100)
            
            win_embed = discord.Embed(
                title="🎉 إجابة صحيحة وسريعة!",
                description=f"كفو يا {msg.author.mention}! الإجابة هي **{answer}**.\nفزت بـ **100 دولار** 💸!",
                color=discord.Color.green()
            )
            await ctx.send(embed=win_embed)
        except asyncio.TimeoutError:
            fail_embed = discord.Embed(
                title="⏰ انتهى الوقت!",
                description=f"للأسف لم يجُب أحد بسرعة كافية!\nالإجابة الصحيحة هي: **{answer}**",
                color=discord.Color.dark_grey()
            )
            await ctx.send(embed=fail_embed)

        if round_num < rounds:
            await asyncio.sleep(2)

# --- 🚨 أمر !سجن مع مكافأة 30 دولار عند الحل ---
@bot.command(name="سجن")
async def jail_user(ctx):
    member = ctx.author
    riddle = random.choice(ESCAPE_RIDDLES)
    
    embed = discord.Embed(
        title="🚔 لقد دخلت السجن بنفسك!",
        description=f"يا {member.mention}، لقد تم سجنك! للهروب، يجب أن تحل اللغز التالي بسرعة خلال **10 ثوانٍ** فقط:\n\n🧩 **{riddle['q']}**",
        color=discord.Color.dark_red()
    )
    await ctx.send(embed=embed)

    def check(m):
        return m.author == member and m.channel == ctx.channel and riddle['a'] in m.content.strip().lower()

    try:
        await bot.wait_for('message', timeout=10.0, check=check)
        await async_update_balance(member.id, 30)
        await ctx.send(f"🔓 **مبروك!** {member.mention} حل اللغز الصعب بنجاح، ونجح في الهروب وحصل على **30 دولار** 💸!")
    except asyncio.TimeoutError:
        await ctx.send(f"🔒 **انتهى الوقت!** {member.mention} لم يجب خلال 10 ثوانٍ ويبقى محبوساً!")

# --- 💳 أمر !فلوس ---
@bot.command(name="فلوس")
async def check_wallet(ctx):
    balance = get_balance(ctx.author.id)
    embed = discord.Embed(
        title="💳 بطاقة حسابك البنكي",
        color=discord.Color.gold()
    )
    embed.add_field(name="صاحب الحساب", value=ctx.author.mention, inline=False)
    embed.add_field(name="الرصيد الحالي", value=f"**${balance:,}** دولار 💸", inline=False)
    embed.set_footer(text="B✰IL Bank System")
    await ctx.send(embed=embed)

# --- 🛒 أمر !متجر ---
@bot.command(name="متجر")
async def show_shop(ctx):
    embed = discord.Embed(
        title="🛒 متجر السيرفر",
        description="اختر القسم الذي تريد الشراء منه باستخدام القائمة أدناه:",
        color=discord.Color.purple()
    )
    
    roles_desc = "\n".join([f"• **{item['name']}** - ${item['price']} ({item['desc']})" for item in ROLES_SHOP.values()])
    colors_desc = "\n".join([f"• **{item['name']}** - ${item['price']}" for item in COLORS_SHOP.values()])
    
    embed.add_field(name="👑 قسم الرتب", value=roles_desc, inline=False)
    embed.add_field(name="🎨 قسم الألوان", value=colors_desc, inline=False)
    
    await ctx.send(embed=embed, view=MainShopView(ctx.author))

# --- 🛒 واجهات الشراء والمشتروات ---
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
            await interaction.response.send_message("❌ البوت لا يملك صلاحية إدارة الرتب.", ephemeral=True)

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
            await interaction.response.send_message("🎨 اختر اللون المراد شراؤه:", view=ItemPurchaseView(self.author, COLORS_SHOP, "🎨 اختر لوناً...", is_color_shop=True), ephemeral=True)

class MainShopView(discord.ui.View):
    def __init__(self, author):
        super().__init__(timeout=60.0)
        self.add_item(ShopSelect(author))

# --- 💸 أمر التحويل ---
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

# --- 👑 أمر إعطاء الأدمن ---
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

# --- 🚀 تشغيل البوت ---
@bot.event
async def on_ready():
    print("🤖 B✰IL bot is checking database...")
    await load_data_from_github()
    print(f"Logged in as {bot.user.name}!")

bot.run(os.environ.get('DISCORD_TOKEN'))