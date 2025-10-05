import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
import os
import asyncio
import json
import random
import re
from pathlib import Path

YDL_OPTIONS = {'format': 'bestaudio'}
FFMPEG_OPTIONS = {'options': '-vn'}

base_dir = Path(__file__).resolve().parent
data_dir = base_dir.parent / "data"

allowed_user_id = None
allowed_guild_id = None

def check_admin(id):
    return int(id) == allowed_user_id

def check_guild(id):
    return int(id) == allowed_guild_id

# Given a string, leave only KR characters and alphabets, numerics.
# Then, convert every uppercase alphabets to lowercase alphabets.
# Used on comparing quiz answer.
def leave_only_kr_en_chars(s: str):
    subbed = re.sub(r'[^가-힣ㄱ-ㅎㅏ-ㅣA-Za-z0-9]', '', s)
    return subbed.lower()


class Track:
    def __init__(self, id: int, title: str, artist: str, yt_uri: str | None = None, yt_vid_title: str | None = None, yt_vid_length: int | None = None):
        self.id = id
        self.title = title
        self.artist = artist
        self.yt_uri = yt_uri
        self.yt_vid_title = yt_vid_title
        self.yt_vid_length = yt_vid_length

    def __str__(self):
        return f"{self.id}\t{self.title}\t{self.artist}\t{self.yt_uri}"

class User:
    def __init__(self, id: int, point: int = 0, coin: int = 10):
        self.id = id
        self.point = point
        self.coin = coin

    def change_point(self, delta: int):
        self.point += delta

    def change_coin(self, coin: int):
        if self.coin + coin < 0:
            return False
        
        self.coin += coin

        return True
    
class Problem():
    MAX_HINTS = 2
    MAX_WRONG_ANSWERS = 10
    SKIP_VOTES = 3
    BASE_POINTS = 10

    def __init__(self, track):
        self.track = track

        self.answer: str = track.title
        self.wrong_answers = 0
        self.hints = Problem.MAX_HINTS
        self.skip_votes = Problem.SKIP_VOTES
        self.completed = False
    
    def compare_answer(self, user_answer: str):
        if self.completed:
            return False, 2

        hint_now = self.hints

        truth_parts = self.answer.split("(")
        truth_keywords = []

        for part in truth_parts:
            if part.startswith("Feat.") or part.startswith("feat."):
                continue
            truth_keywords.append(leave_only_kr_en_chars(part))
        
        # Do the same thing on user.

        submitted_parts = user_answer.split("(")
        submitted_keywords = []

        for part in submitted_parts:
            if part.startswith("Feat.") or part.startswith("feat."):
                continue
            submitted_keywords.append(leave_only_kr_en_chars(part))
        
        # Now given keywords, check if user-submitted keywords are all present in truth keywords.
        for user_keyword in submitted_keywords:
            if user_keyword not in truth_keywords:
                self.wrong_answers += 1

                if self.wrong_answers == Problem.MAX_WRONG_ANSWERS:
                    return False, 1
                else:
                    return False, 0
                
        self.completed = True
            
        return True, (Problem.BASE_POINTS - Problem.MAX_HINTS + hint_now)

    # Returns hint string of the current problem.
    def hint_str(self):
        # TODO: Add more hint logic.
        hint_index = Problem.MAX_HINTS - self.hints

        self.hints = max(0, self.hints - 1)

        
        tail = f"*문제에서 획득하는 점수: {Problem.BASE_POINTS - hint_index - 1}*"

        if hint_index != Problem.MAX_HINTS:
            header = f"**힌트 {hint_index + 1}**"
            body = None

            if hint_index == 0:
                body = f"**제목 첫 글자: {self.answer[0]}**"
            elif hint_index == 1:
                body = f"**가수: {self.track.artist}**"

            return (header, body, tail)

        else:
            return ("**힌트 없음**", f"이미 힌트를 {hint_index}개 다 썼어요.", tail)

    def skip(self) -> bool:
        self.skip_votes = max(0, self.skip_votes - 1)

        return self.skip_votes <= 0

class SongQuiz(commands.Cog):
    def __init__(self, bot):
        self.quiz_running = False
        self.quiz_match_songs_played = -1
        self.quiz_match_songs_total = -1
        self.quiz_sampled_problems = []
        self.quiz_guild_id = None
        self.quiz_text_channel_id = None
        self.match_id = 0

        self.bot: commands.Bot = bot
        self.voice_client = None

        self.song_database = []
        self.load_song_database()

        self.use_random_offset = False

        self.scoreboard = {}

        super().__init__()

    @app_commands.command(name="노래퀴즈", description="노래 퀴즈를 시작합니다.")
    @app_commands.describe(song_count="퀴즈를 몇 곡 동안 진행할 것인지 적습니다. 최소 10, 최대 50.")
    @app_commands.describe(random_offset="노래를 무작위 시점에서 재생하는 버전의 노래퀴즈를 합니다. 사용하려면 true로 설정하세요.")
    async def song_quiz_begin(self, interaction: discord.Interaction, song_count: int, random_offset: bool = False):
        if song_count < 10 or song_count > 50:
            await interaction.response.send_message("퀴즈는 최소 10곡, 최대 50곡까지만 할 수 있어요.", ephemeral=True)
            return

        if interaction.user.voice is None:
            await interaction.response.send_message("노래 퀴즈를 시작하려면 음성 채널에 입장해야 해요.", ephemeral=True)
            return
        
        if self.quiz_running:
            await interaction.response.send_message("이미 노래 퀴즈가 진행 중이에요. 퀴즈를 종료하고 싶다면 **/종료** 명령어로 퀴즈를 종료하세요.", ephemeral=True)
            return

        self.quiz_text_channel_id = interaction.channel_id
        self.quiz_guild_id = interaction.guild_id

        begin_random_offset_string = "**켜짐**" if random_offset else "꺼짐"
        begin_title = "노래 퀴즈를 시작할게요!"
        begin_description = f"문제 수: **{song_count}**\n무작위 시점 재생: {begin_random_offset_string}"
        await interaction.response.send_message(embed=discord.Embed(title=begin_title, description=begin_description, color=discord.Color.blue()))

        self.match_id += 1
        self.quiz_match_songs_played = 0
        self.quiz_match_songs_total = song_count
        self.quiz_running = True
        self.sample_quiz_problems(song_count)
        self.use_random_offset = random_offset
        self.scoreboard = {}

        voice_channel = interaction.user.voice.channel
        self.voice_client = discord.utils.get(self.bot.voice_clients, guild=interaction.guild)

        if self.voice_client is None:
            self.voice_client = await voice_channel.connect()

        await asyncio.sleep(2)

        await self.run_quiz_problem()
    
    @app_commands.command(name="종료", description="노래 퀴즈를 종료합니다.")
    async def song_quiz_end(self, interaction: discord.Interaction):
        if not self.quiz_running:
            await interaction.response.send_message("노래 퀴즈를 시작하지 않았는데 종료하려고 하다니 정말 박규순 같군..", ephemeral=True)
            return
    
        voice_client = interaction.guild.voice_client
        
        if voice_client is None:
            await interaction.response.send_message("뭔가 잘못됐네요. 음성 채팅에 제가 있지 않은데.. 아무튼 노래 퀴즈를 종료할게요.", ephemeral=True)
            self.voice_client = None
            return
        
        interaction.response.send_message("퀴즈 강제 종료!")
        await self.show_quiz_scoreboard(at_end=True)
        await voice_client.disconnect()
        await interaction.response.send_message("한 번 더 하려면 **/노래퀴즈** 명령어를 사용하세요.\n노래 퀴즈의 랭킹을 보려면 **/랭킹** 명령어를 사용하세요.")

        self.voice_client = None
        self.quiz_cleanup()

    @app_commands.command(name="답", description="노래 퀴즈의 답안을 제출합니다.")  
    @app_commands.describe(answer="노래 제목의 정답. 대소문자, 특수문자, 띄어쓰기는 신경쓰지 않아도 돼요.")
    async def song_quiz_submit(self, interaction: discord.Interaction, answer: str):
        current_problem = self.get_current_problem()

        if current_problem is None:
            await interaction.response.send_message("노래 퀴즈가 진행 중이지 않거나, 아직 문제를 불러오는 중이에요.", ephemeral=True)
            return
        
        correctness, point = current_problem.compare_answer(answer)
        guild = self.bot.get_guild(self.quiz_guild_id)
        channel = guild.get_channel(self.quiz_text_channel_id)

        if interaction.user.id not in self.scoreboard:
            self.scoreboard[interaction.user.id] = User(interaction.user.id)

        if correctness:
            answered_user = self.scoreboard[interaction.user.id]
            answered_user.change_point(point)

            self.voice_client.stop()
            embed = discord.Embed(title=f"**정답!**", description=f"정답자: {interaction.user.mention}\n**{current_problem.track.title}** - *{current_problem.track.artist}*", color=discord.Color.blue())
            await interaction.response.send_message(embed=embed)
            self.quiz_match_songs_played += 1

            await self.check_quiz_has_ended(channel)
                        
        else:
            if point == 0:
                # Just do next trial
                embed = discord.Embed(
                    title=f"**오답!** <남은 기회: {Problem.MAX_WRONG_ANSWERS - current_problem.wrong_answers} / {Problem.MAX_WRONG_ANSWERS}>",
                    description=f"{interaction.user.mention}의 답안:\n{answer}",
                    color=discord.Color.blue()
                    )
                await interaction.response.send_message(embed=embed)
            elif point == 1:
                # Skip current quiz.
                embed = discord.Embed(
                    title=f"**오답!** <남은 기회 없음>",
                    description=f"오답 횟수 10회를 모두 소모했어요.\n정답은 **{current_problem.track.title}** - *{current_problem.track.artist}* 였습니다",
                    color=discord.Color.blue()
                    )

                self.quiz_match_songs_played += 1
                self.voice_client.stop()
                await interaction.response.send_message(embed=embed)

                await self.check_quiz_has_ended(channel)
            elif point == 2:
                # Other user had already submitted the answer. Make it failure.
                embed = discord.Embed(
                    title=f"{interaction.user.mention} **정답이지만..**",
                    description=f"작은 차이로 누군가 먼저 정답을 맞혔어요. 다음 기회에!",
                    color=discord.Color.blue()
                    )
                
                await interaction.response.send_message(embed=embed)

            else:
                await interaction.response.send_message("예기치 못한 오류입니다.")

    @app_commands.command(name="스킵", description="현재 나오는 노래를 스킵하고 다음 문제로 넘어갑니다.")
    async def song_quiz_skip(self, interaction: discord.Interaction):
        current_problem = self.get_current_problem()

        if current_problem is None:
            await interaction.response.send_message("노래 퀴즈 중이 아니라 스킵할 수 없습니다.", ephemeral=True)
            return
        
        if current_problem.skip():
            guild = self.bot.get_guild(self.quiz_guild_id)
            channel = guild.get_channel(self.quiz_text_channel_id)

            self.quiz_match_songs_played += 1
            self.voice_client.stop()

            embed = discord.Embed(title=f"문제 스킵!", description=f"문제를 스킵합니다.\n문제 정답: **{current_problem.track.title}** - *{current_problem.track.artist}*", color=discord.Color.blue())

            await channel.send(embed=embed)
            await self.check_quiz_has_ended(channel)
        else:
            await interaction.response.send_message("문제를 스킵하려면, **/스킵** 명령어를 몇 번 더 입력하면 스킵할 수 있어요.", ephemeral=True)

    @app_commands.command(name="힌트", description="현재 나오는 노래 문제의 힌트를 봅니다. 노래 당 2번까지.")
    async def song_quiz_hint(self, interaction: discord.Interaction):
        current_problem = self.get_current_problem()

        if current_problem is None:
            await interaction.response.send_message("노래 퀴즈가 진행 중이지 않은데 힌트를 받으려 하면 엎드려 뻗치게 될 것입니다.", ephemeral=True)
            return
    
        hint_title, hint_body, hint_tail = current_problem.hint_str()
        embed = discord.Embed(
            title=hint_title,
            description="\n\n".join([hint_body, hint_tail]),
            color=discord.Color.blue()
        )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="랭킹", description="노래 퀴즈의 누적 순위표를 봅니다.")
    async def song_quiz_rank(self, interaction: discord.Interaction):
        scoreboard_list = self.bot.user_map.values()
        sorted_list = sorted(scoreboard_list, key=lambda x: x.point, reverse=True)

        guild = interaction.guild

        rank = 0
        prev_point = 9999999999
        title_string = "**노래 퀴즈 누적 순위표**"
        output_string = ""

        for user in sorted_list:
            if user.point != prev_point:
                rank += 1
                prev_point = user.point
            
            line = f"**{rank}등**: {guild.get_member(user.id).mention}\t{user.point}점\n"

            output_string += line

        await interaction.response.send_message(embed=discord.Embed(title=title_string, description=output_string, color=discord.Color.blue()))

    @app_commands.command(name="노래추가요청", description="(추가 예정) 곡 데이터베이스에 노래를 추가하고 싶을 때 사용합니다.")
    @app_commands.describe(title="추가 요청할 노래의 제목.")
    @app_commands.describe(artist="추가 요청할 노래의 가수/아티스트.")
    async def song_quiz_add_request(self, interaction: discord.Interaction, title: str, artist: str):
        # TODO: Implement Request.
        await interaction.response.send_message("추가 예정입니다.", ephemeral=True)
        # await interaction.response.send_message(f"곡 **{title}** - *{artist}* 을 추가요청했습니다.")

    @app_commands.command(name="데이터갱신", description="(관리자 전용) 곡 데이터베이스를 새로고침합니다.")
    async def refresh_song_database(self, interaction: discord.Interaction):
        if self.quiz_running:
            await interaction.response.send_message("퀴즈가 진행 중이라 갱신 안된다~", ephemeral=True)
            return

        self.song_database = []
        self.load_song_database()

        await interaction.response.send_message("데이터 갱신 완료.")

    # Loads song data from songs.json.
    def load_song_database(self):
        songs_file = data_dir / "songs.json"

        with open(songs_file, "r", encoding="utf-8") as f:
            song_list = json.load(f)

            for song in song_list:
                track = Track(song["id"], song["title"], song["artist"], yt_uri=song["yt_uri"], yt_vid_title=song["yt_vid_title"], yt_vid_length=song["yt_vid_length"])

                self.song_database.append(track)

    # Gets current song under quiz.
    def get_current_problem(self):
        if not self.quiz_running:
            return None
        
        return self.quiz_sampled_problems[self.quiz_match_songs_played]

    # Samples song pool from song database.
    def sample_quiz_problems(self, song_count: int):
        tracks = random.sample(self.song_database, song_count)
        problems = map(lambda x: Problem(x), tracks)

        self.quiz_sampled_problems = list(problems)

    # Shows current quiz scoreboard.
    async def show_quiz_scoreboard(self, at_end=False):
        guild = self.bot.get_guild(self.quiz_guild_id)
        channel = guild.get_channel(self.quiz_text_channel_id)

        scoreboard_list = self.scoreboard.values()
        sorted_list = sorted(scoreboard_list, key=lambda x: x.point, reverse=True)

        rank = 0
        prev_point = 9999999999
        title_string = "**최종 순위표**" if at_end else "**중간 점검 순위표**"
        output_string = ""
        people = len(scoreboard_list)

        for user in sorted_list:
            if user.point != prev_point:
                rank += 1
                prev_point = user.point
            
            line = f"**{rank}등**: {guild.get_member(user.id).mention}\t{user.point}점"

            if at_end:
                if people - rank > 0:
                    line += f"\t>>**염코인 {people - rank}개** 획득!"
                else:
                    line += f"\t>>염코인 미지급"

            output_string += line + "\n"

        await channel.send(embed=discord.Embed(title=title_string, description=output_string, color=discord.Color.blue()))

    # Run quiz problem.
    async def run_quiz_problem(self):
        guild = self.bot.get_guild(self.quiz_guild_id)
        channel = guild.get_channel(self.quiz_text_channel_id)

        if channel is None:
            print("WHAT? Channel is NONE?")
            self.quiz_running = False
            return

        current_problem = self.get_current_problem()

        if current_problem is None:
            print("WHAT? Current problem is NONE? The quiz is not playing!!")
            return
        
        print(f"Running song quiz.. {current_problem.track}")

        current_problem_index = self.quiz_match_songs_played
        current_match_id = self.match_id

        if current_problem_index == self.quiz_match_songs_total // 2:
            await self.show_quiz_scoreboard()
            await channel.send(f"3초 뒤 다음 문제를 시작할게요.")
            await asyncio.sleep(3)
            

        file_to_play = base_dir.parent / f"songs/{current_problem.track.yt_uri}.opus"
        audio_length = current_problem.track.yt_vid_length

        offset = random.randint(0, audio_length * 2 // 3) if self.use_random_offset else 0
        audio = discord.FFmpegPCMAudio(file_to_play, before_options=f"-ss {offset}", options="-vn")

        self.voice_client.play(audio)
        embed = discord.Embed(
            title=f"**노래 재생 중: [문제 {self.quiz_match_songs_played + 1} / {self.quiz_match_songs_total}]**",
            description="**/답** 명령어로 노래의 제목을 제출하세요.",
            color=discord.Color.blue()
        )

        await channel.send(embed=embed)
        await asyncio.sleep(audio_length - offset + 8)

        # Do nothing if quiz index 
        if current_problem_index == self.quiz_match_songs_played and self.match_id == current_match_id:
            self.quiz_match_songs_played += 1
            excess_embed = discord.Embed(title=f"시간 초과..", description=f"노래가 끝났습니다.\n문제 정답: **{current_problem.track.title}** - *{current_problem.track.artist}*", color=discord.Color.blue())
            await channel.send(embed=excess_embed)

            await asyncio.sleep(1)
            await self.run_quiz_problem()

    # Checks if the quiz has ended, by checking if the number of problems completed is equal to the number of total problems.
    # Otherwise proceed to next problem.
    async def check_quiz_has_ended(self, channel):
        if self.quiz_match_songs_played == self.quiz_match_songs_total:
            # End quiz, since we've played every song in the match.
            voice_client = self.voice_client
            await channel.send("퀴즈가 종료되었어요!")
            await self.show_quiz_scoreboard(at_end=True)
            await channel.send("한 번 더 플레이하려면 **/노래퀴즈** 명령어를 사용하세요.")
            self.quiz_cleanup()

            await asyncio.sleep(10)

            if not self.quiz_running:
                # If not playing quiz after 10 seconds, disconnect from the voice channel.
                await voice_client.disconnect()
        
        else:
            # Show next problem.
            await asyncio.sleep(2)

            await self.run_quiz_problem()

    # Cleanup quiz-related member variables.
    def quiz_cleanup(self):
        self.quiz_running = False
        self.quiz_match_songs_played = -1
        self.quiz_match_songs_total = -1
        self.use_random_offset = False
        self.quiz_text_channel_id = None
        self.quiz_guild_id = None

        self.bot.update_quiz_result(self.scoreboard)
        self.scoreboard = {}

class MiscPlayable(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        super().__init__()

    @app_commands.command(name="쥐테스트", description="해당 인물의 쥐 여부를 판단합니다.")
    @app_commands.describe(name="쥐 여부를 판단할 인물의 이름.")
    async def mouse_test(self, interaction: discord.Interaction, name: str):
        if name in ["윤정민", "노유종", "김희준", "허강민", "김영민", "염승민", "최성훈", "이형민", "신동하", "김원호"]:
            await interaction.response.send_message(f"{name}: 쥐가 맞습니다.")
        elif name.find("성혁") >= 0:
            await interaction.response.send_message(f"{name}: 이 사람은 절대 쥐가 아닙니다. 쥐일 가능성이 존재하지 않습니다.")
        else:
            await interaction.response.send_message(f"{name}: 현재는 쥐가 아닙니다. 하지만 쥐가 될 가능성이 있습니다.")

    @app_commands.command(name="버전", description="봇의 버전과 업데이트 날짜를 보여줍니다.")
    async def version(self, interaction: discord.Interaction):
        content = "버전: v0.0.3\n마지막 업데이트: 2025.10.05\n업데이트 예정 기능: 힌트 개선, 노래 추천/비추천 기능, 노래 추가 요청 기능"
        await interaction.response.send_message(embed=discord.Embed(title="**염민열의 노래퀴즈**", description=content, color=discord.Color.blue()), ephemeral=True)

    @app_commands.command(name="코인", description="보유한 염코인 개수를 봅니다.")
    async def show_coins(self, interaction: discord.Interaction):
        user_id = interaction.user.id

        # If there was no user with that ID, create new one.
        if user_id not in self.bot.user_map:
            self.bot.user_map[user_id] = User(user_id)
        
        coins = self.bot.user_map[user_id].coin

        await interaction.response.send_message(f"{interaction.user.mention} 님의 염코인 보유 개수는 **{coins}개** 입니다.", ephemeral=True)

class GunjaQuizBot(commands.Bot):
    def __init__(self, command_prefix='/', description=None, intents=discord.Intents.default()):
        self.user_map = {}
        self.load_users()

        super().__init__(command_prefix=command_prefix, description=description, intents=intents)

    async def setup_hook(self):
        await self.add_cog(MiscPlayable(self))
        await self.add_cog(SongQuiz(self))
        await self.tree.sync()

    def load_users(self):
        user_file = base_dir / "users.json"

        try:
            with open(user_file, "r", encoding="utf-8") as f:
                content = json.load(f)

                for user_data in content:
                    user = User(user_data["id"], user_data["point"], user_data["coin"])
                    self.user_map[user_data["id"]] = user
        except:
            pass

    def save_users(self):
        user_file = base_dir / "users.json"

        user_list = []

        for user in self.user_map.values():
            user_list.append(user.__dict__)

        with open(user_file, "w", encoding="utf-8") as f:
            json.dump(user_list, f, indent=2, ensure_ascii=False)

    # quiz_scoreboard is dictionary of User.id -> User.
    def update_quiz_result(self, quiz_scoreboard: dict):
        scoreboard_list = quiz_scoreboard.values()

        sorted_list = sorted(scoreboard_list, key=lambda x: x.point, reverse=True)

        # Reward table.
        # 1 person: No reward whatsoever.
        # 2 people: 1 0
        # 3 people: 2 1 0
        # ...
        # n people: (n-1) (n-2) (n-3) ... 0
        # More precisely, person with i-th rank would receive (n - i) coins.

        # If there are ties, the rank is generously determined:
        # ex) Rank is [1 1 2 2 2 3 4 5]
        #     If score was [500 500 400 400 300 200 100 0].
        #     Received coins are [7 7 6 6 6 5 4 3].

        rank = 0
        prev_point = 9999999999
        people = len(sorted_list)

        for user in sorted_list:
            user: User = user
            
            if user.id not in self.user_map:
                self.user_map[user.id] = User(user.id)
            
            acc_user = self.user_map[user.id]

            if user.point != prev_point:
                rank += 1
                prev_point = user.point
            
            received_coins = people - rank
            acc_user.change_coin(received_coins)
            acc_user.change_point(user.point)

        self.save_users()


for cmd in SongQuiz.__cog_app_commands__:
    print("Cog command:", cmd.name)

if __name__ == "__main__":
    load_dotenv()

    bot_token = os.environ.get('DISCORD_TOKEN')
    allowed_guild_id = os.environ.get('ALLOWED_GUILD')
    allowed_user_id = os.environ.get('ALLOWED_USER')

    intents = discord.Intents.default()
    intents.members = True
    intents.message_content = True
    bot = GunjaQuizBot(command_prefix='/', description="대충 설명", intents=intents)
    bot.run(bot_token)