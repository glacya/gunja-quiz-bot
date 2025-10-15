import random
import json
import threading
import discord
from discord import app_commands
from discord.ext import commands

from utils import *

money_color = discord.Color.gold()

class YeomCoinPlayer(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        super().__init__()

    @app_commands.command(name="코인", description="보유한 염코인 개수를 봅니다.")
    async def show_coins(self, interaction: discord.Interaction):
        user_id = interaction.user.id

        # If there was no user with that ID, create new one.
        if user_id not in self.bot.user_map:
            self.bot.user_map[user_id] = User(user_id)
        
        coins = self.bot.user_map[user_id].coin

        await interaction.response.send_message(f"{interaction.user.mention} 님의 염코인 보유 개수는 **{coins}개** 입니다.", ephemeral=True)

    @app_commands.command(name="코인랭킹", description="보유한 염코인 랭킹을 봅니다.")
    async def show_coin_rank(self, interaction: discord.Interaction):
        users = self.bot.user_map.values()
        sorted_list = sorted(users, key=lambda x: x.coin, reverse=True)

        rank = 0
        prev_coin = 9999999999
        title_string = "**코인 보유 랭킹**"
        output_string = ""

        for user in sorted_list:
            member = interaction.guild.get_member(user.id)

            if member is None:
                continue

            if user.coin != prev_coin:
                rank += 1
                prev_coin = user.coin
            
            line = f"**{rank}등**: {member.mention}\t{user.coin} 염코인"
            output_string += line + "\n"

        await interaction.response.send_message(embed=discord.Embed(title=title_string, description=output_string, color=money_color))

    @app_commands.command(name="코인기록", description="최근 10일간 염코인을 획득하거나 소모한 기록을 봅니다. 최대 30건.")
    async def check_transactions(self, interaction: discord.Interaction):
        transaction_strs = self.bot.show_transactions(interaction.user.id)

        if len(transaction_strs) == 0:
            await interaction.response.send_message("최근 10일간 염코인을 획득하거나 소모하지 않았어요.", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="**염코인 기록**",
            description=f"{interaction.user.mention} 님의 최근 10일간 염코인 기록:\n" + "\n".join(transaction_strs),
            color=money_color
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)