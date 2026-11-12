"""Local-time companionship. Short original messages plus attributed public-domain verse."""
from __future__ import annotations

from datetime import datetime
import random
import time

# Keep every line short enough for the small speech bubble beside the cat
# (about twelve characters fit at the default 0.6x size).
GREETINGS = {
    "morning": [
        "早安！橘子陪你开启今天。",
        "早安，先对自己温柔一点。",
        "新的一天，记得吃早餐。",
        "早安，喝口水再开始。",
        "今天也要照顾好自己。",
        "早安，阳光到你桌边了吗？",
        "不用急着奔跑，慢慢来。",
        "早安，挑件小事一起开始。",
        "早餐吃了吗？元气靠它。",
        "拉开窗帘，给今天一点光。",
    ],
    "noon": [
        "中午好，先去吃饱饭吧。",
        "午饭时间，工作先等等。",
        "辛苦一上午，吃点喜欢的。",
        "电脑要充电，你也要。",
        "放下鼠标，好好吃午饭。",
        "橘子查岗：午饭吃了吗？",
        "吃饱了，让眼睛歇一会儿。",
        "待办放一边，先吃午饭。",
        "中午好，今天想吃什么？",
        "上午忙完了，歇一小会儿。",
    ],
    "afternoon": [
        "下午好，放松肩膀慢慢做。",
        "看看远处，让眼睛歇会儿。",
        "水杯还在吗？喝两口吧。",
        "困了，就起来走两步。",
        "这页做完，伸个懒腰吧。",
        "任务再多，也一件件来。",
        "松口气，不用一直绷着。",
        "陪你值班，也护好腰背。",
        "卡住了？看看窗外吧。",
        "歇一会儿，也算下午茶。",
    ],
    "evening": [
        "累了吗？出去走走散散心。",
        "傍晚好，晚饭吃了吗？",
        "今天辛苦了，看看夜色吧。",
        "下班后的时间留给自己。",
        "累了，就散步放空一下。",
        "晚饭想吃点什么热乎的？",
        "把辛苦放下，橘子接着。",
        "放首喜欢的歌换换心情。",
        "黄昏了，停下来喘口气。",
        "今天有件开心的小事吗？",
    ],
    "late": [
        "夜深了，早点休息吧。",
        "做得够多了，明天再继续。",
        "记下想法，安心收工吧。",
        "晚安，把待办先放下吧。",
        "橘子打哈欠了，你也睡吧。",
        "画个句号，不必都完美。",
        "写下下一步，明天继续。",
        "休息，也是今天的成果。",
        "累了就停下，明天再走。",
        "今天到这里也很好，晚安。",
    ],
    "night": [
        "很晚了，能睡就早点睡。",
        "深夜了，你也要被照顾。",
        "记下没做完的，别硬撑。",
        "夜里安静，早点休息吧。",
        "事情慢慢来，先睡一觉。",
        "现在收工也没关系，晚安。",
    ],
}

GENTLE = [
    "喝口水吧，我帮你看着。", "久坐了？学我伸个懒腰。",
    "看看窗外，世界比屏幕大。", "今天的你也值得温柔。",
    "先做一小步，剩下慢慢来。", "进度慢一点，没有关系。",
    "不用和别人的时钟赛跑。", "没做好，也不代表你不好。",
    "切成小块，第一步不难。", "你可以努力，也可以休息。",
    "脑袋乱了？先收拾一小角。", "抬头松肩，我也伸个懒腰。",
    "先呼口气，我们再看一遍。", "小小的完成，也值得鼓掌。",
    "认真生活，也要记得充电。", "今天不用塞满，留点空白。",
    "喜欢的小事，就是奖励。", "这次没做好，下次换法子。",
    "倒杯水，再回来继续。", "休息不是掉队，是充电。",
]

ENCOURAGEMENT = [
    "每一小步，都算数。", "今天多做一点，就多一点。",
    "扎根也需要时间，别急。", "把注意力放回眼前的小事。",
    "路很长，不必一直奔跑。", "偶尔绕路，也有新风景。",
    "不用每天发光，安稳就好。", "允许自己慢一点、再开始。",
    "完成，比完美更重要。", "认真投入的时间不会白费。",
    "累了，就别急着下结论。", "今天有难，明天也有可能。",
    "先做五分钟，试试看。", "失败只是反馈，别当名字。",
    "想清下一步，就是进展。", "再开始的勇气，值得庆祝。",
    "别等状态完美，先写一行。", "慢慢来，找到自己的节奏。",
    "平凡的一天，也有小惊喜。", "向前有力气，停下也从容。",
    "何妨吟啸且徐行。——苏轼", "诗酒趁年华。——苏轼",
]


def period(hour: int) -> str:
    if 5 <= hour < 11:
        return "morning"
    if 11 <= hour < 14:
        return "noon"
    if 14 <= hour < 18:
        return "afternoon"
    if 18 <= hour < 22:
        return "evening"
    return "late" if hour >= 22 else "night"


class CareScheduler:
    def __init__(self, settings, clock=time.monotonic, rng=None):
        self.settings = settings
        self.clock = clock
        self.rng = rng or random.Random()
        self.last_time = clock()
        self.last_period = ""
        self.last_message = ""

    def choose(self, now=None, greeting=False):
        now = now or datetime.now().astimezone()
        slot = period(now.hour)
        pool = GREETINGS[slot] if greeting else GREETINGS[slot] + GENTLE
        if not greeting and self.settings.quotes:
            pool = pool + ENCOURAGEMENT
        choice = self.rng.choice([s for s in pool if s != self.last_message])
        self.last_message = choice
        return choice

    def welcome(self, now=None):
        now = now or datetime.now().astimezone()
        self.last_period = now.date().isoformat() + period(now.hour)
        self.last_time = self.clock()
        return self.choose(now, greeting=True)

    def due(self, now=None, busy=False):
        if not self.settings.greetings or busy:
            return None
        now = now or datetime.now().astimezone()
        slot = now.date().isoformat() + period(now.hour)
        elapsed = self.clock() - self.last_time
        changed = slot != self.last_period
        if elapsed < 300 or (not changed and elapsed < self.settings.reminder_minutes * 60):
            return None
        self.last_time = self.clock()
        self.last_period = slot
        return self.choose(now, greeting=changed)


MESSAGE_COUNT = sum(map(len, GREETINGS.values())) + len(GENTLE) + len(ENCOURAGEMENT)
