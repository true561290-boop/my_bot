import discord
from discord.ext import commands

class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # --- 👤 أمر الأفاتار (!افتار) ---
    @commands.command(name="افتار", aliases=["avatar"])
    async def show_avatar(self, ctx, member: discord.Member = None):
        """عرض الصورة الشخصية للعضو بحجمها الكامل"""
        # إذا لم يذكر العضو أحداً، يعرض أفتار الشخص الذي كتب الأمر نفسه
        member = member or ctx.author
        
        embed = discord.Embed(
            title=f"👤 الصورة الشخصية لـ {member.name}", 
            color=discord.Color.blue()
        )
        embed.set_image(url=member.display_avatar.url)
        await ctx.send(embed=embed)

    # --- 🖼️ أمر البانر (!بنر) ---
    @commands.command(name="بنر", aliases=["banner"])
    async def show_banner(self, ctx, member: discord.Member = None):
        """عرض بنر الحساب للعضو بحجمه الكامل إذا كان متوفراً"""
        member = member or ctx.author
        
        # يجب جلب بيانات المستخدم كاملة من الديسكورد للتحقق من وجود البانر
        user = await self.bot.fetch_user(member.id)
        
        # التحقق إذا كان المستخدم يملك بنر فعلياً
        if user.banner:
            embed = discord.Embed(
                title=f"🖼️ بنر الحساب لـ {user.name}", 
                color=discord.Color.purple()
            )
            embed.set_image(url=user.banner.url)
            await ctx.send(embed=embed)
        else:
            # إذا لم يكن لديه بنر، لن يرسل البوت أي شيء في الشات تماماً كما طلبت
            return

# دالة التجهيز لربط الملف بالملف الرئيسي
async def setup(bot):
    await bot.add_cog(Utility(bot))