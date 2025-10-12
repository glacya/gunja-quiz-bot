import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
import os
import json
import threading

from utils import *
from quiz import SongQuiz
from yeomcoin import YeomCoinPlayer

misc_color = discord.Color.light_grey()

class MiscCog(commands.Cog):
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
        content = "버전: v2.0.0\n마지막 업데이트: 2025.10.12\n" \
        "업데이트 주요 내역: 노래 추가 기능\n" \
        "업데이트 예정 기능: 없음"
        await interaction.response.send_message(embed=discord.Embed(title="**염민열의 노래퀴즈**", description=content, color=misc_color), ephemeral=True)


class GunjaQuizBot(commands.Bot):
    def __init__(self, command_prefix='/', description=None, intents=discord.Intents.default()):
        self.user_map = {}
        self.transactions = []
        self.transaction_lock = threading.Lock()
        self.load_users()
        self.load_transactions()

        super().__init__(command_prefix=command_prefix, description=description, intents=intents)

    async def setup_hook(self):
        await self.add_cog(MiscCog(self))
        await self.add_cog(SongQuiz(self))
        await self.add_cog(YeomCoinPlayer(self))
        await self.tree.sync()

    # Load users from the disk.
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

    # Save users to the disk.
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

    # Loads transactions from `transactions.json`.
    def load_transactions(self):
        transaction_file = base_dir / "transactions.json"

        try:
            with open(transaction_file, "r", encoding="utf-8") as f:
                raw_tranactions = json.load(f)

                for trans_dict in raw_tranactions:
                    transaction = Transaction.from_json(trans_dict)
                    self.transactions.append(transaction)
                
                self.transactions = sorted(self.transactions, key=lambda x: x.tid)
        except:
            pass
        
        self.filter_transactions()

    # Save transactions from `transactons.json`.
    def save_transactions(self):
        transaction_file = base_dir / "transactions.json"

        with open(transaction_file, "w", encoding="utf-8") as f:
            trans = list(map(lambda x: x.to_dict(), self.transactions))
            
            json.dump(trans, f, indent=2, ensure_ascii=False)

    # Make transaction.
    # Append new transaction to the Bot, process it, and save immediately.
    def make_transaction(self, transaction: Transaction):
        if uid not in self.user_map:
            self.user_map[uid] = User(uid)

        with self.transaction_lock:
            uid = transaction.uid
            
            if self.user_map[uid].change_coin(transaction.delta):
                self.transactions.append(transaction)
                self.save_transactions()

    # Filter out transactions that are too old. (over 10 days)
    def filter_transactions(self):
        def filter_func(transaction: Transaction) -> bool:
            return (get_current_kst_time() - transaction.when).days > 10

        with self.transaction_lock:
            self.transactions = list(filter(filter_func, self.transactions))
            
    # Returns a stringified list of transactions, of the given user.
    def show_transactions(self, uid: int) -> list[str]:
        MAX_TRANSACTIONS_DISPLAY = 30
        filtered = []

        with self.transaction_lock:
            filtered = list(filter(lambda x: x.uid == uid, self.transactions))
        
        user_transactions = sorted(filtered, key=lambda x: x.tid)[-MAX_TRANSACTIONS_DISPLAY:]

        return list(map(str, user_transactions))

    # Get user coins.
    def get_user_coins(self, uid):
        if uid not in self.user_map:
            self.user_map[uid] = User(uid)

        return self.user_map[uid].coin

for cmd in SongQuiz.__cog_app_commands__:
    print("Cog command:", cmd.name)

for cmd in YeomCoinPlayer.__cog_app_commands__:
    print("Cog command:", cmd.name)

if __name__ == "__main__":
    env_path = base_dir / ".env"
    load_dotenv(dotenv_path=env_path)

    bot_token = os.environ.get('DISCORD_TOKEN')
    allowed_guild_id = os.environ.get('ALLOWED_GUILD')
    allowed_user_id = os.environ.get('ALLOWED_USER')

    set_env(allowed_guild_id, allowed_user_id)

    intents = discord.Intents.default()
    intents.members = True
    intents.message_content = True
    bot = GunjaQuizBot(command_prefix='/', description="대충 설명", intents=intents)
    bot.run(bot_token)