r"""由 AI 圖像資產驅動的黑暗奇幻互動 RPG。

Arcade 負責視窗、輸入、文字及 AI PNG 的即時呈現。

執行：.\.venv\Scripts\python.exe rpg.py
"""

from __future__ import annotations

import ctypes
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum, auto
import hashlib
import json
import math
import os
from pathlib import Path
import random
import sys
from typing import Callable

try:
    import arcade
    from pyglet.math import Mat4

    import mage
    from localization import (
        DEFAULT_LOCALE,
        SUPPORTED_LOCALES,
        get_locale,
        set_locale,
        translate,
    )
    import paladin
    import rogue
    from sound_manager import SoundManager
    from perf_probe import PerfProbe
    from ui.bootstrap import AssetWarmupQueue, BootstrapTask
    from ui.combat_icons import ENEMY_STATUS_ICONS, PLAYER_STATUS_ICONS
    from ui.runtime import ResponsiveCanvas, SceneController, SpriteBatchLayer
    from ui.views import GameRuntimeView, LoadingView
    from ui.map_layout import route_boss_geometry, route_node_geometry
    import warlock
    import warrior
    from combat_intents import (
        AggressiveIntentSelector,
        INTENT_SPECS,
        IntentStreak,
        get_intent_spec,
    )
    from encounter_modifiers import (
        BattleModifier,
        choose_battle_modifier,
        modified_enemy_stats,
        opening_shield_for,
        reward_multiplier_for,
    )
    from replay_variation import (
        CampfireOptionSelector,
        RecentEventPicker,
        ShopInventorySelector,
    )
    from route_map import (
        JourneyRoute,
        NodeKind,
        generate_journey_route,
        validate_journey_route,
    )
    from rpg_drawing import (
        BLUE,
        INTENT_ICON_FILES,
        SCREEN_HEIGHT,
        SCREEN_TITLE,
        SCREEN_WIDTH,
        UI_FONT_FAMILY,
        RPGDrawingMixin,
        make_activity_background,
        make_adventure_map,
        make_background,
        make_critical_effect,
        make_player_portrait,
        make_talent_background,
        load_ai_effect,
        load_ai_ui_texture,
        load_tight_ai_ui_texture,
        load_title_logo,
        player_gear_tier,
        skill_effect_files,
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
    SETTINGS = auto()
    CREATION = auto()
    TALENT = auto()
    SUBCLASS = auto()
    ADVENTURE = auto()
    BATTLE = auto()
    REWARD = auto()
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
    agony_grace_turns: int = 0
    doom_turns: int = 0
    doom_damage: int = 0
    weak_turns: int = 0
    weak_multiplier: float = 1.0
    immune_turns: int = 0
    reflect_turns: int = 0
    berserk_stacks: int = 0
    bulwark_stacks: int = 0
    nonhostile_streak: int = 0
    no_immediate_streak: int = 0
    heavy_blow_charged: bool = False


@dataclass
class AttackAnimation:
    attacker: str
    damage: int
    critical: bool
    elapsed: float = 0.0
    impacted: bool = False
    enemy_index: int = 0
    blocked_by: str = ""
    forced_critical: bool = False
    action_id: str = ""
    floating: "FloatingDamage | None" = None
    floating_prime_index: int = 0


@dataclass
class FloatingDamage:
    target: str
    amount: int
    critical: bool
    healing: bool = False
    shielding: bool = False
    elapsed: float = 0.0
    label: object | None = None
    outline_labels: list[object] = field(default_factory=list)
    target_index: int = 0
    pool_slot: int = -1


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
    role: str = "normal"
    disabled_reason: str = ""
    sub_label: str = ""
    icon: str = ""
    icon_only: bool = False
    badge: str = ""
    presentation: str = "auto"
    selected: bool = False
    loading: bool = False
    error: bool = False
    hit_x: float | None = None
    hit_y: float | None = None
    hit_width: float | None = None
    hit_height: float | None = None
    group: str = ""

    def contains(self, px: float, py: float) -> bool:
        return (
            self.enabled
            and self.hit_test(px, py)
        )

    def hit_test(self, px: float, py: float) -> bool:
        center_x = self.x if self.hit_x is None else self.hit_x
        center_y = self.y if self.hit_y is None else self.hit_y
        width = self.width if self.hit_width is None else self.hit_width
        height = self.height if self.hit_height is None else self.hit_height
        return (
            center_x - width / 2 <= px <= center_x + width / 2
            and center_y - height / 2 <= py <= center_y + height / 2
        )




class RPGWindow(RPGDrawingMixin, arcade.Window):
    Scene = Scene
    SKILL_COOLDOWN_TURNS = 1
    LOG_RECORD_LIMIT = 12
    TEXT_CACHE_LIMIT = 1000
    MEASURE_CACHE_LIMIT = 1000
    FIRST_BATTLE_TUTORIAL_KEY = "first_battle_basics"
    FIRST_BATTLE_TUTORIAL_PAGES = (
        (
            "護盾會先承受傷害",
            "藍色護盾條會在血條下方顯示。受到攻擊時，護盾會先扣除，剩餘傷害才會減少血量。",
        ),
        (
            "暴擊是翻盤的時機",
            "暴擊會造成更高傷害，並以金色數字和更強的命中效果呈現。暴擊率可由幸運、裝備與天賦提升。",
        ),
        (
            "三星試煉的額外規則",
            "三星難度的普通戰鬥會同時出現兩名敵人，每回合可使用兩個技能。點擊敵人可切換目標，先集火危險目標。",
        ),
    )

    RACES = (
        ("獸人", "血量 +10"),
        ("人類", "攻擊 +5"),
        ("矮人", "防禦 +5"),
        ("精靈", "暴擊 +1%"),
    )
    JOBS = (
        ("戰士", "血量 +10；升級血量成長提高 50%"),
        ("法師", "攻擊 +5；升級攻擊成長提高 35%"),
        ("聖騎士", "防禦 +5；升級防禦成長提高 35%"),
        ("盜賊", "暴擊 +1%；升級暴擊 +2%；暴擊傷害 175%"),
        ("術士", "攻擊 +5；每次升級使 DOT 傷害提高 1%"),
    )
    JOB_PAGE_SIZE = 3
    TALENT_POINT_INTERVAL = 2
    MAX_NAME_LENGTH = 10
    SAVE_SLOT_COUNT = 3
    SAVE_DIR = (
        Path(os.environ.get("LOCALAPPDATA", Path.home()))
        / "EmberKingdom"
        / "saves"
        if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parent / "saves"
    )
    SAVE_VERSION = 5
    DIFFICULTY_NAMES = {1: "一星難度", 2: "二星難度", 3: "三星難度"}
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
        ("王城門前", "城門就在眼前，最終魔王也在裡面等著你。"),
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
            "王城大門就在前方，門縫裡透出暗紅火光。",
            "城牆後傳來低語，你離最後一戰越來越近。",
            "城門前的石像轉頭看著你，像在等待最後一位挑戰者。",
            "你已站在王城陰影下，只差最後一段路就能踏入王座廳。",
        ),
    )
    SHOP_LORE = (
        "蒙面商人把藥瓶排上桌，等你挑選。",
        "藥瓶閃著不同顏色的光，商人說每一瓶都有效。",
        "商人晃了晃藥瓶，裡面的液體跟著發亮。",
    )
    DIFFICULTY_PROFILES = {
        1: {"turns": (5.0, 7.0), "defense": (.28, .42), "danger_hits": (11.0, 15.0)},
        2: {"turns": (6.0, 8.0), "defense": (.34, .50), "danger_hits": (10.0, 14.0)},
        3: {"turns": (7.0, 9.0), "defense": (.36, .54), "danger_hits": (12.0, 16.0)},
    }
    MAX_DIFFICULTY = 3
    STAR_TOOLTIPS = (
        "標準難度",
        "敵人更強，也更常使用危險招式",
        "一次對付兩隻怪物",
    )
    DUAL_ENEMY_ATTACK_SCALE = .52
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
    HOSTILE_ENEMY_INTENTS = frozenset(
        key for key, spec in INTENT_SPECS.items() if spec.hostile
    )
    CHEAT_PLUS_KEYS = (arcade.key.PLUS, arcade.key.NUM_ADD, arcade.key.EQUAL)
    CHEAT_MINUS_KEYS = (arcade.key.MINUS, arcade.key.NUM_SUBTRACT)
    CHEAT_FIELDS = (
        ("lv", "關卡"),
        ("difficulty", "難度"),
        ("max_hp", "血量上限"),
        ("hp", "目前血量"),
        ("attack", "攻擊"),
        ("defense", "防禦"),
        ("luck", "暴擊率"),
        ("gold", "金幣"),
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
        "cleanse_curse": {"name": "解咒聖水", "desc": "清除身上的衰敗詛咒。", "base": 28},
        "stun_ward": {"name": "醒神清露", "desc": "預先服用，擋下一次昏迷。", "base": 28},
        "dispel_immunity": {"name": "破魔藥劑", "desc": "解除目標敵人的免疫狀態。", "base": 22},
        "heal": {"name": "月泉靈藥", "desc": "立即恢復 50% 最大血量。", "base": 30},
        "full_heal": {"name": "聖輝仙釀", "desc": "立即恢復全部血量。", "base": 52},
    }
    # Compact two-column shelf cards. Drawing and hit testing share these
    # values so the visible card matches its clickable area.
    SHOP_CARD_CENTERS = (430, 750)
    SHOP_CARD_WIDTH = 150
    SHOP_CARD_HEIGHT = 44
    SHOP_CARD_TOP = 500
    SHOP_CARD_ROW_GAP = 55
    START_GIFT_EVENT_NUMBER = 21
    EVENT_DECK = (
        {"title": "倒塌貨車", "background": 1, "options": ("搬開貨箱", "檢查車轍"),
         "intro": "王家貨車翻倒在泥路旁，破布下露出藥瓶與銅幣，車轍卻一路延伸進黑霧。",
         "positive": ("你搬開貨箱，找到完好的補給，也救出受困的押車人。", "車轍帶你找到盜匪遺落的物資，這次追查很值得。"),
         "negative": ("貨箱底下的機關炸開，散落物資也引來一陣混亂。", "你循著假車轍踏入埋伏，只能狼狽突圍。")},
        {"title": "符文石門", "background": 2, "options": ("按亮符號", "聽門後聲音"),
         "intro": "山壁裂出一扇符文石門，六個記號依序亮起，門後傳來低沉的呼喚。",
         "positive": ("你按對符文順序，石門打開並送出寶物。", "你聽出安全的節奏，避開陷阱拿到寶物。"),
         "negative": ("你按錯符文，石門立刻放出攻擊魔法。", "你靠得太近，門縫裡的詛咒纏上了你。")},
        {"title": "鏡影古井", "background": 3, "options": ("汲取井水", "丟石探底"),
         "intro": "荒草中央的古井清澈見底，水面裡的倒影卻比你慢了半拍。",
         "positive": ("井水洗去旅途疲憊，倒影也送上一份意外祝福。", "石子擊碎虛假倒影，井底浮起一只封存完好的袋子。"),
         "negative": ("冰冷井水化成黑霧鑽入掌心，倒影露出不祥笑容。", "回音喚醒井底怪影，你在拉扯中付出不少代價。")},
        {"title": "殘火祭壇", "background": 4, "options": ("觸碰微光", "獻上一枚幣"),
         "intro": "半塌祭壇被藤蔓纏住，中央仍燃著一點不肯熄滅的蒼白火光。",
         "positive": ("微光接受了你，一股暖意流過全身。", "祭壇收下硬幣，回送你更好的獎勵。"),
         "negative": ("火光突然變黑，藏在裡面的詛咒醒了。", "祭壇還想拿走更多東西，你只好立刻離開。")},
        {"title": "無人荒村", "background": 5, "options": ("走向鐘樓", "搜尋民宅"),
         "intro": "荒村突然響起鐘聲，街上空無一人，所有窗紙卻在同一刻鼓動。",
         "positive": ("你讓鐘聲停下，也找到村民留下的謝禮。", "地窖裡有乾糧和藥品，正好補足物資。"),
         "negative": ("鐘聲引來一群鬼影，你受了傷才逃出去。", "空屋裡藏著陷阱，你在搜查時受了傷。")},
        {"title": "斷橋孤舟", "background": 6, "options": ("修補斷橋", "划船渡河"),
         "intro": "洪水沖斷古橋，一艘漏水小舟綁在岸邊，對岸似乎有人揮動燈火。",
         "positive": ("修好的橋承受住水勢，對岸旅人也慷慨答謝。", "你順流越過險灘，還撈起一箱漂流物資。"),
         "negative": ("腐朽橋板突然崩落，你連同工具一起跌入急流。", "小舟在河心進水，你丟下不少東西才勉強上岸。")},
        {"title": "水晶礦坑", "background": 7, "options": ("鑿取水晶", "追蹤敲擊聲"),
         "intro": "舊礦坑長滿發光水晶，深處傳來規律敲擊，像鎚聲也像某種心跳。",
         "positive": ("水晶帶有魔力，碎片也能賣到不少錢。", "你找到受困礦工，他們送你物資作為答謝。"),
         "negative": ("水晶裂縫噴出有毒粉塵，礦道也開始坍塌。", "聲音來自誘捕獵物的礦獸，你付出代價才逃出生天。")},
        {"title": "騎士墓園", "background": 8, "options": ("拔出長劍", "向亡者致敬"),
         "intro": "沉默墓碑環繞著一柄生鏽長劍，風穿過劍格，響起整齊的盔甲碰撞聲。",
         "positive": ("長劍認可你的勇氣，留下力量後安靜下來。", "亡靈接受你的敬意，送你一份禮物。"),
         "negative": ("拔劍驚醒不願安息的騎士，你遭到亡靈圍攻。", "墓碑誤解了你的儀式，陰冷怨氣奪走不少力量。")},
        {"title": "路邊商棚", "background": 9, "options": ("打開貨盒", "試著殺價"),
         "intro": "蒙面商人推來一個上鎖木盒，笑著要你碰碰運氣。",
         "positive": ("盒裡全是稀有補給，商人也承認你押對了運氣。", "你看穿話術談成好交易，帶著額外贈品離開。"),
         "negative": ("木盒噴出詛咒粉塵，商人趁亂偷走你的物資。", "殺價惹怒了保鑣，你吃了虧才成功離開。")},
        {"title": "星光花海", "background": 10, "options": ("採集花瓣", "追隨花粉"),
         "intro": "花叢像落地星河般發亮，每朵花都朝著你轉動，銀色花粉飄向林間。",
         "positive": ("溫順花靈分享治癒花蜜，花瓣也能製成珍貴藥材。", "花粉引你抵達隱密泉眼，精靈留下了旅途祝福。"),
         "negative": ("花瓣閉合成尖牙，麻痺花粉讓你吃盡苦頭。", "花粉將你引進食人花巢，逃出時已損失慘重。")},
        {"title": "烏鴉告示", "background": 11, "options": ("拆開信筒", "核對懸賞印章"),
         "intro": "烏鴉停在王家告示牌上，爪邊綁著信筒，褪色懸賞令的紅蠟仍在流動。",
         "positive": ("信裡的情報幫你找到失物，烏鴉也帶回報酬。", "印章是真的，你完成任務並領到錢。"),
         "negative": ("信筒藏著追蹤咒，假委託人很快找上了你。", "偽造印章觸發警戒法術，你被當成竊賊追趕。")},
        {"title": "獵人機關", "background": 12, "options": ("拆除獸夾", "順著細線追查"),
         "intro": "靴尖勾到細線，泥地下傳來連串機簧聲，獸夾正把獵物趕向樹林深處。",
         "positive": ("你安全拆下精良零件，還救出一隻帶路的靈獸。", "細線通往盜獵者營地，你趁無人時收走補給。"),
         "negative": ("連鎖機關突然啟動，鋸齒與飛箭讓你難以招架。", "你一路追進包圍網，成了獵人真正等待的目標。")},
        {"title": "修女藥箱", "background": 13, "options": ("檢查藥瓶", "閱讀警告字條"),
         "intro": "石台上的藥箱刻有聖徽與抓痕，瓶罐排列整齊，旁邊夾著染血警告。",
         "positive": ("你辨認出安全藥劑，正好補足身體與行囊的缺口。", "字條記下正確配方與藏物位置，修女的準備沒有白費。"),
         "negative": ("標籤被換過了，喝錯藥讓你非常不舒服。", "字條上的咒文傷了你，燒掉它也已經太晚。")},
        {"title": "精靈月車", "background": 14, "options": ("提出交易", "詢問隱密道路"),
         "intro": "精靈商隊從樹影間無聲現身，月銀鈴與三角帆布在霧中泛著柔光。",
         "positive": ("精靈欣賞你的眼光，給出公平價格與額外禮物。", "領隊指向安全捷徑，並贈送抵禦迷霧的物資。"),
         "negative": ("精靈契約暗藏文字陷阱，交易代價遠超預期。", "所謂捷徑通往迷幻森林，你繞了很久才脫困。")},
        {"title": "獸人戰鼓", "background": 15, "options": ("回應鼓點", "潛入鼓陣"),
         "intro": "三面巨鼓震動山谷，鼓槌無人揮動，猩紅火光卻隨每次鼓聲升高。",
         "positive": ("你的節奏獲得戰魂認可，狂野力量灌入全身。", "你在鼓陣中心找到獸人祭品，並安全解除儀式。"),
         "negative": ("錯亂節拍激怒戰魂，震波與幻影將你重重包圍。", "鼓陣早已等著入侵者，伏兵從火光後一擁而上。")},
        {"title": "漂浮魔典", "background": 16, "options": ("閱讀發光咒文", "撕下空白書頁"),
         "intro": "一本破舊魔典懸在半空自動翻頁，符文從紙面飛出，在周圍排成圓環。",
         "positive": ("咒文主動校正你的魔力，書中知識化為實際助力。", "空白頁顯現藏寶路線，殘留魔力也被你收為己用。"),
         "negative": ("危險文字傷了你的眼睛，魔力也跟著失控。", "書頁變成利刃反擊，魔典還對你下了詛咒。")},
        {"title": "霧中渡船", "background": 17, "options": ("付錢上船", "奪槳自行渡河"),
         "intro": "無燈小船滑出濃霧，斗篷船夫伸出乾枯手掌，始終不肯露出面孔。",
         "positive": ("船夫收下船資，將你送到藏有漂流寶箱的安全河灣。", "你駕船穿過霧牆，意外避開危險並撈到補給。"),
         "negative": ("船夫到了河中央又加價，你付出更多才離開。", "霧讓你看錯方向，小船撞上暗礁，物資掉進河裡。")},
        {"title": "遠古龍骸", "background": 18, "options": ("拾起龍骨", "就地舉行葬儀"),
         "intro": "焦黑龍骨橫臥石原，骨縫仍有火光脈動，遠處不時傳回低沉龍吼。",
         "positive": ("龍骨留下的力量進入你體內，碎片也很值錢。", "你安葬了古龍，牠留下最後的寶藏作為回報。"),
         "negative": ("龍骨燙傷你的手，醒來的龍魂開始追你。", "儀式出了錯，龍焰燒掉了部分物資。")},
        {"title": "星象鐘塔", "background": 19, "options": ("校準星盤", "轉動黃銅鐘針"),
         "intro": "荒野鐘塔的巨大星盤仍在運轉，黃銅齒輪映出不屬於今夜的星座。",
         "positive": ("星盤對準夜空，一道好運星光照在你身上。", "鐘針轉到正確時間，密室打開並露出寶物。"),
         "negative": ("錯位星光扭曲周圍時間，你的身體與行囊都受影響。", "逆轉鐘針釋放積壓魔力，齒輪風暴席捲塔頂。")},
        {"title": "極光冰湖", "background": 20, "options": ("踏上冰面", "鑿開冰層"),
         "intro": "極光覆蓋寂靜冰湖，透明冰層下游著巨大黑影，一座冰封寶箱若隱若現。",
         "positive": ("冰面穩穩承住腳步，極光祝福與冰封寶箱都成為收穫。", "你避開湖底黑影鑿出寶箱，寒泉也恢復了精神。"),
         "negative": ("冰層突然龜裂，刺骨湖水與黑影同時逼近。", "鑿擊驚醒湖底巨獸，你丟下許多物資才逃上岸。")},
    )
    EVENT_STAT_KEYS = ("max_hp", "hp", "attack", "defense", "luck", "gold", "potion")
    EVENT_STAT_LABELS = {
        "max_hp": "血",
        "hp": "目前血量",
        "attack": "攻",
        "defense": "守",
        "gold": "錢",
        "luck": "暴擊",
        "potion": "藥水",
    }
    EVENT_KIND_MULTIPLIERS = {7: .35}

    def __init__(self, *, visible: bool = True) -> None:
        # The UI is authored against a fixed 1180x720 canvas. Windows can
        # clamp the logical client height on a high-DPI desktop, so preserve
        # the canvas aspect instead of letting Arcade crop its lower edge.
        self.ui_canvas = ResponsiveCanvas(SCREEN_WIDTH, SCREEN_HEIGHT)
        super().__init__(SCREEN_WIDTH, SCREEN_HEIGHT, SCREEN_TITLE,
                         resizable=True, visible=visible)
        self.set_minimum_size(820, 500)
        self.apply_ui_viewport()
        self.perf_probe = PerfProbe.from_env(capacity=3600)
        self.asset_warmup = AssetWarmupQueue(
            default_budget_ms=5.0, probe=self.perf_probe
        )
        # LoadingView is texture-independent. Heavy images are deliberately
        # absent until its first frame has reached the screen.
        self.background: arcade.Texture | None = None
        self.background_layer = SpriteBatchLayer()
        self.adventure_map: arcade.Texture | None = None
        self.adventure_maps: dict[int, arcade.Texture] = {}
        self.talent_background: arcade.Texture | None = None
        self.battle_backgrounds: dict[int, arcade.Texture] = {}
        self.battle_background: arcade.Texture | None = None
        self.shop_background: arcade.Texture | None = None
        self.campfire_background: arcade.Texture | None = None
        self.event_backgrounds: dict[int, arcade.Texture] = {}
        self.hero_portrait: arcade.Texture | None = None
        self.hero_attack_portrait: arcade.Texture | None = None
        self.hero_hurt_portrait: arcade.Texture | None = None
        self.hero_block_portrait: arcade.Texture | None = None
        self._monster_portrait_cache: dict[tuple[int, str, str], arcade.Texture] = {}
        self._intent_icon_cache: dict[str, arcade.Texture] = {}
        self.enemy_portrait: arcade.Texture | None = None
        self.enemy_portraits: list[arcade.Texture] = []
        self.enemy_attack_portrait: arcade.Texture | None = None
        self.enemy_attack_portraits: list[arcade.Texture] = []
        self.enemy_hurt_portrait: arcade.Texture | None = None
        self.enemy_hurt_portraits: list[arcade.Texture] = []
        self.enemy_block_portrait: arcade.Texture | None = None
        self.enemy_block_portraits: list[arcade.Texture] = []
        self.critical_effect: arcade.Texture | None = None
        self._log_card_skin_cache: dict[tuple, arcade.Texture] = {}
        self._scroll_skin_cache: dict[tuple, arcade.Texture] = {}
        self._measure_cache: dict[tuple[str, int, bool], float] = {}
        self._text_cache: dict[tuple, arcade.Text] = {}
        self._floating_label_pool: list[dict[str, object]] = []
        self.sounds = SoundManager(master_volume=.72, preload=False)
        self.ui_layout_warnings: list[tuple[str, float, float]] = []
        self.ui_truncations: list[tuple[str, str]] = []
        self.scene_transition_elapsed = .28
        self.scene_transition_duration = .28
        self.scene_controller = SceneController(Scene.TITLE)
        self.language_menu_open = False
        self.scene = Scene.TITLE
        self.player = Player()
        self.enemies: list[Enemy] = []
        self.target_index = 0
        self.battle_action_points = 1
        self.player_actions_left = 1
        self.enemy_turn_order: list[int] = []
        self.enemy_turn_skip_player_dot = False
        self.acting_enemy_index = 0
        self.boss_split_done = False
        self.enemy_hitboxes: list[tuple[float, float, float, float]] = []
        self.enemy_intent_hitboxes: list[tuple[float, float, float, float]] = []
        self.hovered_enemy_intent_index: int | None = None
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
        self.focused_button_index = -1
        self.settings_return = Scene.TITLE
        self.ui_scale = 1.0
        self.high_contrast = False
        self.reduce_motion = False
        self.home_confirmation = False
        self.log_scroll = 0
        self.log_scroll_dragging = False
        self.log_scroll_drag_offset = 0.0
        self.battle_log_expanded = False
        self._log_scroll_geometry: tuple[float, ...] | None = None
        self.messages = []
        self.combat_messages: list[str] = []
        self.journey_lore = self.random_journey_lore()
        self.shop_lore = random.choice(self.SHOP_LORE)
        self.victory = False
        self.end_record_open = False
        self.pending_reward_gold = 0
        self.reward_level_before = 1
        self.reward_level_after = 1
        self.run_battles_won = 0
        self.run_enemies_defeated = 0
        self.run_damage_dealt = 0
        self.run_highest_hit = 0
        self.tutorial_seen: set[str] = set()
        self.tutorial_tip = ""
        self.talent_reset_confirmation = False
        self.event_number = 1
        self.event_title = "隨機事件"
        self.event_messages: list[str] = []
        self.event_options: tuple[str, ...] = ("靠近查看", "保持距離")
        self.event_resolved = True
        self.event_kind = "random"
        self.run_seed = 0
        self.recent_event_numbers: list[int] = []
        self.journey_route: JourneyRoute | None = None
        self.route_completed_ids: list[str] = []
        self.route_selected_id: str | None = None
        self.route_active_id: str | None = None
        self.route_preview_chapter = 1
        self.elite_reward_choices: tuple[str, ...] = ()
        self.elite_reward_claimed = True
        self.shop_inventory: tuple[str, ...] = tuple(self.POTIONS)
        self.shop_inventory_level = 0
        self.shop_inventory_node_id = ""
        self.campfire_options: tuple[str, ...] = (
            "rest", "attack", "defense", "luck", "gold",
        )
        self.battle_modifier: BattleModifier | None = None
        self.combat_rng = random.Random()
        self.intent_selector = AggressiveIntentSelector(self.combat_rng)
        self.reset_run_variation()
        self.final_enemy_name = ""
        self.attack_animation: AttackAnimation | None = None
        self.floating_damage: list[FloatingDamage] = []
        self.skill_effects: list[SkillVisual] = []
        self.battle_clock = 0.0
        self._audio_prune_elapsed = 0.0
        self.pending_turn: str | None = None
        self.battle_delay = 0.0
        self.player_block = 0
        self.enemy_block = 0
        self.display_player_hp = float(self.player.hp)
        self.display_player_block = 0.0
        self.display_enemy_hp: list[float] = []
        self.display_enemy_block: list[float] = []
        self._last_player_block = 0
        self._last_enemy_blocks: list[int] = []
        self.hit_stop_remaining = 0.0
        self.combat_impact_remaining = 0.0
        self.combat_impact_duration = .18
        self.combat_impact_target = ""
        self.combat_impact_enemy_index = 0
        self.camera_shake_remaining = 0.0
        self.camera_shake_duration = .16
        self.camera_shake_strength = 0.0
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
        self.pressed_button: Button | None = None
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
        self.locale = DEFAULT_LOCALE
        set_locale(self.locale)
        self.job_clears: dict[str, int] = {}
        self.load_job_progress()
        self.refresh_save_slots()
        self._install_ime_support()
        self.configure_buttons()
        # A real Arcade View now owns frame events.  The compatibility view
        # forwards into the existing RPGWindow methods so save files, callbacks
        # and public APIs remain unchanged during incremental scene migration.
        self.game_view = GameRuntimeView(self)
        bootstrap_tasks = (
            BootstrapTask("Loading title background", self._load_title_background),
            BootstrapTask("Preparing title logo", load_title_logo),
            BootstrapTask(
                "Preparing interface materials",
                lambda: load_ai_ui_texture("surface.material"),
            ),
            BootstrapTask("Preparing interface audio", self._load_core_ui_audio),
        )
        self.loading_view = LoadingView(
            bootstrap_tasks, window=self, total_tasks=len(bootstrap_tasks),
            step_budget_ms=8.0, minimum_display_seconds=.30,
            on_complete=self._complete_bootstrap,
            on_error=self._bootstrap_failed,
            probe=self.perf_probe, reduced_motion=self.reduce_motion,
            subtitle="Preparing your journey...",
        )
        self.show_view(self.loading_view)

    def _load_title_background(self) -> None:
        self.background = make_background()
        self.background_layer.set_texture(
            "main", self.background, center_x=SCREEN_WIDTH / 2,
            center_y=SCREEN_HEIGHT / 2, width=SCREEN_WIDTH,
            height=SCREEN_HEIGHT,
        )

    def _load_core_ui_audio(self) -> None:
        self.sounds.preload_group("ui")

    def _bootstrap_failed(self, error: Exception) -> None:
        self.perf_probe.mark(
            "bootstrap.failed", error_type=type(error).__name__
        )

    def _complete_bootstrap(self) -> None:
        self._enqueue_idle_warmups()
        self.show_view(self.game_view)

    def _ensure_adventure_map(self, chapter: int | None = None) -> arcade.Texture:
        chapter = max(1, min(5, int(
            self.route_preview_chapter if chapter is None else chapter
        )))
        texture = self.adventure_maps.get(chapter)
        if texture is None:
            texture = make_adventure_map(chapter)
            self.adventure_maps[chapter] = texture
        self.adventure_map = texture
        return texture

    def _ensure_talent_background(self) -> arcade.Texture:
        if self.talent_background is None:
            self.talent_background = make_talent_background()
        return self.talent_background

    def _ensure_battle_background(self, stage: int) -> arcade.Texture:
        stage = max(1, min(5, int(stage)))
        texture = self.battle_backgrounds.get(stage)
        if texture is None:
            texture = make_activity_background("battle", stage)
            self.battle_backgrounds[stage] = texture
        self.battle_background = texture
        return texture

    def _ensure_shop_background(self) -> arcade.Texture:
        if self.shop_background is None:
            self.shop_background = make_activity_background("shop")
        return self.shop_background

    def _ensure_campfire_background(self) -> arcade.Texture:
        if self.campfire_background is None:
            self.campfire_background = make_activity_background("campfire")
        return self.campfire_background

    def _ensure_critical_effect(self) -> arcade.Texture:
        if self.critical_effect is None:
            self.critical_effect = make_critical_effect()
        return self.critical_effect

    def load_player_combat_portraits(self) -> None:
        """Load the four combat poses for the current player identity."""
        p = self.player
        self.hero_portrait = make_player_portrait(
            p.sex, p.race, p.job, p.lv, pose="idle"
        )
        self.hero_attack_portrait = make_player_portrait(
            p.sex, p.race, p.job, p.lv, pose="attack"
        )
        self.hero_hurt_portrait = make_player_portrait(
            p.sex, p.race, p.job, p.lv, pose="hurt"
        )
        self.hero_block_portrait = make_player_portrait(
            p.sex, p.race, p.job, p.lv, pose="block"
        )

    def _enqueue_idle_warmups(self) -> None:
        """Warm likely next-scene resources without blocking the first title."""
        queue = self.asset_warmup
        generation = queue.generation
        for chapter in range(1, 6):
            queue.enqueue(
                ("background:adventure", chapter),
                lambda selected=chapter: self._ensure_adventure_map(selected),
                priority=91 - chapter, generation=generation,
            )
        queue.enqueue(
            "background:battle:1", lambda: self._ensure_battle_background(1),
            priority=85, generation=generation,
        )
        queue.enqueue(
            "effect:impact", self._ensure_critical_effect,
            priority=80, generation=generation,
        )
        battle_ui = (
            ("meter.frame", False),
            ("meter.hp", True),
            ("meter.shield", True),
            ("frame.skill_slot", False),
            ("icons/markers/action_point.png", False),
            ("icons/markers/ground_shadow.png", False),
            ("icons/markers/badge_round.png", False),
            ("icons/markers/target_selected.png", False),
        )
        for asset_name, tight in battle_ui:
            loader = (
                (lambda name=asset_name: load_tight_ai_ui_texture(name, 1))
                if tight else
                (lambda name=asset_name: load_ai_ui_texture(name))
            )
            queue.enqueue(
                ("battle-ui", asset_name),
                loader,
                priority=79, generation=generation,
            )
        for intent in INTENT_ICON_FILES:
            queue.enqueue(
                ("intent", intent),
                lambda intent_name=intent:
                    self.intent_icon_texture(intent_name),
                priority=76, generation=generation,
            )
        status_icon_paths = sorted({
            spec.asset_path
            for registry in (PLAYER_STATUS_ICONS, ENEMY_STATUS_ICONS)
            for spec in registry.values()
        })
        for asset_name in status_icon_paths:
            queue.enqueue(
                ("status-icon", asset_name),
                lambda name=asset_name: load_tight_ai_ui_texture(name, 2),
                priority=74, generation=generation,
            )
        for style in ("damage", "critical", "healing", "shielding"):
            for slot in range(3):
                queue.enqueue(
                    ("floating-label", style, slot),
                    lambda style_name=style: self.prewarm_floating_label_slot(
                        style_name
                    ),
                    priority=70, generation=generation,
                )
        for kind in ("血量型", "攻擊型", "防禦型"):
            for pose in ("idle", "attack", "hurt", "block"):
                queue.enqueue(
                    ("monster", 1, kind, pose),
                    lambda monster_kind=kind, monster_pose=pose:
                        self.monster_portrait(
                            1, monster_kind, monster_pose
                        ),
                    priority=65, generation=generation,
                )
        queue.enqueue(
            "background:shop", self._ensure_shop_background,
            priority=25, generation=generation,
        )
        queue.enqueue(
            "background:campfire", self._ensure_campfire_background,
            priority=25, generation=generation,
        )
        queue.enqueue(
            "background:talent", self._ensure_talent_background,
            priority=20, generation=generation,
        )
        for group_index, group in enumerate(("combat", "magic", "progression")):
            for cue in self.sounds.warmup_groups[group]:
                queue.enqueue(
                    ("sound", cue),
                    lambda cue_name=cue: self.sounds.load(cue_name),
                    priority=60 - group_index * 10,
                    generation=generation,
                )

    def enqueue_job_effect_warmups(self, *jobs: str) -> None:
        generation = self.asset_warmup.generation
        for job in jobs:
            if not job:
                continue
            for filename in skill_effect_files(job):
                self.asset_warmup.enqueue(
                    ("skill-vfx", filename),
                    lambda effect_file=filename: load_ai_effect(effect_file),
                    priority=78, generation=generation,
                )

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
            font.lfFaceName = UI_FONT_FAMILY
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
            and self.creation_step == 0
            and not self.home_confirmation
            and not self.cheat_open
        )

    # ---------- 場景與戰鬥視覺狀態 ----------
    @property
    def scene(self) -> Scene:
        controller = getattr(self, "scene_controller", None)
        return controller.current if controller is not None else getattr(
            self, "_scene", Scene.TITLE
        )

    @scene.setter
    def scene(self, value: Scene) -> None:
        controller = getattr(self, "scene_controller", None)
        previous = (controller.current if controller is not None
                    else getattr(self, "_scene", None))
        if value != Scene.TITLE:
            self.language_menu_open = False
        self._scene = value
        if controller is not None:
            controller.change(value)
        if (previous is not None and previous != value
                and hasattr(self, "scene_transition_elapsed")):
            self.scene_transition_elapsed = 0.0

    def play_sound(self, name: str, volume: float = 1.0,
                   vary: bool = True) -> None:
        """Play one optional cue without letting audio disable game actions."""
        self.sounds.play(name, volume=volume, vary=vary)

    def rng_for(self, namespace: str, *parts: object) -> random.Random:
        """Return deterministic gameplay RNG isolated from cosmetic calls."""
        seed = ":".join((str(self.run_seed), namespace, *(str(p) for p in parts)))
        return random.Random(seed)

    def reset_run_variation(
        self, seed: int | None = None, *, recent_events: list[int] | None = None
    ) -> None:
        """Start or restore one reproducible run without touching global RNG."""
        if seed is None:
            seed = random.SystemRandom().getrandbits(63)
        self.run_seed = max(0, int(seed))
        self.recent_event_numbers = list(recent_events or ())[-3:]
        self.initialize_journey_route()
        self.shop_inventory = tuple(self.POTIONS)
        self.shop_inventory_level = 0
        self.shop_inventory_node_id = ""
        self.campfire_options = (
            "rest", "attack", "defense", "luck", "gold",
        )
        self.battle_modifier = None
        self.combat_rng = self.rng_for("combat", 0, self.difficulty)
        self.intent_selector = AggressiveIntentSelector(self.combat_rng)

    def initialize_journey_route(
        self,
        route: JourneyRoute | None = None,
        *,
        completed_ids: list[str] | tuple[str, ...] = (),
        selected_id: str | None = None,
        active_id: str | None = None,
    ) -> None:
        """Install one deterministic route and sanitize its persisted cursor."""
        candidate = route or generate_journey_route(self.run_seed, self.difficulty)
        validate_journey_route(candidate)
        if (candidate.run_seed != self.run_seed
                or candidate.difficulty != self.difficulty):
            raise ValueError("saved route does not match the active run")
        self.journey_route = candidate
        known = {node.id for node in candidate.nodes}
        ordered: list[str] = []
        for node_id in completed_ids:
            if node_id in known and node_id not in ordered:
                ordered.append(node_id)
        self.route_completed_ids = ordered
        self.route_active_id = None
        self.route_selected_id = None
        reachable = set(self.route_reachable_ids())
        self.route_selected_id = selected_id if selected_id in reachable else None
        self.route_active_id = (
            active_id if active_id in known and active_id not in ordered else None
        )
        if self.route_active_id:
            self.route_selected_id = None
        self.route_preview_chapter = self.current_route_chapter()
        self.elite_reward_choices = ()
        self.elite_reward_claimed = True

    def route_node(self, node_id: str | None = None):
        if self.journey_route is None:
            return None
        target = self.route_active_id if node_id is None else node_id
        if not target:
            return None
        try:
            return self.journey_route.node_by_id(target)
        except (KeyError, ValueError):
            return None

    def route_reachable_ids(self) -> tuple[str, ...]:
        """Return the next legal mouse-selectable nodes in stable route order."""
        route = self.journey_route
        if route is None or self.route_active_id:
            return ()
        if not self.route_completed_ids:
            return tuple(route.start_ids)
        last_id = self.route_completed_ids[-1]
        try:
            successors = route.available_successors(last_id)
        except (KeyError, ValueError):
            return ()
        completed = set(self.route_completed_ids)
        return tuple(node.id for node in successors if node.id not in completed)

    def route_reachable_nodes(self) -> tuple:
        route = self.journey_route
        if route is None:
            return ()
        nodes = []
        for node_id in self.route_reachable_ids():
            try:
                nodes.append(route.node_by_id(node_id))
            except (KeyError, ValueError):
                continue
        return tuple(nodes)

    def current_route_chapter(self) -> int:
        """Return the chapter that currently owns the next playable node."""
        route = self.journey_route
        if route is None:
            return 1
        candidates = (
            self.route_active_id,
            self.route_selected_id,
            *self.route_reachable_ids(),
        )
        for node_id in candidates:
            if not node_id:
                continue
            try:
                return max(1, min(5, route.node_by_id(node_id).chapter))
            except (KeyError, ValueError):
                continue
        if self.route_completed_ids:
            try:
                chapter = route.node_by_id(self.route_completed_ids[-1]).chapter
                return max(1, min(5, chapter))
            except (KeyError, ValueError):
                pass
        return 1

    def set_route_preview_chapter(self, chapter: int) -> None:
        """Show any chapter map without changing the committed route."""
        if self.scene != Scene.ADVENTURE:
            return
        self.route_preview_chapter = max(1, min(5, int(chapter)))
        self._ensure_adventure_map(self.route_preview_chapter)
        self.configure_buttons()

    def select_route_node(self, node_id: str) -> None:
        if self.scene != Scene.ADVENTURE or node_id not in self.route_reachable_ids():
            return
        self.route_selected_id = node_id
        self.play_sound("map_advance", volume=.42)
        self.configure_buttons()

    def confirm_route_selection(self) -> None:
        node_id = self.route_selected_id
        if self.scene != Scene.ADVENTURE or node_id not in self.route_reachable_ids():
            return
        node = self.route_node(node_id)
        if node is None:
            return
        self.route_active_id = node_id
        self.route_selected_id = None
        self.journey_lore = self.random_journey_lore()
        self.log(self.journey_lore)
        if node.kind in (NodeKind.BATTLE, NodeKind.ELITE, NodeKind.BOSS):
            self.start_battle(rank_override=6 if node.kind is NodeKind.BOSS else None)
        elif node.kind is NodeKind.CAMPFIRE:
            self.open_campfire()
        elif node.kind is NodeKind.SHOP:
            self.open_black_market()

    def begin_route_at_start(self) -> None:
        """The departure gift flows directly into the route's opening battle."""
        starts = self.route_reachable_ids()
        if not starts:
            self.scene = Scene.ADVENTURE
            self.configure_buttons()
            return
        self.scene = Scene.ADVENTURE
        self.route_selected_id = starts[0]
        self.confirm_route_selection()

    def complete_active_route_node(self) -> None:
        node_id = self.route_active_id
        if node_id and node_id not in self.route_completed_ids:
            self.route_completed_ids.append(node_id)
        self.route_active_id = None
        self.route_selected_id = None
        self.elite_reward_choices = ()
        self.elite_reward_claimed = True
        self.scene = Scene.ADVENTURE
        self.route_preview_chapter = self.current_route_chapter()
        self.configure_buttons()

    def migrate_legacy_route_progress(self, completed_battles: int) -> None:
        """Place a v4 save before its next fight without granting free progress."""
        route = self.journey_route
        if route is None:
            return
        target = max(0, min(20, int(completed_battles)))
        completed: list[str] = []
        battle_count = 0
        next_ids = tuple(route.start_ids)
        while next_ids and battle_count < target:
            node_id = next_ids[0]
            node = route.node_by_id(node_id)
            completed.append(node_id)
            if node.kind in (NodeKind.BATTLE, NodeKind.ELITE):
                battle_count += 1
            next_ids = tuple(
                node.id for node in route.available_successors(node_id)
            )
        self.route_completed_ids = completed
        self.route_selected_id = None
        self.route_active_id = None

    @staticmethod
    def stable_legacy_run_seed(data: dict) -> int:
        payload = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(payload.encode("utf-8")).digest()
        return int.from_bytes(digest[:8], "big") & ((1 << 63) - 1)

    def prepare_battle_rng(self) -> None:
        self.combat_rng = self.rng_for(
            "combat", self.route_active_id or self.player.lv, self.difficulty
        )
        hostile_bias = {1: .55, 2: .60, 3: .60}[self.difficulty]
        self.intent_selector = AggressiveIntentSelector(
            self.combat_rng, hostile_bias=hostile_bias,
            max_non_hostile_streak=2, max_no_immediate_streak=2,
        )

    def add_floating_damage(self, target: str, amount: int, critical: bool,
                            healing: bool = False, shielding: bool = False,
                            target_index: int = 0) -> FloatingDamage:
        """Acquire a warmed label group before publishing combat feedback."""
        floating = FloatingDamage(
            target, amount, critical, healing=healing,
            shielding=shielding, target_index=target_index,
        )
        self.prepare_floating_damage_label(floating)
        self.floating_damage.append(floating)
        return floating

    def prepare_attack_feedback(self, animation: AttackAnimation) -> None:
        """Reserve the final damage label during the attack wind-up."""
        target = "enemy" if animation.attacker == "player" else "player"
        floating = FloatingDamage(
            target, animation.damage, animation.critical,
            target_index=animation.enemy_index,
        )
        self.prepare_floating_damage_label(floating)
        animation.floating = floating

    def publish_attack_feedback(self, animation: AttackAnimation) -> None:
        """Publish a label whose glyph layout was primed before impact."""
        floating = animation.floating
        if floating is None:
            target = "enemy" if animation.attacker == "player" else "player"
            self.add_floating_damage(
                target, animation.damage, animation.critical,
                target_index=animation.enemy_index,
            )
            return
        animation.floating = None
        floating.elapsed = 0.0
        self.floating_damage.append(floating)

    def clear_floating_damage_feedback(self) -> None:
        for floating in self.floating_damage:
            self.release_floating_damage_label(floating)
        self.floating_damage.clear()

    @staticmethod
    def skill_sound(action_id: str) -> str:
        if action_id == "meteor":
            return "meteor_fall"
        if action_id in {"fireball", "pyroblast"}:
            return "fireball"
        if action_id in {"ice_wall", "ice_barrier", "frost_mastery"}:
            return "ice_spell"
        if action_id in {"shadowstep", "vanish", "backstab", "assassinate", "sap"}:
            return "shadow_step"
        if action_id == "smoke_bomb":
            return "smoke_bomb"
        if action_id in {"smite", "judgment", "divine_wrath", "divine_protection"}:
            return "holy_cast"
        if action_id in {"agony", "hex", "doom", "corruption_bolt", "soul_drain"}:
            return "curse"
        if action_id in {"counter", "fortify", "shield_mastery"}:
            return "shield"
        return "sword_swing"

    def reset_combat_feedback(self) -> None:
        """將 HUD 補間基準對齊目前戰鬥數值。"""
        self.display_player_hp = float(self.player.hp)
        self.display_player_block = float(self.player_block)
        self.display_enemy_hp = [float(enemy.hp) for enemy in self.enemies]
        self.display_enemy_block = [float(enemy.block) for enemy in self.enemies]
        self._last_player_block = self.player_block
        self._last_enemy_blocks = [enemy.block for enemy in self.enemies]
        self.hit_stop_remaining = 0.0
        self.combat_impact_remaining = 0.0
        self.camera_shake_remaining = 0.0

    @staticmethod
    def _approach_display_value(current: float, target: float,
                                delta_time: float) -> float:
        if abs(current - target) < .03:
            return target
        blend = 1.0 - math.exp(-11.5 * max(0.0, delta_time))
        return current + (target - current) * blend

    def update_combat_feedback(self, delta_time: float) -> None:
        """更新 HUD 補間、護盾回饋與命中視覺計時。"""
        if self.scene_transition_elapsed < self.scene_transition_duration:
            transition_speed = 2.2 if self.reduce_motion else 1.0
            self.scene_transition_elapsed = min(
                self.scene_transition_duration,
                self.scene_transition_elapsed + delta_time * transition_speed,
            )

        if self.scene != Scene.BATTLE:
            self.combat_impact_remaining = 0.0
            self.camera_shake_remaining = 0.0
            return

        self.display_player_hp = self._approach_display_value(
            self.display_player_hp, float(self.player.hp), delta_time
        )
        self.display_player_block = self._approach_display_value(
            self.display_player_block, float(self.player_block), delta_time
        )

        while len(self.display_enemy_hp) < len(self.enemies):
            enemy = self.enemies[len(self.display_enemy_hp)]
            self.display_enemy_hp.append(float(enemy.hp))
            self.display_enemy_block.append(float(enemy.block))
        self.display_enemy_hp = self.display_enemy_hp[:len(self.enemies)]
        self.display_enemy_block = self.display_enemy_block[:len(self.enemies)]
        for index, enemy in enumerate(self.enemies):
            self.display_enemy_hp[index] = self._approach_display_value(
                self.display_enemy_hp[index], float(enemy.hp), delta_time
            )
            self.display_enemy_block[index] = self._approach_display_value(
                self.display_enemy_block[index], float(enemy.block), delta_time
            )

        gained_player_block = self.player_block - self._last_player_block
        if gained_player_block > 0:
            self.add_floating_damage(
                "player", gained_player_block, False, shielding=True
            )
        self._last_player_block = self.player_block

        while len(self._last_enemy_blocks) < len(self.enemies):
            self._last_enemy_blocks.append(self.enemies[len(self._last_enemy_blocks)].block)
        self._last_enemy_blocks = self._last_enemy_blocks[:len(self.enemies)]
        for index, enemy in enumerate(self.enemies):
            gained_block = enemy.block - self._last_enemy_blocks[index]
            if gained_block > 0:
                self.add_floating_damage(
                    "enemy", gained_block, False, shielding=True,
                    target_index=index,
                )
            self._last_enemy_blocks[index] = enemy.block

        self.combat_impact_remaining = max(
            0.0, self.combat_impact_remaining - delta_time
        )
        self.camera_shake_remaining = max(
            0.0, self.camera_shake_remaining - delta_time
        )

    def trigger_combat_impact(self, target: str, enemy_index: int,
                              critical: bool) -> None:
        if self.reduce_motion:
            self.hit_stop_remaining = .018
            self.combat_impact_remaining = .07
            self.camera_shake_remaining = 0.0
            return
        self.hit_stop_remaining = .09 if critical else .055
        self.combat_impact_duration = .24 if critical else .18
        self.combat_impact_remaining = self.combat_impact_duration
        self.combat_impact_target = target
        self.combat_impact_enemy_index = enemy_index
        self.camera_shake_duration = .21 if critical else .15
        self.camera_shake_remaining = self.camera_shake_duration
        self.camera_shake_strength = 7.5 if critical else 4.5

    def combat_camera_offset(self) -> tuple[float, float]:
        if self.camera_shake_remaining <= 0 or self.reduce_motion:
            return 0.0, 0.0
        progress = 1.0 - self.camera_shake_remaining / max(
            .001, self.camera_shake_duration
        )
        strength = self.camera_shake_strength * (1.0 - progress) ** 1.35
        return (
            math.sin(progress * math.pi * 13.0) * strength,
            math.sin(progress * math.pi * 17.0 + .8) * strength * .55,
        )

    def combat_knockback_offset(self, target: str,
                                enemy_index: int = 0) -> float:
        if (self.combat_impact_remaining <= 0
                or self.combat_impact_target != target
                or (target == "enemy"
                    and enemy_index != self.combat_impact_enemy_index)):
            return 0.0
        progress = 1.0 - self.combat_impact_remaining / max(
            .001, self.combat_impact_duration
        )
        kick = math.sin(min(1.0, progress) * math.pi) * (22.0 if target == "enemy" else 18.0)
        return kick if target == "enemy" else -kick

    def combat_flash_alpha(self, target: str, enemy_index: int = 0) -> int:
        if (self.combat_impact_remaining <= 0
                or self.combat_impact_target != target
                or (target == "enemy"
                    and enemy_index != self.combat_impact_enemy_index)):
            return 0
        progress = 1.0 - self.combat_impact_remaining / max(
            .001, self.combat_impact_duration
        )
        return round(190 * max(0.0, 1.0 - progress / .42))

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
        if not isinstance(data, dict):
            return
        saved_locale = data.get("locale", DEFAULT_LOCALE)
        if saved_locale in SUPPORTED_LOCALES:
            set_locale(saved_locale)
            self.locale = get_locale()
        clears = data.get("job_clears")
        if isinstance(clears, dict):
            for job, _bonus in self.JOBS:
                try:
                    self.job_clears[job] = max(
                        0, min(self.MAX_DIFFICULTY, int(clears.get(job, 0)))
                    )
                except (TypeError, ValueError):
                    continue

    def save_job_progress(self) -> None:
        try:
            self.SAVE_DIR.mkdir(parents=True, exist_ok=True)
            self.progress_path().write_text(
                json.dumps(
                    {
                        "version": 2,
                        "locale": self.locale,
                        "job_clears": self.job_clears,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
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
        if kind == "cleanse_curse":
            return self.player_curse_turns > 0
        if kind == "stun_ward":
            return self.player_stun_immunity_turns < 1
        if kind == "dispel_immunity":
            return bool(self.enemy and self.enemy.immune_turns > 0)
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
        legacy_purify_count = clean_count(p.potion_bag.get("purify", 0))
        legacy_purify_purchases = clean_count(p.potion_purchase_counts.get("purify", 0))
        legacy_reveal_count = clean_count(p.potion_bag.get("reveal", 0))
        legacy_reveal_purchases = clean_count(p.potion_purchase_counts.get("reveal", 0))
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
        if legacy_purify_count > 0:
            p.potion_bag["cleanse_curse"] = self.potion_count("cleanse_curse") + legacy_purify_count
        if legacy_purify_purchases > 0:
            p.potion_purchase_counts["cleanse_curse"] = (
                self.potion_purchase_count("cleanse_curse") + legacy_purify_purchases
            )
        if legacy_reveal_count > 0:
            p.potion_bag["dispel_immunity"] = (
                self.potion_count("dispel_immunity") + legacy_reveal_count
            )
        if legacy_reveal_purchases > 0:
            p.potion_purchase_counts["dispel_immunity"] = (
                self.potion_purchase_count("dispel_immunity") + legacy_reveal_purchases
            )
        if p.potions > 0:
            p.potion_bag["heal"] = self.potion_count("heal") + p.potions
            p.potions = 0

    def can_open_black_market(self) -> bool:
        return any(self.potion_available(kind) for kind in self.POTIONS)

    def shop_has_affordable_offer(self) -> bool:
        return any(
            self.potion_available(kind) for kind in self.shop_inventory
        )

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
            self.add_floating_damage("player", amount, False, healing=True)

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

    def preview_skill_damage(self, multiplier: float,
                             guaranteed_critical: bool = False) -> int:
        """Return current class-skill damage before enemy shielding."""
        attack_power = self.effective_player_attack() * multiplier
        attack_power += self.warrior_attack_bonus
        if self.potion_attack_boost:
            attack_power *= 1.5
        if guaranteed_critical or self.forced_critical:
            attack_power *= self.player_critical_damage_multiplier()
        return max(1, math.ceil(attack_power))

    def preview_skill_damage_text(self, multiplier: float,
                                  guaranteed_critical: bool = False) -> str:
        damage = self.preview_skill_damage(multiplier, guaranteed_critical)
        if guaranteed_critical or self.forced_critical:
            return f"造成 {damage} 點傷害（必定暴擊）"
        critical = self.preview_skill_damage(multiplier, True)
        return f"造成 {damage} 點傷害（暴擊 {critical} 點）"

    def preview_skill_block(self, multiplier: float) -> int:
        return max(1, math.ceil(self.effective_player_defense() * multiplier))

    def preview_max_hp_amount(self, rate: float) -> int:
        return max(1, math.ceil(self.player.max_hp * rate))

    def critical_chance_for_luck(self, luck: int | float) -> float:
        """Return the real natural critical chance represented by a luck value."""
        return round(max(0.0, float(luck)), 1)

    def player_critical_damage_multiplier(self) -> float:
        """Rogues trade raw stat growth for more lethal critical hits."""
        return 1.75 if self.player.job == "盜賊" else 1.50

    def natural_critical_chance(self) -> float:
        return self.critical_chance_for_luck(self.player.luck)

    def displayed_critical_chance(self) -> float:
        """Include a queued or currently animating guaranteed critical hit."""
        animation = self.attack_animation
        if self.forced_critical or (
            animation is not None
            and animation.attacker == "player"
            and animation.forced_critical
        ):
            return 100.0
        return self.natural_critical_chance()

    def roll_player_critical(self) -> tuple[bool, bool]:
        forced = self.forced_critical
        critical = forced or self.combat_rng.random() * 100 < self.natural_critical_chance()
        return critical, forced

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
        if self.attack_animation and self.attack_animation.floating:
            self.release_floating_damage_label(
                self.attack_animation.floating
            )
        self.attack_animation = None
        self.skill_effects.clear()
        self.battle_clock = 0.0
        self.player_block = 0
        self.player_dot_damage = 0
        self.player_dot_turns = 0
        self.player_dot_stacks = 0
        self.player_curse_turns = 0
        for enemy in self.enemies:
            enemy.block = 0
            enemy.intent = ""
            enemy.nonhostile_streak = 0
            enemy.no_immediate_streak = 0
            enemy.heavy_blow_charged = False
            enemy.stealth_turns = 0
            enemy.immune_turns = 0
            enemy.reflect_turns = 0
            enemy.berserk_stacks = 0
            enemy.bulwark_stacks = 0
        self.enemy_turn_order = []
        self.enemy_turn_skip_player_dot = False
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
        self.play_sound("ui_talent_unlock", volume=.82)
        self.configure_buttons()

    def reset_class_talents(self) -> None:
        if not self.talent_reset_confirmation:
            self.talent_reset_confirmation = True
            self.configure_buttons()
            return
        spent = self.class_talent_spent()
        if spent < 1:
            return
        self.player.talent_points += spent
        self.class_talents().clear()
        self.class_skill_cooldowns.clear()
        self.talent_reset_confirmation = False
        self.log(f"你重置了{self.player.job}天賦，所有點數已返還。")
        self.configure_buttons()

    def open_talent_page(self) -> None:
        if not self.has_class_talents():
            return
        self.scene = Scene.TALENT
        self.configure_buttons()

    def close_talent_page(self) -> None:
        self.talent_reset_confirmation = False
        self.scene = Scene.ADVENTURE
        self.configure_buttons()

    def cancel_talent_reset(self) -> None:
        self.talent_reset_confirmation = False
        self.configure_buttons()

    def dismiss_tutorial(self) -> None:
        if self.tutorial_tip:
            self.tutorial_seen.add(self.FIRST_BATTLE_TUTORIAL_KEY)
        self.tutorial_tip = ""
        self.configure_buttons()

    def battle_tutorial_page(self) -> int:
        if not self.tutorial_tip.startswith(f"{self.FIRST_BATTLE_TUTORIAL_KEY}:"):
            return 0
        try:
            return max(0, min(
                len(self.FIRST_BATTLE_TUTORIAL_PAGES) - 1,
                int(self.tutorial_tip.rsplit(":", 1)[1]),
            ))
        except (TypeError, ValueError):
            return 0

    def continue_battle_tutorial(self) -> None:
        if not self.tutorial_tip:
            return
        next_page = self.battle_tutorial_page() + 1
        if next_page >= len(self.FIRST_BATTLE_TUTORIAL_PAGES):
            self.dismiss_tutorial()
            return
        self.tutorial_tip = f"{self.FIRST_BATTLE_TUTORIAL_KEY}:{next_page}"
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
            "獸人": "強健體魄",
            "人類": "快速適應",
            "矮人": "尋金本能",
            "精靈": "天生好運",
        }[race]

    def job_skill_name(self, job: str | None = None) -> str:
        job = job or self.player.job
        return self.CLASS_PROFILES[job].LEGACY_NAME

    def race_talent_description(self, race: str | None = None) -> str:
        race = race or self.player.race
        return {
            "獸人": "營火可回 50% 血量，下場戰鬥開始時多 15% 護盾。",
            "人類": "在營火提升能力時，攻防 +5%，暴擊 +2%。",
            "矮人": "在營火選擇金幣時，獲得的金幣加倍。",
            "精靈": "事件遇到壞結果的機率降低 20%。",
        }[race]

    def job_skill_description(self, job: str | None = None) -> str:
        job = job or self.player.job
        profile = self.CLASS_PROFILES[job]
        dynamic_description = getattr(profile, "legacy_description", None)
        if callable(dynamic_description):
            return dynamic_description(self)
        return profile.LEGACY_DESCRIPTION

    def job_skill_tooltip(self, job: str | None = None) -> str:
        return f"{self.job_skill_description(job)} 使用後不會用掉這回合的行動。"

    @staticmethod
    def battle_action_name(label: str) -> str:
        return label.replace(" 已用", "").split(" CD", 1)[0].strip()

    def battle_skill_icon(self, job: str, action_id: str = "legacy") -> str:
        job_dir = {
            "戰士": "warrior", "法師": "mage", "聖騎士": "paladin",
            "盜賊": "rogue", "術士": "warlock",
        }[job]
        legacy_icons = {
            "戰士": "icons/talents/warrior/last_stand.png",
            "法師": "icons/talents/warlock/hex.png",
            "聖騎士": "icons/talents/paladin/guardian_angel.png",
            "盜賊": "icons/intents/stun.png",
            "術士": "icons/talents/warlock/life_tap.png",
        }
        if action_id == "legacy":
            return legacy_icons[job]
        aliases = {
            "戰士": {"slash": "weapon_mastery", "guard": "shield_mastery"},
            "法師": {"fireball": "fire_mastery", "ice_armor": "frost_mastery"},
            "聖騎士": {"smite": "holy_might", "blessing": "devotion"},
            "盜賊": {"stab": "dagger_mastery", "smokescreen": "evasion"},
            "術士": {"corruption_bolt": "corruption_mastery", "dark_charm": "dark_ward"},
        }
        icon_id = aliases[job].get(action_id, action_id)
        return f"icons/talents/{job_dir}/{icon_id}.png"

    @staticmethod
    def potion_icon(kind: str | None = None) -> str:
        return f"icons/potions/{kind or 'universal'}.png"

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
        self.play_sound(self.skill_sound(legacy_effects[selected_job]), volume=.82)
        if secondary:
            self.sub_job_skill_cooldown = self.skill_cooldown_turns
        else:
            self.job_skill_cooldown = self.skill_cooldown_turns
        self.configure_buttons()

    # ---------- character creation ----------
    def open_settings(self) -> None:
        self.settings_return = self.scene
        self.scene = Scene.SETTINGS
        self.configure_buttons()

    def close_settings(self) -> None:
        self.scene = self.settings_return
        self.configure_buttons()

    # Language-neutral latin codes so the picker never renders as tofu boxes
    # regardless of which locale's font is currently active.
    LOCALE_LABELS = {
        "zh-TW": "TW", "zh-CN": "CN", "EN": "EN", "JA": "JA", "KO": "KO",
    }

    def locale_abbreviation(self, locale: str | None = None) -> str:
        """Return the compact label used by the title control's language picker."""
        locale = self.locale if locale is None else locale
        return self.LOCALE_LABELS.get(locale, locale)

    def toggle_language_menu(self) -> None:
        """Open or close the expandable locale picker on the title screen."""
        if self.scene != Scene.TITLE:
            self.language_menu_open = False
            return
        self.language_menu_open = not self.language_menu_open
        self.configure_buttons()

    def close_language_menu(self) -> None:
        if not self.language_menu_open:
            return
        self.language_menu_open = False
        self.configure_buttons()

    def select_locale(self, locale: str) -> None:
        """Select one supported locale, refresh the UI, and persist it."""
        if locale not in SUPPORTED_LOCALES:
            return
        set_locale(locale)
        self.locale = get_locale()
        self.language_menu_open = False
        self._text_cache.clear()
        self._measure_cache.clear()
        # Floating-damage labels are persistent Arcade Text objects whose font
        # stack is fixed when they are created.  Drop the pre-warmed pool so
        # the next combat value is rebuilt with the newly selected locale.
        self._floating_label_pool.clear()
        self.save_job_progress()
        self.configure_buttons()

    def toggle_locale(self) -> None:
        """Compatibility helper that advances directly to the next locale."""
        locales = tuple(SUPPORTED_LOCALES)
        if not locales:
            return
        try:
            current = locales.index(self.locale)
        except ValueError:
            current = -1
        self.select_locale(locales[(current + 1) % len(locales)])

    def cycle_ui_scale(self) -> None:
        options = (1.0, 1.1, 1.25)
        current = min(range(len(options)), key=lambda i: abs(options[i] - self.ui_scale))
        self.ui_scale = options[(current + 1) % len(options)]
        self._text_cache.clear()
        self._measure_cache.clear()
        self.configure_buttons()

    def toggle_high_contrast(self) -> None:
        self.high_contrast = not self.high_contrast
        self._text_cache.clear()
        self.configure_buttons()

    def toggle_reduce_motion(self) -> None:
        self.reduce_motion = not self.reduce_motion
        if self.reduce_motion:
            self.skill_effects.clear()
        self.configure_buttons()

    def start_creation(self) -> None:
        self.scene = Scene.CREATION
        self.creation_step = 0
        self.selected_sex = "男性"
        self.selected_race = "獸人"
        self.selected_job = "戰士"
        self.name_input = ""
        self.name_input_focused = True
        self.job_page = 0
        self.configure_buttons()

    def next_creation_step(self) -> None:
        if self.creation_step == 0 and not self.name_input.strip():
            return
        self.creation_step += 1
        self.configure_buttons()

    def add_name_text(self, text: str) -> None:
        self.name_input_focused = True
        self.name_caret_timer = 0.0
        if not text:
            return
        cleaned = "".join(character for character in text if character not in "\r\n\t")
        if not cleaned:
            return
        available = self.MAX_NAME_LENGTH - len(self.name_input)
        if available <= 0:
            return
        self.name_input += cleaned[:available]
        self.configure_buttons()

    def choose_sex(self, sex: str) -> None:
        self.selected_sex = sex
        self.name_input_focused = False
        self.creation_step = 3
        self.job_page = 0
        self.configure_buttons()

    def choose_race(self, race: str) -> None:
        self.selected_race = race
        self.creation_step = 2
        self.configure_buttons()

    def job_summary(self, job: str) -> str:
        return {
            "戰士": "血量高，能用護盾防守，也能強力反擊。",
            "法師": "用火焰攻擊、冰霜防守，還能改變怪物行動。",
            "聖騎士": "能加護盾、回血，也有保命技能。",
            "盜賊": "擅長暴擊、隱身和讓怪物停一回合。",
            "術士": "用持續傷害削弱怪物，並吸血恢復自己。",
        }[job]

    def job_creation_tooltip(self, job: str) -> str:
        bonus = dict(self.JOBS)[job]
        return (
            f"{job}｜{bonus}\n"
            f"專屬技能：{self.job_skill_name(job)}｜{self.job_skill_description(job)}"
        )

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
        self.reset_run_variation()
        self.pending_reward_gold = 0
        self.run_battles_won = 0
        self.run_enemies_defeated = 0
        self.run_damage_dealt = 0
        self.run_highest_hit = 0
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
        self.player = p
        self.skill_cooldown_turns = self.SKILL_COOLDOWN_TURNS
        self.reset_skills()
        self.clear_battle_state()
        self.after_subclass = "adventure"
        self.load_player_combat_portraits()
        self.enqueue_job_effect_warmups(p.job)
        self.messages = [f"開始旅程：{p.name}｜{p.race}{p.job}｜{self.level_label(p.lv)}"]
        self.log_scroll = 0
        self.journey_lore = self.random_journey_lore()
        self.open_start_gift_event()
        self.configure_buttons()

    def previous_creation_step(self) -> None:
        if self.scene != Scene.CREATION or self.creation_step <= 0:
            return
        self.creation_step -= 1
        self.name_input_focused = self.creation_step == 0
        self.configure_buttons()

    def toggle_battle_log(self) -> None:
        if self.scene != Scene.BATTLE:
            return
        self.battle_log_expanded = not self.battle_log_expanded
        self.log_scroll = 0
        self.configure_buttons()

    # ---------- journey ----------
    def open_start_gift_event(self) -> None:
        self.event_number = self.START_GIFT_EVENT_NUMBER
        self.event_title = "啟程贈禮"
        self.event_options = ("收下靈藥",)
        self.event_resolved = False
        self.event_kind = "start_gift"
        self.event_messages = []
        self.scene = Scene.EVENT
        self.log("城門藥師把一瓶月泉靈藥交到你手上。瓶中銀光像小小月泉，足以在危急時修補半身傷勢。")

    def continue_journey(self) -> None:
        self.confirm_route_selection()

    def should_open_campfire(self) -> bool:
        return 3 <= self.player.lv <= 19 and self.player.lv % 2 == 1

    def open_campfire(self) -> None:
        selector = CampfireOptionSelector(
            self.rng_for(
                "campfire", self.route_active_id or self.player.lv, self.difficulty
            )
        )
        categories = {
            "rest": "recovery",
            "attack": "growth", "defense": "growth", "luck": "growth",
            "gold": "resource",
        }
        self.campfire_options = selector.select(
            tuple(categories), 3, category_of=categories.__getitem__,
        )
        self.scene = Scene.CAMPFIRE
        self.play_sound("campfire", volume=.65)
        self.log("你在黑霧間找到一處營火，可以短暫整備。")
        self.configure_buttons()

    def finish_campfire(self) -> None:
        if self.route_active_id:
            self.complete_active_route_node()
            return
        self.scene = Scene.ADVENTURE
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
        # These are permanent bonuses. Keep them restrained now that enemies
        # use a fixed level curve instead of mirroring the player's stats.
        ability_rate = .05 if self.player.race == "人類" else .03
        if stat == "attack":
            amount = max(1, math.ceil(self.player.attack * ability_rate))
            self.player.attack += amount
            self.log(f"你磨利武器，攻擊 +{amount}。")
        elif stat == "defense":
            amount = max(1, math.ceil(self.player.defense * ability_rate))
            self.player.defense += amount
            self.log(f"你修補護具，防禦 +{amount}。")
        elif stat == "luck":
            before = self.natural_critical_chance()
            amount = 2 if self.player.race == "人類" else 1
            self.player.luck += amount
            gained = self.natural_critical_chance() - before
            self.log(f"你整理行囊與路線，暴擊 +{gained:.0f}%。")
        elif stat == "gold":
            multiplier = 2 if self.player.race == "矮人" else 1
            amount = max(1, self.player.lv * 60 * multiplier)
            self.player.gold += amount
            self.log(f"你在營火旁整理戰利品，金幣 +{amount}G。")
        self.finish_campfire()

    def continue_after_battle_reward(self) -> None:
        if self.route_active_id:
            self.complete_active_route_node()
            return
        self.scene = Scene.ADVENTURE
        self.configure_buttons()

    # ---------- potion merchant ----------
    def open_black_market(self) -> None:
        """Open the active shop node even when the player cannot buy anything."""
        if self.scene != Scene.ADVENTURE:
            return
        node_key = self.route_active_id or f"legacy-level-{self.player.lv}"
        if self.shop_inventory_node_id != node_key:
            has_affordable = any(
                self.potion_available(kind) for kind in self.POTIONS
            )
            selector = ShopInventorySelector(
                self.rng_for("shop", node_key, self.difficulty)
            )
            self.shop_inventory = selector.select(
                (node_key, self.difficulty), tuple(self.POTIONS), 6,
                is_healing=lambda kind: kind in {"heal", "full_heal"},
                is_affordable=(
                    self.potion_available if has_affordable else lambda _kind: True
                ),
            )
            self.shop_inventory_level = self.player.lv
            self.shop_inventory_node_id = node_key
        self.scene = Scene.SHOP
        self.shop_lore = self.rng_for(
            "shop-lore", self.player.lv, self.difficulty
        ).choice(self.SHOP_LORE)
        self.log("霧巷盡頭亮起紫色燈火，藥水商掀開了攤位的布簾。")
        self.configure_buttons()

    def leave_black_market(self) -> None:
        self.log("你收好藥瓶離開攤位，紫色燈火在身後慢慢熄滅。")
        node = self.route_node()
        if node is not None and node.kind is NodeKind.SHOP:
            self.complete_active_route_node()
            return
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
        if not self.shop_has_affordable_offer():
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
            return self.combat_rng.randint(1, 2)
        if 9 < lv < 15:
            return self.combat_rng.randint(2, 3)
        if 14 < lv < 20:
            return self.combat_rng.randint(3, 4)
        if lv == 20:
            return 5
        return 1

    @staticmethod
    def reference_player_stats(level: int) -> tuple[int, int, int]:
        """Return the level curve used to build enemies, independent of the player build."""
        level = max(1, min(21, int(level)))
        growth = level * (level + 1) // 2 - 1
        return 25 + growth * 2, 10 + growth, 15 + growth

    def build_enemy(self, rank: int, kind: str, dual: bool) -> Enemy:
        profile = self.DIFFICULTY_PROFILES[self.difficulty]
        type_mod = self.MONSTER_TYPE_MODIFIERS[kind]
        reference_hp, reference_attack, reference_defense = self.reference_player_stats(
            self.player.lv
        )
        target_turns = self.combat_rng.uniform(*profile["turns"])
        defense_ratio = self.combat_rng.uniform(*profile["defense"]) * type_mod["defense"]
        defense = max(0, math.ceil(reference_attack * defense_ratio))
        expected_player_damage = max(1, reference_attack)
        hp = max(1, math.ceil(expected_player_damage * target_turns * type_mod["hp"]))
        target_hits_to_defeat_player = self.combat_rng.uniform(*profile["danger_hits"])
        expected_enemy_damage = max(
            1,
            math.ceil((reference_hp / target_hits_to_defeat_player) * type_mod["damage"]),
        )
        attack = math.ceil(reference_defense * .70) + expected_enemy_damage
        if dual:
            attack = max(1, math.ceil(attack * self.DUAL_ENEMY_ATTACK_SCALE))
        monster_name = "魔王" if rank == 6 else self.MONSTER_NAMES[rank][kind]
        return Enemy(monster_name, kind, rank, self.player.lv, hp, hp, attack, defense)

    def start_battle(self, rank_override: int | None = None) -> None:
        self.prepare_battle_rng()
        rank = self.monster_rank() if rank_override is None else int(rank_override)
        self._ensure_battle_background(
            self.battle_background_stage(self.player.lv)
        )
        self._ensure_critical_effect()
        dual = self.difficulty >= 3 and rank != 6
        if dual:
            kinds = self.combat_rng.sample(("血量型", "攻擊型", "防禦型"), 2)
        else:
            kinds = [self.combat_rng.choice(("血量型", "攻擊型", "防禦型"))]
        self.enemies = [self.build_enemy(rank, kind, dual) for kind in kinds]
        active_node = self.route_node()
        is_elite = active_node is not None and active_node.kind is NodeKind.ELITE
        if is_elite:
            for enemy in self.enemies:
                enemy.max_hp = max(1, math.ceil(enemy.max_hp * 1.40))
                enemy.hp = enemy.max_hp
                enemy.attack = max(1, math.ceil(enemy.attack * 1.15))
                enemy.defense = max(0, math.ceil(enemy.defense * 1.20))
        self.battle_modifier = choose_battle_modifier(
            rng=self.combat_rng,
            is_first_battle=self.player.lv <= 1,
            is_boss=rank == 6 or is_elite,
        )
        for enemy in self.enemies:
            enemy.max_hp, enemy.attack, enemy.defense = modified_enemy_stats(
                self.battle_modifier,
                max_hp=enemy.max_hp,
                attack=enemy.attack,
                defense=enemy.defense,
            )
            enemy.hp = enemy.max_hp
        self.target_index = 0
        self.enemy_portraits = [self.monster_portrait(rank, e.kind) for e in self.enemies]
        self.enemy_portrait = self.enemy_portraits[0]
        self.enemy_attack_portraits = [
            self.monster_portrait(rank, e.kind, "attack") for e in self.enemies
        ]
        self.enemy_attack_portrait = self.enemy_attack_portraits[0]
        self.enemy_hurt_portraits = [
            self.monster_portrait(rank, e.kind, "hurt") for e in self.enemies
        ]
        self.enemy_hurt_portrait = self.enemy_hurt_portraits[0]
        self.enemy_block_portraits = [
            self.monster_portrait(rank, e.kind, "block") for e in self.enemies
        ]
        self.enemy_block_portrait = self.enemy_block_portraits[0]
        self.battle_action_points = 2 if dual else 1
        self.boss_split_done = False
        self.pending_reward_gold = 0
        self.scene = Scene.BATTLE
        self.clear_battle_state()
        if self.battle_modifier is BattleModifier.RAMPART:
            for enemy in self.enemies:
                enemy.block = opening_shield_for(
                    self.battle_modifier, enemy_defense=enemy.defense
                )
        self.combat_messages.clear()
        self.player_actions_left = self.battle_action_points
        self.clear_floating_damage_feedback()
        self.clear_battle_skill_effects()
        self.reset_battle_skill_uses()
        if self.player.campfire_shield_ready:
            shield = max(1, math.ceil(self.player.max_hp * .15))
            self.player_block += shield
            self.player.campfire_shield_ready = False
            self.log(f"餘燼體魄化作護盾，戰鬥開始時獲得 {shield} 點護盾。")
        self.reset_combat_feedback()
        self.play_sound("boss_roar" if rank == 6 else "battle_start",
                        volume=.88 if rank == 6 else .72)
        self.choose_enemy_intent()
        if self.battle_modifier is BattleModifier.RAMPART:
            self.log("戰局變體「堅壁」：敵人以護盾迎戰。")
        elif self.battle_modifier is BattleModifier.GREED:
            self.log("戰局變體「貪婪」：敵人攻擊提高 15%，擊敗後金幣加倍。")
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
        if self.FIRST_BATTLE_TUTORIAL_KEY not in self.tutorial_seen:
            self.tutorial_tip = f"{self.FIRST_BATTLE_TUTORIAL_KEY}:0"
        if self.scene == Scene.BATTLE:
            self.configure_buttons()

    @property
    def battle_busy(self) -> bool:
        return (self.attack_animation is not None or self.pending_turn is not None
                or bool(self.tutorial_tip))

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
            if enemy and enemy.rank >= 2:
                pool.extend(("heavy_blow", "lifedrain"))
            return tuple(pool)
        pool = ["attack", "defend"]
        one_star_unlocks = (
            (3, "dot"),
            (6, "curse"),
            (9, "stun"),
            (12, "immune"),
            (15, "reflect"),
            (18, "cleanse"),
        )
        pool.extend(intent for unlock_level, intent in one_star_unlocks
                    if level >= unlock_level)
        if level >= 21:
            pool.extend(("berserk", "bulwark"))
        if enemy and enemy.rank >= 2:
            pool.extend(("heavy_blow", "lifedrain"))
        return tuple(pool)

    def choose_enemy_intent(self) -> None:
        living = [enemy for enemy in self.enemies if enemy.hp > 0]
        selectable = [enemy for enemy in living if not enemy.heavy_blow_charged]
        if not selectable:
            return
        pools = [self.enemy_intent_pool(enemy) for enemy in selectable]
        streaks = [
            IntentStreak(enemy.nonhostile_streak, enemy.no_immediate_streak)
            for enemy in selectable
        ]
        if len(living) >= 2 and len(selectable) == len(living):
            choices = self.intent_selector.choose_group(pools, streaks)
        else:
            chosen: list[str] = []
            for pool, streak in zip(pools, streaks):
                choice = self.intent_selector.choose_one(pool, streak)
                streak.record(choice)
                chosen.append(choice)
            choices = tuple(chosen)
        for enemy, streak, choice in zip(selectable, streaks, choices):
            enemy.intent = choice
            enemy.nonhostile_streak = streak.non_hostile
            enemy.no_immediate_streak = streak.no_immediate

    def enemy_intent_label(self, enemy: Enemy | None = None) -> str:
        enemy = enemy or self.enemy
        if not enemy:
            return ""
        if enemy.skip_turns > 0:
            return "昏迷中，無法行動"
        if not enemy.intent:
            return ""
        attack_multiplier = enemy.weak_multiplier if enemy.weak_turns > 0 else 1.0
        dot_damage = max(1, math.ceil(enemy.attack * .33))
        strong_dot_damage = max(1, math.ceil(enemy.attack * .50))
        intent_effects = {
            "defend": f"+{max(1, enemy.defense)} 護盾",
            "attack": f"造成 {max(1, math.ceil(enemy.attack * attack_multiplier))} 傷害",
            "strong_attack": (
                f"造成 {max(1, math.ceil(enemy.attack * 1.5 * attack_multiplier))} 傷害"
            ),
            "heavy_blow": (
                f"蓄力後造成 {max(1, math.ceil(enemy.attack * 1.8 * attack_multiplier))} 傷害"
            ),
            "lifedrain": (
                f"造成 {max(1, math.ceil(enemy.attack * .9 * attack_multiplier))} 傷害並回復生命"
            ),
            "dot": f"每回合 {dot_damage} 傷害，持續 3 回合",
            "strong_dot": f"每回合 {strong_dot_damage} 傷害，持續 3 回合",
            "curse": "攻擊與防禦 -33%，持續 3 回合",
            "stun": "使你跳過下一次行動",
            "immune": "免疫下一次受到的傷害",
            "reflect": "1 回合內反彈 50% 傷害",
            "cleanse": "淨化負面狀態，否則轉為護盾",
            "berserk": f"攻擊 +{max(1, math.ceil(enemy.attack * .10))}",
            "bulwark": f"防禦 +{max(1, math.ceil(enemy.defense * .10))}",
        }
        skill_name = self.enemy_intent_skill_name(enemy)
        effect = intent_effects.get(enemy.intent, "")
        return f"{skill_name}｜{effect}" if skill_name and effect else skill_name

    def enemy_intent_value(self, enemy: Enemy | None = None) -> str:
        """Return the compact numeric value drawn beside an intent icon."""
        enemy = enemy or self.enemy
        if not enemy or enemy.skip_turns > 0:
            return ""
        attack_multiplier = enemy.weak_multiplier if enemy.weak_turns > 0 else 1.0
        values = {
            "attack": str(max(1, math.ceil(enemy.attack * attack_multiplier))),
            "strong_attack": str(max(1, math.ceil(
                enemy.attack * 1.5 * attack_multiplier
            ))),
            "heavy_blow": str(max(1, math.ceil(
                enemy.attack * 1.8 * attack_multiplier
            ))),
            "lifedrain": str(max(1, math.ceil(
                enemy.attack * .9 * attack_multiplier
            ))),
            "defend": str(max(1, enemy.defense)),
            "dot": f"{max(1, math.ceil(enemy.attack * .33))}X3",
            "strong_dot": f"{max(1, math.ceil(enemy.attack * .50))}X3",
            "berserk": f"+{max(1, math.ceil(enemy.attack * .10))}",
            "bulwark": f"+{max(1, math.ceil(enemy.defense * .10))}",
        }
        return values.get(enemy.intent, "")

    @staticmethod
    def enemy_intent_skill_name(enemy: Enemy) -> str:
        """Give every mechanical intent an in-world monster ability name."""
        if enemy.rank == 6:
            boss_skills = {
                "attack": "王座裁決",
                "strong_attack": "終焉斬決",
                "heavy_blow": "滅國重鎚",
                "lifedrain": "王血汲取",
                "dot": "終焉黑潮",
                "strong_dot": "深淵蝕界",
                "curse": "失落王印",
                "stun": "魔王敕令",
                "defend": "深淵王權",
                "immune": "不滅魔軀",
                "reflect": "逆命王鏡",
                "cleanse": "深淵洗禮",
                "berserk": "末日狂宴",
                "bulwark": "永夜城牆",
            }
            return boss_skills.get(enemy.intent, "未知王術")

        archetype_skills = {
            "血量型": {
                "attack": "巨獸撕咬",
                "strong_attack": "血肉碾壓",
                "heavy_blow": "巨軀蓄勢",
                "lifedrain": "噬血再生",
                "dot": "腐血瘴霧",
                "strong_dot": "疫血爆發",
                "curse": "衰亡凝視",
                "stun": "震魂咆哮",
                "defend": "血肉壁壘",
                "immune": "蛻皮再生",
                "reflect": "血棘反噬",
                "cleanse": "吞噬病灶",
                "berserk": "飢血沸騰",
                "bulwark": "骸骨增生",
            },
            "攻擊型": {
                "attack": "裂牙突襲",
                "strong_attack": "荒原獵殺",
                "heavy_blow": "獵殺蓄勢",
                "lifedrain": "裂喉汲血",
                "dot": "裂傷毒爪",
                "strong_dot": "蝕骨獵痕",
                "curse": "獵物烙印",
                "stun": "撼地撲殺",
                "defend": "鐵爪招架",
                "immune": "暗影疾行",
                "reflect": "逆刃獠牙",
                "cleanse": "野性甩脫",
                "berserk": "荒原狂獵",
                "bulwark": "鋼鬃護體",
            },
            "防禦型": {
                "attack": "碎岩角擊",
                "strong_attack": "山岳衝城",
                "heavy_blow": "崩城蓄勢",
                "lifedrain": "岩髓汲取",
                "dot": "灰燼孢塵",
                "strong_dot": "石疫風暴",
                "curse": "沉重威壓",
                "stun": "山崩震踏",
                "defend": "黑岩甲殼",
                "immune": "封閉甲殼",
                "reflect": "晶甲反震",
                "cleanse": "岩殼剝離",
                "berserk": "熔核升溫",
                "bulwark": "王城壁壘",
            },
        }
        return archetype_skills.get(enemy.kind, {}).get(enemy.intent, "未知獸技")

    @staticmethod
    def enemy_intent_style(intent: str) -> tuple[str, tuple[int, int, int], str]:
        """Return icon, colour and tactical category for an intent telegraph."""
        styles = {
            "attack": ("攻", (226, 78, 72), "攻擊"),
            "strong_attack": ("重", (255, 61, 61), "重擊"),
            "heavy_blow": ("蓄", (255, 92, 54), "蓄力重擊"),
            "lifedrain": ("汲", (205, 72, 126), "汲取生命"),
            "dot": ("蝕", (172, 96, 220), "持續傷害"),
            "strong_dot": ("毒", (205, 78, 223), "強效持續傷害"),
            "curse": ("咒", (161, 91, 211), "弱化"),
            "stun": ("暈", (238, 143, 61), "控制"),
            "defend": ("防", (75, 147, 218), "防禦"),
            "immune": ("免", (85, 188, 222), "免疫"),
            "reflect": ("返", (224, 174, 67), "反彈"),
            "cleanse": ("淨", (82, 189, 126), "淨化"),
            "berserk": ("狂", (236, 91, 52), "強化攻擊"),
            "bulwark": ("壁", (91, 135, 194), "強化防禦"),
        }
        return styles.get(intent, ("?", (169, 178, 191), "未知"))

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
        blocked_by = self.consume_enemy_attack_protection(target)
        if blocked_by:
            return 0, blocked_by
        blocked = min(target.block, raw_damage)
        target.block -= blocked
        if blocked > 0:
            self.log(f"{target.name}的護盾擋下 {blocked} 點傷害。")
        return raw_damage - blocked, "block" if blocked >= raw_damage else ""

    @staticmethod
    def consume_enemy_attack_protection(enemy: Enemy) -> str:
        """消耗怪物的一次攻擊迴避／免疫，並回傳阻擋來源。"""
        if enemy.stealth_turns > 0:
            enemy.stealth_turns -= 1
            return "stealth"
        if enemy.immune_turns > 0:
            enemy.immune_turns -= 1
            return "immune"
        return ""

    def consume_player_attack_protection(self) -> str:
        """消耗玩家的一次攻擊迴避／免疫，適用直接攻擊與 DOT。"""
        if self.player_attack_immunity_turns > 0:
            self.player_attack_immunity_turns -= 1
            return "immunity"
        if self.mage_ice_barrier_turns > 0:
            self.mage_ice_barrier_turns -= 1
            return "ice_barrier"
        if self.stealth_turns > 0:
            self.stealth_turns -= 1
            return "stealth"
        return ""

    def log_player_attack_block(self, blocked_by: str, source: str = "這次攻擊") -> None:
        messages = {
            "immunity": f"神聖庇護擋下了{source}。",
            "ice_barrier": f"寒冰屏障擋下了{source}。",
            "stealth": f"敵人無法鎖定你的身影，{source}失效。",
        }
        if blocked_by:
            self.log(messages[blocked_by])

    def log_enemy_attack_block(self, enemy: Enemy, blocked_by: str,
                               source: str = "這次攻擊") -> None:
        if blocked_by == "stealth":
            self.log(f"{enemy.name}處於隱身，{source}無法命中。")
        elif blocked_by == "immune":
            self.log(f"{enemy.name}的黑霧外殼免疫了{source}。")

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
            enemy.agony_grace_turns = 0
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
        critical, forced_critical = self.roll_player_critical()
        if self.forced_critical:
            self.forced_critical = False
            self.log("星眼看穿破綻，這一擊必定暴擊。")
        if critical:
            raw_damage = max(1, math.ceil(
                attack_power * self.player_critical_damage_multiplier()
            ))
        else:
            raw_damage = max(1, math.ceil(attack_power))
        damage, blocked_by = self.resolve_player_hit_damage(raw_damage)
        self.attack_animation = AttackAnimation("player", damage, critical,
                                                enemy_index=self.target_index,
                                                blocked_by=blocked_by,
                                                forced_critical=forced_critical)
        self.prepare_attack_feedback(self.attack_animation)
        self.play_sound("sword_swing", volume=.78)
        self.configure_buttons()

    def class_attack_skill(self, skill_id: str, multiplier: float,
                           cooldown: int = 0, suppress_next_attack: bool = False,
                           once: bool = False) -> None:
        if not self.enemy or self.battle_busy or not self.class_action_ready(skill_id):
            return
        self.spend_skill_action(skill_id)
        if self.enemy_stealth_turns > 0:
            self.enemy_stealth_turns -= 1
            self.attack_animation = AttackAnimation(
                "player", 0, False, enemy_index=self.target_index,
                blocked_by="stealth", action_id=skill_id,
            )
            self.prepare_attack_feedback(self.attack_animation)
            self.configure_buttons()
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
        critical, forced_critical = self.roll_player_critical()
        if self.forced_critical:
            self.forced_critical = False
            self.log("星眼看穿破綻，這一擊必定暴擊。")
        critical_multiplier = self.player_critical_damage_multiplier() if critical else 1
        raw_damage = max(1, math.ceil(attack_power * critical_multiplier))
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
                                                blocked_by=blocked_by,
                                                forced_critical=forced_critical)
        self.prepare_attack_feedback(self.attack_animation)
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
            self.play_sound(self.skill_sound(action_id), volume=.82)

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
        self.play_sound("shield", volume=.72)
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
        elif kind == "cleanse_curse":
            self.clear_player_curse()
            self.log(f"你喝下{spec['name']}，身上的衰敗詛咒被解除。")
        elif kind == "stun_ward":
            self.player_stun_turns = 0
            self.player_stun_immunity_turns = 1
            self.log(f"你喝下{spec['name']}，精神清醒，可擋下一次昏迷。")
        elif kind == "dispel_immunity":
            if self.enemy:
                self.enemy.immune_turns = 0
            self.log(f"你喝下{spec['name']}，敵人的黑霧免疫外殼碎裂了。")
        elif kind == "heal":
            restored = self.heal_player(max(1, math.ceil(self.player.max_hp * .50)))
            self.add_floating_damage("player", restored, False, healing=True)
            self.log(f"你喝下{spec['name']}，恢復 {restored} 點血量。")
        elif kind == "full_heal":
            restored = self.heal_player(self.player.max_hp)
            self.add_floating_damage("player", restored, False, healing=True)
            self.log(f"你喝下{spec['name']}，傷勢在暖流中完全復原。")
        self.play_sound("heal" if kind in ("heal", "full_heal") else "potion",
                        volume=.74)
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
            if actor.heavy_blow_charged:
                actor.heavy_blow_charged = False
                actor.intent = ""
                self.log(f"{actor.name}的蓄力被打斷。")
            self.log(f"{actor.name}陷入昏迷，這回合無法行動。")
            self.finish_enemy_action()
            return
        action = actor.intent or "attack"
        releasing_heavy = action == "heavy_blow" and actor.heavy_blow_charged
        if action in self.HOSTILE_ENEMY_INTENTS and (
                action != "heavy_blow" or releasing_heavy):
            blocked_by = self.consume_player_attack_protection()
        else:
            blocked_by = ""
        if blocked_by:
            if releasing_heavy:
                actor.heavy_blow_charged = False
            self.attack_animation = AttackAnimation(
                "enemy", 0, False, enemy_index=index,
                blocked_by=blocked_by, action_id=action,
            )
            self.prepare_attack_feedback(self.attack_animation)
            self.configure_buttons()
            return
        if (self.mage_meteor_suppression > 0
                and action in ("attack", "strong_attack", "heavy_blow", "lifedrain",
                               "dot", "strong_dot", "curse", "stun")):
            self.mage_meteor_suppression -= 1
            actor.heavy_blow_charged = False
            self.log("隕石風暴壓制了敵方攻擊意圖。")
            self.finish_enemy_action()
            return
        if action == "heavy_blow" and not releasing_heavy:
            actor.heavy_blow_charged = True
            self.log(f"{actor.name}開始蓄力，下一次行動將施放重擊。")
            self.play_sound("boss_roar", volume=.48)
            self.finish_enemy_action()
            return
        if action == "defend":
            block = max(1, actor.defense)
            actor.block += block
            self.log(f"{actor.name}縮起身形，獲得 {block} 點護盾。")
            self.finish_enemy_action()
            return
        if action in ("dot", "strong_dot"):
            dot_was_active = self.player_dot_damage > 0 and self.player_dot_turns > 0
            multiplier = .50 if action == "strong_dot" else .33
            dot = max(1, math.ceil(actor.attack * multiplier))
            self.apply_player_dot_status(actor.name, dot, "黑霧")
            self.finish_enemy_action(apply_player_dot=dot_was_active)
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

        if action == "heavy_blow":
            multiplier = 1.8
            actor.heavy_blow_charged = False
        elif action == "lifedrain":
            multiplier = .9
        else:
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
        if action in ("strong_attack", "heavy_blow"):
            self.log(f"{actor.name}蓄力重擊，攻勢翻倍。")
        self.attack_animation = AttackAnimation("enemy", damage, critical,
                                                enemy_index=index,
                                                action_id=action)
        self.prepare_attack_feedback(self.attack_animation)
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
        blocked_by = self.consume_player_attack_protection()
        if blocked_by:
            self.log_player_attack_block(blocked_by, "這次持續傷害")
            self.player_dot_turns -= 1
            if self.player_dot_turns <= 0:
                self.clear_player_dot()
                self.log("纏身的黑霧散去了。")
            return False
        damage = self.player_dot_damage * max(1, self.player_dot_stacks)
        self.player.hp -= damage
        self.add_floating_damage("player", damage, False)
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
                              turns: int, *, bypass_protection: bool = False) -> bool:
        if not enemy or damage < 1 or turns < 1:
            return False
        if not bypass_protection:
            blocked_by = self.consume_enemy_attack_protection(enemy)
            if blocked_by:
                self.log_enemy_attack_block(enemy, blocked_by, "腐蝕")
                return False
        enemy.corrosion_damage = max(enemy.corrosion_damage, damage)
        enemy.corrosion_turns = max(enemy.corrosion_turns, turns)
        self.log(f"{enemy.name}被腐蝕纏上，每回合受 {enemy.corrosion_damage} 傷害。")
        return True

    def apply_enemy_agony(self, enemy: Enemy | None, damage: int,
                          turns: int, *, bypass_protection: bool = False) -> bool:
        if not enemy or damage < 1 or turns < 1:
            return False
        if not bypass_protection:
            blocked_by = self.consume_enemy_attack_protection(enemy)
            if blocked_by:
                self.log_enemy_attack_block(enemy, blocked_by, "痛苦詛咒")
                return False
        enemy.agony_damage = max(enemy.agony_damage, damage)
        agony_active = enemy.agony_turns > 0 or enemy.agony_grace_turns > 0
        enemy.agony_stacks = min(3, enemy.agony_stacks + 1 if agony_active else 1)
        enemy.agony_turns = max(enemy.agony_turns, turns)
        enemy.agony_grace_turns = 0
        total = enemy.agony_damage * enemy.agony_stacks
        self.log(
            f"{enemy.name}被痛苦詛咒折磨，每回合受 {total} 傷害"
            f"（{enemy.agony_stacks} 層）。"
        )
        return True

    def trigger_enemy_dot_now(self, enemy: Enemy | None, kind: str) -> bool:
        """把指定術士 DOT 的第一跳移到施加當下，總跳數維持不變。"""
        if not enemy or enemy.hp < 1 or enemy not in self.enemies:
            return False
        if kind == "corrosion":
            damage = enemy.corrosion_damage
            if damage < 1 or enemy.corrosion_turns < 1:
                return False
            enemy.corrosion_turns -= 1
            if enemy.corrosion_turns <= 0:
                enemy.corrosion_damage = 0
            label = "腐蝕"
        elif kind == "agony":
            damage = enemy.agony_damage * enemy.agony_stacks
            if damage < 1 or enemy.agony_turns < 1:
                return False
            enemy.agony_turns -= 1
            if enemy.agony_turns <= 0:
                enemy.agony_grace_turns = 1
            label = "痛苦"
        else:
            return False
        index = self.enemies.index(enemy)
        enemy.hp -= damage
        self.add_floating_damage(
            "enemy", damage, False, target_index=index,
        )
        self.log(f"{enemy.name}立刻受到{label}傷害 {damage} 點。")
        if self.player.job == "術士":
            rank = self.class_talent_rank("soul_link")
            if rank > 0:
                rate = .30 if rank >= 2 else .20
                restored = self.heal_player(max(1, math.ceil(damage * rate)))
                self.show_player_heal(restored)
        if enemy.hp < 1 and self.attack_animation is None:
            self.handle_enemy_defeat(enemy)
            return True
        return False

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
                         turns: int, *, bypass_protection: bool = False) -> bool:
        if not enemy or damage < 1 or turns < 1:
            return False
        if not bypass_protection:
            blocked_by = self.consume_enemy_attack_protection(enemy)
            if blocked_by:
                self.log_enemy_attack_block(enemy, blocked_by, "末日印記")
                return False
        enemy.doom_damage = max(enemy.doom_damage, damage)
        enemy.doom_turns = max(enemy.doom_turns, turns)
        self.log(f"{enemy.name}被末日印記鎖定，{enemy.doom_turns} 回合後爆發 {enemy.doom_damage} 傷害。")
        return True

    def weaken_enemy_attack(self, enemy: Enemy | None, reduction: float) -> bool:
        if not enemy:
            return False
        blocked_by = self.consume_enemy_attack_protection(enemy)
        if blocked_by:
            self.log_enemy_attack_block(enemy, blocked_by, "衰弱咒印")
            return False
        enemy.weak_turns = max(enemy.weak_turns, 1)
        enemy.weak_multiplier = min(enemy.weak_multiplier, max(0.1, 1.0 - reduction))
        self.log(f"{enemy.name}被衰弱咒印壓制，下一次攻擊傷害降低 {int(reduction * 100)}%。")
        return True

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
                    enemy.agony_grace_turns = 1
            elif enemy.agony_grace_turns > 0:
                enemy.agony_grace_turns -= 1
                if enemy.agony_grace_turns <= 0:
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
            blocked_by = self.consume_enemy_attack_protection(enemy)
            if blocked_by:
                self.log_enemy_attack_block(enemy, blocked_by, "這次持續傷害")
                continue
            enemy.hp -= total
            self.add_floating_damage(
                "enemy", total, False, target_index=index,
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
            self.add_floating_damage("player", restored, False, healing=True)
            self.log(f"血祭的鮮血回流，恢復 {restored} 點血量。")
        if self.warrior_blood_regen_turns <= 0:
            self.warrior_blood_regen = 0

    def finish_enemy_action(self, apply_player_dot: bool = True) -> None:
        """單隻怪物行動結束：還有怪物就換下一隻，否則結束整個敵方回合。"""
        if not apply_player_dot:
            self.enemy_turn_skip_player_dot = True
        if self.scene == Scene.BATTLE and self.enemy_turn_order:
            self.queue_turn("enemy", .45)
            return
        skip_player_dot = self.enemy_turn_skip_player_dot
        self.enemy_turn_skip_player_dot = False
        self.end_enemy_turn(not skip_player_dot)

    def end_enemy_turn(self, apply_player_dot: bool = True) -> None:
        if apply_player_dot and self.apply_player_dot():
            return
        if self.apply_enemy_dots():
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
            self.trigger_combat_impact("enemy", target_index, animation.critical)
            if animation.damage > 0:
                self.play_sound("critical" if animation.critical else "sword_hit",
                                volume=.9)
            else:
                self.play_sound("dodge" if animation.blocked_by == "stealth"
                                else "shield_block", volume=.76)
            if animation.damage > 0:
                self.run_damage_dealt += animation.damage
                self.run_highest_hit = max(self.run_highest_hit, animation.damage)
            prefix = "暴擊！" if animation.critical else ""
            if animation.damage > 0:
                self.log(f"{prefix}你對 {target.name} 造成 {animation.damage} 點傷害。")
            else:
                if animation.blocked_by == "immune":
                    self.log(f"{target.name}的黑霧外殼免疫了這次傷害。")
                elif animation.blocked_by == "stealth":
                    self.log(f"{target.name}處於隱身，這次攻擊落空。")
                else:
                    self.log(f"{target.name}用護盾擋下了這次攻擊。")
            self.publish_attack_feedback(animation)
            if animation.damage > 0 and target.reflect_turns > 0:
                reflected = max(1, math.ceil(animation.damage * .50))
                blocked_by = self.consume_player_attack_protection()
                if blocked_by:
                    self.log_player_attack_block(blocked_by, "這次反彈傷害")
                else:
                    self.player.hp -= reflected
                    self.add_floating_damage("player", reflected, False)
                    self.log(f"{target.name}的反射咒壁回彈 {reflected} 點傷害。")
                    if self.player.hp < 1:
                        self.trigger_mage_mana_shield()
        elif animation.attacker == "enemy" and self.enemies:
            actor_index = min(animation.enemy_index, len(self.enemies) - 1)
            actor = self.enemies[actor_index]
            self.player.hp -= animation.damage
            self.trigger_combat_impact("player", actor_index, animation.critical)
            self.play_sound("hurt" if animation.damage > 0 else "shield_block",
                            volume=.9 if animation.damage > 0 else .76)
            prefix = "暴擊！" if animation.critical else ""
            if animation.damage > 0:
                self.log(f"{prefix}{actor.name} 對你造成 {animation.damage} 點傷害。")
                if animation.action_id == "lifedrain":
                    restored = min(
                        max(0, actor.max_hp - actor.hp),
                        max(1, math.ceil(animation.damage * .40)),
                    )
                    if restored > 0:
                        actor.hp += restored
                        self.add_floating_damage(
                            "enemy", restored, False, healing=True,
                            target_index=actor_index,
                        )
                        self.log(f"{actor.name}汲取生命，回復 {restored} 點生命。")
            else:
                if animation.blocked_by:
                    self.log_player_attack_block(
                        animation.blocked_by, "這次敵方行動"
                    )
                else:
                    self.log("你的護盾完全擋下了這次攻擊。")
            self.publish_attack_feedback(animation)
            if self.player.hp < 1:
                self.trigger_mage_mana_shield()

    def finish_attack_animation(self) -> None:
        animation = self.attack_animation
        self.attack_animation = None
        if animation and animation.floating is not None:
            self.release_floating_damage_label(animation.floating)
            animation.floating = None
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
        clone_attack_portrait = (
            self.enemy_attack_portraits[0] if self.enemy_attack_portraits
            else self.monster_portrait(6, boss.kind, "attack")
        )
        self.enemy_attack_portraits = [clone_attack_portrait, clone_attack_portrait]
        clone_hurt_portrait = (
            self.enemy_hurt_portraits[0] if self.enemy_hurt_portraits
            else self.monster_portrait(6, boss.kind, "hurt")
        )
        self.enemy_hurt_portraits = [clone_hurt_portrait, clone_hurt_portrait]
        clone_block_portrait = (
            self.enemy_block_portraits[0] if self.enemy_block_portraits
            else self.monster_portrait(6, boss.kind, "block")
        )
        self.enemy_block_portraits = [clone_block_portrait, clone_block_portrait]
        self.enemy_portrait = clone_portrait
        self.enemy_attack_portrait = clone_attack_portrait
        self.enemy_hurt_portrait = clone_hurt_portrait
        self.enemy_block_portrait = clone_block_portrait
        self.enemy_turn_order = []
        self.battle_action_points = 2
        self.choose_enemy_intent()
        self.log("魔王倒下的瞬間裂成兩道身影，各自持有本體四成的力量！")
        self.log("擊敗兩隻分身才能真正通關。點擊怪物可切換攻擊目標。")
        self.configure_buttons()

    def spread_warlock_dots(self, source: Enemy, remaining: list[Enemy]) -> None:
        """三星雙怪中，術士目標死亡時把腐蝕與痛苦半效傳給存活目標。"""
        if self.difficulty < 3 or self.player.job != "術士":
            return
        target = next((enemy for enemy in remaining if enemy.hp > 0), None)
        if not target:
            return
        has_corrosion = source.corrosion_turns > 0 and source.corrosion_damage > 0
        has_agony = (
            source.agony_turns > 0 and source.agony_damage > 0
            and source.agony_stacks > 0
        )
        if not has_corrosion and not has_agony:
            return
        blocked_by = self.consume_enemy_attack_protection(target)
        if blocked_by:
            self.log_enemy_attack_block(target, blocked_by, "蔓延的詛咒")
            return
        effects: list[str] = []
        if has_corrosion:
            target.corrosion_damage = max(
                target.corrosion_damage, max(1, math.ceil(source.corrosion_damage * .50))
            )
            target.corrosion_turns = max(target.corrosion_turns, source.corrosion_turns)
            effects.append("腐蝕")
        if has_agony:
            target.agony_damage = max(
                target.agony_damage, max(1, math.ceil(source.agony_damage * .50))
            )
            target.agony_stacks = max(target.agony_stacks, source.agony_stacks)
            target.agony_turns = max(target.agony_turns, source.agony_turns)
            target.agony_grace_turns = 0
            effects.append("痛苦")
        self.log(f"{source.name}倒下時，半效的{'、'.join(effects)}蔓延到{target.name}。")

    def enemy_gold_reward(self, enemy: Enemy) -> int:
        gold_multipliers = {1: .5, 2: 1, 3: 1.5, 4: 2, 5: 2.5}
        base = int(self.player.lv * 50 * gold_multipliers.get(enemy.rank, 1))
        node = self.route_node()
        elite_multiplier = (
            1.5 if node is not None and node.kind is NodeKind.ELITE else 1.0
        )
        return int(
            base * elite_multiplier * reward_multiplier_for(self.battle_modifier)
        )

    def handle_enemy_defeat(self, target: Enemy) -> None:
        """目標倒下：還有其他怪物就結算獎勵並換目標，否則直接獲勝。"""
        if (target.rank == 6 and self.difficulty >= self.MAX_DIFFICULTY
                and not self.boss_split_done):
            self.split_boss(target)
            return
        self.run_enemies_defeated += 1
        remaining = [enemy for enemy in self.enemies if enemy is not target]
        if not remaining:
            self.win_battle()
            return
        self.spread_warlock_dots(target, remaining)
        gained_gold = self.enemy_gold_reward(target)
        self.player.gold += gained_gold
        self.pending_reward_gold += gained_gold
        if any(enemy.hp > 0 for enemy in remaining):
            self.log(f"{target.name}倒下，你搜出 {gained_gold}G。另一隻怪物仍在逼近！")
        else:
            self.log(f"{target.name}倒下，你搜出 {gained_gold}G。另一隻怪物也已倒下。")
        index = self.enemies.index(target)
        self.enemies.pop(index)
        if index < len(self.enemy_portraits):
            self.enemy_portraits.pop(index)
        if index < len(self.enemy_attack_portraits):
            self.enemy_attack_portraits.pop(index)
        if index < len(self.enemy_hurt_portraits):
            self.enemy_hurt_portraits.pop(index)
        if index < len(self.enemy_block_portraits):
            self.enemy_block_portraits.pop(index)
        if self.enemy_portraits:
            self.enemy_portrait = self.enemy_portraits[0]
        if self.enemy_attack_portraits:
            self.enemy_attack_portrait = self.enemy_attack_portraits[0]
        if self.enemy_hurt_portraits:
            self.enemy_hurt_portrait = self.enemy_hurt_portraits[0]
        if self.enemy_block_portraits:
            self.enemy_block_portrait = self.enemy_block_portraits[0]
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
            self.run_battles_won += 1
            self.log(f"{self.enemy.name}倒下了，{self.player.name}讓王城重新看見黎明！")
            if (self.route_active_id
                    and self.route_active_id not in self.route_completed_ids):
                self.route_completed_ids.append(self.route_active_id)
            self.route_active_id = None
            self.route_selected_id = None
            self.finish(True)
            return
        gained_gold = self.enemy_gold_reward(self.enemy)
        self.player.gold += gained_gold
        self.pending_reward_gold += gained_gold
        self.run_battles_won += 1
        self.log(f"{self.enemy.name}倒下，你搜出 {gained_gold}G。")
        self.complete_battle(level_up=True)

    def complete_battle(self, level_up: bool = False) -> None:
        """收束戰鬥，前往下一個旅途場景。"""
        self.enemy = None
        self.clear_battle_state()
        self.battle_modifier = None
        self.clear_battle_skill_effects()
        self.reset_battle_skill_uses()
        self.reward_level_before = self.player.lv
        self.after_subclass = "reward"
        opened_subclass = self.check_level_up(from_battle=level_up)
        self.reward_level_after = self.player.lv
        if opened_subclass:
            self.configure_buttons()
            return
        self.open_reward_summary()

    def open_reward_summary(self) -> None:
        node = self.route_node()
        if node is not None and node.kind is NodeKind.ELITE:
            if not self.elite_reward_choices:
                rng = self.rng_for("elite-reward", node.id)
                self.elite_reward_choices = tuple(
                    rng.sample(tuple(self.POTIONS), min(3, len(self.POTIONS)))
                )
                self.elite_reward_claimed = False
        else:
            self.elite_reward_choices = ()
            self.elite_reward_claimed = True
        self.scene = Scene.REWARD
        self.play_sound("reward_open", volume=.74)
        self.configure_buttons()

    def choose_elite_reward(self, kind: str) -> None:
        if (self.scene != Scene.REWARD or self.elite_reward_claimed
                or kind not in self.elite_reward_choices):
            return
        self.player.potion_bag[kind] = self.potion_count(kind) + 1
        self.elite_reward_claimed = True
        self.log(f"菁英戰利品：獲得{self.POTIONS[kind]['name']} ×1。")
        self.play_sound("reward_open", volume=.68)
        self.configure_buttons()

    def continue_after_reward(self) -> None:
        if self.elite_reward_choices and not self.elite_reward_claimed:
            return
        self.continue_after_battle_reward()

    def check_level_up(self, from_battle: bool = False) -> bool:
        """結算冒險者的成長。"""
        p = self.player
        if not from_battle or p.lv >= 21:
            return False
        old_gear_tier = player_gear_tier(p.lv)
        p.lv += 1
        hp_gain = p.lv * (3 if p.job == "戰士" else 2)
        attack_gain = math.floor(p.lv * 1.35 + .5) if p.job == "法師" else p.lv
        defense_gain = math.floor(p.lv * 1.35 + .5) if p.job == "聖騎士" else p.lv
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
            self.load_player_combat_portraits()
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
        self.enqueue_job_effect_warmups(job)
        self.log(f"{self.player.name}選擇了副職業 {job}，學會「{self.job_skill_name(job)}」。")
        destination = self.after_subclass
        self.after_subclass = "adventure"
        if destination == "post_battle":
            self.continue_after_battle_reward()
        elif destination == "reward":
            self.open_reward_summary()
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
        if stat == "hp":
            return max(1, math.ceil(p.lv * 4 * multiplier))
        if stat in ("attack", "defense"):
            return max(1, math.ceil(p.lv * .5 * multiplier))
        if stat == "gold":
            return max(10, math.ceil(p.lv * 60 * multiplier))
        if stat == "luck":
            return random.randint(1, 2)
        if stat == "potion":
            return 1
        raise ValueError(f"Unknown event stat: {stat}")

    def apply_event_stat_change(self, stat: str, direction: int, amount: int) -> int | float:
        p = self.player
        if stat == "max_hp":
            if direction > 0:
                p.max_hp += amount
                actual = amount
            else:
                old_value = p.max_hp
                # An event may shrink the cap, but never below current HP. This
                # avoids indirectly damaging or killing the player via max HP.
                p.max_hp = max(p.hp, p.max_hp - amount)
                actual = old_value - p.max_hp
            self.track_player_hp()
            return actual

        if stat == "hp":
            old_value = p.hp
            if direction > 0:
                # The maximum-HP event is resolved first. Only grant and report
                # the remaining space under that final cap (for example, a
                # rolled +5 becomes an actual +1 when only 1 HP is missing).
                available_hp = max(0, p.max_hp - p.hp)
                self.heal_player(min(amount, available_hp))
            else:
                # Wilderness events cannot kill the player directly.
                p.hp = max(1, p.hp - amount)
                self.track_player_hp()
            return abs(p.hp - old_value)

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
            old_chance = self.natural_critical_chance()
            if direction > 0:
                p.luck += amount
            else:
                if p.luck <= 0:
                    return 0.0
                new_luck = max(0, p.luck - amount)
                while new_luck > 0 and self.critical_chance_for_luck(new_luck) == old_chance:
                    new_luck -= 1
                p.luck = new_luck
            return round(abs(self.natural_critical_chance() - old_chance), 1)

        if stat == "potion":
            if direction > 0:
                kind = random.choice(tuple(self.POTIONS))
                p.potion_bag[kind] = self.potion_count(kind) + amount
                return amount
            owned = self.owned_potions()
            if not owned:
                return 0
            kind = random.choice(owned)
            old_value = self.potion_count(kind)
            new_value = max(0, old_value - amount)
            if new_value:
                p.potion_bag[kind] = new_value
            else:
                p.potion_bag.pop(kind, None)
            return old_value - new_value

        raise ValueError(f"Unknown event stat: {stat}")

    def event_change_phrase(self, stat: str, direction: int, actual: int | float) -> str:
        sign = "+" if direction > 0 else "-"
        if stat == "max_hp":
            return f"血量上限 {sign}{actual}"
        if stat == "hp":
            return f"目前血量 {sign}{actual}"
        if stat == "attack":
            return f"攻擊 {sign}{actual}"
        if stat == "defense":
            return f"防禦 {sign}{actual}"
        if stat == "gold":
            return f"金幣 {sign}{actual}G"
        if stat == "luck":
            return f"暴擊 {sign}{float(actual):.0f}%"
        if stat == "potion":
            if direction < 0 and actual == 0:
                return ""
            return f"藥水 {sign}{actual}"
        raise ValueError(f"Unknown event stat: {stat}")

    def apply_random_event_changes(self, option_index: int) -> str:
        """七種事件資源各擲一次增減，並依多數方向敘述結果。"""
        # Resolve the HP cap before current HP, regardless of future changes to
        # EVENT_STAT_KEYS. All current-HP clamping therefore uses the final cap.
        hp_priority = {"max_hp": 0, "hp": 1}
        stats = sorted(
            self.EVENT_STAT_KEYS,
            key=lambda stat: hp_priority.get(stat, 2),
        )
        stat_count = len(stats)
        phrases: list[str] = []
        positive_count = 0
        negative_count = 0

        for stat in stats:
            positive_chance = .60 if self.player.race == "精靈" else .50
            direction = 1 if random.random() < positive_chance else -1
            amount = self.event_stat_amount(stat, stat_count)
            actual = self.apply_event_stat_change(stat, direction, amount)

            # Potions keep their own ownership rule: an empty bag may still count
            # as a negative result without displaying a fake -0. All other stats
            # must produce a real change, so reverse a capped direction once.
            if stat != "potion" and actual < 1:
                direction *= -1
                actual = self.apply_event_stat_change(stat, direction, amount)

            if direction > 0:
                positive_count += 1
            else:
                negative_count += 1
            phrase = self.event_change_phrase(stat, direction, actual)
            if phrase:
                phrases.append(phrase)

        event = self.EVENT_DECK[self.event_number - 1]
        result_key = "positive" if positive_count > negative_count else "negative"
        result_descriptions = event[result_key]
        self.log(str(result_descriptions[option_index]))
        self.log("、".join(phrases) + "。")
        return result_key

    def event_background_number(self, event_number: int) -> int:
        if event_number == self.START_GIFT_EVENT_NUMBER:
            return 13
        if 1 <= event_number <= len(self.EVENT_DECK):
            return int(self.EVENT_DECK[event_number - 1]["background"])
        return ((event_number - 1) % 20) + 1

    def resolve_event(self) -> None:
        picker = RecentEventPicker(
            self.rng_for("event", self.player.lv, self.difficulty),
            recent_window=3,
        )
        picker.restore_recent(self.recent_event_numbers)
        event_number = picker.pick(tuple(range(1, len(self.EVENT_DECK) + 1)))
        self.recent_event_numbers = list(picker.recent)
        event = self.EVENT_DECK[event_number - 1]

        self.event_number = event_number
        self.event_title = str(event["title"])
        self.event_options = event["options"]
        self.event_resolved = False
        self.event_kind = "random"
        self.event_messages = []
        self.scene = Scene.EVENT
        self.log(str(event["intro"]))
        # Keep the scene transition self-contained so event choices never
        # inherit buttons from the previous screen.
        self.configure_buttons()

    def choose_event_option(self, option_index: int) -> None:
        if self.event_resolved:
            return
        option_index = max(0, min(len(self.event_options) - 1, option_index))
        choice = self.event_options[option_index]
        self.event_resolved = True
        self.log(f"你選擇「{choice}」。", record=False)
        if self.event_kind == "start_gift":
            self.player.potion_bag["heal"] = self.potion_count("heal") + 1
            self.log("你把月泉靈藥收入藥袋。戰鬥中可從藥水列喝下，立即恢復 50% 血量。")
            self.begin_route_at_start()
            return
        self.apply_random_event_changes(option_index)
        self.configure_buttons()

    def leave_event(self) -> None:
        self.after_subclass = "adventure"
        if self.check_level_up():
            return
        self.scene = Scene.ADVENTURE
        self.configure_buttons()

    def finish(self, victory: bool) -> None:
        self.victory = victory
        self.end_record_open = False
        self.scene = Scene.END
        if victory and self.enemy:
            self.final_enemy_name = self.enemy.name
        self.enemy = None
        self.clear_battle_state()
        self.clear_battle_skill_effects()
        if victory:
            self.record_job_clear()
            self.play_sound("victory", volume=.9, vary=False)
        else:
            self.player.hp = 0
            self.log("DEATH")
            self.play_sound("death", volume=.88, vary=False)
        self.configure_buttons()

    def replay(self) -> None:
        """Restart immediately with the same name, sex, race, and job."""
        self.name_input = self.player.name
        self.selected_sex = self.player.sex
        self.selected_race = self.player.race
        self.selected_job = self.player.job
        self.enemy = None
        self.final_enemy_name = ""
        self.victory = False
        self.end_record_open = False
        self.skill_cooldown_turns = self.SKILL_COOLDOWN_TURNS
        self.clear_battle_state()
        self.reset_skills()
        self.after_subclass = "adventure"
        self.clear_floating_damage_feedback()
        self.choose_difficulty(self.job_difficulty(self.selected_job))

    def request_return_home(self) -> None:
        """Open a mouse-only confirmation before abandoning the current journey."""
        self.home_confirmation = True
        self.hovered = None
        self.configure_buttons()

    def toggle_end_record(self) -> None:
        """Show or hide the current run summary on the ending screen."""
        if self.scene != Scene.END:
            return
        self.end_record_open = not self.end_record_open
        self.hovered = None
        self.configure_buttons()

    def cancel_return_home(self) -> None:
        self.home_confirmation = False
        self.hovered = None
        self.configure_buttons()

    def return_home(self) -> None:
        self.home_confirmation = False
        self.player = Player()
        self.load_player_combat_portraits()
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
        self.end_record_open = False
        self.skill_cooldown_turns = self.SKILL_COOLDOWN_TURNS
        self.clear_battle_state()
        self.clear_battle_skill_effects()
        self.clear_floating_damage_feedback()
        self.scene = Scene.TITLE
        self.configure_buttons()

    def close_game(self) -> None:
        self.close()

    # ---------- save / load ----------
    def save_slot_path(self, slot: int) -> Path:
        return self.SAVE_DIR / f"save_slot_{slot}.json"

    def validate_saved_player(self, raw_player: object) -> dict[str, object] | None:
        """驗證並過濾存檔角色資料，避免損壞欄位進入遊戲流程。"""
        if not isinstance(raw_player, dict):
            return None
        required_fields = {
            "name", "sex", "race", "job", "lv", "hp", "max_hp",
            "attack", "defense", "luck", "gold",
        }
        if not required_fields.issubset(raw_player):
            return None
        player_data = {
            key: value for key, value in raw_player.items()
            if key in Player.__dataclass_fields__
        }
        defaults = Player()
        valid_races = {race for race, _bonus in self.RACES}
        valid_jobs = {job for job, _bonus in self.JOBS}

        name = player_data.get("name", defaults.name)
        sex = player_data.get("sex", defaults.sex)
        race = player_data.get("race", defaults.race)
        job = player_data.get("job", defaults.job)
        sub_job = player_data.get("sub_job", defaults.sub_job)
        if not isinstance(name, str) or not name.strip() or len(name) > self.MAX_NAME_LENGTH:
            return None
        if sex not in ("男性", "女性") or race not in valid_races or job not in valid_jobs:
            return None
        if not isinstance(sub_job, str) or (sub_job and (sub_job not in valid_jobs or sub_job == job)):
            return None

        integer_limits = {
            "lv": (1, 21), "hp": (0, None), "max_hp": (1, None),
            "attack": (1, None), "defense": (0, None), "luck": (0, None),
            "gold": (0, None), "black_market_lv": (0, None),
            "potions": (0, None), "talent_points": (0, None),
        }
        for key, (minimum, maximum) in integer_limits.items():
            value = player_data.get(key, getattr(defaults, key))
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                return None
            if maximum is not None and value > maximum:
                return None
        if player_data.get("hp", defaults.hp) > player_data.get("max_hp", defaults.max_hp):
            return None

        shield_ready = player_data.get("campfire_shield_ready", defaults.campfire_shield_ready)
        if not isinstance(shield_ready, bool):
            return None
        for key in ("potion_bag", "potion_purchase_counts"):
            counts = player_data.get(key, getattr(defaults, key))
            if not isinstance(counts, dict):
                return None
            if any(
                not isinstance(kind, str) or isinstance(count, bool)
                or not isinstance(count, int) or count < 0
                for kind, count in counts.items()
            ):
                return None

        class_talents = player_data.get("class_talents", defaults.class_talents)
        if not isinstance(class_talents, dict):
            return None
        for talent_job, talents in class_talents.items():
            if not isinstance(talent_job, str) or not isinstance(talents, dict):
                return None
            if any(
                not isinstance(talent_id, str) or isinstance(rank, bool)
                or not isinstance(rank, int) or not 0 <= rank <= 3
                for talent_id, rank in talents.items()
            ):
                return None
        return player_data

    def read_save_slot(self, slot: int) -> dict | None:
        path = self.save_slot_path(slot)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict):
            return None
        player_data = self.validate_saved_player(data.get("player"))
        if player_data is None:
            return None
        try:
            difficulty = int(data.get("difficulty", 1))
        except (TypeError, ValueError):
            return None
        if difficulty not in self.DIFFICULTY_PROFILES:
            difficulty = 1
        validated = dict(data)
        validated["player"] = player_data
        validated["difficulty"] = difficulty
        tutorial_seen = data.get("tutorial_seen")
        if tutorial_seen is not None:
            if (not isinstance(tutorial_seen, list)
                    or any(not isinstance(key, str) for key in tutorial_seen)):
                return None
            validated["tutorial_seen"] = list(dict.fromkeys(tutorial_seen))
        if not isinstance(validated.get("saved_at", "—"), str):
            validated["saved_at"] = "—"
        return validated

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
            "tutorial_seen": sorted(self.tutorial_seen),
            "run_seed": self.run_seed,
            "recent_event_numbers": self.recent_event_numbers,
            "journey_route": (
                self.journey_route.to_dict() if self.journey_route is not None else None
            ),
            "route_completed_ids": list(self.route_completed_ids),
            "route_selected_id": self.route_selected_id,
            "route_active_id": self.route_active_id,
            "elite_reward_choices": list(self.elite_reward_choices),
            "elite_reward_claimed": self.elite_reward_claimed,
            "shop_inventory": list(self.shop_inventory),
            "shop_inventory_level": self.shop_inventory_level,
            "shop_inventory_node_id": self.shop_inventory_node_id,
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
        try:
            run_seed = max(0, int(data.get("run_seed")))
        except (TypeError, ValueError):
            run_seed = self.stable_legacy_run_seed(data)
        recent_events = data.get("recent_event_numbers", [])
        if (not isinstance(recent_events, list)
                or any(not isinstance(value, int) for value in recent_events)):
            recent_events = []
        self.reset_run_variation(run_seed, recent_events=recent_events)
        route_data = data.get("journey_route")
        if isinstance(route_data, dict):
            try:
                restored_route = JourneyRoute.from_dict(route_data)
                validate_journey_route(restored_route)
                completed_ids = data.get("route_completed_ids", [])
                if not isinstance(completed_ids, list):
                    completed_ids = []
                selected_id = data.get("route_selected_id")
                active_id = data.get("route_active_id")
                self.initialize_journey_route(
                    restored_route,
                    completed_ids=[
                        item for item in completed_ids if isinstance(item, str)
                    ],
                    selected_id=selected_id if isinstance(selected_id, str) else None,
                    active_id=active_id if isinstance(active_id, str) else None,
                )
            except (KeyError, TypeError, ValueError):
                self.initialize_journey_route()
                self.migrate_legacy_route_progress(p.lv - 1)
        else:
            self.migrate_legacy_route_progress(p.lv - 1)
        saved_inventory = data.get("shop_inventory", [])
        if (isinstance(saved_inventory, list)
                and saved_inventory
                and all(kind in self.POTIONS for kind in saved_inventory)):
            self.shop_inventory = tuple(dict.fromkeys(saved_inventory))
            try:
                self.shop_inventory_level = max(
                    0, int(data.get("shop_inventory_level", 0))
                )
            except (TypeError, ValueError):
                self.shop_inventory_level = 0
        saved_shop_node = data.get("shop_inventory_node_id", "")
        self.shop_inventory_node_id = (
            saved_shop_node if isinstance(saved_shop_node, str) else ""
        )
        choices = data.get("elite_reward_choices", [])
        if (isinstance(choices, list)
                and all(kind in self.POTIONS for kind in choices)):
            self.elite_reward_choices = tuple(dict.fromkeys(choices))[:3]
        self.elite_reward_claimed = bool(data.get("elite_reward_claimed", True))
        if "tutorial_seen" in data:
            self.tutorial_seen = set(data["tutorial_seen"])
        self.tutorial_tip = ""
        self.migrate_legacy_potions()
        self.name_input = p.name
        self.selected_sex = p.sex
        self.selected_race = p.race
        self.selected_job = p.job
        self.enemy = None
        self.final_enemy_name = ""
        self.victory = False
        self.home_confirmation = False
        self.skill_cooldown_turns = self.SKILL_COOLDOWN_TURNS
        self.reset_skills()
        self.clear_battle_state()
        self.clear_battle_skill_effects()
        self.reset_battle_skill_uses()
        self.clear_floating_damage_feedback()
        self.after_subclass = "adventure"
        self.track_player_hp()
        self.load_player_combat_portraits()
        self.enqueue_job_effect_warmups(p.job, p.sub_job)
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
            self.load_player_combat_portraits()
            if self.cheat_dirty:
                self.log("作弊調整完成，將於下一場戰鬥完全生效。")
                self.cheat_dirty = False
        self.configure_buttons()

    def cheat_value(self, field: str) -> int:
        if field == "difficulty":
            return self.difficulty
        if field == "potions":
            return self.potion_count("heal")
        if field == "luck":
            return int(self.natural_critical_chance())
        return int(getattr(self.player, field))

    def cheat_value_label(self, field: str) -> str:
        value = self.cheat_value(field)
        if field == "difficulty":
            return f"{value}（{self.DIFFICULTY_NAMES[value]}）"
        if field == "lv":
            return self.level_label(value)
        if field == "luck":
            return f"{self.natural_critical_chance():.0f}%"
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
        elif field == "luck":
            p.luck = math.ceil(value)
        elif field in ("defense", "gold", "talent_points"):
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
                    446 + col * 48, 470 - row * 44, 44, 36, str(level),
                    lambda v=level: self.select_cheat_option("lv", v),
                    accent=(102, 86, 151), attention=self.player.lv == level,
                ))
            self.buttons.append(Button(590, 100, 200, 42, "返回",
                                       lambda: self.toggle_cheat_dropdown("lv"),
                                       accent=(73, 79, 91)))
            return
        if self.cheat_dropdown == "difficulty":
            for level in range(1, self.MAX_DIFFICULTY + 1):
                self.buttons.append(Button(
                    590, 470 - (level - 1) * 48, 240, 40,
                    f"{level}（{self.DIFFICULTY_NAMES[level]}）",
                    lambda v=level: self.select_cheat_option("difficulty", v),
                    accent=(102, 86, 151), attention=self.difficulty == level,
                ))
            self.buttons.append(Button(590, 100, 200, 42, "返回",
                                       lambda: self.toggle_cheat_dropdown("difficulty"),
                                       accent=(73, 79, 91)))
            return
        for row_index, (field, _label) in enumerate(self.CHEAT_FIELDS):
            y = self.CHEAT_ROW_TOP - row_index * self.CHEAT_ROW_GAP
            if field in self.CHEAT_DROPDOWN_FIELDS:
                self.buttons.append(Button(
                    750, y, 230, 34, f"{self.cheat_value_label(field)}▾",
                    lambda f=field: self.toggle_cheat_dropdown(f),
                    accent=(102, 86, 151),
                    tooltip="點擊開啟下拉選單。",
                ))
            else:
                focused = self.cheat_focus == field
                label = f"{self.cheat_input}|" if focused else self.cheat_value_label(field)
                self.buttons.append(Button(
                    750, y, 230, 34, label,
                    lambda f=field: self.focus_cheat_field(f),
                    accent=(62, 100, 139), attention=focused,
                    tooltip="點擊後輸入數字（最多 4 位）。",
                ))
        self.buttons.append(Button(590, 100, 200, 42, "關閉", self.toggle_cheat,
                                   accent=(73, 79, 91)))

    def add_potion_menu_buttons(self, anchor_x: float = 650.0,
                                anchor_top: float = 0.0) -> None:
        """以藥水清單取代戰鬥 dock 內容，不覆蓋戰場角色與狀態條。"""
        del anchor_top
        can_choose = not self.battle_busy
        owned = self.owned_potions()
        if not owned:
            # Keep the overlay fail-safe even when a restored or test state
            # incorrectly leaves the menu flag open with an empty bag.
            self.potion_menu_open = False
            self.potion_menu_bounds = None
            return
        columns = min(10, max(1, len(owned)))
        column_gap = 16
        row_gap = 0
        # Potion choices share the normal battle-slot geometry.
        button_width = 64
        button_height = 64
        row_width = columns * button_width + (columns - 1) * column_gap
        left_x = anchor_x - row_width / 2 + button_width / 2
        bottom_row_y = 68.0
        # The battle dock is already the visual container. A second tooltip
        # frame was the cause of the floating panel over the enemy.
        self.potion_menu_bounds = None
        for index, kind in enumerate(owned):
            spec = self.POTIONS[kind]
            label = f"{spec['name']} ×{self.potion_count(kind)}"
            if kind in self.potions_used_this_turn:
                label = f"{spec['name']} 本回合已喝"
            col, row = index % columns, index // columns
            self.buttons.append(Button(
                left_x + col * (button_width + column_gap), bottom_row_y + row * row_gap,
                button_width, button_height,
                label,
                lambda k=kind: self.drink_battle_potion(k),
                enabled=can_choose and self.battle_potion_usable(kind),
                accent=self.BATTLE_ACCENT_POTION,
                tooltip=f"{spec['name']}：{spec['desc']}",
                icon=self.potion_icon(kind), icon_only=True,
                badge=str(self.potion_count(kind)),
            ))

    # ---------- buttons ----------
    def configure_buttons(self) -> None:
        """Build scene controls, then translate every user-facing button field."""
        self._configure_buttons()
        for button in self.buttons:
            button.label = translate(button.label)
            button.tooltip = translate(button.tooltip)
            button.disabled_reason = translate(button.disabled_reason)
            button.sub_label = translate(button.sub_label)

    def _configure_buttons(self) -> None:
        self.sync_ime_state()
        self.pressed_button = None
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
        if self.talent_reset_confirmation:
            self.buttons.extend([
                Button(480, 290, 180, 50, "保留天賦", self.cancel_talent_reset,
                       "ESC", accent=(73, 79, 91), role="secondary"),
                Button(700, 290, 180, 50, "確認重置", self.reset_class_talents,
                       accent=(132, 50, 55), role="danger"),
            ])
            return
        p = self.player
        if self.scene == Scene.TITLE:
            self.buttons.append(Button(
                590, 270, 280, 56, "開始遊戲", self.start_creation, "ENTER",
                role="primary", presentation="surface",
            ))
            if self.has_any_save():
                self.buttons.extend([
                    Button(590, 205, 280, 50, "讀取存檔",
                           lambda: self.open_save_menu("load"), accent=(112, 82, 48)),
                    Button(590, 140, 280, 50, "設定", self.open_settings,
                           accent=(73, 79, 91), role="secondary"),
                    Button(590, 75, 280, 50, "關閉遊戲", self.close_game,
                           accent=(110, 53, 58)),
                ])
            else:
                self.buttons.extend([
                    Button(590, 200, 280, 52, "設定", self.open_settings,
                           accent=(73, 79, 91), role="secondary"),
                    Button(590, 130, 280, 52, "關閉遊戲", self.close_game,
                           accent=(110, 53, 58)),
                ])
            self.buttons.append(Button(
                1105, 38, 110, 38, self.locale_abbreviation(),
                self.toggle_language_menu, "L", accent=(73, 79, 91),
                tooltip="切換語系", role="secondary", presentation="surface",
                selected=self.language_menu_open, group="language",
            ))
            if self.language_menu_open:
                # The currently-selected locale is already shown on the toggle
                # button, so the pop-up lists only the other options.
                other_locales = [loc for loc in SUPPORTED_LOCALES
                                 if loc != self.locale]
                for index, locale in enumerate(other_locales):
                    self.buttons.append(Button(
                        1105, 84 + index * 46, 110, 38,
                        self.locale_abbreviation(locale),
                        lambda selected_locale=locale: self.select_locale(
                            selected_locale
                        ),
                        accent=(112, 82, 48), tooltip="切換語系",
                        role="secondary", presentation="surface",
                        selected=False, group="language",
                    ))
        elif self.scene == Scene.SETTINGS:
            self.buttons.extend([
                Button(590, 430, 410, 50, f"文字縮放　{int(self.ui_scale * 100)}%",
                       self.cycle_ui_scale, "1", accent=(75, 104, 129),
                       sub_label="在 100%、110%、125% 之間切換",
                       selected=self.ui_scale > 1.0),
                Button(590, 320, 410, 50,
                       f"高對比文字　{'開' if self.high_contrast else '關'}",
                       self.toggle_high_contrast, "2", accent=(75, 104, 129),
                       sub_label="提高次要文字與面板資訊的亮度",
                       selected=self.high_contrast),
                Button(590, 210, 410, 50,
                       f"減少動態效果　{'開' if self.reduce_motion else '關'}",
                       self.toggle_reduce_motion, "3", accent=(75, 104, 129),
                       sub_label="隱藏技能粒子與戰鬥提示動畫",
                       selected=self.reduce_motion),
                Button(590, 130, 200, 42, "返回", self.close_settings, "ESC",
                       accent=(73, 79, 91), role="secondary"),
            ])
        elif self.scene == Scene.CREATION:
            if self.creation_step == 0:
                self.buttons.extend([
                    Button(590, 270, 220, 54, "確認名字", self.next_creation_step,
                           enabled=bool(self.name_input.strip())),
                ])
            elif self.creation_step == 1:
                for i, (race, bonus) in enumerate(self.RACES):
                    x = 290 + i * 200
                    self.buttons.append(Button(
                        x, 352, 170, 185, "",
                        lambda selected=race: self.choose_race(selected), str(i + 1),
                        tooltip=(f"{race}｜初始{bonus}｜"
                                 f"{self.race_talent_name_for(race)}："
                                 f"{self.race_talent_description(race)}"),
                        decorated=False,
                    ))
            elif self.creation_step == 2:
                self.buttons.extend([
                    Button(465, 355, 190, 190, "", lambda: self.choose_sex("男性"), "1",
                           tooltip="男性｜防禦增加 5。", decorated=False),
                    Button(715, 355, 190, 190, "", lambda: self.choose_sex("女性"), "2",
                           tooltip="女性｜暴擊增加 1%。", decorated=False),
                ])
            else:
                visible_jobs = self.visible_jobs()
                start_x = 590 - (len(visible_jobs) - 1) * 120
                for i, (job, _bonus) in enumerate(visible_jobs):
                    x = start_x + i * 240
                    self.buttons.append(Button(
                        x, 320, 216, 230, "",
                        lambda selected=job: self.choose_job(selected), str(i + 1),
                        tooltip=self.job_creation_tooltip(job), decorated=False,
                    ))
                if self.job_page > 0:
                    self.buttons.append(Button(208, 322, 48, 58, "‹",
                                               lambda: self.change_job_page(-1), accent=(73, 79, 91),
                                               tooltip="上一組職業", decorated=False))
                if self.job_page < self.max_job_page():
                    self.buttons.append(Button(972, 322, 48, 58, "›",
                                               lambda: self.change_job_page(1), accent=(73, 79, 91),
                                               tooltip="下一組職業", decorated=False))
            if self.creation_step > 0:
                self.buttons.append(Button(480, 120, 180, 42, "上一步",
                                           self.previous_creation_step, "ESC",
                                           accent=(73, 79, 91), role="secondary"))
                home_x = 700
            else:
                home_x = 590
            self.buttons.append(Button(home_x, 120, 180, 42, "回到主頁",
                                       self.request_return_home,
                                       accent=(73, 79, 91), role="secondary"))
        elif self.scene == Scene.ADVENTURE:
            chapter_labels = ("古道", "荒野", "城郊", "城門", "王座")
            # 分頁需容納較長的翻譯(英文如 OUTSKIRTS 約 113px + 內距),故加寬。
            tab_width = 140
            tab_gap = 8
            first_tab_x = 590 - ((len(chapter_labels) - 1) * (tab_width + tab_gap)) / 2
            current_chapter = self.current_route_chapter()
            for index, label in enumerate(chapter_labels, start=1):
                self.buttons.append(Button(
                    first_tab_x + (index - 1) * (tab_width + tab_gap),
                    594, tab_width, 34,
                    f"{index}．{label}",
                    lambda chapter=index: self.set_route_preview_chapter(chapter),
                    "", True,
                    accent=(112, 82, 48) if index == current_chapter else (73, 79, 91),
                    tooltip=(
                        "目前可前往的章節" if index == current_chapter
                        else "預覽本局已生成的後續分支"
                    ),
                    selected=index == self.route_preview_chapter,
                    group="route-chapter",
                ))
            for node in self.route_reachable_nodes():
                if node.chapter != self.route_preview_chapter:
                    continue
                geometry = (
                    route_boss_geometry() if node.kind is NodeKind.BOSS
                    else route_node_geometry(node.layer, node.lane)
                )
                self.buttons.append(Button(
                    geometry.center_x, geometry.center_y,
                    geometry.hit_width, geometry.hit_height,
                    "", lambda node_id=node.id: self.select_route_node(node_id),
                    enabled=True, decorated=False, group="route-node",
                    tooltip="選擇此旅途節點",
                    selected=self.route_selected_id == node.id,
                ))
            selected = self.route_node(self.route_selected_id)
            previewing_future = self.route_preview_chapter != current_chapter
            if previewing_future:
                confirm_label = "回到目前章節"
                confirm_action = (
                    lambda chapter=current_chapter:
                    self.set_route_preview_chapter(chapter)
                )
                confirm_enabled = True
                confirm_reason = ""
            else:
                confirm_label = (
                    "前往所選節點" if selected is not None
                    else "請選擇下一個節點"
                )
                confirm_action = self.confirm_route_selection
                confirm_enabled = selected is not None
                confirm_reason = "請先用滑鼠選擇可達節點"
            self.buttons.extend([
                Button(590, 48, 300, 50, confirm_label,
                       confirm_action, "", confirm_enabled, role="primary",
                       presentation="surface",
                       disabled_reason=confirm_reason),
                Button(850, 48, 170, 44, "存檔 / 讀檔",
                       lambda: self.open_save_menu("manage"), accent=(53, 127, 153)),
                Button(1020, 48, 120, 44, "設定", self.open_settings,
                       "O", accent=(73, 79, 91), role="secondary"),
                Button(1130, 48, 80, 40, "離開", self.request_return_home,
                       accent=(91, 71, 75), role="secondary", decorated=False),
            ])
            if self.has_class_talents():
                self.buttons.append(Button(125, 48, 150, 44, "天賦", self.open_talent_page,
                                           "T",
                                           True, accent=(126, 79, 173),
                                           tooltip="查看天賦；有點數時可以學新能力。",
                                           attention=p.talent_points > 0))
        elif self.scene == Scene.REWARD:
            if self.elite_reward_choices and not self.elite_reward_claimed:
                gap = 220
                first_x = 590 - (len(self.elite_reward_choices) - 1) * gap / 2
                for index, kind in enumerate(self.elite_reward_choices):
                    spec = self.POTIONS[kind]
                    self.buttons.append(Button(
                        first_x + index * gap, 235, 190, 48,
                        f"領取{spec['name']}",
                        lambda k=kind: self.choose_elite_reward(k),
                        accent=(112, 82, 48),
                        tooltip=spec["desc"],
                        icon=self.potion_icon(kind),
                    ))
            self.buttons.append(Button(590, 155, 240, 54, "收下獎勵",
                                       self.continue_after_reward, "ENTER",
                                       not (self.elite_reward_choices
                                            and not self.elite_reward_claimed),
                                       role="primary",
                                       disabled_reason="請先選擇一瓶菁英戰利品"))
        elif self.scene == Scene.TALENT:
            for talent_id, talent in self.class_talent_defs().items():
                tier = int(talent["tier"])
                side = int(talent["side"])
                if tier < 4:
                    x = 395 + side * 480
                    y = 505 - (tier - 1) * 125
                    card_center_x = 350 + side * 480
                else:
                    x = 635
                    y = 130
                    card_center_x = 590
                rank = self.class_talent_rank(talent_id)
                tier_locked = tier > 1 and self.class_tier_spent(tier - 1) < 3
                if rank >= int(talent["max"]):
                    disabled_reason = "已達最高階級"
                elif tier_locked:
                    disabled_reason = f"上一層尚需投入 {3 - self.class_tier_spent(tier - 1)} 點"
                elif p.talent_points < 1:
                    disabled_reason = "沒有可用天賦點"
                else:
                    disabled_reason = ""
                self.buttons.append(Button(
                    x, y, 190, 44, f"{talent['name']} {rank}/{talent['max']}",
                    lambda selected=talent_id: self.learn_class_talent(selected),
                    enabled=self.class_talent_can_add(talent_id),
                    accent=(102, 86, 151),
                    tooltip=self.class_talent_tooltip(talent_id),
                    talent_id=talent_id,
                    disabled_reason=disabled_reason,
                    hit_x=card_center_x, hit_y=y,
                    hit_width=300, hit_height=96,
                ))
            self.buttons.extend([
                Button(480, 34, 180, 42, "重置天賦", self.reset_class_talents,
                       "R", self.class_talent_spent() > 0, accent=(132, 50, 55)),
                Button(700, 34, 180, 42, "返回", self.close_talent_page,
                       "ESC", True, accent=(73, 79, 91)),
            ])
        elif self.scene == Scene.SUBCLASS:
            centers = ((380, 415), (800, 415), (380, 250), (800, 250))
            for i, job in enumerate(self.subclass_options()):
                x, y = centers[i]
                self.buttons.append(Button(
                    x, y, 220, 50, job,
                    lambda selected=job: self.choose_sub_job(selected),
                    str(i + 1), True, accent=(112, 82, 48),
                    tooltip=self.job_skill_tooltip(job),
                ))
        elif self.scene == Scene.BATTLE:
            if self.tutorial_tip:
                final_page = (
                    self.battle_tutorial_page()
                    == len(self.FIRST_BATTLE_TUTORIAL_PAGES) - 1
                )
                self.buttons.extend([
                    Button(
                        500, 188, 180, 46,
                        "開始戰鬥" if final_page else "繼續",
                        self.continue_battle_tutorial, "ENTER", True,
                        accent=(112, 82, 48), role="primary",
                    ),
                    Button(
                        700, 188, 160, 46, "略過教學",
                        self.dismiss_tutorial, "ESC", True,
                        accent=(73, 79, 91), role="secondary",
                    ),
                ])
                return
            can_choose = not self.battle_busy
            self.buttons.append(Button(
                872 if self.battle_log_expanded else 1085,
                492 if self.battle_log_expanded else 670,
                104, 34,
                "關閉" if self.battle_log_expanded else "紀錄",
                self.toggle_battle_log, "L", True, accent=(73, 79, 91),
                tooltip="展開或收合戰鬥紀錄。", decorated=False,
                role="secondary",
            ))
            # The log is a modal overlay. Keep the close control, but do not
            # redraw the skill dock or an open potion menu above the record.
            if self.battle_log_expanded:
                self.potion_menu_open = False
                return
            job_name = self.job_skill_name(p.job)
            job_status = "（已使用）" if self.job_skill_cooldown > 0 else (
                "（生效中）" if self.job_skill_active(p.job) else ""
            )
            job_slots = [(
                self.skill_label(self.job_skill_name(p.job), self.job_skill_cooldown,
                                 self.job_skill_active(p.job)),
                self.use_job_skill,
                "J",
                self.job_skill_enabled(p.job, can_choose and self.job_skill_ready()),
                self.BATTLE_ACCENT_JOB_SKILL,
                f"{job_name}{job_status}：{self.job_skill_tooltip(p.job)}",
                self.battle_skill_icon(p.job),
                (str(self.job_skill_cooldown) if self.job_skill_cooldown > 0
                 else "●" if self.job_skill_active(p.job) else ""),
            )]
            if p.sub_job:
                sub_name = self.job_skill_name(p.sub_job)
                sub_status = "（已使用）" if self.sub_job_skill_cooldown > 0 else (
                    "（生效中）" if self.job_skill_active(p.sub_job) else ""
                )
                job_slots.append((
                    self.skill_label(self.job_skill_name(p.sub_job), self.sub_job_skill_cooldown,
                                     self.job_skill_active(p.sub_job)),
                    lambda: self.use_job_skill(p.sub_job, True),
                    "K",
                    self.job_skill_enabled(
                        p.sub_job,
                        can_choose and self.job_skill_ready(p.sub_job, self.sub_job_skill_cooldown),
                    ),
                    self.BATTLE_ACCENT_JOB_SKILL,
                    f"{sub_name}{sub_status}：{self.job_skill_tooltip(p.sub_job)}",
                    self.battle_skill_icon(p.sub_job),
                    (str(self.sub_job_skill_cooldown) if self.sub_job_skill_cooldown > 0
                     else "●" if self.job_skill_active(p.sub_job) else ""),
                ))
            general_slots = []
            for index, (label, action_id, enabled, _accent, tooltip) in enumerate(
                    self.class_profile().action_slots(self), start=1):
                action_name = self.battle_action_name(label)
                general_slots.append((
                    label,
                    lambda selected=action_id: self.use_class_action(selected),
                    str(index),
                    self.class_action_enabled(action_id, can_choose and enabled),
                    self.battle_class_action_accent(action_id),
                    f"{action_name}：{tooltip}",
                    self.battle_skill_icon(p.job, action_id),
                    "",
                ))
            total_potions = self.total_potions()
            potion_slot = (
                f"藥水 x{total_potions}", self.toggle_potion_menu,
                "P",
                can_choose and total_potions > 0, self.BATTLE_ACCENT_POTION,
                f"藥水袋（剩餘 {total_potions} 瓶）：展開藥水選單；同種藥水每回合只能喝一瓶，使用後不消耗回合。",
                self.potion_icon(),
                str(total_potions),
            )
            # One centred sequence gives every icon the same footprint and
            # rhythm.  The action counter remains the dock's left anchor; job,
            # class, talent and potion actions no longer form disconnected
            # islands with a large accidental hole in the middle.
            slot_width = slot_height = 68
            slot_gap = 14
            dock_y = 73.0
            dock_slots = [*job_slots, *general_slots, potion_slot]
            total_width = (len(dock_slots) * slot_width
                           + max(0, len(dock_slots) - 1) * slot_gap)
            dock_center_x = (180.0 + 1125.0) / 2
            first_x = dock_center_x - total_width / 2 + slot_width / 2
            slot_xs = [first_x + index * (slot_width + slot_gap)
                       for index in range(len(dock_slots))]

            if self.potion_menu_open:
                self.add_potion_menu_buttons(anchor_x=dock_center_x)
                self.buttons.append(Button(
                    slot_xs[-1], dock_y, slot_width, slot_height, "",
                    self.toggle_potion_menu, "P", True,
                    accent=self.BATTLE_ACCENT_POTION,
                    tooltip="收起藥水袋，返回技能列。",
                    icon=self.potion_icon(), icon_only=True,
                ))
                return

            for slot_x, (_label, action, shortcut, enabled, accent,
                         tooltip, icon, badge) in zip(slot_xs, dock_slots):
                self.buttons.append(Button(
                    slot_x, dock_y, slot_width, slot_height, "", action, shortcut,
                    enabled, accent=accent, tooltip=tooltip,
                    icon=icon, icon_only=True, badge=badge,
                ))
            return
        elif self.scene == Scene.CAMPFIRE:
            rest_percent = 50 if p.race == "獸人" else 33
            rest_amount = min(
                max(0, p.max_hp - p.hp),
                max(1, math.ceil(p.max_hp * rest_percent / 100)),
            )
            ability_rate = .05 if p.race == "人類" else .03
            attack_gain = max(1, math.ceil(p.attack * ability_rate))
            defense_gain = max(1, math.ceil(p.defense * ability_rate))
            camp_gold = p.lv * 60 * (2 if p.race == "矮人" else 1)
            camp_luck_amount = 2 if p.race == "人類" else 1
            camp_critical_gain = (
                self.critical_chance_for_luck(p.luck + camp_luck_amount)
                - self.natural_critical_chance()
            )
            camp_specs = {
                "rest": (
                    f"恢復 {rest_amount} 血量", self.choose_campfire_rest,
                    (71, 127, 85),
                ),
                "attack": (
                    f"攻擊 +{attack_gain}",
                    lambda: self.choose_campfire_stat("attack"),
                    (147, 92, 54),
                ),
                "defense": (
                    f"防禦 +{defense_gain}",
                    lambda: self.choose_campfire_stat("defense"),
                    (75, 104, 129),
                ),
                "luck": (
                    f"暴擊 +{camp_critical_gain:.0f}%",
                    lambda: self.choose_campfire_stat("luck"),
                    (102, 86, 151),
                ),
                "gold": (
                    f"金幣 +{camp_gold}G",
                    lambda: self.choose_campfire_stat("gold"),
                    (112, 82, 48),
                ),
            }
            count = len(self.campfire_options)
            gap = 230
            first_x = 590 - (count - 1) * gap / 2
            for index, option in enumerate(self.campfire_options):
                label, action, accent = camp_specs[option]
                self.buttons.append(Button(
                    first_x + index * gap, 66, 190, 46, label, action,
                    str(index + 1), True, accent=accent,
                    tooltip="只能選擇一項；選擇後會立即離開營火。",
                    presentation="surface",
                ))
        elif self.scene == Scene.SHOP:
            for i, kind in enumerate(self.shop_inventory):
                spec = self.POTIONS[kind]
                col, row = i % 2, i // 2
                price = self.potion_price(kind)
                self.buttons.append(Button(
                    self.SHOP_CARD_CENTERS[col],
                    self.SHOP_CARD_TOP - row * self.SHOP_CARD_ROW_GAP,
                    self.SHOP_CARD_WIDTH, self.SHOP_CARD_HEIGHT,
                    f"{price}G",
                                           lambda k=kind: self.buy_potion(k),
                                           "", self.potion_available(kind),
                                           accent=(112, 82, 48),
                                           tooltip=f"{spec['name']}\n{spec['desc']}",
                                           disabled_reason=f"需要 {price}G，目前只有 {p.gold}G",
                                           icon=self.potion_icon(kind)))
            self.buttons.append(Button(590, 55, 180, 42, "離開藥水商", self.leave_black_market, "ESC",
                                       accent=(77, 83, 95)))
        elif self.scene == Scene.EVENT:
            event_layout = self.event_panel_layout()
            event_button_x = event_layout[6]
            event_button_ys = event_layout[7]
            if self.event_resolved:
                self.buttons.append(Button(event_button_x, event_button_ys[0], 160, 42,
                                           "繼續旅程", self.leave_event, "ENTER",
                                           accent=(77, 83, 95)))
            else:
                if len(self.event_options) == 1:
                    self.buttons.append(
                        Button(event_button_x, event_button_ys[0], 160, 42,
                               self.event_options[0],
                               lambda: self.choose_event_option(0), "1",
                               accent=(112, 82, 48),
                               tooltip="收下城門藥師贈送的月泉靈藥。")
                    )
                else:
                    top_label, bottom_label = self.event_options
                    self.buttons.extend([
                        Button(event_button_x, event_button_ys[0], 160, 42, top_label,
                               lambda: self.choose_event_option(0), "1",
                               accent=(112, 82, 48)),
                        Button(event_button_x, event_button_ys[1], 160, 42, bottom_label,
                               lambda: self.choose_event_option(1), "2",
                               accent=(75, 104, 129)),
                    ])
        elif self.scene == Scene.SAVE_MENU:
            for slot in range(1, self.SAVE_SLOT_COUNT + 1):
                center_y = 446 - (slot - 1) * 104
                has_data = bool(self.save_slots.get(slot))
                if self.save_menu_mode == "manage":
                    self.buttons.extend([
                        Button(835, center_y + 23, 110, 38, "存檔",
                               lambda n=slot: self.save_to_slot(n),
                               accent=(71, 127, 85),
                               tooltip=f"把目前旅程寫入存檔槽 {slot}。"
                                       + ("會覆蓋原本的紀錄。" if has_data else "")),
                        Button(835, center_y - 23, 110, 38, "讀檔",
                               lambda n=slot: self.load_from_slot(n),
                               enabled=has_data, accent=(112, 82, 48),
                               tooltip=f"讀取存檔槽 {slot} 的旅程進度。" if has_data
                               else ""),
                    ])
                else:
                    self.buttons.append(Button(835, center_y, 120, 42, "讀取",
                                               lambda n=slot: self.load_from_slot(n),
                                               enabled=has_data, accent=(112, 82, 48),
                                               tooltip=f"讀取存檔槽 {slot} 的旅程進度。" if has_data
                                               else ""))
            self.buttons.append(Button(590, 108, 190, 42, "返回", self.close_save_menu,
                                       "ESC", accent=(73, 79, 91)))
        elif self.scene == Scene.END:
            self.buttons.extend([
                Button(350, 70, 200, 50, "再玩一次", self.replay),
                Button(590, 70, 160, 50, "紀錄", self.toggle_end_record,
                       accent=(112, 82, 48), selected=self.end_record_open,
                       tooltip="顯示或收起此次玩家紀錄。"),
                Button(830, 70, 200, 50, "回到主頁", self.request_return_home,
                       accent=(73, 79, 91)),
            ])

    # ---------- draw scenes ----------

    # ---------- animation and input ----------
    def apply_ui_viewport(self, width: int | None = None,
                          height: int | None = None) -> None:
        """Map the fixed UI canvas onto the real framebuffer without cropping."""
        logical_width = max(1, int(width if width is not None else self.width))
        logical_height = max(1, int(height if height is not None else self.height))
        responsive = self.ui_canvas.fit(logical_width, logical_height)
        self._responsive_viewport = responsive
        canvas_scale = responsive.scale
        viewport_width = max(1, round(responsive.width))
        viewport_height = max(1, round(responsive.height))
        viewport_left = round(responsive.left)
        viewport_bottom = round(responsive.bottom)

        self.viewport = (
            viewport_left, viewport_bottom, viewport_width, viewport_height,
        )
        # Set viewport before projection. Arcade applies the DPI multiplier
        # to viewport coordinates internally on Windows.
        self.projection = Mat4.orthogonal_projection(
            0, SCREEN_WIDTH, 0, SCREEN_HEIGHT, -8192, 8192,
        )
        self._ui_viewport = (
            float(viewport_left), float(viewport_bottom), float(canvas_scale),
        )

    def on_resize(self, width: int, height: int) -> None:
        # Arcade's internal resize handler runs first and restores a
        # window-sized viewport; immediately replace it with the DPI-aware
        # physical framebuffer mapping.
        self.apply_ui_viewport(width, height)

    def screen_to_ui(self, x: float, y: float) -> tuple[float, float]:
        responsive = getattr(self, "_responsive_viewport", None)
        if responsive is not None:
            return self.ui_canvas.to_canvas(x, y, responsive)
        viewport = getattr(self, "_ui_viewport", None)
        if viewport is None:
            return x, y
        left, bottom, canvas_scale = viewport
        return (
            (x - left) / canvas_scale,
            (y - bottom) / canvas_scale,
        )

    def move_button_focus(self, horizontal: int = 0, vertical: int = 0,
                          cycle: int = 0) -> None:
        candidates = [index for index, button in enumerate(self.buttons)
                      if (not button.invisible and button.enabled
                          and button.group not in {"route-node", "route-chapter"})]
        if not candidates:
            self.focused_button_index = -1
            return
        if self.focused_button_index not in candidates:
            self.focused_button_index = candidates[0 if cycle >= 0 else -1]
            self.hovered = None
            return
        if cycle:
            position = candidates.index(self.focused_button_index)
            self.focused_button_index = candidates[(position + cycle) % len(candidates)]
            self.hovered = None
            return
        current = self.buttons[self.focused_button_index]
        choices: list[tuple[float, int]] = []
        for index in candidates:
            if index == self.focused_button_index:
                continue
            button = self.buttons[index]
            dx, dy = button.x - current.x, button.y - current.y
            if horizontal and dx * horizontal <= 0:
                continue
            if vertical and dy * vertical <= 0:
                continue
            primary = abs(dx) if horizontal else abs(dy)
            secondary = abs(dy) if horizontal else abs(dx)
            choices.append((primary + secondary * .35, index))
        if choices:
            self.focused_button_index = min(choices)[1]
            self.hovered = None

    def activate_focused_button(self) -> bool:
        if not self.buttons or self.focused_button_index < 0:
            return False
        index = min(self.focused_button_index, len(self.buttons) - 1)
        button = self.buttons[index]
        if not button.enabled or button.invisible:
            return False
        self.run_button_action(button)
        self.hovered = None
        return True

    def run_button_action(self, button: Button) -> None:
        """執行滑鼠、鍵盤或手把觸發的按鈕。"""
        self.play_sound("ui_click", volume=.48)
        button.action()

    def on_update(self, delta_time: float) -> None:
        if (self.scene == Scene.CREATION and self.creation_step == 0
                and self.name_input_focused):
            self.name_caret_timer += delta_time
        if self.scene != Scene.BATTLE and not self.asset_warmup.idle:
            self.asset_warmup.step(5.0)
        self._audio_prune_elapsed += delta_time
        if self._audio_prune_elapsed >= .25:
            self._audio_prune_elapsed = 0.0
            self.sounds.prune_finished_players()
        # Consume hit-stop from the real frame without throwing away the
        # remainder.  The previous early-return path rounded every stop up to
        # the next full frame (55 ms became ~67 ms at 60 Hz).  Keeping a
        # separate simulation delta preserves the same authored 55/90 ms pose
        # freeze while making its duration independent of refresh rate.
        simulation_delta = delta_time
        if self.hit_stop_remaining > 0:
            frozen_delta = min(simulation_delta, self.hit_stop_remaining)
            self.hit_stop_remaining -= frozen_delta
            simulation_delta -= frozen_delta
        self.update_combat_feedback(simulation_delta)
        if simulation_delta <= 0:
            return
        surviving_floating: list[FloatingDamage] = []
        for floating in self.floating_damage:
            floating.elapsed += simulation_delta
            if floating.elapsed < 1.05:
                surviving_floating.append(floating)
            else:
                self.release_floating_damage_label(floating)
        self.floating_damage = surviving_floating
        for effect in self.skill_effects:
            effect.elapsed += simulation_delta
        self.skill_effects = [
            effect for effect in self.skill_effects if effect.elapsed < effect.duration
        ]
        if self.scene != Scene.BATTLE:
            self.skill_effects.clear()
            return
        self.battle_clock += simulation_delta
        if self.cheat_open:
            return
        if self.attack_animation:
            self.attack_animation.elapsed += simulation_delta * (
                4 if self.reduce_motion else 1
            )
            if self.attack_animation.elapsed >= .17:
                self.apply_attack_impact()
            if self.attack_animation and self.attack_animation.elapsed >= .48:
                self.finish_attack_animation()
            return
        if self.pending_turn:
            self.battle_delay -= simulation_delta
            if self.battle_delay <= 0:
                turn = self.pending_turn
                self.pending_turn = None
                if turn == "enemy":
                    self.enemy_attack()

    def log_scroll_available(self) -> bool:
        return (
            not self.home_confirmation
            and not self.cheat_open
            and not self.tutorial_tip
            and self.scene not in (Scene.TITLE, Scene.CREATION,
                                   Scene.TALENT, Scene.SAVE_MENU)
            and self._log_scroll_geometry is not None
        )

    def on_mouse_scroll(self, x: float, y: float,
                        scroll_x: float, scroll_y: float) -> None:
        x, y = self.screen_to_ui(x, y)
        if not self.log_scroll_available():
            return
        track_left, track_bottom, track_width, track_height = self._log_scroll_geometry[:4]
        if not (20 <= x <= track_left + track_width
                and track_bottom - 17 <= y <= track_bottom + track_height + 32):
            return
        maximum = int(self._log_scroll_geometry[6])
        if scroll_y:
            steps = max(1, int(abs(scroll_y)))
            direction = 1 if scroll_y < 0 else -1
            self.log_scroll = max(0, min(maximum, self.log_scroll + direction * steps))

    def on_mouse_motion(self, x: float, y: float, dx: float, dy: float) -> None:
        x, y = self.screen_to_ui(x, y)
        # Disabled controls still need hover so their explanatory tooltip can
        # tell the player what requirement is missing. Click handling remains
        # gated by Button.contains().
        self.hovered = next(
            (b for b in self.buttons if not b.invisible and b.hit_test(x, y)),
            None,
        )
        self.hovered_enemy_intent_index = None
        if (self.scene == Scene.BATTLE and not self.battle_log_expanded
                and not self.tutorial_tip
                and not self.home_confirmation and not self.cheat_open):
            # Prefer the compact intent icon, while the visible portrait is a
            # larger discovery target. Multi-enemy click targeting is separate.
            for hitboxes in (self.enemy_intent_hitboxes, self.enemy_hitboxes):
                for index, (left, bottom, width, height) in enumerate(hitboxes):
                    if (index < len(self.enemies)
                            and left <= x <= left + width
                            and bottom <= y <= bottom + height):
                        self.hovered_enemy_intent_index = index
                        break
                if self.hovered_enemy_intent_index is not None:
                    break
        over_scroll = False
        if self.log_scroll_available():
            track_left, track_bottom, track_width, track_height = self._log_scroll_geometry[:4]
            over_scroll = (
                track_left <= x <= track_left + track_width
                and track_bottom <= y <= track_bottom + track_height
            )
        over_name_box = (
            self.scene == Scene.CREATION and self.creation_step == 0
            and not self.home_confirmation and not self.cheat_open
            and self.name_box_hit(x, y)
        )
        over_enemy = self.hovered_enemy_intent_index is not None
        if ((self.hovered and self.hovered.enabled)
                or over_scroll or over_enemy):
            cursor = self.CURSOR_HAND
        elif over_name_box:
            cursor = self.CURSOR_TEXT
        else:
            cursor = self.CURSOR_DEFAULT
        self.set_mouse_cursor(self.get_system_mouse_cursor(cursor))

    def on_mouse_press(self, x: float, y: float, button: int, modifiers: int) -> None:
        x, y = self.screen_to_ui(x, y)
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
        if (self.scene == Scene.CREATION and self.creation_step == 0
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
        if (self.scene == Scene.TITLE and self.language_menu_open
                and (clicked is None or clicked.group != "language")):
            # Collapse first, then resolve the click again so selecting another
            # title control still works in the same press/release gesture.
            self.language_menu_open = False
            self.configure_buttons()
            clicked = next((b for b in self.buttons if b.contains(x, y)), None)
        if clicked:
            # Execute on release. This provides a readable pressed state and
            # lets the player cancel by dragging outside the original target.
            self.pressed_button = clicked
            self.hovered = clicked
        elif self.cheat_open and (self.cheat_focus or self.cheat_dropdown):
            self.unfocus_cheat_field()

    def on_mouse_drag(self, x: float, y: float, dx: float, dy: float,
                      buttons: int, modifiers: int) -> None:
        x, y = self.screen_to_ui(x, y)
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
        x, y = self.screen_to_ui(x, y)
        if button == arcade.MOUSE_BUTTON_LEFT:
            self.log_scroll_dragging = False
            pressed = self.pressed_button
            self.pressed_button = None
            if pressed is not None and pressed.contains(x, y):
                self.run_button_action(pressed)
                self.hovered = None

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
                self.run_button_action(button)
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
        if symbol == arcade.key.ESCAPE and self.language_menu_open:
            self.close_language_menu()
            return
        if symbol == arcade.key.TAB:
            self.move_button_focus(cycle=-1 if modifiers & arcade.key.MOD_SHIFT else 1)
            return
        if symbol in (arcade.key.LEFT, arcade.key.RIGHT, arcade.key.UP, arcade.key.DOWN):
            self.move_button_focus(
                horizontal=(-1 if symbol == arcade.key.LEFT else (1 if symbol == arcade.key.RIGHT else 0)),
                vertical=(1 if symbol == arcade.key.UP else (-1 if symbol == arcade.key.DOWN else 0)),
            )
            return
        if symbol in (arcade.key.SPACE, arcade.key.ENTER, arcade.key.NUM_ENTER):
            if self.activate_focused_button():
                return
        if not (self.scene == Scene.CREATION and self.creation_step == 0):
            if self.activate_shortcut(symbol):
                return
        if self.scene != Scene.CREATION or self.creation_step != 0:
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

    def on_joyhat_motion(self, joystick, hat_x: int, hat_y: int) -> None:
        if hat_x or hat_y:
            self.move_button_focus(horizontal=hat_x, vertical=hat_y)

    def on_joybutton_press(self, joystick, button: int) -> None:
        if button == 0:
            self.activate_focused_button()
        elif button == 1:
            escape_button = next((item for item in self.buttons
                                  if item.shortcut.upper() == "ESC" and item.enabled), None)
            if escape_button:
                self.run_button_action(escape_button)

    def on_text(self, text: str) -> None:
        if self.cheat_open:
            self.cheat_input_text(text)
            return
        if self.scene != Scene.CREATION or self.creation_step != 0:
            return
        self.add_name_text(text)

def main() -> None:
    RPGWindow()
    arcade.run()


if __name__ == "__main__":
    main()
