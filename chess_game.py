import discord
from discord.ext import commands
import chess
import urllib.parse
import asyncio
import random

# قاموس لحفظ الألعاب النشطة في السيرفر
active_games = {}

class ChessGame:
    def __init__(self, white_player, black_player, is_vs_bot=False):
        self.board = chess.Board()
        self.white = white_player
        self.black = black_player
        self.current_turn = white_player
        self.is_vs_bot = is_vs_bot # تحديد ما إذا كان اللعب ضد البوت
        
        # متغيرات مؤقتة لحفظ حالة الجولة الحالية
        self.current_legal_pieces = []
        self.current_legal_destinations = []
        self.selected_piece = None

    def get_board_image_url(self, mode="pieces"):
        fen_encoded = urllib.parse.quote(self.board.fen())
        orientation = "black" if self.board.turn == chess.BLACK else "white"
        base_url = f"https://fen2image.chessvision.ai/{fen_encoded}?orientation={orientation}"
        
        # إضافة الأرقام التوضيحية فوق المربعات كعلامات (Marks) في رابط الصورة
        marks = []
        if mode == "pieces":
            # وضع أرقام فوق القطع المتاحة للتحريك للّاعب البشري فقط
            for index, square in enumerate(self.current_legal_pieces):
                sq_name = chess.square_name(square)
                marks.append(f"mark={sq_name},label={index+1},color=blue")
        
        elif mode == "destinations" and self.selected_piece is not None:
            # وضع أرقام فوق المربعات المتاحة للقطعة المختارة
            for index, square in enumerate(self.current_legal_destinations):
                sq_name = chess.square_name(square)
                marks.append(f"mark={sq_name},label={index+1},color=green")
                
        if marks:
            base_url += "&" + "&".join(marks)
            
        return base_url

    def update_legal_pieces(self):
        # تجميع كل المربعات الفريدة التي تحتوي على قطع تملك حركات قانونية حالياً
        moves = list(self.board.legal_moves)
        self.current_legal_pieces = sorted(list(set([m.from_square for m in moves])))

    def update_legal_destinations(self, piece_square):
        # تجميع المربعات التي يمكن للقطعة المحددة الذهاب إليها
        moves = list(self.board.legal_moves)
        self.current_legal_destinations = sorted([m.to_square for m in moves if m.from_square == piece_square])

class ChessCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="شطرنج")
    async def start_chess(self, ctx, opponent: discord.Member = None):
        if ctx.channel.id in active_games:
            await ctx.send("⚠️ | هناك مباراة قائمة بالفعل في هذه القناة!")
            return

        is_vs_bot = False
        # إذا لم يتم تحديد خصم، أو تم منشنة البوت نفسه، يتم اللعب ضد البوت
        if opponent is None or opponent == self.bot.user:
            opponent = self.bot.user
            is_vs_bot = True
            await ctx.send("🤖 **لقد قبلت تحدي الذكاء الاصطناعي لبوت B✰IL! جاهز للهزيمة؟**")
        elif opponent == ctx.author or opponent.bot:
            await ctx.send("⚠️ | يرجى منشن لاعب حقيقي لتتحداه، أو اكتب الأمر بمفردك للعب ضد البوت!")
            return
        else:
            await ctx.send("♟️ **تبدأ معركة الشطرنج بالأرقام بين لاعبين!**")

        game = ChessGame(white_player=ctx.author, black_player=opponent, is_vs_bot=is_vs_bot)
        active_games[ctx.channel.id] = game
        
        await asyncio.sleep(1.5)
        
        while ctx.channel.id in active_games:
            game.update_legal_pieces()
            turn_name = "الأبيض ⚪" if game.board.turn == chess.WHITE else "الأسود ⚫"
            
            # --- دور البوت (إذا كان النمط ضد البوت وجاء دوره) ---
            if game.is_vs_bot and game.current_turn == self.bot.user:
                bot_msg = await ctx.send("🤖 *البوت يقوم بحساب النقلة القانونية الأفضل الآن...*")
                await asyncio.sleep(2) # محاكاة تفكير البوت
                
                # البوت يختار نقلة ذكية/عشوائية من النقلات القانونية المتاحة
                legal_moves = list(game.board.legal_moves)
                bot_move = random.choice(legal_moves) # يمكنك مستقبلاً دمج محرك Stockfish هنا لصعوبة أعلى
                
                game.board.push(bot_move)
                await bot_msg.delete()
                
                # التحقق من انتهاء اللعبة بعد نقلة البوت
                if await self.check_game_end(ctx, game):
                    break
                    
                game.current_turn = game.white
                continue

            # --- دور اللاعب البشري ---
            embed = discord.Embed(
                title=f"♟️ دور اللاعب {turn_name}",
                description=f"👑 **المطلوب من {game.current_turn.mention}:**\n"
                            f"اكتب في الشات **رقم الأزرق** المتواجد فوق القطعة التي تريد تحريكها الآن.\n\n"
                            f"🏳️ للاستسلام في أي وقت، اكتب: `!استسلام`",
                color=discord.Color.blue()
            )
            embed.set_image(url=game.get_board_image_url(mode="pieces"))
            status_msg = await ctx.send(embed=embed)

            def check_piece_choice(m):
                if m.channel == ctx.channel and m.author == game.current_turn:
                    if m.content.strip().isdigit():
                        val = int(m.content.strip())
                        return 1 <= val <= len(game.current_legal_pieces)
                return False

            try:
                msg = await self.bot.wait_for('message', check=check_piece_choice, timeout=60.0)
                chosen_piece_index = int(msg.content.strip()) - 1
                game.selected_piece = game.current_legal_pieces[chosen_piece_index]
            except asyncio.TimeoutError:
                await ctx.send(f"⏱️ | تأخر {game.current_turn.mention} في الاختيار، تم إلغاء المباراة بسبب الخمول.")
                active_games.pop(ctx.channel.id, None)
                break

            # --- المرحلة 2: اختيار الوجهة للمحرك ---
            game.update_legal_destinations(game.selected_piece)
            
            embed_dest = discord.Embed(
                title="🎯 أين تريد نقل القطعة؟",
                description=f"👤 **{game.current_turn.mention}**، اختر الآن **الرقم الأخضر** للمربع الذي تريد نقل القطعة إليه.\n"
                            f"🔄 لتغيير رأيك واختيار قطعة أخرى، اكتب الرقم `0`.",
                color=discord.Color.green()
            )
            embed_dest.set_image(url=game.get_board_image_url(mode="destinations"))
            await status_msg.delete() 
            dest_msg = await ctx.send(embed=embed_dest)

            def check_dest_choice(m):
                if m.channel == ctx.channel and m.author == game.current_turn:
                    if m.content.strip().isdigit():
                        val = int(m.content.strip())
                        return 0 <= val <= len(game.current_legal_destinations)
                return False

            try:
                msg_dest = await self.bot.wait_for('message', check=check_dest_choice, timeout=60.0)
                chosen_dest_val = int(msg_dest.content.strip())
                
                if chosen_dest_val == 0:
                    await dest_msg.delete()
                    await ctx.send("🔄 تم إلغاء تحديد القطعة، يرجى إعادة الاختيار من جديد..", delete_after=3)
                    continue 
                    
                chosen_dest_square = game.current_legal_destinations[chosen_dest_val - 1]
            except asyncio.TimeoutError:
                await ctx.send(f"⏱️ | تأخر {game.current_turn.mention} في اختيار المربع، تم إلغاء المباراة.")
                active_games.pop(ctx.channel.id, None)
                break

            # تنفيذ الحركة الفعلية
            move = chess.Move(game.selected_piece, chosen_dest_square)
            
            # ترقية البيدق التلقائية لوزير
            if game.board.piece_at(game.selected_piece).piece_type == chess.PAWN:
                if chess.square_rank(chosen_dest_square) in [0, 7]:
                    move.promotion = chess.QUEEN

            game.board.push(move)
            await dest_msg.delete()

            # التحقق من انتهاء اللعبة بعد نقلة اللاعب
            if await self.check_game_end(ctx, game):
                break

            # تبديل الأدوار
            game.current_turn = game.black if game.current_turn == game.white else game.white

    async def check_game_end(self, ctx, game):
        if game.board.is_game_over():
            result_text = "🏁 **انتهت الملحمة الكبرى!** "
            if game.board.is_checkmate():
                # معرفة من الفائز بناءً على الدور الحالي في الرقعة
                if game.board.turn == chess.BLACK:
                    winner = game.white
                    result_text += f"كش ملك! الفائز الفعلي هو {winner.mention} 🏆"
                    # توزيع الجائزة إذا لم يكن الفائز هو البوت
                    if winner != self.bot.user and hasattr(self.bot, 'user_bank'):
                        uid = str(winner.id)
                        self.bot.user_bank[uid] = self.bot.user_bank.get(uid, 200) + 300
                        result_text += "\n💸 تم إضافة **300 دولار** لجائزة الفوز الحاسم!"
                else:
                    winner = game.black
                    result_text += f"كش ملك! الفائز هو {winner.mention} 🏆"
            else:
                result_text += "انتهت المعركة بالتعادل السلمي بين الطرفين!"

            final_embed = discord.Embed(title="🏁 نهاية الشطرنج", description=result_text, color=discord.Color.gold())
            final_embed.set_image(url=game.get_board_image_url(mode="none"))
            await ctx.send(embed=final_embed)
            active_games.pop(ctx.channel.id, None)
            return True
        return False

    @commands.command(name="استسلام")
    async def forfeit_chess(self, ctx):
        if ctx.channel.id not in active_games:
            await ctx.send("❌ | لا توجد مباراة شطرنج نشطة في هذه القناة حالياً.")
            return
            
        game = active_games[ctx.channel.id]
        if ctx.author != game.white and ctx.author != game.black:
            await ctx.send("❌ | أنت لست طرفاً في المباراة لتستسلم!")
            return
            
        winner = game.black if ctx.author == game.white else game.white
        active_games.pop(ctx.channel.id, None)
        
        name = "البوت 🤖" if winner == self.bot.user else winner.mention
        await ctx.send(f"🏳️ | أعلن {ctx.author.mention} انسحابه! الفائز بالمباراة هو {name} 🏆!")

async def setup(bot):
    await bot.add_cog(ChessCog(bot))