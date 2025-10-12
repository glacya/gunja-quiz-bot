from pathlib import Path
import re
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta

base_dir = Path(__file__).resolve().parent
data_dir = base_dir.parent / "data"
FFMPEG_OPTIONS = {'options': '-vn'}

allowed_user_id = None
allowed_guild_id = None

def set_env(guild, user):
    global allowed_guild_id
    global allowed_user_id

    allowed_guild_id = guild
    allowed_user_id = user

def check_admin(id):
    global allowed_user_id
    return int(id) == int(allowed_user_id)

def check_guild(id):
    global allowed_guild_id
    return int(id) == int(allowed_guild_id)


def get_current_kst_time():
    KST = timezone(timedelta(hours=9))
    return datetime.now(KST).replace(tzinfo=KST)

def datetime_to_str(dt: datetime):
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def datetime_from_str(s: str):
    KST = timezone(timedelta(hours=9))
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)

# Given a string, leave only KR characters and alphabets, numerics.
# Then, convert every uppercase alphabets to lowercase alphabets.
# Used on comparing quiz answer.
def leave_only_kr_en_chars(s: str):
    subbed = re.sub(r'[^가-힣ㄱ-ㅎㅏ-ㅣA-Za-z0-9]', '', s)
    return subbed.lower()

class User:
    def __init__(self, id: int, point: int = 0, coin: int = 1000):
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
    
# Class for transaction records. What did you buy? How much did you cost?
class Transaction:
    TRANSACTION_ID = 0

    TYPE_QUIZ_REWARD = 0
    TYPE_SONG_SKIP = 1
    TYPE_STOCK = 2
    # TYPE_ROOM_UPGRADE = 3
    # TYPE_ROOM_REVENUE = 4

    def __init__(self, uid: int, delta: int, item_type: int, item_id: any, is_buy: bool):
        Transaction.TRANSACTION_ID += 1

        self.tid = Transaction.TRANSACTION_ID,
        self.uid = uid
        self.delta = delta
        self.item_type = item_type
        self.item_id = item_id
        self.is_buy = is_buy
        self.when = get_current_kst_time()

    def from_json(json_dict: dict):
        tid = json_dict["tid"]
        uid = json_dict["uid"]
        delta = json_dict["delta"]
        item_type = json_dict["item_type"]
        item_id = json_dict["item_id"]
        is_buy = json_dict["is_buy"]
        when = datetime_from_str(json_dict["when"])

        transaction = Transaction(uid, delta, item_type, item_id, is_buy)
        transaction.tid = tid
        transaction.when = when
        Transaction.TRANSACTION_ID = max(Transaction.TRANSACTION_ID, tid)

    def to_dict(self):
        value = self.__dict__.copy()
        value["when"] = datetime_to_str(value["when"])

        return value

    def __str__(self):
        transaction_time_str = datetime_to_str(self.when)

        match self.item_type:
            case Transaction.TYPE_QUIZ_REWARD:
                return f"퀴즈 보상\t**{self.delta}**\t{transaction_time_str}"
            case Transaction.TYPE_SONG_SKIP:
                return f"노래 스킵\t**{self.delta}**\t{transaction_time_str}"
            case Transaction.TYPE_STOCK:
                buy_string = "구매" if self.is_buy else "판매"

                return f"주식 거래\t**{self.delta}**\t{transaction_time_str}\t{buy_string}\t*{self.item_id}*"

        return "---"