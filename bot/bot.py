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

# Given a string, leave only KR characters and alphabets.
# Then, convert every uppercase alphabets to lowercase alphabets.
# Used on comparing quiz answer.
def leave_only_kr_en_chars(s: str):
    subbed = re.sub(r'[^가-힣ㄱ-ㅎㅏ-ㅣA-Za-z]', '', s)
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
    def __init__(self, id: int, point: int):
        self.id = id
        self.point = point

    def change_point(self, delta: int):
        self.point += delta

class SongQuiz(commands.Cog):
    def __init__(self, bot):
        self.quiz_running = False
        self.quiz_match_songs_played = -1
        self.quiz_match_songs_total = -1
        self.quiz_sampled_songs = []
        self.quiz_guild_id = None
        self.quiz_text_channel_id = None
        self.current_quiz_song_answer = None
        self.quiz_problem_wrong_answers = 0
        self.match_id = 0

        self.bot: commands.Bot = bot
        self.voice_client = None

        self.song_database = []
        self.load_song_database()

        self.use_random_offset = False
        super().__init__()

    @app_commands.command(name="노래퀴즈", description="노래 퀴즈를 시작합니다.")
    @app_commands.describe(song_count="퀴즈를 몇 곡 동안 진행할 것인지 적습니다. 최소 10, 최대 50.")
    @app_commands.describe(random_offset="노래를 무작위 시점에서 재생하는 버전의 노래퀴즈를 합니다. 사용하려면 true로 설정하세요.")
    async def song_quiz_begin(self, interaction: discord.Interaction, song_count: int, random_offset: bool = False):
        if song_count < 10 or song_count > 50:
            await interaction.response.send_message("퀴즈는 최소 10곡, 최대 50곡까지만 할 수 있어요.")
            return

        if interaction.user.voice is None:
            await interaction.response.send_message("노래 퀴즈를 시작하려면 음성 채널에 입장해야 해요.")
            return
        
        if self.quiz_running:
            await interaction.response.send_message("이미 노래 퀴즈가 진행 중이에요. 퀴즈를 종료하고 싶다면 **/종료** 명령어로 퀴즈를 종료하세요.")
            return

        self.quiz_text_channel_id = interaction.channel_id
        self.quiz_guild_id = interaction.guild_id
        await interaction.response.send_message("노래 퀴즈를 시작할게요!")

        self.match_id += 1
        self.quiz_problem_wrong_answers = 0
        self.quiz_match_songs_played = 0
        self.quiz_match_songs_total = song_count
        self.quiz_running = True
        self.sample_song_pool(song_count)
        self.use_random_offset = random_offset

        voice_channel = interaction.user.voice.channel
        self.voice_client = discord.utils.get(self.bot.voice_clients, guild=interaction.guild)

        if self.voice_client is None:
            self.voice_client = await voice_channel.connect()

        await asyncio.sleep(2)

        await self.run_quiz_problem()
    
    @app_commands.command(name="종료", description="노래 퀴즈를 종료합니다.")
    async def song_quiz_end(self, interaction: discord.Interaction):
        if not self.quiz_running:
            await interaction.response.send_message("노래 퀴즈를 시작하지 않았는데 종료하려고 하다니 정말 박규순 같군..")
            return
    
        voice_client = interaction.guild.voice_client
        
        if voice_client is None:
            await interaction.response.send_message("뭔가 잘못됐네요. 음성 채팅에 제가 있지 않은데.. 아무튼 노래 퀴즈를 종료할게요.")
            self.voice_client = None
            return
        
        await voice_client.disconnect()
        await interaction.response.send_message("퀴즈 종료!\n한 번 더 하려면 **/노래퀴즈** 명령어를 사용하세요.\n노래 퀴즈의 랭킹을 보려면 **/랭킹** 명령어를 사용하세요.")

        self.voice_client = None
        self.quiz_cleanup()

    @app_commands.command(name="답", description="노래 퀴즈의 답안을 제출합니다.")  
    @app_commands.describe(answer="노래 제목의 정답. 대소문자, 특수문자, 띄어쓰기는 신경쓰지 않아도 돼요.")
    async def song_quiz_submit(self, interaction: discord.Interaction, answer: str):
        # TODO: Use member to give points.
        if not self.quiz_running:
            await interaction.response.send_message("노래 퀴즈가 진행 중이지 않아서 제출할 수 없어요.")
            return

        current_track = self.get_current_quiz_song()
        correct = SongQuiz.determine_answer_correctness(self.current_quiz_song_answer, answer)

        if current_track is None:
            print("Unexpected error: Cannot load current song.")
            return

        if correct:
            self.voice_client.stop()
            await interaction.response.send_message(f"{interaction.user.mention} 정답!\n정답은 **{current_track.title}** - *{current_track.artist}* 입니다.")
            self.set_new_problem()
            guild = self.bot.get_guild(self.quiz_guild_id)
            channel = guild.get_channel(self.quiz_text_channel_id)

            if self.quiz_match_songs_played == self.quiz_match_songs_total:
                # End quiz, since we've played every song in the match.
                voice_client = self.voice_client
                # TODO: Show scoreboard.
                await channel.send("퀴즈가 종료되었습니다.\n한 번 더 플레이하려면 **/노래퀴즈** 명령어를 사용하세요.")
                self.quiz_cleanup()

                await asyncio.sleep(10)

                if not self.quiz_running:
                    # If not playing quiz after 10 seconds, disconnect from the voice channel.
                    await voice_client.disconnect()
            
            else:
                # Show next problem.
                await channel.send("다음 문제가 곧 옵니다..!")
                await asyncio.sleep(2)

                await self.run_quiz_problem()
                        
        else:
            # TODO: Implement skipping to next quiz, if wrong answers were too much. (over 10)
            self.quiz_problem_wrong_answers += 1
            await interaction.response.send_message(f"오답! <남은 기회: {10 - self.quiz_problem_wrong_answers} / {10}>\n{interaction.user.mention}의 답안: {answer}")

    @app_commands.command(name="스킵", description="현재 나오는 노래를 스킵하고 다음 문제로 넘어갑니다.")
    async def song_quiz_skip(self, interaction: discord.Interaction):
        # TODO: Implement skip logic.
        await interaction.response.send_message("스킵은 아직 구현 중이다 ㅋ")

    @app_commands.command(name="랭킹", description="노래 퀴즈의 랭킹을 봅니다.")
    async def song_quiz_rank(self, interaction: discord.Interaction):
        # TODO: Implement leaderboard logic.

        await interaction.response.send_message("랭킹은 아직 구현 중임.")

    @app_commands.command(name="데이터갱신", description="(관리자 전용) 곡 데이터베이스를 새로고침합니다.")
    async def refresh_song_database(self, interaction: discord.Interaction):
        # TODO: Implement refreshing.
        if self.quiz_running:
            await interaction.response.send_message("퀴즈가 진행 중이라 갱신 안된다~")
            return

        await interaction.response.send_message("데이터갱신은 아직 구현 중이란다.")

    # Loads song data from songs.json.
    def load_song_database(self):
        songs_file = data_dir / "songs.json"

        with open(songs_file, "r", encoding="utf-8") as f:
            song_list = json.load(f)

            for song in song_list:
                track = Track(song["id"], song["title"], song["artist"], yt_uri=song["yt_uri"], yt_vid_title=song["yt_vid_title"], yt_vid_length=song["yt_vid_length"])

                self.song_database.append(track)

    # Gets current song under quiz.
    def get_current_quiz_song(self):
        if not self.quiz_running:
            return None
        
        return self.quiz_sampled_songs[self.quiz_match_songs_played]

    # Samples song pool from song database.
    def sample_song_pool(self, song_count: int):
        self.quiz_sampled_songs = random.sample(self.song_database, song_count)

    # Run quiz problem.
    async def run_quiz_problem(self):
        guild = self.bot.get_guild(self.quiz_guild_id)
        channel = guild.get_channel(self.quiz_text_channel_id)

        if channel is None:
            print("WHAT? Channel is NONE?")
            self.quiz_running = False
            return

        current_track = self.get_current_quiz_song()
        print(f"Running song quiz.. {current_track}")

        if current_track is None:
            print("WHAT? Current song is NONE? The quiz is not playing!!")
            return

        self.current_quiz_song_answer = current_track.title

        file_to_play = base_dir.parent / f"songs/{current_track.yt_uri}.opus"

        offset = random.randint(0, current_track.yt_vid_length * 2 // 3) if self.use_random_offset else 0
        audio = discord.FFmpegPCMAudio(file_to_play, before_options=f"-ss {offset}", options="-vn")

        current_problem_index = self.quiz_match_songs_played
        current_match_id = self.match_id

        self.voice_client.play(audio)
        await channel.send(f"노래 재생 중! [문제 {self.quiz_match_songs_played + 1} / {self.quiz_match_songs_total}]\n**/답** 명령어로 노래의 제목을 제출하세요.")
        await asyncio.sleep(current_track.yt_vid_length - offset + 8)

        # Do nothing if quiz index 
        if current_problem_index == self.quiz_match_songs_played and self.match_id == current_match_id:
            self.set_new_problem()
            await channel.send(f"시간 초과. 정답은 **{current_track.title}** - *{current_track.artist}* 입니다.\n다음 문제를 준비할게요..")
            await asyncio.sleep(1)
            await self.run_quiz_problem()

    # Sets member variables on new problem.
    def set_new_problem(self):
        self.quiz_match_songs_played += 1
        self.quiz_problem_wrong_answers = 0

    # Cleanup quiz-related member variables.
    def quiz_cleanup(self):
        self.quiz_running = False
        self.quiz_match_songs_played = -1
        self.quiz_match_songs_total = -1
        self.quiz_sampled_songs = []
        self.use_random_offset = False

    # Static method. Determines whether `truth` and `submitted` is equal in Quiz context.
    # Returns True if the submitted answer is considered correct, False otherwise.
    def determine_answer_correctness(truth: str, submitted: str):
        # Most song titles have format of [title] ([sub]) (feat. something)
        # I want to acknowledge both `title` and `sub` to be the answer.

        truth_parts = truth.split("(")
        truth_keywords = []

        for part in truth_parts:
            if part.startswith("Feat.") or part.startswith("feat."):
                continue
            truth_keywords.append(leave_only_kr_en_chars(part))
        
        # Do the same thing on user.

        submitted_parts = submitted.split("(")
        submitted_keywords = []

        for part in submitted_parts:
            if part.startswith("Feat.") or part.startswith("feat."):
                continue
            submitted_keywords.append(leave_only_kr_en_chars(part))
        
        # Now given keywords, check if user-submitted keywords are all present in truth keywords.
        for user_keyword in submitted_keywords:
            if user_keyword not in truth_keywords:
                return False
            
        return True

class MiscPlayable(commands.Cog):
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
        await interaction.response.send_message(f"**염민열의 노래퀴즈**\n버전: v0.0.2\n마지막 업데이트: 2025.10.05")


class GunjaQuizBot(commands.Bot):
    def __init__(self, command_prefix='/', description=None, intents=discord.Intents.default()):
        super().__init__(command_prefix=command_prefix, description=description, intents=intents)

    async def setup_hook(self):
        await self.add_cog(MiscPlayable(self))
        await self.add_cog(SongQuiz(self))
        await self.tree.sync()

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