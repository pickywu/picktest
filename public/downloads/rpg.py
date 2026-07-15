r"""Arcade + Pycairo 製作的黑暗奇幻互動 RPG。

Arcade 負責滑鼠互動與 UI，Pycairo 動態繪製背景、角色及怪物圖像。

執行：.\.venv\Scripts\python.exe rpg.py
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
import io
import math
import random
from typing import Callable

try:
    import arcade
    import cairo
    from PIL import Image
except ImportError as exc:
    raise SystemExit(
        "缺少遊戲套件。Python 3.14 請執行 setup_game.ps1；"
        "其他版本請執行 pip install -r requirements.txt"
    ) from exc


SCREEN_WIDTH = 1180
SCREEN_HEIGHT = 720
SCREEN_TITLE = "餘燼王國：失落王座"

INK = (235, 232, 220)
MUTED = (169, 178, 191)
GOLD = (239, 191, 91)
PANEL = (13, 21, 35, 230)
PANEL_EDGE = (75, 96, 124)
RED = (202, 67, 73)
GREEN = (66, 174, 111)
BLUE = (58, 122, 184)


class Scene(Enum):
    TITLE = auto()
    CREATION = auto()
    ADVENTURE = auto()
    BATTLE = auto()
    SHOP = auto()
    EVENT = auto()
    END = auto()


@dataclass
class Player:
    """冒險者的能力、財富與隨身物品。"""

    name: str = "勇者"
    sex: str = "男性"
    race: str = "獸人"
    job: str = "戰士"
    lv: int = 1
    hp: int = 20
    attack: int = 10
    defense: int = 10
    luck: int = 1
    gold: int = 0
    exp: int = 0
    black_market_lv: int = 0
    potions: int = 0


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


@dataclass
class AttackAnimation:
    attacker: str
    damage: int
    critical: bool
    elapsed: float = 0.0
    impacted: bool = False


@dataclass
class FloatingDamage:
    target: str
    amount: int
    critical: bool
    healing: bool = False
    elapsed: float = 0.0
    label: object | None = None


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

    def contains(self, px: float, py: float) -> bool:
        return (
            self.enabled
            and self.x - self.width / 2 <= px <= self.x + self.width / 2
            and self.y - self.height / 2 <= py <= self.y + self.height / 2
        )


def texture_from_cairo(width: int, height: int, painter: Callable) -> arcade.Texture:
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    ctx = cairo.Context(surface)
    painter(ctx, width, height)
    stream = io.BytesIO()
    surface.write_to_png(stream)
    stream.seek(0)
    image = Image.open(stream).convert("RGBA")
    image.load()
    return arcade.Texture(image=image)


def make_background() -> arcade.Texture:
    def paint(ctx: cairo.Context, w: int, h: int) -> None:
        gradient = cairo.LinearGradient(0, 0, 0, h)
        gradient.add_color_stop_rgb(0, .025, .04, .09)
        gradient.add_color_stop_rgb(.58, .08, .15, .24)
        gradient.add_color_stop_rgb(1, .20, .14, .16)
        ctx.set_source(gradient)
        ctx.paint()

        rng = random.Random(1987)
        for _ in range(105):
            x, y = rng.randrange(w), rng.randrange(int(h * .55), h)
            radius = rng.choice((.6, .8, 1.1, 1.5))
            ctx.arc(x, y, radius, 0, math.tau)
            ctx.set_source_rgba(.88, .91, 1, rng.uniform(.25, .8))
            ctx.fill()

        moon = cairo.RadialGradient(w * .81, h * .82, 3, w * .81, h * .82, 64)
        moon.add_color_stop_rgba(0, 1, .94, .68, 1)
        moon.add_color_stop_rgba(1, .78, .82, .88, .12)
        ctx.arc(w * .81, h * .82, 64, 0, math.tau)
        ctx.set_source(moon)
        ctx.fill()

        mountains = (
            ([(0, 205), (155, 385), (285, 245), (450, 410), (625, 225),
              (790, 360), (960, 225), (1100, 370), (w, 265), (w, 0), (0, 0)],
             (.07, .11, .17)),
            ([(0, 80), (185, 245), (330, 95), (500, 270), (690, 75),
              (870, 220), (1040, 90), (w, 175), (w, 0), (0, 0)],
             (.025, .05, .075)),
        )
        for points, color in mountains:
            ctx.move_to(*points[0])
            for point in points[1:]:
                ctx.line_to(*point)
            ctx.set_source_rgb(*color)
            ctx.fill()

        # 遠方終極魔王的城堡
        ctx.set_source_rgb(.018, .03, .045)
        ctx.rectangle(830, 175, 145, 100)
        for x, height in ((812, 135), (875, 155), (958, 145)):
            ctx.rectangle(x, 175, 34, height)
            ctx.move_to(x - 5, 175 + height)
            ctx.line_to(x + 17, 205 + height)
            ctx.line_to(x + 39, 175 + height)
            ctx.close_path()
        ctx.fill()
        ctx.set_source_rgba(1, .55, .13, .8)
        for x, y in ((842, 235), (920, 238), (967, 252)):
            ctx.rectangle(x, y, 7, 13)
            ctx.fill()

    return texture_from_cairo(SCREEN_WIDTH, SCREEN_HEIGHT, paint)


def make_portrait(enemy: bool = False) -> arcade.Texture:
    def paint(ctx: cairo.Context, w: int, h: int) -> None:
        glow = cairo.RadialGradient(w / 2, h / 2, 5, w / 2, h / 2, w / 2)
        glow.add_color_stop_rgba(0, .72 if enemy else .18, .12 if enemy else .46,
                                 .15 if enemy else .72, .85)
        glow.add_color_stop_rgba(1, .04, .02, .06, 0)
        ctx.set_source(glow)
        ctx.paint()
        ctx.translate(w / 2, h / 2)
        if enemy:
            ctx.set_source_rgb(.14, .025, .04)
            ctx.move_to(-62, -58)
            ctx.curve_to(-115, -120, -126, -62, -76, -5)
            ctx.line_to(76, -5)
            ctx.curve_to(126, -62, 115, -120, 62, -58)
            ctx.curve_to(96, 22, 72, 98, 0, 119)
            ctx.curve_to(-72, 98, -96, 22, -62, -58)
            ctx.fill()
            ctx.set_source_rgb(1, .52, .12)
            ctx.arc(-45, 0, 8, 0, math.tau)
            ctx.arc(45, 0, 8, 0, math.tau)
            ctx.fill()
        else:
            ctx.set_source_rgb(.07, .14, .22)
            ctx.move_to(-70, -88)
            ctx.curve_to(-120, -18, -105, 95, -75, 120)
            ctx.line_to(80, 120)
            ctx.curve_to(108, 42, 100, -40, 60, -88)
            ctx.close_path()
            ctx.fill()
            ctx.set_source_rgb(.65, .69, .70)
            ctx.arc(0, 2, 52, 0, math.tau)
            ctx.fill()
            ctx.set_source_rgb(.055, .09, .14)
            ctx.move_to(-57, -2)
            ctx.curve_to(-30, -95, 34, -95, 59, -2)
            ctx.curve_to(20, -30, -20, -30, -57, -2)
            ctx.fill()
            ctx.set_source_rgb(.97, .72, .21)
            ctx.rectangle(-31, 7, 21, 4)
            ctx.rectangle(12, 7, 21, 4)
            ctx.fill()

    return texture_from_cairo(300, 300, paint)


def make_activity_background(kind: str, variant: int = 0) -> arcade.Texture:
    """Draw a dedicated battle, event, or black-market backdrop."""
    def paint(ctx: cairo.Context, w: int, h: int) -> None:
        if kind == "battle":
            sky = cairo.LinearGradient(0, 0, 0, h)
            sky.add_color_stop_rgb(0, .09, .025, .04)
            sky.add_color_stop_rgb(.58, .34, .09, .07)
            sky.add_color_stop_rgb(1, .08, .055, .045)
            ctx.set_source(sky); ctx.paint()
            ctx.set_source_rgba(1, .38, .12, .36)
            ctx.arc(w * .5, h * .73, 92, 0, math.tau); ctx.fill()
            ctx.set_source_rgb(.055, .035, .03)
            ctx.move_to(0, 135); ctx.line_to(145, 220); ctx.line_to(265, 142)
            ctx.line_to(395, 245); ctx.line_to(535, 130); ctx.line_to(w, 210)
            ctx.line_to(w, 0); ctx.line_to(0, 0); ctx.close_path(); ctx.fill()
            # Cracked arena floor and two banners.
            ctx.set_source_rgb(.12, .085, .065); ctx.rectangle(0, 0, w, 135); ctx.fill()
            ctx.set_source_rgba(.75, .38, .18, .35); ctx.set_line_width(2)
            for x in range(45, w, 95):
                ctx.move_to(x, 0); ctx.line_to(x + 25, 55); ctx.line_to(x - 8, 105); ctx.stroke()
            for x, flip in ((70, 1), (w - 70, -1)):
                ctx.set_source_rgb(.18, .13, .10); ctx.rectangle(x - 4, 165, 8, 230); ctx.fill()
                ctx.set_source_rgb(.48, .07, .08)
                ctx.move_to(x, 378); ctx.line_to(x + 62 * flip, 354)
                ctx.line_to(x + 52 * flip, 285); ctx.line_to(x, 305); ctx.close_path(); ctx.fill()
        elif kind == "shop":
            wall = cairo.LinearGradient(0, 0, 0, h)
            wall.add_color_stop_rgb(0, .055, .035, .07)
            wall.add_color_stop_rgb(1, .19, .095, .045)
            ctx.set_source(wall); ctx.paint()
            # Canvas tent roof.
            ctx.set_source_rgb(.22, .055, .075)
            ctx.move_to(0, h); ctx.line_to(w, h); ctx.line_to(w * .84, h * .72)
            ctx.line_to(w * .16, h * .72); ctx.close_path(); ctx.fill()
            ctx.set_source_rgba(.9, .55, .16, .24)
            for x in (115, w - 115):
                ctx.arc(x, h * .67, 42, 0, math.tau); ctx.fill()
                ctx.set_source_rgb(.95, .58, .17); ctx.arc(x, h * .67, 8, 0, math.tau); ctx.fill()
                ctx.set_source_rgba(.9, .55, .16, .24)
            # Shelves, bottles, crates, and a central counter.
            ctx.set_source_rgb(.16, .09, .055)
            for y in (145, 255, 365): ctx.rectangle(35, y, w - 70, 13)
            ctx.fill()
            bottle_colors = ((.22, .7, .48), (.65, .16, .3), (.22, .45, .75), (.73, .55, .12))
            for row, y in enumerate((165, 275, 385)):
                for col, x in enumerate(range(65, w - 45, 74)):
                    r, g, b = bottle_colors[(row + col) % len(bottle_colors)]
                    ctx.set_source_rgba(r, g, b, .85)
                    ctx.rectangle(x, y, 26, 48); ctx.arc(x + 13, y + 48, 13, math.pi, 0); ctx.fill()
                    ctx.set_source_rgb(.72, .62, .43); ctx.rectangle(x + 8, y + 58, 10, 12); ctx.fill()
            ctx.set_source_rgb(.13, .07, .04); ctx.rectangle(120, 0, w - 240, 108); ctx.fill()
            ctx.set_source_rgb(.34, .18, .08); ctx.rectangle(105, 98, w - 210, 18); ctx.fill()
        else:
            palettes = (
                ((.045, .08, .12), (.13, .20, .21)),
                ((.035, .08, .15), (.16, .20, .34)),
                ((.035, .12, .10), (.18, .27, .14)),
                ((.12, .07, .025), (.28, .18, .055)),
            )
            top, bottom = palettes[max(0, min(3, variant - 1))]
            sky = cairo.LinearGradient(0, 0, 0, h)
            sky.add_color_stop_rgb(0, *top); sky.add_color_stop_rgb(1, *bottom)
            ctx.set_source(sky); ctx.paint()
            # Forest path shared by all event variants.
            ctx.set_source_rgb(.035, .065, .055)
            for x in range(0, w + 1, 95):
                ctx.rectangle(x, 80, 24, 350)
                ctx.arc(x + 12, 420, 70, 0, math.tau)
            ctx.fill()
            ctx.set_source_rgba(.48, .39, .22, .5)
            ctx.move_to(w * .36, 0); ctx.curve_to(w * .42, 175, w * .56, 270, w * .55, h)
            ctx.line_to(w * .66, h); ctx.curve_to(w * .62, 270, w * .55, 165, w * .65, 0)
            ctx.close_path(); ctx.fill()
            if variant == 1:  # merchant silhouette
                ctx.set_source_rgba(.95, .54, .14, .35); ctx.arc(w * .52, 335, 105, 0, math.tau); ctx.fill()
                ctx.set_source_rgb(.12, .055, .04); ctx.arc(w * .52, 330, 55, 0, math.tau); ctx.fill()
                ctx.move_to(w * .43, 150); ctx.line_to(w * .61, 150); ctx.line_to(w * .57, 315)
                ctx.line_to(w * .47, 315); ctx.close_path(); ctx.fill()
            elif variant == 2:  # light from the sky
                beam = cairo.LinearGradient(w * .5, h, w * .5, 0)
                beam.add_color_stop_rgba(0, .4, .65, 1, 0)
                beam.add_color_stop_rgba(1, .7, .86, 1, .7)
                ctx.set_source(beam); ctx.move_to(w * .35, 0); ctx.line_to(w * .46, h)
                ctx.line_to(w * .61, h); ctx.line_to(w * .67, 0); ctx.close_path(); ctx.fill()
            elif variant == 3:  # mysterious potion
                ctx.set_source_rgba(.26, 1, .55, .32); ctx.arc(w * .53, 180, 78, 0, math.tau); ctx.fill()
                ctx.set_source_rgb(.15, .7, .39); ctx.rectangle(w * .50, 145, 42, 78); ctx.fill()
                ctx.set_source_rgb(.72, .58, .34); ctx.rectangle(w * .51, 220, 26, 18); ctx.fill()
            else:  # treasure chest
                ctx.set_source_rgba(1, .63, .12, .28); ctx.arc(w * .53, 190, 100, 0, math.tau); ctx.fill()
                ctx.set_source_rgb(.34, .14, .045); ctx.rectangle(w * .43, 125, 150, 105); ctx.fill()
                ctx.set_source_rgb(.62, .32, .08); ctx.arc(w * .525, 225, 75, math.pi, 0); ctx.fill()
                ctx.set_source_rgb(.87, .65, .18); ctx.rectangle(w * .515, 166, 16, 28); ctx.fill()

        # Subtle vignette improves text contrast at the edges.
        vignette = cairo.RadialGradient(w / 2, h / 2, w * .18, w / 2, h / 2, w * .68)
        vignette.add_color_stop_rgba(0, 0, 0, 0, 0)
        vignette.add_color_stop_rgba(1, 0, 0, 0, .58)
        ctx.set_source(vignette); ctx.paint()

    return texture_from_cairo(800, 565, paint)


def make_player_portrait(sex: str, race: str, job: str) -> arcade.Texture:
    """Compose visible gender, race, and class traits into one portrait."""
    def paint(ctx: cairo.Context, w: int, h: int) -> None:
        race_colors = {
            "獸人": (.30, .54, .27), "人類": (.78, .58, .43),
            "矮人": (.66, .46, .32), "精靈": (.72, .61, .48),
        }
        skin = race_colors[race]
        job_colors = {
            "戰士": (.48, .10, .09), "法師": (.17, .22, .58),
            "聖騎士": (.65, .54, .18), "盜賊": (.16, .28, .24),
        }
        accent = job_colors[job]
        glow = cairo.RadialGradient(w / 2, h * .52, 8, w / 2, h * .52, w * .48)
        glow.add_color_stop_rgba(0, *accent, .62); glow.add_color_stop_rgba(1, 0, 0, 0, 0)
        ctx.set_source(glow); ctx.paint(); ctx.translate(w / 2, h / 2)

        female = sex == "女性"
        shoulder = 72 if female else 88
        # Cloak / armor silhouette.
        ctx.set_source_rgb(*accent)
        ctx.move_to(-shoulder, 116); ctx.line_to(-shoulder + 12, 32)
        ctx.curve_to(-55, 5, 55, 5, shoulder - 12, 32)
        ctx.line_to(shoulder, 116); ctx.close_path(); ctx.fill()
        if job == "聖騎士":
            ctx.set_source_rgb(.72, .72, .66)
            ctx.arc(-shoulder + 8, 48, 26, 0, math.tau); ctx.arc(shoulder - 8, 48, 26, 0, math.tau); ctx.fill()
            ctx.set_source_rgb(.92, .72, .20); ctx.rectangle(-7, 55, 14, 55); ctx.rectangle(-28, 76, 56, 12); ctx.fill()
        elif job == "戰士":
            ctx.set_source_rgb(.48, .49, .48); ctx.rectangle(-shoulder, 54, shoulder * 2, 14); ctx.fill()
            ctx.set_line_width(10); ctx.move_to(58, 72); ctx.line_to(105, -18); ctx.set_source_rgb(.72, .72, .67); ctx.stroke()
        elif job == "法師":
            ctx.set_source_rgb(.20, .19, .42); ctx.move_to(-72, -36); ctx.line_to(0, -126); ctx.line_to(75, -34); ctx.close_path(); ctx.fill()
            ctx.set_source_rgba(.55, .74, 1, .9); ctx.arc(82, 25, 17, 0, math.tau); ctx.fill()
        else:
            ctx.set_source_rgb(.06, .10, .09); ctx.move_to(-75, 35); ctx.line_to(0, -82); ctx.line_to(75, 35); ctx.close_path(); ctx.fill()
            ctx.set_source_rgb(.73, .73, .68); ctx.set_line_width(7); ctx.move_to(-62, 80); ctx.line_to(-96, 12); ctx.stroke()

        # Neck and face.
        ctx.set_source_rgb(*skin); ctx.rectangle(-16, 8, 32, 37); ctx.fill()
        face_w = 48 if female else 55
        ctx.arc(0, -17, face_w, 0, math.tau); ctx.fill()
        if race == "精靈":
            ctx.move_to(-42, -24); ctx.line_to(-92, -44); ctx.line_to(-43, -3); ctx.close_path()
            ctx.move_to(42, -24); ctx.line_to(92, -44); ctx.line_to(43, -3); ctx.close_path(); ctx.fill()
        elif race == "獸人":
            ctx.set_source_rgb(.85, .78, .58)
            ctx.move_to(-30, 8); ctx.line_to(-18, -12); ctx.line_to(-9, 10); ctx.close_path()
            ctx.move_to(30, 8); ctx.line_to(18, -12); ctx.line_to(9, 10); ctx.close_path(); ctx.fill()
        elif race == "矮人":
            ctx.set_source_rgb(.30, .14, .06)
            ctx.move_to(-44, 2); ctx.curve_to(-38, 78, -15, 102, 0, 122)
            ctx.curve_to(15, 102, 38, 78, 44, 2); ctx.curve_to(18, 20, -18, 20, -44, 2); ctx.fill()

        hair = (.20, .08, .04) if race != "精靈" else (.78, .73, .45)
        ctx.set_source_rgb(*hair)
        if female:
            ctx.arc(0, -28, 54, math.pi, math.tau); ctx.rectangle(-53, -28, 18, 80); ctx.rectangle(35, -28, 18, 80); ctx.fill()
        else:
            ctx.arc(0, -35, 55, math.pi, math.tau); ctx.fill()
        ctx.set_source_rgb(.97, .82, .35); ctx.rectangle(-27, -15, 17, 4); ctx.rectangle(10, -15, 17, 4); ctx.fill()

    return texture_from_cairo(300, 300, paint)


def make_monster_portrait_legacy(rank: int, kind: str) -> arcade.Texture:
    """Create a distinct silhouette for each of the five monster ranks."""
    def paint(ctx: cairo.Context, w: int, h: int) -> None:
        colors = ((.24, .66, .36), (.60, .28, .16), (.40, .20, .62),
                  (.66, .10, .10), (.12, .025, .18))
        body = colors[rank - 1]
        glow = cairo.RadialGradient(w / 2, h / 2, 8, w / 2, h / 2, 145)
        glow.add_color_stop_rgba(0, *body, .8); glow.add_color_stop_rgba(1, 0, 0, 0, 0)
        ctx.set_source(glow); ctx.paint(); ctx.translate(w / 2, h / 2)
        scale = (.68, .82, .94, 1.06, 1.18)[rank - 1]
        ctx.scale(scale, scale)
        ctx.set_source_rgb(*body)
        if rank == 1:  # round small monster
            ctx.arc(0, 28, 74, math.pi, math.tau); ctx.rectangle(-74, 28, 148, 58)
            ctx.curve_to(65, 108, 30, 118, 0, 104); ctx.curve_to(-30, 118, -65, 108, -74, 86); ctx.fill()
        elif rank == 2:  # horned small king
            ctx.arc(0, 22, 72, 0, math.tau); ctx.fill()
            ctx.move_to(-55, -20); ctx.line_to(-98, -72); ctx.line_to(-65, 2)
            ctx.move_to(55, -20); ctx.line_to(98, -72); ctx.line_to(65, 2); ctx.fill()
        elif rank == 3:  # armored middle king
            ctx.rectangle(-72, 8, 144, 108); ctx.arc(0, 0, 69, math.pi, math.tau); ctx.fill()
            ctx.set_source_rgb(.52, .48, .57); ctx.rectangle(-82, 24, 164, 20); ctx.fill()
        elif rank == 4:  # winged large king
            ctx.arc(0, 15, 72, 0, math.tau); ctx.fill()
            ctx.move_to(-52, 35); ctx.line_to(-128, -35); ctx.line_to(-110, 70); ctx.line_to(-58, 82); ctx.close_path()
            ctx.move_to(52, 35); ctx.line_to(128, -35); ctx.line_to(110, 70); ctx.line_to(58, 82); ctx.close_path(); ctx.fill()
        else:  # final demon king with crown and four horns
            ctx.arc(0, 17, 76, 0, math.tau); ctx.fill()
            for x, tip_x in ((-58, -115), (-25, -55), (25, 55), (58, 115)):
                ctx.move_to(x - 14, -30); ctx.line_to(tip_x, -105); ctx.line_to(x + 14, -20); ctx.close_path()
            ctx.fill(); ctx.set_source_rgb(.82, .62, .12)
            ctx.move_to(-48, -56); ctx.line_to(-25, -98); ctx.line_to(0, -60)
            ctx.line_to(27, -98); ctx.line_to(48, -56); ctx.close_path(); ctx.fill()
        # Type-specific mark: heart, blade, or shield.
        if kind == "血量型":
            ctx.set_source_rgb(.95, .26, .30); ctx.arc(-10, 52, 12, 0, math.tau); ctx.arc(10, 52, 12, 0, math.tau)
            ctx.move_to(-22, 55); ctx.line_to(0, 80); ctx.line_to(22, 55); ctx.fill()
        elif kind == "攻擊型":
            ctx.set_source_rgb(.94, .74, .22); ctx.move_to(-8, 30); ctx.line_to(16, 62); ctx.line_to(5, 64); ctx.line_to(18, 92); ctx.line_to(-17, 55); ctx.line_to(-5, 53); ctx.close_path(); ctx.fill()
        else:
            ctx.set_source_rgb(.45, .70, .82); ctx.move_to(0, 28); ctx.line_to(28, 43); ctx.line_to(22, 76); ctx.line_to(0, 93); ctx.line_to(-22, 76); ctx.line_to(-28, 43); ctx.close_path(); ctx.fill()
        ctx.set_source_rgb(1, .70, .12); ctx.arc(-29, 2, 7, 0, math.tau); ctx.arc(29, 2, 7, 0, math.tau); ctx.fill()

    return texture_from_cairo(300, 300, paint)


def _rounded_path(ctx: cairo.Context, x: float, y: float,
                  width: float, height: float, radius: float) -> None:
    radius = min(radius, width / 2, height / 2)
    ctx.new_sub_path()
    ctx.arc(x + width - radius, y + radius, radius, -math.pi / 2, 0)
    ctx.arc(x + width - radius, y + height - radius, radius, 0, math.pi / 2)
    ctx.arc(x + radius, y + height - radius, radius, math.pi / 2, math.pi)
    ctx.arc(x + radius, y + radius, radius, math.pi, math.pi * 1.5)
    ctx.close_path()


def _star_path(ctx: cairo.Context, x: float, y: float,
               outer: float, inner: float, points: int = 5) -> None:
    for index in range(points * 2):
        angle = -math.pi / 2 + index * math.pi / points
        radius = outer if index % 2 == 0 else inner
        px, py = x + math.cos(angle) * radius, y + math.sin(angle) * radius
        if index == 0:
            ctx.move_to(px, py)
        else:
            ctx.line_to(px, py)
    ctx.close_path()


def _grain(ctx: cairo.Context, width: int, height: int,
           seed: int, amount: int = 260, alpha: float = .035) -> None:
    rng = random.Random(seed)
    for _ in range(amount):
        shade = rng.uniform(.35, 1)
        ctx.set_source_rgba(shade, shade, shade, rng.uniform(alpha * .2, alpha))
        radius = rng.uniform(.25, 1.2)
        ctx.arc(rng.uniform(0, width), rng.uniform(0, height), radius, 0, math.tau)
        ctx.fill()


def _vignette(ctx: cairo.Context, width: int, height: int, strength: float = .72) -> None:
    gradient = cairo.RadialGradient(width / 2, height / 2, width * .12,
                                    width / 2, height / 2, width * .7)
    gradient.add_color_stop_rgba(0, 0, 0, 0, 0)
    gradient.add_color_stop_rgba(.68, 0, 0, 0, .08)
    gradient.add_color_stop_rgba(1, 0, 0, 0, strength)
    ctx.set_source(gradient)
    ctx.paint()


def _glow(ctx: cairo.Context, x: float, y: float, radius: float,
          color: tuple[float, float, float], alpha: float = .75) -> None:
    gradient = cairo.RadialGradient(x, y, 0, x, y, radius)
    gradient.add_color_stop_rgba(0, *color, alpha)
    gradient.add_color_stop_rgba(.35, *color, alpha * .36)
    gradient.add_color_stop_rgba(1, *color, 0)
    ctx.arc(x, y, radius, 0, math.tau)
    ctx.set_source(gradient)
    ctx.fill()


def _rune_ring(ctx: cairo.Context, x: float, y: float, radius: float,
               color: tuple[float, float, float], alpha: float = .45) -> None:
    ctx.save()
    ctx.translate(x, y)
    ctx.set_source_rgba(*color, alpha)
    ctx.set_line_width(2)
    ctx.arc(0, 0, radius, 0, math.tau)
    ctx.stroke()
    ctx.arc(0, 0, radius * .76, 0, math.tau)
    ctx.stroke()
    for index in range(12):
        angle = index * math.tau / 12
        ctx.save()
        ctx.rotate(angle)
        ctx.move_to(radius * .80, 0)
        ctx.line_to(radius * .91, -6)
        ctx.line_to(radius * .96, 0)
        ctx.line_to(radius * .91, 6)
        ctx.close_path()
        ctx.stroke()
        ctx.restore()
    ctx.restore()


def make_background() -> arcade.Texture:
    """Layered dark-fantasy title world with moon, aurora, mist, and castle."""
    def paint(ctx: cairo.Context, w: int, h: int) -> None:
        sky = cairo.LinearGradient(0, 0, 0, h)
        sky.add_color_stop_rgb(0, .008, .018, .045)
        sky.add_color_stop_rgb(.42, .025, .07, .14)
        sky.add_color_stop_rgb(.76, .13, .075, .14)
        sky.add_color_stop_rgb(1, .035, .025, .045)
        ctx.set_source(sky); ctx.paint()

        # Painted aurora ribbons.
        ctx.set_line_cap(cairo.LINE_CAP_ROUND)
        for offset, color, width in ((0, (.12, .55, .55), 46),
                                     (34, (.28, .28, .72), 32),
                                     (-38, (.42, .16, .55), 24)):
            ctx.set_source_rgba(*color, .055)
            ctx.set_line_width(width)
            ctx.move_to(-80, h * .66 + offset)
            ctx.curve_to(w * .20, h * .91 + offset, w * .50, h * .53 + offset,
                         w + 90, h * .78 + offset)
            ctx.stroke()

        # Stars with a handful of bright cross glints.
        rng = random.Random(3407)
        for index in range(190):
            x, y = rng.uniform(0, w), rng.uniform(h * .37, h - 10)
            radius = rng.uniform(.35, 1.35)
            ctx.set_source_rgba(.72, .82, 1, rng.uniform(.25, .88))
            ctx.arc(x, y, radius, 0, math.tau); ctx.fill()
            if index % 31 == 0:
                ctx.set_source_rgba(.87, .91, 1, .62); ctx.set_line_width(.8)
                ctx.move_to(x - 7, y); ctx.line_to(x + 7, y)
                ctx.move_to(x, y - 7); ctx.line_to(x, y + 7); ctx.stroke()

        # Moon glow, rim, and crater detail.
        moon_x, moon_y, moon_r = w * .81, h * .79, 62
        _glow(ctx, moon_x, moon_y, 122, (1, .74, .34), .34)
        moon = cairo.RadialGradient(moon_x - 20, moon_y - 22, 4,
                                    moon_x, moon_y, moon_r)
        moon.add_color_stop_rgb(0, 1, .91, .62)
        moon.add_color_stop_rgb(.72, .87, .68, .39)
        moon.add_color_stop_rgb(1, .42, .28, .25)
        ctx.arc(moon_x, moon_y, moon_r, 0, math.tau)
        ctx.set_source(moon); ctx.fill()
        for cx, cy, cr in ((-19, 8, 10), (18, -17, 7), (25, 20, 12), (-5, -27, 5)):
            ctx.set_source_rgba(.25, .17, .18, .15)
            ctx.arc(moon_x + cx, moon_y + cy, cr, 0, math.tau); ctx.fill()

        # Four mountain layers with atmospheric perspective.
        mountain_layers = (
            (h * .45, (.10, .14, .22), .52, 170),
            (h * .34, (.065, .095, .15), .70, 135),
            (h * .24, (.035, .065, .10), .88, 105),
            (h * .13, (.015, .035, .052), 1, 72),
        )
        for layer, (base, color, alpha, peak) in enumerate(mountain_layers):
            local = random.Random(90 + layer)
            ctx.move_to(0, 0); ctx.line_to(0, base)
            x = 0
            while x < w:
                x2 = min(w, x + local.uniform(90, 170))
                mid = (x + x2) / 2
                ctx.line_to(mid, base + local.uniform(peak * .55, peak))
                ctx.line_to(x2, base + local.uniform(-18, 12))
                x = x2
            ctx.line_to(w, 0); ctx.close_path()
            ctx.set_source_rgba(*color, alpha); ctx.fill()

        # Mist bands between the mountains.
        for y, alpha in ((205, .105), (158, .075), (112, .055)):
            mist = cairo.LinearGradient(0, y - 35, 0, y + 38)
            mist.add_color_stop_rgba(0, .45, .58, .72, 0)
            mist.add_color_stop_rgba(.5, .45, .58, .72, alpha)
            mist.add_color_stop_rgba(1, .45, .58, .72, 0)
            ctx.set_source(mist)
            ctx.move_to(0, y)
            ctx.curve_to(w * .22, y + 34, w * .48, y - 29, w * .70, y + 12)
            ctx.curve_to(w * .84, y + 35, w * .94, y - 14, w, y + 5)
            ctx.line_to(w, y - 55); ctx.line_to(0, y - 55); ctx.close_path(); ctx.fill()

        # Detailed castle silhouette and glowing windows.
        ctx.set_source_rgb(.008, .017, .027)
        ctx.rectangle(820, 146, 180, 116)
        for x, tower_h, tower_w in ((798, 164, 42), (858, 198, 38),
                                    (930, 176, 45), (988, 214, 44)):
            ctx.rectangle(x, 146, tower_w, tower_h)
            ctx.move_to(x - 5, 146 + tower_h)
            ctx.line_to(x + tower_w / 2, 180 + tower_h)
            ctx.line_to(x + tower_w + 5, 146 + tower_h)
            ctx.close_path()
        ctx.fill()
        ctx.set_source_rgba(.95, .42, .09, .82)
        for x, y in ((817, 226), (870, 258), (947, 238), (1004, 278),
                     (848, 184), (911, 196), (970, 188)):
            _rounded_path(ctx, x, y, 7, 14, 3); ctx.fill()
            _glow(ctx, x + 3.5, y + 7, 20, (1, .32, .06), .16)

        # Foreground pines and cliff.
        ctx.set_source_rgb(.006, .015, .021)
        for x, height in ((35, 125), (84, 94), (1090, 135), (1138, 108)):
            ctx.rectangle(x - 4, 0, 8, height * .72)
            for level in range(4):
                y = height * (.22 + level * .15)
                spread = 38 - level * 6
                ctx.move_to(x, y + 55); ctx.line_to(x - spread, y)
                ctx.line_to(x + spread, y); ctx.close_path()
            ctx.fill()
        _grain(ctx, w, h, 8001, 330, .028)
        _vignette(ctx, w, h, .66)

    return texture_from_cairo(SCREEN_WIDTH, SCREEN_HEIGHT, paint)


def make_activity_background(kind: str, variant: int = 0) -> arcade.Texture:
    """Richly illustrated encounter backdrops with scene-specific storytelling."""
    def paint(ctx: cairo.Context, w: int, h: int) -> None:
        if kind == "battle":
            sky = cairo.LinearGradient(0, 0, 0, h)
            sky.add_color_stop_rgb(0, .025, .008, .025)
            sky.add_color_stop_rgb(.48, .22, .025, .035)
            sky.add_color_stop_rgb(1, .035, .018, .022)
            ctx.set_source(sky); ctx.paint()
            _glow(ctx, w * .5, h * .77, 165, (.95, .08, .035), .34)
            ctx.set_source_rgb(.045, .012, .02)
            ctx.arc(w * .5, h * .77, 82, 0, math.tau); ctx.fill()
            ctx.set_source_rgba(1, .35, .08, .52); ctx.set_line_width(3)
            ctx.arc(w * .5, h * .77, 86, 0, math.tau); ctx.stroke()
            # Jagged obsidian canyon.
            for side in (-1, 1):
                ctx.set_source_rgb(.025, .018, .024)
                ctx.move_to(w / 2, 98)
                points = ((280, 160), (325, 235), (245, 312), (360, 405), (300, h))
                for px, py in points:
                    ctx.line_to(w / 2 + side * px, py)
                ctx.line_to(w / 2 + side * w / 2, 0); ctx.close_path(); ctx.fill()
            # Ruined pillars and chains.
            for x in (68, 126, w - 126, w - 68):
                ctx.set_source_rgb(.10, .065, .072); ctx.rectangle(x - 13, 100, 26, 275); ctx.fill()
                ctx.set_source_rgb(.19, .10, .075); ctx.rectangle(x - 20, 365, 40, 18); ctx.fill()
                ctx.set_source_rgba(.65, .22, .08, .32); ctx.rectangle(x - 5, 122, 10, 225); ctx.fill()
            # Runic arena disc.
            arena = cairo.RadialGradient(w / 2, 122, 10, w / 2, 122, 210)
            arena.add_color_stop_rgb(0, .31, .105, .045)
            arena.add_color_stop_rgb(.7, .105, .045, .035)
            arena.add_color_stop_rgb(1, .018, .018, .025)
            ctx.set_source(arena); ctx.arc(w / 2, 122, 210, math.pi, math.tau); ctx.fill()
            _rune_ring(ctx, w / 2, 116, 145, (1, .27, .07), .27)
            rng = random.Random(77)
            for _ in range(60):
                x, y = rng.uniform(30, w - 30), rng.uniform(80, h - 30)
                ctx.set_source_rgba(1, rng.uniform(.18, .48), .03, rng.uniform(.2, .7))
                ctx.arc(x, y, rng.uniform(.5, 2.2), 0, math.tau); ctx.fill()
        elif kind == "shop":
            wall = cairo.LinearGradient(0, 0, 0, h)
            wall.add_color_stop_rgb(0, .025, .018, .038)
            wall.add_color_stop_rgb(.55, .12, .045, .055)
            wall.add_color_stop_rgb(1, .045, .022, .028)
            ctx.set_source(wall); ctx.paint()
            # Draped velvet canopy with gold trim.
            ctx.set_source_rgb(.26, .025, .07)
            ctx.move_to(0, h); ctx.line_to(w, h); ctx.line_to(w, h * .78)
            for index in range(8):
                x = w - index * w / 7
                ctx.curve_to(x - 35, h * .70, x - 70, h * .87, x - w / 7, h * .78)
            ctx.close_path(); ctx.fill()
            ctx.set_source_rgb(.67, .40, .10); ctx.set_line_width(5)
            ctx.move_to(0, h * .78); ctx.curve_to(w * .25, h * .72, w * .75, h * .84, w, h * .78); ctx.stroke()
            # Cabinets with carved shelves.
            for shelf_x in (32, 510):
                wood = cairo.LinearGradient(shelf_x, 0, shelf_x + 250, 0)
                wood.add_color_stop_rgb(0, .08, .034, .025)
                wood.add_color_stop_rgb(.5, .25, .105, .045)
                wood.add_color_stop_rgb(1, .06, .025, .022)
                ctx.set_source(wood); _rounded_path(ctx, shelf_x, 92, 258, 335, 12); ctx.fill()
                ctx.set_source_rgb(.39, .20, .07)
                for y in (175, 265, 355): ctx.rectangle(shelf_x + 12, y, 234, 12)
                ctx.fill()
            # Jewel-like bottles with glass highlights.
            bottle_colors = ((.12, .82, .52), (.76, .08, .32), (.13, .49, .92),
                             (.88, .62, .08), (.55, .13, .80))
            for cabinet in (42, 520):
                for row, y in enumerate((190, 280, 370)):
                    for col in range(4):
                        x = cabinet + 18 + col * 54
                        color = bottle_colors[(col + row * 2) % len(bottle_colors)]
                        _glow(ctx, x + 17, y + 18, 28, color, .20)
                        glass = cairo.LinearGradient(x, y, x + 34, y + 45)
                        glass.add_color_stop_rgba(0, min(1, color[0] + .3), min(1, color[1] + .3), min(1, color[2] + .3), .95)
                        glass.add_color_stop_rgba(1, *color, .72)
                        ctx.set_source(glass); _rounded_path(ctx, x, y, 34, 43, 9); ctx.fill()
                        ctx.set_source_rgba(1, 1, 1, .42); _rounded_path(ctx, x + 6, y + 5, 5, 25, 3); ctx.fill()
                        ctx.set_source_rgb(.55, .38, .20); ctx.rectangle(x + 11, y + 43, 12, 10); ctx.fill()
            # Merchant silhouette, counter, lanterns, rug.
            _glow(ctx, w / 2, 325, 125, (1, .38, .07), .16)
            ctx.set_source_rgb(.018, .012, .021); ctx.arc(w / 2, 328, 48, 0, math.tau); ctx.fill()
            ctx.move_to(w / 2 - 78, 112); ctx.line_to(w / 2 - 48, 300)
            ctx.line_to(w / 2 + 48, 300); ctx.line_to(w / 2 + 78, 112); ctx.close_path(); ctx.fill()
            counter = cairo.LinearGradient(0, 70, 0, 130)
            counter.add_color_stop_rgb(0, .37, .16, .055); counter.add_color_stop_rgb(1, .09, .035, .026)
            ctx.set_source(counter); _rounded_path(ctx, 210, 58, 380, 92, 10); ctx.fill()
            ctx.set_source_rgb(.72, .42, .10); ctx.rectangle(195, 139, 410, 12); ctx.fill()
            for x in (115, w - 115):
                _glow(ctx, x, 455, 68, (1, .48, .08), .40)
                ctx.set_source_rgb(.83, .46, .10); _rounded_path(ctx, x - 18, 425, 36, 58, 8); ctx.fill()
                ctx.set_source_rgba(1, .82, .36, .85); _rounded_path(ctx, x - 10, 435, 20, 37, 6); ctx.fill()
        else:
            # Event backgrounds share a moonlit forest, then gain a unique centerpiece.
            palettes = (((.012, .040, .055), (.045, .12, .11)),
                        ((.012, .035, .09), (.08, .11, .24)),
                        ((.012, .055, .045), (.07, .16, .10)),
                        ((.07, .030, .012), (.18, .095, .025)))
            top, bottom = palettes[max(0, min(3, variant - 1))]
            gradient = cairo.LinearGradient(0, 0, 0, h)
            gradient.add_color_stop_rgb(0, *top); gradient.add_color_stop_rgb(1, *bottom)
            ctx.set_source(gradient); ctx.paint()
            # Deep forest layers.
            rng = random.Random(340 + variant)
            for depth in range(3):
                shade = .02 + depth * .012
                ctx.set_source_rgba(shade, shade * 1.6, shade * 1.4, .65 + depth * .1)
                for x in range(-25 + depth * 20, w + 40, 74 - depth * 7):
                    trunk = 15 + depth * 8
                    ctx.rectangle(x, 72, trunk, 330 + rng.uniform(-35, 55))
                    ctx.arc(x + trunk / 2, 410 + rng.uniform(-25, 30), 52 + depth * 12, 0, math.tau)
                ctx.fill()
            path = cairo.LinearGradient(0, 0, 0, h)
            path.add_color_stop_rgb(0, .22, .16, .09); path.add_color_stop_rgb(1, .055, .05, .045)
            ctx.set_source(path); ctx.move_to(260, 0); ctx.curve_to(300, 180, 350, 280, 378, h)
            ctx.line_to(500, h); ctx.curve_to(455, 280, 520, 165, 580, 0); ctx.close_path(); ctx.fill()
            # Fireflies.
            for _ in range(45):
                x, y = rng.uniform(25, w - 25), rng.uniform(85, h - 35)
                _glow(ctx, x, y, rng.uniform(8, 16), (.72, 1, .45), .16)
                ctx.set_source_rgba(.82, 1, .48, .7); ctx.arc(x, y, 1.1, 0, math.tau); ctx.fill()
            if variant == 1:
                # Hooded travelling merchant and wagon.
                _glow(ctx, 418, 300, 118, (1, .44, .10), .24)
                ctx.set_source_rgb(.12, .045, .025); _rounded_path(ctx, 250, 145, 285, 120, 18); ctx.fill()
                ctx.set_source_rgb(.36, .13, .045); ctx.arc(290, 142, 45, 0, math.tau); ctx.arc(500, 142, 45, 0, math.tau); ctx.fill()
                ctx.set_source_rgb(.025, .018, .032); ctx.arc(420, 332, 44, 0, math.tau); ctx.fill()
                ctx.move_to(340, 150); ctx.line_to(375, 315); ctx.line_to(465, 315); ctx.line_to(505, 150); ctx.close_path(); ctx.fill()
                ctx.set_source_rgba(1, .65, .20, .78); ctx.arc(405, 330, 4, 0, math.tau); ctx.arc(435, 330, 4, 0, math.tau); ctx.fill()
            elif variant == 2:
                # Celestial breach, beam, and levitating rune stones.
                _glow(ctx, 420, 390, 190, (.30, .65, 1), .28)
                beam = cairo.LinearGradient(420, h, 420, 0)
                beam.add_color_stop_rgba(0, .45, .75, 1, 0)
                beam.add_color_stop_rgba(.55, .45, .75, 1, .20)
                beam.add_color_stop_rgba(1, .75, .90, 1, .68)
                ctx.set_source(beam); ctx.move_to(280, 0); ctx.line_to(355, h)
                ctx.line_to(500, h); ctx.line_to(555, 0); ctx.close_path(); ctx.fill()
                _rune_ring(ctx, 425, 205, 105, (.55, .82, 1), .53)
                for index in range(7):
                    angle = index * math.tau / 7
                    x, y = 425 + math.cos(angle) * 145, 205 + math.sin(angle) * 90
                    ctx.save(); ctx.translate(x, y); ctx.rotate(angle)
                    ctx.set_source_rgb(.22, .30, .42); ctx.move_to(-12, -18); ctx.line_to(13, -12)
                    ctx.line_to(9, 20); ctx.line_to(-15, 13); ctx.close_path(); ctx.fill(); ctx.restore()
            elif variant == 3:
                # Ancient shrine with luminous potion.
                ctx.set_source_rgb(.075, .10, .085); ctx.rectangle(250, 95, 350, 42); ctx.fill()
                for x in (280, 535):
                    ctx.set_source_rgb(.11, .13, .11); ctx.rectangle(x, 120, 38, 245); ctx.fill()
                    ctx.set_source_rgb(.18, .16, .11); ctx.rectangle(x - 16, 350, 70, 20); ctx.fill()
                _glow(ctx, 425, 210, 135, (.12, 1, .56), .40)
                liquid = cairo.LinearGradient(390, 150, 460, 260)
                liquid.add_color_stop_rgb(0, .45, 1, .72); liquid.add_color_stop_rgb(1, .02, .43, .22)
                ctx.set_source(liquid); _rounded_path(ctx, 385, 150, 80, 108, 25); ctx.fill()
                ctx.set_source_rgba(1, 1, 1, .45); _rounded_path(ctx, 402, 164, 10, 67, 5); ctx.fill()
                ctx.set_source_rgb(.48, .31, .14); ctx.rectangle(408, 255, 34, 26); ctx.fill()
                _rune_ring(ctx, 425, 205, 92, (.25, 1, .55), .32)
            else:
                # Treasure grotto with coins, gems, and open chest.
                _glow(ctx, 425, 210, 170, (1, .48, .06), .36)
                rng2 = random.Random(904)
                for _ in range(90):
                    x, y = rng2.gauss(425, 120), rng2.uniform(75, 175)
                    ctx.set_source_rgb(.78 + rng2.random() * .18, .43 + rng2.random() * .2, .04)
                    ctx.arc(x, y, rng2.uniform(2, 5), 0, math.tau); ctx.fill()
                wood = cairo.LinearGradient(310, 0, 540, 0)
                wood.add_color_stop_rgb(0, .20, .065, .025); wood.add_color_stop_rgb(.5, .55, .20, .045); wood.add_color_stop_rgb(1, .16, .05, .022)
                ctx.set_source(wood); _rounded_path(ctx, 300, 125, 250, 135, 16); ctx.fill()
                ctx.set_source_rgb(.11, .035, .025); ctx.rectangle(310, 207, 230, 20); ctx.fill()
                ctx.set_source_rgb(.78, .52, .12); ctx.set_line_width(8); _rounded_path(ctx, 300, 125, 250, 135, 16); ctx.stroke()
                ctx.set_source_rgb(.95, .72, .20); _rounded_path(ctx, 412, 168, 28, 42, 7); ctx.fill()
                for x, y, color in ((350, 280, (.12, .65, 1)), (482, 275, (.85, .08, .28)), (420, 292, (.42, .92, .30))):
                    _glow(ctx, x, y, 28, color, .27); _star_path(ctx, x, y, 15, 8, 4); ctx.set_source_rgb(*color); ctx.fill()
        _grain(ctx, w, h, 5000 + variant + len(kind), 220, .032)
        _vignette(ctx, w, h, .72)

    return texture_from_cairo(800, 565, paint)


def make_player_portrait(sex: str, race: str, job: str) -> arcade.Texture:
    """Detailed painterly bust assembled from race, class, and gender traits."""
    def paint(ctx: cairo.Context, w: int, h: int) -> None:
        race_skin = {"獸人": (.30, .52, .25), "人類": (.76, .54, .39),
                     "矮人": (.65, .43, .29), "精靈": (.78, .64, .48)}
        class_color = {"戰士": (.56, .075, .065), "法師": (.19, .17, .58),
                       "聖騎士": (.68, .49, .10), "盜賊": (.075, .25, .20)}
        skin, accent = race_skin[race], class_color[job]
        female = sex == "女性"
        # Medallion backdrop and magical halo.
        backdrop = cairo.RadialGradient(150, 155, 8, 150, 155, 145)
        backdrop.add_color_stop_rgba(0, min(1, accent[0] + .18), min(1, accent[1] + .15), min(1, accent[2] + .15), .62)
        backdrop.add_color_stop_rgba(.64, *accent, .28)
        backdrop.add_color_stop_rgba(1, 0, 0, 0, 0)
        ctx.set_source(backdrop); ctx.paint()
        _rune_ring(ctx, 150, 155, 123, (min(1, accent[0] + .4), min(1, accent[1] + .35), min(1, accent[2] + .25)), .20)
        ctx.translate(150, 150)
        ctx.set_line_join(cairo.LINE_JOIN_ROUND)
        ctx.set_line_cap(cairo.LINE_CAP_ROUND)

        # Back cloak with deep shadow.
        cloak = cairo.LinearGradient(-100, 20, 100, 120)
        cloak.add_color_stop_rgb(0, accent[0] * .28, accent[1] * .28, accent[2] * .28)
        cloak.add_color_stop_rgb(.48, *accent)
        cloak.add_color_stop_rgb(1, accent[0] * .2, accent[1] * .2, accent[2] * .2)
        cloak_half = 92 if female else 108
        upper_half = 37 if female else 46
        ctx.set_source(cloak); ctx.move_to(-cloak_half, 130)
        ctx.curve_to(-cloak_half, 52, -68 if female else -78, 18, -upper_half, 10)
        ctx.line_to(upper_half, 10)
        ctx.curve_to(68 if female else 78, 18, cloak_half, 52, cloak_half, 130)
        ctx.close_path(); ctx.fill()
        ctx.set_source_rgba(0, 0, 0, .25); ctx.set_line_width(4)
        ctx.move_to(-cloak_half, 130); ctx.curve_to(-72, 87, -47, 74, 0, 82 if female else 76)
        ctx.curve_to(47, 74, 72, 87, cloak_half, 130); ctx.stroke()

        # Class equipment behind the head.
        if job == "戰士":
            ctx.save(); ctx.rotate(-.46); ctx.set_source_rgb(.72, .75, .75)
            ctx.rectangle(54, -112, 13, 225); ctx.fill(); ctx.set_source_rgb(.34, .20, .08)
            ctx.rectangle(42, 76, 38, 17); ctx.fill(); ctx.restore()
        elif job == "法師":
            ctx.set_source_rgb(.075, .055, .25); ctx.move_to(-86, -62); ctx.line_to(5, -148)
            ctx.line_to(96, -55); ctx.curve_to(35, -74, -30, -70, -86, -62); ctx.fill()
            _glow(ctx, 88, 16, 42, (.35, .62, 1), .52)
            ctx.set_source_rgb(.48, .72, 1); ctx.arc(88, 16, 12, 0, math.tau); ctx.fill()
            ctx.set_source_rgb(.26, .15, .07); ctx.set_line_width(9); ctx.move_to(88, 28); ctx.line_to(100, 128); ctx.stroke()
        elif job == "聖騎士":
            # Shield and sunburst.
            ctx.set_source_rgb(.62, .65, .62); ctx.move_to(-104, 20); ctx.line_to(-48, 4)
            ctx.line_to(-46, 100); ctx.line_to(-76, 126); ctx.line_to(-105, 100); ctx.close_path(); ctx.fill()
            ctx.set_source_rgb(.93, .66, .12); _star_path(ctx, -76, 64, 25, 10, 8); ctx.fill()
        else:
            for side in (-1, 1):
                ctx.save(); ctx.rotate(side * .55); ctx.set_source_rgb(.72, .75, .72)
                ctx.move_to(side * 58, -30); ctx.line_to(side * 81, 90); ctx.line_to(side * 66, 76); ctx.close_path(); ctx.fill(); ctx.restore()

        # Shoulders / armor plates.
        shoulder_y = 47
        if job in ("戰士", "聖騎士"):
            metal = cairo.LinearGradient(-105, 20, 105, 72)
            if job == "聖騎士":
                metal.add_color_stop_rgb(0, .30, .30, .31); metal.add_color_stop_rgb(.5, .88, .77, .45); metal.add_color_stop_rgb(1, .22, .22, .25)
            else:
                metal.add_color_stop_rgb(0, .16, .18, .20); metal.add_color_stop_rgb(.5, .64, .68, .69); metal.add_color_stop_rgb(1, .12, .13, .15)
            shoulder_x = 63 if female else 72
            shoulder_r = 30 if female else 37
            ctx.set_source(metal)
            for side in (-1, 1):
                ctx.arc(side * shoulder_x, shoulder_y, shoulder_r, math.pi, math.tau)
                ctx.rectangle(side * shoulder_x - shoulder_r, shoulder_y,
                              shoulder_r * 2, 24 if female else 28)
            ctx.fill(); ctx.set_source_rgba(1, 1, 1, .28); ctx.set_line_width(3)
            highlight_r = shoulder_r - 7
            ctx.arc(-shoulder_x, shoulder_y, highlight_r, math.pi + .3, math.tau - .3)
            ctx.arc(shoulder_x, shoulder_y, highlight_r, math.pi + .3, math.tau - .3); ctx.stroke()

        # Neck and face with directional skin shading.
        neck_w = 28 if female else 40
        ctx.set_source_rgb(skin[0] * .68, skin[1] * .68, skin[2] * .68)
        _rounded_path(ctx, -neck_w / 2, -1, neck_w, 54, 10 if female else 13); ctx.fill()
        face_w, face_h = ((42, 59) if female else (51, 60))
        face = cairo.RadialGradient(-15, -38, 5, 5, -18, 72)
        face.add_color_stop_rgb(0, min(1, skin[0] + .20), min(1, skin[1] + .18), min(1, skin[2] + .14))
        face.add_color_stop_rgb(.62, *skin)
        face.add_color_stop_rgb(1, skin[0] * .54, skin[1] * .50, skin[2] * .46)
        ctx.set_source(face); ctx.save(); ctx.scale(1, face_h / face_w); ctx.arc(0, -22 * face_w / face_h, face_w, 0, math.tau); ctx.fill(); ctx.restore()
        if female:
            # Softer tapered jaw and cheek light.
            ctx.set_source_rgba(1, .48, .44, .13)
            ellipse_y = -1
            ctx.save(); ctx.translate(-25, ellipse_y); ctx.scale(13, 7); ctx.arc(0, 0, 1, 0, math.tau); ctx.restore(); ctx.fill()
            ctx.save(); ctx.translate(25, ellipse_y); ctx.scale(13, 7); ctx.arc(0, 0, 1, 0, math.tau); ctx.restore(); ctx.fill()
        else:
            # Squared jaw shadow and stronger cheek planes.
            ctx.set_source_rgba(.09, .035, .025, .16)
            ctx.move_to(-43, -2); ctx.line_to(-31, 25); ctx.line_to(-17, 35)
            ctx.line_to(17, 35); ctx.line_to(31, 25); ctx.line_to(43, -2)
            ctx.curve_to(27, 25, -27, 25, -43, -2); ctx.fill()

        # Race silhouette details.
        if race == "精靈":
            ctx.set_source_rgb(*skin)
            for side in (-1, 1):
                ctx.move_to(side * 38, -33); ctx.line_to(side * 92, -58)
                ctx.line_to(side * 43, -9); ctx.close_path()
            ctx.fill(); ctx.set_source_rgba(.5, .16, .13, .34); ctx.set_line_width(3)
            ctx.move_to(-45, -31); ctx.line_to(-77, -47); ctx.move_to(45, -31); ctx.line_to(77, -47); ctx.stroke()
        elif race == "獸人":
            ctx.set_source_rgb(.92, .82, .58)
            for side in (-1, 1):
                ctx.move_to(side * 27, 2); ctx.line_to(side * 18, -21); ctx.line_to(side * 8, 5); ctx.close_path()
            ctx.fill(); ctx.set_source_rgba(.08, .20, .055, .35); ctx.rectangle(-42, -4, 84, 16); ctx.fill()
        elif race == "矮人":
            beard = cairo.LinearGradient(0, -2, 0, 92)
            beard.add_color_stop_rgb(0, .37, .15, .045); beard.add_color_stop_rgb(1, .10, .035, .018)
            if female:
                # Dwarven women wear paired forge-braids instead of the broad beard.
                ctx.set_source(beard); ctx.set_line_width(13)
                for side in (-1, 1):
                    ctx.move_to(side * 36, -1); ctx.curve_to(side * 49, 34, side * 42, 72, side * 52, 101)
                ctx.stroke()
                ctx.set_source_rgb(.82, .58, .16)
                for side in (-1, 1):
                    for y in (32, 55, 78, 101):
                        ctx.arc(side * (42 + (y / 100) * 8), y, 5, 0, math.tau)
                ctx.fill()
            else:
                ctx.set_source(beard); ctx.move_to(-48, -2); ctx.curve_to(-46, 62, -25, 85, 0, 111)
                ctx.curve_to(25, 85, 46, 62, 48, -2); ctx.curve_to(18, 15, -18, 15, -48, -2); ctx.fill()
                ctx.set_source_rgba(.75, .42, .12, .45); ctx.set_line_width(3)
                for x in (-25, -10, 10, 25): ctx.move_to(x, 15); ctx.curve_to(x - 8, 45, x + 7, 72, x, 95)
                ctx.stroke()

        # Hair / hood and facial detail.
        hair = (.16, .045, .022) if race != "精靈" else (.74, .66, .36)
        if job == "盜賊":
            ctx.set_source_rgb(.025, .075, .065); ctx.move_to(-62, -18); ctx.curve_to(-48, -102, 48, -102, 62, -18)
            ctx.line_to(43, -2); ctx.curve_to(27, -52, -27, -52, -43, -2); ctx.close_path(); ctx.fill()
        else:
            ctx.set_source_rgb(*hair)
            ctx.arc(0, -39, face_w + 3, math.pi, math.tau); ctx.fill()
            if female:
                # Long side locks, tapered fringe, and two ornamented braids.
                ctx.move_to(-face_w, -34); ctx.curve_to(-64, 18, -51, 62, -39, 88)
                ctx.line_to(-24, 18); ctx.move_to(face_w, -34); ctx.curve_to(64, 18, 51, 62, 39, 88)
                ctx.line_to(24, 18); ctx.fill()
                ctx.set_source_rgb(*hair); ctx.set_line_width(9)
                for side in (-1, 1):
                    ctx.move_to(side * 40, 8); ctx.curve_to(side * 54, 35, side * 43, 70, side * 50, 103)
                ctx.stroke()
                ctx.set_source_rgb(.88, .64, .16)
                for side in (-1, 1):
                    for y in (35, 58, 81, 102):
                        ctx.arc(side * (46 + (y % 2) * .03), y, 3.5, 0, math.tau)
                ctx.fill()
                ctx.set_source_rgb(*hair)
                ctx.move_to(-32, -66); ctx.curve_to(-19, -43, -7, -35, 0, -18)
                ctx.curve_to(7, -35, 19, -43, 32, -66); ctx.line_to(0, -82); ctx.close_path(); ctx.fill()
            else:
                # Short angular fringe and sideburns emphasize a broader face.
                ctx.move_to(-face_w - 1, -38); ctx.line_to(-38, -8); ctx.line_to(-29, -32)
                ctx.line_to(-15, -9); ctx.line_to(0, -35); ctx.line_to(17, -10)
                ctx.line_to(31, -34); ctx.line_to(39, -8); ctx.line_to(face_w + 1, -38)
                ctx.close_path(); ctx.fill()
                ctx.rectangle(-face_w - 1, -34, 9, 45); ctx.rectangle(face_w - 8, -34, 9, 45); ctx.fill()
        eye_color = (.95, .74, .20) if race == "獸人" else (.35, .85, .92) if race == "精靈" else (.16, .10, .07)
        ctx.set_source_rgba(.08, .04, .035, .74)
        if female:
            ctx.set_line_width(2.4)
            ctx.move_to(-31, -25); ctx.curve_to(-23, -30, -13, -29, -7, -24)
            ctx.move_to(7, -24); ctx.curve_to(13, -29, 23, -30, 31, -25); ctx.stroke()
            # Eyelashes and a small star-metal circlet make the silhouette readable at distance.
            ctx.set_line_width(1.8)
            for side in (-1, 1):
                ctx.move_to(side * 29, -25); ctx.line_to(side * 35, -30)
                ctx.move_to(side * 27, -27); ctx.line_to(side * 31, -34)
            ctx.stroke()
            ctx.set_source_rgb(*eye_color); ctx.arc(-19, -23, 4.6, 0, math.tau); ctx.arc(19, -23, 4.6, 0, math.tau); ctx.fill()
            ctx.set_source_rgb(.91, .68, .18); _star_path(ctx, 0, -70, 8, 3, 4); ctx.fill()
        else:
            ctx.set_line_width(4.8)
            ctx.move_to(-33, -27); ctx.line_to(-8, -22)
            ctx.move_to(8, -22); ctx.line_to(33, -27); ctx.stroke()
            ctx.set_source_rgb(*eye_color); ctx.arc(-20, -22, 3.8, 0, math.tau); ctx.arc(20, -22, 3.8, 0, math.tau); ctx.fill()
            if race != "矮人":
                ctx.set_source_rgba(.08, .035, .025, .22)
                for x in (-27, -18, -8, 8, 18, 27):
                    ctx.arc(x, 14 + abs(x) * .12, 1.5, 0, math.tau)
                ctx.fill()
        ctx.set_source_rgba(.20, .06, .035, .48); ctx.set_line_width(2.5); ctx.move_to(0, -19); ctx.line_to(-4, -2); ctx.line_to(3, 0); ctx.stroke()
        if female:
            ctx.set_source_rgba(.56, .08, .12, .72); ctx.set_line_width(2.8)
            ctx.move_to(-13, 10); ctx.curve_to(-5, 15, 5, 15, 13, 10)
            ctx.curve_to(5, 20, -5, 20, -13, 10); ctx.stroke()
        else:
            ctx.move_to(-16, 9); ctx.curve_to(-6, 13, 6, 13, 16, 9); ctx.stroke()
        # Class emblem on the chest.
        emblem_color = (.95, .72, .18)
        ctx.set_source_rgb(*emblem_color)
        if job == "戰士":
            ctx.move_to(-7, 70); ctx.line_to(8, 98); ctx.line_to(2, 99); ctx.line_to(11, 119)
            ctx.line_to(-13, 94); ctx.line_to(-5, 92); ctx.close_path(); ctx.fill()
        elif job == "法師":
            _star_path(ctx, 0, 91, 17, 7, 6); ctx.fill()
        elif job == "聖騎士":
            ctx.rectangle(-6, 70, 12, 43); ctx.rectangle(-20, 83, 40, 10); ctx.fill()
        else:
            ctx.arc(0, 91, 17, math.pi * .1, math.pi * 1.3); ctx.set_line_width(5); ctx.stroke()
        ctx.translate(-150, -150)
        _grain(ctx, w, h, hash((sex, race, job)) & 0xFFFF, 120, .028)

    return texture_from_cairo(300, 300, paint)


def make_monster_portrait_legacy(rank: int, kind: str) -> arcade.Texture:
    """Five increasingly elaborate monster silhouettes with attribute sigils."""
    def paint(ctx: cairo.Context, w: int, h: int) -> None:
        rank_colors = ((.12, .72, .38), (.62, .24, .08), (.37, .18, .66),
                       (.68, .055, .055), (.12, .018, .19))
        body = rank_colors[rank - 1]
        aura_color = {"血量型": (.94, .12, .24), "攻擊型": (1, .48, .06),
                      "防禦型": (.16, .60, 1)}[kind]
        _glow(ctx, 150, 158, 145, aura_color, .22 + rank * .025)
        _rune_ring(ctx, 150, 158, 126, aura_color, .16 + rank * .025)
        ctx.translate(150, 150)
        ctx.set_line_join(cairo.LINE_JOIN_ROUND)
        ctx.set_line_cap(cairo.LINE_CAP_ROUND)
        scale = (.74, .82, .91, 1.00, 1.08)[rank - 1]
        ctx.scale(scale, scale)
        outline = (body[0] * .28, body[1] * .24, body[2] * .28)

        if rank == 1:
            # Translucent slime with bubbles and glossy rim.
            slime = cairo.RadialGradient(-25, 18, 4, 0, 35, 105)
            slime.add_color_stop_rgba(0, min(1, body[0] + .35), min(1, body[1] + .25), min(1, body[2] + .30), .94)
            slime.add_color_stop_rgba(.68, *body, .90); slime.add_color_stop_rgba(1, *outline, .96)
            ctx.set_source(slime); ctx.move_to(-90, 92); ctx.curve_to(-105, 20, -68, -76, 0, -88)
            ctx.curve_to(68, -76, 105, 20, 90, 92); ctx.curve_to(54, 115, -54, 115, -90, 92); ctx.fill()
            ctx.set_source_rgba(1, 1, 1, .25); ctx.arc(-38, -35, 17, 0, math.tau); ctx.fill()
            for x, y, r in ((45, 40, 8), (-52, 55, 6), (23, 73, 5)):
                ctx.set_source_rgba(.75, 1, .86, .24); ctx.arc(x, y, r, 0, math.tau); ctx.fill()
        elif rank == 2:
            # Goblin king: broad ears, crooked horns, fur mantle.
            body_grad = cairo.RadialGradient(-20, -30, 5, 0, 10, 110)
            body_grad.add_color_stop_rgb(0, min(1, body[0] + .25), min(1, body[1] + .18), min(1, body[2] + .10))
            body_grad.add_color_stop_rgb(1, *outline)
            ctx.set_source(body_grad); ctx.arc(0, 4, 72, 0, math.tau); ctx.fill()
            ctx.set_source_rgb(*body)
            ctx.move_to(-58, -16); ctx.line_to(-112, -42); ctx.line_to(-66, 15)
            ctx.move_to(58, -16); ctx.line_to(112, -42); ctx.line_to(66, 15); ctx.fill()
            ctx.set_source_rgb(.14, .075, .035)
            ctx.move_to(-75, 58); ctx.curve_to(-38, 34, 38, 34, 75, 58); ctx.line_to(92, 116); ctx.line_to(-92, 116); ctx.close_path(); ctx.fill()
            ctx.set_source_rgb(.83, .68, .31)
            ctx.move_to(-48, -58); ctx.line_to(-27, -102); ctx.line_to(-8, -61)
            ctx.line_to(12, -108); ctx.line_to(28, -60); ctx.line_to(50, -95); ctx.line_to(48, -48); ctx.close_path(); ctx.fill()
        elif rank == 3:
            # Armored ogre king with riveted mask.
            ctx.set_source_rgb(*body); ctx.arc(0, 4, 78, 0, math.tau); ctx.rectangle(-82, 34, 164, 88); ctx.fill()
            metal = cairo.LinearGradient(-80, -60, 80, 50)
            metal.add_color_stop_rgb(0, .12, .13, .18); metal.add_color_stop_rgb(.48, .58, .50, .69); metal.add_color_stop_rgb(1, .10, .08, .15)
            ctx.set_source(metal); ctx.move_to(-74, -38); ctx.line_to(-46, -78); ctx.line_to(46, -78)
            ctx.line_to(74, -38); ctx.line_to(58, 42); ctx.line_to(-58, 42); ctx.close_path(); ctx.fill()
            ctx.set_source_rgb(.78, .63, .24)
            for x, y in ((-54, -33), (54, -33), (-45, 24), (45, 24)):
                ctx.arc(x, y, 5, 0, math.tau)
            ctx.fill(); ctx.set_source_rgb(.025, .02, .04); ctx.rectangle(-47, -25, 94, 13); ctx.fill()
            ctx.set_source_rgb(.25, .21, .32); ctx.arc(-78, 63, 35, 0, math.tau); ctx.arc(78, 63, 35, 0, math.tau); ctx.fill()
        elif rank == 4:
            # Winged dragon king.
            wing = cairo.LinearGradient(0, -40, 0, 100)
            wing.add_color_stop_rgb(0, min(1, body[0] + .18), body[1], body[2])
            wing.add_color_stop_rgb(1, *outline)
            ctx.set_source(wing)
            ctx.move_to(-48, 15); ctx.line_to(-137, -70); ctx.line_to(-115, 8); ctx.line_to(-140, 70); ctx.line_to(-58, 90); ctx.close_path()
            ctx.move_to(48, 15); ctx.line_to(137, -70); ctx.line_to(115, 8); ctx.line_to(140, 70); ctx.line_to(58, 90); ctx.close_path(); ctx.fill()
            ctx.set_source_rgb(*body); ctx.arc(0, 4, 70, 0, math.tau); ctx.fill()
            ctx.set_source_rgb(.78, .62, .34)
            for side in (-1, 1):
                ctx.move_to(side * 45, -48); ctx.line_to(side * 92, -112); ctx.line_to(side * 65, -27); ctx.close_path()
            ctx.fill(); ctx.set_source_rgba(.95, .66, .18, .60); ctx.set_line_width(3)
            for side in (-1, 1):
                ctx.move_to(side * 55, 30); ctx.line_to(side * 125, -45); ctx.move_to(side * 64, 55); ctx.line_to(side * 128, 22)
            ctx.stroke()
        else:
            # Final demon lord: antlers, crown, layered obsidian armor, shadow flames.
            for side in (-1, 1):
                flame = cairo.LinearGradient(0, -120, 0, 120)
                flame.add_color_stop_rgba(0, .76, .05, .38, .80); flame.add_color_stop_rgba(1, .08, .01, .16, 0)
                ctx.set_source(flame); ctx.move_to(side * 38, -42); ctx.curve_to(side * 115, -65, side * 92, 25, side * 130, 62)
                ctx.curve_to(side * 82, 48, side * 108, 128, side * 34, 115); ctx.close_path(); ctx.fill()
            armor = cairo.RadialGradient(-25, -28, 5, 0, 18, 118)
            armor.add_color_stop_rgb(0, .33, .07, .40); armor.add_color_stop_rgb(.55, *body); armor.add_color_stop_rgb(1, .018, .006, .035)
            ctx.set_source(armor); ctx.arc(0, 0, 76, 0, math.tau); ctx.rectangle(-86, 38, 172, 93); ctx.fill()
            ctx.set_source_rgb(.055, .012, .085)
            for side in (-1, 1):
                ctx.move_to(side * 42, -48); ctx.curve_to(side * 105, -80, side * 75, -130, side * 122, -145)
                ctx.curve_to(side * 78, -88, side * 56, -38, side * 58, -8); ctx.close_path()
                ctx.move_to(side * 25, -61); ctx.line_to(side * 45, -132); ctx.line_to(side * 9, -65); ctx.close_path()
            ctx.fill()
            ctx.set_source_rgb(.88, .61, .13)
            ctx.move_to(-58, -55); ctx.line_to(-34, -105); ctx.line_to(-10, -60)
            ctx.line_to(10, -112); ctx.line_to(34, -60); ctx.line_to(58, -98); ctx.line_to(54, -43); ctx.close_path(); ctx.fill()
            ctx.set_source_rgba(.65, .18, .78, .62); ctx.set_line_width(4)
            for y in (55, 82, 108): ctx.move_to(-62 + (y - 55) * .4, y); ctx.line_to(62 - (y - 55) * .4, y)
            ctx.stroke()

        # Eyes, mouth, and attribute sigil.
        eye = (1, .75, .10) if rank < 4 else (1, .12, .08)
        _glow(ctx, -29, -10, 18, eye, .34); _glow(ctx, 29, -10, 18, eye, .34)
        ctx.set_source_rgb(*eye); ctx.arc(-29, -10, 5.5, 0, math.tau); ctx.arc(29, -10, 5.5, 0, math.tau); ctx.fill()
        ctx.set_source_rgba(.015, .008, .018, .72); ctx.move_to(-28, 20); ctx.curve_to(-10, 35, 10, 35, 28, 20)
        ctx.curve_to(8, 53, -8, 53, -28, 20); ctx.fill()
        # Attribute emblem floats over the chest.
        _glow(ctx, 0, 72, 42, aura_color, .28); ctx.set_source_rgb(*aura_color)
        if kind == "血量型":
            ctx.arc(-10, 67, 11, 0, math.tau); ctx.arc(10, 67, 11, 0, math.tau)
            ctx.move_to(-21, 70); ctx.line_to(0, 94); ctx.line_to(21, 70); ctx.fill()
        elif kind == "攻擊型":
            ctx.move_to(-8, 52); ctx.line_to(13, 73); ctx.line_to(3, 77)
            ctx.line_to(17, 102); ctx.line_to(-19, 70); ctx.line_to(-6, 68); ctx.close_path(); ctx.fill()
        else:
            ctx.move_to(0, 48); ctx.line_to(28, 61); ctx.line_to(22, 91)
            ctx.line_to(0, 108); ctx.line_to(-22, 91); ctx.line_to(-28, 61); ctx.close_path(); ctx.fill()
        ctx.scale(1 / scale, 1 / scale); ctx.translate(-150, -150)
        _grain(ctx, w, h, rank * 117 + len(kind), 120, .026)

    return texture_from_cairo(300, 300, paint)


def make_monster_portrait(rank: int, kind: str) -> arcade.Texture:
    """Render one of fifteen species: five threat ranks by three power forms."""
    aura = {
        "血量型": (.94, .10, .25),
        "攻擊型": (1.00, .43, .055),
        "防禦型": (.12, .58, 1.00),
    }[kind]

    def paint(ctx: cairo.Context, w: int, h: int) -> None:
        ctx.set_line_join(cairo.LINE_JOIN_ROUND)
        ctx.set_line_cap(cairo.LINE_CAP_ROUND)
        _glow(ctx, 150, 153, 148, aura, .17 + rank * .025)
        _rune_ring(ctx, 150, 153, 128, aura, .12 + rank * .02)
        ctx.translate(150, 150)

        def ellipse(x: float, y: float, rx: float, ry: float) -> None:
            ctx.save(); ctx.translate(x, y); ctx.scale(rx, ry)
            ctx.arc(0, 0, 1, 0, math.tau); ctx.restore()

        def polygon(points: tuple[tuple[float, float], ...]) -> None:
            ctx.move_to(*points[0])
            for point in points[1:]:
                ctx.line_to(*point)
            ctx.close_path()

        def glowing_eye(x: float, y: float, radius: float = 4.5,
                        color: tuple[float, float, float] | None = None) -> None:
            eye_color = color or ((1, .75, .12) if rank < 4 else (1, .12, .08))
            _glow(ctx, x, y, radius * 4, eye_color, .34)
            ctx.set_source_rgb(*eye_color); ctx.arc(x, y, radius, 0, math.tau); ctx.fill()
            ctx.set_source_rgba(1, 1, .82, .72); ctx.arc(x - radius * .25, y - radius * .3,
                                                        max(1, radius * .25), 0, math.tau); ctx.fill()

        def horn(points: tuple[tuple[float, float], ...]) -> None:
            horn_grad = cairo.LinearGradient(-80, -100, 70, 30)
            horn_grad.add_color_stop_rgb(0, .82, .72, .51)
            horn_grad.add_color_stop_rgb(.48, .38, .29, .20)
            horn_grad.add_color_stop_rgb(1, .08, .055, .05)
            polygon(points); ctx.set_source(horn_grad); ctx.fill_preserve()
            ctx.set_source_rgba(.05, .025, .02, .72); ctx.set_line_width(2); ctx.stroke()

        def crack(x: float, y: float, length: float, direction: float) -> None:
            dx, dy = math.cos(direction), math.sin(direction)
            ctx.move_to(x, y); ctx.line_to(x + dx * length * .45, y + dy * length * .45)
            ctx.line_to(x + dx * length, y + dy * length)
            bx, by = x + dx * length * .55, y + dy * length * .55
            ctx.move_to(bx, by); ctx.line_to(bx - dy * length * .25, by + dx * length * .25)

        # Ground shadow keeps every silhouette anchored in the battle scene.
        shadow = cairo.RadialGradient(0, 108, 4, 0, 108, 105)
        shadow.add_color_stop_rgba(0, 0, 0, 0, .58); shadow.add_color_stop_rgba(1, 0, 0, 0, 0)
        ctx.set_source(shadow); ellipse(0, 108, 108, 24); ctx.fill()

        if rank == 1 and kind == "血量型":
            # Red-pouched bog toad: swollen life sacs, wet skin, warts and webbed feet.
            ctx.set_source_rgb(.10, .24, .12)
            for side in (-1, 1):
                ellipse(side * 63, 70, 46, 25); ctx.fill()
                polygon(((side * 50, 72), (side * 102, 89), (side * 72, 99),
                         (side * 35, 86))); ctx.fill()
            sac = cairo.RadialGradient(-22, 23, 5, 0, 35, 83)
            sac.add_color_stop_rgb(0, .96, .30, .36); sac.add_color_stop_rgb(.55, .55, .07, .12)
            sac.add_color_stop_rgb(1, .12, .16, .09)
            ctx.set_source(sac); ellipse(0, 35, 78, 70); ctx.fill_preserve()
            ctx.set_source_rgba(.04, .06, .03, .85); ctx.set_line_width(4); ctx.stroke()
            skin = cairo.RadialGradient(-30, -55, 3, 0, -30, 75)
            skin.add_color_stop_rgb(0, .42, .83, .31); skin.add_color_stop_rgb(1, .08, .25, .10)
            ctx.set_source(skin); ellipse(0, -28, 70, 49); ctx.fill_preserve()
            ctx.set_source_rgb(.035, .08, .04); ctx.set_line_width(4); ctx.stroke()
            for side in (-1, 1):
                ctx.set_source_rgb(.20, .49, .15); ellipse(side * 43, -68, 24, 23); ctx.fill()
                glowing_eye(side * 43, -70, 6, (1, .78, .10))
            ctx.set_source_rgba(.02, .05, .025, .85); ctx.set_line_width(5)
            ctx.move_to(-38, -13); ctx.curve_to(-15, 4, 15, 4, 38, -13); ctx.stroke()
            for x, y, r in ((-48, -22, 5), (30, -35, 4), (-15, 23, 6), (45, 37, 5), (5, 63, 4)):
                ctx.set_source_rgba(.66, .93, .36, .30); ctx.arc(x, y, r, 0, math.tau); ctx.fill()
                ctx.set_source_rgba(.07, .16, .06, .65); ctx.set_line_width(1.5); ctx.stroke()

        elif rank == 1 and kind == "攻擊型":
            # Ashland wolf: lean muzzle, torn ears, bone fangs and battle scars.
            ctx.set_source_rgb(.12, .08, .075)
            polygon(((-76, 108), (-91, 42), (-58, -8), (0, -28), (58, -8),
                     (91, 42), (76, 108), (35, 82), (0, 113), (-35, 82))); ctx.fill()
            fur = cairo.RadialGradient(-25, -40, 4, 0, 4, 104)
            fur.add_color_stop_rgb(0, .58, .32, .17); fur.add_color_stop_rgb(.55, .29, .13, .09)
            fur.add_color_stop_rgb(1, .07, .045, .045)
            ctx.set_source(fur); polygon(((-68, -15), (-91, -99), (-39, -71), (0, -86),
                                          (39, -71), (91, -99), (68, -15), (54, 51),
                                          (0, 78), (-54, 51))); ctx.fill_preserve()
            ctx.set_source_rgb(.035, .018, .018); ctx.set_line_width(4); ctx.stroke()
            ctx.set_source_rgb(.40, .18, .11); ellipse(0, 11, 55, 42); ctx.fill()
            ctx.set_source_rgb(.16, .075, .065); ellipse(0, 30, 42, 25); ctx.fill()
            ctx.set_source_rgb(.025, .018, .02); ellipse(0, 15, 14, 10); ctx.fill()
            glowing_eye(-31, -22, 5); glowing_eye(31, -22, 5)
            ctx.set_source_rgb(.93, .78, .55)
            for side in (-1, 1):
                polygon(((side * 18, 37), (side * 31, 72), (side * 5, 45))); ctx.fill()
            ctx.set_source_rgba(.72, .08, .07, .78); ctx.set_line_width(4)
            ctx.move_to(17, -58); ctx.line_to(6, -30); ctx.move_to(28, -52); ctx.line_to(16, -27); ctx.stroke()
            ctx.set_source_rgba(.90, .55, .22, .26); ctx.set_line_width(2)
            for side in (-1, 1):
                for i in range(4):
                    ctx.move_to(side * (45 + i * 4), 47 + i * 8); ctx.line_to(side * (69 + i * 5), 68 + i * 8)
            ctx.stroke()

        elif rank == 1:
            # Rune-shell cave crab: segmented legs, oversized claws and mineral plates.
            ctx.set_source_rgb(.08, .12, .17); ctx.set_line_width(13)
            for side in (-1, 1):
                for y in (18, 43, 68):
                    ctx.move_to(side * 55, y); ctx.line_to(side * 96, y + 17)
                    ctx.line_to(side * 116, y + 5)
            ctx.stroke()
            shell = cairo.RadialGradient(-35, -39, 6, 0, 15, 102)
            shell.add_color_stop_rgb(0, .34, .65, .83); shell.add_color_stop_rgb(.48, .17, .34, .48)
            shell.add_color_stop_rgb(1, .045, .09, .15)
            ctx.set_source(shell); ellipse(0, 22, 82, 72); ctx.fill_preserve()
            ctx.set_source_rgb(.025, .05, .085); ctx.set_line_width(5); ctx.stroke()
            for side in (-1, 1):
                ctx.set_source_rgb(.12, .27, .40); ellipse(side * 91, 3, 37, 32); ctx.fill_preserve()
                ctx.set_source_rgb(.035, .075, .12); ctx.set_line_width(4); ctx.stroke()
                polygon(((side * 87, -4), (side * 119, -25), (side * 112, 14))); ctx.set_source_rgb(.04, .10, .16); ctx.fill()
                ctx.set_source_rgb(.08, .15, .20); ctx.set_line_width(7)
                ctx.move_to(side * 30, -42); ctx.line_to(side * 36, -78); ctx.stroke()
                glowing_eye(side * 36, -82, 5, (.35, .84, 1))
            ctx.set_source_rgba(.30, .74, 1, .45); ctx.set_line_width(2.5)
            for angle in (-2.4, -1.8, -1.2, -.6):
                crack(0, 12, 54, angle)
            ctx.stroke()

        elif rank == 2 and kind == "血量型":
            # Plague-blood ogre: massive shoulders, stitched hide and trophy necklace.
            ctx.set_source_rgb(.18, .07, .045); ellipse(0, 73, 108, 67); ctx.fill()
            body_grad = cairo.RadialGradient(-25, -35, 5, 0, 10, 108)
            body_grad.add_color_stop_rgb(0, .66, .39, .16); body_grad.add_color_stop_rgb(.55, .34, .18, .07)
            body_grad.add_color_stop_rgb(1, .09, .045, .03)
            ctx.set_source(body_grad); ellipse(0, -4, 76, 77); ctx.fill_preserve()
            ctx.set_source_rgb(.08, .035, .025); ctx.set_line_width(5); ctx.stroke()
            for side in (-1, 1):
                horn(((side * 49, -54), (side * 88, -105), (side * 71, -34)))
                ctx.set_source_rgb(.25, .10, .055); ellipse(side * 70, -2, 25, 35); ctx.fill()
                glowing_eye(side * 28, -22, 5)
            ctx.set_source_rgb(.14, .045, .03); ellipse(0, 20, 43, 29); ctx.fill()
            ctx.set_source_rgb(.86, .69, .43)
            for x in (-28, -14, 0, 14, 28):
                polygon(((x - 5, 25), (x, 45 + abs(x) * .15), (x + 6, 25))); ctx.fill()
            ctx.set_source_rgba(.08, .02, .015, .78); ctx.set_line_width(3)
            for x, y, flip in ((-35, -48, 1), (20, 3, -1), (-10, 55, 1)):
                ctx.move_to(x, y); ctx.line_to(x + 24 * flip, y + 13); ctx.move_to(x + 7 * flip, y + 4); ctx.line_to(x + 3 * flip, y + 12)
            ctx.stroke()
            for i, x in enumerate((-52, -26, 0, 26, 52)):
                ctx.set_source_rgb(.76, .67, .48); ellipse(x, 78 + abs(i - 2) * 5, 9, 11); ctx.fill()
                ctx.set_source_rgb(.08, .04, .03); ctx.arc(x - 3, 76 + abs(i - 2) * 5, 2, 0, math.tau); ctx.arc(x + 3, 76 + abs(i - 2) * 5, 2, 0, math.tau); ctx.fill()

        elif rank == 2 and kind == "攻擊型":
            # Twin-blade gnoll king: crossed cleavers, ragged mane and laughing jaws.
            steel = cairo.LinearGradient(-120, -90, 120, 110)
            steel.add_color_stop_rgb(0, .86, .82, .68); steel.add_color_stop_rgb(.4, .24, .27, .30); steel.add_color_stop_rgb(1, .06, .07, .09)
            for side in (-1, 1):
                ctx.save(); ctx.rotate(side * .58); ctx.set_source(steel)
                polygon(((side * 18, -123), (side * 40, -105), (side * 30, 91),
                         (side * 7, 109), (side * 11, -83))); ctx.fill_preserve()
                ctx.set_source_rgb(.04, .025, .02); ctx.set_line_width(3); ctx.stroke(); ctx.restore()
            ctx.set_source_rgb(.10, .055, .035)
            polygon(((-79, 107), (-95, 40), (-66, -19), (-83, -91), (-34, -68),
                     (0, -84), (34, -68), (83, -91), (66, -19), (95, 40), (79, 107))); ctx.fill()
            fur = cairo.RadialGradient(-18, -45, 4, 0, 0, 95)
            fur.add_color_stop_rgb(0, .72, .43, .16); fur.add_color_stop_rgb(1, .13, .07, .035)
            ctx.set_source(fur); ellipse(0, -6, 70, 73); ctx.fill()
            ctx.set_source_rgb(.27, .12, .065); ellipse(0, 22, 48, 33); ctx.fill()
            ctx.set_source_rgb(.025, .018, .018); ellipse(0, 4, 13, 9); ctx.fill()
            glowing_eye(-29, -28, 5); glowing_eye(29, -28, 5)
            ctx.set_source_rgb(.91, .75, .48)
            for side in (-1, 1):
                for y in (28, 41, 54):
                    polygon(((side * 10, y), (side * (30 + (y - 28) * .3), y + 10), (side * 22, y - 2))); ctx.fill()
            ctx.set_source_rgb(.75, .12, .07); ctx.move_to(-34, 54); ctx.curve_to(-8, 72, 8, 72, 34, 54); ctx.set_line_width(4); ctx.stroke()
            ctx.set_source_rgb(.90, .58, .12); polygon(((-28, -79), (0, -105), (28, -79), (18, -55), (-18, -55))); ctx.fill()

        elif rank == 2:
            # Black-iron gargoyle: masonry wings, chiseled mask and glowing cracks.
            stone = cairo.LinearGradient(-100, -90, 100, 110)
            stone.add_color_stop_rgb(0, .35, .45, .52); stone.add_color_stop_rgb(.5, .15, .20, .25)
            stone.add_color_stop_rgb(1, .035, .055, .08)
            ctx.set_source(stone)
            polygon(((-47, 6), (-128, -83), (-107, 5), (-136, 55), (-72, 79), (-42, 51)))
            ctx.fill(); polygon(((47, 6), (128, -83), (107, 5), (136, 55), (72, 79), (42, 51))); ctx.fill()
            ctx.set_source(stone); polygon(((-68, -38), (-42, -91), (-16, -62), (0, -84),
                                            (16, -62), (42, -91), (68, -38), (60, 67),
                                            (34, 112), (-34, 112), (-60, 67))); ctx.fill_preserve()
            ctx.set_source_rgb(.025, .035, .05); ctx.set_line_width(5); ctx.stroke()
            horn(((-45, -60), (-76, -118), (-27, -74))); horn(((45, -60), (76, -118), (27, -74)))
            ctx.set_source_rgb(.07, .10, .13); polygon(((-40, -20), (0, -45), (40, -20), (31, 35),
                                                        (0, 58), (-31, 35))); ctx.fill()
            glowing_eye(-21, -13, 5, (.25, .75, 1)); glowing_eye(21, -13, 5, (.25, .75, 1))
            ctx.set_source_rgba(.20, .65, 1, .60); ctx.set_line_width(3)
            for x, y, d in ((-43, 2, .8), (33, -43, 2.2), (-10, 48, 1.1), (70, 26, 2.5)):
                crack(x, y, 31, d)
            ctx.stroke()

        elif rank == 3 and kind == "血量型":
            # Soul-eating elder tree: root crown, hollow face, spirit fruit and sap veins.
            ctx.set_source_rgb(.055, .08, .045); ctx.set_line_width(18)
            for side in (-1, 1):
                ctx.move_to(side * 27, 88); ctx.curve_to(side * 58, 72, side * 74, 111, side * 118, 104)
                ctx.move_to(side * 32, -42); ctx.curve_to(side * 82, -68, side * 69, -112, side * 112, -125)
                ctx.move_to(side * 38, -18); ctx.curve_to(side * 96, -16, side * 83, -67, side * 132, -62)
            ctx.stroke()
            bark = cairo.LinearGradient(-70, -100, 70, 115)
            bark.add_color_stop_rgb(0, .27, .34, .12); bark.add_color_stop_rgb(.48, .16, .13, .055)
            bark.add_color_stop_rgb(1, .045, .065, .035)
            ctx.set_source(bark); polygon(((-56, 111), (-44, 18), (-67, -37), (-34, -102),
                                           (0, -72), (34, -102), (67, -37), (44, 18), (56, 111),
                                           (18, 83), (0, 122), (-18, 83))); ctx.fill_preserve()
            ctx.set_source_rgb(.04, .035, .02); ctx.set_line_width(5); ctx.stroke()
            ctx.set_source_rgb(.025, .025, .018); ellipse(0, -10, 39, 48); ctx.fill()
            glowing_eye(-18, -21, 5, (.75, 1, .24)); glowing_eye(18, -21, 5, (.75, 1, .24))
            ctx.set_source_rgba(.58, .95, .16, .60); ctx.set_line_width(3)
            for x in (-35, -13, 12, 34):
                ctx.move_to(x, 94); ctx.curve_to(x - 14, 54, x + 18, 11, x + (5 if x < 0 else -5), -63)
            ctx.stroke()
            for x, y in ((-92, -72), (94, -29), (-73, 3), (82, -89), (1, -106)):
                _glow(ctx, x, y, 18, (.75, .08, .28), .28); ctx.set_source_rgb(.72, .06, .20); ctx.arc(x, y, 7, 0, math.tau); ctx.fill()

        elif rank == 3 and kind == "攻擊型":
            # Crimson griffin lord: layered eagle wings, hooked beak, mane and talons.
            for side in (-1, 1):
                for layer in range(5):
                    offset = layer * 15
                    feather = cairo.LinearGradient(0, -90, 0, 100)
                    feather.add_color_stop_rgb(0, .82 - layer * .08, .16, .08)
                    feather.add_color_stop_rgb(1, .13, .035, .025)
                    ctx.set_source(feather)
                    polygon(((side * 37, -25 + layer * 7), (side * (132 - offset * .15), -94 + offset),
                             (side * (113 - offset * .10), 22 + offset), (side * 51, 65))); ctx.fill()
            ctx.set_source_rgb(.18, .055, .028)
            polygon(((-71, 106), (-83, 24), (-59, -42), (-30, -74), (0, -97),
                     (30, -74), (59, -42), (83, 24), (71, 106), (0, 79))); ctx.fill()
            head = cairo.RadialGradient(-18, -49, 3, 0, -20, 78)
            head.add_color_stop_rgb(0, .92, .76, .32); head.add_color_stop_rgb(.55, .58, .23, .08)
            head.add_color_stop_rgb(1, .16, .045, .025)
            ctx.set_source(head); ellipse(0, -25, 59, 57); ctx.fill()
            ctx.set_source_rgb(.92, .57, .08)
            polygon(((-25, -7), (0, 35), (31, -7), (7, 3), (0, 19), (-7, 3))); ctx.fill_preserve()
            ctx.set_source_rgb(.16, .05, .02); ctx.set_line_width(3); ctx.stroke()
            glowing_eye(-23, -35, 5); glowing_eye(23, -35, 5)
            ctx.set_source_rgb(.80, .66, .34)
            for side in (-1, 1):
                for i in range(3):
                    polygon(((side * (28 + i * 9), 77), (side * (39 + i * 12), 118),
                             (side * (18 + i * 9), 88))); ctx.fill()
            ctx.set_source_rgba(1, .42, .08, .55); ctx.set_line_width(2.5)
            for side in (-1, 1):
                ctx.move_to(side * 49, -14); ctx.line_to(side * 101, -66)
                ctx.move_to(side * 59, 9); ctx.line_to(side * 114, -29)
            ctx.stroke()

        elif rank == 3:
            # Rune-bone warlord: crowned helm, articulated skull and layered fortress armor.
            metal = cairo.LinearGradient(-100, -90, 100, 115)
            metal.add_color_stop_rgb(0, .52, .62, .72); metal.add_color_stop_rgb(.42, .16, .19, .24)
            metal.add_color_stop_rgb(1, .035, .055, .09)
            ctx.set_source(metal); ellipse(-78, 47, 45, 49); ctx.fill(); ellipse(78, 47, 45, 49); ctx.fill()
            ctx.set_source(metal); polygon(((-73, 111), (-66, 12), (-45, -51), (0, -76),
                                            (45, -51), (66, 12), (73, 111), (0, 82))); ctx.fill_preserve()
            ctx.set_source_rgb(.025, .035, .055); ctx.set_line_width(5); ctx.stroke()
            ctx.set_source_rgb(.78, .72, .59); polygon(((-42, -49), (-30, -83), (0, -96),
                                                        (30, -83), (42, -49), (35, 11),
                                                        (19, 38), (-19, 38), (-35, 11))); ctx.fill()
            ctx.set_source_rgb(.08, .07, .065); ellipse(-18, -42, 10, 13); ctx.fill(); ellipse(18, -42, 10, 13); ctx.fill()
            glowing_eye(-18, -42, 4, (.28, .77, 1)); glowing_eye(18, -42, 4, (.28, .77, 1))
            ctx.set_source_rgb(.56, .47, .25)
            polygon(((-54, -57), (-38, -116), (-12, -76), (0, -126), (12, -76),
                     (38, -116), (54, -57), (31, -68), (0, -57))); ctx.fill()
            ctx.set_source_rgba(.20, .66, 1, .72); ctx.set_line_width(3)
            for y, half in ((20, 42), (49, 50), (79, 56)):
                ctx.move_to(-half, y); ctx.line_to(0, y + 15); ctx.line_to(half, y)
            ctx.stroke()
            ctx.set_source_rgb(.10, .08, .07); ctx.set_line_width(2)
            for x in (-21, -7, 7, 21): ctx.rectangle(x - 4, 9, 8, 18)
            ctx.stroke()

        elif rank == 4 and kind == "血量型":
            # Abyssal hydra sovereign: three independent heads, scaled necks and venom crests.
            ctx.set_source_rgb(.055, .035, .075); ellipse(0, 74, 102, 52); ctx.fill()
            necks = ((-48, -17, -66, -81), (0, -26, 0, -108), (48, -17, 66, -81))
            for index, (sx, sy, hx, hy) in enumerate(necks):
                grad = cairo.LinearGradient(sx, 83, hx, hy)
                grad.add_color_stop_rgb(0, .16, .05, .25); grad.add_color_stop_rgb(.5, .50, .08, .28)
                grad.add_color_stop_rgb(1, .10, .025, .14)
                ctx.set_source(grad); ctx.set_line_width(34 if index == 1 else 29)
                ctx.move_to(sx, 83); ctx.curve_to(sx * .7, 37, hx * 1.15, -25, hx, hy + 18); ctx.stroke()
                ctx.set_source_rgb(.39, .07, .25); ellipse(hx, hy, 36, 30); ctx.fill_preserve()
                ctx.set_source_rgb(.04, .015, .055); ctx.set_line_width(4); ctx.stroke()
                for side in (-1, 1):
                    horn(((hx + side * 18, hy - 19), (hx + side * 34, hy - 56), (hx + side * 30, hy - 12)))
                glowing_eye(hx - 13, hy - 4, 4); glowing_eye(hx + 13, hy - 4, 4)
                ctx.set_source_rgb(.85, .72, .48)
                for side in (-1, 1): polygon(((hx + side * 7, hy + 14), (hx + side * 15, hy + 35), (hx + side * 21, hy + 13))); ctx.fill()
            ctx.set_source_rgba(.86, .12, .35, .45); ctx.set_line_width(2)
            for x in (-65, -42, -18, 12, 38, 65):
                ctx.arc(x, 70 - abs(x) * .18, 7, 0, math.pi); ctx.stroke()

        elif rank == 4 and kind == "攻擊型":
            # Thunder-prison wyvern: vast membrane wings, crown horns and lightning veins.
            wing = cairo.LinearGradient(0, -110, 0, 100)
            wing.add_color_stop_rgb(0, .72, .12, .035); wing.add_color_stop_rgb(.55, .24, .045, .035)
            wing.add_color_stop_rgb(1, .055, .02, .025)
            ctx.set_source(wing)
            polygon(((-37, 8), (-139, -102), (-116, -11), (-143, 45), (-78, 83), (-47, 49))); ctx.fill()
            polygon(((37, 8), (139, -102), (116, -11), (143, 45), (78, 83), (47, 49))); ctx.fill()
            ctx.set_source_rgba(1, .48, .07, .62); ctx.set_line_width(3)
            for side in (-1, 1):
                ctx.move_to(side * 44, 11); ctx.line_to(side * 132, -88)
                ctx.move_to(side * 57, 35); ctx.line_to(side * 126, -2)
                ctx.move_to(side * 64, 59); ctx.line_to(side * 132, 39)
            ctx.stroke()
            dragon = cairo.RadialGradient(-26, -45, 3, 0, 4, 105)
            dragon.add_color_stop_rgb(0, .84, .18, .055); dragon.add_color_stop_rgb(.52, .34, .055, .035)
            dragon.add_color_stop_rgb(1, .055, .018, .025)
            ctx.set_source(dragon); polygon(((-67, 106), (-59, -31), (-38, -79), (0, -101),
                                             (38, -79), (59, -31), (67, 106), (0, 73))); ctx.fill()
            for side in (-1, 1):
                horn(((side * 29, -77), (side * 70, -133), (side * 48, -59)))
                horn(((side * 44, -52), (side * 94, -84), (side * 55, -33)))
            ctx.set_source_rgb(.12, .025, .025); ellipse(0, -9, 48, 38); ctx.fill()
            glowing_eye(-23, -37, 5); glowing_eye(23, -37, 5)
            ctx.set_source_rgb(.91, .74, .48)
            for x in (-27, -13, 13, 27): polygon(((x - 6, 4), (x, 34), (x + 6, 4))); ctx.fill()
            ctx.set_source_rgba(1, .56, .08, .62); ctx.set_line_width(3)
            for y in (43, 66, 89): ctx.move_to(-35 - y * .15, y); ctx.line_to(0, y + 12); ctx.line_to(35 + y * .15, y)
            ctx.stroke()

        elif rank == 4:
            # Obsidian mountain titan: architectural armor, floating rock fists and blue core.
            rock = cairo.LinearGradient(-100, -100, 100, 120)
            rock.add_color_stop_rgb(0, .32, .40, .49); rock.add_color_stop_rgb(.45, .11, .15, .21)
            rock.add_color_stop_rgb(1, .025, .045, .075)
            for side in (-1, 1):
                ctx.set_source(rock); polygon(((side * 46, -31), (side * 95, -64), (side * 129, -25),
                                               (side * 105, 26), (side * 58, 19))); ctx.fill()
                polygon(((side * 88, 36), (side * 132, 46), (side * 124, 102),
                         (side * 75, 96), (side * 60, 61))); ctx.fill()
            ctx.set_source(rock); polygon(((-67, 111), (-62, -35), (-39, -88), (0, -112),
                                           (39, -88), (62, -35), (67, 111), (0, 83))); ctx.fill_preserve()
            ctx.set_source_rgb(.02, .035, .06); ctx.set_line_width(6); ctx.stroke()
            ctx.set_source_rgb(.045, .07, .10); polygon(((-37, -70), (0, -91), (37, -70),
                                                         (28, -20), (0, -4), (-28, -20))); ctx.fill()
            glowing_eye(-17, -54, 4, (.25, .78, 1)); glowing_eye(17, -54, 4, (.25, .78, 1))
            _glow(ctx, 0, 36, 48, (.18, .67, 1), .34)
            ctx.set_source_rgb(.20, .68, 1); polygon(((0, 9), (26, 31), (16, 65), (0, 79),
                                                      (-16, 65), (-26, 31))); ctx.fill()
            ctx.set_source_rgba(.18, .65, 1, .70); ctx.set_line_width(3)
            for x, y, d in ((-50, -5, 2.2), (44, -22, .7), (-37, 72, 1.8), (77, 53, 2.5), (-92, -31, .4)):
                crack(x, y, 36, d)
            ctx.stroke()

        elif rank == 5 and kind == "血量型":
            # Star-devouring elder god: hooded void, many eyes and living tentacle halo.
            tentacle_grad = cairo.LinearGradient(0, -130, 0, 130)
            tentacle_grad.add_color_stop_rgb(0, .50, .035, .42); tentacle_grad.add_color_stop_rgb(1, .035, .008, .09)
            ctx.set_source(tentacle_grad); ctx.set_line_width(17)
            for i in range(9):
                angle = -2.75 + i * .69
                sx, sy = math.cos(angle) * 43, math.sin(angle) * 34 + 20
                ex, ey = math.cos(angle) * 132, math.sin(angle) * 118 + 5
                bend = 25 if i % 2 else -25
                ctx.move_to(sx, sy); ctx.curve_to(sx + bend, sy - 35, ex - bend, ey + 25, ex, ey); ctx.stroke()
            cloak = cairo.RadialGradient(-24, -52, 4, 0, 12, 118)
            cloak.add_color_stop_rgb(0, .28, .035, .34); cloak.add_color_stop_rgb(.55, .075, .008, .13)
            cloak.add_color_stop_rgb(1, .012, .003, .03)
            ctx.set_source(cloak); polygon(((-82, 118), (-69, -36), (-42, -103), (0, -130),
                                            (42, -103), (69, -36), (82, 118), (0, 84))); ctx.fill()
            ctx.set_source_rgb(.006, .002, .015); ellipse(0, -35, 51, 57); ctx.fill()
            for x, y, r in ((-24, -56, 5), (0, -68, 6), (24, -56, 5), (-32, -27, 4),
                            (0, -24, 7), (32, -27, 4), (-18, 3, 4), (18, 3, 4)):
                glowing_eye(x, y, r, (1, .12, .46))
            ctx.set_source_rgba(.80, .08, .48, .68); ctx.set_line_width(3)
            for y, span in ((35, 39), (57, 48), (81, 58)):
                ctx.move_to(-span, y); ctx.curve_to(-12, y + 19, 12, y - 12, span, y); ctx.stroke()
            for x, y in ((-100, -94), (102, -52), (-116, 49), (91, 93), (0, -121)):
                _star_path(ctx, x, y, 8, 3, 5); ctx.set_source_rgba(1, .22, .55, .72); ctx.fill()

        elif rank == 5 and kind == "攻擊型":
            # Crimson world-ending dragon emperor: six horns, royal crown, fire wings and fangs.
            flame = cairo.LinearGradient(0, -130, 0, 130)
            flame.add_color_stop_rgb(0, .95, .16, .025); flame.add_color_stop_rgb(.45, .38, .025, .025)
            flame.add_color_stop_rgb(1, .055, .005, .018)
            ctx.set_source(flame)
            polygon(((-38, 19), (-140, -116), (-123, -18), (-148, 31), (-91, 84), (-48, 60))); ctx.fill()
            polygon(((38, 19), (140, -116), (123, -18), (148, 31), (91, 84), (48, 60))); ctx.fill()
            ctx.set_source_rgba(1, .48, .04, .70); ctx.set_line_width(3)
            for side in (-1, 1):
                ctx.move_to(side * 41, 18); ctx.line_to(side * 132, -99)
                ctx.move_to(side * 58, 43); ctx.line_to(side * 134, -10)
                ctx.move_to(side * 67, 67); ctx.line_to(side * 137, 29)
            ctx.stroke()
            head = cairo.RadialGradient(-24, -43, 4, 0, 5, 112)
            head.add_color_stop_rgb(0, .84, .10, .045); head.add_color_stop_rgb(.52, .28, .018, .035)
            head.add_color_stop_rgb(1, .035, .004, .018)
            ctx.set_source(head); polygon(((-73, 116), (-66, -32), (-43, -88), (0, -112),
                                           (43, -88), (66, -32), (73, 116), (0, 79))); ctx.fill()
            for side in (-1, 1):
                horn(((side * 18, -91), (side * 36, -145), (side * 38, -76)))
                horn(((side * 40, -76), (side * 82, -135), (side * 57, -57)))
                horn(((side * 55, -49), (side * 111, -83), (side * 65, -25)))
            ctx.set_source_rgb(.14, .01, .022); ellipse(0, 4, 54, 45); ctx.fill()
            glowing_eye(-26, -42, 6, (1, .13, .05)); glowing_eye(26, -42, 6, (1, .13, .05))
            ctx.set_source_rgb(.94, .77, .49)
            for x in (-38, -23, -8, 8, 23, 38):
                polygon(((x - 6, 12), (x, 49 + abs(x) * .18), (x + 6, 12))); ctx.fill()
            ctx.set_source_rgb(.90, .59, .10)
            polygon(((-55, -88), (-35, -129), (-12, -94), (0, -143), (12, -94),
                     (35, -129), (55, -88), (34, -74), (0, -84), (-34, -74))); ctx.fill()
            ctx.set_source_rgba(1, .19, .025, .70); ctx.set_line_width(3)
            for y in (50, 73, 96): ctx.move_to(-43 - y * .13, y); ctx.line_to(0, y + 13); ctx.line_to(43 + y * .13, y)
            ctx.stroke()

        else:
            # Obsidian doomsday idol: cathedral-scale armor, mask, crown and sealed blue sun.
            obsidian = cairo.LinearGradient(-120, -120, 120, 120)
            obsidian.add_color_stop_rgb(0, .24, .31, .42); obsidian.add_color_stop_rgb(.32, .055, .06, .12)
            obsidian.add_color_stop_rgb(.67, .13, .08, .18); obsidian.add_color_stop_rgb(1, .012, .02, .045)
            for side in (-1, 1):
                ctx.set_source(obsidian); polygon(((side * 40, -24), (side * 93, -92), (side * 139, -47),
                                                   (side * 119, 21), (side * 64, 35))); ctx.fill()
                polygon(((side * 65, 27), (side * 123, 39), (side * 137, 105),
                         (side * 76, 119), (side * 52, 72))); ctx.fill()
            ctx.set_source(obsidian); polygon(((-75, 123), (-69, -38), (-45, -101), (0, -132),
                                               (45, -101), (69, -38), (75, 123), (0, 88))); ctx.fill_preserve()
            ctx.set_source_rgb(.006, .012, .03); ctx.set_line_width(7); ctx.stroke()
            ctx.set_source_rgb(.025, .04, .075); polygon(((-43, -85), (0, -113), (43, -85),
                                                          (34, -14), (0, 12), (-34, -14))); ctx.fill()
            glowing_eye(-20, -58, 5, (.26, .74, 1)); glowing_eye(20, -58, 5, (.26, .74, 1))
            ctx.set_source_rgb(.55, .47, .29)
            polygon(((-58, -93), (-40, -139), (-15, -105), (0, -151), (15, -105),
                     (40, -139), (58, -93), (33, -82), (0, -94), (-33, -82))); ctx.fill()
            _glow(ctx, 0, 38, 59, (.15, .62, 1), .40)
            ctx.set_source_rgb(.12, .54, .98); ctx.arc(0, 38, 26, 0, math.tau); ctx.fill()
            ctx.set_source_rgb(.75, .91, 1); _star_path(ctx, 0, 38, 18, 7, 8); ctx.fill()
            ctx.set_source_rgba(.18, .65, 1, .78); ctx.set_line_width(3.5)
            for x, y, d in ((-52, -35, 2.1), (47, -12, .7), (-42, 67, 1.8),
                            (62, 78, 2.7), (-99, -35, .35), (101, 30, 2.4)):
                crack(x, y, 39, d)
            ctx.stroke()

        # Form sigil and rank marks provide a readable visual taxonomy without
        # hiding the species-specific face and silhouette.
        _glow(ctx, 0, 113, 31, aura, .24)
        ctx.set_source_rgba(.015, .02, .04, .82); ctx.arc(0, 113, 18, 0, math.tau); ctx.fill()
        ctx.set_source_rgb(*aura)
        if kind == "血量型":
            ctx.arc(-6, 109, 7, 0, math.tau); ctx.arc(6, 109, 7, 0, math.tau)
            ctx.move_to(-13, 112); ctx.line_to(0, 126); ctx.line_to(13, 112); ctx.fill()
        elif kind == "攻擊型":
            polygon(((-5, 99), (9, 111), (2, 114), (11, 128), (-12, 110), (-3, 108))); ctx.fill()
        else:
            polygon(((0, 98), (14, 105), (11, 120), (0, 129), (-11, 120), (-14, 105))); ctx.fill()
        ctx.set_source_rgba(*aura, .78)
        for index in range(rank):
            x = (index - (rank - 1) / 2) * 17
            polygon(((x, -137), (x + 6, -129), (x, -121), (x - 6, -129))); ctx.fill()

        ctx.translate(-150, -150)
        _grain(ctx, w, h, rank * 1009 + sum(map(ord, kind)), 155, .032)
        _vignette(ctx, w, h, .25)

    return texture_from_cairo(300, 300, paint)


def make_critical_effect() -> arcade.Texture:
    """Layered impact burst used by both player and monster critical hits."""
    def paint(ctx: cairo.Context, w: int, h: int) -> None:
        cx, cy = w / 2, h / 2
        _glow(ctx, cx, cy, 168, (1, .13, .025), .31)
        _glow(ctx, cx, cy, 112, (1, .74, .10), .54)
        ctx.save(); ctx.translate(cx, cy)
        # Alternating long and short impact rays.
        for index in range(24):
            ctx.save(); ctx.rotate(index * math.tau / 24)
            length = 158 if index % 2 == 0 else 119
            half_width = 5.5 if index % 2 == 0 else 3.2
            ray = cairo.LinearGradient(28, 0, length, 0)
            ray.add_color_stop_rgba(0, 1, .96, .70, .90)
            ray.add_color_stop_rgba(.35, 1, .48, .035, .72)
            ray.add_color_stop_rgba(1, .82, .025, .015, 0)
            ctx.move_to(26, -half_width); ctx.line_to(length, 0); ctx.line_to(26, half_width)
            ctx.close_path(); ctx.set_source(ray); ctx.fill(); ctx.restore()
        # Two luminous blade trails with dark red outer cuts.
        for angle in (-.70, .70):
            ctx.save(); ctx.rotate(angle)
            ctx.set_source_rgba(.55, .015, .012, .72); ctx.set_line_width(27)
            ctx.move_to(-116, 0); ctx.line_to(116, 0); ctx.stroke()
            ctx.set_source_rgba(1, .18, .025, .92); ctx.set_line_width(15)
            ctx.move_to(-122, 0); ctx.line_to(122, 0); ctx.stroke()
            ctx.set_source_rgba(1, .94, .68, .98); ctx.set_line_width(4.5)
            ctx.move_to(-128, 0); ctx.line_to(128, 0); ctx.stroke(); ctx.restore()
        ctx.restore()
        _rune_ring(ctx, cx, cy, 91, (1, .64, .08), .72)
        _rune_ring(ctx, cx, cy, 60, (1, .18, .025), .66)
        # Central shock core and flying fragments.
        _glow(ctx, cx, cy, 65, (1, .94, .46), .72)
        ctx.set_source_rgba(1, .98, .82, .95); _star_path(ctx, cx, cy, 31, 11, 8); ctx.fill()
        for index in range(12):
            angle = index * math.tau / 12 + .16
            radius = 118 + (index % 3) * 13
            x, y = cx + math.cos(angle) * radius, cy + math.sin(angle) * radius
            ctx.save(); ctx.translate(x, y); ctx.rotate(angle)
            ctx.move_to(-9, -3); ctx.line_to(10, 0); ctx.line_to(-7, 5); ctx.close_path()
            ctx.set_source_rgba(1, .48 if index % 2 else .78, .045, .80); ctx.fill(); ctx.restore()

    return texture_from_cairo(360, 360, paint)


def make_panel_skin(width: int, height: int) -> arcade.Texture:
    def paint(ctx: cairo.Context, w: int, h: int) -> None:
        # Soft shadow.
        for spread, alpha in ((8, .06), (5, .10), (2, .15)):
            _rounded_path(ctx, spread, spread, w - spread * 2, h - spread * 2, 14)
            ctx.set_source_rgba(0, 0, 0, alpha); ctx.fill()
        panel = cairo.LinearGradient(0, 0, w, h)
        panel.add_color_stop_rgba(0, .035, .07, .12, .97)
        panel.add_color_stop_rgba(.52, .018, .035, .065, .96)
        panel.add_color_stop_rgba(1, .055, .028, .070, .97)
        _rounded_path(ctx, 8, 8, w - 16, h - 16, 12); ctx.set_source(panel); ctx.fill_preserve()
        border = cairo.LinearGradient(0, 0, w, h)
        border.add_color_stop_rgb(0, .34, .54, .70); border.add_color_stop_rgb(.45, .82, .61, .25); border.add_color_stop_rgb(1, .28, .38, .55)
        ctx.set_source(border); ctx.set_line_width(2.2); ctx.stroke()
        _rounded_path(ctx, 14, 14, w - 28, h - 28, 8); ctx.set_source_rgba(.58, .70, .82, .16); ctx.set_line_width(1); ctx.stroke()
        # Etched corner ornaments.
        ctx.set_source_rgba(.88, .65, .25, .46); ctx.set_line_width(1.6)
        for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
            ctx.save(); ctx.translate(w / 2 + sx * (w / 2 - 20), h / 2 + sy * (h / 2 - 20)); ctx.scale(sx, sy)
            ctx.move_to(0, 18); ctx.line_to(0, 0); ctx.line_to(18, 0)
            ctx.move_to(4, 13); ctx.line_to(13, 4); ctx.move_to(8, 18); ctx.line_to(18, 8); ctx.stroke(); ctx.restore()
        _grain(ctx, w, h, w * 31 + h, max(40, w * h // 2500), .024)

    return texture_from_cairo(width, height, paint)


def make_button_skin(width: int, height: int, accent: tuple[int, int, int],
                     active: bool, enabled: bool) -> arcade.Texture:
    def paint(ctx: cairo.Context, w: int, h: int) -> None:
        r, g, b = (channel / 255 for channel in accent)
        if not enabled:
            r = g = b = .18
        glow_alpha = .28 if active and enabled else .10
        _glow(ctx, w / 2, h / 2, w * .55, (r, g, b), glow_alpha)
        face = cairo.LinearGradient(0, 4, 0, h - 4)
        boost = .22 if active else .10
        face.add_color_stop_rgb(0, min(1, r + boost), min(1, g + boost), min(1, b + boost))
        face.add_color_stop_rgb(.5, r * .80, g * .80, b * .80)
        face.add_color_stop_rgb(1, r * .38, g * .38, b * .38)
        _rounded_path(ctx, 5, 5, w - 10, h - 10, 9); ctx.set_source(face); ctx.fill_preserve()
        ctx.set_source_rgba(.70, .84, .95, .72 if active else .42); ctx.set_line_width(2); ctx.stroke()
        _rounded_path(ctx, 9, 9, w - 18, h - 18, 6); ctx.set_source_rgba(1, 1, 1, .13); ctx.set_line_width(1); ctx.stroke()
        # Top gloss and small diamond rivets.
        gloss = cairo.LinearGradient(0, 7, 0, h * .55)
        gloss.add_color_stop_rgba(0, 1, 1, 1, .20 if enabled else .06)
        gloss.add_color_stop_rgba(1, 1, 1, 1, 0)
        _rounded_path(ctx, 10, 9, w - 20, h * .46, 6); ctx.set_source(gloss); ctx.fill()
        ctx.set_source_rgba(.92, .70, .28, .52 if enabled else .18)
        for x in (15, w - 15):
            _star_path(ctx, x, h / 2, 4.5, 2.2, 4); ctx.fill()

    return texture_from_cairo(width, height, paint)


def make_bar_skin(width: int, height: int, ratio: float,
                  color: tuple[int, ...]) -> arcade.Texture:
    def paint(ctx: cairo.Context, w: int, h: int) -> None:
        r, g, b = (color[index] / 255 for index in range(3))
        _rounded_path(ctx, 1, 1, w - 2, h - 2, h / 2)
        ctx.set_source_rgba(.01, .02, .03, .88); ctx.fill_preserve()
        ctx.set_source_rgba(.55, .67, .78, .58); ctx.set_line_width(1.4); ctx.stroke()
        fill_width = max(0, (w - 6) * ratio)
        if fill_width > 1:
            meter = cairo.LinearGradient(0, 2, 0, h - 2)
            meter.add_color_stop_rgb(0, min(1, r + .32), min(1, g + .32), min(1, b + .32))
            meter.add_color_stop_rgb(.55, r, g, b)
            meter.add_color_stop_rgb(1, r * .52, g * .52, b * .52)
            _rounded_path(ctx, 3, 3, fill_width, h - 6, (h - 6) / 2); ctx.set_source(meter); ctx.fill()
            ctx.set_source_rgba(1, 1, 1, .22); ctx.set_line_width(1); ctx.move_to(7, 5); ctx.line_to(3 + fill_width - 5, 5); ctx.stroke()

    return texture_from_cairo(width, height, paint)


def make_log_card_skin(width: int, height: int, accent: tuple[int, int, int],
                       newest: bool) -> arcade.Texture:
    """Compact glass card used to keep individual adventure records distinct."""
    def paint(ctx: cairo.Context, w: int, h: int) -> None:
        r, g, b = (channel / 255 for channel in accent)
        _rounded_path(ctx, 1, 1, w - 2, h - 2, 9)
        card = cairo.LinearGradient(0, 0, w, h)
        card.add_color_stop_rgba(0, r * .24, g * .24, b * .24, .94)
        card.add_color_stop_rgba(.16, .035, .055, .085, .96)
        card.add_color_stop_rgba(1, .018, .026, .045, .94)
        ctx.set_source(card); ctx.fill_preserve()
        ctx.set_source_rgba(r, g, b, .82 if newest else .38)
        ctx.set_line_width(2 if newest else 1); ctx.stroke()
        # Category rail and medallion.
        rail = cairo.LinearGradient(0, 3, 0, h - 3)
        rail.add_color_stop_rgba(0, r, g, b, .25)
        rail.add_color_stop_rgba(.5, r, g, b, .95)
        rail.add_color_stop_rgba(1, r, g, b, .25)
        _rounded_path(ctx, 4, 5, 4, h - 10, 2); ctx.set_source(rail); ctx.fill()
        _glow(ctx, 23, h / 2, 17, (r, g, b), .24 if newest else .12)
        ctx.set_source_rgba(.015, .025, .045, .96); ctx.arc(23, h / 2, 11, 0, math.tau); ctx.fill_preserve()
        ctx.set_source_rgba(r, g, b, .90); ctx.set_line_width(1.5); ctx.stroke()
        # Top sheen and a small latest-record gem.
        ctx.set_source_rgba(1, 1, 1, .055); ctx.set_line_width(1)
        ctx.move_to(11, 6); ctx.curve_to(w * .33, 2, w * .67, 2, w - 11, 6); ctx.stroke()
        if newest:
            _glow(ctx, w - 13, 12, 13, (1, .72, .18), .32)
            ctx.move_to(w - 13, 5); ctx.line_to(w - 7, 12); ctx.line_to(w - 13, 19)
            ctx.line_to(w - 19, 12); ctx.close_path()
            ctx.set_source_rgb(1, .72, .18); ctx.fill()

    return texture_from_cairo(width, height, paint)


def make_log_scroll_skin(width: int, height: int, part: str,
                         active: bool = False) -> arcade.Texture:
    """Draw the recessed record track or its draggable rune-metal thumb."""
    def paint(ctx: cairo.Context, w: int, h: int) -> None:
        if part == "track":
            _rounded_path(ctx, 1, 1, w - 2, h - 2, w / 2)
            track = cairo.LinearGradient(0, 0, w, 0)
            track.add_color_stop_rgba(0, .008, .015, .028, .86)
            track.add_color_stop_rgba(.5, .055, .085, .12, .96)
            track.add_color_stop_rgba(1, .008, .015, .028, .86)
            ctx.set_source(track); ctx.fill_preserve()
            ctx.set_source_rgba(.30, .48, .66, .30); ctx.set_line_width(1); ctx.stroke()
            ctx.set_source_rgba(.42, .62, .78, .18); ctx.set_line_width(1)
            ctx.move_to(w / 2, 9); ctx.line_to(w / 2, h - 9); ctx.stroke()
        else:
            _rounded_path(ctx, 1, 1, w - 2, h - 2, min(6, w / 2))
            thumb = cairo.LinearGradient(0, 0, w, 0)
            if active:
                thumb.add_color_stop_rgb(0, .34, .57, .76)
                thumb.add_color_stop_rgb(.48, .88, .69, .27)
                thumb.add_color_stop_rgb(1, .25, .43, .64)
            else:
                thumb.add_color_stop_rgb(0, .19, .36, .53)
                thumb.add_color_stop_rgb(.48, .70, .54, .24)
                thumb.add_color_stop_rgb(1, .14, .28, .44)
            ctx.set_source(thumb); ctx.fill_preserve()
            ctx.set_source_rgba(1, .77, .30, .82 if active else .56)
            ctx.set_line_width(1.4); ctx.stroke()
            ctx.set_source_rgba(1, .86, .48, .62)
            for offset in (-5, 0, 5):
                ctx.move_to(3, h / 2 + offset); ctx.line_to(w - 3, h / 2 + offset)
            ctx.set_line_width(1); ctx.stroke()

    return texture_from_cairo(width, height, paint)


def make_activity_frame(width: int, height: int) -> arcade.Texture:
    def paint(ctx: cairo.Context, w: int, h: int) -> None:
        _rounded_path(ctx, 3, 3, w - 6, h - 6, 7)
        frame = cairo.LinearGradient(0, 0, w, h)
        frame.add_color_stop_rgb(0, .34, .54, .70); frame.add_color_stop_rgb(.5, .82, .60, .22); frame.add_color_stop_rgb(1, .28, .39, .58)
        ctx.set_source(frame); ctx.set_line_width(3); ctx.stroke()
        ctx.set_source_rgba(.92, .70, .27, .72); ctx.set_line_width(2)
        for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
            ctx.save(); ctx.translate(w / 2 + sx * (w / 2 - 18), h / 2 + sy * (h / 2 - 18)); ctx.scale(sx, sy)
            ctx.move_to(0, 28); ctx.line_to(0, 0); ctx.line_to(28, 0)
            ctx.move_to(5, 22); ctx.line_to(22, 5); ctx.stroke(); ctx.restore()

    return texture_from_cairo(width, height, paint)


class RPGWindow(arcade.Window):
    MALE_NAMES = (
        "亞倫", "凱恩", "雷歐", "洛克", "艾德林",
        "賽勒斯", "奧德里克", "維爾恩", "達里安", "羅蘭",
        "伊薩克", "卡修斯", "諾克斯", "斐恩", "格雷文",
        "路西恩", "索恩", "艾爾德", "泰瑞斯", "沃爾夫",
    )
    FEMALE_NAMES = (
        "莉亞", "露娜", "米菈", "艾瑟琳", "賽蕾娜",
        "伊芙琳", "維奧拉", "芙蕾雅", "諾薇雅", "希爾妲",
        "卡珊德拉", "奧菲莉亞", "蕾妮絲", "艾莉希亞", "薇爾莎",
        "莫莉安", "塔莉雅", "伊瑟拉", "蘿莎琳", "瑟菲雅",
    )
    NAME_POOLS = {"男性": MALE_NAMES, "女性": FEMALE_NAMES}
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
    )
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
    JOURNEY_LORE = (
        "殘月沉入群山，你沿著失落王國的古道向北而行。",
        "風從斷垣間捎來低語，像是某位無名騎士仍在守望。",
        "遠方鐘塔敲響第十三聲，荒野的影子開始蠢動。",
        "古老星圖在行囊中微微發亮，指向被黑霧吞沒的王城。",
        "你跨過覆滿銀苔的石橋，橋下傳來沉睡巨獸的吐息。",
        "烏鴉掠過猩紅天際，前方廢墟亮起一盞孤獨燈火。",
    )
    SHOP_LORE = (
        "紫焰燈下，蒙面商人攤開封存禁藥的黑絨布。",
        "每只藥瓶都映著陌生星辰，彷彿盛裝著另一個世界。",
        "商人以沙啞嗓音報價，斗篷深處傳來金屬鎖鏈的輕響。",
    )

    def __init__(self) -> None:
        super().__init__(SCREEN_WIDTH, SCREEN_HEIGHT, SCREEN_TITLE, resizable=False)
        self.background = make_background()
        self.battle_background = make_activity_background("battle")
        self.shop_background = make_activity_background("shop")
        self.event_backgrounds = {
            number: make_activity_background("event", number) for number in range(1, 5)
        }
        self.hero_portrait = make_player_portrait("男性", "獸人", "戰士")
        self.enemy_portrait = make_monster_portrait(1, "血量型")
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
        self.enemy: Enemy | None = None
        self.difficulty = 1
        self.creation_step = 0
        self.selected_sex = "男性"
        self.name_index = 0
        self.name_input = self.NAME_POOLS[self.selected_sex][self.name_index]
        self.selected_race = "獸人"
        self.selected_job = "戰士"
        self.buttons: list[Button] = []
        self.hovered: Button | None = None
        self.home_confirmation = False
        self.log_scroll = 0
        self.log_scroll_dragging = False
        self.log_scroll_drag_offset = 0.0
        self._log_scroll_geometry: tuple[float, ...] | None = None
        self.messages = [
            "黑潮吞沒北境，最後的旅人踏上命運古道。",
            "願星火照亮你的劍鋒。",
        ]
        self.journey_lore = random.choice(self.JOURNEY_LORE)
        self.shop_lore = random.choice(self.SHOP_LORE)
        self.victory = False
        self.player_hp_peak = self.player.hp
        self.event_number = 1
        self.event_title = "隨機事件"
        self.event_result = ""
        self.event_messages: list[str] = []
        self.final_enemy_name = ""
        self.attack_animation: AttackAnimation | None = None
        self.floating_damage: list[FloatingDamage] = []
        self.pending_turn: str | None = None
        self.battle_delay = 0.0
        self.auto_battle = False
        self.configure_buttons()

    # ---------- UI helpers ----------
    @staticmethod
    def rect(left: float, bottom: float, width: float, height: float,
             color: tuple[int, ...], border: tuple[int, ...] | None = None,
             border_width: int = 1) -> None:
        arcade.draw_lbwh_rectangle_filled(left, bottom, width, height, color)
        if border:
            arcade.draw_lbwh_rectangle_outline(left, bottom, width, height,
                                               border, border_width)

    def text(self, value: str, x: float, y: float, size: int = 18,
             color: tuple[int, ...] = INK, anchor_x: str = "left",
             anchor_y: str = "baseline", bold: bool = False,
             width: int | None = None, multiline: bool = False,
             max_width: float | None = None, max_height: float | None = None,
             min_size: int = 8) -> None:
        """Draw text and shrink it until it stays inside the supplied bounds."""
        fitted_size = size

        def get_label(display_value: str) -> arcade.Text:
            key = (display_value, x, y, fitted_size, color, anchor_x, anchor_y,
                   bold, width, multiline)
            cached = self._text_cache.get(key)
            if cached is None:
                cached = arcade.Text(
                    display_value, x, y, color, fitted_size, width=width, align="left",
                    anchor_x=anchor_x, anchor_y=anchor_y, bold=bold,
                    multiline=multiline,
                    font_name=("Microsoft JhengHei", "Noto Sans CJK TC", "Arial"),
                )
                self._text_cache[key] = cached
            return cached

        while True:
            label = get_label(value)
            fits_width = max_width is None or label.content_width <= max_width
            fits_height = max_height is None or label.content_height <= max_height
            if fits_width and fits_height:
                label.draw()
                return
            if fitted_size <= min_size:
                if max_width is not None and not fits_width:
                    low, high = 0, len(value)
                    best = "…"
                    while low <= high:
                        middle = (low + high) // 2
                        candidate = value[:middle].rstrip() + "…"
                        candidate_label = get_label(candidate)
                        if candidate_label.content_width <= max_width:
                            best = candidate
                            low = middle + 1
                        else:
                            high = middle - 1
                    label = get_label(best)
                label.draw()
                return
            fitted_size -= 1

    def panel(self, left: float, bottom: float, width: float, height: float,
              title: str = "") -> None:
        key = (int(width), int(height))
        texture = self._panel_skin_cache.get(key)
        if texture is None:
            texture = make_panel_skin(*key)
            self._panel_skin_cache[key] = texture
        arcade.draw_texture_rect(
            texture, arcade.XYWH(left + width / 2, bottom + height / 2, width, height)
        )
        if title:
            self.text(title, left + 20, bottom + height - 31, 18, GOLD, bold=True,
                      max_width=max(20, width - 40), max_height=24)

    def bar(self, x: float, y: float, width: float, value: int, maximum: int,
            color: tuple[int, ...], label: str) -> None:
        ratio = max(0, min(1, value / max(1, maximum)))
        key = (int(width), 17, round(ratio, 3), tuple(color[:3]))
        texture = self._bar_skin_cache.get(key)
        if texture is None:
            texture = make_bar_skin(int(width), 17, ratio, color)
            self._bar_skin_cache[key] = texture
        arcade.draw_texture_rect(texture, arcade.XYWH(x + width / 2, y + 8.5, width, 17))
        self.text(label, x + width / 2, y + 8, 11, INK, "center", "center", True,
                  max_width=width - 14, max_height=14, min_size=7)

    def draw_button(self, button: Button) -> None:
        active = button is self.hovered and button.enabled
        if button.enabled:
            color = button.accent
        else:
            color = (53, 60, 70)
        left = button.x - button.width / 2
        key = (int(button.width), int(button.height), tuple(color), active, button.enabled)
        texture = self._button_skin_cache.get(key)
        if texture is None:
            texture = make_button_skin(int(button.width), int(button.height), color,
                                       active, button.enabled)
            self._button_skin_cache[key] = texture
        arcade.draw_texture_rect(
            texture, arcade.XYWH(button.x, button.y, button.width, button.height)
        )
        self.text(button.label, button.x, button.y + 1, 16,
                  INK if button.enabled else (120, 124, 132),
                  "center", "center", True,
                  max_width=button.width - 26, max_height=button.height - 18,
                  min_size=9)

    def log(self, message: str) -> None:
        if self.log_scroll > 0:
            self.log_scroll += 1
        self.messages.append(message)
        self.messages = self.messages[-200:]
        if self.scene == Scene.EVENT:
            self.event_messages.append(message)

    def recent_log_lines(self, width: int = 18, limit: int = 8) -> list[str]:
        return self.wrap_log_lines(self.messages, width, limit)

    @staticmethod
    def wrap_log_lines(messages: list[str], width: int, limit: int) -> list[str]:
        lines: list[str] = []
        for message in messages:
            chunks = [message[index:index + width]
                      for index in range(0, max(1, len(message)), width)]
            lines.extend(chunks or [""])
        return lines[-limit:]

    def measure_text_width(self, value: str, size: int = 11,
                           bold: bool = False) -> float:
        key = (value, size, bold)
        measured = self._measure_cache.get(key)
        if measured is None:
            label = arcade.Text(
                value, 0, 0, INK, size, bold=bold,
                font_name=("Microsoft JhengHei", "Noto Sans CJK TC", "Arial"),
            )
            measured = label.content_width
            self._measure_cache[key] = measured
        return measured

    def wrap_text_pixels(self, value: str, max_width: float,
                         size: int = 11) -> list[str]:
        """Wrap CJK and Latin text by rendered width while preserving each record."""
        lines: list[str] = []
        for paragraph in value.splitlines() or [""]:
            current = ""
            for character in paragraph:
                candidate = current + character
                if current and self.measure_text_width(candidate, size) > max_width:
                    lines.append(current.rstrip())
                    current = character.lstrip()
                else:
                    current = candidate
            lines.append(current or " ")
        return lines

    @staticmethod
    def log_card_style(message: str) -> tuple[str, tuple[int, int, int]]:
        if any(word in message for word in ("暴擊", "傷害", "迎戰", "戰鬥", "先攻", "撲來")):
            return "戰", (216, 76, 65)
        if any(word in message for word in ("詛咒", "劇毒", "毒火", "失去", "失敗", "不足", "GAME")):
            return "危", (180, 68, 126)
        if any(word in message for word in ("恢復", "靈藥", "泉光", "血量增加")):
            return "癒", (70, 174, 119)
        if any(word in message for word in ("獲得", "增加", "升級", "金幣", "經驗", "購買", "折扣", "拾得")):
            return "獲", (231, 177, 72)
        if any(word in message for word in ("黑市", "商人", "紫焰", "貨物", "契印")):
            return "市", (169, 91, 196)
        return "旅", (70, 137, 196)

    def prepared_log_cards(self, text_width: float = 224
                           ) -> list[tuple[str, list[str], tuple[int, int, int], int]]:
        cards: list[tuple[str, list[str], tuple[int, int, int], int]] = []
        for message in reversed(self.messages):
            lines = self.wrap_text_pixels(message, text_width, 11)
            if len(lines) > 2:
                lines = lines[:2]
                clipped = lines[-1].rstrip()
                while clipped and self.measure_text_width(clipped + "…", 11) > text_width:
                    clipped = clipped[:-1]
                lines[-1] = clipped + "…"
            icon, accent = self.log_card_style(message)
            cards.append((icon, lines, accent, 39 if len(lines) == 1 else 55))
        return cards

    @staticmethod
    def max_log_scroll(cards: list[tuple[str, list[str], tuple[int, int, int], int]],
                       available_height: float = 247) -> int:
        used_height = 0.0
        oldest_page_count = 0
        for _icon, _lines, _accent, card_height in reversed(cards):
            next_height = card_height + (5 if oldest_page_count else 0)
            if used_height + next_height > available_height:
                break
            used_height += next_height
            oldest_page_count += 1
        return max(0, len(cards) - oldest_page_count)

    def visible_log_cards(self, text_width: float = 224,
                          available_height: float = 247) -> list[tuple[str, list[str], tuple[int, int, int], int]]:
        prepared = self.prepared_log_cards(text_width)
        maximum = self.max_log_scroll(prepared, available_height)
        self.log_scroll = max(0, min(self.log_scroll, maximum))
        cards: list[tuple[str, list[str], tuple[int, int, int], int]] = []
        used_height = 0.0
        for icon, lines, accent, card_height in prepared[self.log_scroll:]:
            next_height = card_height + (5 if cards else 0)
            if used_height + next_height > available_height:
                break
            cards.append((icon, lines, accent, card_height))
            used_height += next_height
        return cards

    def activity_canvas(self, texture: arcade.Texture, title: str) -> None:
        arcade.draw_texture_rect(texture, arcade.XYWH(760, 417.5, 800, 565))
        arcade.draw_texture_rect(self.activity_frame, arcade.XYWH(760, 417.5, 800, 565))
        self.panel(360, 650, 800, 50, title)

    @property
    def black_market_price(self) -> int:
        return int(self.player.lv * 100 * (1 - .02 * self.player.black_market_lv))

    def track_player_hp(self) -> None:
        """Maintain a display-only HP ceiling for the player health bar."""
        self.player_hp_peak = max(self.player_hp_peak, self.player.hp, 1)

    # ---------- character creation ----------
    def start_creation(self) -> None:
        self.scene = Scene.CREATION
        self.creation_step = 0
        self.selected_sex = "男性"
        self.name_index = 0
        self.name_input = self.NAME_POOLS[self.selected_sex][self.name_index]
        self.configure_buttons()

    def cycle_name(self, direction: int) -> None:
        name_pool = self.NAME_POOLS[self.selected_sex]
        self.name_index = (self.name_index + direction) % len(name_pool)
        self.name_input = name_pool[self.name_index]
        self.configure_buttons()

    def random_name(self) -> None:
        name_pool = self.NAME_POOLS[self.selected_sex]
        available = [name for name in name_pool if name != self.name_input]
        self.name_input = random.choice(available)
        self.name_index = name_pool.index(self.name_input)
        self.configure_buttons()

    def next_creation_step(self) -> None:
        if self.creation_step == 1 and not self.name_input.strip():
            return
        self.creation_step += 1
        self.configure_buttons()

    def choose_sex(self, sex: str) -> None:
        self.selected_sex = sex
        self.name_index = 0
        self.name_input = self.NAME_POOLS[sex][self.name_index]
        self.creation_step = 1
        self.configure_buttons()

    def choose_race(self, race: str) -> None:
        self.selected_race = race
        self.creation_step = 3
        self.configure_buttons()

    def choose_job(self, job: str) -> None:
        self.selected_job = job
        self.creation_step = 4
        self.configure_buttons()

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
        }[p.job]
        p.hp += race_bonus[0] + job_bonus[0]
        p.attack += race_bonus[1] + job_bonus[1]
        p.defense += race_bonus[2] + job_bonus[2]
        p.luck += race_bonus[3] + job_bonus[3]
        self.player = p
        self.player_hp_peak = p.hp
        self.hero_portrait = make_player_portrait(p.sex, p.race, p.job)
        self.messages = [
            f"{p.name}在星火祭壇前立誓，以{p.race}{p.job}之名踏入荒野。",
            "王城的最後一盞烽火，正等待一位英雄回應。",
        ]
        self.log_scroll = 0
        self.journey_lore = random.choice(self.JOURNEY_LORE)
        self.scene = Scene.ADVENTURE
        self.configure_buttons()

    # ---------- journey ----------
    def continue_journey(self) -> None:
        self.journey_lore = random.choice(self.JOURNEY_LORE)
        self.log(self.journey_lore)
        if random.randint(1, 10) <= 3:
            self.resolve_event()
            if self.scene == Scene.EVENT:
                self.configure_buttons()
        else:
            self.start_battle()

    # ---------- black market ----------
    def open_black_market(self) -> None:
        self.scene = Scene.SHOP
        self.shop_lore = random.choice(self.SHOP_LORE)
        self.log("霧巷盡頭亮起紫色燈火，無名黑市為你敞開暗門。")
        self.configure_buttons()

    def leave_black_market(self) -> None:
        self.scene = Scene.ADVENTURE
        self.log("你收好行囊，身後的暗門隨紫焰一同消失。")
        self.check_level_up()
        self.configure_buttons()

    def buy_black_market_item(self, item: int) -> None:
        price = self.black_market_price
        if self.player.gold - price < 0:
            return
        self.player.gold -= price
        p = self.player
        if item == 1:
            p.hp += p.lv * 2
            self.track_player_hp()
            result = f"巨人心血在體內沸騰，血量增加 {p.lv * 2}"
        elif item == 2:
            p.attack += p.lv
            result = f"龍牙烈酒點燃戰意，攻擊增加 {p.lv}"
        elif item == 3:
            p.defense += p.lv
            result = f"玄鐵聖油凝成護膜，防禦增加 {p.lv}"
        elif item == 4:
            p.luck += 1
            result = "星紋骰骨回應命運，幸運增加 1"
        elif item == 5:
            p.potions += 1
            result = "獲得月泉靈藥 1 瓶"
        else:
            p.black_market_lv += 1
            result = "紫焰契印加深一階，往後價格降低 2%"
        self.log(f"購買成功：{result}。")
        if p.gold - self.black_market_price < 0:
            self.log("錢袋的聲音太輕，商人收起貨物，隱入帷幕後方。")
            self.scene = Scene.ADVENTURE
            self.check_level_up()
        self.configure_buttons()

    # ---------- battle ----------
    def monster_rank(self) -> int:
        lv = self.player.lv
        if 4 < lv < 10:
            return random.randint(1, 2)
        if 9 < lv < 15:
            return random.randint(2, 3)
        if 14 < lv < 20:
            return random.randint(3, 4)
        if lv == 20:
            return 5
        return 1

    def start_battle(self) -> None:
        rank = self.monster_rank()
        kind_number = random.randint(1, 3)
        kind = ("血量型", "攻擊型", "防禦型")[kind_number - 1]
        monster_level = self.player.lv + 1
        base = monster_level * rank * self.difficulty
        hp = base * (2 if kind_number == 1 else 1)
        attack = base * (2 if kind_number == 2 else 1)
        defense = base * (2 if kind_number == 3 else 1)
        self.enemy = Enemy(
            self.MONSTER_NAMES[rank][kind], kind, rank, monster_level,
            hp, hp, attack, defense,
        )
        self.enemy_portrait = make_monster_portrait(rank, kind)
        self.scene = Scene.BATTLE
        self.attack_animation = None
        self.floating_damage.clear()
        self.pending_turn = None
        self.battle_delay = 0
        self.auto_battle = False
        battle_omens = {
            1: "枯枝在黑霧中折斷，一雙飢餓的眼睛逼近。",
            2: "沉重腳步震落岩塵，荒野霸主攔住了去路。",
            3: "古戰場的旗幟無風而動，強敵自亡者之間甦醒。",
            4: "天空被巨影遮蔽，王者般的咆哮撕裂群山。",
            5: "猩紅王座升出深淵，終焉之主向世界張開利爪。",
        }
        self.log(battle_omens[rank])
        self.log(f"{self.enemy.name}挾著{kind[:-1]}魔力現身，戰鬥一觸即發！")
        first_turn = random.randint(1, 2)
        if first_turn == 1:
            self.log("星火回應你的意志，你搶得先機。")
        else:
            self.log(f"{self.enemy.name}挾著腥風率先撲來！")
            self.queue_turn("enemy", .35)
        if self.scene == Scene.BATTLE:
            self.configure_buttons()

    @property
    def battle_busy(self) -> bool:
        return self.attack_animation is not None or self.pending_turn is not None

    def queue_turn(self, who: str, delay: float = .32) -> None:
        self.pending_turn = who
        self.battle_delay = delay
        self.configure_buttons()

    def normal_attack(self) -> None:
        if not self.enemy or self.battle_busy:
            return
        critical_roll = random.randint(1, 100)
        critical = critical_roll < self.player.luck * 2
        if critical:
            damage = max(1, math.ceil(self.player.attack * 1.5 - self.enemy.defense))
        else:
            damage = max(1, self.player.attack - self.enemy.defense)
        self.attack_animation = AttackAnimation("player", damage, critical)
        self.configure_buttons()

    def toggle_auto_attack(self) -> None:
        if self.scene != Scene.BATTLE or not self.enemy:
            return
        self.auto_battle = not self.auto_battle
        if self.auto_battle and not self.battle_busy:
            self.queue_turn("player", .18)
        elif not self.auto_battle and self.pending_turn == "player":
            self.pending_turn = None
            self.battle_delay = 0
        self.log("自動攻擊已開啟。" if self.auto_battle else "自動攻擊已停止。")
        self.configure_buttons()

    def drink_potion(self) -> None:
        if self.player.potions < 1 or self.battle_busy or self.auto_battle:
            return
        healing = self.player.lv * 3
        self.player.hp += healing
        self.track_player_hp()
        self.player.potions -= 1
        self.floating_damage.append(FloatingDamage("player", healing, False, True))
        self.log(f"飲下月泉靈藥，銀色泉光恢復 {healing} 點血量。")
        self.queue_turn("enemy")

    def flee(self) -> None:
        if not self.enemy or self.battle_busy or self.auto_battle:
            return
        if random.randint(1, 3) == 1:
            self.log("黑霧封住退路，你只能轉身迎戰！")
            self.queue_turn("enemy")
        else:
            self.log("你借著斷牆陰影脫離戰場，遠處仍傳來怒吼。")
            self.complete_battle()

    def enemy_attack(self) -> None:
        if not self.enemy or self.scene != Scene.BATTLE or self.attack_animation:
            return
        critical = random.randint(1, 5) == 1
        if critical:
            damage = max(1, math.ceil(self.enemy.attack * 1.5 - self.player.defense))
        else:
            damage = max(1, self.enemy.attack - self.player.defense)
        self.attack_animation = AttackAnimation("enemy", damage, critical)
        self.configure_buttons()

    def apply_attack_impact(self) -> None:
        animation = self.attack_animation
        if not animation or animation.impacted:
            return
        animation.impacted = True
        if animation.attacker == "player" and self.enemy:
            self.enemy.hp -= animation.damage
            prefix = "暴擊！" if animation.critical else ""
            self.log(f"{prefix}你對{self.enemy.name}造成 {animation.damage} 點傷害。")
            self.floating_damage.append(
                FloatingDamage("enemy", animation.damage, animation.critical)
            )
        elif animation.attacker == "enemy" and self.enemy:
            self.player.hp -= animation.damage
            prefix = "暴擊！" if animation.critical else ""
            self.log(f"{prefix}{self.enemy.name}造成 {animation.damage} 點傷害。")
            self.floating_damage.append(
                FloatingDamage("player", animation.damage, animation.critical)
            )

    def finish_attack_animation(self) -> None:
        animation = self.attack_animation
        self.attack_animation = None
        if not animation or self.scene != Scene.BATTLE:
            return
        if animation.attacker == "player":
            if self.enemy and self.enemy.hp < 1:
                self.win_battle()
            else:
                self.queue_turn("enemy")
        elif self.player.hp < 1:
            self.finish(False)
        elif self.auto_battle:
            self.queue_turn("player", .28)
        else:
            self.configure_buttons()

    def win_battle(self) -> None:
        if not self.enemy:
            return
        rank = self.enemy.rank
        if rank == 5:
            self.log(f"{self.enemy.name}化為灰燼，{self.player.name}讓黎明重返大地！")
            self.finish(True)
            return
        exp_rewards = {1: 1, 2: 3, 3: 5, 4: 10}
        gold_multipliers = {1: .5, 2: 1, 3: 1.5, 4: 2}
        gained_exp = exp_rewards[rank]
        gained_gold = int(self.player.lv * 50 * gold_multipliers[rank])
        self.player.exp += gained_exp
        self.player.gold += gained_gold
        self.log(f"{self.enemy.name}倒下，靈魂餘燼化為經驗 +{gained_exp}。")
        self.log(f"你從破碎護甲中拾得 {gained_gold}g。")
        self.complete_battle()

    def complete_battle(self) -> None:
        """收束戰鬥，前往下一個旅途場景。"""
        self.enemy = None
        self.auto_battle = False
        self.pending_turn = None
        self.attack_animation = None
        self.check_level_up()
        if self.player.gold >= self.black_market_price:
            self.open_black_market()
        else:
            self.scene = Scene.ADVENTURE
            self.log("紫焰印記沒有回應；你只能繼續走入漫長夜色。")
            self.configure_buttons()

    def check_level_up(self) -> None:
        """結算冒險者的成長。"""
        p = self.player
        if p.exp < p.lv:
            return
        p.lv += 1
        p.exp = 0
        p.hp += p.lv * (4 if p.job == "戰士" else 2)
        p.attack += p.lv * (2 if p.job == "法師" else 1)
        p.defense += p.lv * (2 if p.job == "聖騎士" else 1)
        p.luck += 2 if p.job == "盜賊" else 1
        self.track_player_hp()
        self.log(f"星火淬鍊了你的靈魂，力量提升至 Lv.{p.lv}！")

    # ---------- wilderness events ----------
    def resolve_event(self) -> None:
        p = self.player
        if p.gold - p.lv * 100 < 0:
            event_number = random.randint(2, 4)
        else:
            event_number = random.randint(1, 4)

        self.event_number = event_number
        self.event_title = ("暮鴉行商", "隕星聖痕", "月影靈藥", "無主王匣")[event_number - 1]
        self.event_messages = []
        self.scene = Scene.EVENT

        if event_number == 1:
            items = ("武器", "防具", "飾品")
            units = ("攻擊", "防禦", "幸運")
            choice = random.randint(0, 2)
            cost = p.lv * 100
            p.gold -= cost
            self.log("披羽斗篷的行商自枯樹後現身，肩上暮鴉念著你的名字。")
            self.log(f"他將一件{items[choice]}塞入你手中，收走 {cost}g。")
            outcome = random.randint(0, 2)
            if outcome == 0:
                if choice == 2:
                    p.luck += 2
                    amount = 2
                elif choice == 0:
                    p.attack += p.lv * 2
                    amount = p.lv * 2
                else:
                    p.defense += p.lv * 2
                    amount = p.lv * 2
                self.log(f"古老符文驟然甦醒，{units[choice]}增加 {amount}。")
            elif outcome == 1:
                self.log(f"暮鴉嘲笑一聲；那件{items[choice]}沒有任何魔力。")
            else:
                if choice == 2:
                    p.luck -= 1
                    amount = 1
                elif choice == 0:
                    p.attack -= p.lv
                    amount = p.lv
                else:
                    p.defense -= p.lv
                    amount = p.lv
                self.log(f"詛咒沿著{items[choice]}爬上手臂，{units[choice]}降低 {amount}。")
            return

        if event_number == 2:
            self.log("蒼穹裂開銀色縫隙，一枚隕星在你面前化作聖痕。")
            outcome = random.randint(1, 3)
            if outcome == 1:
                p.exp += p.lv
                self.log(f"群星低聲傳授失落知識，經驗增加 {p.lv}。")
            elif outcome == 2:
                self.log("聖痕如晨露般消散，只留下一縷溫暖星塵。")
            elif p.hp - p.lv * 2 < 1:
                self.log("聖痕驟變為蒼白雷霆，你在星火中倒下。")
                self.finish(False)
            else:
                p.hp -= p.lv * 2
                p.attack -= p.lv
                p.defense -= p.lv
                p.luck -= 1
                self.log("那並非祝福；虛空低語侵入靈魂，所有能力下降。")
            return

        if event_number == 3:
            self.log("月光照亮石祠，一瓶銀藍靈藥懸浮在無名女神掌中。")
            outcome = random.randint(1, 3)
            if outcome == 1:
                healing = p.lv * 3
                p.hp += healing
                self.track_player_hp()
                self.log(f"清涼月華流遍全身，恢復 {healing} 點血量。")
            elif outcome == 2:
                self.log("瓶中只有一滴古老泉水，飲下後沒有任何變化。")
            elif p.hp - p.lv * 2 < 1:
                self.log("幽紫毒霧封住呼吸，你倒在沉默石祠之前。")
                self.finish(False)
            else:
                damage = p.lv * 2
                p.hp -= damage
                self.log(f"靈藥化為灼熱毒火，你失去 {damage} 點血量。")
            return

        self.log("藤蔓深處沉睡著一只王室寶匣，褪色徽記仍泛著金光。")
        outcome = random.randint(1, 3)
        if outcome == 1:
            reward = p.lv * 200
            p.gold += reward
            self.log(f"匣內金幣如凝固陽光，你獲得 {reward}g。")
        elif outcome == 2:
            self.log("寶匣只剩乾枯玫瑰，以及一封無法辨讀的王家密函。")
        else:
            p.gold = 0
            self.log("匣中竄出貪婪妖靈，捲走你身上所有金幣！")

    def leave_event(self) -> None:
        self.check_level_up()
        self.scene = Scene.ADVENTURE
        self.configure_buttons()

    def finish(self, victory: bool) -> None:
        self.victory = victory
        self.scene = Scene.END
        if victory and self.enemy:
            self.final_enemy_name = self.enemy.name
        self.enemy = None
        self.auto_battle = False
        self.pending_turn = None
        self.attack_animation = None
        if not victory:
            self.player.hp = 0
            self.log("GAME OVER")
        self.configure_buttons()

    def replay(self) -> None:
        """Restart immediately with the same name, sex, race, job, and difficulty."""
        self.enemy = None
        self.final_enemy_name = ""
        self.victory = False
        self.auto_battle = False
        self.pending_turn = None
        self.attack_animation = None
        self.floating_damage.clear()
        self.choose_difficulty(self.difficulty)

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
        self.player_hp_peak = self.player.hp
        self.hero_portrait = make_player_portrait("男性", "獸人", "戰士")
        self.enemy = None
        self.final_enemy_name = ""
        self.selected_sex = "男性"
        self.name_index = 0
        self.name_input = self.NAME_POOLS[self.selected_sex][self.name_index]
        self.selected_race = "獸人"
        self.selected_job = "戰士"
        self.difficulty = 1
        self.messages = [
            "黑潮吞沒北境，最後的旅人踏上命運古道。",
            "願星火照亮你的劍鋒。",
        ]
        self.log_scroll = 0
        self.log_scroll_dragging = False
        self.journey_lore = random.choice(self.JOURNEY_LORE)
        self.shop_lore = random.choice(self.SHOP_LORE)
        self.victory = False
        self.auto_battle = False
        self.pending_turn = None
        self.attack_animation = None
        self.floating_damage.clear()
        self.scene = Scene.TITLE
        self.configure_buttons()

    def close_game(self) -> None:
        self.close()

    # ---------- buttons ----------
    def configure_buttons(self) -> None:
        self.buttons.clear()
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
            self.buttons.extend([
                Button(590, 245, 280, 58, "開始遊戲", self.start_creation),
                Button(590, 170, 280, 54, "關閉遊戲", self.close_game,
                       accent=(110, 53, 58)),
            ])
        elif self.scene == Scene.CREATION:
            if self.creation_step == 0:
                self.buttons.extend([
                    Button(475, 300, 190, 58, "男性｜防禦 +5", lambda: self.choose_sex("男性"), "1"),
                    Button(705, 300, 190, 58, "女性｜幸運 +1", lambda: self.choose_sex("女性"), "2"),
                ])
            elif self.creation_step == 1:
                self.buttons.extend([
                    Button(395, 305, 175, 52, "上一個名稱", lambda: self.cycle_name(-1)),
                    Button(590, 305, 175, 52, "隨機名稱", self.random_name),
                    Button(785, 305, 175, 52, "下一個名稱", lambda: self.cycle_name(1)),
                    Button(590, 235, 220, 54, "使用這個名稱", self.next_creation_step),
                ])
            elif self.creation_step == 2:
                for i, (race, bonus) in enumerate(self.RACES):
                    self.buttons.append(Button(345 + i * 165, 300, 150, 58,
                                               f"{race}｜{bonus}",
                                               lambda r=race: self.choose_race(r), str(i + 1)))
            elif self.creation_step == 3:
                for i, (job, _bonus) in enumerate(self.JOBS):
                    self.buttons.append(Button(345 + i * 165, 300, 150, 58, job,
                                               lambda j=job: self.choose_job(j), str(i + 1)))
            else:
                self.buttons.extend([
                    Button(475, 300, 190, 58, "星火遠征｜敵勢平衡",
                           lambda: self.choose_difficulty(1), "1"),
                    Button(705, 300, 190, 58, "黑潮試煉｜敵勢倍增",
                           lambda: self.choose_difficulty(2), "2", accent=(139, 57, 64)),
                ])
            self.buttons.append(Button(590, 170, 180, 42, "回到主頁", self.request_return_home,
                                       accent=(73, 79, 91)))
        elif self.scene == Scene.ADVENTURE:
            self.buttons.extend([
                Button(680, 92, 260, 54, "繼續旅程", self.continue_journey),
                Button(960, 92, 180, 50, "回到主頁", self.request_return_home,
                       accent=(73, 79, 91)),
            ])
        elif self.scene == Scene.BATTLE:
            can_choose = not self.battle_busy and not self.auto_battle
            self.buttons.extend([
                Button(397, 88, 165, 52, "攻擊", self.normal_attack, "1", can_choose),
                Button(575, 88, 165, 52, f"月泉靈藥 ×{p.potions}", self.drink_potion, "2",
                       can_choose and p.potions > 0, accent=(71, 127, 85)),
                Button(753, 88, 165, 52, "逃跑", self.flee, "3", can_choose, accent=(82, 88, 101)),
                Button(970, 88, 205, 52,
                       "停止自動攻擊" if self.auto_battle else "自動攻擊",
                       self.toggle_auto_attack, "4", True,
                       accent=(126, 69, 49) if self.auto_battle else (64, 101, 145)),
            ])
        elif self.scene == Scene.SHOP:
            price = self.black_market_price
            labels = (
                f"巨人心血｜血量 +{p.lv * 2}",
                f"龍牙烈酒｜攻擊 +{p.lv}",
                f"玄鐵聖油｜防禦 +{p.lv}",
                "星紋骰骨｜幸運 +1",
                "月泉靈藥｜戰鬥回血",
                "紫焰契印｜折扣 +2%",
            )
            for i, label in enumerate(labels):
                col, row = i % 3, i // 3
                self.buttons.append(Button(475 + col * 220, 300 - row * 72, 205, 54,
                                           label, lambda n=i + 1: self.buy_black_market_item(n),
                                           str(i + 1), p.gold - price >= 0,
                                           accent=(112, 82, 48)))
            self.buttons.append(Button(755, 105, 180, 48, "離開黑市", self.leave_black_market, "ESC",
                                       accent=(77, 83, 95)))
        elif self.scene == Scene.EVENT:
            self.buttons.append(Button(755, 95, 220, 52, "繼續旅程", self.leave_event, "ENTER"))
        elif self.scene == Scene.END:
            self.buttons.extend([
                Button(650, 105, 210, 54, "重玩", self.replay),
                Button(880, 105, 210, 54, "回到主頁", self.request_return_home,
                       accent=(73, 79, 91)),
            ])

    # ---------- draw scenes ----------
    def on_draw(self) -> None:
        self.clear()
        arcade.draw_texture_rect(self.background, arcade.LBWH(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT))
        if self.scene == Scene.TITLE:
            self.draw_title()
        elif self.scene == Scene.CREATION:
            self.draw_creation()
        else:
            self.draw_game()
        if self.home_confirmation:
            self.draw_home_confirmation()
        for button in self.buttons:
            self.draw_button(button)

    def draw_home_confirmation(self) -> None:
        self.rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, (2, 4, 9, 190))
        self.panel(330, 215, 520, 300, "離開遠征？")
        self.text("要讓這段旅程沉入餘燼嗎？", 590, 430, 25, GOLD,
                  "center", "center", True, max_width=450, max_height=36)
        self.text("返回主頁後，本次冒險進度將無法取回。",
                  590, 380, 15, INK, "center", "center", max_width=450)
        self.text("你也可以留在古道，繼續追尋失落王座。",
                  590, 345, 13, MUTED, "center", "center", max_width=450)

    def draw_title(self) -> None:
        self.rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, (3, 6, 12, 65))
        self.text("餘 燼 王 國", 590, 455, 54, GOLD, "center", "center", True,
                  max_width=920, max_height=70)
        self.text("暮色遠征・失落王座", 590, 395, 21, INK, "center", "center",
                  max_width=760)
        self.text("黑潮越過北境長城，古老王城只剩最後一盞不滅烽火。",
                  590, 342, 16, MUTED, "center", "center", max_width=900)
        self.text("選擇你的血脈與誓約，讓星火再次照亮被遺忘的黎明。",
                  590, 308, 14, MUTED, "center", "center", max_width=900)

    def draw_creation(self) -> None:
        self.panel(165, 145, 850, 455, "建立角色")
        titles = ("選擇性別", "聆聽群星賜名", "選擇種族", "選擇職業", "立下遠征誓約")
        self.text(titles[self.creation_step], 590, 505, 31, INK, "center", "center", True,
                  max_width=760, max_height=45)
        if self.creation_step == 0:
            self.text("血脈將決定群星以何種名字呼喚你。",
                      590, 405, 15, MUTED, "center", "center", max_width=760)
        elif self.creation_step == 1:
            self.panel(410, 365, 360, 62)
            self.text(self.name_input, 590, 396, 24, GOLD, "center", "center", True,
                      max_width=320, max_height=38)
            self.text("名字將被群星銘記，也可能成為荒野最後的傳說。",
                      590, 345, 14, MUTED, "center", "center", max_width=760)
        elif self.creation_step == 3:
            for i, (job, bonus) in enumerate(self.JOBS):
                self.text(f"{i + 1}. {job}：{bonus}", 590, 442 - i * 30, 13, MUTED,
                          "center", "center", max_width=760, max_height=24)
        elif self.creation_step == 4:
            self.text(f"{self.name_input}｜{self.selected_sex}｜{self.selected_race}｜{self.selected_job}",
                      590, 445, 18, GOLD, "center", "center", max_width=760)
            self.text("星火遠征：餘燼仍會庇佑旅人，荒野敵勢維持平衡。",
                      590, 402, 14, INK, "center", "center", max_width=760)
            self.text("黑潮試煉：敵人受黑潮灌注，血量、攻擊與防禦全面倍增。",
                      590, 369, 14, MUTED, "center", "center", max_width=760)

    def draw_game(self) -> None:
        p = self.player
        self.panel(20, 465, 315, 235, "角色資料")
        self.text(f"{p.name}｜{p.sex}", 40, 628, 21, INK, bold=True,
                  max_width=270, max_height=28)
        self.text(f"{p.race}・{p.job}　Lv.{p.lv}", 40, 595, 16, GOLD,
                  max_width=270, max_height=23)
        self.text(f"血量　{p.hp}", 40, 558, 16, RED, bold=True,
                  max_width=270, max_height=23)
        self.text(f"攻擊　{p.attack}　　防禦　{p.defense}", 40, 526, 15, INK,
                  max_width=270, max_height=22)
        self.text(f"幸運　{p.luck}　　金幣　{p.gold}g", 40, 496, 15, INK,
                  max_width=270, max_height=22)
        self.text(f"經驗 {p.exp}/{p.lv}　藥水 {p.potions}", 295, 480, 12, MUTED,
                  "right", "center", max_width=255, max_height=18)

        self.panel(20, 135, 315, 310, "冒險紀錄")
        prepared_logs = self.prepared_log_cards()
        maximum_log_scroll = self.max_log_scroll(prepared_logs)
        self.log_scroll = max(0, min(self.log_scroll, maximum_log_scroll))
        visible_logs = self.visible_log_cards()
        log_cursor = 400.0
        for index, (icon, lines, accent, card_height) in enumerate(visible_logs):
            newest = index == 0 and self.log_scroll == 0
            card_bottom = log_cursor - card_height
            skin_key = (287, card_height, accent, newest)
            texture = self._log_card_skin_cache.get(skin_key)
            if texture is None:
                texture = make_log_card_skin(287, card_height, accent, newest)
                self._log_card_skin_cache[skin_key] = texture
            arcade.draw_texture_rect(
                texture,
                arcade.XYWH(177.5, card_bottom + card_height / 2, 287, card_height),
            )
            self.text(icon, 57, card_bottom + card_height / 2, 10,
                      accent, "center", "center", True,
                      max_width=18, max_height=17, min_size=8)
            line_color = INK if newest else (194, 201, 210)
            if len(lines) == 1:
                self.text(lines[0], 76, card_bottom + card_height / 2, 11,
                          line_color, anchor_y="center",
                          max_width=220, max_height=18, min_size=9)
            else:
                self.text(lines[0], 76, card_bottom + card_height / 2 + 9, 11,
                          line_color, anchor_y="center",
                          max_width=220, max_height=17, min_size=9)
                self.text(lines[1], 76, card_bottom + card_height / 2 - 9, 11,
                          line_color, anchor_y="center",
                          max_width=220, max_height=17, min_size=9)
            log_cursor = card_bottom - 5
        if prepared_logs:
            range_start = self.log_scroll + 1
            range_end = self.log_scroll + len(visible_logs)
            self.text(f"{range_start}–{range_end} / {len(prepared_logs)}",
                      306, 414, 9, MUTED, "right", "center",
                      max_width=88, max_height=14, min_size=8)
        if maximum_log_scroll > 0:
            track_left, track_bottom = 321.0, 152.0
            track_width, track_height = 10, 246
            thumb_height = max(35, int(track_height * len(visible_logs) / len(prepared_logs)))
            thumb_travel = track_height - thumb_height
            scroll_ratio = self.log_scroll / maximum_log_scroll
            thumb_bottom = track_bottom + thumb_travel * (1 - scroll_ratio)
            track_key = ("track", track_width, track_height)
            track_texture = self._scroll_skin_cache.get(track_key)
            if track_texture is None:
                track_texture = make_log_scroll_skin(track_width, track_height, "track")
                self._scroll_skin_cache[track_key] = track_texture
            thumb_key = ("thumb", track_width, thumb_height, self.log_scroll_dragging)
            thumb_texture = self._scroll_skin_cache.get(thumb_key)
            if thumb_texture is None:
                thumb_texture = make_log_scroll_skin(
                    track_width, thumb_height, "thumb", self.log_scroll_dragging
                )
                self._scroll_skin_cache[thumb_key] = thumb_texture
            arcade.draw_texture_rect(
                track_texture,
                arcade.XYWH(track_left + track_width / 2,
                            track_bottom + track_height / 2,
                            track_width, track_height),
            )
            arcade.draw_texture_rect(
                thumb_texture,
                arcade.XYWH(track_left + track_width / 2,
                            thumb_bottom + thumb_height / 2,
                            track_width, thumb_height),
            )
            self._log_scroll_geometry = (
                track_left, track_bottom, track_width, track_height,
                thumb_bottom, float(thumb_height), float(maximum_log_scroll),
                float(max(1, len(visible_logs))),
            )
        else:
            self._log_scroll_geometry = None
            self.log_scroll_dragging = False

        if self.scene == Scene.BATTLE and self.enemy:
            e = self.enemy
            self.activity_canvas(self.battle_background, "戰鬥")
            player_offset = 0.0
            enemy_offset = 0.0
            if self.attack_animation:
                elapsed = self.attack_animation.elapsed
                if elapsed <= .17:
                    motion = math.sin((elapsed / .17) * math.pi / 2)
                else:
                    motion = max(0, 1 - (elapsed - .17) / .31)
                if self.attack_animation.attacker == "player":
                    player_offset = 92 * motion
                else:
                    enemy_offset = -92 * motion
                if self.attack_animation.critical and elapsed >= .17:
                    impact_phase = min(1, (elapsed - .17) / .31)
                    shake = math.sin(impact_phase * math.pi * 8) * 14 * (1 - impact_phase)
                    if self.attack_animation.attacker == "player":
                        enemy_offset += shake
                    else:
                        player_offset += shake
            arcade.draw_texture_rect(self.hero_portrait, arcade.XYWH(555 + player_offset, 435, 255, 255))
            arcade.draw_texture_rect(self.enemy_portrait, arcade.XYWH(950 + enemy_offset, 435, 255, 255))
            self.text("VS", 752, 450, 30, GOLD, "center", "center", True,
                      max_width=80, max_height=42)
            self.text(f"{p.name}｜Lv.{p.lv}", 555, 300, 16, INK, "center", "center", True,
                      max_width=260, max_height=24)
            self.text(f"{e.name}｜Lv.{e.level}", 950, 300, 16, INK,
                      "center", "center", True, max_width=260, max_height=24)
            self.bar(435, 255, 240, p.hp, self.player_hp_peak, GREEN,
                     f"血量 {max(0, p.hp)} / {self.player_hp_peak}")
            self.bar(830, 255, 240, e.hp, e.max_hp, RED, f"血量 {max(0, e.hp)} / {e.max_hp}")
            self.text(f"攻擊 {p.attack}　防禦 {p.defense}", 555, 228, 12, MUTED,
                      "center", "center", max_width=240, max_height=18, min_size=7)
            self.text(f"攻擊 {e.attack}　防禦 {e.defense}", 950, 228, 12, MUTED,
                      "center", "center", max_width=240, max_height=18, min_size=7)
            for floating in self.floating_damage:
                x = 555 if floating.target == "player" else 950
                y = 580 + floating.elapsed * 54
                alpha = int(255 * max(0, 1 - floating.elapsed / .9))
                if floating.critical and not floating.healing and floating.elapsed < .68:
                    burst_phase = floating.elapsed / .68
                    burst_alpha = int(255 * (1 - burst_phase) ** 1.35)
                    burst_size = 185 + 235 * burst_phase
                    burst_angle = (-18 if floating.target == "player" else 18) + burst_phase * 42
                    arcade.draw_texture_rect(
                        self.critical_effect,
                        arcade.XYWH(x, 435, burst_size, burst_size),
                        angle=burst_angle,
                        alpha=burst_alpha,
                    )
                    if burst_phase < .38:
                        echo_phase = burst_phase / .38
                        arcade.draw_texture_rect(
                            self.critical_effect,
                            arcade.XYWH(x, 435, burst_size * (.58 + echo_phase * .28),
                                        burst_size * (.58 + echo_phase * .28)),
                            angle=-burst_angle * .65,
                            alpha=int(burst_alpha * .48),
                        )
                if floating.healing:
                    value, color = f"+{floating.amount}", (*GREEN, alpha)
                else:
                    value = f"{'暴擊 ' if floating.critical else ''}-{floating.amount}"
                    color = (*GOLD, alpha) if floating.critical else (*RED, alpha)
                if floating.label is None:
                    float_size = 31 if floating.critical else 27
                    while True:
                        floating.label = arcade.Text(
                            value, x, y, color, float_size,
                            anchor_x="center", anchor_y="center", bold=True,
                            font_name=("Microsoft JhengHei", "Noto Sans CJK TC", "Arial"),
                        )
                        if floating.label.content_width <= 230 or float_size <= 13:
                            break
                        float_size -= 1
                else:
                    floating.label.x = x
                    floating.label.y = y
                    floating.label.color = color
                floating.label.draw()
        elif self.scene == Scene.SHOP:
            self.activity_canvas(self.shop_background, "黑市")
            self.panel(405, 425, 710, 155)
            self.text(f"黑市等級：{p.black_market_lv}｜折扣：{p.black_market_lv * 2}%",
                      760, 545, 22, GOLD, "center", "center", True,
                      max_width=650, max_height=30)
            self.text(f"所有商品本次價格：{self.black_market_price}g｜持有：{p.gold}g",
                      760, 505, 16, INK, "center", "center",
                      max_width=650, max_height=24)
            self.text(self.shop_lore, 760, 464, 13, MUTED, "center", "center",
                      max_width=650, max_height=22, min_size=10)
        elif self.scene == Scene.EVENT:
            self.activity_canvas(self.event_backgrounds[self.event_number], self.event_title)
            self.panel(405, 165, 710, 150)
            event_lines = self.wrap_log_lines(self.event_messages, width=30, limit=3)
            for index, line in enumerate(event_lines):
                self.text(line, 760, 275 - index * 38, 15, INK, "center", "center",
                          max_width=650, max_height=28, min_size=10)
        elif self.scene == Scene.END:
            self.panel(360, 135, 800, 565)
            self.text("恭 喜 過 關" if self.victory else "G A M E  O V E R",
                      760, 505, 44, GOLD if self.victory else RED, "center", "center", True,
                      max_width=700, max_height=60)
            if self.victory:
                final_name = self.final_enemy_name or "終焉之主"
                self.text(f"{p.name}擊敗{final_name}，讓黎明重返世界！",
                          760, 420, 23, INK, "center", "center",
                          max_width=690, max_height=34)
            else:
                self.text(f"{p.name}倒在了冒險途中。", 760, 420, 23, INK,
                          "center", "center", max_width=690, max_height=34)
            self.text(f"最終等級 Lv.{p.lv}｜攻擊 {p.attack}｜防禦 {p.defense}｜幸運 {p.luck}",
                      760, 350, 16, MUTED, "center", "center",
                      max_width=680, max_height=24, min_size=9)
        else:
            self.panel(360, 135, 800, 565, "冒險")
            arcade.draw_texture_rect(self.hero_portrait, arcade.XYWH(760, 435, 305, 305))
            self.text("命 運 古 道", 760, 263, 22, GOLD, "center", "center", True,
                      max_width=680, max_height=30)
            self.text(self.journey_lore, 760, 225, 14, INK, "center", "center",
                      max_width=670, max_height=23, min_size=10)
            if p.lv < 20:
                self.text(f"王座深處的陰影仍在沉睡，而你的星火已燃至 Lv.{p.lv}。",
                          760, 190, 15, MUTED, "center", "center",
                          max_width=670, max_height=23, min_size=10)
            else:
                self.text("猩紅王座已經甦醒，終焉之主正等待最後一戰！",
                          760, 190, 17, RED, "center", "center", True,
                          max_width=670, max_height=25)

    # ---------- animation and input ----------
    def on_update(self, delta_time: float) -> None:
        for floating in self.floating_damage:
            floating.elapsed += delta_time
        self.floating_damage = [f for f in self.floating_damage if f.elapsed < .9]

        if self.scene != Scene.BATTLE:
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
                elif self.auto_battle:
                    self.normal_attack()

    def log_scroll_available(self) -> bool:
        return (
            not self.home_confirmation
            and self.scene not in (Scene.TITLE, Scene.CREATION)
            and self._log_scroll_geometry is not None
        )

    def on_mouse_scroll(self, x: float, y: float,
                        scroll_x: float, scroll_y: float) -> None:
        if not self.log_scroll_available() or not (20 <= x <= 335 and 135 <= y <= 445):
            return
        maximum = int(self._log_scroll_geometry[6])
        if scroll_y:
            steps = max(1, int(abs(scroll_y)))
            direction = 1 if scroll_y < 0 else -1
            self.log_scroll = max(0, min(maximum, self.log_scroll + direction * steps))

    def on_mouse_motion(self, x: float, y: float, dx: float, dy: float) -> None:
        self.hovered = next((b for b in self.buttons if b.contains(x, y)), None)
        over_scroll = False
        if self.log_scroll_available():
            track_left, track_bottom, track_width, track_height = self._log_scroll_geometry[:4]
            over_scroll = (
                track_left <= x <= track_left + track_width
                and track_bottom <= y <= track_bottom + track_height
            )
        cursor = self.CURSOR_HAND if self.hovered or over_scroll else self.CURSOR_DEFAULT
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
        clicked = next((b for b in self.buttons if b.contains(x, y)), None)
        if clicked:
            clicked.action()
            self.hovered = None

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

    def on_key_press(self, symbol: int, modifiers: int) -> None:
        """Keyboard input is intentionally disabled; the game is mouse-only."""

    def on_text(self, text: str) -> None:
        """Text input is intentionally disabled; names are selected by mouse."""

def main() -> None:
    RPGWindow()
    arcade.run()


if __name__ == "__main__":
    main()
