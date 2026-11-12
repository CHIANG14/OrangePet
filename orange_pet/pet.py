from __future__ import annotations

import math
import random
import time

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QGuiApplication, QLinearGradient, QPainter, QPainterPath, QPen,
)
from PySide6.QtWidgets import QApplication, QWidget

from .art import draw_cat
from .characters import CHARACTERS

# Media actions exposed by the lyric control row, in display order.
CONTROL_ACTIONS = ("previous", "toggle", "next")


class Pet(QWidget):
    petted = Signal()
    panel_requested = Signal()
    menu_requested = Signal(object)
    moved = Signal()
    media_requested = Signal(str)
    timer_toggle_requested = Signal()
    lyric_close_requested = Signal()

    def __init__(self):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setWindowTitle("橘子 · 桌面小猫")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self._pet_size = 1.0
        self.apply_size(1.0)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip("单击沙漏：暂停/继续 · 单击歌词：播放控制 · 双击歌词区：关闭歌词展示 · 双击番茄钟 · 拖动换位置")
        self.walking_enabled = True
        self.focused = False
        self.singing = False
        self.lyric = ""
        self.lyric_char_index = 0
        self.lyric_char_total = 0
        self.lyric_font = "Microsoft YaHei UI"
        self.lyric_mode = "line"
        self._character_draw = draw_cat  # default; updated by apply_character()
        self.music_hint = ""
        # Song strip stays open only while music is actually playing.
        self.music_visible = False
        # Alarm clock held by the cat (shows the current time)
        self._clock_display = time.strftime("%H:%M")
        # Hourglass countdown state
        self.countdown_remaining = 0
        self.countdown_total = 0
        self.countdown_state = "ready"
        self.countdown_phase = "focus"
        # Lyric control row state
        self.controls_visible = False
        self.controls_hide_at = 0.0
        self._hover_control = None
        self._pressed_control = None
        self._ui_press = None
        self._countdown_press = False
        self.message = "我是橘子，摸摸我吧！"
        self.message_until = time.monotonic() + 10
        self.happy_until = 0.0
        # Treat celebration: a short dance with hops and sparkles.
        self.celebrate_until = 0.0
        self.celebrate_duration = 2.8
        self.direction = -1
        self.hovered = False
        self.drag_start = None
        self.press_pos = None
        self.dragging = False
        self.next_decision = time.monotonic() + 3
        self.roaming = False
        self.x_float = 0.0
        self.last_frame = time.monotonic()
        self.frame_time = 1.0
        self.click_timer = QTimer(self)
        self.click_timer.setSingleShot(True)
        self.click_timer.timeout.connect(self.petted)
        self.animation = QTimer(self)
        self.animation.timeout.connect(self.animate)
        self.animation.start(33)

    # ---- layout constants (base scale 1.0) ----
    CAT_H = 181         # cat drawing height
    LYRIC_H = 44        # lyric / message / control strip height

    def _lyric_rect(self):
        return QRectF(6, 4, self.width() - 12, self.LYRIC_H)

    def _cat_top(self):
        # Cat drawing has ~18px internal top padding; overlap the lyric rect so
        # the visible ears sit right beneath the lyrics.
        return self._lyric_rect().bottom() - 14 * self._pet_size

    def _cat_x(self):
        return (self.width() - 206 * self._pet_size) / 2

    def apply_size(self, scale: float):
        self._pet_size = scale
        w = int(320 * scale)
        h = int(self._cat_top() + self.CAT_H * scale) + 4
        self.setFixedSize(w, h)

    def apply_character(self, key: str):
        """Switch the vector character drawn in the pet window."""
        entry = CHARACTERS.get(key)
        if entry:
            self._character_draw = entry[1]
            self.update()

    def set_clock_text(self, text: str):
        """Update the time shown on the alarm clock in the cat's paws."""
        if text == self._clock_display:
            return
        self._clock_display = text
        self.update()

    def set_music_visible(self, visible: bool):
        """Show or close the song strip.  Playback state no longer drives this;
        the user closes it by double-clicking the strip or from the menu."""
        if visible == self.music_visible:
            return
        self.music_visible = visible
        if not visible:
            self.controls_visible = False
            self._hover_control = None
            self._pressed_control = None
            self._ui_press = None
        self.update()

    def say(self, text: str, happy=False, seconds=5):
        self.message = text
        self.message_until = time.monotonic() + seconds
        if happy:
            self.happy_until = time.monotonic() + 3
        self.update()

    def celebrate(self, seconds: float = 2.8):
        """Play a happy dance: hop, wiggle and sparkle for a moment."""
        now = time.monotonic()
        self.celebrate_duration = max(0.4, seconds)
        self.celebrate_until = now + self.celebrate_duration
        if now + self.celebrate_duration > self.happy_until:
            self.happy_until = now + self.celebrate_duration + 0.3
        self.update()

    def screen_rect(self):
        screen = QGuiApplication.screenAt(self.frameGeometry().center()) or self.screen()
        return screen.availableGeometry()

    def clamp(self):
        rect = self.screen_rect()
        x = max(rect.left(), min(self.x(), rect.right() - self.width() + 1))
        y = max(rect.top(), min(self.y(), rect.bottom() - self.height() + 1))
        self.move(x, y)
        self.x_float = float(x)

    def home(self):
        rect = QGuiApplication.primaryScreen().availableGeometry()
        self.move(rect.right() - self.width() - 35, rect.bottom() - self.height() + 4)
        self.clamp()

    def animate(self):
        now = time.monotonic()
        dt = min(now - self.last_frame, 0.1)
        self.last_frame = now
        self.frame_time += dt
        if self.controls_visible and now > self.controls_hide_at:
            self.controls_visible = False
            self._hover_control = None
            self.update()
        if now > self.next_decision:
            self.roaming = not self.roaming
            self.direction = random.choice((-1, 1))
            self.next_decision = now + random.uniform(4, 9)
        # Automatic movement is a standalone option: focus and music no longer
        # suppress it, only the user's walking setting does.
        can_walk = (self.walking_enabled and self.roaming and not self.hovered
                    and not self.dragging and self.press_pos is None
                    and now > self.happy_until)
        if can_walk:
            self.x_float += self.direction * dt * 30
            rect = self.screen_rect()
            right = rect.right() - self.width() + 1
            if self.x_float < rect.left() or self.x_float > right:
                self.direction *= -1
            self.move(round(self.x_float), self.y())
            x = max(rect.left(), min(self.x(), right))
            self.move(x, max(rect.top(), min(self.y(), rect.bottom() - self.height() + 1)))
            if x != round(self.x_float):
                self.x_float = float(x)
        self.is_walking = can_walk
        self.update()

    # ------------------------------------------------------------------ paint

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        now = time.monotonic()
        self._draw_lyric_area(p, now)
        cat_w = 206 * self._pet_size
        cat_h = self.CAT_H * self._pet_size
        cat_x = self._cat_x()
        cat_y = self._cat_top()
        talking = now < self.message_until and not self.singing
        celebrating = now < self.celebrate_until
        hop = 0.0
        if celebrating:
            span = max(0.001, self.celebrate_duration)
            t = 1.0 - max(0.0, self.celebrate_until - now) / span
            env = math.sin(math.pi * max(0.0, min(1.0, t)))  # ease in and out
            hop = -abs(math.sin(self.frame_time * 10)) * 9 * env
            tilt = math.sin(self.frame_time * 9) * 7 * env
            center = QPointF(cat_x + cat_w / 2, cat_y + cat_h * 0.66)
            p.save()
            p.translate(center.x(), center.y() + hop)
            p.rotate(tilt)
            p.translate(-center.x(), -center.y())
        self._character_draw(p, QRectF(cat_x, cat_y, cat_w, cat_h), self.frame_time,
                 getattr(self, "is_walking", False), now < self.happy_until,
                 self.singing, talking, self.direction,
                 clock_text=self._clock_display, clock_font=self.lyric_font)
        if celebrating:
            p.restore()
            self._draw_celebrate_sparkles(p, now, cat_x, cat_y, cat_w, cat_h, env, hop)
        self._draw_message_bubble(p, now)
        self._draw_side_countdown(p, now)
        p.end()

    def _draw_celebrate_sparkles(self, p, now, cat_x, cat_y, cat_w, cat_h, env, hop):
        """Golden four-point sparkles twinkling around the dancing cat."""
        spots = (
            (0.10, 0.05, 0.0), (0.90, 0.02, 1.7), (0.02, 0.38, 3.1),
            (0.98, 0.32, 4.4), (0.26, -0.06, 2.4), (0.74, -0.08, 5.2),
        )
        p.save()
        p.setPen(Qt.PenStyle.NoPen)
        for fx, fy, phase in spots:
            twinkle = 0.5 + 0.5 * math.sin(now * 6 + phase)
            r = (2.0 + 2.2 * twinkle) * self._pet_size
            cx = cat_x + fx * cat_w
            cy = cat_y + fy * cat_h + hop * 0.7 + math.sin(now * 4 + phase) * 2
            if phase % 2 < 1:
                color = QColor(242, 193, 78)
            else:
                color = QColor(255, 243, 206)
            color.setAlpha(int(60 + 170 * twinkle * env))
            p.setBrush(color)
            star = QPainterPath(QPointF(cx, cy - r))
            star.quadTo(QPointF(cx + r * 0.18, cy - r * 0.18), QPointF(cx + r, cy))
            star.quadTo(QPointF(cx + r * 0.18, cy + r * 0.18), QPointF(cx, cy + r))
            star.quadTo(QPointF(cx - r * 0.18, cy + r * 0.18), QPointF(cx - r, cy))
            star.quadTo(QPointF(cx - r * 0.18, cy - r * 0.18), QPointF(cx, cy - r))
            p.drawPath(star)
        p.restore()

    # ---- lyric area ----

    def _draw_lyric_area(self, p, now):
        if not self.music_visible:
            return
        if self.controls_visible:
            self._draw_controls(p)
            return
        text = self.lyric or self.music_hint
        if not text:
            return
        if self.lyric and self.lyric_mode == "word" and self.lyric_char_total > 0:
            self._draw_word_lyrics(p, text, now)
        else:
            self._draw_line_lyrics(p, text)

    def _draw_glass_pill(self, p, rect, radius):
        grad = QLinearGradient(0, rect.top(), 0, rect.bottom())
        grad.setColorAt(0.0, QColor(255, 253, 248, 205))
        grad.setColorAt(1.0, QColor(236, 243, 235, 145))
        p.setPen(QPen(QColor(255, 255, 255, 130), 1))
        p.setBrush(grad)
        p.drawRoundedRect(rect, radius, radius)
        clip = QPainterPath()
        clip.addRoundedRect(rect, radius, radius)
        p.save()
        p.setClipPath(clip)
        spec = QLinearGradient(0, rect.top(), 0, rect.top() + rect.height() * 0.45)
        spec.setColorAt(0.0, QColor(255, 255, 255, 110))
        spec.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setBrush(spec)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(QRectF(rect.left(), rect.top(), rect.width(), rect.height() * 0.5))
        p.restore()

    def _draw_line_lyrics(self, p, text):
        """Draw lyrics without border, with subtle shadow for readability."""
        rect = self._lyric_rect()
        display = text if len(text) <= 100 else text[:97] + "…"
        font = QFont(self.lyric_font, 10 if len(text) > 42 else 11)
        p.setFont(font)
        box = QRectF(rect.left() + 12, rect.top(), rect.width() - 24, rect.height())
        # Shadow
        p.setPen(QColor(0, 0, 0, 80))
        p.drawText(box.adjusted(1, 1, 1, 1),
                   Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, display)
        # Main text
        p.setPen(QColor("#526452"))
        p.drawText(box, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, display)

    def _draw_word_lyrics(self, p, text, now):
        """Draw lyrics character by character with bounce on the active char."""
        rect = self._lyric_rect()
        if not text:
            return
        display = text if len(text) <= 100 else text[:97] + "…"
        chars = list(display)
        active = min(self.lyric_char_index, len(chars) - 1)
        font = QFont(self.lyric_font, 11 if len(chars) <= 42 else 10)
        p.setFont(font)
        fm = QFontMetrics(font)
        widths = [fm.horizontalAdvance(ch) for ch in chars]
        total_w = sum(widths)
        if total_w < 1:
            return
        start_x = (self.width() - total_w) / 2
        y = rect.top() + 30
        for i, ch in enumerate(chars):
            x = start_x + sum(widths[:i])
            if i == active:
                bounce = -abs(math.sin(self.frame_time * 8)) * 4
                p.setPen(QColor(0, 0, 0, 60))
                p.drawText(QPoint(int(x) + 1, int(y + bounce) + 1), ch)
                p.setPen(QColor("#397761"))
                p.drawText(QPoint(int(x), int(y + bounce)), ch)
            elif i < active:
                p.setPen(QColor("#8a9a8a"))
                p.drawText(QPoint(int(x), int(y)), ch)
            else:
                p.setPen(QColor("#a8b8a8"))
                p.drawText(QPoint(int(x), int(y)), ch)

    # ---- lyric control row ----

    def _control_rects(self):
        rect = self._lyric_rect()
        count = len(CONTROL_ACTIONS)
        d = max(26.0, min(44.0, 30.0 * self._pet_size))
        margin = 10.0
        gap = max(2.0, (rect.width() - 2 * margin - count * d) / max(1, count - 1))
        cy = rect.center().y()
        x = rect.left() + margin
        rects = []
        for _ in range(count):
            rects.append(QRectF(x, cy - d / 2, d, d))
            x += d + gap
        return rects

    def _control_at(self, pos):
        if not self.controls_visible:
            return None
        for i, rect in enumerate(self._control_rects()):
            if rect.contains(pos):
                return i
        return None

    def _draw_controls(self, p):
        rect = self._lyric_rect()
        self._draw_glass_pill(p, rect, rect.height() / 2)
        for i, box in enumerate(self._control_rects()):
            active = self._hover_control == i or self._pressed_control == i
            grad = QLinearGradient(0, box.top(), 0, box.bottom())
            if active:
                grad.setColorAt(0.0, QColor(214, 234, 220, 235))
                grad.setColorAt(1.0, QColor(188, 216, 200, 195))
            else:
                grad.setColorAt(0.0, QColor(255, 255, 255, 195))
                grad.setColorAt(1.0, QColor(232, 240, 233, 145))
            p.setPen(QPen(QColor(255, 255, 255, 120), 1))
            p.setBrush(grad)
            p.drawEllipse(box)
            self._draw_control_icon(p, box, i, active)

    def _draw_control_icon(self, p, box, index, active):
        cx, cy = box.center().x(), box.center().y()
        k = box.width() / 30.0
        base = QColor("#1f5240") if active else QColor("#2d6450")
        if not self.singing and not self.lyric and not self.music_hint:
            base = QColor(base.red(), base.green(), base.blue(), 150)
        p.setPen(QPen(base, 1.8 * k, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                      Qt.PenJoinStyle.RoundJoin))
        p.setBrush(base)
        if index in (0, 2):  # previous / next: bar + two triangles
            direction = -1 if index == 0 else 1
            size = 8.0 * k
            bar_x = cx + direction * 7.5 * k
            p.drawRoundedRect(QRectF(bar_x - 1.0 * k, cy - size / 2, 2.0 * k, size), 1.0 * k, 1.0 * k)
            for offset in (-1.0, 4.0):
                tri_cx = cx + direction * offset * k
                tri = QPainterPath()
                tri.moveTo(tri_cx - direction * 2.6 * k, cy - size / 2)
                tri.lineTo(tri_cx - direction * 2.6 * k, cy + size / 2)
                tri.lineTo(tri_cx + direction * 3.2 * k, cy)
                tri.closeSubpath()
                p.drawPath(tri)
        elif index == 1:  # play / pause
            if self.singing:
                p.drawRoundedRect(QRectF(cx - 4.6 * k, cy - 5.2 * k, 3.2 * k, 10.4 * k), 1.2 * k, 1.2 * k)
                p.drawRoundedRect(QRectF(cx + 1.4 * k, cy - 5.2 * k, 3.2 * k, 10.4 * k), 1.2 * k, 1.2 * k)
            else:
                tri = QPainterPath()
                tri.moveTo(cx - 3.4 * k, cy - 5.4 * k)
                tri.lineTo(cx - 3.4 * k, cy + 5.4 * k)
                tri.lineTo(cx + 5.2 * k, cy)
                tri.closeSubpath()
                p.drawPath(tri)

    # ---- speech bubble (left of the cat) ----

    def _draw_message_bubble(self, p, now):
        if now >= self.message_until or not self.message:
            return
        left = 4.0
        right = self._cat_x() + 44 * self._pet_size - 2
        width = right - left
        if width < 30:
            return
        font = QFont(self.lyric_font, max(9, int(9 * self._pet_size)))
        fm = QFontMetrics(font)
        inner = width - 16
        per_line = max(1, int(inner / max(1, fm.horizontalAdvance("字"))))
        text = self.message.strip()
        limit = per_line * 4
        display = text if len(text) <= limit else text[: max(1, limit - 1)] + "…"
        lines = min(4, max(1, math.ceil(len(display) / per_line)))
        height = lines * fm.lineSpacing() + 12
        top = self._lyric_rect().bottom() + 2
        rect = QRectF(left, top, width, height)
        radius = min(11.0, height / 2)
        # Soft drop shadow, then a warm paper-like fill.
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(70, 60, 45, 26))
        p.drawRoundedRect(rect.adjusted(0, 2, 0, 2), radius, radius)
        grad = QLinearGradient(0, rect.top(), 0, rect.bottom())
        grad.setColorAt(0.0, QColor(255, 253, 247, 246))
        grad.setColorAt(1.0, QColor(248, 240, 226, 240))
        border = QColor(231, 220, 200, 220)
        p.setPen(QPen(border, 1))
        p.setBrush(grad)
        p.drawRoundedRect(rect, radius, radius)
        # Tail pointing right, toward the cat's cheek.
        tail_y = rect.top() + height * 0.62
        tail = QPainterPath()
        tail.moveTo(rect.right() - 1, tail_y - 5)
        tail.lineTo(rect.right() + 7, tail_y)
        tail.lineTo(rect.right() - 1, tail_y + 5)
        tail.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(249, 241, 227, 242))
        p.drawPath(tail)
        p.setPen(QPen(border, 1))
        p.drawLine(QPointF(rect.right() - 1, tail_y - 5), QPointF(rect.right() + 6.5, tail_y))
        p.drawLine(QPointF(rect.right() + 6.5, tail_y), QPointF(rect.right() - 1, tail_y + 5))
        p.setFont(font)
        p.setPen(QColor("#705443"))
        p.drawText(rect.adjusted(8, 5, -8, -5),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                   | Qt.TextFlag.TextWordWrap, display)

    # ---- hourglass countdown (right of the cat) ----

    def _countdown_layout(self):
        """Icon/text geometry for the side countdown, or None when idle."""
        if self.countdown_total <= 0:
            return None
        scale = min(206 * self._pet_size / 200, self.CAT_H * self._pet_size / 180)
        left = self._cat_x() + 164 * scale + 6 * self._pet_size
        right = self.width() - 4
        icon_h = max(14.0, 24.0 * self._pet_size)
        icon_w = icon_h * 14.0 / 22.0
        font = QFont(self.lyric_font, max(9, int(11 * self._pet_size)))
        fm = QFontMetrics(font)
        remaining = max(0, math.ceil(self.countdown_remaining))
        mm, ss = divmod(remaining, 60)
        label = f"{mm:02}:{ss:02}"
        text_w = fm.horizontalAdvance(label)
        cx = (left + right) / 2
        top = self._cat_top() + 52 * self._pet_size - (icon_h + 2 + fm.lineSpacing()) / 2
        icon_rect = QRectF(cx - icon_w / 2, top, icon_w, icon_h)
        text_rect = QRectF(cx - text_w / 2 - 3, top + icon_h + 2, text_w + 6, fm.lineSpacing() + 2)
        return icon_rect, text_rect, font, label

    def _countdown_hit_rect(self):
        layout = self._countdown_layout()
        if layout is None:
            return QRectF()
        icon_rect, text_rect = layout[0], layout[1]
        return icon_rect.united(text_rect).adjusted(-6, -4, 6, 4)

    def _draw_side_countdown(self, p, now):
        layout = self._countdown_layout()
        if layout is None:
            return
        icon_rect, text_rect, font, label = layout
        frac = 1.0 - max(0.0, min(float(self.countdown_total), self.countdown_remaining)) / self.countdown_total
        flip = 1.0
        if self.countdown_state == "running":
            # Flip end-over-end about once every eight seconds while running.
            phase = now % 8.0
            if phase < 1.1:
                flip = math.cos(2 * math.pi * (phase / 1.1))
                if abs(flip) < 0.05:
                    flip = 0.05 if flip >= 0 else -0.05
        p.save()
        if flip != 1.0:
            center = icon_rect.center()
            p.translate(center.x(), center.y())
            p.scale(1.0, flip)
            p.translate(-center.x(), -center.y())
        self._draw_hourglass(p, icon_rect.x(), icon_rect.y(), icon_rect.width(), icon_rect.height(),
                             frac, self.countdown_state, self.countdown_phase, now)
        p.restore()
        if self.countdown_state == "running":
            color = QColor("#2d6450") if self.countdown_phase == "focus" else QColor("#4e7385")
        else:
            color = QColor("#7d8678")
        p.setFont(font)
        halo = QColor(255, 255, 255, 110)
        p.setPen(halo)
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            p.drawText(text_rect.adjusted(dx, dy, dx, dy), Qt.AlignmentFlag.AlignCenter, label)
        p.setPen(color)
        p.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, label)

    def _draw_hourglass(self, p, x, y, w, h, frac, state, phase, now):
        paused = state in ("paused", "ready")
        phase_color = QColor("#4f8f6d") if phase == "focus" else QColor("#5f8fae")
        sand_color = QColor("#f0ad5b") if phase == "focus" else QColor("#94c4e0")
        wood_top = QColor("#f3c78f")
        wood_bottom = QColor("#c98a55")
        if paused:
            frame = QColor(phase_color.red(), phase_color.green(), phase_color.blue(), 150)
            sand = QColor(sand_color.red(), sand_color.green(), sand_color.blue(), 165)
            wood_top = QColor(wood_top.red(), wood_top.green(), wood_top.blue(), 170)
            wood_bottom = QColor(wood_bottom.red(), wood_bottom.green(), wood_bottom.blue(), 150)
        else:
            frame = phase_color
            sand = sand_color
        mid = y + h / 2
        cx = x + w / 2
        frac = max(0.0, min(1.0, frac))
        cap_h = max(2.0, h * 0.12)
        neck = max(1.1, w * 0.16)
        # Plump toy-like glass: two chubby bulbs joined by a soft waist.
        body = QPainterPath()
        body.moveTo(x + w * 0.10, y)
        body.cubicTo(x - w * 0.06, y + h * 0.17,
                     cx - neck, mid - h * 0.10, cx - neck, mid)
        body.cubicTo(cx - neck, mid + h * 0.10,
                     x - w * 0.06, y + h * 0.83, x + w * 0.10, y + h)
        body.lineTo(x + w * 0.90, y + h)
        body.cubicTo(x + w * 1.06, y + h * 0.83,
                     cx + neck, mid + h * 0.10, cx + neck, mid)
        body.cubicTo(cx + neck, mid - h * 0.10,
                     x + w * 1.06, y + h * 0.17, x + w * 0.90, y)
        body.closeSubpath()
        # Sand drains from the upper bulb...
        p.save()
        p.setClipPath(body)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(sand)
        surface = y + (mid - y) * frac
        p.drawRect(QRectF(x - 1, surface, w + 2, mid - surface))
        # ...and settles into a rounded mound at the bottom.
        fill = max(0.0, (y + h - mid) * frac)
        if fill > 0.4:
            top = y + h - fill
            p.drawEllipse(QRectF(x - w * 0.2, top - fill * 0.5, w * 1.4, fill))
            p.drawRect(QRectF(x - w * 0.2, top, w * 1.4, fill + 1))
        p.restore()
        # A wiggly stream of falling sand while running.
        if state == "running" and frac < 1.0:
            pile_top = y + h - fill
            if pile_top > mid + 1:
                alpha = 150 + int(60 * (0.5 + 0.5 * math.sin(now * 10)))
                p.setPen(QPen(QColor(sand.red(), sand.green(), sand.blue(), alpha),
                              max(1.0, w * 0.09), Qt.PenStyle.SolidLine,
                              Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                stream = QPainterPath()
                stream.moveTo(cx, mid - 0.5)
                for t in (0.35, 0.7, 1.0):
                    stream.lineTo(cx + math.sin(now * 6 + t * 7) * w * 0.06,
                                  mid + (pile_top - mid) * t)
                p.drawPath(stream)
        # Soft glass shine makes it read as a toy instead of a diagram.
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 70 if paused else 110))
        p.drawEllipse(QRectF(x + w * 0.15, y + h * 0.10, w * 0.20, h * 0.16))
        p.drawEllipse(QRectF(x + w * 0.12, y + h * 0.62, w * 0.10, h * 0.10))
        # Rounded glass outline.
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(frame, max(1.2, h * 0.055), Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawPath(body)
        # A tiny sleepy-happy face once the icon is large enough to show it.
        if h >= 18:
            ink = QColor(96, 62, 40, 150 if paused else 220)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(ink)
            eye = max(0.9, w * 0.05)
            for side in (-1, 1):
                p.drawEllipse(QRectF(cx + side * w * 0.18 - eye / 2,
                                     y + h * 0.25 - eye / 2, eye, eye))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(ink, max(0.8, w * 0.045), Qt.PenStyle.SolidLine,
                          Qt.PenCapStyle.RoundCap))
            p.drawArc(QRectF(cx - w * 0.14, y + h * 0.28, w * 0.28, h * 0.10),
                      200 * 16, 140 * 16)
        # Chunky wooden caps with a warm gradient.
        cap_w = w * 1.16
        cap_x = cx - cap_w / 2
        grad = QLinearGradient(0, y, 0, y + h)
        grad.setColorAt(0.0, wood_top)
        grad.setColorAt(1.0, wood_bottom)
        p.setPen(QPen(QColor(wood_bottom.red(), wood_bottom.green(), wood_bottom.blue(), 180), 0.8))
        p.setBrush(grad)
        p.drawRoundedRect(QRectF(cap_x, y - cap_h * 0.35, cap_w, cap_h), cap_h / 2, cap_h / 2)
        p.drawRoundedRect(QRectF(cap_x, y + h - cap_h * 0.65, cap_w, cap_h), cap_h / 2, cap_h / 2)

    # ---- interaction ----

    def enterEvent(self, event):
        self.hovered = True
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hovered = False
        self._hover_control = None
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position()
            if self.music_visible and self._lyric_rect().contains(pos):
                self._ui_press = pos
                self._pressed_control = self._control_at(pos)
                self.update()
                return
            if self._countdown_hit_rect().contains(pos):
                self._countdown_press = True
                self.update()
                return
            self.press_pos = event.globalPosition().toPoint()
            self.drag_start = self.pos()
            self.dragging = False
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif event.button() == Qt.MouseButton.RightButton:
            self.click_timer.stop()
            self.menu_requested.emit(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event):
        pos = event.position()
        if self._ui_press is None and self.press_pos is None:
            clickable = ((self.music_visible and self._lyric_rect().contains(pos))
                         or self._countdown_hit_rect().contains(pos))
            self.setCursor(Qt.CursorShape.PointingHandCursor if clickable
                           else Qt.CursorShape.OpenHandCursor)
        if self._ui_press is not None:
            pressed = self._control_at(pos)
            if pressed != self._pressed_control:
                self._pressed_control = pressed
                self.update()
            return
        hover = self._control_at(pos)
        if hover != self._hover_control:
            self._hover_control = hover
            self.update()
        if self.press_pos is not None:
            distance = event.globalPosition().toPoint() - self.press_pos
            if distance.manhattanLength() > QApplication.startDragDistance():
                self.dragging = True
            if self.dragging:
                self.move(self.drag_start + distance)
                self.x_float = float(self.x())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._countdown_press:
            if self._countdown_hit_rect().contains(event.position()):
                self.timer_toggle_requested.emit()
            self._countdown_press = False
            self.update()
            return
        if event.button() == Qt.MouseButton.LeftButton and self._ui_press is not None:
            pos = event.position()
            index = self._control_at(pos)
            if index is not None and index == self._pressed_control:
                self.media_requested.emit(CONTROL_ACTIONS[index])
                self.controls_hide_at = time.monotonic() + 6
            elif self.music_visible and self._lyric_rect().contains(pos):
                self.controls_visible = not self.controls_visible
                self._hover_control = None
                if self.controls_visible:
                    self.controls_hide_at = time.monotonic() + 6
            self._ui_press = None
            self._pressed_control = None
            self.update()
            return
        if event.button() == Qt.MouseButton.LeftButton and self.press_pos is not None:
            if self.dragging:
                self.clamp()
                self.moved.emit()
            else:
                self.click_timer.start(QApplication.doubleClickInterval())
            self.press_pos = None
            self.dragging = False
            self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.click_timer.stop()
            self.press_pos = None
            pos = event.position()
            if self.music_visible and self._lyric_rect().contains(pos):
                # Double-clicking the song strip folds it away; the menu can
                # bring it back.  Drop the press state from the second click.
                self._ui_press = None
                self._pressed_control = None
                self.lyric_close_requested.emit()
                return
            if self._countdown_hit_rect().contains(pos):
                self._countdown_press = False
                return
            self.panel_requested.emit()

    def closeEvent(self, event):
        # The tray and panel provide explicit Quit; accidentally closing the pet hides it.
        event.ignore()
        self.hide()
