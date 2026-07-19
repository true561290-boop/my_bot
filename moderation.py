import discord
from discord.ext import commands

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # --- 🧹 أمر مسح الرسائل المطور ---
    @commands.command(name="مسح")
    @commands.has_permissions(manage_messages=True)
    async def clear_messages(self, ctx, amount: int):
        """أمر مسح الرسائل: !مسح 10"""
        if amount <= 0:
            await ctx.send("❌ | يرجى تحديد عدد رسائل أكبر من صفر!", delete_after=2)
            return

        # إضافة 1 لعدد الرسائل لحذف رسالة الأمر نفسه (!مسح) مع الرسائل المطلوبة
        deleted = await ctx.channel.purge(limit=amount + 1)
        
        # 🌟 هنا التعديل: البوت يرسل الرسالة ويحذفها تلقائياً بعد ثانيتين (2)
        await ctx.send(f"🧹 | تم مسح {len(deleted) - 1} رسالة بنجاح!", delete_after=2)

    # معالجة الخطأ في حال عدم امتلاك الصلاحية
    @clear_messages.error
    async def clear_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ | عذراً، هذا الأمر خاص بالمشرفين الذين يملكون صلاحية `إدارة الرسائل` فقط!", delete_after=3)

# دالة التجهيز لربط الملف بالملف الرئيسي
async def setup(bot):
    await bot.add_cog(Moderation(bot))


    # 2. أمر الميوت (كتم الصوت والكتابة)
    @commands.command(name="ميوت")
    @commands.has_permissions(manage_roles=True)
    async def mute_user(self, ctx, member: discord.Member, *, reason="لا يوجد سبب"):
        mute_role = discord.utils.get(ctx.guild.roles, name="Muted")
        if not mute_role:
            mute_role = await ctx.guild.create_role(name="Muted")
            for channel in ctx.guild.channels:
                await channel.set_permissions(mute_role, speak=False, send_messages=False, add_reactions=False)
        
        await member.add_roles(mute_role)
        await ctx.send(f"🔇 | تم إعطاء ميوت للمستخدم {member.mention} بسبب: {reason}")

    # 3. أمر الطرد (Kick)
    @commands.command(name="طرد")
    @commands.has_permissions(kick_members=True)
    async def kick_user(self, ctx, member: discord.Member, *, reason="لا يوجد سبب"):
        await member.kick(reason=reason)
        await ctx.send(f"👞 | تم طرد المستخدم {member.mention} بنجاح بسبب: {reason}")

    # 4. أمر البان (Ban)
    @commands.command(name="بان")
    @commands.has_permissions(ban_members=True)
    async def ban_user(self, ctx, member: discord.Member, *, reason="لا يوجد سبب"):
        await member.ban(reason=reason)
        await ctx.send(f"🔨 | تم حظر المستخدم {member.mention} نهائياً بسبب: {reason}")

    # معالجة الأخطاء إذا حاول شخص بدون رتبة/صلاحية استخدام الأوامر
    @clear_messages.error
    @mute_user.error
    @kick_user.error
    @ban_user.error
    async def mod_errors(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ | نعتذر، ولكنك لا تملك الصلاحيات الإدارية الكافية لاستخدام هذا الأمر!")
        elif isinstance(error, commands.MissingRequiredArgument):
            if ctx.command.name == "مسح":
                await ctx.send("❓ | طريقة الاستخدام الخاطئة! اكتب الأمر ثم عدد الرسائل. مثال: `!مسح 50`")
            else:
                await ctx.send("❓ | طريقة الاستخدام الخاطئة! اكتب الأمر ثم منشن العضو. مثال: `!طرد @اسم_العضو`")
        elif isinstance(error, commands.BadArgument) and ctx.command.name == "مسح":
            await ctx.send("❌ | يرجى كتابة عدد صحيح للرسائل! مثال: `!مسح 20`")

async def setup(bot):
    await bot.add_cog(Moderation(bot))