import random
import json
import discord
from discord import app_commands
from discord.ext import commands

from utils import *

money_color = discord.Color.gold()

class Stock:
    MAX_PRICE = 1000
    DELIST_THRESHOLD = 100

    def __init__(self, id):
        self.id = id
        self.price = random.randint(300, 600)
        self.shift = random.randint(-3, 3)
        self.base_shift = self.shift
        self.delisted = False

    # Adjust the price of the stock, by -6 to 6.
    # self.shift intervenes this process, and put extra delta on price.
    # It would make some stocks tend to have their price increasing, while some other stocks would have their price decreasing.
    def process(self, delist_bonus: float) -> bool:
        price_delta = random.randint(-6, 6) + self.shift

        self.price = max(0, min(Stock.MAX_PRICE, self.price + price_delta))

        if self.price == Stock.MAX_PRICE:
            self.shift = -10
        elif self.price < Stock.MAX_PRICE * 3 // 4 and self.shift <= -10:
            self.shift = self.base_shift - 1

        return self.delist(delist_bonus)

    # Checks if the stock is going to be delisted.
    # It is more likely to be delisted if the market has too many stocks live. It is passed to argument `delist_bonus`.
    def delist(self, delist_bonus: float) -> bool:
        if self.price > Stock.DELIST_THRESHOLD:
            return False

        # 0     if self.price == Stock.DELIST_THRESHOLD.
        # 0.33  if self.price == 0.
        delist_ratio = (Stock.DELIST_THRESHOLD - self.price) / Stock.DELIST_THRESHOLD / 3 + delist_bonus

        if delist_ratio > random.random():
            self.delisted = True
            
            return True
    
    def from_json(json_dict: dict):
        stock = Stock(json_dict["id"])
        stock.price = json_dict["price"]
        stock.shift = json_dict["shift"]
        stock.base_shift = json_dict["base_shift"]
        stock.delisted = json_dict["delisted"]

        return stock

class MarketNotification:
    NOTI_TYPE_DELIST = 0
    NOTI_TYPE_NEW_STOCK = 1

    def __init__(self, noti_type: int, stock: Stock, uids: list[int] = []):
        self.type = noti_type
        self.stock = stock
        self.uids = uids

    @staticmethod
    def of_delist(stock):
        return MarketNotification(MarketNotification.NOTI_TYPE_DELIST, stock)
    
    @staticmethod
    def of_new_stock(stock):
        return MarketNotification(MarketNotification.NOTI_TYPE_NEW_STOCK, stock)

class Market:
    STOCK_NAMES = ["발기훈의박사반", "최진건하이닉스", "염승민의민족", "염민열제국", "쥐희준의퀴즈쇼", "대퀴벌레s", "엠따꿀벌", "군경자동차", "박규순슬라", "코로나퍼뜨린임인수", "전문하사최성훈"
                   "김영플레이스", "윤정민브라더스", "쥐텐도", "윤커머스", "남종국온리팬스", "성혁노인회관", "성혁노인제약", "공병아무것도안함", "노노노종", "쌀동하의재획소", "배신쥐똥갈하",
                   "쥐희준과쥐정민", "저이제짬다찬거같", "주임원사메이커", "야바위마스터동하", "절벽밑으로떨어진방현", "최진건결혼대행", "이현우메이드카페", "유종신용은행", "허강민투폰대리구매점",
                   "원호해결센터", "쓰러진신동하", "모기잡는윤정민", "대주와단둘이", "짱비짱비짱비", "짱비비비휴가", "365절대못하는노유", "금일아침점호는실내점호", "실외점호꼴찌하는염승민",
                   "매일두시간씩근무하라", "김희상궁", "신동하가원샷한소주", "현우테이스트커피", "노인회관이된싸지방", "팬티만남은윤정민", "김익희의매칭어플", "전역1572일늦춰진최진건",
                   "운전중사망한김희준", "김영민쓰리섬커피", "모기물려서풍선된권예준", "포폰보유자최진건", "귀파면서바람부는구성배", "꿀군경", "리그오브군자", "트위스티드윤정민",
                   "김한준의1생활관", "패트리어트대신발사된김원호", "박연웅과의BOQ한방생활", "박연웅안혁진임인수letsgo", "안혁진의고백", "모용종의성은모씨", "새벽밤화장실에서원선재와만나다", "오늘의한준",
                   "테이저건맞고쓰러진염승민", "초대형쥐노르톨트후버", "군자팝혁진헌터스", "박규순의은밀한웹사이트", "야근이너무나도좋은최성훈", "최성훈의50가지그림자", "형냥이긴급보호소",
                   "풋살못하게된허강민", "고죠김원호", "김원호의레식솔랭", "안혁진방현지응원단", "맨시티의극단적패배", "바이브코더허강민", "이터널리턴지금바로다운로", "야추골절윤기훈"
                   ]

    STOCK_DESIRED_CAPACITY = 10

    def __init__(self, bot):
        self.bot = bot
        self.stocks_live = {}
        self.market_under_maintenance = False
        self.notifications = []

    def load_stocks(self):
        stock_file = base_dir / "stocks.json"

        try:
            with open(stock_file, "r", encoding="utf-8") as f:
                stocks = json.load(f)

                for stock_raw in stocks:
                    stock = Stock.from_json(stock_raw)
                    self.stocks_live[stock.id] = stock
        except:
            pass

    def save_stocks(self):
        stock_file = base_dir / "stocks.json"

        with open(stock_file, "w", encoding="utf-8") as f:
            stocks = []

            for stock in self.stocks_live.values():
                stocks.append(stock.__dict__)

            json.dump(stocks, f, indent=2, ensure_ascii=False)

    # Called every 30 minutes.
    # Processes market. It adjusts the stock price, check for delisting, and notify users if there were delists.
    # If there were too much stocks, delist frequently.
    def process_market(self):
        self.market_under_maintenance = True
        delist_bonus = max(0, len(self.stocks_live) - Market.STOCK_DESIRED_CAPACITY) / 20
        delisted_stocks = []

        # Process all stocks.
        for stock in self.stocks_live.values():
            if stock.process(delist_bonus):
                delisted_stocks.append(stock.id)

        # TODO: Destroy stocks.

        

        self.market_under_maintenance = False

        # TODO: Return a dictionary to give notifications.

        self.save_stocks()


        # Finally, spawn a new stock if possible.

        return None

    # Spawns a new stock.
    # It would spawn a new stock based on the random probability.
    # In short, I would like to adjust the number of stocks so that it can ideally at 
    def spawn_stock(self):
        # TODO: Implement.
        pass

    # Buy or sell some stocks for user.
    # Leaves a transaction.
    def transact_stock(self, stock_id: str, uid: int, amount: int):
        # TODO: Implement.
        pass


class GunjaRoom:
    MAX_UPGRADE_CHOICES = 5

    ROOM_UPGRADES = [
        "옷걸이",
        "열쇠",
        "베개",
        "총기함",
        "이불 세트",
        "침대",
        "빗자루",
        "걸레",
        "세면바구니",
        "군장",
        "외출증",
        "일병모",
        "관물함1",

        "책상",
        "전투복",
        "휴지",
        "빨랫대",
        "세제",
        "페브리즈",
        "살충제",
        "펜",
        "정수기",
        "라디에이터",
        "휴가증",
        "상병모",
        "관물함2",

        "약복",
        "라면세트",
        "섬유유연제",
        "슈넬치킨",
        "후리스",
        "추가피복",
        "딸기몽쉘",
        "건조기",
        "TV",
        "에어컨",
        "병장모",
        "관물함3",

        "깔깔이",
        "군자디펜스",
        "태블릿",
        "소주",
        "냉장고",
        "말출휴가증",
        "배달음식",
        "컴퓨터",
        "투폰",
        "공유기",
        "전역모",
        "예비군마크",
        "전역복",
        "군적금계좌"
    ]

    def __init__(self, uid: int):
        # TODO: Add more fields.
        self.uid = uid
        self.revenue = 0

        # Use bitmap or bitvector to store upgrade status easily.
    
    # Upgrade room with the given ID.
    # Note that, the user can upgrade only the first (GunjaRoom.MAX_UPGRADE_CHOICES) non-upgraded things. Be sure to take it.
    def upgrade(self, rid: str):
        # TODO: Implement.
        pass


class RoomManager:
    def __init__(self, bot):
        self.bot = bot
        self.rooms = {}

    def load_rooms(self):
        # TODO: Implement loading room data.
        pass

    # Processes gunja rooms. Called every day.
    def process_rooms(self):
        # TODO: Implement.
        pass

    
    def upgrade_user_room(self, uid: int, rid: str):
        pass


class YeomCoinPlayer(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        self.market = Market(self.bot)
        self.gunja_rooms = RoomManager(self.bot)

        super.__init__()

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
        # TODO: Implement.
        pass

    @app_commands.command(name="주식매입", description="염코인을 사용해 주식을 매입합니다.")
    async def buy_stock(self, interaction: discord.Interaction):
        # TODO: Implement.
        pass
    
    @app_commands.command(name="주식매도", description="주식을 매도하고 염코인을 받습니다.")
    async def sell_stock(self, interaction: discord.Interaction):
        # TODO: Implement.
        pass

    @app_commands.command(name="주식시세", description="주식 시세를 봅니다.")
    async def show_stock_chart(self, interaction: discord.Interaction):
        # TODO: Implement.
        pass

    @app_commands.command(name="주식확인", description="보유한 주식과, 그 정보를 봅니다.")
    async def check_stock(self, interaction: discord.Interaction):
        # TODO: Implement.
        pass

    @app_commands.command(name="생활관확인", description="현재 생활관 상태, 생활관으로 얻은 수익, 구매 가능한 업그레이드를 봅니다.")
    async def check_gunja_room(self, interaction: discord.Interaction):
        # TODO: Implement.
        pass

    @app_commands.command(name="생활관구매", description="염코인을 사용하여 생활관을 업그레이드합니다. 생활관을 업그레이드하면 수익이 생깁니다.")
    async def upgrade_gunja_room(self, interaction: discord.Interaction):
        # TODO: Implement.
        pass

    @app_commands.command(name="거래내역", description="최근 10일간의 거래 내역을 봅니다. 최대 30건.")
    async def check_transactions(self, interaction: discord.Interaction):
        MAX_TRANSACTIONS_DISPLAY = 30

        # TODO: Implement.
        pass