r"""Arcade + Skia 製作的黑暗奇幻互動 RPG。

Arcade 負責滑鼠互動與 UI，Skia 動態繪製背景、角色及怪物圖像。

執行：.\.venv\Scripts\python.exe rpg.py
"""

from __future__ import annotations

import ctypes
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum, auto
import json
import math
from pathlib import Path
import random
import sys
from typing import Callable

try:
    import arcade

    import mage
    import paladin
    import rogue
    import warlock
    import warrior
    from rpg_drawing import (
        BLUE,
        SCREEN_HEIGHT,
        SCREEN_TITLE,
        SCREEN_WIDTH,
        RPGDrawingMixin,
        make_activity_background,
        make_activity_frame,
        make_background,
        make_critical_effect,
        make_player_portrait,
        player_gear_tier,
    )
except ImportError as exc:
    raise SystemExit(
        "缺少遊戲套件。Python 3.14 請執行 setup_game.ps1；"
        "其他版本請執行 pip install -r requirements.txt"
    ) from exc

# ---------- Windows IME（中文輸入法）支援 ----------
WM_IME_STARTCOMPOSITION = 0x010D
CFS_POINT = 0x0002
CFS_CANDIDATEPOS = 0x0040

if sys.platform == "win32":
    from ctypes import wintypes

    class _COMPOSITIONFORM(ctypes.Structure):
        _fields_ = (
            ("dwStyle", wintypes.DWORD),
            ("ptCurrentPos", wintypes.POINT),
            ("rcArea", wintypes.RECT),
        )

    class _CANDIDATEFORM(ctypes.Structure):
        _fields_ = (
            ("dwIndex", wintypes.DWORD),
            ("dwStyle", wintypes.DWORD),
            ("ptCurrentPos", wintypes.POINT),
            ("rcArea", wintypes.RECT),
        )

    class _LOGFONTW(ctypes.Structure):
        _fields_ = (
            ("lfHeight", wintypes.LONG),
            ("lfWidth", wintypes.LONG),
            ("lfEscapement", wintypes.LONG),
            ("lfOrientation", wintypes.LONG),
            ("lfWeight", wintypes.LONG),
            ("lfItalic", ctypes.c_byte),
            ("lfUnderline", ctypes.c_byte),
            ("lfStrikeOut", ctypes.c_byte),
            ("lfCharSet", ctypes.c_byte),
            ("lfOutPrecision", ctypes.c_byte),
            ("lfClipPrecision", ctypes.c_byte),
            ("lfQuality", ctypes.c_byte),
            ("lfPitchAndFamily", ctypes.c_byte),
            ("lfFaceName", ctypes.c_wchar * 32),
        )


class Scene(Enum):
    TITLE = auto()
    GUIDE = auto()
    CREATION = auto()
    TALENT = auto()
    SUBCLASS = auto()
    ADVENTURE = auto()
    BATTLE = auto()
    CAMPFIRE = auto()
    SHOP = auto()
    EVENT = auto()
    END = auto()
    SAVE_MENU = auto()


@dataclass
class Player:
    """冒險者的能力、財富與隨身物品。"""

    name: str = "勇者"
    sex: str = "男性"
    race: str = "獸人"
    job: str = "戰士"
    sub_job: str = ""
    lv: int = 1
    hp: int = 20
    max_hp: int = 20
    attack: int = 10
    defense: int = 10
    luck: int = 1
    gold: int = 0
    black_market_lv: int = 0  # 舊版存檔相容欄位，已不再使用
    potions: int = 0  # 舊版存檔相容欄位，讀檔時併入 potion_bag
    potion_bag: dict[str, int] = field(default_factory=dict)
    potion_purchase_counts: dict[str, int] = field(default_factory=dict)
    campfire_shield_ready: bool = False
    talent_points: int = 0
    class_talents: dict[str, dict[str, int]] = field(default_factory=dict)


@dataclass
class Enemy:
    name: str
    kind: str
    rank: int
    level: int
    max_hp: int
    hp: int
    attack: int
    defense: int
    block: int = 0
    intent: str = ""
    stealth_turns: int = 0
    skip_turns: int = 0
    corrosion_turns: int = 0
    corrosion_damage: int = 0
    agony_turns: int = 0
    agony_damage: int = 0
    agony_stacks: int = 0
    doom_turns: int = 0
    doom_damage: int = 0
    weak_turns: int = 0
    weak_multiplier: float = 1.0
    immune_turns: int = 0
    reflect_turns: int = 0
    berserk_stacks: int = 0
    bulwark_stacks: int = 0


@dataclass
class AttackAnimation:
    attacker: str
    damage: int
    critical: bool
    elapsed: float = 0.0
    impacted: bool = False
    enemy_index: int = 0
    blocked_by: str = ""


@dataclass
class FloatingDamage:
    target: str
    amount: int
    critical: bool
    healing: bool = False
    elapsed: float = 0.0
    label: object | None = None
    target_index: int = 0


@dataclass
class SkillVisual:
    skill_id: str
    job: str
    duration: float = .82
    elapsed: float = 0.0


@dataclass
class Button:
    x: float
    y: float
    width: float
    height: float
    label: str
    action: Callable[[], None]
    shortcut: str = ""
    enabled: bool = True
    accent: tuple[int, int, int] = BLUE
    tooltip: str = ""
    talent_id: str = ""
    attention: bool = False
    invisible: bool = False
    decorated: bool = True

    def contains(self, px: float, py: float) -> bool:
        return (
            self.enabled
            and self.hit_test(px, py)
        )

    def hit_test(self, px: float, py: float) -> bool:
        return (
            self.x - self.width / 2 <= px <= self.x + self.width / 2
            and self.y - self.height / 2 <= py <= self.y + self.height / 2
        )




class RPGWindow(RPGDrawingMixin, arcade.Window):
    Scene = Scene
    SKILL_COOLDOWN_TURNS = 1
    LOG_RECORD_LIMIT = 12
    TEXT_CACHE_LIMIT = 1000
    MEASURE_CACHE_LIMIT = 1000

    RACES = (
        ("獸人", "血量 +10"),
        ("人類", "攻擊 +5"),
        ("矮人", "防禦 +5"),
        ("精靈", "幸運 +1"),
    )
    JOBS = (
        ("戰士", "血量 +10；升級時血量成長加倍"),
        ("法師", "攻擊 +5；升級時攻擊成長加倍"),
        ("聖騎士", "防禦 +5；升級時防禦成長加倍"),
        ("盜賊", "幸運 +1；升級時幸運成長加倍"),
        ("術士", "攻擊 +5；擅長腐蝕與吸血續戰"),
    )
    JOB_PAGE_SIZE = 3
    TALENT_POINT_INTERVAL = 2
    MAX_NAME_LENGTH = 10
    SAVE_SLOT_COUNT = 3
    SAVE_DIR = Path(__file__).resolve().parent / "saves"
    SAVE_VERSION = 3
    DIFFICULTY_NAMES = {1: "一星試煉", 2: "二星試煉", 3: "三星試煉"}
    CLASS_PROFILES = {
        "戰士": warrior,
        "法師": mage,
        "聖騎士": paladin,
        "盜賊": rogue,
        "術士": warlock,
    }
    MONSTER_NAMES = {
        1: {
            "血量型": "赤囊沼澤蛙",
            "攻擊型": "裂牙荒原狼",
            "防禦型": "岩殼穴居蟹",
        },
        2: {
            "血量型": "腐血食人魔",
            "攻擊型": "雙刃豺狼人王",
            "防禦型": "黑鐵石像鬼",
        },
        3: {
            "血量型": "噬魂古樹",
            "攻擊型": "猩紅獅鷲領主",
            "防禦型": "符文骸骨巨將",
        },
        4: {
            "血量型": "深淵多首蛇皇",
            "攻擊型": "雷獄翼龍君",
            "防禦型": "玄岩泰坦王",
        },
        5: {
            "血量型": "永夜吞星古神",
            "攻擊型": "猩紅滅世龍皇",
            "防禦型": "黑曜末日神像",
        },
    }
    JOURNEY_STAGES = (
        ("邊境古道", "王城還在遠方，你先穿過荒草與破舊哨塔。"),
        ("灰霧荒野", "王城的外牆已能看見，黑霧也開始變得濃重。"),
        ("斷橋城郊", "你抵達王城外圍，廢村與斷橋擋在前方。"),
        ("王城門前", "城門就在眼前，終焉之主的氣息壓得空氣發沉。"),
    )
    JOURNEY_LORE = (
        (
            "你沿著舊王國的石路前進，遠方的城牆被黑霧遮住。",
            "風穿過倒塌的塔樓，像有人在低聲提醒你小心。",
            "遠方鐘聲響起，荒野裡的怪物開始靠近道路。",
            "你走過長滿銀苔的石橋，橋下傳來沉重的呼吸聲。",
        ),
        (
            "你越過邊境碑，黑霧像潮水一樣貼著地面推來。",
            "王城的尖塔偶爾露出輪廓，又很快被灰霧吞回去。",
            "路旁的旗幟還在飄，但上面的王徽已經被燻黑。",
            "你聽見遠方傳來戰鼓聲，像在催你繼續往前。",
        ),
        (
            "你走進廢棄村落，家家戶戶的門都朝王城方向半開。",
            "斷橋下翻著黑水，橋對面就是王城外圍的舊軍道。",
            "路邊的騎士墓碑越來越多，劍尖全都指向城門。",
            "你離王城更近了，連空氣裡都帶著鐵鏽與火灰味。",
        ),
        (
            "王城大門佇立在黑霧盡頭，門縫裡透出暗紅火光。",
            "終焉之主的低語從城牆後傳來，每一步都像踩在戰鼓上。",
            "城門前的石像轉頭看著你，像在等待最後一位挑戰者。",
            "你已站在王城陰影下，只差最後一段路就能踏入王座廳。",
        ),
    )
    SHOP_LORE = (
        "紫色燈火下，蒙面藥水商把一排藥瓶擺上桌面。",
        "每個藥瓶都閃著奇異的光，商人低聲說：藥效保證，童叟無欺。",
        "商人晃了晃藥瓶，瓶裡的液體像活物一樣旋轉發亮。",
    )
    DIFFICULTY_PROFILES = {
        1: {"turns": (3.0, 5.0), "defense": (.32, .52), "danger_hits": (9.0, 13.0)},
        2: {"turns": (3.0, 5.0), "defense": (.32, .52), "danger_hits": (9.0, 13.0)},
        3: {"turns": (3.0, 5.0), "defense": (.32, .52), "danger_hits": (9.0, 13.0)},
    }
    MAX_DIFFICULTY = 3
    STAR_TOOLTIPS = (
        "標準試煉",
        "進階意圖",
        "雙怪行動",
    )
    DUAL_ENEMY_ATTACK_SCALE = .60
    BOSS_SPLIT_STAT_SCALE = .40
    BATTLE_ACCENT_JOB_SKILL = (135, 92, 54)
    BATTLE_ACCENT_BASIC = (75, 104, 129)
    BATTLE_ACCENT_COOLDOWN = (102, 86, 151)
    BATTLE_ACCENT_ULTIMATE = (150, 80, 55)
    BATTLE_ACCENT_POTION = (71, 127, 85)
    BASIC_CLASS_ACTIONS = frozenset({
        "slash", "guard", "fireball", "ice_armor", "smite", "blessing",
        "stab", "smokescreen", "corruption_bolt", "dark_charm",
    })
    ULTIMATE_CLASS_ACTIONS = frozenset({
        "bladestorm", "meteor", "divine_wrath", "assassinate", "doom",
    })
    CHEAT_PLUS_KEYS = (arcade.key.PLUS, arcade.key.NUM_ADD, arcade.key.EQUAL)
    CHEAT_MINUS_KEYS = (arcade.key.MINUS, arcade.key.NUM_SUBTRACT)
    CHEAT_FIELDS = (
        ("lv", "關卡"),
        ("difficulty", "難度"),
        ("max_hp", "血量上限"),
        ("hp", "目前血量"),
        ("attack", "攻擊"),
        ("defense", "防禦"),
        ("luck", "幸運"),
        ("gold", "金錢"),
        ("potions", "補血藥水"),
        ("talent_points", "天賦點"),
    )
    CHEAT_DROPDOWN_FIELDS = ("lv", "difficulty")
    CHEAT_MAX_DIGITS = 4
    CHEAT_ROW_TOP = 540
    CHEAT_ROW_GAP = 44
    MONSTER_TYPE_MODIFIERS = {
        "血量型": {"hp": 1.25, "damage": .9, "defense": .95},
        "攻擊型": {"hp": .9, "damage": 1.2, "defense": .95},
        "防禦型": {"hp": 1.0, "damage": .9, "defense": 1.12},
    }
    POTIONS = {
        "attack": {"name": "龍牙戰藥", "desc": "下一次攻擊傷害提升 50%。", "base": 24},
        "defense": {"name": "玄鐵護藥", "desc": "下一次防守獲得的護盾提升 50%。", "base": 24},
        "lucky": {"name": "星眼藥劑", "desc": "下一次攻擊必定暴擊。", "base": 34},
        "iron_skin": {"name": "鐵膚藥劑", "desc": "本回合下一次受傷降低 30%。", "base": 30},
        "cleanse_dot": {"name": "驅霧清露", "desc": "清除黑霧持續傷害。", "base": 26},
        "stun_ward": {"name": "醒神清露", "desc": "預先服用，擋下一次昏迷。", "base": 28},
        "reveal": {"name": "破影藥劑", "desc": "驅散目標敵人的隱身。", "base": 22},
        "purify": {"name": "淨化聖露", "desc": "清除黑霧與詛咒，並擋下一次昏迷。", "base": 42},
        "heal": {"name": "月泉靈藥", "desc": "立即恢復 50% 最大血量。", "base": 30},
        "full_heal": {"name": "聖輝仙釀", "desc": "立即恢復全部血量。", "base": 52},
    }
    START_GIFT_EVENT_NUMBER = 31
    EVENT_DECK = (
        {"title": "路邊商人", "background": 9, "options": ("打開貨盒", "婉拒試探"),
         "intro": "黃昏的路邊支著一頂破布小棚，商人把鎖住的木盒推到你面前，笑說裡面可能是補給，也可能是別人的麻煩。"},
        {"title": "舊神像", "background": 4, "options": ("擦亮神像", "低頭祈禱"),
         "intro": "苔痕爬滿倒塌神像，石眼深處仍有微光。你只碰掉一層灰，附近的黑霧就像聽見名字般往後退了半步。"},
        {"title": "廢棄營地", "background": 5, "options": ("搜查包裹", "重燃營火"),
         "intro": "林間營地空無一人，火堆下還壓著溫熱灰燼，幾只旅袋被拖到雨篷底下，像主人只是剛剛離開。"},
        {"title": "奇怪水井", "background": 3, "options": ("汲取井水", "丟石探底"),
         "intro": "一口古井立在荒草中央，井水清得不像這片黑霧之地。水面映出的你慢了半拍，還對你眨了一下眼。"},
        {"title": "倒塌貨車", "background": 1, "options": ("搬開貨箱", "檢查車轍"),
         "intro": "王家貨車翻倒在泥路旁，車輪仍在微微轉動。破布下露出藥瓶與銅幣，也可能壓著還沒觸發的機關。"},
        {"title": "迷路旅人", "background": 10, "options": ("帶他一程", "指一條路"),
         "intro": "披斗篷的旅人攔下你，說自己在霧裡繞了三天。他願意回報幫助，但袖口的泥點不像來自這條路。"},
        {"title": "古老石碑", "background": 2, "options": ("念出碑文", "描下符號"),
         "intro": "山壁旁矗立著裂紋石碑，碑文有一半能讀懂，另一半像在避開你的視線。當你靠近，刻痕開始滲出冷光。"},
        {"title": "雨中的木屋", "background": 5, "options": ("進屋避雨", "敲門等待"),
         "intro": "暴雨忽然壓低天空，一間木屋亮著孤燈。門縫飄出熱茶香，桌上卻只擺著一副碗筷。"},
        {"title": "發光花叢", "background": 10, "options": ("採下花瓣", "繞路觀察"),
         "intro": "路邊花叢像星火般發亮，花粉隨呼吸黏上披風。每朵花都朝著你的方向轉動，彷彿在等你伸手。"},
        {"title": "岔路口", "background": 11, "options": ("走左邊路", "走右邊路"),
         "intro": "一根腐朽路牌立在三叉口，左路有車痕，右路有新鮮腳印。兩邊都安靜得過分，像有人替你清過場。"},
        {"title": "黑市包裹", "background": 9, "options": ("拆開包裹", "藏到路旁"),
         "intro": "你在石縫裡撿到黑蠟封住的包裹，封條沒有署名，只刻著黑市暗記與一句小字：打開前先想清楚。"},
        {"title": "破舊祭壇", "background": 4, "options": ("觸碰微光", "獻上一枚幣"),
         "intro": "半塌祭壇被藤蔓纏住，中心仍燃著指尖大小的光。周圍沒有腳印，卻有許多被拖走的痕跡。"},
        {"title": "斷橋守衛", "background": 6, "options": ("相信近路", "修補木板"),
         "intro": "老守衛坐在斷橋邊擦拭長矛，說橋下水流會吃人。他能指你走近路，但每個字都像在試探你的膽量。"},
        {"title": "銀幣賭局", "background": 9, "options": ("押上一把", "旁觀一輪"),
         "intro": "三個傭兵圍著鐵杯擲銀幣，笑聲在林道裡傳得很遠。他們替你空出位置，桌面卻沒有一枚乾淨的硬幣。"},
        {"title": "受傷斥候", "background": 13, "options": ("替他包紮", "取走情報"),
         "intro": "王城斥候倒在灌木旁，傷口邊緣冒著黑煙。他把染血地圖塞給你，聲音微弱到像隨時會被霧吞掉。"},
        {"title": "烏鴉信使", "background": 11, "options": ("拆開信件", "放飛烏鴉"),
         "intro": "一隻烏鴉落上你的肩甲，爪上綁著無署名信筒。牠不啄也不叫，只用黑亮眼珠盯著你的手。"},
        {"title": "石門謎題", "background": 2, "options": ("按亮符號", "聽門後聲音"),
         "intro": "山壁裂出一扇石門，六個符號依序亮起又熄滅。門後傳來像風又像低語的聲音，催你做出選擇。"},
        {"title": "荒村鐘聲", "background": 5, "options": ("走向鐘樓", "搜尋民宅"),
         "intro": "荒村裡突然響起鐘聲，街上沒有半個人影，窗紙卻同時鼓動。你能感覺整座村子正在醒來。"},
        {"title": "獵人陷阱", "background": 12, "options": ("拆掉陷阱", "順藤追查"),
         "intro": "靴尖勾到一條細線，泥地立刻傳來機簧聲。陷阱不像要殺人，更像要把獵物趕向某個方向。"},
        {"title": "修女藥箱", "background": 13, "options": ("翻找藥品", "閱讀字條"),
         "intro": "路旁石台放著修女留下的藥箱，箱蓋上有聖徽與抓痕。藥瓶排列整齊，旁邊夾著幾張警告字條。"},
        {"title": "騎士墓碑", "background": 8, "options": ("拔出長劍", "致上敬意"),
         "intro": "你走過一排沉默墓碑，最中央的生鏽長劍忽然泛光。風穿過劍格，發出像盔甲碰撞的聲響。"},
        {"title": "精靈商隊", "background": 14, "options": ("提出交易", "詢問路況"),
         "intro": "精靈商隊從樹影間無聲現身，貨車掛滿月銀鈴。領隊願意與你交易，但微笑裡看不出價格是否公平。"},
        {"title": "矮人礦坑", "background": 7, "options": ("進坑查看", "敲擊岩壁"),
         "intro": "舊礦坑深處傳來規律敲打聲，像鎚子也像牙齒。礦車上殘留新鮮礦粉，說明裡面不久前還有人活動。"},
        {"title": "獸人戰鼓", "background": 15, "options": ("循聲前進", "壓低腳步"),
         "intro": "遠方獸人戰鼓震動胸口，鼓點讓血液升溫，也讓黑霧變得厚重。你分不清那是戰前儀式還是陷阱。"},
        {"title": "法師殘卷", "background": 16, "options": ("閱讀殘卷", "封進行囊"),
         "intro": "破舊法師筆記被風吹到你腳邊，書頁自動翻到空白處。墨跡浮出又消散，像還在等待最後一句咒文。"},
        {"title": "聖騎士旗幟", "background": 8, "options": ("扶正旗幟", "取下徽章"),
         "intro": "一面破損聖騎士旗插在泥中，金線被雨水洗得黯淡，卻仍守著一點未熄的光。"},
        {"title": "盜賊暗號", "background": 12, "options": ("照暗號走", "抹掉記號"),
         "intro": "牆上刻著連串盜賊暗號，箭頭指向一條狹窄小徑。筆畫很新，像有人故意留給下一個路過的人。"},
        {"title": "霧中渡船", "background": 17, "options": ("付錢上船", "沿岸尋路"),
         "intro": "濃霧裡靠來一艘無燈小船，船夫藏在斗篷底下不發一語，只把乾枯的手伸到你面前。"},
        {"title": "龍骨碎片", "background": 18, "options": ("拾起碎骨", "就地掩埋"),
         "intro": "石堆裡露出一片燙手龍骨，骨面還殘留焦黑紋路。你靠近時，耳邊像響起遙遠龍吼。"},
        {"title": "王家告示", "background": 11, "options": ("撕下告示", "核對印章"),
         "intro": "舊王家告示貼在斷木牌上，懸賞文字幾乎褪色，紅蠟印章卻仍有魔力在邊緣流動。"},
    )
    EVENT_STAT_KEYS = ("max_hp", "attack", "defense", "gold", "luck")
    EVENT_STAT_LABELS = {
        "max_hp": "血",
        "attack": "攻",
        "defense": "守",
        "gold": "錢",
        "luck": "幸運",
    }
    EVENT_KIND_MULTIPLIERS = {1: 1.00, 2: .64, 3: .49, 4: .41, 5: .35, 6: .31}

    def __init__(self) -> None:
        super().__init__(SCREEN_WIDTH, SCREEN_HEIGHT, SCREEN_TITLE, resizable=False)
        self.background = make_background()
        self.battle_background = make_activity_background("battle")
        self.shop_background = make_activity_background("shop")
        self.campfire_background = make_activity_background("campfire")
        self.event_backgrounds: dict[int, arcade.Texture] = {}
        self.hero_portrait = make_player_portrait("男性", "獸人", "戰士")
        self._monster_portrait_cache: dict[tuple[int, str], arcade.Texture] = {}
        self.enemy_portrait = self.monster_portrait(1, "血量型")
        self.enemy_portraits: list[arcade.Texture] = [self.enemy_portrait]
        self.critical_effect = make_critical_effect()
        self.activity_frame = make_activity_frame(800, 565)
        self._panel_skin_cache: dict[tuple[int, int], arcade.Texture] = {}
        self._button_skin_cache: dict[tuple, arcade.Texture] = {}
        self._bar_skin_cache: dict[tuple, arcade.Texture] = {}
        self._log_card_skin_cache: dict[tuple, arcade.Texture] = {}
        self._scroll_skin_cache: dict[tuple, arcade.Texture] = {}
        self._measure_cache: dict[tuple[str, int, bool], float] = {}
        self._text_cache: dict[tuple, arcade.Text] = {}
        self.scene = Scene.TITLE
        self.player = Player()
        self.enemies: list[Enemy] = []
        self.target_index = 0
        self.battle_action_points = 1
        self.player_actions_left = 1
        self.enemy_turn_order: list[int] = []
        self.enemy_turn_skip_dot = False
        self.acting_enemy_index = 0
        self.boss_split_done = False
        self.enemy_hitboxes: list[tuple[float, float, float, float]] = []
        self.difficulty = 1
        self.creation_step = 0
        self.selected_sex = "男性"
        self.name_input = ""
        self.name_input_focused = False
        self.name_caret_timer = 0.0
        self.selected_race = "獸人"
        self.selected_job = "戰士"
        self.job_page = 0
        self.buttons: list[Button] = []
        self.hovered: Button | None = None
        self.home_confirmation = False
        self.log_scroll = 0
        self.log_scroll_dragging = False
        self.log_scroll_drag_offset = 0.0
        self._log_scroll_geometry: tuple[float, ...] | None = None
        self.messages = []
        self.journey_lore = self.random_journey_lore()
        self.shop_lore = random.choice(self.SHOP_LORE)
        self.victory = False
        self.event_number = 1
        self.event_title = "隨機事件"
        self.event_messages: list[str] = []
        self.event_options: tuple[str, str] = ("靠近查看", "保持距離")
        self.event_resolved = True
        self.event_kind = "random"
        self.final_enemy_name = ""
        self.attack_animation: AttackAnimation | None = None
        self.floating_damage: list[FloatingDamage] = []
        self.skill_effects: list[SkillVisual] = []
        self.pending_turn: str | None = None
        self.battle_delay = 0.0
        self.player_block = 0
        self.enemy_block = 0
        self.player_dot_damage = 0
        self.player_dot_turns = 0
        self.player_dot_stacks = 0
        self.player_curse_turns = 0
        self.enemy_intent = ""
        self.enemy_stealth_turns = 0
        self.player_stun_turns = 0
        self.player_stun_immunity_turns = 0
        self.class_skill_cooldowns: dict[str, int] = {}
        self.mage_ice_barrier_turns = 0
        self.player_attack_immunity_turns = 0
        self.mage_meteor_suppression = 0
        self.mage_mana_shield_used = False
        self.warrior_last_stand_used = False
        self.paladin_guardian_used = False
        self.warlock_soul_link_used = False
        self.skill_cooldown_turns = self.SKILL_COOLDOWN_TURNS
        self.race_skill_cooldown = 0
        self.job_skill_cooldown = 0
        self.sub_job_skill_cooldown = 0
        self.after_subclass = "adventure"
        self.orc_attack_bonus = 0
        self.warrior_attack_bonus = 0
        self.warrior_blood_regen = 0
        self.warrior_blood_regen_turns = 0
        self.forced_critical = False
        self.enemy_skip_turns = 0
        self.stealth_turns = 0
        self.potion_menu_open = False
        self.potion_menu_bounds: tuple[float, float, float, float] | None = None
        self.potions_used_this_turn: set[str] = set()
        self.potion_attack_boost = False
        self.potion_defense_boost = False
        self.potion_iron_skin_turns = 0
        self.cheat_open = False
        self.cheat_dirty = False
        self.cheat_focus: str | None = None
        self.cheat_input = ""
        self.cheat_dropdown: str | None = None
        self._cheat_plus_down = False
        self._cheat_minus_down = False
        self.save_menu_mode = "load"
        self.save_menu_return = Scene.TITLE
        self.save_slots: dict[int, dict | None] = {}
        self.job_clears: dict[str, int] = {}
        self.load_job_progress()
        self.refresh_save_slots()
        self._install_ime_support()
        self.configure_buttons()

    # ---------- IME（中文輸入法浮窗）----------
    IME_NAME_INPUT_POS = (415, 361)  # 名字輸入框下方（視窗客戶區座標，y 向下）
    NAME_INPUT_BOX = (410, 365, 360, 62)  # 名字輸入框（left, bottom, width, height）

    def name_box_hit(self, x: float, y: float) -> bool:
        left, bottom, width, height = self.NAME_INPUT_BOX
        return left <= x <= left + width and bottom <= y <= bottom + height

    def _install_ime_support(self) -> None:
        """讓名字輸入支援中文輸入法（新注音）的組字與選字浮窗；僅 Windows 有效。"""
        self._ime_ready = False
        self._ime_enabled = True
        self._ime_default_context = None
        if sys.platform != "win32":
            return
        handlers = getattr(self, "_event_handlers", None)
        hwnd = getattr(self, "_hwnd", None)
        if handlers is None or not hwnd:
            return
        try:
            imm = ctypes.WinDLL("imm32", use_last_error=True)
        except OSError:
            return
        imm.ImmGetContext.restype = ctypes.c_void_p
        imm.ImmGetContext.argtypes = (ctypes.c_void_p,)
        imm.ImmReleaseContext.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
        imm.ImmAssociateContext.restype = ctypes.c_void_p
        imm.ImmAssociateContext.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
        imm.ImmSetCompositionWindow.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
        imm.ImmSetCandidateWindow.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
        imm.ImmSetCompositionFontW.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
        self._imm32 = imm
        self._ime_ready = True
        # pyglet 沒有處理 WM_IME_*；加掛定位後回傳 None，交回系統顯示預設浮窗。
        handlers.setdefault(WM_IME_STARTCOMPOSITION, self._on_ime_start_composition)

    def _on_ime_start_composition(self, msg: int, wParam: int, lParam: int) -> None:
        self._position_ime_windows()
        return None

    def _position_ime_windows(self) -> None:
        """把 IME 組字與選字浮窗固定在名字輸入框下方。"""
        if not self._ime_ready:
            return
        imm = self._imm32
        himc = imm.ImmGetContext(self._hwnd)
        if not himc:
            return
        try:
            x, y = self.IME_NAME_INPUT_POS
            composition = _COMPOSITIONFORM()
            composition.dwStyle = CFS_POINT
            composition.ptCurrentPos.x = x
            composition.ptCurrentPos.y = y
            imm.ImmSetCompositionWindow(himc, ctypes.byref(composition))
            candidate = _CANDIDATEFORM()
            candidate.dwIndex = 0
            candidate.dwStyle = CFS_CANDIDATEPOS
            candidate.ptCurrentPos.x = x
            candidate.ptCurrentPos.y = y + 36
            imm.ImmSetCandidateWindow(himc, ctypes.byref(candidate))
            font = _LOGFONTW()
            font.lfHeight = -22
            font.lfCharSet = 1  # DEFAULT_CHARSET
            font.lfFaceName = "Microsoft JhengHei"
            imm.ImmSetCompositionFontW(himc, ctypes.byref(font))
        finally:
            imm.ImmReleaseContext(self._hwnd, himc)

    def set_ime_enabled(self, enabled: bool) -> None:
        if not self._ime_ready or enabled == self._ime_enabled:
            return
        if enabled:
            self._imm32.ImmAssociateContext(self._hwnd, self._ime_default_context)
            self._position_ime_windows()
        else:
            previous = self._imm32.ImmAssociateContext(self._hwnd, None)
            if previous:
                self._ime_default_context = previous
        self._ime_enabled = enabled

    def sync_ime_state(self) -> None:
        """只有名字輸入步驟開啟輸入法，避免其他場景誤觸組字。"""
        if not getattr(self, "_ime_ready", False):
            return
        self.set_ime_enabled(
            self.scene == Scene.CREATION
            and self.creation_step == 1
            and not self.home_confirmation
            and not self.cheat_open
        )

    # ---------- 敵人目標（相容舊介面：委派到目前選定的目標） ----------
    @property
    def enemy(self) -> Enemy | None:
        if not self.enemies:
            return None
        return self.enemies[min(self.target_index, len(self.enemies) - 1)]

    @enemy.setter
    def enemy(self, value: Enemy | None) -> None:
        self.enemies = [value] if value else []
        self.target_index = 0

    @property
    def enemy_block(self) -> int:
        return self.enemy.block if self.enemy else 0

    @enemy_block.setter
    def enemy_block(self, value: int) -> None:
        if self.enemy:
            self.enemy.block = value

    @property
    def enemy_intent(self) -> str:
        return self.enemy.intent if self.enemy else ""

    @enemy_intent.setter
    def enemy_intent(self, value: str) -> None:
        if self.enemy:
            self.enemy.intent = value

    @property
    def enemy_stealth_turns(self) -> int:
        return self.enemy.stealth_turns if self.enemy else 0

    @enemy_stealth_turns.setter
    def enemy_stealth_turns(self, value: int) -> None:
        if self.enemy:
            self.enemy.stealth_turns = value

    @property
    def enemy_skip_turns(self) -> int:
        return self.enemy.skip_turns if self.enemy else 0

    @enemy_skip_turns.setter
    def enemy_skip_turns(self, value: int) -> None:
        if self.enemy:
            self.enemy.skip_turns = value

    # ---------- 職業星級進度（難度只往前不往後） ----------
    def progress_path(self) -> Path:
        return self.SAVE_DIR / "progress.json"

    def load_job_progress(self) -> None:
        self.job_clears = {}
        path = self.progress_path()
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        clears = data.get("job_clears") if isinstance(data, dict) else None
        if not isinstance(clears, dict):
            return
        for job, _bonus in self.JOBS:
            try:
                self.job_clears[job] = max(0, min(self.MAX_DIFFICULTY, int(clears.get(job, 0))))
            except (TypeError, ValueError):
                continue

    def save_job_progress(self) -> None:
        try:
            self.SAVE_DIR.mkdir(parents=True, exist_ok=True)
            self.progress_path().write_text(
                json.dumps({"version": 1, "job_clears": self.job_clears},
                           ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            self.log("難度進度寫入失敗。")

    def job_clear_count(self, job: str) -> int:
        try:
            return max(0, min(self.MAX_DIFFICULTY, int(self.job_clears.get(job, 0))))
        except (TypeError, ValueError):
            return 0

    def job_difficulty(self, job: str) -> int:
        return min(self.MAX_DIFFICULTY, self.job_clear_count(job) + 1)

    def record_job_clear(self) -> None:
        job = self.player.job
        before = self.job_clear_count(job)
        after = max(before, min(self.MAX_DIFFICULTY, self.difficulty))
        if after <= before:
            return
        self.job_clears[job] = after
        self.save_job_progress()
        if after >= self.MAX_DIFFICULTY:
            self.log(f"{job}的試煉星星全數點亮，你征服了三星試煉！")
        else:
            self.log(f"{job}點亮第 {after} 顆試煉星星，下一輪將以更高難度開始。")

    def potion_price(self, kind: str) -> int:
        bought = self.potion_purchase_count(kind)
        multiplier = min(3.0, 1.25 ** bought)
        return max(1, int(self.player.lv * self.POTIONS[kind]["base"] * multiplier))

    def potion_purchase_count(self, kind: str) -> int:
        try:
            return max(0, int(self.player.potion_purchase_counts.get(kind, 0)))
        except (TypeError, ValueError):
            return 0

    def cheapest_potion_price(self) -> int:
        return min(self.potion_price(kind) for kind in self.POTIONS)

    def potion_available(self, kind: str) -> bool:
        return self.player.gold >= self.potion_price(kind)

    def potion_count(self, kind: str) -> int:
        try:
            return max(0, int(self.player.potion_bag.get(kind, 0)))
        except (TypeError, ValueError):
            return 0

    def total_potions(self) -> int:
        return sum(self.potion_count(kind) for kind in self.POTIONS)

    def owned_potions(self) -> list[str]:
        return [kind for kind in self.POTIONS if self.potion_count(kind) > 0]

    def potion_stock_summary(self) -> str:
        owned = [
            f"{self.POTIONS[kind]['name']}×{self.potion_count(kind)}"
            for kind in self.owned_potions()
        ]
        return "、".join(owned) if owned else "尚無藥水"

    def battle_potion_usable(self, kind: str) -> bool:
        if self.potion_count(kind) < 1:
            return False
        if kind in self.potions_used_this_turn:
            return False
        if kind == "attack":
            return not self.potion_attack_boost
        if kind == "defense":
            return not self.potion_defense_boost
        if kind == "lucky":
            return not self.forced_critical
        if kind == "iron_skin":
            return self.potion_iron_skin_turns < 1
        if kind == "cleanse_dot":
            return self.player_dot_damage > 0 and self.player_dot_turns > 0
        if kind == "stun_ward":
            return self.player_stun_immunity_turns < 1
        if kind == "reveal":
            return self.enemy_hidden()
        if kind == "purify":
            has_dot = self.player_dot_damage > 0 and self.player_dot_turns > 0
            return has_dot or self.player_stun_immunity_turns < 1
        if kind in ("heal", "full_heal"):
            return self.player.hp < self.player.max_hp
        return False

    def migrate_legacy_potions(self) -> None:
        """把舊版單一藥水數量併入新的藥水袋。"""
        p = self.player
        if not isinstance(p.potion_bag, dict):
            p.potion_bag = {}
        if not isinstance(p.potion_purchase_counts, dict):
            p.potion_purchase_counts = {}
        def clean_count(value: object) -> int:
            try:
                return max(0, int(value))
            except (TypeError, ValueError):
                return 0
        p.potion_bag = {
            kind: clean_count(p.potion_bag.get(kind, 0))
            for kind in self.POTIONS
            if clean_count(p.potion_bag.get(kind, 0)) > 0
        }
        p.potion_purchase_counts = {
            kind: clean_count(p.potion_purchase_counts.get(kind, 0))
            for kind in self.POTIONS
            if clean_count(p.potion_purchase_counts.get(kind, 0)) > 0
        }
        if p.potions > 0:
            p.potion_bag["heal"] = self.potion_count("heal") + p.potions
            p.potions = 0

    def can_open_black_market(self) -> bool:
        return any(self.potion_available(kind) for kind in self.POTIONS)

    def journey_stage_index(self) -> int:
        return min(len(self.JOURNEY_STAGES) - 1, max(0, (self.player.lv - 1) // 5))

    def journey_stage(self) -> tuple[str, str]:
        return self.JOURNEY_STAGES[self.journey_stage_index()]

    def random_journey_lore(self) -> str:
        return random.choice(self.JOURNEY_LORE[self.journey_stage_index()])

    @staticmethod
    def level_label(level: int) -> str:
        return f"第{level}關"

    def track_player_hp(self) -> None:
        """Keep current HP inside the real maximum HP used by the UI."""
        self.player.max_hp = max(1, self.player.max_hp)
        self.player.hp = min(self.player.hp, self.player.max_hp)

    def heal_player(self, amount: int) -> int:
        if amount <= 0:
            return 0
        before = self.player.hp
        self.player.hp = min(self.player.max_hp, self.player.hp + amount)
        self.track_player_hp()
        return self.player.hp - before

    def show_player_heal(self, amount: int) -> None:
        if amount > 0:
            self.floating_damage.append(FloatingDamage("player", amount, False, True))

    def clear_player_dot(self) -> None:
        self.player_dot_damage = 0
        self.player_dot_turns = 0
        self.player_dot_stacks = 0

    def clear_player_curse(self) -> None:
        self.player_curse_turns = 0

    def player_curse_multiplier(self) -> float:
        return .67 if self.player_curse_turns > 0 else 1.0

    def effective_player_attack(self) -> int:
        return max(1, math.ceil(self.player.attack * self.player_curse_multiplier()))

    def effective_player_defense(self) -> int:
        return max(1, math.ceil(self.player.defense * self.player_curse_multiplier()))

    def clear_battle_skill_effects(self) -> None:
        self.orc_attack_bonus = 0
        self.warrior_attack_bonus = 0
        self.warrior_blood_regen = 0
        self.warrior_blood_regen_turns = 0
        for enemy in self.enemies:
            enemy.skip_turns = 0
        self.stealth_turns = 0

    def reset_skills(self) -> None:
        self.race_skill_cooldown = 0
        self.job_skill_cooldown = 0
        self.sub_job_skill_cooldown = 0
        self.forced_critical = False
        self.clear_battle_skill_effects()

    def reset_battle_skill_uses(self) -> None:
        self.race_skill_cooldown = 0
        self.job_skill_cooldown = 0
        self.sub_job_skill_cooldown = 0
        self.class_skill_cooldowns.clear()
        self.mage_ice_barrier_turns = 0
        self.player_attack_immunity_turns = 0
        self.mage_meteor_suppression = 0
        self.mage_mana_shield_used = False
        self.warrior_last_stand_used = False
        self.paladin_guardian_used = False
        self.warlock_soul_link_used = False

    def clear_battle_state(self) -> None:
        self.pending_turn = None
        self.attack_animation = None
        self.skill_effects.clear()
        self.player_block = 0
        self.player_dot_damage = 0
        self.player_dot_turns = 0
        self.player_dot_stacks = 0
        self.player_curse_turns = 0
        for enemy in self.enemies:
            enemy.block = 0
            enemy.intent = ""
            enemy.stealth_turns = 0
            enemy.immune_turns = 0
            enemy.reflect_turns = 0
            enemy.berserk_stacks = 0
            enemy.bulwark_stacks = 0
        self.enemy_turn_order = []
        self.enemy_turn_skip_dot = False
        self.acting_enemy_index = 0
        self.potion_menu_open = False
        self.potions_used_this_turn.clear()
        self.potion_attack_boost = False
        self.potion_defense_boost = False
        self.forced_critical = False
        self.player_stun_turns = 0
        self.player_stun_immunity_turns = 0
        self.potion_iron_skin_turns = 0
        self.class_skill_cooldowns.clear()
        self.mage_ice_barrier_turns = 0
        self.player_attack_immunity_turns = 0
        self.mage_meteor_suppression = 0
        self.mage_mana_shield_used = False
        self.warrior_last_stand_used = False
        self.paladin_guardian_used = False

    def class_profile(self):
        return self.CLASS_PROFILES.get(self.player.job)

    def class_talents(self) -> dict[str, int]:
        return self.player.class_talents.setdefault(self.player.job, {})

    def class_talent_defs(self) -> dict[str, dict]:
        profile = self.class_profile()
        return profile.TALENTS if profile else {}

    def has_class_talents(self) -> bool:
        return self.class_profile() is not None

    def class_talent_rank(self, talent_id: str) -> int:
        return self.class_talents().get(talent_id, 0)

    def class_talent_tooltip(self, talent_id: str) -> str:
        talent = self.class_talent_defs()[talent_id]
        lines = [str(talent["name"])]
        details = [str(line) for line in talent.get("details", ())]
        if int(talent["max"]) == 1:
            details = [
                detail.removeprefix("1點：").removeprefix("1點:")
                for detail in details
            ]
        lines.extend(details)
        return "\n".join(lines)

    def class_talent_spent(self) -> int:
        return sum(self.class_talents().values())

    def class_tier_spent(self, tier: int) -> int:
        talents = self.class_talent_defs()
        return sum(
            rank for talent_id, rank in self.class_talents().items()
            if talents[talent_id]["tier"] == tier
        )

    def class_talent_can_add(self, talent_id: str) -> bool:
        if not self.has_class_talents() or self.player.talent_points < 1:
            return False
        talents = self.class_talent_defs()
        talent = talents[talent_id]
        tier = int(talent["tier"])
        if self.class_talent_rank(talent_id) >= int(talent["max"]):
            return False
        if tier > 1 and self.class_tier_spent(tier - 1) < 3:
            return False
        return True

    def learn_class_talent(self, talent_id: str) -> None:
        if not self.class_talent_can_add(talent_id):
            return
        talents = self.class_talents()
        talents[talent_id] = self.class_talent_rank(talent_id) + 1
        self.player.talent_points -= 1
        self.configure_buttons()

    def reset_class_talents(self) -> None:
        spent = self.class_talent_spent()
        if spent < 1:
            return
        self.player.talent_points += spent
        self.class_talents().clear()
        self.class_skill_cooldowns.clear()
        self.log(f"你重置了{self.player.job}天賦，所有點數已返還。")
        self.configure_buttons()

    def open_talent_page(self) -> None:
        if not self.has_class_talents():
            return
        self.scene = Scene.TALENT
        self.configure_buttons()

    def close_talent_page(self) -> None:
        self.scene = Scene.ADVENTURE
        self.configure_buttons()

    def class_action_ready(self, action_id: str) -> bool:
        return self.class_skill_cooldowns.get(action_id, 0) < 1

    TARGETED_CLASS_ACTIONS = frozenset({
        "slash", "cleave", "counter", "bladestorm",
        "fireball", "pyroblast", "meteor",
        "smite", "judgment", "divine_wrath",
        "stab", "backstab", "shadowstep", "assassinate",
        "corruption_bolt", "agony", "hex", "doom",
    })
    TARGETED_LEGACY_JOBS = frozenset({"盜賊", "術士"})

    def enemy_hidden(self) -> bool:
        return self.enemy_stealth_turns > 0

    def attack_skill_enabled(self, enabled: bool = True) -> bool:
        return enabled and not self.enemy_hidden()

    def class_action_enabled(self, action_id: str, enabled: bool = True) -> bool:
        if action_id in self.TARGETED_CLASS_ACTIONS:
            return self.attack_skill_enabled(enabled)
        return enabled

    def job_skill_enabled(self, job: str | None, enabled: bool = True) -> bool:
        if (job or self.player.job) in self.TARGETED_LEGACY_JOBS:
            return self.attack_skill_enabled(enabled)
        return enabled

    def class_action_label(self, action_id: str, name: str) -> str:
        cooldown = self.class_skill_cooldowns.get(action_id, 0)
        if cooldown >= 99:
            return f"{name} 已用"
        if cooldown > 0:
            return f"{name} CD{cooldown}"
        return name

    def battle_class_action_accent(self, action_id: str) -> tuple[int, int, int]:
        if action_id in self.BASIC_CLASS_ACTIONS:
            return self.BATTLE_ACCENT_BASIC
        if action_id in self.ULTIMATE_CLASS_ACTIONS:
            return self.BATTLE_ACCENT_ULTIMATE
        return self.BATTLE_ACCENT_COOLDOWN

    def reduce_class_cooldowns(self) -> None:
        for skill_id, cooldown in list(self.class_skill_cooldowns.items()):
            if 0 < cooldown < 99:
                self.class_skill_cooldowns[skill_id] = cooldown - 1

    def trigger_mage_mana_shield(self) -> bool:
        profile = self.class_profile()
        prevent = getattr(profile, "prevent_death", None)
        prevented = bool(prevent and prevent(self))
        if prevented:
            passive_effects = {
                "戰士": "last_stand",
                "法師": "mana_shield",
                "聖騎士": "guardian_angel",
                "術士": "soul_link",
            }
            effect_id = passive_effects.get(self.player.job)
            if effect_id:
                self.trigger_skill_effect(effect_id, self.player.job, duration=1.05)
        return prevented

    def race_talent_name_for(self, race: str) -> str:
        return {
            "獸人": "餘燼體魄",
            "人類": "百鍊成鋼",
            "矮人": "尋金本能",
            "精靈": "命運眷顧",
        }[race]

    def job_skill_name(self, job: str | None = None) -> str:
        job = job or self.player.job
        return self.CLASS_PROFILES[job].LEGACY_NAME

    def race_talent_description(self, race: str | None = None) -> str:
        race = race or self.player.race
        return {
            "獸人": "營火回血 50%，下場獲得 15% 護盾。",
            "人類": "營火的攻擊、防禦與幸運提升改為 20%。",
            "矮人": "營火金錢整備獲得的金錢加倍。",
            "精靈": "事件出現負面加成的機率降低 20%。",
        }[race]

    def job_skill_description(self, job: str | None = None) -> str:
        job = job or self.player.job
        return self.CLASS_PROFILES[job].LEGACY_DESCRIPTION

    def job_skill_tooltip(self, job: str | None = None) -> str:
        return self.job_skill_description(job)

    def skill_label(self, name: str, cooldown: int, active: bool = False) -> str:
        if cooldown > 0:
            return f"{name} 已用"
        if active:
            return f"{name} 生效中"
        return name

    def job_skill_ready(self, job: str | None = None, cooldown: int | None = None) -> bool:
        if cooldown is None:
            cooldown = self.job_skill_cooldown
        if cooldown > 0:
            return False
        job = job or self.player.job
        return self.CLASS_PROFILES[job].legacy_ready(self)

    def job_skill_active(self, job: str | None = None) -> bool:
        job = job or self.player.job
        return self.CLASS_PROFILES[job].legacy_active(self)

    def activate_job_skill(self, job: str) -> bool:
        return self.CLASS_PROFILES[job].activate_legacy(self)

    def use_job_skill(self, job: str | None = None, secondary: bool = False) -> None:
        if self.scene != Scene.BATTLE or not self.enemy or self.battle_busy:
            return
        cooldown = self.sub_job_skill_cooldown if secondary else self.job_skill_cooldown
        if cooldown > 0:
            return
        selected_job = job or self.player.job
        if selected_job == self.player.sub_job and not secondary:
            secondary = True
        if not self.job_skill_enabled(selected_job):
            return
        if not self.job_skill_ready(selected_job, cooldown):
            return
        if not self.activate_job_skill(selected_job):
            return
        legacy_effects = {
            "戰士": "blood_ritual",
            "法師": "fate_rewrite",
            "聖騎士": "divine_protection",
            "盜賊": "sap",
            "術士": "soul_drain",
        }
        self.trigger_skill_effect(legacy_effects[selected_job], selected_job, duration=.95)
        if secondary:
            self.sub_job_skill_cooldown = self.skill_cooldown_turns
        else:
            self.job_skill_cooldown = self.skill_cooldown_turns
        self.finish_skill_action(legacy_effects[selected_job])

    # ---------- character creation ----------
    def open_guide(self) -> None:
        self.scene = Scene.GUIDE
        self.configure_buttons()

    def start_creation(self) -> None:
        self.scene = Scene.CREATION
        self.creation_step = 0
        self.selected_sex = "男性"
        self.name_input = ""
        self.name_input_focused = False
        self.job_page = 0
        self.configure_buttons()

    def next_creation_step(self) -> None:
        if self.creation_step == 1 and not self.name_input.strip():
            return
        self.creation_step += 1
        self.configure_buttons()

    def add_name_text(self, text: str) -> None:
        self.name_input_focused = True
        self.name_caret_timer = 0.0
        if not text:
            return
        cleaned = "".join(character for character in text if character not in "\r\n\t").strip()
        if not cleaned:
            return
        available = self.MAX_NAME_LENGTH - len(self.name_input)
        if available <= 0:
            return
        self.name_input += cleaned[:available]
        self.configure_buttons()

    def choose_sex(self, sex: str) -> None:
        self.selected_sex = sex
        self.name_input = ""
        self.name_input_focused = False
        self.creation_step = 1
        self.configure_buttons()

    def choose_race(self, race: str) -> None:
        self.selected_race = race
        self.creation_step = 3
        self.job_page = 0
        self.configure_buttons()

    def job_summary(self, job: str) -> str:
        return {
            "戰士": "高血量，血祭爆發與護盾反擊",
            "法師": "高攻擊，火冰法術與意圖干擾",
            "聖騎士": "高防禦，護盾、治療與保命",
            "盜賊": "高幸運，暴擊、隱身與控制",
            "術士": "腐蝕傷害，吸血並削弱敵人",
        }[job]

    def visible_jobs(self) -> tuple[tuple[str, str], ...]:
        start = self.job_page * self.JOB_PAGE_SIZE
        return self.JOBS[start:start + self.JOB_PAGE_SIZE]

    def max_job_page(self) -> int:
        return max(0, math.ceil(len(self.JOBS) / self.JOB_PAGE_SIZE) - 1)

    def change_job_page(self, direction: int) -> None:
        self.job_page = max(0, min(self.max_job_page(), self.job_page + direction))
        self.configure_buttons()

    def choose_job(self, job: str) -> None:
        self.selected_job = job
        self.choose_difficulty(self.job_difficulty(job))

    def choose_difficulty(self, difficulty: int) -> None:
        self.difficulty = difficulty
        p = Player(
            name=self.name_input.strip(), sex=self.selected_sex,
            race=self.selected_race, job=self.selected_job,
        )
        if p.sex == "男性":
            p.defense += 5
        else:
            p.luck += 1
        race_bonus = {
            "獸人": (10, 0, 0, 0), "人類": (0, 5, 0, 0),
            "矮人": (0, 0, 5, 0), "精靈": (0, 0, 0, 1),
        }[p.race]
        job_bonus = {
            "戰士": (10, 0, 0, 0), "法師": (0, 5, 0, 0),
            "聖騎士": (0, 0, 5, 0), "盜賊": (0, 0, 0, 1),
            "術士": (0, 5, 0, 0),
        }[p.job]
        hp_bonus = race_bonus[0] + job_bonus[0]
        p.max_hp += hp_bonus
        p.hp += hp_bonus
        p.attack += race_bonus[1] + job_bonus[1]
        p.defense += race_bonus[2] + job_bonus[2]
        p.luck += race_bonus[3] + job_bonus[3]
        p.potion_bag["heal"] = 1
        self.player = p
        self.skill_cooldown_turns = self.SKILL_COOLDOWN_TURNS
        self.reset_skills()
        self.clear_battle_state()
        self.after_subclass = "adventure"
        self.hero_portrait = make_player_portrait(p.sex, p.race, p.job, p.lv)
        self.messages = [f"開始旅程：{p.name}｜{p.race}{p.job}｜{self.level_label(p.lv)}"]
        self.log_scroll = 0
        self.journey_lore = self.random_journey_lore()
        self.open_start_gift_event()
        self.configure_buttons()

    # ---------- journey ----------
    def open_start_gift_event(self) -> None:
        self.event_number = self.START_GIFT_EVENT_NUMBER
        self.event_title = "啟程贈禮"
        self.event_options = ("收下靈藥", "繫上腰帶")
        self.event_resolved = False
        self.event_kind = "start_gift"
        self.event_messages = []
        self.scene = Scene.EVENT
        self.log("城門藥師把一瓶月泉靈藥交到你手上。瓶中銀光像小小月泉，足以在危急時修補半身傷勢。")

    def continue_journey(self) -> None:
        self.journey_lore = self.random_journey_lore()
        self.log(self.journey_lore)
        self.start_battle()

    def should_open_campfire(self) -> bool:
        return 3 <= self.player.lv <= 19 and self.player.lv % 2 == 1

    def open_campfire(self) -> None:
        self.scene = Scene.CAMPFIRE
        self.log("你在黑霧間找到一處營火，可以短暫整備。")
        self.configure_buttons()

    def finish_campfire(self) -> None:
        self.resolve_event()
        if self.scene == Scene.EVENT:
            self.configure_buttons()

    def choose_campfire_rest(self) -> None:
        recovery_rate = .50 if self.player.race == "獸人" else .33
        restored = self.heal_player(max(1, math.ceil(self.player.max_hp * recovery_rate)))
        self.log(f"你靠著營火休息，恢復 {restored} 點血量。")
        if self.player.race == "獸人":
            self.player.campfire_shield_ready = True
            shield = max(1, math.ceil(self.player.max_hp * .15))
            self.log(f"餘燼體魄蓄住熱力，下一場戰鬥開始時獲得 {shield} 點護盾。")
        self.finish_campfire()

    def choose_campfire_stat(self, stat: str) -> None:
        ability_rate = .20 if self.player.race == "人類" else .10
        if stat == "attack":
            amount = max(1, math.ceil(self.player.attack * ability_rate))
            self.player.attack += amount
            self.log(f"你磨利武器，攻擊 +{amount}。")
        elif stat == "defense":
            amount = max(1, math.ceil(self.player.defense * ability_rate))
            self.player.defense += amount
            self.log(f"你修補護具，防禦 +{amount}。")
        elif stat == "luck":
            amount = max(1, math.ceil(self.player.luck * ability_rate))
            self.player.luck += amount
            self.log(f"你整理行囊與路線，幸運 +{amount}。")
        elif stat == "gold":
            multiplier = 2 if self.player.race == "矮人" else 1
            amount = max(1, self.player.lv * 60 * multiplier)
            self.player.gold += amount
            self.log(f"你在營火旁整理戰利品，金錢 +{amount}G。")
        self.finish_campfire()

    def continue_after_battle_reward(self) -> None:
        if self.should_open_campfire():
            self.open_campfire()
        else:
            self.resolve_event()
            if self.scene == Scene.EVENT:
                self.configure_buttons()

    # ---------- potion merchant ----------
    def open_black_market(self) -> None:
        """開啟藥水商：沒有冷卻，只要買得起任一瓶就能進門。"""
        if self.scene != Scene.ADVENTURE or not self.can_open_black_market():
            return
        self.scene = Scene.SHOP
        self.shop_lore = random.choice(self.SHOP_LORE)
        self.log("霧巷盡頭亮起紫色燈火，藥水商掀開了攤位的布簾。")
        self.configure_buttons()

    def leave_black_market(self) -> None:
        self.log("你收好藥瓶離開攤位，紫色燈火在身後慢慢熄滅。")
        self.scene = Scene.ADVENTURE
        self.configure_buttons()

    def buy_potion(self, kind: str) -> None:
        if not self.potion_available(kind):
            return
        price = self.potion_price(kind)
        self.player.gold -= price
        self.player.potion_bag[kind] = self.potion_count(kind) + 1
        self.player.potion_purchase_counts[kind] = self.potion_purchase_count(kind) + 1
        spec = self.POTIONS[kind]
        self.log(f"購買成功：{spec['name']} ×1（{spec['desc']}）")
        if not self.can_open_black_market():
            self.log("你的錢不夠再買了，藥水商把藥瓶收回箱子。")
            self.leave_black_market()
            return
        self.configure_buttons()

    # ---------- battle ----------
    def monster_rank(self) -> int:
        lv = self.player.lv
        if lv >= 21:
            return 6
        if 4 < lv < 10:
            return random.randint(1, 2)
        if 9 < lv < 15:
            return random.randint(2, 3)
        if 14 < lv < 20:
            return random.randint(3, 4)
        if lv == 20:
            return 5
        return 1

    def build_enemy(self, rank: int, kind: str, dual: bool) -> Enemy:
        profile = self.DIFFICULTY_PROFILES[self.difficulty]
        type_mod = self.MONSTER_TYPE_MODIFIERS[kind]
        target_turns = random.uniform(*profile["turns"])
        defense_ratio = random.uniform(*profile["defense"]) * type_mod["defense"]
        defense = max(0, math.ceil(self.player.attack * defense_ratio))
        expected_player_damage = max(1, self.player.attack)
        hp = max(1, math.ceil(expected_player_damage * target_turns * type_mod["hp"]))
        target_hits_to_defeat_player = random.uniform(*profile["danger_hits"])
        expected_enemy_damage = max(
            1,
            math.ceil((self.player.max_hp / target_hits_to_defeat_player) * type_mod["damage"]),
        )
        attack = math.ceil(self.player.defense * .70) + expected_enemy_damage
        if dual:
            attack = max(1, math.ceil(attack * self.DUAL_ENEMY_ATTACK_SCALE))
        monster_name = "魔王" if rank == 6 else self.MONSTER_NAMES[rank][kind]
        return Enemy(monster_name, kind, rank, self.player.lv, hp, hp, attack, defense)

    def start_battle(self) -> None:
        rank = self.monster_rank()
        dual = self.difficulty >= 3 and rank != 6
        if dual:
            kinds = random.sample(("血量型", "攻擊型", "防禦型"), 2)
        else:
            kinds = [random.choice(("血量型", "攻擊型", "防禦型"))]
        self.enemies = [self.build_enemy(rank, kind, dual) for kind in kinds]
        self.target_index = 0
        self.enemy_portraits = [self.monster_portrait(rank, e.kind) for e in self.enemies]
        self.enemy_portrait = self.enemy_portraits[0]
        self.battle_action_points = 2 if dual else 1
        self.boss_split_done = False
        self.scene = Scene.BATTLE
        self.clear_battle_state()
        self.player_actions_left = self.battle_action_points
        self.floating_damage.clear()
        self.clear_battle_skill_effects()
        self.reset_battle_skill_uses()
        if self.player.campfire_shield_ready:
            shield = max(1, math.ceil(self.player.max_hp * .15))
            self.player_block += shield
            self.player.campfire_shield_ready = False
            self.log(f"餘燼體魄化作護盾，戰鬥開始時獲得 {shield} 點護盾。")
        self.choose_enemy_intent()
        battle_omens = {
            1: "路旁的枯枝突然折斷，有怪物從黑霧裡靠近。",
            2: "沉重腳步震動地面，一頭強大的怪物擋住去路。",
            3: "古戰場的旗幟自己飄動，亡者的強敵醒了過來。",
            4: "天空被巨大影子遮住，一聲咆哮震過山谷。",
            5: "猩紅王座從深淵升起，終焉之主準備開戰。",
        }
        battle_omens[6] = "第21關：魔王現身，狂暴與壁壘會讓戰鬥越拖越危險。"
        self.log(battle_omens[rank])
        if dual:
            first, second = self.enemies
            self.log(f"{first.name}與{second.name}同時擋住去路！點擊怪物可切換攻擊目標。")
            self.log("三星試煉：每回合可使用兩個技能。")
        else:
            self.log(f"{self.enemy.name}出現了。它偏向{kinds[0][:-1]}，準備攻擊你。")
        self.log("你掌握先機，先取得行動機會。")
        if self.scene == Scene.BATTLE:
            self.configure_buttons()

    @property
    def battle_busy(self) -> bool:
        return self.attack_animation is not None or self.pending_turn is not None

    def queue_turn(self, who: str, delay: float = .32) -> None:
        if who == "enemy" and not self.enemy_turn_order:
            self.enemy_turn_order = [
                index for index, enemy in enumerate(self.enemies) if enemy.hp > 0
            ]
        self.potion_menu_open = False
        self.pending_turn = who
        self.battle_delay = delay
        self.configure_buttons()

    def enemy_intent_pool(self, enemy: Enemy | None = None) -> tuple[str, ...]:
        enemy = enemy or self.enemy
        level = enemy.level if enemy else self.player.lv
        if self.difficulty >= 2:
            pool = [
                "attack", "defend", "dot", "curse",
                "stun", "immune", "reflect", "cleanse",
            ]
            if level >= 21:
                pool.extend(("berserk", "bulwark"))
            return tuple(pool)
        pool = ["attack", "defend"]
        if level >= 6:
            pool.extend(("dot", "curse"))
        if level >= 11:
            pool.extend(("stun", "immune"))
        if level >= 16:
            pool.extend(("reflect", "cleanse"))
        if level >= 21:
            pool.extend(("berserk", "bulwark"))
        return tuple(pool)

    def choose_enemy_intent(self) -> None:
        for enemy in self.enemies:
            if enemy.hp > 0:
                enemy.intent = random.choice(self.enemy_intent_pool(enemy))

    def enemy_intent_label(self, enemy: Enemy | None = None) -> str:
        enemy = enemy or self.enemy
        if not enemy:
            return ""
        if enemy.skip_turns > 0:
            return "昏迷中，無法行動"
        if not enemy.intent:
            enemy.intent = random.choice(self.enemy_intent_pool(enemy))
        attack_multiplier = enemy.weak_multiplier if enemy.weak_turns > 0 else 1.0
        dot_damage = max(1, math.ceil(enemy.attack * .33))
        intent_labels = {
            "defend": f"防守 +{max(1, enemy.defense)} 護盾",
            "attack": f"攻擊 {max(1, math.ceil(enemy.attack * attack_multiplier))}",
            "dot": f"黑霧：每回合 {dot_damage} 傷害，3 回合",
            "curse": "詛咒：攻防 -33%，3 回合",
            "stun": "昏迷：跳過玩家下一次行動",
            "immune": "免疫：擋下一次受到的傷害",
            "reflect": "反彈：1 回合內反彈 50% 傷害",
            "cleanse": "淨化：清除持續傷害與弱化",
            "berserk": f"狂暴：攻擊 +{max(1, math.ceil(enemy.attack * .10))}",
            "bulwark": f"壁壘：防禦 +{max(1, math.ceil(enemy.defense * .10))}",
        }
        return intent_labels.get(enemy.intent, "")

    def end_player_action(self) -> None:
        """消耗一點行動後，決定續行或輪到敵方。"""
        if self.scene != Scene.BATTLE:
            return
        if self.player_actions_left > 0 and self.enemies:
            self.configure_buttons()
        else:
            self.expire_player_turn_statuses()
            self.queue_turn("enemy")

    def spend_skill_action(self, action_id: str) -> None:
        if action_id in self.ULTIMATE_CLASS_ACTIONS:
            self.player_actions_left = 0
        else:
            self.player_actions_left = max(0, self.player_actions_left - 1)

    def finish_skill_action(self, action_id: str) -> None:
        self.spend_skill_action(action_id)
        self.end_player_action()

    def finish_class_action(self, action_id: str) -> None:
        self.finish_skill_action(action_id)

    def resolve_player_hit_damage(self, raw_damage: int) -> tuple[int, str]:
        target = self.enemy
        if not target:
            return 0, ""
        if target.immune_turns > 0:
            target.immune_turns -= 1
            return 0, "immune"
        blocked = min(target.block, raw_damage)
        target.block -= blocked
        if blocked > 0:
            self.log(f"{target.name}的護盾擋下 {blocked} 點傷害。")
        return raw_damage - blocked, "block" if blocked >= raw_damage else ""

    def expire_player_turn_statuses(self) -> None:
        if self.player_curse_turns > 0:
            self.player_curse_turns -= 1
            if self.player_curse_turns <= 0:
                self.log("衰敗詛咒散去了。")
        for enemy in self.enemies:
            enemy.immune_turns = 0
            enemy.reflect_turns = 0

    def cleanse_enemy_negative_states(self, enemy: Enemy) -> bool:
        cleared = False
        if enemy.corrosion_turns > 0 or enemy.corrosion_damage > 0:
            enemy.corrosion_turns = 0
            enemy.corrosion_damage = 0
            cleared = True
        if enemy.agony_turns > 0 or enemy.agony_damage > 0 or enemy.agony_stacks > 0:
            enemy.agony_turns = 0
            enemy.agony_damage = 0
            enemy.agony_stacks = 0
            cleared = True
        if enemy.doom_turns > 0 or enemy.doom_damage > 0:
            enemy.doom_turns = 0
            enemy.doom_damage = 0
            cleared = True
        if enemy.weak_turns > 0 or enemy.weak_multiplier < 1.0:
            enemy.weak_turns = 0
            enemy.weak_multiplier = 1.0
            cleared = True
        return cleared

    def normal_attack(self) -> None:
        if not self.enemy or self.battle_busy or self.enemy_hidden():
            return
        self.player_actions_left = max(0, self.player_actions_left - 1)
        attack_power = self.effective_player_attack()
        bonus_damage = self.warrior_attack_bonus
        if bonus_damage > 0:
            attack_power += bonus_damage
            self.log(f"蓄積的力量釋放，這次攻擊追加 {bonus_damage} 傷害。")
            self.warrior_attack_bonus = 0
        if self.potion_attack_boost:
            self.potion_attack_boost = False
            attack_power *= 1.5
            self.log("龍牙戰藥的藥力爆發，這次攻擊傷害提升 50%。")
        critical_roll = random.randint(1, 100)
        critical = self.forced_critical or critical_roll < self.player.luck * 2
        if self.forced_critical:
            self.forced_critical = False
            self.log("星眼看穿破綻，這一擊必定暴擊。")
        if critical:
            raw_damage = max(1, math.ceil(attack_power * 1.5))
        else:
            raw_damage = max(1, math.ceil(attack_power))
        damage, blocked_by = self.resolve_player_hit_damage(raw_damage)
        self.attack_animation = AttackAnimation("player", damage, critical,
                                                enemy_index=self.target_index,
                                                blocked_by=blocked_by)
        self.configure_buttons()

    def class_attack_skill(self, skill_id: str, multiplier: float,
                           cooldown: int = 0, suppress_next_attack: bool = False,
                           once: bool = False) -> None:
        if not self.enemy or self.battle_busy or not self.class_action_ready(skill_id):
            return
        self.spend_skill_action(skill_id)
        if self.enemy_stealth_turns > 0:
            self.enemy_stealth_turns -= 1
            self.log(f"{self.enemy.name}處於隱身，這次攻擊落空。")
            self.end_player_action()
            return
        attack_power = self.effective_player_attack() * multiplier
        bonus_damage = self.warrior_attack_bonus
        if bonus_damage > 0:
            attack_power += bonus_damage
            self.log(f"蓄積的力量釋放，這次法術追加 {bonus_damage} 傷害。")
            self.warrior_attack_bonus = 0
        if self.potion_attack_boost:
            self.potion_attack_boost = False
            attack_power *= 1.5
            self.log("龍牙戰藥的藥力爆發，這次攻擊傷害提升 50%。")
        critical_roll = random.randint(1, 100)
        critical = self.forced_critical or critical_roll < self.player.luck * 2
        if self.forced_critical:
            self.forced_critical = False
            self.log("星眼看穿破綻，這一擊必定暴擊。")
        raw_damage = max(1, math.ceil(attack_power * (1.5 if critical else 1)))
        damage, blocked_by = self.resolve_player_hit_damage(raw_damage)
        if cooldown > 0:
            self.class_skill_cooldowns[skill_id] = cooldown
        if once:
            self.class_skill_cooldowns[skill_id] = 99
        if suppress_next_attack:
            self.mage_meteor_suppression = 1
            self.class_skill_cooldowns[skill_id] = 99
        self.attack_animation = AttackAnimation("player", damage, critical,
                                                enemy_index=self.target_index,
                                                blocked_by=blocked_by)
        self.configure_buttons()

    def use_class_action(self, action_id: str) -> None:
        profile = self.class_profile()
        if not profile or self.scene != Scene.BATTLE or not self.enemy or self.battle_busy:
            return
        if not self.class_action_enabled(action_id):
            return
        before_animation = self.attack_animation
        before_pending = self.pending_turn
        before_block = self.player_block
        before_hp = self.player.hp
        before_state = (
            self.stealth_turns,
            self.player_attack_immunity_turns,
            self.mage_ice_barrier_turns,
            self.forced_critical,
        )
        profile.execute(self, action_id)
        activated = (
            self.attack_animation is not before_animation
            or self.pending_turn != before_pending
            or self.player_block != before_block
            or self.player.hp != before_hp
            or before_state != (
                self.stealth_turns,
                self.player_attack_immunity_turns,
                self.mage_ice_barrier_turns,
                self.forced_critical,
            )
        )
        if activated:
            duration = 1.12 if action_id in ("bladestorm", "meteor", "divine_wrath", "assassinate", "doom") else .82
            self.trigger_skill_effect(action_id, self.player.job, duration=duration)

    def trigger_skill_effect(self, skill_id: str, job: str,
                             duration: float = .82) -> None:
        """Queue a short class-coloured visual without changing combat results."""
        self.skill_effects.append(SkillVisual(skill_id, job, duration))
        self.skill_effects = self.skill_effects[-4:]
        if self.pending_turn == "enemy" and self.attack_animation is None:
            self.battle_delay = max(self.battle_delay, min(.68, duration * .72))

    def defend(self) -> None:
        if not self.enemy or self.battle_busy:
            return
        self.player_actions_left = max(0, self.player_actions_left - 1)
        player_defense = self.effective_player_defense()
        gained_block = max(1, player_defense)
        if self.potion_defense_boost:
            self.potion_defense_boost = False
            gained_block = max(1, math.ceil(player_defense * 1.5))
            self.log("玄鐵護藥的藥力生效，這次防守護盾提升 50%。")
        self.player_block += gained_block
        self.log(f"你專心防守，獲得 {gained_block} 點護盾。")
        self.end_player_action()

    def toggle_potion_menu(self) -> None:
        if self.battle_busy or self.total_potions() < 1:
            self.potion_menu_open = False
            self.configure_buttons()
            return
        self.potion_menu_open = not self.potion_menu_open
        self.configure_buttons()

    def drink_battle_potion(self, kind: str) -> None:
        if self.scene != Scene.BATTLE or self.battle_busy or self.potion_count(kind) < 1:
            return
        if not self.battle_potion_usable(kind):
            return
        self.potions_used_this_turn.add(kind)
        self.player.potion_bag[kind] = self.potion_count(kind) - 1
        spec = self.POTIONS[kind]
        if kind == "attack":
            self.potion_attack_boost = True
            self.log(f"你喝下{spec['name']}，下一次攻擊傷害提升 50%。")
        elif kind == "defense":
            self.potion_defense_boost = True
            self.log(f"你喝下{spec['name']}，下一次防守護盾提升 50%。")
        elif kind == "lucky":
            self.forced_critical = True
            self.log(f"你喝下{spec['name']}，藥力鎖定敵人破綻，下一次攻擊必定暴擊。")
        elif kind == "iron_skin":
            self.potion_iron_skin_turns = 1
            self.log(f"你喝下{spec['name']}，本回合下一次受傷降低 30%。")
        elif kind == "cleanse_dot":
            self.clear_player_dot()
            self.log(f"你喝下{spec['name']}，身上的黑霧被驅散。")
        elif kind == "stun_ward":
            self.player_stun_turns = 0
            self.player_stun_immunity_turns = 1
            self.log(f"你喝下{spec['name']}，精神清醒，可擋下一次昏迷。")
        elif kind == "reveal":
            if self.enemy:
                self.enemy.stealth_turns = 0
            self.log(f"你喝下{spec['name']}，敵人的隱身被破除。")
        elif kind == "purify":
            self.clear_player_dot()
            self.clear_player_curse()
            self.player_stun_turns = 0
            self.player_stun_immunity_turns = 1
            self.log(f"你喝下{spec['name']}，黑霧與詛咒散去，並可擋下一次昏迷。")
        elif kind == "heal":
            restored = self.heal_player(max(1, math.ceil(self.player.max_hp * .50)))
            self.floating_damage.append(FloatingDamage("player", restored, False, True))
            self.log(f"你喝下{spec['name']}，恢復 {restored} 點血量。")
        elif kind == "full_heal":
            restored = self.heal_player(self.player.max_hp)
            self.floating_damage.append(FloatingDamage("player", restored, False, True))
            self.log(f"你喝下{spec['name']}，傷勢在暖流中完全復原。")
        self.potion_menu_open = False
        self.configure_buttons()

    def enemy_attack(self) -> None:
        if not self.enemies or self.scene != Scene.BATTLE or self.attack_animation:
            return
        if not self.enemy_turn_order:
            self.enemy_turn_order = [
                index for index, enemy in enumerate(self.enemies) if enemy.hp > 0
            ]
        if not self.enemy_turn_order:
            self.finish_enemy_action()
            return
        index = self.enemy_turn_order.pop(0)
        if index >= len(self.enemies) or self.enemies[index].hp < 1:
            self.finish_enemy_action()
            return
        self.acting_enemy_index = index
        actor = self.enemies[index]
        if actor.skip_turns > 0:
            actor.skip_turns -= 1
            self.log(f"{actor.name}陷入昏迷，這回合無法行動。")
            self.finish_enemy_action()
            return
        action = actor.intent or "attack"
        if self.player_attack_immunity_turns > 0 and action in ("attack", "strong_attack"):
            self.player_attack_immunity_turns -= 1
            self.log("神聖庇護擋下了這次怪物攻擊。")
            self.finish_enemy_action()
            return
        if self.mage_ice_barrier_turns > 0 and action in ("attack", "strong_attack"):
            self.mage_ice_barrier_turns -= 1
            self.log("寒冰屏障擋下了這次敵方攻擊。")
            self.finish_enemy_action()
            return
        if self.mage_meteor_suppression > 0 and action in ("attack", "strong_attack", "stun"):
            self.mage_meteor_suppression -= 1
            self.log("隕石風暴壓制了敵方攻擊意圖。")
            self.finish_enemy_action()
            return
        if self.stealth_turns > 0:
            self.stealth_turns -= 1
            if action in ("attack", "strong_attack", "dot", "strong_dot", "curse", "stun"):
                self.log(f"{actor.name}無法鎖定你的身影，行動失效。")
                self.finish_enemy_action()
                return
        if action == "defend":
            block = max(1, actor.defense)
            actor.block += block
            self.log(f"{actor.name}縮起身形，獲得 {block} 點護盾。")
            self.finish_enemy_action()
            return
        if action == "dot":
            dot = max(1, math.ceil(actor.attack * .33))
            self.apply_player_dot_status(actor.name, dot, "黑霧")
            self.finish_enemy_action(apply_dot=False)
            return
        if action == "curse":
            self.player_curse_turns = 3
            self.log(f"{actor.name}施加衰敗詛咒，你的攻擊與防禦降低 33%，剩餘 3 回合。")
            self.finish_enemy_action()
            return
        if action == "immune":
            actor.immune_turns = 1
            self.log(f"{actor.name}凝成黑霧外殼，將免疫下一次受到的傷害。")
            self.finish_enemy_action()
            return
        if action == "stun":
            if self.player_stun_immunity_turns > 0:
                self.player_stun_immunity_turns -= 1
                self.log(f"{actor.name}試圖造成昏迷，但醒神藥力擋下了。")
                self.finish_enemy_action()
                return
            self.player_stun_turns = 1
            self.log(f"{actor.name}造成昏迷，你下一次行動會被跳過。")
            self.finish_enemy_action()
            return
        if action == "reflect":
            actor.reflect_turns = 1
            self.log(f"{actor.name}張開反射咒壁，1 回合內反彈受到傷害的 50%。")
            self.finish_enemy_action()
            return
        if action == "cleanse":
            cleared = self.cleanse_enemy_negative_states(actor)
            if cleared:
                self.log(f"{actor.name}淨化身上的持續傷害與弱化。")
            else:
                block = max(1, math.ceil(actor.defense * .75))
                actor.block += block
                self.log(f"{actor.name}沒有可淨化的狀態，轉而獲得 {block} 點護盾。")
            self.finish_enemy_action()
            return
        if action == "berserk":
            if actor.berserk_stacks >= 5:
                self.log(f"{actor.name}狂暴已達極限。")
                self.finish_enemy_action()
                return
            gain = max(1, math.ceil(actor.attack * .10))
            actor.attack += gain
            actor.berserk_stacks += 1
            self.log(f"{actor.name}進入狂暴，攻擊增加 {gain}（{actor.berserk_stacks}/5）。")
            self.finish_enemy_action()
            return
        if action == "bulwark":
            if actor.bulwark_stacks >= 5:
                self.log(f"{actor.name}壁壘已達極限。")
                self.finish_enemy_action()
                return
            gain = max(1, math.ceil(actor.defense * .10))
            actor.defense += gain
            actor.bulwark_stacks += 1
            self.log(f"{actor.name}築起壁壘，防禦增加 {gain}（{actor.bulwark_stacks}/5）。")
            self.finish_enemy_action()
            return

        multiplier = 1.5 if action == "strong_attack" else 1
        if actor.weak_turns > 0:
            multiplier *= actor.weak_multiplier
            actor.weak_turns -= 1
            self.log(f"{actor.name}受到衰弱咒印影響，這次攻擊變弱。")
        raw_damage = max(1, math.ceil(actor.attack * multiplier))
        if self.potion_iron_skin_turns > 0:
            self.potion_iron_skin_turns = 0
            raw_damage = max(1, math.ceil(raw_damage * .70))
            self.log("鐵膚藥力讓這次傷害降低 30%。")
        critical = False
        blocked = min(self.player_block, raw_damage)
        self.player_block -= blocked
        damage = raw_damage - blocked
        if blocked > 0:
            self.log(f"你的護盾擋下 {blocked} 點傷害。")
        if action == "strong_attack":
            self.log(f"{actor.name}蓄力重擊，攻勢翻倍。")
        self.attack_animation = AttackAnimation("enemy", damage, critical,
                                                enemy_index=index)
        self.configure_buttons()

    def apply_player_dot_status(self, source_name: str, damage: int, label: str) -> None:
        if damage < 1:
            return
        was_active = self.player_dot_damage > 0 and self.player_dot_turns > 0
        self.player_dot_damage = max(self.player_dot_damage, damage)
        self.player_dot_stacks = min(3, self.player_dot_stacks + 1 if was_active else 1)
        self.player_dot_turns = 3
        total = self.player_dot_damage * max(1, self.player_dot_stacks)
        stack_text = f"（{self.player_dot_stacks} 層）" if self.player_dot_stacks > 1 else ""
        self.log(
            f"{source_name}讓{label}纏上你，每回合受到 {total} 點持續傷害"
            f"{stack_text}，剩餘 {self.player_dot_turns} 回合。"
        )

    def apply_player_dot(self) -> bool:
        if self.scene != Scene.BATTLE:
            return False
        if self.player_dot_damage <= 0 or self.player_dot_turns <= 0:
            self.clear_player_dot()
            return False
        damage = self.player_dot_damage * max(1, self.player_dot_stacks)
        self.player.hp -= damage
        self.floating_damage.append(FloatingDamage("player", damage, False))
        self.log(f"黑霧侵蝕造成 {damage} 點持續傷害。")
        self.player_dot_turns -= 1
        if self.player_dot_turns <= 0:
            self.clear_player_dot()
            self.log("纏身的黑霧散去了。")
        if self.player.hp < 1:
            if self.trigger_mage_mana_shield():
                return False
            self.finish(False)
            return True
        return False

    def enemy_has_corrosion(self, enemy: Enemy | None = None) -> bool:
        enemy = enemy or self.enemy
        return bool(enemy and enemy.corrosion_turns > 0 and enemy.corrosion_damage > 0)

    def enemy_has_dot(self, enemy: Enemy | None = None) -> bool:
        enemy = enemy or self.enemy
        return bool(enemy and (
            (enemy.corrosion_turns > 0 and enemy.corrosion_damage > 0)
            or (enemy.agony_turns > 0 and enemy.agony_damage > 0 and enemy.agony_stacks > 0)
            or (enemy.doom_turns > 0 and enemy.doom_damage > 0)
        ))

    def apply_enemy_corrosion(self, enemy: Enemy | None, damage: int,
                              turns: int) -> None:
        if not enemy or damage < 1 or turns < 1:
            return
        enemy.corrosion_damage = max(enemy.corrosion_damage, damage)
        enemy.corrosion_turns = max(enemy.corrosion_turns, turns)
        self.log(f"{enemy.name}被腐蝕纏上，每回合受 {enemy.corrosion_damage} 傷害。")

    def apply_enemy_agony(self, enemy: Enemy | None, damage: int,
                          turns: int) -> None:
        if not enemy or damage < 1 or turns < 1:
            return
        enemy.agony_damage = max(enemy.agony_damage, damage)
        enemy.agony_stacks = min(3, enemy.agony_stacks + 1 if enemy.agony_turns > 0 else 1)
        enemy.agony_turns = max(enemy.agony_turns, turns)
        total = enemy.agony_damage * enemy.agony_stacks
        self.log(
            f"{enemy.name}被痛苦詛咒折磨，每回合受 {total} 傷害"
            f"（{enemy.agony_stacks} 層）。"
        )

    def extend_enemy_corrosion(self, enemy: Enemy | None, turns: int = 1) -> None:
        if enemy and enemy.corrosion_turns > 0:
            enemy.corrosion_turns += turns

    def extend_enemy_dots(self, enemy: Enemy | None, turns: int = 1) -> None:
        if not enemy or turns < 1:
            return
        extended = False
        if enemy.corrosion_turns > 0 and enemy.corrosion_damage > 0:
            enemy.corrosion_turns += turns
            extended = True
        if enemy.agony_turns > 0 and enemy.agony_damage > 0 and enemy.agony_stacks > 0:
            enemy.agony_turns += turns
            extended = True
        if extended:
            self.log(f"{enemy.name}身上的詛咒被延長 {turns} 回合。")

    def apply_enemy_doom(self, enemy: Enemy | None, damage: int,
                         turns: int) -> None:
        if not enemy or damage < 1 or turns < 1:
            return
        enemy.doom_damage = max(enemy.doom_damage, damage)
        enemy.doom_turns = max(enemy.doom_turns, turns)
        self.log(f"{enemy.name}被末日印記鎖定，{enemy.doom_turns} 回合後爆發 {enemy.doom_damage} 傷害。")

    def weaken_enemy_attack(self, enemy: Enemy | None, reduction: float) -> None:
        if not enemy:
            return
        enemy.weak_turns = max(enemy.weak_turns, 1)
        enemy.weak_multiplier = min(enemy.weak_multiplier, max(0.1, 1.0 - reduction))
        self.log(f"{enemy.name}被衰弱咒印壓制，下一次攻擊傷害降低 {int(reduction * 100)}%。")

    def apply_enemy_dots(self) -> bool:
        if self.scene != Scene.BATTLE or not self.enemies:
            return False
        dead: list[Enemy] = []
        for index, enemy in list(enumerate(self.enemies)):
            if enemy.hp < 1:
                continue
            total = 0
            dot_names = []
            if enemy.corrosion_turns > 0 and enemy.corrosion_damage > 0:
                total += enemy.corrosion_damage
                dot_names.append("腐蝕")
                enemy.corrosion_turns -= 1
                if enemy.corrosion_turns <= 0:
                    enemy.corrosion_damage = 0
            if enemy.agony_turns > 0 and enemy.agony_damage > 0 and enemy.agony_stacks > 0:
                total += enemy.agony_damage * enemy.agony_stacks
                dot_names.append("痛苦")
                enemy.agony_turns -= 1
                if enemy.agony_turns <= 0:
                    enemy.agony_damage = 0
                    enemy.agony_stacks = 0
            if enemy.doom_turns > 0 and enemy.doom_damage > 0:
                enemy.doom_turns -= 1
                if enemy.doom_turns <= 0:
                    total += enemy.doom_damage
                    dot_names.append("末日")
                    enemy.doom_damage = 0
            if total < 1:
                continue
            enemy.hp -= total
            self.floating_damage.append(
                FloatingDamage("enemy", total, False, target_index=index)
            )
            self.log(f"{enemy.name}受到{'、'.join(dot_names)}傷害 {total} 點。")
            if self.player.job == "術士":
                rank = self.class_talent_rank("soul_link")
                if rank > 0:
                    rate = .30 if rank >= 2 else .20
                    restored = self.heal_player(max(1, math.ceil(total * rate)))
                    self.show_player_heal(restored)
            if enemy.hp < 1:
                dead.append(enemy)
        for enemy in dead:
            if enemy in self.enemies and enemy.hp < 1:
                self.handle_enemy_defeat(enemy)
                if self.scene != Scene.BATTLE or not self.enemies:
                    return True
        return False

    def apply_warrior_blood_regen(self) -> None:
        if self.warrior_blood_regen_turns <= 0 or self.scene != Scene.BATTLE:
            return
        restored = self.heal_player(self.warrior_blood_regen)
        self.warrior_blood_regen_turns -= 1
        if restored > 0:
            self.floating_damage.append(FloatingDamage("player", restored, False, True))
            self.log(f"血祭的鮮血回流，恢復 {restored} 點血量。")
        if self.warrior_blood_regen_turns <= 0:
            self.warrior_blood_regen = 0

    def finish_enemy_action(self, apply_dot: bool = True) -> None:
        """單隻怪物行動結束：還有怪物就換下一隻，否則結束整個敵方回合。"""
        if not apply_dot:
            self.enemy_turn_skip_dot = True
        if self.scene == Scene.BATTLE and self.enemy_turn_order:
            self.queue_turn("enemy", .45)
            return
        skip_dot = self.enemy_turn_skip_dot
        self.enemy_turn_skip_dot = False
        self.end_enemy_turn(not skip_dot)

    def end_enemy_turn(self, apply_dot: bool = True) -> None:
        if apply_dot and self.apply_player_dot():
            return
        if apply_dot and self.apply_enemy_dots():
            return
        self.apply_warrior_blood_regen()
        self.potion_iron_skin_turns = 0
        if self.scene == Scene.BATTLE:
            self.reduce_class_cooldowns()
        if self.scene == Scene.BATTLE and self.enemies:
            self.choose_enemy_intent()
            self.player_actions_left = self.battle_action_points
            self.potions_used_this_turn.clear()
            if self.player_stun_turns > 0:
                self.player_stun_turns -= 1
                self.log("你陷入昏迷，這回合無法行動。")
                self.expire_player_turn_statuses()
                self.queue_turn("enemy", .45)
                return
        self.configure_buttons()

    def apply_attack_impact(self) -> None:
        animation = self.attack_animation
        if not animation or animation.impacted:
            return
        animation.impacted = True
        if animation.attacker == "player" and self.enemies:
            target_index = min(animation.enemy_index, len(self.enemies) - 1)
            target = self.enemies[target_index]
            target.hp -= animation.damage
            prefix = "暴擊！" if animation.critical else ""
            if animation.damage > 0:
                self.log(f"{prefix}你對 {target.name} 造成 {animation.damage} 點傷害。")
            else:
                if animation.blocked_by == "immune":
                    self.log(f"{target.name}的黑霧外殼免疫了這次傷害。")
                else:
                    self.log(f"{target.name}用護盾擋下了這次攻擊。")
            self.floating_damage.append(
                FloatingDamage("enemy", animation.damage, animation.critical,
                               target_index=target_index)
            )
            if animation.damage > 0 and target.reflect_turns > 0:
                reflected = max(1, math.ceil(animation.damage * .50))
                self.player.hp -= reflected
                self.floating_damage.append(FloatingDamage("player", reflected, False))
                self.log(f"{target.name}的反射咒壁回彈 {reflected} 點傷害。")
                if self.player.hp < 1:
                    self.trigger_mage_mana_shield()
        elif animation.attacker == "enemy" and self.enemies:
            actor_index = min(animation.enemy_index, len(self.enemies) - 1)
            actor = self.enemies[actor_index]
            self.player.hp -= animation.damage
            prefix = "暴擊！" if animation.critical else ""
            if animation.damage > 0:
                self.log(f"{prefix}{actor.name} 對你造成 {animation.damage} 點傷害。")
            else:
                self.log("你的護盾完全擋下了這次攻擊。")
            self.floating_damage.append(
                FloatingDamage("player", animation.damage, animation.critical)
            )
            if self.player.hp < 1:
                self.trigger_mage_mana_shield()

    def finish_attack_animation(self) -> None:
        animation = self.attack_animation
        self.attack_animation = None
        if not animation or self.scene != Scene.BATTLE:
            return
        if animation.attacker == "player":
            if self.player.hp < 1:
                self.finish(False)
                return
            target = self.enemies[min(animation.enemy_index, len(self.enemies) - 1)] if self.enemies else None
            if target and target.hp < 1:
                self.handle_enemy_defeat(target)
                if self.scene != Scene.BATTLE or not self.enemies:
                    return
            self.end_player_action()
        elif self.player.hp < 1:
            self.finish(False)
        else:
            self.finish_enemy_action()

    def split_boss(self, boss: Enemy) -> None:
        """三星試煉：魔王首次倒下時分裂成兩隻 40% 屬性的分身。"""
        self.boss_split_done = True
        clone_hp = max(1, math.ceil(boss.max_hp * self.BOSS_SPLIT_STAT_SCALE))
        clone_attack = max(1, math.ceil(boss.attack * self.BOSS_SPLIT_STAT_SCALE))
        clone_defense = max(0, math.ceil(boss.defense * self.BOSS_SPLIT_STAT_SCALE))
        self.enemies = [
            Enemy(f"魔王分身・{suffix}", boss.kind, 6, boss.level,
                  clone_hp, clone_hp, clone_attack, clone_defense)
            for suffix in ("左", "右")
        ]
        self.target_index = 0
        clone_portrait = (self.enemy_portraits[0] if self.enemy_portraits
                          else self.monster_portrait(6, boss.kind))
        self.enemy_portraits = [clone_portrait, clone_portrait]
        self.enemy_turn_order = []
        self.battle_action_points = 2
        self.choose_enemy_intent()
        self.log("魔王倒下的瞬間裂成兩道身影，各自持有本體四成的力量！")
        self.log("擊敗兩隻分身才能真正通關。點擊怪物可切換攻擊目標。")
        self.configure_buttons()

    def handle_enemy_defeat(self, target: Enemy) -> None:
        """目標倒下：還有其他怪物就結算獎勵並換目標，否則直接獲勝。"""
        if (target.rank == 6 and self.difficulty >= self.MAX_DIFFICULTY
                and not self.boss_split_done):
            self.split_boss(target)
            return
        living = [enemy for enemy in self.enemies if enemy is not target and enemy.hp > 0]
        if not living:
            self.win_battle()
            return
        gold_multipliers = {1: .5, 2: 1, 3: 1.5, 4: 2, 5: 2.5}
        gained_gold = int(self.player.lv * 50 * gold_multipliers.get(target.rank, 1))
        self.player.gold += gained_gold
        self.log(f"{target.name}倒下，你搜出 {gained_gold}G。另一隻怪物仍在逼近！")
        index = self.enemies.index(target)
        self.enemies.pop(index)
        if index < len(self.enemy_portraits):
            self.enemy_portraits.pop(index)
        self.enemy_turn_order = [
            order - (1 if order > index else 0)
            for order in self.enemy_turn_order if order != index
        ]
        self.target_index = 0
        self.configure_buttons()

    def win_battle(self) -> None:
        if not self.enemy:
            return
        rank = self.enemy.rank
        if rank == 6:
            self.log(f"{self.enemy.name}倒下了，{self.player.name}讓王城重新看見黎明！")
            self.finish(True)
            return
        gold_multipliers = {1: .5, 2: 1, 3: 1.5, 4: 2, 5: 2.5}
        gained_gold = int(self.player.lv * 50 * gold_multipliers[rank])
        self.player.gold += gained_gold
        self.log(f"{self.enemy.name}倒下，你搜出 {gained_gold}G。")
        self.complete_battle(level_up=True)

    def complete_battle(self, level_up: bool = False) -> None:
        """收束戰鬥，前往下一個旅途場景。"""
        self.enemy = None
        self.clear_battle_state()
        self.clear_battle_skill_effects()
        self.reset_battle_skill_uses()
        self.after_subclass = "post_battle"
        opened_subclass = self.check_level_up(from_battle=level_up)
        if opened_subclass:
            self.configure_buttons()
            return
        self.continue_after_battle_reward()

    def check_level_up(self, from_battle: bool = False) -> bool:
        """結算冒險者的成長。"""
        p = self.player
        if not from_battle or p.lv >= 21:
            return False
        old_gear_tier = player_gear_tier(p.lv)
        p.lv += 1
        hp_gain = p.lv * (4 if p.job == "戰士" else 2)
        attack_gain = p.lv * (2 if p.job == "法師" else 1)
        defense_gain = p.lv * (2 if p.job == "聖騎士" else 1)
        luck_gain = 2 if p.job == "盜賊" else 1
        p.max_hp += hp_gain
        p.hp += hp_gain
        p.attack += attack_gain
        p.defense += defense_gain
        p.luck += luck_gain
        if p.lv % self.TALENT_POINT_INTERVAL == 0:
            p.talent_points += 1
            self.log(f"你獲得 1 點天賦點，目前可用 {p.talent_points} 點。")
        self.track_player_hp()
        if player_gear_tier(p.lv) != old_gear_tier:
            self.hero_portrait = make_player_portrait(p.sex, p.race, p.job, p.lv)
        self.journey_lore = self.random_journey_lore()
        stage_title, _stage_text = self.journey_stage()
        self.log(f"你抵達{self.level_label(p.lv)}，離王城更近了。現在抵達「{stage_title}」。")
        if p.lv >= 10 and not p.sub_job:
            self.scene = Scene.SUBCLASS
            self.log(f"你已達{self.level_label(10)}，可以選擇一個副職業。")
            self.configure_buttons()
            return True
        return False

    def subclass_options(self) -> list[str]:
        options = [job for job, _bonus in self.JOBS if job != self.player.job]
        return options[:4]

    def choose_sub_job(self, job: str) -> None:
        if self.scene != Scene.SUBCLASS or job not in self.subclass_options():
            return
        self.player.sub_job = job
        self.sub_job_skill_cooldown = 0
        self.log(f"{self.player.name}選擇了副職業 {job}，學會「{self.job_skill_name(job)}」。")
        destination = self.after_subclass
        self.after_subclass = "adventure"
        if destination == "post_battle":
            self.continue_after_battle_reward()
        elif destination == "event":
            self.resolve_event()
            if self.scene == Scene.EVENT:
                self.configure_buttons()
        else:
            self.scene = Scene.ADVENTURE
            self.configure_buttons()

    # ---------- wilderness events ----------
    def event_stat_amount(self, stat: str, affected_count: int) -> int:
        p = self.player
        multiplier = self.EVENT_KIND_MULTIPLIERS[affected_count]
        if stat == "max_hp":
            return max(1, math.ceil(p.lv * 2 * multiplier))
        if stat in ("attack", "defense"):
            return max(1, math.ceil(p.lv * .5 * multiplier))
        if stat == "gold":
            return max(10, math.ceil(p.lv * 60 * multiplier))
        if stat == "luck":
            return 2 if affected_count == 1 else 1
        raise ValueError(f"Unknown event stat: {stat}")

    def apply_event_stat_change(self, stat: str, direction: int, amount: int) -> int:
        p = self.player
        if stat == "max_hp":
            if direction > 0:
                p.max_hp += amount
                p.hp += amount
                actual = amount
            else:
                old_value = p.max_hp
                p.max_hp = max(1, p.max_hp - amount)
                p.hp = min(p.hp, p.max_hp)
                actual = old_value - p.max_hp
            self.track_player_hp()
            return actual

        if stat == "attack":
            old_value = p.attack
            p.attack = p.attack + amount if direction > 0 else max(1, p.attack - amount)
            return abs(p.attack - old_value)

        if stat == "defense":
            old_value = p.defense
            p.defense = p.defense + amount if direction > 0 else max(0, p.defense - amount)
            return abs(p.defense - old_value)

        if stat == "gold":
            old_value = p.gold
            p.gold = p.gold + amount if direction > 0 else max(0, p.gold - amount)
            return abs(p.gold - old_value)

        if stat == "luck":
            old_value = p.luck
            p.luck = p.luck + amount if direction > 0 else max(0, p.luck - amount)
            return abs(p.luck - old_value)

        raise ValueError(f"Unknown event stat: {stat}")

    def event_change_phrase(self, stat: str, direction: int, actual: int) -> str:
        if actual == 0:
            return ""
        sign = "+" if direction > 0 else "-"
        if stat == "max_hp":
            return f"血量上限 {sign}{actual}"
        if stat == "attack":
            return f"攻擊 {sign}{actual}"
        if stat == "defense":
            return f"防禦 {sign}{actual}"
        if stat == "gold":
            return f"金錢 {sign}{actual}G"
        if stat == "luck":
            return f"幸運 {sign}{actual}"
        raise ValueError(f"Unknown event stat: {stat}")

    def apply_random_event_changes(self) -> None:
        stat_count = random.randint(1, len(self.EVENT_STAT_KEYS))
        stats = random.sample(self.EVENT_STAT_KEYS, stat_count)
        phrases: list[str] = []
        positive_count = 0
        negative_count = 0

        for stat in stats:
            positive_chance = .60 if self.player.race == "精靈" else .50
            direction = 1 if random.random() < positive_chance else -1
            if direction > 0:
                positive_count += 1
            else:
                negative_count += 1
            amount = self.event_stat_amount(stat, stat_count)
            actual = self.apply_event_stat_change(stat, direction, amount)
            phrase = self.event_change_phrase(stat, direction, actual)
            if phrase:
                phrases.append(phrase)

        if phrases:
            self.log("、".join(phrases) + "。")
        else:
            self.log("沒有明顯變化。")

    def event_background_number(self, event_number: int) -> int:
        if event_number == self.START_GIFT_EVENT_NUMBER:
            return 13
        if 1 <= event_number <= len(self.EVENT_DECK):
            return int(self.EVENT_DECK[event_number - 1]["background"])
        return ((event_number - 1) % 18) + 1

    def resolve_event(self) -> None:
        event_number = random.randint(1, len(self.EVENT_DECK))
        event = self.EVENT_DECK[event_number - 1]

        self.event_number = event_number
        self.event_title = str(event["title"])
        self.event_options = event["options"]
        self.event_resolved = False
        self.event_kind = "random"
        self.event_messages = []
        self.scene = Scene.EVENT
        self.log(str(event["intro"]))

    def choose_event_option(self, option_index: int) -> None:
        if self.event_resolved:
            return
        choice = self.event_options[max(0, min(1, option_index))]
        self.event_resolved = True
        self.log(f"你選擇「{choice}」。", record=False)
        if self.event_kind == "start_gift":
            self.log("你把月泉靈藥收入藥袋。戰鬥中可從藥水列喝下，立即恢復 50% 血量。")
            self.configure_buttons()
            return
        outcome = random.random()
        if outcome < .95:
            self.apply_random_event_changes()
        else:
            self.log("你檢查了一下，沒有找到能用的東西，也沒有遇到危險。")
        self.configure_buttons()

    def leave_event(self) -> None:
        self.after_subclass = "adventure"
        if self.check_level_up():
            return
        self.scene = Scene.ADVENTURE
        self.configure_buttons()

    def finish(self, victory: bool) -> None:
        self.victory = victory
        self.scene = Scene.END
        if victory and self.enemy:
            self.final_enemy_name = self.enemy.name
        self.enemy = None
        self.clear_battle_state()
        self.clear_battle_skill_effects()
        if victory:
            self.record_job_clear()
        else:
            self.player.hp = 0
            self.log("GAME OVER")
        self.configure_buttons()

    def replay(self) -> None:
        """Restart immediately with the same name, sex, race, and job."""
        self.enemy = None
        self.final_enemy_name = ""
        self.victory = False
        self.skill_cooldown_turns = self.SKILL_COOLDOWN_TURNS
        self.clear_battle_state()
        self.reset_skills()
        self.after_subclass = "adventure"
        self.floating_damage.clear()
        self.choose_difficulty(self.job_difficulty(self.selected_job))

    def request_return_home(self) -> None:
        """Open a mouse-only confirmation before abandoning the current journey."""
        self.home_confirmation = True
        self.hovered = None
        self.configure_buttons()

    def cancel_return_home(self) -> None:
        self.home_confirmation = False
        self.hovered = None
        self.configure_buttons()

    def return_home(self) -> None:
        self.home_confirmation = False
        self.player = Player()
        self.hero_portrait = make_player_portrait("男性", "獸人", "戰士")
        self.enemy = None
        self.final_enemy_name = ""
        self.selected_sex = "男性"
        self.name_input = ""
        self.selected_race = "獸人"
        self.selected_job = "戰士"
        self.difficulty = 1
        self.reset_skills()
        self.after_subclass = "adventure"
        self.messages = []
        self.log_scroll = 0
        self.log_scroll_dragging = False
        self.journey_lore = self.random_journey_lore()
        self.shop_lore = random.choice(self.SHOP_LORE)
        self.victory = False
        self.skill_cooldown_turns = self.SKILL_COOLDOWN_TURNS
        self.clear_battle_state()
        self.clear_battle_skill_effects()
        self.floating_damage.clear()
        self.scene = Scene.TITLE
        self.configure_buttons()

    def close_game(self) -> None:
        self.close()

    # ---------- save / load ----------
    def save_slot_path(self, slot: int) -> Path:
        return self.SAVE_DIR / f"save_slot_{slot}.json"

    def read_save_slot(self, slot: int) -> dict | None:
        path = self.save_slot_path(slot)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict) or not isinstance(data.get("player"), dict):
            return None
        return data

    def refresh_save_slots(self) -> None:
        self.save_slots = {
            slot: self.read_save_slot(slot)
            for slot in range(1, self.SAVE_SLOT_COUNT + 1)
        }

    def has_any_save(self) -> bool:
        return any(self.save_slots.values())

    def open_save_menu(self, mode: str) -> None:
        """開啟存讀檔頁面；mode 為 load（僅讀檔）或 manage（可存可讀）。"""
        self.save_menu_mode = mode
        self.save_menu_return = self.scene
        self.refresh_save_slots()
        self.scene = Scene.SAVE_MENU
        self.hovered = None
        self.configure_buttons()

    def close_save_menu(self) -> None:
        self.scene = self.save_menu_return
        self.hovered = None
        self.configure_buttons()

    def save_to_slot(self, slot: int) -> None:
        if self.save_menu_mode != "manage":
            return
        data = {
            "version": self.SAVE_VERSION,
            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "player": asdict(self.player),
            "difficulty": self.difficulty,
        }
        try:
            self.SAVE_DIR.mkdir(parents=True, exist_ok=True)
            self.save_slot_path(slot).write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            self.log(f"存檔失敗：無法寫入存檔槽 {slot}。")
            return
        self.log(f"旅程進度已寫入存檔槽 {slot}。")
        self.refresh_save_slots()
        self.configure_buttons()

    def load_from_slot(self, slot: int) -> None:
        data = self.read_save_slot(slot)
        if not data:
            return
        try:
            player_data = {
                key: value for key, value in data["player"].items()
                if key in Player.__dataclass_fields__
            }
            p = Player(**player_data)
            difficulty = int(data.get("difficulty", 1))
        except (TypeError, ValueError):
            self.log(f"存檔槽 {slot} 已損毀，無法讀取。")
            return
        self.player = p
        self.difficulty = difficulty if difficulty in self.DIFFICULTY_PROFILES else 1
        self.migrate_legacy_potions()
        self.enemy = None
        self.final_enemy_name = ""
        self.victory = False
        self.home_confirmation = False
        self.skill_cooldown_turns = self.SKILL_COOLDOWN_TURNS
        self.reset_skills()
        self.clear_battle_state()
        self.clear_battle_skill_effects()
        self.reset_battle_skill_uses()
        self.floating_damage.clear()
        self.after_subclass = "adventure"
        self.track_player_hp()
        self.hero_portrait = make_player_portrait(p.sex, p.race, p.job, p.lv)
        self.messages = []
        self.log_scroll = 0
        self.journey_lore = self.random_journey_lore()
        stage_title, _stage_text = self.journey_stage()
        self.log(f"讀取存檔槽 {slot}：{p.name}回到「{stage_title}」。")
        self.log(f"目前{self.level_label(p.lv)}，旅程從戰鬥前重新出發。")
        self.scene = Scene.ADVENTURE
        self.configure_buttons()

    # ---------- 作弊工具 ----------
    def toggle_cheat(self) -> None:
        self.cheat_open = not self.cheat_open
        self.cheat_focus = None
        self.cheat_input = ""
        self.cheat_dropdown = None
        self.hovered = None
        if not self.cheat_open:
            p = self.player
            self.track_player_hp()
            self.hero_portrait = make_player_portrait(p.sex, p.race, p.job, p.lv)
            if self.cheat_dirty:
                self.log("作弊調整完成，將於下一場戰鬥完全生效。")
                self.cheat_dirty = False
        self.configure_buttons()

    def cheat_value(self, field: str) -> int:
        if field == "difficulty":
            return self.difficulty
        if field == "potions":
            return self.potion_count("heal")
        return int(getattr(self.player, field))

    def cheat_value_label(self, field: str) -> str:
        value = self.cheat_value(field)
        if field == "difficulty":
            return f"{value}（{self.DIFFICULTY_NAMES[value]}）"
        if field == "lv":
            return self.level_label(value)
        return str(value)

    def cheat_set(self, field: str, value: int) -> None:
        """作弊直接設值：僅正整數，最多 4 位數。"""
        value = max(0, min(9999, int(value)))
        p = self.player
        if field == "max_hp":
            p.max_hp = max(1, value)
        elif field == "hp":
            p.hp = max(1, min(p.max_hp, value))
        elif field == "attack":
            p.attack = max(1, value)
        elif field == "potions":
            if value > 0:
                p.potion_bag["heal"] = value
            else:
                p.potion_bag.pop("heal", None)
        elif field in ("defense", "luck", "gold", "talent_points"):
            setattr(p, field, value)
        self.track_player_hp()
        self.cheat_dirty = True

    def focus_cheat_field(self, field: str) -> None:
        self.cheat_focus = field
        self.cheat_input = ""
        self.cheat_dropdown = None
        self.configure_buttons()

    def unfocus_cheat_field(self) -> None:
        self.cheat_focus = None
        self.cheat_input = ""
        self.cheat_dropdown = None
        self.configure_buttons()

    def cheat_input_text(self, text: str) -> None:
        if self.cheat_focus is None:
            return
        for character in text:
            if character.isdigit() and len(self.cheat_input) < self.CHEAT_MAX_DIGITS:
                self.cheat_input += character
        if self.cheat_input:
            self.cheat_set(self.cheat_focus, int(self.cheat_input))
        self.configure_buttons()

    def cheat_input_backspace(self) -> None:
        if self.cheat_focus is None:
            return
        self.cheat_input = self.cheat_input[:-1]
        if self.cheat_input:
            self.cheat_set(self.cheat_focus, int(self.cheat_input))
        self.configure_buttons()

    def toggle_cheat_dropdown(self, field: str) -> None:
        self.cheat_dropdown = None if self.cheat_dropdown == field else field
        self.cheat_focus = None
        self.cheat_input = ""
        self.configure_buttons()

    def select_cheat_option(self, field: str, value: int) -> None:
        if field == "difficulty":
            self.difficulty = max(1, min(self.MAX_DIFFICULTY, value))
        else:
            self.player.lv = max(1, min(21, value))
        self.cheat_dirty = True
        self.cheat_dropdown = None
        self.configure_buttons()

    def configure_cheat_buttons(self) -> None:
        if self.cheat_dropdown == "lv":
            for level in range(1, 22):
                col = (level - 1) % 7
                row = (level - 1) // 7
                self.buttons.append(Button(
                    496 + col * 48, 470 - row * 44, 44, 36, str(level),
                    lambda v=level: self.select_cheat_option("lv", v),
                    accent=(102, 86, 151), attention=self.player.lv == level,
                ))
            self.buttons.append(Button(640, 100, 200, 42, "返回",
                                       lambda: self.toggle_cheat_dropdown("lv"),
                                       accent=(73, 79, 91)))
            return
        if self.cheat_dropdown == "difficulty":
            for level in range(1, self.MAX_DIFFICULTY + 1):
                self.buttons.append(Button(
                    640, 470 - (level - 1) * 48, 240, 40,
                    f"{level}（{self.DIFFICULTY_NAMES[level]}）",
                    lambda v=level: self.select_cheat_option("difficulty", v),
                    accent=(102, 86, 151), attention=self.difficulty == level,
                ))
            self.buttons.append(Button(640, 100, 200, 42, "返回",
                                       lambda: self.toggle_cheat_dropdown("difficulty"),
                                       accent=(73, 79, 91)))
            return
        for row_index, (field, _label) in enumerate(self.CHEAT_FIELDS):
            y = self.CHEAT_ROW_TOP - row_index * self.CHEAT_ROW_GAP
            if field in self.CHEAT_DROPDOWN_FIELDS:
                self.buttons.append(Button(
                    800, y, 230, 34, f"{self.cheat_value_label(field)}▾",
                    lambda f=field: self.toggle_cheat_dropdown(f),
                    accent=(102, 86, 151),
                    tooltip="點擊開啟下拉選單。",
                ))
            else:
                focused = self.cheat_focus == field
                label = f"{self.cheat_input}|" if focused else str(self.cheat_value(field))
                self.buttons.append(Button(
                    800, y, 230, 34, label,
                    lambda f=field: self.focus_cheat_field(f),
                    accent=(62, 100, 139), attention=focused,
                    tooltip="點擊後輸入數字（最多 4 位）。",
                ))
        self.buttons.append(Button(640, 100, 200, 42, "關閉", self.toggle_cheat,
                                   accent=(73, 79, 91)))

    def add_potion_menu_buttons(self, anchor_x: float, anchor_top: float) -> None:
        """在藥水按鈕上方浮出可飲用的藥水清單（只列出有庫存的種類）。"""
        can_choose = not self.battle_busy
        owned = self.owned_potions()
        column_gap = 18
        row_gap = 42
        button_width = 210
        button_height = 36
        left_x = 650
        top_y = 308
        rows = max(1, math.ceil(len(owned) / 2))
        panel_width = button_width * 2 + column_gap + 28
        panel_height = rows * button_height + (rows - 1) * (row_gap - button_height) + 28
        self.potion_menu_bounds = (
            left_x - button_width / 2 - 14,
            top_y - (rows - 1) * row_gap - button_height / 2 - 14,
            panel_width,
            panel_height,
        )
        for index, kind in enumerate(owned):
            spec = self.POTIONS[kind]
            label = f"{spec['name']} ×{self.potion_count(kind)}"
            if kind in self.potions_used_this_turn:
                label = f"{spec['name']} 本回合已喝"
            col, row = index % 2, index // 2
            self.buttons.append(Button(
                left_x + col * (button_width + column_gap), top_y - row * row_gap,
                button_width, button_height,
                label,
                lambda k=kind: self.drink_battle_potion(k),
                enabled=can_choose and self.battle_potion_usable(kind),
                accent=self.BATTLE_ACCENT_POTION,
                tooltip=spec["desc"],
            ))

    # ---------- buttons ----------
    def configure_buttons(self) -> None:
        self.sync_ime_state()
        self.buttons.clear()
        self.potion_menu_bounds = None
        if self.cheat_open:
            self.configure_cheat_buttons()
            return
        if self.home_confirmation:
            self.buttons.extend([
                Button(490, 285, 175, 54, "留在旅途中", self.cancel_return_home,
                       accent=(62, 100, 139)),
                Button(690, 285, 175, 54, "確認返回", self.return_home,
                       accent=(132, 50, 55)),
            ])
            return
        p = self.player
        if self.scene == Scene.TITLE:
            self.buttons.append(Button(590, 245, 280, 58, "開始遊戲", self.open_guide))
            if self.has_any_save():
                self.buttons.extend([
                    Button(590, 178, 280, 54, "讀取存檔",
                           lambda: self.open_save_menu("load"), accent=(112, 82, 48)),
                    Button(590, 111, 280, 54, "關閉遊戲", self.close_game,
                           accent=(110, 53, 58)),
                ])
            else:
                self.buttons.append(Button(590, 170, 280, 54, "關閉遊戲", self.close_game,
                                           accent=(110, 53, 58)))
        elif self.scene == Scene.GUIDE:
            self.buttons.extend([
                Button(475, 125, 220, 54, "建立角色", self.start_creation),
                Button(705, 125, 220, 54, "回到主頁", self.return_home,
                       accent=(73, 79, 91)),
            ])
        elif self.scene == Scene.CREATION:
            if self.creation_step == 0:
                self.buttons.extend([
                    Button(475, 300, 190, 58, "男性", lambda: self.choose_sex("男性"), "1"),
                    Button(705, 300, 190, 58, "女性", lambda: self.choose_sex("女性"), "2"),
                ])
            elif self.creation_step == 1:
                self.buttons.extend([
                    Button(590, 270, 220, 54, "確認名字", self.next_creation_step,
                           enabled=bool(self.name_input.strip())),
                ])
            elif self.creation_step == 2:
                for i, (race, bonus) in enumerate(self.RACES):
                    self.buttons.append(Button(365, 425 - i * 65, 190, 54,
                                               race,
                                               lambda r=race: self.choose_race(r), str(i + 1),
                                               tooltip=bonus))
            else:
                visible_jobs = self.visible_jobs()
                start_x = 590 - (len(visible_jobs) - 1) * 120
                for i, (job, _bonus) in enumerate(visible_jobs):
                    x = start_x + i * 240
                    self.buttons.append(Button(x, 382, 185, 42, job,
                                               lambda j=job: self.choose_job(j), str(i + 1),
                                               decorated=False))
                if self.job_page > 0:
                    self.buttons.append(Button(208, 336, 48, 58, "‹",
                                               lambda: self.change_job_page(-1), accent=(73, 79, 91),
                                               tooltip="上一組職業", decorated=False))
                if self.job_page < self.max_job_page():
                    self.buttons.append(Button(972, 336, 48, 58, "›",
                                               lambda: self.change_job_page(1), accent=(73, 79, 91),
                                               tooltip="下一組職業", decorated=False))
            self.buttons.append(Button(590, 170, 180, 42, "回到主頁", self.request_return_home,
                                       accent=(73, 79, 91)))
        elif self.scene == Scene.ADVENTURE:
            self.buttons.extend([
                Button(680, 92, 260, 54, "繼續旅程", self.continue_journey),
                Button(960, 92, 180, 50, "回到主頁", self.request_return_home,
                       accent=(73, 79, 91)),
                Button(680, 35, 260, 46, "存檔 / 讀檔",
                       lambda: self.open_save_menu("manage"), accent=(75, 104, 129)),
            ])
            if self.has_class_talents():
                self.buttons.append(Button(455, 92, 180, 50, f"{p.job}天賦", self.open_talent_page, "T",
                                           True, accent=(102, 86, 151),
                                           tooltip="查看或重置已學天賦；有點數時可學新天賦。",
                                           attention=p.talent_points > 0))
            self.buttons.append(Button(
                455, 35, 180, 46, "藥水商", self.open_black_market, "B",
                self.can_open_black_market(), accent=(112, 82, 48),
            ))
        elif self.scene == Scene.TALENT:
            for talent_id, talent in self.class_talent_defs().items():
                tier = int(talent["tier"])
                side = int(talent["side"])
                if tier < 4:
                    x = 575 + side * 370
                    y = 505 - (tier - 1) * 125
                else:
                    x = 760
                    y = 130
                rank = self.class_talent_rank(talent_id)
                self.buttons.append(Button(
                    x, y, 245, 44, f"{talent['name']} {rank}/{talent['max']}",
                    lambda selected=talent_id: self.learn_class_talent(selected),
                    enabled=self.class_talent_can_add(talent_id),
                    accent=(102, 86, 151),
                    tooltip=self.class_talent_tooltip(talent_id),
                    talent_id=talent_id,
                ))
            self.buttons.extend([
                Button(570, 34, 180, 42, "重置天賦", self.reset_class_talents,
                       "R", self.class_talent_spent() > 0, accent=(132, 50, 55)),
                Button(800, 34, 180, 42, "返回", self.close_talent_page,
                       "ESC", True, accent=(73, 79, 91)),
            ])
        elif self.scene == Scene.SUBCLASS:
            centers = ((570, 355), (950, 355), (570, 225), (950, 225))
            for i, job in enumerate(self.subclass_options()):
                x, y = centers[i]
                self.buttons.append(Button(
                    x, y, 220, 50, job,
                    lambda selected=job: self.choose_sub_job(selected),
                    str(i + 1), True, accent=(112, 82, 48),
                    tooltip=self.job_skill_tooltip(job),
                ))
        elif self.scene == Scene.BATTLE:
            can_choose = not self.battle_busy
            action_slots = [(
                self.skill_label(self.job_skill_name(p.job), self.job_skill_cooldown,
                                 self.job_skill_active(p.job)),
                self.use_job_skill,
                "J",
                self.job_skill_enabled(p.job, can_choose and self.job_skill_ready()),
                self.BATTLE_ACCENT_JOB_SKILL,
                f"主職專屬｜{self.job_skill_tooltip(p.job)}",
            )]
            if p.sub_job:
                action_slots.append((
                    self.skill_label(self.job_skill_name(p.sub_job), self.sub_job_skill_cooldown,
                                     self.job_skill_active(p.sub_job)),
                    lambda: self.use_job_skill(p.sub_job, True),
                    "K",
                    self.job_skill_enabled(
                        p.sub_job,
                        can_choose and self.job_skill_ready(p.sub_job, self.sub_job_skill_cooldown),
                    ),
                    self.BATTLE_ACCENT_JOB_SKILL,
                    f"副職專屬｜{self.job_skill_tooltip(p.sub_job)}",
                ))
            for index, (label, action_id, enabled, _accent, tooltip) in enumerate(
                    self.class_profile().action_slots(self), start=1):
                action_slots.append((
                    label,
                    lambda selected=action_id: self.use_class_action(selected),
                    str(index),
                    self.class_action_enabled(action_id, can_choose and enabled),
                    self.battle_class_action_accent(action_id),
                    tooltip,
                ))
            total_potions = self.total_potions()
            action_slots.append((
                f"藥水 x{total_potions}", self.toggle_potion_menu, "P",
                can_choose and total_potions > 0, self.BATTLE_ACCENT_POTION,
                "展開藥水選單；同種藥水每回合只能喝一瓶，使用後不消耗回合。",
            ))
            slot_width = 140 if len(action_slots) > 8 else 150
            slot_height = 34 if len(action_slots) > 8 else 42
            slot_gap = 14 if len(action_slots) > 8 else 18
            row_y = (108, 68, 28) if len(action_slots) > 8 else ((86, 36) if len(action_slots) > 4 else (62,))
            for index, (label, action, shortcut, enabled, accent, tooltip) in enumerate(action_slots):
                row = index // 4
                col = index % 4
                count_in_row = min(4, len(action_slots) - row * 4)
                row_width = count_in_row * slot_width + (count_in_row - 1) * slot_gap
                x = 760 - row_width / 2 + slot_width / 2 + col * (slot_width + slot_gap)
                self.buttons.append(Button(
                    x, row_y[row], slot_width, slot_height, label, action, shortcut,
                    enabled, accent=accent, tooltip=tooltip,
                ))
            if self.potion_menu_open and self.buttons:
                potion_button = self.buttons[-1]
                self.add_potion_menu_buttons(potion_button.x,
                                             potion_button.y + potion_button.height / 2)
            return
        elif self.scene == Scene.CAMPFIRE:
            rest_percent = 50 if p.race == "獸人" else 33
            ability_percent = 20 if p.race == "人類" else 10
            camp_gold = p.lv * 60 * (2 if p.race == "矮人" else 1)
            self.buttons.extend([
                Button(635, 242, 210, 50, f"恢復 {rest_percent}% 血量", self.choose_campfire_rest, "1",
                       True, accent=(71, 127, 85)),
                Button(880, 242, 190, 50, f"攻擊 +{ability_percent}%", lambda: self.choose_campfire_stat("attack"), "2",
                       True, accent=(147, 92, 54)),
                Button(635, 182, 210, 50, f"防禦 +{ability_percent}%", lambda: self.choose_campfire_stat("defense"), "3",
                       True, accent=(75, 104, 129)),
                Button(880, 182, 190, 50, f"幸運 +{ability_percent}%", lambda: self.choose_campfire_stat("luck"), "4",
                       True, accent=(102, 86, 151)),
                Button(760, 122, 260, 50, f"金錢 +{camp_gold}G", lambda: self.choose_campfire_stat("gold"), "5",
                       True, accent=(112, 82, 48)),
            ])
        elif self.scene == Scene.SHOP:
            for i, kind in enumerate(self.POTIONS):
                spec = self.POTIONS[kind]
                col, row = i % 4, i // 4
                price = self.potion_price(kind)
                shortcut = "0" if i == 9 else str(i + 1)
                self.buttons.append(Button(505 + col * 170, 315 - row * 60, 158, 50,
                                           f"{spec['name']}｜{price}G",
                                           lambda k=kind: self.buy_potion(k),
                                           shortcut, self.potion_available(kind),
                                           accent=(112, 82, 48),
                                           tooltip=f"{spec['desc']}（目前持有 {self.potion_count(kind)} 瓶）"))
            self.buttons.append(Button(755, 55, 180, 42, "離開藥水商", self.leave_black_market, "ESC",
                                       accent=(77, 83, 95)))
        elif self.scene == Scene.EVENT:
            if self.event_resolved:
                self.buttons.append(Button(755, 95, 220, 52, "繼續旅程", self.leave_event, "ENTER",
                                           accent=(77, 83, 95),
                                           tooltip="離開目前事件，回到冒險路線。"))
            else:
                left_label, right_label = self.event_options
                self.buttons.extend([
                    Button(635, 95, 220, 52, left_label,
                           lambda: self.choose_event_option(0), "1",
                           accent=(112, 82, 48),
                           tooltip="採取這個選擇，結果仍會受到命運影響。"),
                    Button(885, 95, 220, 52, right_label,
                           lambda: self.choose_event_option(1), "2",
                           accent=(75, 104, 129),
                           tooltip="採取這個選擇，結果仍會受到命運影響。"),
                ])
        elif self.scene == Scene.SAVE_MENU:
            for slot in range(1, self.SAVE_SLOT_COUNT + 1):
                center_y = 454 - (slot - 1) * 126
                has_data = bool(self.save_slots.get(slot))
                if self.save_menu_mode == "manage":
                    self.buttons.extend([
                        Button(800, center_y + 26, 130, 42, "存檔",
                               lambda n=slot: self.save_to_slot(n),
                               accent=(71, 127, 85),
                               tooltip=f"把目前旅程寫入存檔槽 {slot}。"
                                       + ("會覆蓋原本的紀錄。" if has_data else "")),
                        Button(800, center_y - 26, 130, 42, "讀檔",
                               lambda n=slot: self.load_from_slot(n),
                               enabled=has_data, accent=(112, 82, 48),
                               tooltip=f"讀取存檔槽 {slot} 的旅程進度。" if has_data
                               else ""),
                    ])
                else:
                    self.buttons.append(Button(800, center_y, 150, 50, "讀取",
                                               lambda n=slot: self.load_from_slot(n),
                                               enabled=has_data, accent=(112, 82, 48),
                                               tooltip=f"讀取存檔槽 {slot} 的旅程進度。" if has_data
                                               else ""))
            self.buttons.append(Button(590, 60, 200, 46, "返回", self.close_save_menu,
                                       "ESC", accent=(73, 79, 91)))
        elif self.scene == Scene.END:
            self.buttons.extend([
                Button(650, 105, 210, 54, "重玩", self.replay),
                Button(880, 105, 210, 54, "回到主頁", self.request_return_home,
                       accent=(73, 79, 91)),
            ])

    # ---------- draw scenes ----------

    # ---------- animation and input ----------
    def on_update(self, delta_time: float) -> None:
        if (self.scene == Scene.CREATION and self.creation_step == 1
                and self.name_input_focused):
            self.name_caret_timer += delta_time
        for floating in self.floating_damage:
            floating.elapsed += delta_time
        self.floating_damage = [f for f in self.floating_damage if f.elapsed < .9]
        for effect in self.skill_effects:
            effect.elapsed += delta_time
        self.skill_effects = [
            effect for effect in self.skill_effects if effect.elapsed < effect.duration
        ]

        if self.scene != Scene.BATTLE:
            self.skill_effects.clear()
            return
        if self.cheat_open:
            return
        if self.attack_animation:
            self.attack_animation.elapsed += delta_time
            if self.attack_animation.elapsed >= .17:
                self.apply_attack_impact()
            if self.attack_animation and self.attack_animation.elapsed >= .48:
                self.finish_attack_animation()
            return
        if self.pending_turn:
            self.battle_delay -= delta_time
            if self.battle_delay <= 0:
                turn = self.pending_turn
                self.pending_turn = None
                if turn == "enemy":
                    self.enemy_attack()

    def log_scroll_available(self) -> bool:
        return (
            not self.home_confirmation
            and not self.cheat_open
            and self.scene not in (Scene.TITLE, Scene.GUIDE, Scene.CREATION,
                                   Scene.TALENT, Scene.SAVE_MENU)
            and self._log_scroll_geometry is not None
        )

    def on_mouse_scroll(self, x: float, y: float,
                        scroll_x: float, scroll_y: float) -> None:
        if not self.log_scroll_available() or not (20 <= x <= 335 and 15 <= y <= 445):
            return
        maximum = int(self._log_scroll_geometry[6])
        if scroll_y:
            steps = max(1, int(abs(scroll_y)))
            direction = 1 if scroll_y < 0 else -1
            self.log_scroll = max(0, min(maximum, self.log_scroll + direction * steps))

    def on_mouse_motion(self, x: float, y: float, dx: float, dy: float) -> None:
        self.hovered = next((b for b in self.buttons if b.hit_test(x, y)), None)
        over_scroll = False
        if self.log_scroll_available():
            track_left, track_bottom, track_width, track_height = self._log_scroll_geometry[:4]
            over_scroll = (
                track_left <= x <= track_left + track_width
                and track_bottom <= y <= track_bottom + track_height
            )
        over_name_box = (
            self.scene == Scene.CREATION and self.creation_step == 1
            and not self.home_confirmation and not self.cheat_open
            and self.name_box_hit(x, y)
        )
        over_enemy = (
            self.scene == Scene.BATTLE and len(self.enemies) > 1
            and not self.home_confirmation and not self.cheat_open
            and any(
                left <= x <= left + width and bottom <= y <= bottom + height
                for left, bottom, width, height in self.enemy_hitboxes
            )
        )
        if (self.hovered and not self.hovered.invisible) or over_scroll or over_enemy:
            cursor = self.CURSOR_HAND
        elif over_name_box:
            cursor = self.CURSOR_TEXT
        else:
            cursor = self.CURSOR_DEFAULT
        self.set_mouse_cursor(self.get_system_mouse_cursor(cursor))

    def on_mouse_press(self, x: float, y: float, button: int, modifiers: int) -> None:
        if button != arcade.MOUSE_BUTTON_LEFT:
            return
        if self.log_scroll_available():
            (track_left, track_bottom, track_width, track_height,
             thumb_bottom, thumb_height, maximum, page_count) = self._log_scroll_geometry
            if (track_left <= x <= track_left + track_width
                    and track_bottom <= y <= track_bottom + track_height):
                if thumb_bottom <= y <= thumb_bottom + thumb_height:
                    self.log_scroll_dragging = True
                    self.log_scroll_drag_offset = y - thumb_bottom
                elif y < thumb_bottom:
                    self.log_scroll = min(int(maximum), self.log_scroll + max(1, int(page_count) - 1))
                else:
                    self.log_scroll = max(0, self.log_scroll - max(1, int(page_count) - 1))
                return
        if (self.scene == Scene.CREATION and self.creation_step == 1
                and not self.home_confirmation and not self.cheat_open):
            self.name_input_focused = self.name_box_hit(x, y)
            if self.name_input_focused:
                self.name_caret_timer = 0.0
                return
        if (self.scene == Scene.BATTLE and len(self.enemies) > 1
                and not self.battle_busy and not self.home_confirmation
                and not self.cheat_open):
            for index, (left, bottom, width, height) in enumerate(self.enemy_hitboxes):
                if (index < len(self.enemies)
                        and left <= x <= left + width and bottom <= y <= bottom + height):
                    if index != self.target_index:
                        self.target_index = index
                        self.log(f"你把攻擊目標換成 {self.enemy.name}。")
                        self.configure_buttons()
                    return
        clicked = next((b for b in self.buttons if b.contains(x, y)), None)
        if clicked:
            clicked.action()
            self.hovered = None
        elif self.cheat_open and (self.cheat_focus or self.cheat_dropdown):
            self.unfocus_cheat_field()

    def on_mouse_drag(self, x: float, y: float, dx: float, dy: float,
                      buttons: int, modifiers: int) -> None:
        if not self.log_scroll_dragging or self._log_scroll_geometry is None:
            return
        (track_left, track_bottom, track_width, track_height,
         _thumb_bottom, thumb_height, maximum, _page_count) = self._log_scroll_geometry
        travel = track_height - thumb_height
        if travel <= 0 or maximum <= 0:
            return
        desired_bottom = max(
            track_bottom,
            min(track_bottom + travel, y - self.log_scroll_drag_offset),
        )
        scroll_ratio = 1 - (desired_bottom - track_bottom) / travel
        self.log_scroll = max(0, min(int(maximum), round(scroll_ratio * maximum)))

    def on_mouse_release(self, x: float, y: float,
                         button: int, modifiers: int) -> None:
        if button == arcade.MOUSE_BUTTON_LEFT:
            self.log_scroll_dragging = False

    def shortcut_matches(self, shortcut: str, symbol: int) -> bool:
        if not shortcut:
            return False
        key_name = shortcut.upper()
        aliases = {
            "ESC": (arcade.key.ESCAPE,),
            "ENTER": (arcade.key.ENTER, arcade.key.NUM_ENTER),
        }
        if key_name in aliases:
            return symbol in aliases[key_name]
        if len(key_name) == 1 and key_name.isdigit():
            return symbol in (
                getattr(arcade.key, f"KEY_{key_name}"),
                getattr(arcade.key, f"NUM_{key_name}"),
            )
        if len(key_name) == 1 and key_name.isalpha():
            return symbol == getattr(arcade.key, key_name)
        return False

    def activate_shortcut(self, symbol: int) -> bool:
        for button in self.buttons:
            if button.enabled and self.shortcut_matches(button.shortcut, symbol):
                button.action()
                self.hovered = None
                return True
        return False

    def on_key_press(self, symbol: int, modifiers: int) -> None:
        if symbol in self.CHEAT_PLUS_KEYS:
            self._cheat_plus_down = True
        elif symbol in self.CHEAT_MINUS_KEYS:
            self._cheat_minus_down = True
        if self._cheat_plus_down and self._cheat_minus_down:
            self._cheat_plus_down = False
            self._cheat_minus_down = False
            self.toggle_cheat()
            return
        if self.cheat_open:
            if symbol == arcade.key.BACKSPACE:
                self.cheat_input_backspace()
            elif symbol in (arcade.key.ENTER, arcade.key.NUM_ENTER, arcade.key.ESCAPE):
                self.unfocus_cheat_field()
            return
        if not (self.scene == Scene.CREATION and self.creation_step == 1):
            if self.activate_shortcut(symbol):
                return
        if self.scene != Scene.CREATION or self.creation_step != 1:
            return
        if symbol == arcade.key.V and modifiers & arcade.key.MOD_CTRL:
            self.add_name_text(self.get_clipboard_text())
        elif symbol == arcade.key.BACKSPACE:
            self.name_input = self.name_input[:-1]
            self.name_input_focused = True
            self.name_caret_timer = 0.0
            self.configure_buttons()
        elif symbol in (arcade.key.ENTER, arcade.key.NUM_ENTER):
            self.next_creation_step()

    def on_key_release(self, symbol: int, modifiers: int) -> None:
        if symbol in self.CHEAT_PLUS_KEYS:
            self._cheat_plus_down = False
        elif symbol in self.CHEAT_MINUS_KEYS:
            self._cheat_minus_down = False

    def on_text(self, text: str) -> None:
        if self.cheat_open:
            self.cheat_input_text(text)
            return
        if self.scene != Scene.CREATION or self.creation_step != 1:
            return
        self.add_name_text(text)

def main() -> None:
    RPGWindow()
    arcade.run()


if __name__ == "__main__":
    main()
