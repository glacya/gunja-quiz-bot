import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
import os
import asyncio
import json
import random
from pathlib import Path

YDL_OPTIONS = {'format': 'bestaudio'}
FFMPEG_OPTIONS = {'options': '-vn'}

base_dir = Path(__file__).resolve().parent
data_dir = base_dir.parent / "data"

def check_admin():
    pass

def check_guild():
    pass

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

class SongQuiz(commands.Cog):
    def __init__(self, bot):
        self.quiz_running = False
        self.quiz_match_songs_played = -1
        self.quiz_match_songs_total = -1
        self.quiz_sampled_songs = []
        self.quiz_guild_id = None
        self.quiz_text_channel_id = None
        self.quiz_current_song_answer = None

        self.bot: commands.Bot = bot
        print(type(self.bot))

        self.voice_client = None

        self.song_database = []
        self.load_song_database()

        super().__init__()

    @app_commands.command(name="노래퀴즈", description="노래 퀴즈를 시작합니다.")
    @app_commands.describe(song_count="퀴즈를 몇 곡 동안 진행할 것인지 적습니다. 최소 10, 최대 50.")
    @app_commands.describe(use_random_offset="")
    async def song_quiz_begin(self, interaction: discord.Interaction, song_count: int, use_random_offset: bool):
        if song_count < 10 or song_count > 50:
            await interaction.response.send_message("퀴즈는 최소 10곡, 최대 50곡까지만 할 수 있어요.")

        if interaction.user.voice is None:
            await interaction.response.send_message("노래 퀴즈를 시작하려면 음성 채널에 입장해야 해요.")
            return
        
        if self.quiz_running:
            await interaction.response.send_message("이미 노래 퀴즈가 진행 중이에요. 퀴즈를 종료하고 싶다면 **/종료** 명령어로 퀴즈를 종료하세요.")
            return

        self.quiz_text_channel_id = interaction.channel_id
        self.quiz_guild_id = interaction.guild_id

        print("Caller:")
        print(self.quiz_text_channel_id)
        print(interaction.guild_id)
        print(interaction.user.id)

        await interaction.response.send_message("노래 퀴즈를 시작할게요!")
        await asyncio.sleep(1)
        await interaction.followup.send("노래를 준비하는 중..")
        await asyncio.sleep(1)

        self.quiz_match_songs_played = 0
        self.quiz_match_songs_total = song_count
        self.quiz_running = True

        channel = interaction.user.voice.channel
        self.voice_client = discord.utils.get(self.bot.voice_clients, guild=interaction.guild)

        if voice_client is None:
            voice_client = await channel.connect()

        # TODO: Implement random song sampling
        # TODO: Revise code, so that it can stream from file
        # TODO: Revise code, so that it can give better UX
        # TODO: Implement optional boolean flag, so that it can support random-offset song quiz

        self.sample_song_pool(song_count)
        self.run_quiz_problem()
    
    @app_commands.command(name="종료", description="노래 퀴즈를 종료합니다.")
    async def song_quiz_end(self, interaction: discord.Interaction):
        if not self.quiz_running:
            await interaction.response.send_message("노래 퀴즈를 시작하지 않았는데요..? 종료할 수 없어요.")
            return
    
        voice_client = interaction.guild.voice_client
        self.quiz_running = False

        if voice_client is None:
            await interaction.response.send_message("뭔가 잘못됐네요. 음성 채팅에 제가 있지 않은데.. 아무튼 노래 퀴즈를 종료할게요.")
            return
        
        await voice_client.disconnect()
        await interaction.response.send_message("퀴즈 종료!\n노래 퀴즈의 랭킹을 보려면 **/랭킹** 명령어를 사용하세요.")

    @app_commands.command(name="제출", description="노래 퀴즈의 답안을 제출합니다.")
    @app_commands.describe(answer="노래 제목의 정답. 띄어쓰기, 특수문자, 대소문자 등은 고려하지 않아도 됩니다.")
    async def song_quiz_submit(self, interaction: discord.Interaction, answer: str):
        # TODO: Implement submit logic.
        # Use username to give points.
        if not self.quiz_running:
            await interaction.response.send_message("노래 퀴즈가 진행 중이지 않아서 제출할 수 없어요.")
            return
        
        

        pass

    @app_commands.command(name="스킵", description="현재 나오는 노래를 스킵하고 다음 문제로 넘어갑니다.")

    @app_commands.command(name="랭킹", description="노래 퀴즈의 랭킹을 봅니다.")
    async def song_quiz_submit(self, interaction: discord.Interaction):
        # TODO: Implement leaderboard logic.

        pass

    @app_commands.command(name="새로고침", description="(관리자 전용) 곡 데이터베이스를 새로고침합니다.")
    async def refresh_song_database(self, interaction: discord.Interaction):
        # TODO: Implement refreshing.
        pass

    # Loads song data from songs.json.
    def load_song_database(self):
        songs_file = data_dir / "songs.json"

        with open(songs_file, "r", encoding="utf-8") as f:
            song_list = json.load(f)

            for song in song_list:
                track = Track(song["id"], song["title"], song["artist"], yt_uri=song["yt_uri"], yt_vid_title=song["yt_vid_title"], yt_vid_length=song["yt_vid_length"])

                self.song_database.append(track)

    # Samples song pool from song database.
    async def sample_song_pool(self, song_count: int):
        return random.sample(self.song_database, song_count)


    # Run quiz problem.
    async def run_quiz_problem(self):
        guild = self.bot.get_guild(self.quiz_guild_id)
        channel = self.quiz_text_channel_id(self.quiz_text_channel_id)
        
        # audio = discord.FFmpegPCMAudio(audio_file, **FFMPEG_OPTIONS)

        # voice_client.play(audio)
        # await interaction.followup.send(f"노래 재생 중! [문제 {self.quiz_match_songs_played + 1} / {self.quiz_match_songs_total}]\n**/제출** 명령어로 노래의 제목을 제출하세요.")

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
        await interaction.response.send_message(f"**염민열의 노래퀴즈**\n버전: v0.0.1\n마지막 업데이트: 2025.10.04")


class GunjaQuizBot(commands.Bot):
    def __init__(self, command_prefix='/', description=None, intents=discord.Intents.default()):
        super().__init__(command_prefix=command_prefix, description=description, intents=intents)
        print("염민열의 노래 퀴즈 시작")

    async def setup_hook(self):
        await self.add_cog(MiscPlayable(self))
        await self.add_cog(SongQuiz(self))
        await self.tree.sync()

if __name__ == "__main__":
    load_dotenv()

    bot_token = os.environ.get('DISCORD_TOKEN')

    intents = discord.Intents.default()
    intents.members = True
    intents.message_content = True
    bot = GunjaQuizBot(command_prefix='/', description="대충 설명", intents=intents)
    bot.run(bot_token)