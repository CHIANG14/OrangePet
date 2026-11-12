"""Animated, resolution independent desktop mascots."""
from __future__ import annotations

import math
from functools import partial

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen


def path(start, *curves):
    shape = QPainterPath(QPointF(*start))
    for curve in curves:
        shape.cubicTo(*curve)
    shape.closeSubpath()
    return shape


def gradient(top, bottom, y, height):
    brush = QLinearGradient(0, y, 0, y + height)
    brush.setColorAt(0, QColor(top))
    brush.setColorAt(1, QColor(bottom))
    return brush


def stroke(color, width):
    return QPen(QColor(color), width, Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)


def shape(p, outline, fill, ink=None, width=2.5):
    p.setPen(stroke(ink, width) if ink else Qt.PenStyle.NoPen)
    p.setBrush(QColor(fill) if isinstance(fill, str) else fill)
    p.drawPath(outline)


def oval(p, x, y, w, h, fill, ink=None, width=2.5):
    p.setPen(stroke(ink, width) if ink else Qt.PenStyle.NoPen)
    p.setBrush(QColor(fill) if isinstance(fill, str) else fill)
    p.drawEllipse(QRectF(x, y, w, h))


def curve(p, start, points, color, width=2.5):
    line = QPainterPath(QPointF(*start))
    line.quadTo(*points)
    p.setPen(stroke(color, width))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(line)


def sparkle(p, x, y, size, color):
    s = size
    shape(p, path((x, y - s), (x + s*.2, y - s*.2, x + s*.2, y - s*.2, x + s, y),
                  (x + s*.2, y + s*.2, x + s*.2, y + s*.2, x, y + s),
                  (x - s*.2, y + s*.2, x - s*.2, y + s*.2, x - s, y),
                  (x - s*.2, y - s*.2, x - s*.2, y - s*.2, x, y - s)), color)


PALETTES = {
    "cat": ("#88563f", "#ffe1a6", "#f3a064", "#fff1d8", "#5e9b86"),
    "frog": ("#577454", "#dceda2", "#a6cf83", "#fbf6cd", "#77a573"),
    "puppy": ("#805b47", "#fff0cf", "#eac095", "#fff8e7", "#8c9fc4"),
    "bunny": ("#88627e", "#fff3f6", "#eec8de", "#fff8fa", "#b082ad"),
}


def eye(p, x, y, ink, blink, happy, glance, frog=False):
    if happy or blink:
        control = y - 6 if happy else y + 5
        curve(p, (x - 8, y + 2), (x, control, x + 8, y + 2), ink, 3)
        return
    if frog:
        oval(p, x - 14, y - 16, 28, 32, "#fffce9")
    x += glance * 1.6
    oval(p, x - 8, y - 11, 16, 23, gradient("#4f3938", "#78514b", y - 11, 23))
    oval(p, x - 4.5, y - 8, 6.4, 7.1, "#fffaf4")
    oval(p, x + 2.1, y + 4, 3.0, 3.2, "#e9b8ab")


def face(p, species, ink, cream, frame, happy, singing, talking, direction):
    frog = species == "frog"
    eye_y = 66 if frog else 88
    for x in ((63, 137) if frog else (76, 124)):
        eye(p, x, eye_y, ink, frame % 5.1 < 0.16, happy, direction, frog)
    blush_y = 97 if frog else 102
    for x in (54, 146):
        oval(p, x - 11, blush_y, 22, 11, "#f2a3a0")
        for offset in (-3, 3):
            curve(p, (x + offset, blush_y + 3),
                  (x + offset - 1, blush_y + 5, x + offset - 2, blush_y + 7),
                  "#dc8788", 1.25)
    if not frog:
        nose_width = 14 if species == "puppy" else 9
        oval(p, 100 - nose_width / 2, 101, nose_width, 6.5,
             ink if species == "puppy" else "#d58183")
    mouth_y = 102 if frog else 111
    if singing or talking or happy:
        height = (7 + 8 * (.5 + .5 * math.sin(frame * 8)) if singing
                  else 3 + 3 * (.5 + .5 * math.sin(frame * 5)) if talking
                  else 13)
        width = 25 if happy else 15 if singing else 10
        oval(p, 100 - width / 2, mouth_y - 1, width, height, "#633f40")
        if height > 7:
            oval(p, 100 - width * .27, mouth_y + height * .53,
                 width * .54, height * .32, "#f4a2a4")
    elif species == "puppy":
        oval(p, 95, mouth_y + 1, 10, 10, "#f39a9a", ink, 1.4)
        curve(p, (90, mouth_y - 1), (100, mouth_y + 8, 110, mouth_y - 1), ink, 2)
    else:
        curve(p, (91, mouth_y), (95, mouth_y + 7, 100, mouth_y - 1), ink, 2.1)
        curve(p, (100, mouth_y - 1), (105, mouth_y + 7, 109, mouth_y), ink, 2.1)


def clock(p, text, font_name, accent, ink, paw):
    if not text:
        return
    oval(p, 75, 127, 14, 9, accent, ink, 1.6)
    oval(p, 111, 127, 14, 9, accent, ink, 1.6)
    p.setPen(stroke(ink, 2.1))
    p.setBrush(QColor(accent))
    p.drawRoundedRect(QRectF(70, 134, 60, 30), 9, 9)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#fff9e9"))
    p.drawRoundedRect(QRectF(76, 139, 48, 20), 6, 6)
    font = QFont(font_name)
    font.setPixelSize(14)
    font.setWeight(QFont.Weight.Bold)
    p.setFont(font)
    p.setPen(QColor("#4c5145"))
    p.drawText(QRectF(76, 139, 48, 20), Qt.AlignmentFlag.AlignCenter, text)
    for x in (65, 122):
        oval(p, x, 143, 13, 12, paw, ink, 1.7)


def cat_details(p, ink, top, base, frame):
    sway = math.sin(frame * 3) * 5
    tail = QPainterPath(QPointF(135, 148))
    tail.cubicTo(161, 165, 190, 138, 173 + sway, 119)
    for color, width in ((ink, 19), (base, 14)):
        p.setPen(stroke(color, width))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(tail)
    for mirror in (False, True):
        p.save()
        if mirror:
            p.translate(200, 0)
            p.scale(-1, 1)
        shape(p, path((42, 75), (30, 53, 32, 17, 42, 19),
                      (52, 18, 76, 40, 79, 48), (70, 66, 55, 76, 42, 75)),
              gradient(top, base, 19, 60), ink)
        shape(p, path((43, 54), (39, 40, 39, 30, 44, 29),
                      (51, 31, 64, 44, 66, 49), (61, 55, 49, 58, 43, 54)), "#f4a8a0")
        p.restore()


def bunny_details(p, ink, top, base, frame, walking):
    oval(p, 141, 125, 31, 29, "#fff8fa", ink)
    for x, angle in ((73, -17), (121, 12)):
        p.save()
        p.translate(x, 64)
        p.rotate(angle + (math.sin(frame * 7) * 4 if walking else 0))
        oval(p, -15, -61, 30, 77, gradient(top, base, -60, 78), ink)
        oval(p, -7, -54, 14, 55, gradient("#fbd8e3", "#efa9c5", -54, 55))
        p.restore()


def puppy_details(p, ink, frame):
    oval(p, 142, 132 + math.sin(frame * 7) * 4, 29, 18, "#c38b69", ink)


def puppy_ears(p, ink, frame, walking):
    for mirror in (False, True):
        p.save()
        if mirror:
            p.translate(200, 0)
            p.scale(-1, 1)
        p.translate(46, 57)
        p.rotate(math.sin(frame * 8) * (9 if walking else 3))
        shape(p, path((14, -8), (-2, -12, -22, 3, -24, 22),
                      (-30, 49, -18, 63, -7, 59),
                      (5, 57, 14, 31, 20, 13), (24, 4, 22, -6, 14, -8)),
              gradient("#d09b76", "#a56b53", -10, 72), ink)
        curve(p, (-12, 38), (-15, 47, -10, 51), "#eab68d", 3)
        p.restore()


def accessory(p, species, accent, ink):
    if species == "frog":
        shape(p, path((98, 48), (77, 47, 76, 28, 79, 25),
                      (93, 26, 102, 34, 98, 48)), "#7eb379", ink, 1.7)
        shape(p, path((99, 48), (98, 31, 110, 28, 120, 30),
                      (120, 41, 112, 49, 99, 48)), "#b3d687", ink, 1.7)
        return
    if species == "bunny":
        sparkle(p, 138, 55, 10, "#f3b472")
        oval(p, 146, 47, 5, 5, "#fff4c4")
        return
    if species == "cat":
        for x, bend in ((87, 4), (100, 0), (113, -4)):
            curve(p, (x, 47), (x + bend, 51, x + bend, 58), "#d98f59", 4.5)
    # Small bow tie keeps each animal's accent visible without the clock.
    for direction in (-1, 1):
        shape(p, path((100, 139), (100 + 21*direction, 122, 100 + 23*direction, 131, 100 + 20*direction, 145),
                      (100 + 17*direction, 151, 100 + 6*direction, 147, 100, 139)), accent, ink, 1.6)
    oval(p, 95, 134, 10, 10, "#f9d38d", ink, 1.5)


def soft_animal(p, species, frame, walking, happy, singing, talking, direction, clock_text, clock_font):
    ink, top, base, cream, accent = PALETTES[species]
    coat = gradient(top, base, 38, 128)
    if species == "cat":
        cat_details(p, ink, top, base, frame)
    elif species == "bunny":
        bunny_details(p, ink, top, base, frame, walking)
    elif species == "puppy":
        puppy_details(p, ink, frame)
    oval(p, 56, 102, 88, 64, coat, ink)
    oval(p, 77, 122, 46, 38, cream)
    for x, sign in ((64, 1), (110, -1)):
        step = math.sin(frame * 9) * 6 * sign if walking else 0
        oval(p, x, 148 + step, 27, 18, cream, ink, 2)
        for toe in (10, 16):
            curve(p, (x + toe, 159 + step), (x + toe, 161 + step, x + toe, 163 + step),
                  ink, 1.15)
    if species == "frog":
        head = path((34, 94), (30, 81, 33, 70, 38, 67),
                    (36, 30, 82, 27, 90, 57), (97, 55, 103, 55, 110, 57),
                    (120, 27, 164, 31, 162, 67), (183, 93, 165, 132, 122, 134),
                    (82, 144, 39, 129, 34, 94))
    else:
        head = path((36, 88), (37, 56, 61, 42, 100, 43),
                    (140, 41, 164, 58, 165, 91),
                    (170, 120, 142, 136, 100, 134),
                    (56, 136, 31, 118, 36, 88))
    shape(p, head, coat, ink)
    if species == "puppy":
        p.save()
        p.setClipPath(head)
        oval(p, 48, 55, 49, 50, "#e2aa82")
        p.restore()
        puppy_ears(p, ink, frame, walking)
    if species != "frog":
        oval(p, 77, 98, 46, 27, cream)
    else:
        oval(p, 68, 104, 64, 24, "#eef4bd")
    accessory(p, species, accent, ink)
    face(p, species, ink, cream, frame, happy, singing, talking, direction)
    clock(p, clock_text, clock_font, accent, ink, top)


def milk_frog(p, frame, walking, happy, singing, talking, direction, clock_text, clock_font):
    # The uneven eyes, hunched silhouette and tiny mouth follow the supplied reference.
    ink = "#977436"
    coat = gradient("#f8df79", "#ca9747", 21, 145)
    move = math.sin(frame * 8) * 7 if walking else 0
    for x, y in ((70, 151 + move), (113, 149 - move)):
        shape(p, path((x, y), (x + 8, y - 2, x + 16, y + 2, x + 16, y + 12),
                      (x + 14, y + 19, x - 8, y + 18, x - 8, y + 13),
                      (x - 9, y + 9, x - 1, y + 9, x, y)), "#af7f39", ink, 2)
    bean = path((58, 96), (64, 81, 49, 79, 51, 59),
                (49, 28, 75, 15, 99, 19), (121, 20, 130, 35, 139, 55),
                (153, 76, 164, 107, 158, 133),
                (154, 158, 130, 165, 101, 164),
                (63, 167, 42, 153, 44, 128), (43, 114, 53, 108, 58, 96))
    shape(p, bean, coat, ink, 2)
    oval(p, 63, 96, 69, 59, gradient("#fff0b4", "#ebca7e", 96, 60))
    for x, y, angle in ((58, 103, -13 + move), (141, 105, 12 - move)):
        p.save()
        p.translate(x, y)
        p.rotate(angle + (math.sin(frame * 12) * 29 if happy else 0))
        shape(p, path((-8, -13), (-17, 1, -17, 25, -9, 35),
                      (-4, 42, 4, 37, 5, 29), (4, 13, 9, -5, -8, -13)),
              gradient("#e1b551", "#ac813c", -13, 52), ink, 1.8)
        p.restore()
    glance = -1 if direction < 0 else 2
    for x, y, radius in ((58, 57, 7), (89, 53, 12)):
        if frame % 4.8 < 0.15:
            curve(p, (x - radius, y), (x, y + 3, x + radius, y - 1), "#514b31", 2.6)
            continue
        oval(p, x - radius, y - radius, radius * 2, radius * 2, "#e7da91", "#c3a24e", 1.25)
        pupil = radius * .77
        oval(p, x - pupil + glance, y - pupil, pupil * 2, pupil * 2,
             gradient("#45694c", "#172e28", y - pupil, pupil * 2))
        oval(p, x - radius * .4 + glance, y - radius * .54, radius * .42, radius * .39, "#f2f2cd")
    if happy or singing or talking:
        height = (14 + 10 * abs(math.sin(frame * 9)) if happy else
                  6 + 11 * abs(math.sin(frame * 8)) if singing else
                  2 + 5 * abs(math.sin(frame * 5)))
        width = 38 if happy else 23
        oval(p, 68 - width / 2, 73, width, height, "#4e3a28")
        if height > 9:
            oval(p, 68 - width * .32, 73 + height * .52, width * .64, height * .36, "#bb7762")
    else:
        curve(p, (51, 73), (60, 71, 77, 73), "#5a492d", 2.15)
    clock(p, clock_text, clock_font, "#bf9b4f", ink, "#e5bc65")


def draw_character(species, p: QPainter, box: QRectF, frame=0, walking=False,
                   happy=False, singing=False, talking=False, direction=1,
                   clock_text="", clock_font="Microsoft YaHei UI"):
    p.save()
    try:
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        scale = min(box.width() / 200, box.height() / 180)
        p.translate(box.x() + (box.width() - 200 * scale) / 2,
                    box.y() + (box.height() - 180 * scale) / 2)
        p.scale(scale, scale)
        oval(p, 42, 163, 120, 12, QColor(72, 51, 41, 23))
        bob = -abs(math.sin(frame * 8)) * 3.5 if walking else math.sin(frame * 2) * 1.2
        p.translate(0, bob)
        if species == "milk_frog":
            milk_frog(p, frame, walking, happy, singing, talking, direction, clock_text, clock_font)
        else:
            soft_animal(p, species, frame, walking, happy, singing, talking,
                        direction, clock_text, clock_font)
        if happy and species != "milk_frog":
            sparkle(p, 25, 56 + math.sin(frame * 4) * 5, 7, "#edab74")
            sparkle(p, 174, 36 + math.cos(frame * 4) * 5, 9, "#e995ab")
    finally:
        p.restore()


draw_cat = partial(draw_character, "cat")
draw_frog = partial(draw_character, "frog")
draw_puppy = partial(draw_character, "puppy")
draw_bunny = partial(draw_character, "bunny")
draw_milk_frog = partial(draw_character, "milk_frog")

CHARACTERS = {
    "cat": ("小猫", draw_cat),
    "frog": ("小青蛙", draw_frog),
    "puppy": ("小奶狗", draw_puppy),
    "bunny": ("小兔子", draw_bunny),
    "milk_frog": ("奶蛙", draw_milk_frog),
}
