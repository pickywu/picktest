r"""Skia-rendered dark fantasy art assets for the RPG."""

from __future__ import annotations

import io
import math
import random
from typing import Any, Callable

import arcade
import skia
from PIL import Image


SCREEN_WIDTH = 1180
SCREEN_HEIGHT = 720
SCREEN_TITLE = "餘燼王國：失落王座 V3.0"

INK = (235, 232, 220)
MUTED = (169, 178, 191)
GOLD = (239, 191, 91)
PANEL = (13, 21, 35, 230)
PANEL_EDGE = (75, 96, 124)
RED = (202, 67, 73)
GREEN = (66, 174, 111)
BLUE = (58, 122, 184)

CJK_NO_LINE_START = frozenset("，。！？；：、）》」』】〕〉…—")


def _color(value: tuple[int, ...], alpha: int | None = None) -> int:
    red, green, blue = value[:3]
    opacity = alpha if alpha is not None else (value[3] if len(value) > 3 else 255)
    return skia.ColorSetARGB(int(opacity), int(red), int(green), int(blue))


def _paint(color: tuple[int, ...] = (255, 255, 255, 255), *,
           style: skia.Paint.Style = skia.Paint.kFill_Style,
           width: float = 1.0, shader=None, blur: float = 0.0) -> skia.Paint:
    paint = skia.Paint(AntiAlias=True, Color=_color(color), Style=style,
                       StrokeWidth=width)
    if shader is not None:
        paint.setShader(shader)
    if blur > 0:
        paint.setMaskFilter(
            skia.MaskFilter.MakeBlur(skia.BlurStyle.kNormal_BlurStyle, blur, False)
        )
    if style == skia.Paint.kStroke_Style:
        paint.setStrokeCap(skia.Paint.kRound_Cap)
        paint.setStrokeJoin(skia.Paint.kRound_Join)
    return paint


def _linear(x0: float, y0: float, x1: float, y1: float,
            colors: list[tuple[int, ...]], positions: list[float] | None = None):
    return skia.GradientShader.MakeLinear(
        [(x0, y0), (x1, y1)], [_color(color) for color in colors],
        positions, skia.TileMode.kClamp,
    )


def _radial(x: float, y: float, radius: float,
            colors: list[tuple[int, ...]], positions: list[float] | None = None):
    return skia.GradientShader.MakeRadial(
        (x, y), radius, [_color(color) for color in colors],
        positions, skia.TileMode.kClamp,
    )


def _rect(canvas: skia.Canvas, x: float, y: float, width: float, height: float,
          color: tuple[int, ...], radius: float = 0.0, *, shader=None,
          stroke: tuple[int, ...] | None = None, stroke_width: float = 1.0,
          blur: float = 0.0) -> None:
    rect = skia.Rect.MakeXYWH(x, y, width, height)
    fill = _paint(color, shader=shader, blur=blur)
    if radius:
        canvas.drawRoundRect(rect, radius, radius, fill)
    else:
        canvas.drawRect(rect, fill)
    if stroke:
        outline = _paint(stroke, style=skia.Paint.kStroke_Style, width=stroke_width)
        if radius:
            canvas.drawRoundRect(rect, radius, radius, outline)
        else:
            canvas.drawRect(rect, outline)


def _circle(canvas: skia.Canvas, x: float, y: float, radius: float,
            color: tuple[int, ...], *, shader=None, stroke: tuple[int, ...] | None = None,
            stroke_width: float = 1.0, blur: float = 0.0) -> None:
    canvas.drawCircle(x, y, radius, _paint(color, shader=shader, blur=blur))
    if stroke:
        canvas.drawCircle(x, y, radius,
                          _paint(stroke, style=skia.Paint.kStroke_Style,
                                 width=stroke_width))


def _oval(canvas: skia.Canvas, x: float, y: float, width: float, height: float,
          color: tuple[int, ...], *, shader=None, stroke: tuple[int, ...] | None = None,
          stroke_width: float = 1.0, blur: float = 0.0) -> None:
    rect = skia.Rect.MakeXYWH(x, y, width, height)
    canvas.drawOval(rect, _paint(color, shader=shader, blur=blur))
    if stroke:
        canvas.drawOval(rect, _paint(stroke, style=skia.Paint.kStroke_Style,
                                     width=stroke_width))


def _path(canvas: skia.Canvas, points: list[tuple[float, float]],
          color: tuple[int, ...], *, close: bool = True,
          stroke: tuple[int, ...] | None = None, stroke_width: float = 1.0,
          shader=None, blur: float = 0.0) -> skia.Path:
    path = skia.Path()
    if points:
        path.moveTo(*points[0])
        for point in points[1:]:
            path.lineTo(*point)
        if close:
            path.close()
    if close:
        canvas.drawPath(path, _paint(color, shader=shader, blur=blur))
    if stroke or not close:
        canvas.drawPath(
            path, _paint(stroke or color, style=skia.Paint.kStroke_Style,
                         width=stroke_width, blur=blur)
        )
    return path


def _bezier(canvas: skia.Canvas, start: tuple[float, float],
            curves: list[tuple[float, float, float, float, float, float]],
            color: tuple[int, ...], *, close: bool = False, fill: bool = False,
            width: float = 1.0, blur: float = 0.0, shader=None) -> None:
    path = skia.Path()
    path.moveTo(*start)
    for curve in curves:
        path.cubicTo(*curve)
    if close:
        path.close()
    style = skia.Paint.kFill_Style if fill or close else skia.Paint.kStroke_Style
    canvas.drawPath(path, _paint(color, style=style, width=width,
                                 blur=blur, shader=shader))


def _star(canvas: skia.Canvas, x: float, y: float, outer: float, inner: float,
          color: tuple[int, ...], points: int = 5, rotation: float = -math.pi / 2,
          blur: float = 0.0) -> None:
    vertices = []
    for index in range(points * 2):
        angle = rotation + index * math.pi / points
        radius = outer if index % 2 == 0 else inner
        vertices.append((x + math.cos(angle) * radius,
                         y + math.sin(angle) * radius))
    _path(canvas, vertices, color, blur=blur)


def _glow(canvas: skia.Canvas, x: float, y: float, radius: float,
          color: tuple[int, int, int], alpha: int = 150) -> None:
    shader = _radial(x, y, radius,
                     [(*color, alpha), (*color, alpha // 3), (*color, 0)],
                     [0.0, .38, 1.0])
    _circle(canvas, x, y, radius, (*color, alpha), shader=shader)


def _grain(canvas: skia.Canvas, width: int, height: int, seed: int,
           amount: int = 300, alpha: int = 12) -> None:
    rng = random.Random(seed)
    for _ in range(amount):
        shade = rng.randint(100, 245)
        radius = rng.uniform(.25, 1.15)
        _circle(canvas, rng.uniform(0, width), rng.uniform(0, height), radius,
                (shade, shade, shade, rng.randint(2, alpha)))


def _vignette(canvas: skia.Canvas, width: int, height: int,
              alpha: int = 205) -> None:
    radius = max(width, height) * .72
    shader = _radial(width / 2, height / 2, radius,
                     [(0, 0, 0, 0), (0, 0, 0, 24), (0, 0, 0, alpha)],
                     [0.0, .55, 1.0])
    _rect(canvas, 0, 0, width, height, (0, 0, 0, 0), shader=shader)


def _rune_ring(canvas: skia.Canvas, x: float, y: float, radius: float,
               color: tuple[int, int, int], alpha: int = 110) -> None:
    stroke = (*color, alpha)
    canvas.drawCircle(x, y, radius,
                      _paint(stroke, style=skia.Paint.kStroke_Style, width=1.6))
    canvas.drawCircle(x, y, radius * .77,
                      _paint((*color, alpha // 2), style=skia.Paint.kStroke_Style,
                             width=1.0))
    for index in range(12):
        angle = index * math.tau / 12
        p1 = (x + math.cos(angle) * radius * .82,
              y + math.sin(angle) * radius * .82)
        p2 = (x + math.cos(angle) * radius * .96,
              y + math.sin(angle) * radius * .96)
        _path(canvas, [p1, p2], stroke, close=False, stroke_width=1.3)


def texture_from_skia(width: int, height: int,
                      painter: Callable[[skia.Canvas, int, int], None]) -> arcade.Texture:
    surface = skia.Surface(width, height)
    canvas = surface.getCanvas()
    canvas.clear(skia.ColorTRANSPARENT)
    painter(canvas, width, height)
    image = surface.makeImageSnapshot()
    encoded = image.encodeToData(skia.EncodedImageFormat.kPNG, 100)
    pil_image = Image.open(io.BytesIO(bytes(encoded))).convert("RGBA")
    pil_image.load()
    return arcade.Texture(image=pil_image)


def _mountain_layer(canvas: skia.Canvas, width: int, base_y: float,
                    amplitude: float, color: tuple[int, ...], seed: int,
                    step: int = 85) -> None:
    rng = random.Random(seed)
    points = [(0, base_y)]
    x = -step
    while x < width + step:
        points.append((x, base_y - rng.uniform(amplitude * .35, amplitude)))
        points.append((x + step * .55,
                       base_y - rng.uniform(amplitude * .55, amplitude * 1.15)))
        x += step
    points.extend([(width, base_y), (width, SCREEN_HEIGHT), (0, SCREEN_HEIGHT)])
    _path(canvas, points, color)


def make_background() -> arcade.Texture:
    """A high-detail moonlit kingdom with aurora, citadel, fog and embers."""
    def paint(canvas: skia.Canvas, w: int, h: int) -> None:
        sky = _linear(0, 0, 0, h,
                      [(3, 7, 20), (9, 24, 52), (35, 22, 58), (16, 12, 26)],
                      [0, .38, .72, 1])
        _rect(canvas, 0, 0, w, h, (3, 7, 20), shader=sky)

        # Diffuse aurora veils.
        _bezier(canvas, (-80, 115),
                [(210, 22, 350, 172, 575, 88),
                 (790, 10, 930, 142, 1240, 38)],
                (62, 185, 205, 70), width=48, blur=22)
        _bezier(canvas, (-100, 168),
                [(230, 85, 390, 214, 620, 130),
                 (850, 45, 1000, 184, 1260, 104)],
                (130, 72, 198, 50), width=30, blur=16)

        rng = random.Random(7021)
        for _ in range(155):
            x, y = rng.uniform(20, w - 20), rng.uniform(18, 390)
            brightness = rng.randint(150, 255)
            radius = rng.choice((.45, .65, .9, 1.2))
            _circle(canvas, x, y, radius,
                    (brightness, brightness, min(255, brightness + 20), rng.randint(75, 210)))
        for x, y in ((111, 85), (355, 128), (770, 62), (1032, 174), (923, 92)):
            _glow(canvas, x, y, 13, (125, 186, 255), 48)
            _star(canvas, x, y, 4.5, 1.1, (228, 244, 255, 235), 4)

        # Moon with halo and subtle crater detail.
        moon_x, moon_y, moon_r = 890, 138, 82
        _glow(canvas, moon_x, moon_y, 155, (126, 177, 235), 90)
        moon = _radial(moon_x - 26, moon_y - 28, moon_r * 1.45,
                       [(255, 246, 211), (202, 220, 232), (82, 104, 142)],
                       [0, .54, 1])
        _circle(canvas, moon_x, moon_y, moon_r, (230, 234, 224), shader=moon,
                stroke=(210, 224, 235, 180), stroke_width=1.5)
        for cx, cy, radius in ((-25, -8, 14), (24, 18, 10), (7, -34, 7), (-2, 36, 12)):
            _circle(canvas, moon_x + cx, moon_y + cy, radius,
                    (54, 72, 105, 30), blur=1.2)

        _mountain_layer(canvas, w, 475, 155, (18, 28, 52, 235), 14)
        _mountain_layer(canvas, w, 535, 112, (12, 20, 38, 250), 31, 70)

        # Distant citadel silhouette and illuminated throne tower.
        castle_x = 550
        _glow(canvas, castle_x, 374, 120, (205, 68, 54), 42)
        _rect(canvas, 438, 342, 226, 205, (7, 11, 22, 255))
        for tower_x, tower_w, tower_h in ((410, 60, 150), (478, 72, 225),
                                         (560, 78, 275), (650, 62, 180)):
            top = 542 - tower_h
            _rect(canvas, tower_x, top, tower_w, tower_h, (6, 10, 20, 255))
            _path(canvas, [(tower_x - 8, top), (tower_x + tower_w / 2, top - 48),
                           (tower_x + tower_w + 8, top)], (5, 8, 17, 255))
            for row in range(3):
                wy = top + 34 + row * 42
                _rect(canvas, tower_x + tower_w / 2 - 4, wy, 8, 19,
                      (226, 78, 43, 180), radius=3, blur=2)
        _rect(canvas, 526, 405, 52, 137, (2, 5, 12, 255), radius=22)
        _rune_ring(canvas, 552, 446, 19, (218, 82, 64), 90)

        # Foreground forest spires.
        rng = random.Random(191)
        for x in range(-20, w + 35, 35):
            height = rng.uniform(85, 195)
            _path(canvas, [(x, h), (x + 15, h - height), (x + 31, h)],
                  (3, 8, 15, 255))
            _path(canvas, [(x + 5, h - height * .32), (x + 15, h - height * .78),
                           (x + 27, h - height * .32)], (4, 12, 21, 255))

        # Layered silver fog.
        for index, y in enumerate((522, 575, 626)):
            _bezier(canvas, (-80, y),
                    [(190, y - 45, 310, y + 42, 540, y - 4),
                     (780, y - 52, 970, y + 38, 1260, y - 12)],
                    (105, 132, 166, 28 - index * 5), width=48, blur=18)
        for _ in range(46):
            x, y = rng.uniform(0, w), rng.uniform(500, h)
            _circle(canvas, x, y, rng.uniform(.7, 2.0),
                    (238, 127, 55, rng.randint(55, 155)), blur=.4)

        _grain(canvas, w, h, 801, 720, 10)
        _vignette(canvas, w, h, 218)

    return texture_from_skia(SCREEN_WIDTH, SCREEN_HEIGHT, paint)


def _draw_battle_scene(canvas: skia.Canvas, w: int, h: int) -> None:
    hall = _linear(0, 0, 0, h,
                   [(5, 10, 24), (18, 29, 48), (42, 23, 31), (8, 8, 14)],
                   [0, .52, .78, 1])
    _rect(canvas, 0, 0, w, h, (5, 10, 24), shader=hall)
    _glow(canvas, w / 2, 210, 220, (167, 42, 52), 80)
    # Cathedral ribs and columns.
    for x in (72, 188, 612, 728):
        _rect(canvas, x - 22, 55, 44, 420, (15, 20, 32), radius=6,
              stroke=(82, 91, 116, 150), stroke_width=2)
        _rect(canvas, x - 30, 48, 60, 24, (31, 35, 49), radius=5)
        for y in range(96, 440, 48):
            _rect(canvas, x - 18, y, 36, 6, (91, 73, 69, 90), radius=3)
    for x in (276, 400, 524):
        _path(canvas, [(x - 46, 270), (x, 105), (x + 46, 270)],
              (10, 14, 26), stroke=(81, 102, 138, 105), stroke_width=2)
        _rect(canvas, x - 28, 145, 56, 95, (27, 22, 37), radius=24,
              shader=_linear(x, 145, x, 240,
                             [(88, 30, 53), (22, 18, 34)]))
        _star(canvas, x, 187, 15, 5, (229, 87, 67, 165), 6)
    # Arena floor and central seal.
    floor = _linear(0, 360, 0, h, [(29, 25, 31), (8, 8, 13)])
    _path(canvas, [(0, 352), (800, 352), (800, 565), (0, 565)],
          (20, 18, 24), shader=floor)
    for y in range(382, 565, 34):
        _path(canvas, [(0, y), (800, y)], (119, 101, 98, 32), close=False)
    for x in range(0, 801, 58):
        _path(canvas, [(400, 352), (x, 565)], (112, 94, 92, 26), close=False)
    _glow(canvas, 400, 445, 150, (198, 51, 55), 42)
    _rune_ring(canvas, 400, 446, 116, (211, 78, 62), 80)
    _rune_ring(canvas, 400, 446, 74, (235, 174, 76), 52)
    for x in (112, 688):
        _glow(canvas, x, 315, 50, (255, 113, 37), 80)
        _path(canvas, [(x - 10, 340), (x - 2, 289), (x + 6, 322),
                       (x + 18, 280), (x + 13, 342)], (225, 70, 29, 235))
        _path(canvas, [(x - 4, 336), (x + 2, 300), (x + 8, 335)],
              (255, 205, 76, 245))


def _draw_shop_scene(canvas: skia.Canvas, w: int, h: int) -> None:
    room = _radial(400, 260, 520,
                   [(74, 31, 84), (20, 15, 34), (6, 8, 17)], [0, .55, 1])
    _rect(canvas, 0, 0, w, h, (7, 8, 18), shader=room)
    for shelf_y in (155, 286):
        _rect(canvas, 38, shelf_y, 724, 18, (73, 40, 27), radius=5,
              shader=_linear(38, shelf_y, 762, shelf_y,
                             [(42, 23, 20), (117, 65, 35), (39, 22, 20)]),
              stroke=(185, 119, 53, 100), stroke_width=1.5)
        _rect(canvas, 55, shelf_y + 17, 10, 125, (35, 22, 25))
        _rect(canvas, 735, shelf_y + 17, 10, 125, (35, 22, 25))
    rng = random.Random(727)
    bottle_colors = ((80, 211, 180), (178, 82, 229), (242, 91, 84),
                     (70, 151, 235), (235, 183, 57), (95, 216, 102))
    for row, shelf_y in enumerate((155, 286)):
        for col in range(10):
            x = 72 + col * 67 + rng.uniform(-5, 5)
            height = rng.uniform(38, 70)
            color = bottle_colors[(col + row * 3) % len(bottle_colors)]
            _glow(canvas, x, shelf_y - height / 2, 30, color, 35)
            _rect(canvas, x - 12, shelf_y - height, 24, height, (*color, 155),
                  radius=8, stroke=(220, 231, 244, 100), stroke_width=1)
            _rect(canvas, x - 6, shelf_y - height - 8, 12, 11, (79, 58, 45), radius=2)
            _rect(canvas, x - 7, shelf_y - height * .45, 14, 5,
                  (241, 221, 168, 115), radius=2)
    # Hooded merchant behind the counter.
    _glow(canvas, 400, 305, 115, (144, 56, 184), 65)
    _path(canvas, [(300, 438), (326, 299), (400, 245), (475, 299), (505, 438)],
          (18, 13, 31), shader=_linear(300, 245, 505, 438,
                                      [(72, 32, 91), (16, 12, 28)]),
          stroke=(135, 75, 161, 125), stroke_width=2)
    _path(canvas, [(340, 318), (400, 260), (460, 318), (438, 366), (361, 366)],
          (5, 7, 13))
    _glow(canvas, 378, 326, 13, (193, 86, 247), 120)
    _glow(canvas, 422, 326, 13, (193, 86, 247), 120)
    _circle(canvas, 378, 326, 3, (231, 176, 255))
    _circle(canvas, 422, 326, 3, (231, 176, 255))
    counter = _linear(0, 432, 0, 565, [(87, 48, 29), (31, 20, 21)])
    _rect(canvas, 0, 428, 800, 137, (61, 35, 27), shader=counter,
          stroke=(176, 113, 47, 145), stroke_width=2)
    for x in range(32, 800, 80):
        _path(canvas, [(x, 438), (x - 10, 565)], (210, 145, 66, 30), close=False)
    _star(canvas, 400, 495, 29, 12, (220, 169, 61, 105), 8)


def _draw_campfire_scene(canvas: skia.Canvas, w: int, h: int) -> None:
    sky = _linear(0, 0, 0, h, [(3, 12, 27), (12, 34, 47), (18, 18, 26)])
    _rect(canvas, 0, 0, w, h, (4, 12, 26), shader=sky)
    _glow(canvas, 625, 105, 95, (149, 187, 226), 50)
    _circle(canvas, 625, 105, 47, (218, 229, 226),
            shader=_radial(606, 86, 70, [(255, 249, 220), (138, 169, 196)]))
    rng = random.Random(515)
    for depth in range(3):
        color = ((7, 23, 28), (6, 18, 24), (3, 12, 18))[depth]
        base = 380 + depth * 34
        for x in range(-30, 840, 55 + depth * 8):
            trunk = rng.uniform(10, 20)
            _rect(canvas, x, 80, trunk, base, (*color, 255))
            for branch in range(3):
                cy = 120 + branch * 85 + rng.uniform(-15, 15)
                _path(canvas, [(x + trunk / 2, cy),
                               (x - 56 - branch * 9, cy + 90),
                               (x + trunk / 2, cy + 52),
                               (x + 62 + branch * 8, cy + 96)],
                      (*color, 245), close=False, stroke_width=7 - depth)
    ground = _linear(0, 345, 0, h, [(30, 42, 36), (7, 13, 16)])
    _rect(canvas, 0, 345, w, h - 345, (15, 24, 23), shader=ground)
    # Camp stones and logs.
    for index in range(12):
        angle = index * math.tau / 12
        x, y = 400 + math.cos(angle) * 82, 451 + math.sin(angle) * 34
        _oval(canvas, x - 18, y - 10, 36, 22, (62, 65, 63),
              shader=_linear(x, y - 10, x, y + 12,
                             [(112, 106, 94), (40, 44, 45)]))
    canvas.save()
    canvas.rotate(-18, 400, 468)
    _rect(canvas, 325, 456, 150, 24, (75, 42, 24), radius=12,
          stroke=(145, 82, 36, 130), stroke_width=2)
    canvas.restore()
    canvas.save()
    canvas.rotate(18, 400, 468)
    _rect(canvas, 325, 456, 150, 24, (68, 38, 23), radius=12,
          stroke=(142, 78, 34, 120), stroke_width=2)
    canvas.restore()
    # Multi-layer flame.
    _glow(canvas, 400, 400, 170, (255, 101, 29), 105)
    _path(canvas, [(350, 460), (367, 388), (389, 424), (401, 323),
                   (424, 401), (444, 360), (452, 460)],
          (225, 57, 21), shader=_linear(400, 318, 400, 462,
                                       [(255, 207, 64), (244, 78, 25), (125, 25, 22)]))
    _path(canvas, [(376, 454), (389, 402), (401, 362), (413, 420),
                   (429, 397), (431, 454)], (255, 178, 45),
          shader=_linear(400, 362, 400, 454,
                         [(255, 247, 171), (255, 128, 26)]))
    for _ in range(38):
        x = rng.gauss(400, 38)
        y = rng.uniform(245, 410)
        _circle(canvas, x, y, rng.uniform(.8, 2.6),
                (255, rng.randint(105, 218), 44, rng.randint(80, 220)), blur=.7)


def _draw_event_scene(canvas: skia.Canvas, w: int, h: int, variant: int) -> None:
    palettes = (
        ((4, 19, 26), (23, 72, 70), (121, 181, 121)),
        ((17, 10, 29), (68, 34, 78), (190, 105, 213)),
        ((5, 18, 32), (31, 72, 101), (74, 188, 222)),
        ((22, 13, 14), (92, 42, 31), (233, 135, 54)),
        ((8, 18, 24), (37, 58, 64), (165, 190, 174)),
        ((6, 13, 31), (34, 48, 91), (107, 145, 229)),
        ((16, 11, 25), (60, 36, 79), (185, 92, 220)),
        ((12, 18, 18), (53, 63, 48), (196, 190, 103)),
        ((24, 13, 18), (82, 45, 39), (234, 153, 70)),
        ((5, 25, 22), (26, 81, 65), (117, 224, 151)),
        ((11, 18, 28), (49, 61, 78), (218, 199, 135)),
        ((13, 18, 16), (55, 69, 49), (196, 122, 72)),
        ((12, 16, 25), (54, 65, 88), (149, 217, 217)),
        ((9, 24, 22), (36, 74, 63), (196, 218, 153)),
        ((28, 13, 12), (92, 34, 30), (232, 95, 55)),
        ((9, 13, 29), (45, 41, 86), (133, 177, 255)),
        ((7, 16, 24), (36, 57, 74), (164, 214, 235)),
        ((25, 12, 9), (82, 45, 35), (230, 116, 74)),
    )
    base, mid, accent = palettes[(variant - 1) % len(palettes)]
    _rect(canvas, 0, 0, w, h, (*base, 255),
          shader=_radial(410, 260, 520,
                         [(*mid, 255), (*base, 255), (2, 5, 12, 255)],
                         [0, .62, 1]))
    rng = random.Random(variant * 811)
    # Universal forest / ruin silhouettes.
    for x in range(-30, 850, 62):
        height = rng.uniform(140, 360)
        _path(canvas, [(x, 420), (x + 14, 420 - height), (x + 31, 420)],
              (*base, 245))
    ground = _linear(0, 350, 0, h, [(*mid, 210), (*base, 255)])
    _rect(canvas, 0, 350, w, h - 350, (*base, 255), shader=ground)
    _glow(canvas, 405, 290, 170, accent, 55)

    scene = (variant - 1) % 18
    if scene == 0:  # overturned royal wagon
        _rect(canvas, 250, 300, 300, 125, (67, 39, 27), radius=12,
              stroke=(*accent, 130), stroke_width=2)
        _path(canvas, [(275, 300), (400, 220), (525, 300)], (44, 23, 28),
              stroke=(*accent, 100), stroke_width=2)
        for x in (300, 505):
            _circle(canvas, x, 438, 52, (24, 22, 24), stroke=(130, 93, 55), stroke_width=8)
            _rune_ring(canvas, x, 438, 25, accent, 80)
        _star(canvas, 400, 355, 24, 10, (*accent, 170), 8)
    elif scene == 1:  # ancient gate
        for x in (250, 520):
            _rect(canvas, x, 120, 45, 345, (40, 39, 49), radius=4,
                  stroke=(*accent, 100), stroke_width=2)
        _rect(canvas, 250, 120, 315, 44, (45, 39, 54), radius=5)
        _rune_ring(canvas, 407, 300, 105, accent, 145)
        _glow(canvas, 407, 300, 80, accent, 90)
    elif scene == 2:  # enchanted well
        _oval(canvas, 270, 335, 270, 85, (25, 35, 48), stroke=(*accent, 155), stroke_width=4)
        _rect(canvas, 287, 260, 236, 120, (48, 51, 57), radius=18,
              stroke=(137, 158, 169, 100), stroke_width=2)
        _oval(canvas, 306, 270, 198, 68, (3, 12, 24),
              shader=_radial(405, 300, 100, [(*accent, 190), (4, 12, 24, 255)]))
        _glow(canvas, 405, 294, 110, accent, 90)
    elif scene == 3:  # sacrificial shrine
        _rect(canvas, 285, 390, 240, 58, (57, 46, 41), radius=8)
        _rect(canvas, 322, 300, 166, 95, (69, 54, 44), radius=5,
              stroke=(*accent, 125), stroke_width=2)
        _star(canvas, 405, 345, 44, 17, (*accent, 190), 7)
        for x in (325, 485):
            _glow(canvas, x, 285, 34, accent, 80)
            _path(canvas, [(x - 9, 310), (x, 258), (x + 10, 310)], (*accent, 230))
    elif scene == 4:  # abandoned village
        for index, x in enumerate((145, 315, 505)):
            top = 250 + index * 18
            _rect(canvas, x, top, 145, 180, (25, 31, 34), radius=3)
            _path(canvas, [(x - 18, top), (x + 72, top - 75), (x + 163, top)], (19, 24, 28))
            _rect(canvas, x + 58, top + 72, 30, 52, (*accent, 90), radius=3, blur=3)
        _bezier(canvas, (0, 438), [(210, 400, 490, 500, 800, 420)],
                (180, 198, 192, 45), width=38, blur=16)
    elif scene == 5:  # broken bridge and boat
        _rect(canvas, 0, 380, w, 185, (5, 15, 29),
              shader=_linear(0, 380, 0, 565, [(27, 49, 79), (3, 10, 22)]))
        for x in range(0, 800, 48):
            _path(canvas, [(x, 400), (x + 30, 392), (x + 54, 408)], (*accent, 38), close=False)
        _path(canvas, [(210, 360), (340, 345), (408, 378), (470, 346), (600, 362),
                       (555, 395), (260, 395)], (57, 41, 30))
        _path(canvas, [(405, 350), (405, 235)], (*accent, 180), close=False, stroke_width=4)
        _path(canvas, [(410, 240), (490, 300), (410, 315)], (*accent, 105))
    elif scene == 6:  # crystal mine
        for x, y, height in ((245, 400, 150), (335, 430, 230), (445, 420, 190), (535, 438, 125)):
            _glow(canvas, x, y - height / 2, height * .7, accent, 60)
            _path(canvas, [(x - 30, y), (x - 12, y - height * .72),
                           (x, y - height), (x + 18, y - height * .62), (x + 32, y)],
                  (*accent, 180), stroke=(226, 218, 255, 110), stroke_width=1.5)
        _rune_ring(canvas, 405, 435, 95, accent, 90)
    elif scene == 7:  # knight graveyard
        for index, x in enumerate((180, 300, 420, 545, 650)):
            y = 350 + (index % 2) * 35
            _rect(canvas, x - 18, y - 105, 36, 122, (52, 56, 50), radius=4,
                  stroke=(*accent, 75), stroke_width=1.5)
            _rect(canvas, x - 44, y - 78, 88, 24, (52, 56, 50), radius=3)
            _circle(canvas, x, y - 105, 20, (52, 56, 50))
        _glow(canvas, 410, 270, 120, accent, 52)
        _path(canvas, [(410, 395), (410, 185)], (*accent, 180), close=False, stroke_width=7)
        _path(canvas, [(350, 255), (470, 255)], (*accent, 160), close=False, stroke_width=6)
    elif scene == 8:  # roadside merchant stall
        _path(canvas, [(180, 240), (620, 240), (560, 165), (245, 165)], (78, 34, 32),
              stroke=(*accent, 125), stroke_width=2)
        _rect(canvas, 215, 240, 370, 175, (35, 24, 22), radius=8,
              stroke=(161, 94, 55, 140), stroke_width=2)
        _rect(canvas, 250, 335, 300, 70, (92, 50, 28), radius=8)
        for x, color in ((295, (92, 156, 118)), (360, (105, 70, 151)),
                         (425, (190, 110, 69)), (492, (76, 123, 172))):
            _rect(canvas, x, 282, 32, 66, (*color, 235), radius=10,
                  stroke=(*accent, 110), stroke_width=1.5)
            _circle(canvas, x + 16, 276, 10, (*color, 210))
        _glow(canvas, 405, 300, 120, accent, 70)
    elif scene == 9:  # glowing flower grove
        for x in range(120, 700, 58):
            stem_h = 60 + (x % 4) * 10
            _path(canvas, [(x, 430), (x + 8, 430 - stem_h)], (65, 120, 75), close=False, stroke_width=4)
            _glow(canvas, x + 8, 430 - stem_h, 38, accent, 80)
            for angle in range(0, 360, 72):
                px = x + 8 + math.cos(math.radians(angle)) * 17
                py = 430 - stem_h + math.sin(math.radians(angle)) * 11
                _oval(canvas, px - 9, py - 6, 18, 12, (*accent, 165), blur=.6)
        _bezier(canvas, (70, 360), [(210, 310, 520, 315, 730, 365)],
                (*accent, 55), width=24, blur=10)
    elif scene == 10:  # raven and notice board
        _rect(canvas, 330, 260, 150, 170, (79, 57, 35), radius=5,
              stroke=(*accent, 135), stroke_width=2)
        _rect(canvas, 350, 285, 110, 95, (186, 158, 102), radius=4)
        _rect(canvas, 390, 430, 25, 85, (61, 43, 28), radius=4)
        _path(canvas, [(435, 230), (485, 255), (532, 230), (488, 284)], (9, 10, 14))
        _circle(canvas, 486, 245, 18, (8, 9, 13))
        _path(canvas, [(498, 246), (535, 238), (504, 257)], (*accent, 200))
        _circle(canvas, 492, 240, 3, (*accent, 240))
        for y in (310, 332, 354):
            _path(canvas, [(365, y), (445, y)], (72, 42, 31), close=False, stroke_width=3)
    elif scene == 11:  # hunter trap
        _path(canvas, [(260, 395), (545, 395)], (88, 78, 58), close=False, stroke_width=6)
        for x in range(300, 520, 32):
            _path(canvas, [(x, 395), (x + 16, 340), (x + 32, 395)], (129, 115, 81),
                  close=False, stroke_width=4)
        _circle(canvas, 405, 365, 78, (25, 29, 27), stroke=(*accent, 115), stroke_width=5)
        for angle in range(0, 360, 30):
            px = 405 + math.cos(math.radians(angle)) * 55
            py = 365 + math.sin(math.radians(angle)) * 55
            _path(canvas, [(405, 365), (px, py)], (*accent, 120), close=False, stroke_width=2)
        _glow(canvas, 405, 365, 95, accent, 45)
    elif scene == 12:  # medicine chest
        _rect(canvas, 260, 285, 280, 135, (58, 37, 38), radius=14,
              stroke=(*accent, 145), stroke_width=3)
        _rect(canvas, 295, 245, 210, 70, (79, 49, 45), radius=10)
        _rect(canvas, 380, 300, 42, 92, (*accent, 210), radius=4)
        _rect(canvas, 350, 325, 102, 34, (*accent, 190), radius=4)
        for x in (300, 500):
            _rect(canvas, x, 240, 35, 76, (70, 120, 112), radius=10,
                  stroke=(218, 238, 226, 90), stroke_width=1.5)
        _glow(canvas, 405, 315, 125, accent, 70)
    elif scene == 13:  # elven caravan
        _path(canvas, [(190, 365), (270, 270), (520, 270), (610, 365)], (42, 72, 58),
              stroke=(*accent, 120), stroke_width=2)
        _rect(canvas, 245, 300, 310, 100, (28, 43, 37), radius=14)
        for x in (300, 500):
            _circle(canvas, x, 420, 44, (24, 24, 24), stroke=(*accent, 130), stroke_width=7)
            _rune_ring(canvas, x, 420, 24, accent, 85)
        for x in (305, 380, 455):
            _path(canvas, [(x, 292), (x + 24, 235), (x + 48, 292)], (*accent, 140),
                  stroke=(233, 240, 188, 80), stroke_width=1)
    elif scene == 14:  # orc war drums
        for x, scale in ((285, 1.0), (405, 1.22), (530, 1.0)):
            _oval(canvas, x - 45 * scale, 300, 90 * scale, 44 * scale, (85, 43, 34),
                  stroke=(*accent, 150), stroke_width=4)
            _rect(canvas, x - 43 * scale, 300, 86 * scale, 112 * scale, (55, 35, 31), radius=12)
            _oval(canvas, x - 43 * scale, 390 * scale / scale, 86 * scale, 38 * scale,
                  (38, 26, 24), stroke=(160, 94, 67), stroke_width=3)
        for x in (345, 470):
            _path(canvas, [(x - 35, 235), (x + 45, 310)], (*accent, 180), close=False, stroke_width=6)
            _circle(canvas, x + 52, 318, 12, (*accent, 200))
    elif scene == 15:  # mage manuscript
        _path(canvas, [(245, 260), (388, 235), (405, 405), (260, 435)], (153, 130, 91),
              stroke=(*accent, 115), stroke_width=2)
        _path(canvas, [(410, 405), (430, 235), (565, 260), (550, 435)], (176, 151, 105),
              stroke=(*accent, 115), stroke_width=2)
        _rune_ring(canvas, 405, 335, 86, accent, 155)
        for y in (285, 318, 360):
            _path(canvas, [(292, y), (365, y - 10)], (70, 50, 72), close=False, stroke_width=3)
            _path(canvas, [(445, y - 10), (520, y)], (70, 50, 72), close=False, stroke_width=3)
        _glow(canvas, 405, 335, 135, accent, 75)
    elif scene == 16:  # fog ferry
        _rect(canvas, 0, 360, w, 205, (10, 23, 35),
              shader=_linear(0, 360, 0, 565, [(37, 66, 80), (5, 12, 22)]))
        _path(canvas, [(225, 380), (580, 380), (520, 435), (285, 435)], (51, 39, 31),
              stroke=(*accent, 95), stroke_width=2)
        _path(canvas, [(405, 385), (405, 220)], (*accent, 160), close=False, stroke_width=5)
        _path(canvas, [(410, 230), (510, 300), (410, 330)], (72, 78, 82, 155))
        _circle(canvas, 355, 322, 24, (18, 21, 24))
        _path(canvas, [(337, 345), (375, 345), (395, 405), (315, 405)], (17, 19, 22))
        _bezier(canvas, (20, 330), [(210, 290, 515, 300, 780, 340)],
                (220, 236, 232, 55), width=42, blur=18)
    else:  # dragon bone
        _path(canvas, [(210, 395), (590, 310)], (215, 197, 163), close=False, stroke_width=22)
        for x, y, rot in ((275, 370, -30), (350, 350, -18), (430, 330, -10), (510, 312, 5)):
            canvas.save()
            canvas.rotate(rot, x, y)
            _path(canvas, [(x, y), (x - 38, y - 70)], (207, 188, 151), close=False, stroke_width=13)
            _path(canvas, [(x, y), (x + 38, y + 62)], (207, 188, 151), close=False, stroke_width=13)
            canvas.restore()
        _path(canvas, [(585, 296), (665, 270), (640, 340), (590, 338)], (198, 173, 136),
              stroke=(*accent, 95), stroke_width=2)
        _glow(canvas, 515, 330, 150, accent, 82)

    for _ in range(55):
        _circle(canvas, rng.uniform(25, w - 25), rng.uniform(90, 470),
                rng.uniform(.5, 1.8), (*accent, rng.randint(30, 130)), blur=.5)


def make_activity_background(kind: str, variant: int = 0) -> arcade.Texture:
    def paint(canvas: skia.Canvas, w: int, h: int) -> None:
        if kind == "battle":
            _draw_battle_scene(canvas, w, h)
        elif kind == "shop":
            _draw_shop_scene(canvas, w, h)
        elif kind == "campfire":
            _draw_campfire_scene(canvas, w, h)
        else:
            _draw_event_scene(canvas, w, h, max(1, variant))
        _grain(canvas, w, h, 4100 + variant * 97 + len(kind), 360, 9)
        _vignette(canvas, w, h, 160)
    return texture_from_skia(800, 565, paint)


def player_gear_tier(level: int) -> int:
    return min(5, 1 + max(0, level - 1) // 5)


def _draw_job_emblem(canvas: skia.Canvas, job: str, tier: int,
                     accent: tuple[int, int, int]) -> None:
    if job == "戰士":
        # Greatsword and crimson gem.
        _path(canvas, [(221, 259), (252, 63)], (191, 207, 218), close=False, stroke_width=9)
        _path(canvas, [(241, 76), (263, 45), (259, 84)], (223, 231, 235))
        _path(canvas, [(222, 184), (253, 190)], (219, 174, 76), close=False, stroke_width=8)
        _circle(canvas, 234, 188, 7, (221, 61, 65), stroke=(255, 196, 96), stroke_width=2)
    elif job == "法師":
        _path(canvas, [(233, 260), (245, 75)], (88, 62, 109), close=False, stroke_width=10)
        _glow(canvas, 246, 62, 44, accent, 115)
        _circle(canvas, 246, 62, 22, (*accent, 220),
                shader=_radial(238, 54, 30, [(241, 248, 255), (*accent, 230), (42, 34, 83, 255)]),
                stroke=(220, 230, 255, 180), stroke_width=2)
        _rune_ring(canvas, 246, 62, 34, accent, 115)
    elif job == "聖騎士":
        _path(canvas, [(210, 83), (269, 101), (259, 218), (236, 246),
                       (205, 218)], (83, 97, 118),
              shader=_linear(205, 83, 269, 246,
                             [(196, 207, 214), (68, 80, 103), (28, 37, 58)]),
              stroke=(239, 191, 91, 220), stroke_width=3)
        _path(canvas, [(236, 111), (236, 215)], (244, 208, 105), close=False, stroke_width=8)
        _path(canvas, [(218, 146), (254, 146)], (244, 208, 105), close=False, stroke_width=8)
        _glow(canvas, 236, 151, 45, (244, 208, 105), 55)
    elif job == "術士":
        _glow(canvas, 238, 116, 56, accent, 95)
        _path(canvas, [(236, 258), (236, 82)], (64, 42, 78), close=False, stroke_width=10)
        _circle(canvas, 236, 68, 24, (*accent, 210),
                shader=_radial(229, 60, 38, [(220, 255, 168), (*accent, 230), (30, 20, 45, 255)]),
                stroke=(190, 238, 125, 180), stroke_width=2)
        _rune_ring(canvas, 236, 68, 40, accent, 120)
        for angle in (math.radians(25), math.radians(155), math.radians(270)):
            x = 236 + math.cos(angle) * 42
            y = 68 + math.sin(angle) * 33
            _circle(canvas, x, y, 5, (168, 238, 104, 210), blur=1)
    else:
        for offset, angle in ((0, -18), (24, 14)):
            canvas.save()
            canvas.rotate(angle, 228 + offset, 164)
            _path(canvas, [(221 + offset, 254), (226 + offset, 85),
                           (236 + offset, 54), (241 + offset, 90),
                           (235 + offset, 254)], (173, 191, 198),
                  shader=_linear(221 + offset, 54, 241 + offset, 254,
                                 [(229, 238, 238), (68, 87, 96)]),
                  stroke=(*accent, 175), stroke_width=2)
            canvas.restore()
    if tier >= 4:
        _glow(canvas, 236, 151, 78, accent, 38)


def make_player_portrait(sex: str, race: str, job: str, level: int = 1) -> arcade.Texture:
    def paint(canvas: skia.Canvas, w: int, h: int) -> None:
        tier = player_gear_tier(level)
        class_colors = {
            "戰士": (190, 64, 62), "法師": (85, 139, 224),
            "聖騎士": (232, 187, 78), "盜賊": (145, 89, 190),
            "術士": (114, 177, 77),
        }
        accent = class_colors[job]
        race_skin = {
            "獸人": (105, 147, 82), "人類": (203, 157, 125),
            "矮人": (184, 127, 91), "精靈": (177, 165, 139),
        }
        skin = race_skin[race]
        # Keep the portrait canvas transparent so the activity scene remains visible.
        _glow(canvas, 150, 143, 124, accent, 62)
        _rune_ring(canvas, 150, 145, 125, accent, 90)
        _circle(canvas, 150, 145, 112, (0, 0, 0, 0),
                stroke=(*accent, 125), stroke_width=2)
        for index in range(8):
            angle = index * math.tau / 8 + math.pi / 8
            _star(canvas, 150 + math.cos(angle) * 125,
                  145 + math.sin(angle) * 125, 5, 2, (*accent, 155), 4)

        _draw_job_emblem(canvas, job, tier, accent)
        # Cloak and torso.
        cloak = _linear(55, 150, 245, 280,
                        [(18, 22, 36), (*accent, 115), (9, 12, 23)], [0, .45, 1])
        _path(canvas, [(54, 286), (66, 205), (98, 168), (150, 151),
                       (207, 171), (245, 286)], (19, 23, 38), shader=cloak,
              stroke=(116, 132, 161, 110), stroke_width=2)
        armor = _linear(95, 165, 205, 285,
                        [(168, 178, 186), (62, 73, 92), (24, 30, 47)])
        if tier == 1:
            armor = _linear(95, 165, 205, 285,
                            [(*accent, 155), (48, 42, 57), (18, 22, 34)])
        _path(canvas, [(95, 280), (101, 184), (150, 161), (201, 185), (207, 280)],
              (74, 77, 91), shader=armor, stroke=(*accent, 145), stroke_width=2.4)
        # Pauldrons with tier-based ornament.
        for side in (-1, 1):
            cx = 150 + side * 70
            _oval(canvas, cx - 43, 168, 86, 52, (61, 72, 91),
                  shader=_linear(cx - 40, 170, cx + 38, 218,
                                 [(191, 202, 210), (55, 65, 85), (19, 25, 42)]),
                  stroke=(*accent, 185), stroke_width=2.5)
            if tier >= 3:
                _path(canvas, [(cx - side * 9, 170), (cx + side * 27, 145),
                               (cx + side * 22, 188)], (189, 201, 210),
                      stroke=(*accent, 150), stroke_width=1.5)
            _star(canvas, cx, 194, 9, 3.8, (*accent, 195), 6)
        # Chest sigil.
        _glow(canvas, 150, 217, 32, accent, 50)
        _star(canvas, 150, 218, 18 + tier, 7, (*accent, 210), 6)
        _circle(canvas, 150, 218, 5, (247, 223, 157), blur=1)

        # Neck and face.
        _rect(canvas, 132, 132, 36, 48, (*skin, 255), radius=13)
        face_shader = _radial(132, 91, 78,
                              [(min(255, skin[0] + 40), min(255, skin[1] + 35), min(255, skin[2] + 28)),
                               (*skin, 255), (74, 55, 52, 255)], [0, .65, 1])
        _oval(canvas, 103, 47, 94, 120, (*skin, 255), shader=face_shader,
              stroke=(55, 45, 48, 150), stroke_width=1.5)

        # Race silhouettes.
        if race == "精靈":
            _path(canvas, [(109, 82), (60, 62), (103, 105)], (*skin, 255),
                  stroke=(95, 76, 76, 150), stroke_width=1.5)
            _path(canvas, [(191, 82), (240, 62), (197, 105)], (*skin, 255),
                  stroke=(95, 76, 76, 150), stroke_width=1.5)
        elif race == "獸人":
            for side in (-1, 1):
                _path(canvas, [(150 + side * 19, 135), (150 + side * 31, 156),
                               (150 + side * 12, 145)], (236, 220, 171),
                      stroke=(83, 62, 51, 160), stroke_width=1)
            _path(canvas, [(112, 63), (94, 42), (120, 52)], (70, 94, 61))
            _path(canvas, [(188, 63), (206, 42), (180, 52)], (70, 94, 61))
        elif race == "矮人":
            beard = _linear(116, 112, 184, 187,
                             [(91, 48, 29), (49, 27, 24), (22, 17, 19)])
            _path(canvas, [(111, 112), (119, 167), (150, 190), (181, 167), (190, 112),
                           (169, 139), (150, 130), (131, 139)], (62, 35, 26), shader=beard,
                  stroke=(151, 84, 43, 120), stroke_width=1.5)
            for x in (132, 150, 168):
                _bezier(canvas, (x, 130), [(x - 7, 149, x + 7, 163, x, 180)],
                        (185, 106, 51, 135), width=2)

        # Hair / helm crown.
        hair_color = (29, 24, 31) if sex == "男性" else (51, 32, 45)
        _path(canvas, [(103, 88), (108, 48), (128, 31), (150, 27),
                       (177, 34), (195, 61), (196, 91), (181, 67),
                       (158, 55), (132, 58), (113, 78)], (*hair_color, 255),
              stroke=(*accent, 75), stroke_width=1.2)
        if sex == "女性":
            _path(canvas, [(109, 67), (91, 118), (103, 168), (118, 126)],
                  (*hair_color, 255))
            _path(canvas, [(191, 67), (211, 118), (198, 168), (181, 126)],
                  (*hair_color, 255))
        if tier >= 5:
            _path(canvas, [(110, 55), (120, 20), (143, 42), (150, 9),
                           (158, 42), (182, 20), (192, 57)], (84, 91, 106),
                  shader=_linear(110, 10, 192, 58,
                                 [(246, 211, 111), (92, 101, 126)]),
                  stroke=(255, 220, 121, 210), stroke_width=2)

        # Eyes, brows and facial detail.
        eye_color = (235, 91, 60) if race == "獸人" else ((100, 223, 255) if race == "精靈" else accent)
        for side in (-1, 1):
            ex = 150 + side * 20
            _path(canvas, [(ex - 9, 92), (ex, 87), (ex + 9, 92)],
                  (52, 37, 42), close=False, stroke_width=2.2)
            _glow(canvas, ex, 96, 9, eye_color, 70)
            _oval(canvas, ex - 7, 91, 14, 8, (238, 231, 211))
            _circle(canvas, ex, 95, 3.5, (*eye_color, 255))
            _circle(canvas, ex - 1, 94, 1.1, (255, 255, 255))
        _path(canvas, [(146, 101), (141, 121), (151, 125), (158, 121)],
              (89, 58, 55, 125), close=False, stroke_width=1.4)
        _bezier(canvas, (132, 139), [(143, 147, 158, 147, 169, 138)],
                (87, 43, 48, 190), width=2)

    return texture_from_skia(300, 300, paint)


def _monster_palette(rank: int, kind: str) -> tuple[tuple[int, int, int], ...]:
    rank_palettes = {
        1: ((89, 139, 79), (151, 79, 55), (76, 100, 111)),
        2: ((116, 86, 66), (171, 72, 50), (75, 83, 106)),
        3: ((72, 119, 82), (172, 57, 72), (76, 91, 126)),
        4: ((63, 105, 104), (145, 67, 192), (71, 88, 112)),
        5: ((76, 51, 95), (194, 45, 55), (56, 72, 102)),
        6: ((45, 35, 71), (225, 49, 70), (39, 64, 98)),
    }
    base = rank_palettes[min(6, rank)]
    index = {"血量型": 0, "攻擊型": 1, "防禦型": 2}[kind]
    primary = base[index]
    accent = ((118, 232, 151) if kind == "血量型" else
              (255, 94, 67) if kind == "攻擊型" else (99, 177, 235))
    shadow = tuple(max(5, int(channel * .26)) for channel in primary)
    highlight = tuple(min(255, int(channel * 1.55 + 25)) for channel in primary)
    return primary, accent, shadow, highlight


def _monster_eye(canvas: skia.Canvas, x: float, y: float, radius: float,
                 accent: tuple[int, int, int]) -> None:
    _glow(canvas, x, y, radius * 4.8, accent, 95)
    _oval(canvas, x - radius * 1.7, y - radius, radius * 3.4, radius * 2,
          (14, 10, 15), stroke=(*accent, 180), stroke_width=1.2)
    _circle(canvas, x, y, radius, (*accent, 255))
    _circle(canvas, x - radius * .28, y - radius * .3, radius * .3,
            (255, 255, 238))


def _monster_horn(canvas: skia.Canvas, start: tuple[float, float],
                  end: tuple[float, float], width: float,
                  flip: float = 1.0) -> None:
    sx, sy = start
    ex, ey = end
    midx = (sx + ex) / 2 + flip * 12
    midy = (sy + ey) / 2 - 9
    path = skia.Path()
    path.moveTo(sx - width, sy)
    path.quadTo(midx, midy, ex, ey)
    path.quadTo(midx - flip * 4, midy + 10, sx + width, sy)
    path.close()
    shader = _linear(sx, sy, ex, ey,
                     [(78, 65, 56), (210, 195, 151), (63, 49, 48)])
    canvas.drawPath(path, _paint((140, 125, 102), shader=shader))
    canvas.drawPath(path, _paint((232, 211, 166, 110),
                                 style=skia.Paint.kStroke_Style, width=1.2))


def make_monster_portrait(rank: int, kind: str) -> arcade.Texture:
    """Distinct Skia monsters by rank and combat archetype."""
    def paint(canvas: skia.Canvas, w: int, h: int) -> None:
        primary, accent, shadow, highlight = _monster_palette(rank, kind)
        # Keep the portrait canvas transparent so monsters blend into the scene.
        _glow(canvas, 150, 142, 130, accent, 55 + rank * 7)
        _rune_ring(canvas, 150, 145, 128, accent, 65 + rank * 8)
        _oval(canvas, 42, 242, 216, 36, (0, 0, 0, 145), blur=8)

        if kind == "血量型":
            # Massive organic ancient with plated belly and tendrils.
            body = _radial(116, 106, 142,
                           [(*highlight, 255), (*primary, 255), (*shadow, 255)],
                           [0, .55, 1])
            _oval(canvas, 55, 61, 190, 205, (*primary, 255), shader=body,
                  stroke=(*accent, 130), stroke_width=2)
            for index in range(5 + rank // 2):
                angle = -math.pi + index * math.pi / max(1, 4 + rank // 2)
                sx = 150 + math.cos(angle) * 72
                sy = 186 + math.sin(angle) * 40
                ex = 150 + math.cos(angle) * (105 + rank * 4)
                ey = 213 + math.sin(angle) * (68 + rank * 3)
                _bezier(canvas, (sx, sy),
                        [((sx + ex) / 2 + math.sin(angle) * 18, (sy + ey) / 2,
                          ex - math.cos(angle) * 16, ey - 8, ex, ey)],
                        (*primary, 240), width=10 + rank * .6)
            # Belly plates.
            for row in range(4):
                radius = 56 - row * 7
                y = 136 + row * 28
                _bezier(canvas, (150 - radius, y),
                        [(150 - radius / 2, y + 18, 150 + radius / 2, y + 18,
                          150 + radius, y)], (*highlight, 95), width=3)
            if rank <= 2:
                _monster_eye(canvas, 122, 112, 5, accent)
                _monster_eye(canvas, 178, 112, 5, accent)
            else:
                for x, y in ((115, 105), (150, 92), (185, 105)):
                    _monster_eye(canvas, x, y, 4.5, accent)
            _bezier(canvas, (105, 142), [(130, 163, 171, 163, 196, 142)],
                    (32, 15, 23), width=7)
        elif kind == "攻擊型":
            # Lean draconic predator with blades, wings and aggressive horns.
            for side in (-1, 1):
                wing = [(150 + side * 18, 140), (150 + side * 76, 61),
                        (150 + side * 122, 91), (150 + side * 82, 151),
                        (150 + side * 126, 194), (150 + side * 39, 184)]
                _path(canvas, wing, (*shadow, 250),
                      shader=_linear(150, 70, 150 + side * 120, 194,
                                     [(*primary, 240), (*shadow, 250)]),
                      stroke=(*accent, 115), stroke_width=2)
                for rib in range(1, 4):
                    _path(canvas, [(150 + side * 28, 145),
                                   (150 + side * (50 + rib * 18), 78 + rib * 30)],
                          (*highlight, 75), close=False, stroke_width=2)
            torso = _linear(100, 70, 202, 254,
                             [(*highlight, 255), (*primary, 255), (*shadow, 255)])
            _path(canvas, [(94, 240), (105, 108), (132, 72), (150, 58),
                           (171, 75), (198, 112), (210, 241)],
                  (*primary, 255), shader=torso, stroke=(*accent, 160), stroke_width=2)
            # Long jaw.
            _path(canvas, [(104, 107), (150, 77), (199, 108), (183, 158),
                           (150, 176), (116, 158)], (*primary, 255),
                  shader=_radial(130, 98, 92,
                                 [(*highlight, 255), (*primary, 255), (*shadow, 255)]),
                  stroke=(*accent, 130), stroke_width=2)
            _monster_horn(canvas, (118, 91), (60 - rank * 3, 32), 9, -1)
            _monster_horn(canvas, (182, 91), (240 + rank * 3, 32), 9, 1)
            _monster_eye(canvas, 128, 119, 5.2, accent)
            _monster_eye(canvas, 174, 119, 5.2, accent)
            _bezier(canvas, (124, 151), [(140, 165, 164, 165, 181, 149)],
                    (18, 9, 15), width=6)
            for x in (134, 150, 166):
                _path(canvas, [(x - 5, 153), (x, 168), (x + 5, 153)],
                      (231, 221, 187))
            # Claws.
            for side in (-1, 1):
                for claw in range(3):
                    x = 150 + side * (69 + claw * 10)
                    _monster_horn(canvas, (x, 218), (x + side * 28, 252), 4, side)
        else:
            # Armoured rune colossus.
            _path(canvas, [(54, 252), (66, 117), (101, 73), (150, 54),
                           (201, 75), (236, 118), (247, 252)], (*shadow, 255),
                  shader=_linear(54, 54, 247, 252,
                                 [(*highlight, 255), (*primary, 255), (*shadow, 255)]),
                  stroke=(*accent, 155), stroke_width=3)
            # Huge plate shoulders.
            for side in (-1, 1):
                cx = 150 + side * 75
                _path(canvas, [(cx - 50, 165), (cx - 38, 104), (cx, 78),
                               (cx + 42, 110), (cx + 50, 178), (cx, 194)],
                      (*primary, 255), shader=_linear(cx - 45, 85, cx + 45, 194,
                                                     [(*highlight, 255), (*shadow, 255)]),
                      stroke=(*accent, 145), stroke_width=2)
                _star(canvas, cx, 135, 15, 6, (*accent, 150), 6)
            # Helmet and slit.
            _path(canvas, [(101, 134), (112, 72), (150, 43), (190, 73),
                           (201, 134), (184, 169), (116, 169)], (*primary, 255),
                  shader=_linear(105, 48, 198, 169,
                                 [(*highlight, 255), (*primary, 255), (*shadow, 255)]),
                  stroke=(*accent, 160), stroke_width=2.5)
            _rect(canvas, 116, 111, 69, 20, (7, 11, 19), radius=7,
                  stroke=(*accent, 150), stroke_width=1.5)
            _glow(canvas, 150, 121, 44, accent, 80)
            _rect(canvas, 124, 118, 52, 5, (*accent, 245), radius=2, blur=1)
            _rune_ring(canvas, 150, 211, 34, accent, 125)
            for row in range(3):
                _rect(canvas, 115 + row * 5, 174 + row * 24,
                      70 - row * 10, 17, (*highlight, 75), radius=5,
                      stroke=(*accent, 70), stroke_width=1)

        # Rank escalation: crown horns, orbiting shards and god-eye.
        if rank >= 3:
            for side in (-1, 1):
                _monster_horn(canvas, (150 + side * 34, 66),
                              (150 + side * (65 + rank * 5), 14 + rank * 2),
                              7 + rank, side)
        if rank >= 4:
            for index in range(6 + rank):
                angle = index * math.tau / (6 + rank)
                x = 150 + math.cos(angle) * 128
                y = 145 + math.sin(angle) * 119
                canvas.save()
                canvas.rotate(math.degrees(angle) + 90, x, y)
                _path(canvas, [(x - 5, y + 12), (x, y - 14), (x + 5, y + 12)],
                      (*accent, 150), stroke=(235, 242, 255, 80), stroke_width=1)
                canvas.restore()
        if rank >= 5:
            _glow(canvas, 150, 42, 56, accent, 105)
            _monster_eye(canvas, 150, 42, 7, accent)
        if rank >= 6:
            _rune_ring(canvas, 150, 145, 142, accent, 180)
            for index in range(10):
                angle = index * math.tau / 10
                _bezier(canvas, (150 + math.cos(angle) * 90,
                                 145 + math.sin(angle) * 90),
                        [(150 + math.cos(angle + .25) * 145,
                          145 + math.sin(angle + .25) * 145,
                          150 + math.cos(angle - .18) * 155,
                          145 + math.sin(angle - .18) * 155,
                          150 + math.cos(angle) * 170,
                          145 + math.sin(angle) * 170)],
                        (*accent, 80), width=3, blur=2)

    return texture_from_skia(300, 300, paint)


def make_critical_effect() -> arcade.Texture:
    def paint(canvas: skia.Canvas, w: int, h: int) -> None:
        cx, cy = w / 2, h / 2
        _glow(canvas, cx, cy, 164, (255, 68, 40), 130)
        rng = random.Random(9127)
        for index in range(28):
            angle = index * math.tau / 28 + rng.uniform(-.035, .035)
            inner = rng.uniform(28, 48)
            outer = rng.uniform(115, 172)
            width = rng.uniform(.025, .07)
            points = [(cx + math.cos(angle - width) * inner,
                       cy + math.sin(angle - width) * inner),
                      (cx + math.cos(angle) * outer,
                       cy + math.sin(angle) * outer),
                      (cx + math.cos(angle + width) * inner,
                       cy + math.sin(angle + width) * inner)]
            ray = _linear(cx, cy, cx + math.cos(angle) * outer,
                          cy + math.sin(angle) * outer,
                          [(255, 244, 178, 225), (255, 90, 35, 140), (255, 42, 22, 0)])
            _path(canvas, points, (255, 90, 35, 160), shader=ray)
        for radius, alpha, width in ((116, 180, 3), (82, 210, 4), (49, 235, 5)):
            canvas.drawCircle(cx, cy, radius,
                              _paint((255, 188, 64, alpha),
                                     style=skia.Paint.kStroke_Style, width=width))
        _star(canvas, cx, cy, 73, 26, (255, 236, 155, 235), 12, rotation=-math.pi / 12)
        _star(canvas, cx, cy, 45, 17, (255, 86, 34, 245), 8)
        _circle(canvas, cx, cy, 18, (255, 250, 218, 245), blur=3)
        for index in range(16):
            angle = index * math.tau / 16 + .12
            radius = rng.uniform(95, 150)
            x, y = cx + math.cos(angle) * radius, cy + math.sin(angle) * radius
            _star(canvas, x, y, rng.uniform(3, 8), 1.5,
                  (255, rng.randint(110, 220), 46, rng.randint(120, 235)), 4,
                  rotation=angle)
    return texture_from_skia(360, 360, paint)


def make_panel_skin(width: int, height: int) -> arcade.Texture:
    def paint(canvas: skia.Canvas, w: int, h: int) -> None:
        _glow(canvas, w * .5, h * .45, max(w, h) * .54, (39, 89, 137), 30)
        panel = _linear(0, 0, w, h,
                        [(19, 31, 50, 244), (7, 14, 27, 247), (24, 14, 33, 248)])
        _rect(canvas, 5, 5, w - 10, h - 10, (10, 18, 31, 245), 11, shader=panel,
              stroke=(82, 110, 143, 190), stroke_width=2)
        _rect(canvas, 10, 10, w - 20, h - 20, (0, 0, 0, 0), 8,
              stroke=(228, 178, 76, 80), stroke_width=1)
        # Art-deco corner filigree.
        for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
            ox = 17 if sx > 0 else w - 17
            oy = 17 if sy > 0 else h - 17
            _path(canvas, [(ox, oy + sy * 19), (ox, oy), (ox + sx * 19, oy)],
                  (231, 183, 78, 145), close=False, stroke_width=2)
            _path(canvas, [(ox + sx * 5, oy + sy * 14),
                           (ox + sx * 14, oy + sy * 5)],
                  (92, 151, 192, 115), close=False, stroke_width=1.2)
        _grain(canvas, w, h, w * 37 + h * 13, max(20, w * h // 1800), 7)
    return texture_from_skia(width, height, paint)


def make_button_skin(width: int, height: int, accent: tuple[int, int, int],
                     active: bool, enabled: bool, decorated: bool = True) -> arcade.Texture:
    def paint(canvas: skia.Canvas, w: int, h: int) -> None:
        base = accent if enabled else (53, 58, 66)
        if active and enabled:
            _glow(canvas, w / 2, h / 2, w * .55, base, 105)
        else:
            _glow(canvas, w / 2, h / 2, w * .5, base, 32)
        top = tuple(min(255, channel + (85 if active else 42)) for channel in base)
        bottom = tuple(max(8, int(channel * .34)) for channel in base)
        face = _linear(0, 4, 0, h - 4,
                       [(*top, 255), (*base, 255), (*bottom, 255)], [0, .48, 1])
        _rect(canvas, 5, 5, w - 10, h - 10, (*base, 255), 10, shader=face,
              stroke=(194, 220, 238, 220 if active else 145),
              stroke_width=2.2 if active else 1.7)
        gloss = _linear(0, 7, 0, h * .56,
                        [(255, 255, 255, 95 if enabled else 24),
                         (255, 255, 255, 0)])
        _rect(canvas, 10, 8, w - 20, max(5, h * .40), (255, 255, 255, 0), 6,
              shader=gloss)
        _rect(canvas, 9, 9, w - 18, h - 18, (0, 0, 0, 0), 7,
              stroke=(255, 240, 196, 52 if enabled else 18), stroke_width=1)
        if decorated:
            for x in (16, w - 16):
                _star(canvas, x, h / 2, 5, 2, (240, 190, 78, 190 if enabled else 60), 4)
                if active:
                    _glow(canvas, x, h / 2, 10, (240, 190, 78), 75)
    return texture_from_skia(width, height, paint)


def make_bar_skin(width: int, height: int, ratio: float,
                  color: tuple[int, ...]) -> arcade.Texture:
    def paint(canvas: skia.Canvas, w: int, h: int) -> None:
        _rect(canvas, 1, 1, w - 2, h - 2, (3, 8, 15, 225), h / 2,
              stroke=(132, 158, 184, 145), stroke_width=1.2)
        fill_width = max(0, (w - 6) * ratio)
        if fill_width > 1:
            rgb = tuple(color[:3])
            bright = tuple(min(255, channel + 78) for channel in rgb)
            dark = tuple(max(5, int(channel * .45)) for channel in rgb)
            meter = _linear(0, 2, 0, h - 2,
                            [(*bright, 255), (*rgb, 255), (*dark, 255)])
            _rect(canvas, 3, 3, fill_width, h - 6, (*rgb, 255), (h - 6) / 2,
                  shader=meter)
            _rect(canvas, 7, 4, max(0, fill_width - 10), 2,
                  (255, 255, 255, 82), 1)
            _glow(canvas, 3 + fill_width, h / 2, min(18, h), rgb, 48)
    return texture_from_skia(width, height, paint)


def make_log_card_skin(width: int, height: int, accent: tuple[int, int, int],
                       newest: bool) -> arcade.Texture:
    def paint(canvas: skia.Canvas, w: int, h: int) -> None:
        if newest:
            _glow(canvas, w * .4, h / 2, w * .55, accent, 48)
        card = _linear(0, 0, w, h,
                       [(15, 29, 47, 245), (6, 13, 25, 248), (17, 11, 25, 248)])
        _rect(canvas, 2, 2, w - 4, h - 4, (7, 15, 27, 245), 8, shader=card,
              stroke=(*accent, 190 if newest else 95),
              stroke_width=1.8 if newest else 1.0)
        rail = _linear(3, 0, 22, 0,
                       [(*accent, 230), (*accent, 45), (*accent, 0)])
        _rect(canvas, 4, 6, 28, h - 12, (*accent, 180), 6, shader=rail)
        _circle(canvas, 23, h / 2, 11, (2, 9, 18, 235),
                stroke=(*accent, 190), stroke_width=1.4)
        _star(canvas, w - 15, h / 2, 5 if newest else 3.5, 1.8,
              (239, 186, 70, 220 if newest else 80), 4)
        _rect(canvas, 43, h - 6, w - 62, 1, (*accent, 48), 0)
    return texture_from_skia(width, height, paint)


def make_log_scroll_skin(width: int, height: int, part: str,
                         active: bool = False) -> arcade.Texture:
    def paint(canvas: skia.Canvas, w: int, h: int) -> None:
        if part == "track":
            track = _linear(0, 0, w, 0,
                            [(20, 28, 40, 170), (66, 80, 100, 150), (13, 21, 33, 180)])
            _rect(canvas, 1, 0, w - 2, h, (24, 34, 48, 165), w / 2, shader=track,
                  stroke=(116, 139, 166, 82), stroke_width=1)
            for y in range(8, h, 16):
                _circle(canvas, w / 2, y, 1, (226, 183, 83, 40))
        else:
            accent = (221, 177, 72) if active else (89, 133, 176)
            if active:
                _glow(canvas, w / 2, h / 2, max(w, h) * .56, accent, 70)
            thumb = _linear(0, 0, w, 0,
                            [(*accent, 230), (225, 233, 239, 220), (*accent, 185)])
            _rect(canvas, 1, 1, w - 2, h - 2, (*accent, 220), w / 2, shader=thumb,
                  stroke=(234, 210, 147, 170), stroke_width=1)
            for y in (h * .38, h * .5, h * .62):
                _rect(canvas, 3, y, max(1, w - 6), 1, (20, 35, 53, 120))
    return texture_from_skia(width, height, paint)


def make_activity_frame(width: int, height: int) -> arcade.Texture:
    def paint(canvas: skia.Canvas, w: int, h: int) -> None:
        border = _linear(0, 0, w, h,
                         [(91, 164, 208, 230), (236, 190, 80, 245),
                          (109, 92, 165, 230), (72, 139, 188, 225)],
                         [0, .35, .7, 1])
        rect = skia.Rect.MakeXYWH(3, 3, w - 6, h - 6)
        canvas.drawRoundRect(rect, 8, 8,
                             _paint((255, 255, 255), style=skia.Paint.kStroke_Style,
                                    width=3, shader=border))
        _rect(canvas, 8, 8, w - 16, h - 16, (0, 0, 0, 0), 6,
              stroke=(195, 218, 232, 72), stroke_width=1)
        for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
            ox = 18 if sx > 0 else w - 18
            oy = 18 if sy > 0 else h - 18
            _glow(canvas, ox, oy, 18, (239, 191, 91), 45)
            _path(canvas, [(ox, oy + sy * 29), (ox, oy), (ox + sx * 29, oy)],
                  (239, 191, 91, 210), close=False, stroke_width=2.2)
            _path(canvas, [(ox + sx * 6, oy + sy * 21),
                           (ox + sx * 21, oy + sy * 6)],
                  (109, 180, 218, 180), close=False, stroke_width=1.3)
            _star(canvas, ox, oy, 5, 2, (247, 208, 111, 210), 4)
    return texture_from_skia(width, height, paint)

class RPGDrawingMixin:
    """提供給 RPGWindow 的所有繪圖與畫面排版功能。"""

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
                if len(self._text_cache) >= self.TEXT_CACHE_LIMIT:
                    self._text_cache.clear()
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
            self.text(title, left + 28, bottom + height - 31, 17, GOLD,
                      "left", "center", True,
                      max_width=max(20, width - 40), max_height=22)

    def bar(self, x: float, y: float, width: float, value: int, maximum: int,
            color: tuple[int, ...], label: str) -> None:
        ratio = max(0, min(1, value / max(1, maximum)))
        key = (int(width), 17, round(ratio, 2), tuple(color[:3]))
        texture = self._bar_skin_cache.get(key)
        if texture is None:
            texture = make_bar_skin(int(width), 17, ratio, color)
            self._bar_skin_cache[key] = texture
        arcade.draw_texture_rect(texture, arcade.XYWH(x + width / 2, y + 8.5, width, 17))
        self.text(label, x + width / 2, y + 8, 11, INK, "center", "center", True,
                  max_width=width - 14, max_height=14, min_size=7)

    def shield_bar(self, x: float, y: float, width: float, value: int,
                   maximum: int) -> None:
        shield = max(0, value)
        self.bar(x, y, width, shield, max(1, maximum, shield), BLUE, f"護盾 {shield}")

    def draw_button(self, button: Any) -> None:
        talent_rank = self.class_talent_rank(button.talent_id) if button.talent_id else 0
        learned_talent = talent_rank > 0
        needs_attention = bool(getattr(button, "attention", False)) and button.enabled
        visually_enabled = button.enabled or learned_talent
        active = learned_talent or needs_attention or (button is self.hovered and visually_enabled)
        if learned_talent:
            color = (137, 105, 196)
        elif needs_attention:
            color = (151, 108, 213)
        elif button.enabled:
            color = button.accent
        else:
            color = (53, 60, 70)
        decorated = bool(getattr(button, "decorated", True))
        key = (int(button.width), int(button.height), tuple(color), active, visually_enabled, decorated)
        texture = self._button_skin_cache.get(key)
        if texture is None:
            texture = make_button_skin(int(button.width), int(button.height), color,
                                       active, visually_enabled, decorated)
            self._button_skin_cache[key] = texture
        arcade.draw_texture_rect(
            texture, arcade.XYWH(button.x, button.y, button.width, button.height)
        )
        label_max_width = button.width - (26 if decorated else 4)
        self.text(button.label, button.x, button.y + 1, 16,
                  GOLD if learned_talent or needs_attention
                  else (INK if button.enabled else (120, 124, 132)),
                  "center", "center", True,
                  max_width=label_max_width, max_height=button.height - 18,
                  min_size=9)

    def draw_potion_menu_backdrop(self) -> None:
        bounds = getattr(self, "potion_menu_bounds", None)
        if not bounds:
            return
        left, bottom, width, height = bounds
        self.rect(left, bottom, width, height, (5, 10, 18, 232),
                  (115, 132, 160, 180), 1)

    def button_tooltip_text(self, button: Any) -> str:
        if button.tooltip:
            return button.tooltip
        label = str(button.label)
        clean = label.split("｜", 1)[0].split(" CD", 1)[0].replace(" 已用", "")
        if "天賦" in clean:
            return "有可用天賦點時，進入天賦頁強化職業能力。"
        if clean.startswith("藥水 x"):
            return "展開藥水清單；同一種藥水每回合只能喝一瓶。"
        if clean.startswith("金錢 +"):
            return "在營火整理戰利品，獲得固定金錢。"
        exact = {
            "開始遊戲": "閱讀操作說明，準備建立角色。",
            "建立角色": "開始建立新角色。",
            "讀取存檔": "進入讀取存檔畫面。",
            "關閉遊戲": "關閉遊戲視窗。",
            "回到主頁": "返回主頁。",
            "留在旅途中": "取消返回，繼續目前旅程。",
            "確認返回": "結束本次旅程並返回主頁。",
            "確認名字": "使用目前輸入的名稱繼續建立角色。",
            "繼續旅程": "前往下一段旅程。",
            "存檔 / 讀檔": "管理目前旅程的存檔與讀檔。",
            "藥水商": "進入藥水商購買藥水。",
            "重置天賦": "返還已投入的天賦點。",
            "返回": "返回上一個畫面。",
            "關閉": "關閉目前面板。",
            "離開藥水商": "離開藥水商，回到旅程。",
            "重玩": "重新開始一輪遊戲。",
            "男性": "選擇男性，防禦增加 5。",
            "女性": "選擇女性，幸運增加 1。",
            "獸人": "選擇獸人，血量上限增加 10。",
            "人類": "選擇人類，攻擊增加 5。",
            "矮人": "選擇矮人，防禦增加 5。",
            "精靈": "選擇精靈，幸運增加 1。",
            "上一組職業": "切換到上一組職業。",
            "下一組職業": "切換到下一組職業。",
            "恢復 50% 血量": "在營火回血 50%，下一場戰鬥獲得護盾。",
            "恢復 33% 血量": "在營火回血 33%。",
            "攻擊 +20%": "在營火整備，提升攻擊。",
            "攻擊 +10%": "在營火整備，提升攻擊。",
            "防禦 +20%": "在營火整備，提升防禦。",
            "防禦 +10%": "在營火整備，提升防禦。",
            "幸運 +20%": "在營火整備，提升幸運。",
            "幸運 +10%": "在營火整備，提升幸運。",
            "存檔": "把目前旅程寫入這個存檔槽。",
            "讀檔": "讀取這個存檔槽的旅程。",
            "讀取": "讀取這個存檔槽的旅程。",
        }
        if clean in {job for job, _bonus in self.JOBS}:
            return self.job_summary(clean)
        return exact.get(clean, f"執行「{clean}」。")

    def draw_hover_tooltip(self) -> None:
        if not self.hovered:
            return
        tooltip = self.button_tooltip_text(self.hovered)
        if not tooltip:
            return
        is_talent_tip = self.scene == self.Scene.TALENT and bool(self.hovered.talent_id)
        raw_lines = tooltip.splitlines()
        if not raw_lines:
            return
        if is_talent_tip:
            title = raw_lines[0]
            width = 430
            talent_rank = self.class_talent_rank(self.hovered.talent_id)
            styled_lines = []
            for point, detail in enumerate(raw_lines[1:], start=1):
                detail_color = GOLD if point <= talent_rank else MUTED
                wrapped = self.wrap_text_hanging(
                    detail, width - 32, 12, single_line_tolerance=.10
                )
                styled_lines.extend(
                    (line, detail_color, indent) for line, indent in wrapped
                )
            styled_lines = styled_lines[:10]
            title_color = GOLD if talent_rank > 0 else MUTED
        else:
            title = "說明"
            width = 360
            lines = self.wrap_text_pixels(
                tooltip, width - 32, 12, single_line_tolerance=.10
            )
            styled_lines = [(line, INK, 0.0) for line in lines[:4]]
            title_color = GOLD
        line_spacing = 24
        height = 34 + len(styled_lines) * line_spacing
        left = max(350, min(SCREEN_WIDTH - width - 24, self.hovered.x - width / 2))
        bottom = self.hovered.y + self.hovered.height / 2 + 12
        if bottom + height > SCREEN_HEIGHT - 18:
            bottom = self.hovered.y - self.hovered.height / 2 - height - 12
        self.rect(left, bottom, width, height, (8, 14, 24, 238), (122, 143, 170, 220), 1)
        self.text(title, left + 16, bottom + height - 20, 13, title_color,
                  bold=True, max_width=width - 32, max_height=24)
        for index, (line, line_color, indent) in enumerate(styled_lines):
            line_width = width - 32 - indent
            measured_width = self.measure_text_width(line, 12)
            if (line and line[-1] in CJK_NO_LINE_START
                    and measured_width <= line_width + 16):
                line_width = measured_width
            self.text(line, left + 16 + indent,
                      bottom + height - 45 - index * line_spacing, 12, line_color,
                      max_width=line_width, max_height=24)

    @staticmethod
    def should_record_log(message: str) -> bool:
        keep_phrases = (
            "開始旅程", "存檔", "讀取", "損毀", "寫入失敗",
            "購買成功", "喝下",
            "倒下", "搜出", "GAME OVER", "過關", "通關",
            "抵達第", "天賦點", "重置了", "副職業", "點亮", "分身",
            "沒有明顯變化", "沒有找到", "作弊調整",
            "血量上限", "攻擊 ", "防禦 ", "幸運 ", "金錢 ",
            "護盾 +", "恢復 ",
        )
        return any(phrase in message for phrase in keep_phrases)

    def log(self, message: str, *, record: bool | None = None) -> None:
        if self.scene == self.Scene.EVENT:
            self.event_messages.append(message)
        if record is None:
            record = self.should_record_log(message)
        if not record:
            return
        if self.log_scroll > 0:
            self.log_scroll += 1
        self.messages.append(message)
        limit = getattr(self, "LOG_RECORD_LIMIT", 12)
        self.messages = self.messages[-limit:]
        self.log_scroll = min(self.log_scroll, max(0, len(self.messages) - 1))

    def measure_text_width(self, value: str, size: int = 11,
                           bold: bool = False) -> float:
        key = (value, size, bold)
        measured = self._measure_cache.get(key)
        if measured is None:
            if len(self._measure_cache) >= self.MEASURE_CACHE_LIMIT:
                self._measure_cache.clear()
            label = arcade.Text(
                value, 0, 0, INK, size, bold=bold,
                font_name=("Microsoft JhengHei", "Noto Sans CJK TC", "Arial"),
            )
            measured = label.content_width
            self._measure_cache[key] = measured
        return measured

    def wrap_text_pixels(self, value: str, max_width: float,
                         size: int = 11,
                         single_line_tolerance: float = 0.0) -> list[str]:
        """Wrap CJK and Latin text by rendered width while preserving each record."""
        lines: list[str] = []
        for paragraph in value.splitlines() or [""]:
            if (paragraph and single_line_tolerance > 0
                    and self.measure_text_width(paragraph, size)
                    <= max_width * (1 + single_line_tolerance)):
                lines.append(paragraph)
                continue
            paragraph_lines: list[str] = []
            current = ""
            for character in paragraph:
                candidate = current + character
                if current and self.measure_text_width(candidate, size) > max_width:
                    if character in CJK_NO_LINE_START:
                        paragraph_lines.append(candidate.rstrip())
                        current = ""
                    else:
                        paragraph_lines.append(current.rstrip())
                        current = character.lstrip()
                else:
                    current = candidate
            if current:
                paragraph_lines.append(current)
            if not paragraph_lines:
                paragraph_lines.append(" ")
            lines.extend(paragraph_lines)
        return lines

    def wrap_text_hanging(self, value: str, max_width: float,
                          size: int = 11,
                          single_line_tolerance: float = 0.0
                          ) -> list[tuple[str, float]]:
        """Wrap a labelled line and align continuations below its body text."""
        if (value and single_line_tolerance > 0
                and self.measure_text_width(value, size)
                <= max_width * (1 + single_line_tolerance)):
            return [(value, 0.0)]

        separator = value.find("：")
        if separator < 0:
            separator = value.find(":")
        if separator < 0:
            return [(line, 0.0) for line in self.wrap_text_pixels(value, max_width, size)]

        prefix = value[:separator + 1]
        body = value[separator + 1:]
        indent = self.measure_text_width(prefix, size)
        continuation_width = max(1.0, max_width - indent)
        wrapped: list[tuple[str, float]] = []
        current = prefix

        for character in body:
            line_indent = 0.0 if not wrapped else indent
            line_width = max_width if not wrapped else continuation_width
            candidate = current + character
            if current and self.measure_text_width(candidate, size) > line_width:
                if character in CJK_NO_LINE_START:
                    wrapped.append((candidate.rstrip(), line_indent))
                    current = ""
                else:
                    wrapped.append((current.rstrip(), line_indent))
                    current = character.lstrip()
            else:
                current = candidate

        if current:
            wrapped.append((current, 0.0 if not wrapped else indent))
        if not wrapped:
            wrapped.append((prefix, 0.0))
        return wrapped

    @staticmethod
    def log_card_style(message: str) -> tuple[str, tuple[int, int, int]]:
        if any(word in message for word in ("倒下", "GAME")):
            return "戰", (216, 76, 65)
        if any(word in message for word in ("詛咒", "劇毒", "毒火", "失去", "失敗", "不足", "GAME")):
            return "危", (180, 68, 126)
        if any(word in message for word in ("恢復", "靈藥", "聖輝", "血量")):
            return "癒", (70, 174, 119)
        if any(word in message for word in ("獲得", "增加", "升級", "金幣", "購買", "金錢", "+", "搜出")):
            return "獲", (231, 177, 72)
        if any(word in message for word in ("藥水商", "商人", "龍牙", "玄鐵", "星眼")):
            return "市", (169, 91, 196)
        return "旅", (70, 137, 196)

    def prepared_log_cards(self, text_width: float = 220
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
            cards.append((icon, lines, accent, 44 if len(lines) == 1 else 62))
        return cards

    @staticmethod
    def max_log_scroll(cards: list[tuple[str, list[str], tuple[int, int, int], int]],
                       available_height: float = 382) -> int:
        used_height = 0.0
        oldest_page_count = 0
        for _icon, _lines, _accent, card_height in reversed(cards):
            next_height = card_height + (5 if oldest_page_count else 0)
            if used_height + next_height > available_height:
                break
            used_height += next_height
            oldest_page_count += 1
        return max(0, len(cards) - oldest_page_count)

    def visible_log_cards(self, text_width: float = 220,
                          available_height: float = 382) -> list[tuple[str, list[str], tuple[int, int, int], int]]:
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

    def event_background(self, number: int) -> arcade.Texture:
        texture = self.event_backgrounds.get(number)
        if texture is None:
            texture = make_activity_background("event", number)
            self.event_backgrounds[number] = texture
        return texture

    def monster_portrait(self, rank: int, kind: str) -> arcade.Texture:
        key = (rank, kind)
        texture = self._monster_portrait_cache.get(key)
        if texture is None:
            texture = make_monster_portrait(rank, kind)
            self._monster_portrait_cache[key] = texture
        return texture

    @staticmethod
    def skill_effect_alpha(progress: float) -> int:
        fade_in = min(1.0, progress / .12)
        fade_out = min(1.0, (1.0 - progress) / .22)
        return max(0, min(255, int(255 * fade_in * fade_out)))

    @staticmethod
    def effect_glow(x: float, y: float, radius: float,
                    color: tuple[int, int, int], alpha: int) -> None:
        for scale, opacity in ((1.35, .08), (1.0, .13), (.66, .22), (.32, .34)):
            arcade.draw_circle_filled(
                x, y, radius * scale, (*color, int(alpha * opacity))
            )

    @staticmethod
    def effect_ring(x: float, y: float, radius: float,
                    color: tuple[int, int, int], alpha: int,
                    width: float = 3, tilt: float = 0) -> None:
        arcade.draw_arc_outline(
            x, y, radius * 2, radius * 1.16, (*color, alpha),
            0, 360, width, tilt_angle=tilt,
        )

    def draw_skill_effects(self) -> None:
        names = {
            "blood_ritual": "血祭強襲", "fate_rewrite": "命運改寫",
            "divine_protection": "神聖庇護", "sap": "悶棍",
            "slash": "斬擊", "guard": "格擋", "cleave": "順劈斬",
            "fortify": "鋼鐵壁壘", "counter": "盾擊反制",
            "bladestorm": "劍刃風暴", "last_stand": "最後防線",
            "fireball": "火球術", "ice_armor": "冰甲術",
            "pyroblast": "炎爆術", "ice_wall": "冰牆術",
            "ice_barrier": "寒冰屏障", "mana_shield": "法力護盾",
            "meteor": "隕石風暴", "smite": "聖光懲擊",
            "blessing": "虔誠祝福", "judgment": "聖光審判",
            "sanctuary": "聖域", "purify": "淨化祈禱",
            "divine_wrath": "神聖怒火", "guardian_angel": "守護天使",
            "stab": "刺擊", "smokescreen": "煙幕",
            "backstab": "背刺", "smoke_bomb": "煙霧彈",
            "vanish": "消失", "shadowstep": "暗影步",
            "assassinate": "刺殺", "soul_drain": "靈魂汲取",
            "corruption_bolt": "腐蝕箭", "dark_charm": "暗影護符",
            "agony": "痛苦詛咒", "life_tap": "生命轉化",
            "soul_link": "靈魂連結", "hex": "衰弱咒印",
            "doom": "末日降臨",
        }
        job_colors = {
            "戰士": (232, 83, 61), "法師": (82, 173, 255),
            "聖騎士": (255, 211, 93), "盜賊": (174, 104, 235),
            "術士": (116, 218, 83),
        }
        for effect in self.skill_effects:
            progress = max(0.0, min(1.0, effect.elapsed / effect.duration))
            alpha = self.skill_effect_alpha(progress)
            if alpha <= 0:
                continue
            color = job_colors.get(effect.job, GOLD)
            self.draw_skill_effect(effect.skill_id, effect.job, progress, alpha, color)
            if progress < .72:
                label_x = 752
                if len(getattr(self, "enemies", ())) > 1:
                    enemy_positions = (865, 1055)
                    target_index = min(getattr(self, "target_index", 0),
                                       len(enemy_positions) - 1)
                    label_x = (555 + enemy_positions[target_index]) / 2
                self.text(names.get(effect.skill_id, effect.skill_id), label_x, 606, 17,
                          color, "center", "center", True,
                          max_width=300, max_height=25, min_size=13)

    def draw_skill_effect(self, skill_id: str, job: str, progress: float,
                          alpha: int, color: tuple[int, int, int]) -> None:
        player_x, player_y = 555.0, 435.0
        enemy_x, enemy_y = 950.0, 435.0
        if len(getattr(self, "enemies", ())) > 1:
            enemy_positions = (865.0, 1055.0)
            target_index = min(getattr(self, "target_index", 0), len(enemy_positions) - 1)
            enemy_x = enemy_positions[target_index]
        phase = progress * math.tau

        warrior_guards = {"guard", "fortify", "last_stand"}
        warrior_strikes = {"slash", "cleave", "counter", "bladestorm"}
        frost_spells = {"ice_armor", "ice_wall", "ice_barrier", "mana_shield"}
        fire_spells = {"fireball", "pyroblast", "meteor"}
        holy_strikes = {"smite", "judgment", "divine_wrath"}
        holy_aura = {"blessing", "sanctuary", "purify", "divine_protection", "guardian_angel"}
        shadow_strikes = {"stab", "backstab", "shadowstep", "assassinate"}
        smoke_spells = {"smokescreen", "smoke_bomb", "vanish"}
        warlock_spells = {
            "soul_drain", "corruption_bolt", "dark_charm", "agony",
            "life_tap", "soul_link", "hex", "doom",
        }

        if skill_id in warlock_spells:
            target_x = enemy_x
            self.effect_glow(target_x, enemy_y, 112, (106, 202, 74), alpha)
            if skill_id in {"dark_charm", "life_tap", "soul_link"}:
                self.effect_glow(player_x, player_y, 105, (125, 214, 78), alpha)
                self.effect_ring(player_x, player_y, 88, (128, 220, 82), alpha, 4,
                                 progress * 95)
                for index in range(9):
                    angle = index * math.tau / 9 + phase * .2
                    x = player_x + math.cos(angle) * 74
                    y = player_y + math.sin(angle) * 50
                    arcade.draw_circle_filled(x, y, 4, (158, 230, 95, alpha))
                if skill_id != "life_tap":
                    return
            if skill_id in {"corruption_bolt", "soul_drain"}:
                travel = min(1.0, progress / .55)
                x = player_x + (target_x - player_x) * travel
                y = player_y + math.sin(travel * math.pi) * 46
                arcade.draw_circle_filled(x, y, 18, (126, 228, 86, alpha))
                self.effect_glow(x, y, 52, (126, 228, 86), alpha)
            if skill_id in {"agony", "hex", "doom", "life_tap", "soul_drain", "corruption_bolt"}:
                ring_radius = 70 + math.sin(phase * 2) * 5
                self.effect_ring(target_x, enemy_y, ring_radius, (128, 226, 83),
                                 alpha, 4, progress * 110)
                self.effect_ring(target_x, enemy_y, ring_radius * .68, (154, 86, 214),
                                 int(alpha * .8), 3, -progress * 90)
                for index in range(10 if skill_id == "doom" else 6):
                    angle = index * math.tau / (10 if skill_id == "doom" else 6) + phase
                    x = target_x + math.cos(angle) * (60 + index % 3 * 12)
                    y = enemy_y - 80 + ((progress * 160 + index * 23) % 170)
                    arcade.draw_circle_filled(x, y, 5, (99, 214, 73, int(alpha * .85)))
                if skill_id == "doom":
                    for index in range(7):
                        x = target_x - 85 + index * 28
                        top = enemy_y + 130 - index % 2 * 18
                        arcade.draw_line(x, top, target_x, enemy_y - 30,
                                         (73, 20, 92, int(alpha * .75)), 6)
                    self.effect_glow(target_x, enemy_y + 40, 150, (96, 33, 122), alpha)
            return

        if skill_id == "blood_ritual":
            self.effect_glow(player_x, player_y, 105, (205, 30, 45), alpha)
            for ring in range(3):
                radius = 42 + ((progress * 95 + ring * 31) % 105)
                self.effect_ring(player_x, player_y, radius, (245, 45, 57),
                                 int(alpha * (1 - radius / 165)), 3)
            for index in range(12):
                angle = index * math.tau / 12 + phase * .35
                x = player_x + math.cos(angle) * (52 + index % 3 * 18)
                y = player_y - 78 + ((progress * 190 + index * 29) % 170)
                arcade.draw_circle_filled(x, y, 3 + index % 3,
                                          (244, 48, 65, int(alpha * .8)))
            return

        if skill_id in warrior_guards or skill_id == "counter":
            radius = 92 + math.sin(phase * 2) * 6
            points = [
                (player_x + math.cos(math.pi / 6 + i * math.tau / 6) * radius,
                 player_y + math.sin(math.pi / 6 + i * math.tau / 6) * radius)
                for i in range(6)
            ]
            arcade.draw_polygon_filled(points, (62, 104, 151, int(alpha * .16)))
            for index in range(6):
                x1, y1 = points[index]
                x2, y2 = points[(index + 1) % 6]
                arcade.draw_line(x1, y1, x2, y2,
                                 (168, 218, 255, alpha), 4 if skill_id == "fortify" else 3)
            self.effect_ring(player_x, player_y, radius * .78, (120, 184, 235),
                             int(alpha * .85), 3, progress * 110)
            if skill_id in ("fortify", "last_stand"):
                self.effect_ring(player_x, player_y, radius * 1.18, color,
                                 int(alpha * .7), 5, -progress * 75)
            if skill_id == "counter":
                arcade.draw_line(player_x + 55, player_y + 58,
                                 enemy_x - 38, enemy_y - 42,
                                 (255, 222, 133, int(alpha * .85)), 7)
            if skill_id in warrior_guards:
                return

        if skill_id in warrior_strikes:
            count = 5 if skill_id == "bladestorm" else (2 if skill_id in ("cleave", "counter") else 1)
            self.effect_glow(enemy_x, enemy_y, 92, (236, 91, 54), alpha)
            for index in range(count):
                angle = -38 + index * (76 / max(1, count - 1)) + progress * (260 if skill_id == "bladestorm" else 20)
                radians = math.radians(angle)
                dx, dy = math.cos(radians) * 125, math.sin(radians) * 125
                arcade.draw_line(enemy_x - dx, enemy_y - dy, enemy_x + dx, enemy_y + dy,
                                 (255, 239, 190, alpha), 7 if skill_id == "cleave" else 4)
                arcade.draw_line(enemy_x - dx * .92, enemy_y - dy * .92,
                                 enemy_x + dx * .92, enemy_y + dy * .92,
                                 (236, 69, 44, int(alpha * .7)), 11)
            if skill_id in ("cleave", "bladestorm"):
                for offset in range(3 if skill_id == "cleave" else 6):
                    arcade.draw_arc_outline(
                        enemy_x, enemy_y, 225 + offset * 14, 185 + offset * 10,
                        (255, 132, 62, int(alpha * (.75 - offset * .08))),
                        22 + progress * 220 + offset * 28,
                        150 + progress * 220 + offset * 28, 4,
                    )
            return

        if skill_id == "fate_rewrite":
            center_x, center_y = 752.0, 435.0
            self.effect_glow(center_x, center_y, 120, (102, 119, 255), alpha)
            for index, radius in enumerate((48, 78, 112)):
                arcade.draw_arc_outline(
                    center_x, center_y, radius * 2, radius * 1.15,
                    ((103, 217, 255, alpha) if index % 2 == 0
                     else (181, 92, 255, alpha)),
                    20 + progress * (220 + index * 80),
                    300 + progress * (220 + index * 80), 3,
                    tilt_angle=index * 35,
                )
            for index in range(8):
                angle = phase * (1 if index % 2 else -1) + index * math.tau / 8
                radius = 74 + index % 2 * 35
                arcade.draw_circle_filled(
                    center_x + math.cos(angle) * radius,
                    center_y + math.sin(angle) * radius * .58,
                    5, (214, 226, 255, alpha),
                )
            return

        if skill_id in fire_spells:
            if skill_id == "meteor":
                travel = min(1.0, progress / .58)
                meteor_x = 1080 - 130 * travel
                meteor_y = 670 - 230 * travel
                arcade.draw_line(meteor_x + 125, meteor_y + 155, meteor_x, meteor_y,
                                 (255, 219, 111, int(alpha * .75)), 8)
                arcade.draw_line(meteor_x + 100, meteor_y + 125, meteor_x, meteor_y,
                                 (255, 72, 28, alpha), 16)
                self.effect_glow(meteor_x, meteor_y, 38, (255, 72, 31), alpha)
                arcade.draw_circle_filled(meteor_x, meteor_y, 20, (74, 35, 28, alpha))
                if progress > .46:
                    blast = 35 + (progress - .46) * 210
                    self.effect_glow(enemy_x, enemy_y, blast, (255, 73, 25), alpha)
                    self.effect_ring(enemy_x, enemy_y, blast * .7, (255, 210, 91), alpha, 7)
                return
            travel_end = .48 if skill_id == "pyroblast" else .58
            travel = min(1.0, progress / travel_end)
            x = player_x + (enemy_x - player_x) * travel
            y = player_y + math.sin(travel * math.pi) * (90 if skill_id == "pyroblast" else 48)
            size = 34 if skill_id == "pyroblast" else 21
            for trail in range(6):
                trail_x = x - (30 + trail * 14) * (1 - min(1, travel + .12)) - trail * 9
                arcade.draw_circle_filled(
                    trail_x, y - math.sin(trail * 1.4) * 8,
                    max(3, size - trail * 4),
                    (255, 70 + trail * 15, 24, int(alpha * (1 - trail * .11))),
                )
            self.effect_glow(x, y, size * 2.5, (255, 91, 28), alpha)
            arcade.draw_circle_filled(x, y, size, (255, 226, 123, alpha))
            if travel >= 1:
                blast = size * (2.0 + (progress - travel_end) * 7)
                self.effect_ring(enemy_x, enemy_y, blast, (255, 196, 73), alpha, 6)
                self.effect_glow(enemy_x, enemy_y, blast, (255, 68, 25), alpha)
            return

        if skill_id in frost_spells:
            center_x = 720.0 if skill_id == "ice_wall" else player_x
            center_y = 365.0 if skill_id == "ice_wall" else player_y
            self.effect_glow(center_x, center_y, 112, (74, 183, 255), alpha)
            crystal_count = 9 if skill_id == "ice_wall" else 7
            for index in range(crystal_count):
                if skill_id == "ice_wall":
                    x = center_x - 120 + index * 30
                    base_y = 330
                    height = 75 + (index % 3) * 30
                    points = [(x - 17, base_y), (x, base_y + height), (x + 17, base_y)]
                else:
                    angle = phase * .35 + index * math.tau / crystal_count
                    x = center_x + math.cos(angle) * 102
                    base_y = center_y + math.sin(angle) * 82
                    points = [(x - 9, base_y - 18), (x, base_y + 20), (x + 9, base_y - 18)]
                arcade.draw_polygon_filled(points, (126, 220, 255, int(alpha * .52)))
                arcade.draw_line(*points[0], *points[1], (222, 249, 255, alpha), 2)
            self.effect_ring(center_x, center_y, 104, (137, 223, 255), alpha, 4,
                             progress * 70)
            if skill_id in ("ice_barrier", "mana_shield"):
                self.effect_ring(center_x, center_y, 82, (190, 245, 255), alpha, 7,
                                 -progress * 105)
            return

        if skill_id in holy_strikes:
            beam_width = 48 if skill_id == "divine_wrath" else 28
            arcade.draw_lrbt_rectangle_filled(
                enemy_x - beam_width, enemy_x + beam_width, enemy_y - 105, 650,
                (255, 222, 105, int(alpha * .13)),
            )
            arcade.draw_lrbt_rectangle_filled(
                enemy_x - beam_width * .36, enemy_x + beam_width * .36,
                enemy_y - 105, 650, (255, 250, 205, int(alpha * .65)),
            )
            self.effect_glow(enemy_x, enemy_y, 118, (255, 207, 67), alpha)
            for index in range(10 if skill_id == "divine_wrath" else 6):
                angle = index * math.tau / (10 if skill_id == "divine_wrath" else 6) + phase
                x = enemy_x + math.cos(angle) * 105
                y = enemy_y + math.sin(angle) * 83
                arcade.draw_line(x - 9, y, x + 9, y, (255, 239, 161, alpha), 3)
                arcade.draw_line(x, y - 9, x, y + 9, (255, 239, 161, alpha), 3)
            self.effect_ring(enemy_x, enemy_y, 112, (255, 219, 91), alpha, 5,
                             progress * 95)
            return

        if skill_id in holy_aura:
            tint = (125, 236, 164) if skill_id == "purify" else (255, 219, 91)
            self.effect_glow(player_x, player_y, 125, tint, alpha)
            self.effect_ring(player_x, player_y, 105 + math.sin(phase) * 5,
                             tint, alpha, 5, progress * 85)
            self.effect_ring(player_x, player_y, 72, (255, 250, 202),
                             int(alpha * .8), 3, -progress * 130)
            for index in range(12):
                angle = index * math.tau / 12
                x = player_x + math.cos(angle) * (55 + index % 3 * 18)
                y = player_y - 75 + ((progress * 170 + index * 23) % 165)
                arcade.draw_line(x - 5, y, x + 5, y, (*tint, alpha), 2)
                arcade.draw_line(x, y - 5, x, y + 5, (*tint, alpha), 2)
            if skill_id == "guardian_angel":
                for side in (-1, 1):
                    wing = [(player_x + side * 24, player_y + 35),
                            (player_x + side * 105, player_y + 105),
                            (player_x + side * 125, player_y + 35),
                            (player_x + side * 70, player_y - 18)]
                    arcade.draw_polygon_filled(wing, (255, 246, 201, int(alpha * .34)))
            return

        if skill_id in smoke_spells:
            radius = 40 + progress * (155 if skill_id == "smoke_bomb" else 120)
            smoke_color = (105, 87, 129) if skill_id == "vanish" else (75, 82, 95)
            for index in range(14):
                angle = index * math.tau / 14 + phase * .18
                distance = radius * (.35 + (index % 5) * .13)
                x = player_x + math.cos(angle) * distance
                y = player_y + math.sin(angle) * distance * .58
                puff = 18 + (index % 4) * 8 + progress * 14
                arcade.draw_circle_filled(x, y, puff,
                                          (*smoke_color, int(alpha * .23)))
                arcade.draw_circle_outline(x, y, puff,
                                           (183, 145, 220, int(alpha * .35)), 2)
            self.effect_ring(player_x, player_y, radius * .72,
                             (174, 104, 235), int(alpha * .7), 3)
            return

        if skill_id == "sap":
            self.effect_ring(enemy_x, enemy_y + 105, 48, (230, 196, 93), alpha, 4,
                             progress * 150)
            for index in range(5):
                angle = phase * 1.8 + index * math.tau / 5
                x = enemy_x + math.cos(angle) * 52
                y = enemy_y + 110 + math.sin(angle) * 26
                points = []
                for point in range(10):
                    point_angle = -math.pi / 2 + point * math.pi / 5
                    radius = 9 if point % 2 == 0 else 4
                    points.append((x + math.cos(point_angle) * radius,
                                   y + math.sin(point_angle) * radius))
                arcade.draw_polygon_filled(points, (255, 224, 112, alpha))
            return

        if skill_id in shadow_strikes:
            strike_count = 4 if skill_id == "assassinate" else (2 if skill_id in ("backstab", "shadowstep") else 1)
            self.effect_glow(enemy_x, enemy_y, 100, (126, 55, 186), alpha)
            for index in range(strike_count):
                angle = math.radians(-52 + index * (104 / max(1, strike_count - 1)))
                offset = (index - (strike_count - 1) / 2) * 24
                dx, dy = math.cos(angle) * 118, math.sin(angle) * 118
                arcade.draw_line(enemy_x - dx + offset, enemy_y - dy,
                                 enemy_x + dx + offset, enemy_y + dy,
                                 (237, 222, 255, alpha), 4)
                arcade.draw_line(enemy_x - dx * .9 + offset, enemy_y - dy * .9,
                                 enemy_x + dx * .9 + offset, enemy_y + dy * .9,
                                 (169, 72, 228, int(alpha * .72)), 9)
            for index in range(8):
                angle = index * math.tau / 8 - phase
                x = enemy_x + math.cos(angle) * (65 + progress * 55)
                y = enemy_y + math.sin(angle) * (48 + progress * 34)
                arcade.draw_circle_filled(x, y, 4, (205, 135, 255, alpha))
            return

        # Fallback aura for any future skill not yet assigned a bespoke shape.
        center_x = enemy_x if job in ("戰士", "法師", "盜賊") else player_x
        self.effect_glow(center_x, player_y, 105, color, alpha)
        self.effect_ring(center_x, player_y, 102, color, alpha, 4, progress * 100)

    def on_draw(self) -> None:
        self.clear()
        arcade.draw_texture_rect(self.background, arcade.LBWH(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT))
        if self.scene == self.Scene.TITLE:
            self.draw_title()
        elif self.scene == self.Scene.GUIDE:
            self.draw_guide()
        elif self.scene == self.Scene.CREATION:
            self.draw_creation()
        elif self.scene == self.Scene.SAVE_MENU:
            self.draw_save_menu()
        else:
            self.draw_game()
        if self.home_confirmation:
            self.draw_home_confirmation()
        if self.cheat_open:
            self.draw_cheat_panel()
        self.draw_potion_menu_backdrop()
        for button in self.buttons:
            if not button.invisible:
                self.draw_button(button)
        self.draw_hover_tooltip()

    def draw_home_confirmation(self) -> None:
        self.rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, (2, 4, 9, 190))
        self.panel(330, 215, 520, 300, "離開遠征？")
        self.text("確定要結束這次冒險嗎？", 590, 430, 25, GOLD,
                  "center", "center", True, max_width=450, max_height=36)
        self.text("返回主頁後，本次冒險進度將無法取回。",
                  590, 380, 15, INK, "center", "center", max_width=450)
        self.text("也可以留下來，繼續往王城前進。",
                  590, 345, 13, MUTED, "center", "center", max_width=450)

    def draw_cheat_panel(self) -> None:
        self.rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, (2, 4, 9, 200))
        self.panel(330, 70, 620, 580, "作弊工具")
        self.text("作弊工具", 640, 612, 28, GOLD, "center", "center", True,
                  max_width=540, max_height=38)
        if self.cheat_dropdown:
            target = "關卡" if self.cheat_dropdown == "lv" else "難度"
            self.text(f"選擇{target}", 640, 545, 22, GOLD, "center", "center", True,
                      max_width=540, max_height=30)
            self.text("點擊要設定的數值，或按「返回」取消。",
                      640, 512, 13, MUTED, "center", "center",
                      max_width=560, max_height=20, min_size=10)
            return
        self.text("點擊數值框輸入數字（最多 4 位）；難度與關卡用下拉選單；下一場戰鬥完全生效。",
                  640, 578, 12, MUTED, "center", "center",
                  max_width=570, max_height=18, min_size=10)
        for row_index, (field, label) in enumerate(self.CHEAT_FIELDS):
            y = self.CHEAT_ROW_TOP - row_index * self.CHEAT_ROW_GAP
            if row_index % 2 == 0:
                self.rect(345, y - 19, 590, 38, (10, 16, 28, 110))
            self.text(label, 370, y, 15, INK, "left", "center", True,
                      max_width=280, max_height=22, min_size=11)
            if field == "hp":
                self.text(f"上限 {self.player.max_hp}", 660, y, 12, MUTED,
                          "right", "center", max_width=120, max_height=18, min_size=9)

    def draw_save_menu(self) -> None:
        self.rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, (2, 4, 9, 190))
        manage_mode = self.save_menu_mode == "manage"
        title = "存檔 / 讀檔" if manage_mode else "讀取存檔"
        self.panel(280, 110, 620, 500, title)
        self.text(title, 590, 572, 30, GOLD, "center", "center", True,
                  max_width=540, max_height=42)
        hint = ("戰鬥開始前的整備時刻，可以保存或讀取旅程。" if manage_mode
                else "選擇一個存檔槽，接續上次的遠征。")
        self.text(hint, 590, 534, 14, MUTED, "center", "center",
                  max_width=540, max_height=22, min_size=11)
        for slot in range(1, self.SAVE_SLOT_COUNT + 1):
            bottom = 398 - (slot - 1) * 126
            data = self.save_slots.get(slot)
            border = (*GOLD, 170) if data else (87, 97, 112, 90)
            fill = (26, 21, 42, 178) if data else (6, 10, 18, 140)
            self.rect(310, bottom, 560, 112, fill, border, 1)
            self.text(f"存檔槽 {slot}", 330, bottom + 92, 15, GOLD, "left", "center",
                      True, max_width=180, max_height=22)
            if not data:
                self.text("（空的存檔槽）", 330, bottom + 50, 15, MUTED,
                          "left", "center", max_width=380, max_height=22)
                continue
            saved_player = data.get("player", {})
            job_text = str(saved_player.get("job", ""))
            if saved_player.get("sub_job"):
                job_text += f"/{saved_player['sub_job']}"
            difficulty_name = self.DIFFICULTY_NAMES.get(
                int(data.get("difficulty", 1)), self.DIFFICULTY_NAMES[1]
            )
            saved_potions = 0
            potion_bag = saved_player.get("potion_bag", {})
            if isinstance(potion_bag, dict):
                for count in potion_bag.values():
                    try:
                        saved_potions += max(0, int(count))
                    except (TypeError, ValueError):
                        continue
            try:
                saved_potions += max(0, int(saved_player.get("potions", 0)))
            except (TypeError, ValueError):
                pass
            self.text(
                f"{saved_player.get('name', '勇者')}｜{saved_player.get('race', '')}・{job_text}"
                f"｜{self.level_label(int(saved_player.get('lv', 1)))}",
                330, bottom + 65, 15, INK, "left", "center", True,
                max_width=390, max_height=22, min_size=11,
            )
            self.text(
                f"血量 {saved_player.get('hp', 0)} / {saved_player.get('max_hp', 0)}"
                f"｜金錢 {saved_player.get('gold', 0)}G｜藥水 {saved_potions}",
                330, bottom + 41, 13, INK, "left", "center",
                max_width=390, max_height=20, min_size=10,
            )
            self.text(
                f"{difficulty_name}｜存檔時間 {data.get('saved_at', '—')}",
                330, bottom + 18, 12, MUTED, "left", "center",
                max_width=390, max_height=18, min_size=9,
            )

    def draw_title(self) -> None:
        self.rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, (3, 6, 12, 65))
        self.text("餘 燼 王 國", 590, 455, 54, GOLD, "center", "center", True,
                  max_width=920, max_height=70)
        self.text("黑霧遠征・失落王座", 590, 395, 21, INK, "center", "center",
                  max_width=760)
        self.text("黑霧越過北境長城，古老王城只剩最後一盞烽火。",
                  590, 342, 16, MUTED, "center", "center", max_width=900)
        self.text("選擇你的種族與職業，走上古道，奪回被黑暗吞掉的黎明。",
                  590, 308, 14, MUTED, "center", "center", max_width=900)

    def draw_guide(self) -> None:
        self.rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, (3, 6, 12, 70))
        self.panel(210, 120, 760, 475, "操作說明")
        self.text("冒險前先看這裡", 590, 505, 30, GOLD,
                  "center", "center", True, max_width=680, max_height=42)
        guide_lines = (
            ("職業技能", "各職業有專屬技能；一場戰鬥只能使用一次。"),
            ("護盾", "攻擊不會清空自身護盾；護盾會抵銷承受的傷害。"),
            ("藥水商", "有錢就能進；同款藥水買越多越貴。"),
            ("藥水", "戰鬥中展開清單；同款每回合只能喝一次。"),
            ("星級", "高星試煉會改變敵方意圖與戰鬥節奏。"),
            ("副職業", "第 10 關後可選副職，只增加專屬技能。"),
            ("營火", "每 3 關出現，可回血、提升能力，或增加金錢。"),
            ("天賦", "每 2 關獲得 1 點，可強化或解鎖招式。"),
            ("存讀檔", "冒險頁可存檔；讀檔會回到戰鬥前。"),
        )
        for index, (title, body) in enumerate(guide_lines):
            y = 454 - index * 34
            self.text(title, 260, y, 15, INK, "left", "center",
                      max_width=120, max_height=25, min_size=15)
            self.text(body, 390, y, 15, INK, "left", "center",
                      max_width=540, max_height=25, min_size=13)

    def draw_creation(self) -> None:
        self.panel(165, 145, 850, 455, "建立角色")
        titles = ("選擇性別", "選擇名字", "選擇種族", "選擇職業")
        title_y = 532 if self.creation_step == 3 else 505
        self.text(titles[self.creation_step], 590, title_y, 31, INK, "center", "center", True,
                  max_width=760, max_height=45)
        if self.creation_step == 0:
            self.text("性別會給一點不同的能力加成。",
                      590, 405, 15, MUTED, "center", "center", max_width=760)
        elif self.creation_step == 1:
            self.panel(410, 365, 360, 62)
            input_y = 399
            if self.name_input or self.name_input_focused:
                if self.name_input:
                    self.text(self.name_input, 590, input_y, 24, GOLD, "center", "center", True,
                              max_width=320, max_height=38)
                if self.name_input_focused and int(self.name_caret_timer * 2) % 2 == 0:
                    name_width = (
                        min(320.0, self.measure_text_width(self.name_input, 24, True))
                        if self.name_input else 0.0
                    )
                    self.text("|", 590 + name_width / 2 + 3, input_y, 24, INK,
                              "left", "center", max_width=20, max_height=38)
            else:
                self.text("輸入角色名稱", 590, input_y, 24, MUTED, "center", "center", True,
                          max_width=320, max_height=38)
        elif self.creation_step == 2:
            for i, (race, _bonus) in enumerate(self.RACES):
                y = 425 - i * 65
                self.text(f"{self.race_talent_name_for(race)}：{self.race_talent_description(race)}",
                          500, y, 14, INK, "left", "center",
                          max_width=470, max_height=42, min_size=11)
        elif self.creation_step == 3:
            self.rect(335, 452, 510, 58, (7, 13, 23, 145),
                      (82, 102, 130, 95), 1)
            self.text("試煉", 590, 496, 15, GOLD, "center", "center", True,
                      max_width=100, max_height=20, min_size=12)
            rule_items = (
                ("*", self.STAR_TOOLTIPS[0], 445),
                ("**", self.STAR_TOOLTIPS[1], 590),
                ("***", self.STAR_TOOLTIPS[2], 735),
            )
            for label, text, x in rule_items:
                self.text(label, x - 54, 471, 13, GOLD, "left", "center", True,
                          max_width=38, max_height=19, min_size=11)
                self.text(text, x - 16, 471, 13, INK, "left", "center",
                          max_width=124, max_height=19, min_size=11)
            visible_jobs = self.visible_jobs()
            start_x = 590 - (len(visible_jobs) - 1) * 120
            for i, (job, bonus) in enumerate(visible_jobs):
                x = start_x + i * 240
                y = 342
                self.rect(x - 108, y - 128, 216, 200, (6, 10, 18, 118),
                          (82, 102, 130, 82), 1)
                progress = self.job_difficulty(job)
                detail_size = 11
                detail_y = y - 48
                line_gap = 19
                star_y = y - 10
                for star in range(self.MAX_DIFFICULTY):
                    lit = star < progress
                    self.text("★", x - 28 + star * 28, star_y, 15,
                              GOLD if lit else (116, 93, 46), "center", "center", True,
                              max_width=24, max_height=20)
                talent_name = self.job_skill_name(job)
                skill_description = self.job_skill_description(job).rstrip("。")
                self.text(bonus, x, detail_y, detail_size, MUTED, "center", "center",
                          max_width=186, max_height=18, min_size=8)
                self.text(f"專屬：{talent_name}", x, detail_y - line_gap, detail_size, GOLD,
                          "center", "center", True, max_width=188, max_height=18,
                          min_size=8)
                for line_index, line in enumerate(
                        self.wrap_text_pixels(skill_description, 188, detail_size)[:2]):
                    self.text(line, x, detail_y - line_gap * (2 + line_index), detail_size, INK,
                              "center", "center", max_width=188, max_height=16,
                              min_size=8)
            page_label = f"{self.job_page + 1}/{self.max_job_page() + 1}"
            self.text(page_label, 590, 205, 11, MUTED, "center", "center",
                      max_width=80, max_height=16)

    def draw_game(self) -> None:
        p = self.player
        job_text = p.job if not p.sub_job else f"{p.job}/{p.sub_job}"
        self.panel(20, 465, 315, 235, "角色資料")
        stat_rows = (
            (f"{p.name}｜{p.sex}", 628, 21, INK, True),
            (f"{p.race}・{job_text}　{self.level_label(p.lv)}", 598, 16, GOLD, False),
            (f"血量　{max(0, p.hp)} / {p.max_hp}", 565, 16, RED, True),
            (f"攻擊　{p.attack}　防禦　{p.defense}　幸運　{p.luck}", 532, 15, INK, False),
            (f"金幣　{p.gold}G　　藥水　{self.total_potions()}", 500, 15, INK, False),
        )
        for value, y, size, color, bold in stat_rows:
            self.text(value, 40, y, size, color, "left", "center", bold,
                      max_width=270, max_height=24, min_size=10)

        self.panel(20, 15, 315, 430, "冒險紀錄")
        prepared_logs = self.prepared_log_cards()
        maximum_log_scroll = self.max_log_scroll(prepared_logs)
        self.log_scroll = max(0, min(self.log_scroll, maximum_log_scroll))
        visible_logs = self.visible_log_cards()
        log_cursor = 394.0
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
                          max_width=220, max_height=22, min_size=9)
            else:
                self.text(lines[0], 76, card_bottom + card_height / 2 + 10, 11,
                          line_color, anchor_y="center",
                          max_width=220, max_height=20, min_size=9)
                self.text(lines[1], 76, card_bottom + card_height / 2 - 10, 11,
                          line_color, anchor_y="center",
                          max_width=220, max_height=20, min_size=9)
            log_cursor = card_bottom - 5
        if maximum_log_scroll > 0:
            track_left, track_bottom = 321.0, 32.0
            track_width, track_height = 10, 381
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

        if self.scene == self.Scene.TALENT:
            self.panel(360, 58, 800, 642)
            self.text(f"{p.job}天賦", 760, 652, 34, GOLD, "center", "center", True,
                      max_width=700, max_height=45)
            self.text(f"剩餘點數 {p.talent_points}｜已投入 {self.class_talent_spent()} / 10",
                      760, 618, 16, INK, "center", "center",
                      max_width=680, max_height=24)
            self.text("每層可自由分配點數；該層合計投入 3 點後解鎖下一層，最後一層投入 1 點。",
                      760, 594, 13, MUTED, "center", "center",
                      max_width=680, max_height=22, min_size=11)
            tier_titles = {
                1: "第一層：熟練基礎",
                2: "第二層：強化戰技",
                3: "第三層：絕境求生",
                4: "第四層：終局絕招",
            }
            for tier, title in tier_titles.items():
                button_y = 505 - (tier - 1) * 125 if tier < 4 else 130
                title_x = 430 if tier < 4 else 640
                self.text(title, title_x, button_y + 60, 13, GOLD, "left", "center", True,
                          max_width=260, max_height=18, min_size=11)
            for talent_id, talent in self.class_talent_defs().items():
                tier = int(talent["tier"])
                side = int(talent["side"])
                if tier < 4:
                    card_left = 425 + side * 370
                    button_y = 505 - (tier - 1) * 125
                else:
                    card_left = 610
                    button_y = 130
                rank = self.class_talent_rank(talent_id)
                card_border = (*GOLD, 190) if rank > 0 else (87, 97, 112, 80)
                card_fill = (32, 22, 52, 190) if rank > 0 else (6, 10, 18, 132)
                self.rect(card_left, button_y - 48, 300, 96, card_fill, card_border, 1)
        elif self.scene == self.Scene.SUBCLASS:
            self.panel(360, 135, 800, 565, "選擇副職業")
            self.text("選擇副職業", 760, 525, 34, GOLD, "center", "center", True,
                      max_width=700, max_height=45)
            self.text(f"{p.name}已經是{self.level_label(10)}，可以選一個不同於{p.job}的副職業。",
                      760, 475, 17, INK, "center", "center",
                      max_width=670, max_height=26)
            self.text("副職業只增加該職業的專屬技能，不改變原本成長與天賦。",
                      760, 440, 14, MUTED, "center", "center",
                      max_width=670, max_height=24, min_size=10)
            centers = ((570, 355), (950, 355), (570, 225), (950, 225))
            for index, job in enumerate(self.subclass_options()):
                x, y = centers[index]
                left = x - 122
                text_top = y - 48
                self.text(self.job_skill_name(job), left, text_top, 17, GOLD,
                          "left", "center", True,
                          max_width=244, max_height=22, min_size=15)
                for line_index, line in enumerate(
                        self.wrap_text_pixels(self.job_skill_tooltip(job), 244, 12)[:2]):
                    self.text(line, left, text_top - 24 - line_index * 17, 12, INK,
                              "left", "center", max_width=244, max_height=16)
        elif self.scene == self.Scene.BATTLE and self.enemy:
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
            dual = len(self.enemies) > 1
            enemy_positions = (865, 1055) if dual else (950,)
            anim_index = self.attack_animation.enemy_index if self.attack_animation else -1
            if dual:
                self.enemy_hitboxes = []
                for index, foe in enumerate(self.enemies):
                    ex = enemy_positions[index] + (enemy_offset if index == anim_index else 0)
                    portrait = (self.enemy_portraits[index]
                                if index < len(self.enemy_portraits) else self.enemy_portrait)
                    arcade.draw_texture_rect(portrait, arcade.XYWH(ex, 460, 175, 175))
                    self.enemy_hitboxes.append((enemy_positions[index] - 88, 372.0, 176.0, 176.0))
                    targeted = index == self.target_index
                    if targeted:
                        self.rect(enemy_positions[index] - 92, 369, 184, 184,
                                  (0, 0, 0, 0), (*GOLD, 210), 2)
                        self.text("▼ 目標", enemy_positions[index], 568, 13, GOLD,
                                  "center", "center", True, max_width=100, max_height=18)
                    self.text(foe.name, enemy_positions[index], 352, 13,
                              INK if targeted else MUTED, "center", "center", True,
                              max_width=180, max_height=20, min_size=10)
                    self.bar(enemy_positions[index] - 80, 318, 160, foe.hp, foe.max_hp, RED,
                             f"{max(0, foe.hp)} / {foe.max_hp}")
                    self.shield_bar(enemy_positions[index] - 80, 296, 160, foe.block, foe.max_hp)
                    self.text(f"攻擊 {foe.attack}　防禦 {foe.defense}",
                              enemy_positions[index], 274, 11, MUTED, "center", "center",
                              max_width=180, max_height=16, min_size=7)
                    self.text(f"意圖：{self.enemy_intent_label(foe)}",
                              enemy_positions[index], 254, 11, GOLD, "center", "center", True,
                              max_width=185, max_height=16, min_size=7)
                    foe_status = []
                    if foe.corrosion_turns > 0:
                        foe_status.append(f"腐蝕 {foe.corrosion_damage}×{foe.corrosion_turns}")
                    if foe.agony_turns > 0:
                        agony_total = foe.agony_damage * max(1, foe.agony_stacks)
                        foe_status.append(
                            f"痛苦 {agony_total}×{foe.agony_turns} 層{foe.agony_stacks}"
                        )
                    if foe.doom_turns > 0:
                        foe_status.append(f"末日 {foe.doom_turns}")
                    if foe.weak_turns > 0:
                        foe_status.append("衰弱")
                    if foe.immune_turns > 0:
                        foe_status.append("免疫")
                    if foe.reflect_turns > 0:
                        foe_status.append("反彈")
                    if foe_status:
                        self.text("｜".join(foe_status), enemy_positions[index], 235, 10,
                                  (126, 218, 83), "center", "center", True,
                                  max_width=185, max_height=15, min_size=7)
            else:
                self.enemy_hitboxes = []
                arcade.draw_texture_rect(self.enemy_portrait,
                                         arcade.XYWH(950 + enemy_offset, 435, 255, 255))
            self.draw_skill_effects()
            vs_x = 705 if dual else 752
            self.text(f"{self.level_label(p.lv)}戰鬥", vs_x, 512, 20, GOLD,
                      "center", "center", True, max_width=220, max_height=28)
            self.text("VS", vs_x, 450, 30, GOLD, "center", "center", True,
                      max_width=80, max_height=42)
            self.text(p.name, 555, 300, 16, INK, "center", "center", True,
                      max_width=260, max_height=24)
            self.bar(435, 255, 240, p.hp, p.max_hp, GREEN,
                     f"血量 {max(0, p.hp)} / {p.max_hp}")
            self.shield_bar(435, 233, 240, self.player_block, p.max_hp)
            self.text(f"攻擊 {p.attack}　防禦 {p.defense}", 555, 207, 12, MUTED,
                      "center", "center", max_width=240, max_height=18, min_size=7)
            if not dual:
                self.text(e.name, 950, 300, 16, INK,
                          "center", "center", True, max_width=260, max_height=24)
                self.bar(830, 255, 240, e.hp, e.max_hp, RED, f"血量 {max(0, e.hp)} / {e.max_hp}")
                self.shield_bar(830, 233, 240, self.enemy_block, e.max_hp)
                self.text(f"攻擊 {e.attack}　防禦 {e.defense}", 950, 207, 12, MUTED,
                          "center", "center", max_width=240, max_height=18, min_size=7)
                self.text(f"意圖：{self.enemy_intent_label()}", 950, 186, 12, GOLD,
                          "center", "center", True, max_width=260, max_height=18, min_size=8)
                enemy_status = []
                if e.corrosion_turns > 0:
                    enemy_status.append(f"腐蝕 {e.corrosion_damage}×{e.corrosion_turns}")
                if e.agony_turns > 0:
                    agony_total = e.agony_damage * max(1, e.agony_stacks)
                    enemy_status.append(
                        f"痛苦 {agony_total}×{e.agony_turns} 層{e.agony_stacks}"
                    )
                if e.doom_turns > 0:
                    enemy_status.append(f"末日 {e.doom_turns}")
                if e.weak_turns > 0:
                    enemy_status.append("衰弱")
                if e.immune_turns > 0:
                    enemy_status.append("免疫")
                if e.reflect_turns > 0:
                    enemy_status.append("反彈")
                if enemy_status:
                    self.text("｜".join(enemy_status), 950, 166, 11,
                              (126, 218, 83), "center", "center", True,
                              max_width=260, max_height=17, min_size=8)
            status_parts = []
            if self.player_dot_damage > 0:
                dot_total = self.player_dot_damage * max(1, self.player_dot_stacks)
                stack_text = (
                    f" 層{self.player_dot_stacks}" if self.player_dot_stacks > 1 else ""
                )
                status_parts.append(
                    f"黑霧 {dot_total}×{self.player_dot_turns}{stack_text}"
                )
            if self.player_curse_turns > 0:
                status_parts.append(f"詛咒 {self.player_curse_turns}")
            if self.warrior_attack_bonus > 0:
                status_parts.append(f"血祭+{self.warrior_attack_bonus}")
            if self.warrior_blood_regen_turns > 0:
                status_parts.append(
                    f"回流 {self.warrior_blood_regen}×{self.warrior_blood_regen_turns}"
                )
            if self.player_attack_immunity_turns > 0:
                status_parts.append("庇護")
            if self.player_stun_immunity_turns > 0:
                status_parts.append("醒神")
            if self.potion_iron_skin_turns > 0:
                status_parts.append("鐵膚")
            if self.stealth_turns > 0:
                status_parts.append("隱身")
            if self.forced_critical:
                status_parts.append("暴擊")
            if status_parts:
                for line_index in range(0, len(status_parts), 4):
                    self.text("｜".join(status_parts[line_index:line_index + 4]),
                              555, 188 - (line_index // 4) * 18, 12, GOLD,
                              "center", "center", True,
                              max_width=300, max_height=18, min_size=8)
            if self.has_class_talents():
                self.rect(405, 15, 710, 112, (5, 10, 18, 170), (115, 132, 160, 135), 1)
            if self.battle_action_points > 1:
                self.text(f"行動點 {self.player_actions_left}/{self.battle_action_points}",
                          412, 132, 13, GOLD, "left", "center", True,
                          max_width=130, max_height=18)
            for floating in self.floating_damage:
                if floating.target == "player":
                    x = 555
                elif dual:
                    x = enemy_positions[min(floating.target_index, len(enemy_positions) - 1)]
                else:
                    x = 950
                on_dual_enemy = dual and floating.target == "enemy"
                y = (545 if on_dual_enemy else 580) + floating.elapsed * 54
                alpha = int(255 * max(0, 1 - floating.elapsed / .9))
                if floating.critical and not floating.healing and floating.elapsed < .68:
                    burst_phase = floating.elapsed / .68
                    burst_alpha = int(255 * (1 - burst_phase) ** 1.35)
                    burst_scale = .72 if on_dual_enemy else 1.0
                    burst_size = (185 + 235 * burst_phase) * burst_scale
                    burst_y = 460 if on_dual_enemy else 435
                    burst_angle = (-18 if floating.target == "player" else 18) + burst_phase * 42
                    arcade.draw_texture_rect(
                        self.critical_effect,
                        arcade.XYWH(x, burst_y, burst_size, burst_size),
                        angle=burst_angle,
                        alpha=burst_alpha,
                    )
                    if burst_phase < .38:
                        echo_phase = burst_phase / .38
                        arcade.draw_texture_rect(
                            self.critical_effect,
                            arcade.XYWH(x, burst_y, burst_size * (.58 + echo_phase * .28),
                                        burst_size * (.58 + echo_phase * .28)),
                            angle=-burst_angle * .65,
                            alpha=int(burst_alpha * .48),
                        )
                if floating.healing:
                    value, color = f"+{floating.amount}", (*GREEN, alpha)
                else:
                    value = "0" if floating.amount == 0 else f"{'暴擊 ' if floating.critical else ''}-{floating.amount}"
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
        elif self.scene == self.Scene.CAMPFIRE:
            self.activity_canvas(self.campfire_background, "營火")
            self.panel(405, 95, 710, 320)
            self.text(f"{self.level_label(p.lv)}營火", 760, 372, 28, GOLD,
                      "center", "center", True, max_width=650, max_height=36)
            self.text("火光暫時逼退黑霧。選擇一種整備方式，然後繼續前進。",
                      760, 332, 15, INK, "center", "center",
                      max_width=650, max_height=24, min_size=12)
            self.text(f"目前血量 {max(0, p.hp)} / {p.max_hp}｜攻擊 {p.attack}｜防禦 {p.defense}｜幸運 {p.luck}｜金錢 {p.gold}G",
                      760, 302, 14, MUTED, "center", "center",
                      max_width=650, max_height=22, min_size=10)
        elif self.scene == self.Scene.SHOP:
            self.activity_canvas(self.shop_background, "藥水商")
            self.panel(405, 425, 710, 155)
            affordable_count = sum(1 for kind in self.POTIONS if self.potion_available(kind))
            self.text("霧巷藥水商",
                      760, 545, 22, GOLD, "center", "center", True,
                      max_width=650, max_height=30)
            self.text(f"持有 {p.gold}G｜買得起 {affordable_count}/{len(self.POTIONS)} 種｜同款越買越貴",
                      760, 505, 16, INK, "center", "center",
                      max_width=650, max_height=24)
            self.text(self.shop_lore, 760, 464, 13, MUTED, "center", "center",
                      max_width=650, max_height=22, min_size=10)
        elif self.scene == self.Scene.EVENT:
            background_number = self.event_background_number(self.event_number)
            self.activity_canvas(self.event_background(background_number), self.event_title)
            self.panel(405, 135, 710, 230)
            event_lines = self.event_messages[-3:]
            wrapped_lines: list[tuple[str, tuple[int, int, int]]] = []
            for index, message in enumerate(event_lines):
                if not message:
                    continue
                is_choice = message.startswith("你選擇")
                line_limit = 1 if is_choice else (3 if len(event_lines) == 1 else 2)
                color = GOLD if is_choice else INK
                for line in self.wrap_text_pixels(message, 650, 15)[:line_limit]:
                    wrapped_lines.append((line, color))
            wrapped_lines = wrapped_lines[:6]
            start_y = 318 if len(wrapped_lines) <= 5 else 330
            for line_index, (line, color) in enumerate(wrapped_lines):
                self.text(line, 760, start_y - line_index * 25, 15, color,
                          "center", "center", max_width=650, max_height=22, min_size=13)
        elif self.scene == self.Scene.END:
            self.panel(360, 135, 800, 565)
            self.text("恭 喜 過 關" if self.victory else "G A M E  O V E R",
                      760, 505, 44, GOLD if self.victory else RED, "center", "center", True,
                      max_width=700, max_height=60)
            if self.victory:
                final_name = self.final_enemy_name or "終焉之主"
                self.text(f"{p.name}擊敗{final_name}，王城終於迎回黎明！",
                          760, 420, 23, INK, "center", "center",
                          max_width=690, max_height=34)
            else:
                self.text(f"{p.name}倒在了冒險途中。", 760, 420, 23, INK,
                          "center", "center", max_width=690, max_height=34)
            self.text(f"最終關卡 {self.level_label(p.lv)}｜攻擊 {p.attack}｜防禦 {p.defense}｜幸運 {p.luck}",
                      760, 350, 16, MUTED, "center", "center",
                      max_width=680, max_height=24, min_size=9)
        else:
            self.panel(360, 135, 800, 565, "冒險")
            arcade.draw_texture_rect(self.hero_portrait, arcade.XYWH(760, 435, 305, 305))
            stage_title, stage_text = self.journey_stage()
            self.text(stage_title, 760, 263, 22, GOLD, "center", "center", True,
                      max_width=680, max_height=30)
            self.text(self.journey_lore, 760, 225, 14, INK, "center", "center",
                      max_width=670, max_height=23, min_size=10)
            if p.lv < 21:
                self.text(f"{stage_text}｜目前 {self.level_label(p.lv)}",
                          760, 190, 15, MUTED, "center", "center",
                          max_width=670, max_height=23, min_size=10)
            else:
                self.text("終焉之主已經甦醒，最後一戰就在前方！",
                          760, 190, 17, RED, "center", "center", True,
                          max_width=670, max_height=25)
