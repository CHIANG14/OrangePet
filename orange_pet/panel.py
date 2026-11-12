from __future__ import annotations

import ctypes
import sys
from PySide6.QtCore import (
    QDate, QEasingCurve, Property, QPointF, QPropertyAnimation, QRectF, Qt, QTimer,
)
from PySide6.QtGui import (
    QColor, QFont, QKeySequence, QLinearGradient, QPainter, QPainterPath, QPen,
)
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDoubleSpinBox, QFrame, QGridLayout, QHBoxLayout,
    QInputDialog, QKeySequenceEdit, QLabel, QLineEdit, QPushButton, QScrollArea, QSlider,
    QSpinBox, QTabBar, QTabWidget, QVBoxLayout, QWidget,
)

from .art import app_icon, character_icon, draw_cat
from . import __version__
from .updates import bundled_repository
from .model import FONTS


def apply_acrylic(widget):
    """Enable Windows 11 Acrylic backdrop on a top-level widget. No-op on older systems."""
    if sys.platform != "win32":
        return
    try:
        hwnd = int(widget.winId())
        dwm = ctypes.WinDLL("dwmapi", use_last_error=True)
        # DWMWA_SYSTEMBACKDROP_TYPE = 38, DWMSBT_TRANSIENTWINDOW = 2 (Acrylic)
        DWMWA_SYSTEMBACKDROP_TYPE = 38
        DWMSBT_TRANSIENTWINDOW = 2
        # Must set window attribute DWMWA_USE_IMMERSIVE_DARK_MODE first is not needed,
        # but we need to set the backdrop type
        dwm.DwmSetWindowAttribute.restype = ctypes.HRESULT
        dwm.DwmSetWindowAttribute.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                              ctypes.POINTER(ctypes.c_int), ctypes.c_size_t]
        value = ctypes.c_int(DWMSBT_TRANSIENTWINDOW)
        result = dwm.DwmSetWindowAttribute(hwnd, DWMWA_SYSTEMBACKDROP_TYPE,
                                           ctypes.byref(value), ctypes.sizeof(value))
        # Also set the window to use rounded corners (DWMWA_WINDOW_CORNER_PREFERENCE = 33, DWMWCP_ROUND = 2)
        corner_pref = ctypes.c_int(2)
        dwm.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(corner_pref), ctypes.sizeof(corner_pref))
        # Enable Mica/Acrylic requires the window to have extended composition
        # Set DWMWA_CAPTION_COLOR = 35 to transparent-ish for blend
        if result == 0:  # S_OK
            widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
    except Exception:
        pass

STYLE = """
QWidget { color: #334a3f; font-family: 'Microsoft YaHei UI'; font-size: 13px; }
QWidget#panel { background: rgba(247, 245, 238, 210); }
QLabel { background: transparent; }
QLabel#title { font-size: 23px; font-weight: 700; color: #294f3e; }
QLabel#subtle { color: #8a8f7e; font-size: 11px; }
QLabel#eyebrow { color: #8a8f7e; font-size: 10px; letter-spacing: 2px; }
QLabel#section { font-size: 15px; font-weight: 600; }
QLabel#hint { color: #87907e; font-size: 12px; }
QLabel#stat { color: #397761; font-size: 23px; font-weight: 600; }
QLabel#currentLyric { color: #397761; font-size: 20px; font-weight: 600; }
QLabel#trackTitle { color: #354e40; font-size: 18px; font-weight: 600; }
QLabel#badge { color: #607c5c; background: rgba(231, 237, 220, 180); border-radius: 10px; padding: 5px 10px; font-size: 11px; }
QFrame#card { background: rgba(255, 253, 248, 200); border: 1px solid rgba(230, 229, 218, 180); border-radius: 18px; }
QTabWidget::pane { border: 0; background: transparent; }
QTabWidget::tab-bar { background: transparent; }
QTabBar { background: transparent; border: none; }
QTabBar::tab { background: transparent; border: none; min-width: 64px; padding: 14px 4px; }
QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; border: none; }
QScrollBar:vertical { background: transparent; width: 6px; }
QScrollBar::handle:vertical { background: rgba(213, 220, 203, 180); border-radius: 3px; min-height: 28px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QPushButton { background: transparent; border: none; border-radius: 11px; padding: 9px 14px; }
QPushButton#primary { font-weight: 600; font-size: 15px; padding: 13px; }
QPushButton#segment { padding: 8px; }
QPushButton#textButton { padding: 4px; }
QLineEdit, QSpinBox, QDoubleSpinBox, QKeySequenceEdit, QComboBox { background: rgba(255, 253, 248, 220); border: 1px solid rgba(223, 223, 211, 160); border-radius: 9px; padding: 9px; selection-background-color: #397761; }
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QKeySequenceEdit:focus { border-color: #397761; }
QCheckBox { spacing: 10px; padding: 7px 0; }
QCheckBox::indicator { width: 17px; height: 17px; border: 1px solid #b9c5ae; border-radius: 5px; background: rgba(255, 253, 248, 220); }
QCheckBox::indicator:checked { background: #397761; border: 3px solid #bdd4b2; }
QMenu { background: rgba(255, 253, 248, 230); border: 1px solid #d9dece; padding: 6px; }
QMenu::item { padding: 8px 22px; border-radius: 6px; }
QMenu::item:selected { background: rgba(230, 237, 220, 200); }
QToolTip { background: rgba(255, 253, 248, 230); color: #334a3f; border: 1px solid #d9dece; padding: 5px; }
"""


def label(text, name=None, wrap=False):
    item = QLabel(text)
    item.setTextFormat(Qt.TextFormat.PlainText)
    if name:
        item.setObjectName(name)
    item.setWordWrap(wrap)
    return item


def button(text, name=None):
    item = GlassButton(text)
    item.setCursor(Qt.CursorShape.PointingHandCursor)
    if name:
        item.setObjectName(name)
    return item


def card():
    item = QFrame()
    item.setObjectName("card")
    layout = QVBoxLayout(item)
    layout.setContentsMargins(18, 18, 18, 18)
    layout.setSpacing(12)
    return item, layout


class GlassButton(QPushButton):
    """QPushButton with a custom-painted glassmorphism effect.

    Draws a frosted-glass body with a bright top specular-highlight line,
    a strong upper light-reflection gradient, a deeper bottom inner shadow,
    a double border (inner luminous + outer edge), and a subtle outer glow.
    The variant (``primary``, ``segment``, ``textButton`` or plain) is chosen
    by the objectName set on the widget, matching the original QSS design.
    Font and padding still come from QSS so sizing stays consistent.
    """

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()
        rect = QRectF(0.5, 0.5, w - 1, h - 1)

        name = self.objectName() or ""
        is_text = name == "textButton"

        # ---- Text button: no glass, just centered text ----
        if is_text:
            if not self.isEnabled():
                p.setPen(QColor("#b9bcb0"))
            elif self.underMouse():
                p.setPen(QColor("#397761"))
            else:
                p.setPen(QColor("#8a907e"))
            p.setFont(self.font())
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.text())
            p.end()
            return

        is_primary = name == "primary"
        is_segment = name == "segment"
        enabled = self.isEnabled()
        checked = self.isChecked()
        hover = self.underMouse()
        pressed = self.isDown()
        radius = 12.0 if is_primary else (9.0 if is_segment else 11.0)

        # ---- Pick palette by variant + state ----
        if is_primary:
            if not enabled:
                fill_top = QColor(210, 214, 205, 120)
                fill_bot = QColor(195, 200, 190, 80)
                border = QColor(200, 205, 195, 60)
                text_color = QColor(185, 188, 176)
            else:
                r, g, b = (38, 92, 74) if pressed else (57, 119, 97)
                fill_top = QColor(r + 18, g + 18, b + 18, 235)
                fill_bot = QColor(r, g, b, 210)
                border = QColor(255, 255, 255, 70)
                text_color = QColor(255, 255, 255)
        elif is_segment:
            if checked:
                fill_top = QColor(228, 240, 218, 210)
                fill_bot = QColor(205, 225, 200, 160)
                border = QColor(255, 255, 255, 80)
                text_color = QColor(45, 100, 80)
            elif not enabled:
                fill_top, fill_bot = QColor(235, 238, 228, 50), QColor(230, 235, 220, 25)
                border = QColor(220, 225, 210, 30)
                text_color = QColor(185, 188, 176)
            else:
                if hover:
                    fill_top = QColor(250, 253, 248, 140)
                    fill_bot = QColor(238, 245, 235, 70)
                    border = QColor(255, 255, 255, 60)
                else:
                    fill_top = QColor(248, 252, 250, 60)
                    fill_bot = QColor(235, 242, 238, 25)
                    border = QColor(255, 255, 255, 30)
                text_color = QColor(120, 130, 115)
        else:
            # Normal button — frosted cool-white glass
            if not enabled:
                fill_top, fill_bot = QColor(235, 238, 232, 70), QColor(225, 230, 222, 35)
                border = QColor(210, 215, 205, 40)
                text_color = QColor(185, 188, 176)
            elif pressed:
                fill_top = QColor(215, 228, 218, 190)
                fill_bot = QColor(195, 215, 205, 130)
                border = QColor(150, 175, 155, 120)
                text_color = QColor(51, 74, 63)
            elif hover:
                fill_top = QColor(248, 253, 252, 200)
                fill_bot = QColor(228, 242, 238, 110)
                border = QColor(170, 200, 180, 100)
                text_color = QColor(51, 74, 63)
            else:
                fill_top = QColor(250, 253, 252, 170)
                fill_bot = QColor(232, 242, 240, 80)
                border = QColor(200, 215, 210, 90)
                text_color = QColor(51, 74, 63)

        clip = QPainterPath()
        clip.addRoundedRect(rect, radius, radius)

        # 0. Outer glow — soft halo around the button (skip for segment)
        if enabled and not is_segment and not pressed:
            glow_alpha = 40 if hover else 22
            glow_color = QColor(120, 180, 160, glow_alpha) if not is_primary else QColor(80, 160, 130, glow_alpha)
            for i in range(3):
                inset = 1.5 + i * 1.5
                alpha = glow_alpha - i * 12
                if alpha <= 0:
                    break
                p.setPen(QPen(QColor(glow_color.red(), glow_color.green(), glow_color.blue(), alpha), 1.5))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(rect.adjusted(-inset, -inset, inset, inset), radius + inset, radius + inset)

        # 1. Glass body — frosted gradient (cool-white top → tinted bottom)
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0.0, fill_top)
        grad.setColorAt(0.5, QColor(
            (fill_top.red() + fill_bot.red()) // 2,
            (fill_top.green() + fill_bot.green()) // 2,
            (fill_top.blue() + fill_bot.blue()) // 2,
            (fill_top.alpha() + fill_bot.alpha()) // 2,
        ))
        grad.setColorAt(1.0, fill_bot)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        p.drawRoundedRect(rect, radius, radius)

        p.save()
        p.setClipPath(clip)

        # 2. Top specular highlight — bright line at the very top edge
        if enabled:
            spec_alpha = 130 if is_primary else (120 if is_segment and checked else 90)
            spec_grad = QLinearGradient(0, 0, 0, h * 0.12)
            spec_grad.setColorAt(0.0, QColor(255, 255, 255, spec_alpha))
            spec_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.setBrush(spec_grad)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(QRectF(0, 0, w, h * 0.5), radius, radius)

        # 3. Top light-reflection — broader glow on upper half
        if enabled:
            ref_alpha = 60 if is_primary else (50 if is_segment and not checked else 45)
            ref_grad = QLinearGradient(0, 0, 0, h * 0.6)
            ref_grad.setColorAt(0.0, QColor(255, 255, 255, ref_alpha))
            ref_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.setBrush(ref_grad)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRect(QRectF(0, 0, w, h * 0.6))

        # 4. Bottom inner shadow — deeper for glass depth
        if enabled:
            sh_alpha = 55 if is_primary else 40
            sh_grad = QLinearGradient(0, h - 10, 0, h)
            sh_grad.setColorAt(0.0, QColor(0, 0, 0, 0))
            sh_grad.setColorAt(1.0, QColor(0, 0, 0, sh_alpha))
            p.setBrush(sh_grad)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRect(QRectF(0, h - 10, w, 10))

        p.restore()

        # 5. Inner luminous border — bright top half, darker bottom half
        if enabled:
            border_grad = QLinearGradient(0, 0, 0, h)
            border_grad.setColorAt(0.0, QColor(255, 255, 255, 120))
            border_grad.setColorAt(0.5, QColor(255, 255, 255, 40))
            border_grad.setColorAt(1.0, QColor(255, 255, 255, 10))
            p.setPen(QPen(border_grad, 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect, radius, radius)

        # 6. Outer edge border
        if border.alpha() > 0:
            p.setPen(QPen(border, 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect.adjusted(-0.5, -0.5, 0.5, 0.5), radius, radius)

        # 7. Focus indicator
        if self.hasFocus() and enabled:
            focus_pen = QPen(QColor(57, 119, 97, 120), 2)
            p.setPen(focus_pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect.adjusted(1, 1, -1, -1), radius - 1, radius - 1)

        # 8. Text
        p.setPen(text_color)
        p.setFont(self.font())
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.text())
        p.end()


class GlassTabBar(QTabBar):
    """Bottom navigation bar with frosted-glass background and a sliding indicator.

    The indicator smoothly animates between tabs when the selection changes,
    driven by a ``QPropertyAnimation`` on a 0→1 ``progress`` property with an
    ``OutCubic`` easing curve (~280 ms).  All visual styling is done in
    ``paintEvent``; QSS only controls sizing (min-width, padding).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._progress = 1.0
        self._from_rect = QRectF()
        self._to_rect = QRectF()
        self._anim = None
        self.currentChanged.connect(self._on_current_changed)

    # ---- animated property: progress 0→1 ----
    def _get_progress(self):
        return self._progress

    def _set_progress(self, v):
        self._progress = v
        self.update()

    progress = Property(float, _get_progress, _set_progress)

    def _on_current_changed(self, index):
        new_rect = QRectF(self.tabRect(index))
        if new_rect.width() <= 0:
            return
        if self._anim is not None:
            self._anim.stop()
        if self._to_rect.width() <= 0:
            self._from_rect = new_rect
            self._to_rect = new_rect
            self._progress = 1.0
            self.update()
            return
        self._from_rect = self._to_rect
        self._to_rect = new_rect
        self._progress = 0.0
        self._anim = QPropertyAnimation(self, b'progress')
        self._anim.setDuration(280)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        idx = self.currentIndex()
        if idx >= 0:
            r = QRectF(self.tabRect(idx))
            if r.width() > 0:
                self._from_rect = r
                self._to_rect = r
                self._progress = 1.0

    def _indicator_rect(self):
        idx = self.currentIndex()
        if idx < 0:
            return QRectF()
        if self._to_rect.width() <= 0:
            return QRectF(self.tabRect(idx))
        p = self._progress
        return QRectF(
            self._from_rect.x() + (self._to_rect.x() - self._from_rect.x()) * p,
            3,
            self._from_rect.width() + (self._to_rect.width() - self._from_rect.width()) * p,
            self.height() - 6,
        )

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0:
            p.end()
            return
        rect = QRectF(0, 0, w, h)

        # 1. Frosted-glass background for the whole bar
        bg = QLinearGradient(0, 0, 0, h)
        bg.setColorAt(0.0, QColor(255, 253, 248, 170))
        bg.setColorAt(1.0, QColor(236, 243, 235, 110))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg)
        p.drawRect(rect)

        # Top specular highlight on the bar
        spec = QLinearGradient(0, 0, 0, h * 0.2)
        spec.setColorAt(0.0, QColor(255, 255, 255, 80))
        spec.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setBrush(spec)
        p.drawRect(QRectF(0, 0, w, h * 0.5))

        # Subtle top border line separating bar from content
        p.setPen(QPen(QColor(200, 210, 200, 70), 1))
        p.drawLine(QRectF(0, 0, w, 0).topLeft(), QRectF(w, 0, 0, 0).topLeft())

        # 2. Sliding glass indicator
        ind = self._indicator_rect()
        if ind.width() > 0 and ind.height() > 0:
            clip = QPainterPath()
            clip.addRoundedRect(ind, 10, 10)
            p.save()
            p.setClipPath(clip)

            ind_grad = QLinearGradient(0, ind.y(), 0, ind.y() + ind.height())
            ind_grad.setColorAt(0.0, QColor(220, 238, 225, 200))
            ind_grad.setColorAt(1.0, QColor(198, 223, 208, 130))
            p.setBrush(ind_grad)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRect(ind)

            ind_spec = QLinearGradient(0, ind.y(), 0, ind.y() + ind.height() * 0.3)
            ind_spec.setColorAt(0.0, QColor(255, 255, 255, 130))
            ind_spec.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.setBrush(ind_spec)
            p.drawRect(QRectF(ind.x(), ind.y(), ind.width(), ind.height() * 0.5))
            p.restore()

            # Indicator luminous border
            p.setPen(QPen(QColor(255, 255, 255, 90), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(ind, 10, 10)

        # 3. Tab labels
        idx = self.currentIndex()
        for i in range(self.count()):
            tab_rect = QRectF(self.tabRect(i))
            is_selected = i == idx
            if is_selected:
                p.setPen(QColor(45, 100, 80))
                f = QFont(self.font())
                f.setWeight(QFont.Weight.Bold)
                p.setFont(f)
            else:
                p.setPen(QColor(139, 147, 130))
                p.setFont(self.font())
            p.drawText(tab_rect, Qt.AlignmentFlag.AlignCenter, self.tabText(i))

        p.end()


class Avatar(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(65, 62)

    def paintEvent(self, event):
        p = QPainter(self)
        draw_cat(p, QRectF(-2, -5, 70, 67), 1)
        p.end()


class TimerDial(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(230)
        self.seconds = 1500
        self.progress = 0
        self.caption = "留一段时间，只做一件事"

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = QRectF(self.width() / 2 - 104, 8, 208, 208)
        p.setPen(QPen(QColor("#e8ecdf"), 7))
        p.drawEllipse(box)
        p.setPen(QPen(QColor("#76a38a"), 7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        if self.progress:
            p.drawArc(box, 90 * 16, -round(360 * 16 * self.progress))
        p.setPen(QColor("#345b48"))
        p.setFont(QFont("Segoe UI", 42, QFont.Weight.Light))
        p.drawText(QRectF(0, 64, self.width(), 78), Qt.AlignmentFlag.AlignCenter,
                   f"{self.seconds // 60:02}:{self.seconds % 60:02}")
        p.setFont(QFont("Microsoft YaHei UI", 9))
        p.setPen(QColor("#909681"))
        p.drawText(QRectF(0, 145, self.width(), 28), Qt.AlignmentFlag.AlignCenter, self.caption)
        p.end()


class Panel(QWidget):
    def __init__(self, controller):
        super().__init__()
        self.c = controller
        self.setObjectName("panel")
        self.setWindowTitle("橘子专注 · 桌面宠物与番茄钟")
        self.setWindowIcon(app_icon())
        self.setMinimumSize(430, 520)
        self.resize(460, min(780, self.screen().availableGeometry().height() - 70))
        # Enable Acrylic glass effect (Windows 11; no-op on older systems)
        self.apply_glass()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 20, 22, 12)
        outer.setSpacing(12)
        header = QHBoxLayout()
        header.addWidget(Avatar())
        title = QVBoxLayout()
        title.setSpacing(3)
        title.addWidget(label("橘子专注", "title"))
        title.addWidget(label("A LITTLE COMPANY, A LITTLE FOCUS", "eyebrow"))
        header.addLayout(title)
        header.addStretch()
        outer.addLayout(header)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tab_bar = GlassTabBar()
        self.tabs.setTabBar(self.tab_bar)
        self.tabs.setTabPosition(QTabWidget.TabPosition.South)
        outer.addWidget(self.tabs, 1)
        self.focus_page()
        self.music_page()
        self.task_page()
        self.care_page()
        self.settings_page()
        footer = QHBoxLayout()
        self.footer = label("单击摸摸 · 双击面板 · 拖动换位置", "subtle")
        footer.addWidget(self.footer)
        footer.addStretch()
        quit_button = button("退出", "textButton")
        quit_button.clicked.connect(controller.quit)
        footer.addWidget(quit_button)
        outer.addLayout(footer)

    def apply_glass(self):
        """Apply Acrylic glass effect after the window has a native handle."""
        # Defer until winId is available
        QTimer.singleShot(0, lambda: apply_acrylic(self))

    def page(self, title):
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 16, 4, 4)
        layout.setSpacing(14)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tabs.addTab(scroll, title)
        return layout

    def focus_page(self):
        layout = self.page("专注时光")
        top = QHBoxLayout()
        top.addWidget(label("今天，慢慢做好一件事。", "section"))
        top.addStretch()
        self.cycle_label = label("第 1 / 4 轮", "badge")
        top.addWidget(self.cycle_label)
        layout.addLayout(top)
        frame, box = card()
        segments = QHBoxLayout()
        self.phase_buttons = {}
        for key, text in (("focus", "专注"), ("short", "短休息"), ("long", "长休息")):
            item = button(text, "segment")
            item.setCheckable(True)
            item.clicked.connect(lambda checked=False, phase=key: self.c.switch_phase(phase))
            self.phase_buttons[key] = item
            segments.addWidget(item)
        box.addLayout(segments)
        preset_row = QHBoxLayout()
        preset_row.addWidget(label("专注时长", "hint"))
        preset_holder = QWidget()
        self.preset_grid = QGridLayout(preset_holder)
        self.preset_grid.setContentsMargins(0, 0, 0, 0)
        self.preset_grid.setHorizontalSpacing(6)
        self.preset_grid.setVerticalSpacing(6)
        preset_row.addWidget(preset_holder, 1)
        box.addLayout(preset_row)
        self.preset_chips = {}
        self.rebuild_focus_presets()
        self.dial = TimerDial()
        box.addWidget(self.dial)
        self.task = QLineEdit(self.c.store.settings.task)
        self.task.setMaxLength(120)
        self.task.setPlaceholderText("这一轮，想完成什么？")
        self.task.setAccessibleName("本轮专注任务")
        self.task.editingFinished.connect(self.c.save_task)
        box.addWidget(self.task)
        self.task_choice = QComboBox()
        self.task_choice.setAccessibleName("下一轮关联任务")
        self.task_choice.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.task_choice.currentIndexChanged.connect(self.c.select_task)
        self.refresh_task_choices()
        box.addWidget(self.task_choice)
        actions = QHBoxLayout()
        self.start = button("开始专注", "primary")
        self.start.clicked.connect(self.c.toggle_timer)
        actions.addWidget(self.start, 3)
        self.reset = button("重置")
        self.reset.clicked.connect(self.c.reset_timer)
        actions.addWidget(self.reset, 1)
        box.addLayout(actions)
        self.focus_hint = label("完成 1 轮专注，为橘子赚 1 份小鱼干。", "hint", True)
        self.focus_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(self.focus_hint)
        layout.addWidget(frame)
        stats = QHBoxLayout()
        self.stat_labels = []
        for caption in ("今日番茄", "专注分钟", "休息分钟", "小鱼干"):
            block, block_layout = card()
            block_layout.setContentsMargins(10, 12, 10, 12)
            number = label("0", "stat")
            number.setAlignment(Qt.AlignmentFlag.AlignCenter)
            text = label(caption, "hint")
            text.setAlignment(Qt.AlignmentFlag.AlignCenter)
            block_layout.addWidget(number)
            block_layout.addWidget(text)
            stats.addWidget(block)
            self.stat_labels.append(number)
        layout.addLayout(stats)
        row = QHBoxLayout()
        feed = button("喂橘子一条小鱼干")
        feed.clicked.connect(self.c.feed)
        row.addWidget(feed)
        locate = button("叫小猫回来")
        locate.clicked.connect(self.c.locate_pet)
        row.addWidget(locate)
        layout.addLayout(row)
        # Star bottle card
        frame, box = card()
        box.addWidget(label("星愿瓶", "section"))
        self.bottle = StarBottle()
        box.addWidget(self.bottle)
        bottle_stats = QHBoxLayout()
        self.bottle_period = QComboBox()
        self.bottle_period.addItem("今天", "day")
        self.bottle_period.addItem("本周", "week")
        self.bottle_period.addItem("本月", "month")
        self.bottle_period.currentIndexChanged.connect(self.c.refresh_bottle)
        bottle_stats.addWidget(label("统计周期"))
        bottle_stats.addWidget(self.bottle_period)
        self.bottle_stats = label("还没有星星，完成专注来收集吧。", "hint", True)
        bottle_stats.addWidget(self.bottle_stats)
        box.addLayout(bottle_stats)
        layout.addWidget(frame)
        layout.addStretch()

    def rebuild_focus_presets(self):
        """Rebuild the focus-duration chips from the saved presets."""
        grid = getattr(self, "preset_grid", None)
        if grid is None:
            return
        while grid.count():
            item = grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.preset_chips = {}
        presets = list(self.c.store.settings.focus_presets)
        for index, minutes in enumerate(presets):
            text = f"{minutes // 60} 小时" if minutes >= 60 and minutes % 60 == 0 else f"{minutes} 分"
            chip = button(text, "segment")
            chip.setCheckable(True)
            chip.setAccessibleName(f"专注 {minutes} 分钟")
            chip.clicked.connect(lambda checked=False, m=minutes: self.c.change_duration("focus", m))
            grid.addWidget(chip, index // 4, index % 4)
            self.preset_chips[minutes] = chip
        add = button("自定义…", "segment")
        add.clicked.connect(self.add_focus_preset)
        position = len(presets)
        grid.addWidget(add, position // 4, position % 4)
        self.refresh_preset_checks()

    def refresh_preset_checks(self):
        focus = self.c.store.settings.focus
        for minutes, chip in getattr(self, "preset_chips", {}).items():
            chip.setChecked(focus == minutes)

    def add_focus_preset(self):
        current = max(1, min(180, self.c.store.settings.focus))
        value, ok = QInputDialog.getInt(self, "自定义专注时长", "分钟数（1–180）：", current, 1, 180)
        if ok:
            self.c.add_focus_preset(value)

    def music_page(self):
        layout = self.page("一起听歌")
        title_row = QHBoxLayout()
        title_row.addWidget(label("你的音乐，橘子来唱。", "section"))
        title_row.addStretch()
        title_row.addWidget(label("Apple Music 优先", "badge"))
        layout.addLayout(title_row)
        frame, box = card()
        self.track_title = label("等待 Apple Music", "trackTitle", True)
        self.track_artist = label("在播放器中播放一首歌，橘子会自动连接。", "hint", True)
        box.addWidget(self.track_title)
        box.addWidget(self.track_artist)
        self.playback_status = label("尚未连接", "subtle", True)
        box.addWidget(self.playback_status)
        self.lyric_current = label("让音乐陪你一会儿", "currentLyric", True)
        self.lyric_current.setMinimumHeight(78)
        self.lyric_current.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lyric_next = label("逐句歌词会显示在小猫头顶", "hint", True)
        self.lyric_next.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lyric_next.setMinimumHeight(35)
        box.addWidget(self.lyric_current)
        box.addWidget(self.lyric_next)
        self.music_time = label("00:00 / 00:00", "subtle")
        self.music_time.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(self.music_time)
        controls = QHBoxLayout()
        self.previous = button("上一曲")
        self.play = button("播放", "primary")
        self.next = button("下一曲")
        for item, action in ((self.previous, "previous"), (self.play, "toggle"), (self.next, "next")):
            item.clicked.connect(lambda checked=False, act=action: self.c.media_command(act))
            item.setEnabled(False)
            controls.addWidget(item)
        box.addLayout(controls)
        layout.addWidget(frame)
        self.lyric_source = label("歌词支持自动查询或导入本地 LRC。", "hint", True)
        layout.addWidget(self.lyric_source)
        row = QHBoxLayout()
        self.import_button = button("导入 LRC")
        self.import_button.clicked.connect(self.c.import_lyrics)
        row.addWidget(self.import_button)
        retry = button("重试歌词")
        retry.clicked.connect(self.c.retry_lyrics)
        row.addWidget(retry)
        self.demo_button = button("跟唱演示")
        self.demo_button.clicked.connect(self.c.toggle_demo)
        row.addWidget(self.demo_button)
        layout.addLayout(row)
        offset_row = QHBoxLayout()
        offset_row.addWidget(label("歌词时间微调", "hint"))
        self.offset = QDoubleSpinBox()
        self.offset.setRange(-60, 60)
        self.offset.setDecimals(1)
        self.offset.setSingleStep(0.5)
        self.offset.setSuffix(" 秒")
        self.offset.setValue(self.c.store.settings.lyric_offset)
        self.offset.valueChanged.connect(self.c.change_offset)
        self.offset.setAccessibleName("歌词时间偏移，正数提前")
        offset_row.addWidget(self.offset)
        layout.addLayout(offset_row)
        layout.addWidget(label("正数让歌词提前，负数让歌词延后。", "subtle"))
        # Font selector
        font_row = QHBoxLayout()
        font_row.addWidget(label("歌词字体", "hint"))
        self.font_select = QComboBox()
        for family, name in FONTS.items():
            self.font_select.addItem(name, family)
        current_idx = self.font_select.findData(self.c.store.settings.lyric_font)
        if current_idx >= 0:
            self.font_select.setCurrentIndex(current_idx)
        self.font_select.currentIndexChanged.connect(self.c.change_font)
        font_row.addWidget(self.font_select)
        layout.addLayout(font_row)
        # Lyric mode toggle
        mode_row = QHBoxLayout()
        mode_row.addWidget(label("歌词显示模式", "hint"))
        self.mode_select = QComboBox()
        self.mode_select.addItem("逐句高亮", "line")
        self.mode_select.addItem("逐字跳动", "word")
        mode_idx = 0 if self.c.store.settings.lyric_mode == "line" else 1
        self.mode_select.setCurrentIndex(mode_idx)
        self.mode_select.currentIndexChanged.connect(self.c.change_lyric_mode)
        mode_row.addWidget(self.mode_select)
        layout.addLayout(mode_row)
        layout.addWidget(label("逐字跳动按行时长估算每个字的显示时间，无逐字标签时为近似效果。", "subtle", True))
        self.music_enabled = QCheckBox("开启音乐联动与小猫跟唱")
        self.music_enabled.setChecked(self.c.store.settings.music)
        self.music_enabled.toggled.connect(self.c.change_music)
        layout.addWidget(self.music_enabled)
        self.online = QCheckBox("自动查找逐句歌词（LRCLIB）")
        self.online.setChecked(self.c.store.settings.online_lyrics)
        self.online.toggled.connect(self.c.change_online)
        layout.addWidget(self.online)
        layout.addWidget(label("自动查询会发送歌名、歌手和专辑到 LRCLIB，可关闭后只用本地 LRC。演示只有动画，不播放声音。", "subtle", True))
        layout.addStretch()

    def care_page(self):
        layout = self.page("日常陪伴")
        self.local_clock = label("当地时间", "section", True)
        layout.addWidget(self.local_clock)
        frame, box = card()
        box.addWidget(label("窗外的天气", "section"))
        self.weather_title = label("北京 · 正在看看窗外…", "trackTitle", True)
        self.weather_detail = label("正在查询天气", "hint", True)
        self.weather_tip = label("出门前，记得看看天气。", "hint", True)
        self.weather_update = label("天气数据：Open-Meteo", "subtle", True)
        for item in (self.weather_title, self.weather_detail, self.weather_tip, self.weather_update):
            box.addWidget(item)
        row = QHBoxLayout()
        self.city_input = QLineEdit(self.c.store.settings.city)
        self.city_input.setPlaceholderText("城市名，如 北京 / Beijing")
        self.city_input.setAccessibleName("天气城市搜索")
        row.addWidget(self.city_input, 1)
        search = button("搜索城市")
        search.clicked.connect(self.c.search_city)
        self.city_input.returnPressed.connect(self.c.search_city)
        row.addWidget(search)
        box.addLayout(row)
        row = QHBoxLayout()
        self.city_results = QComboBox()
        self.city_results.setMinimumWidth(100)
        self.city_results.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.city_results.setAccessibleName("搜索到的城市")
        row.addWidget(self.city_results, 1)
        use_city = button("使用城市")
        use_city.clicked.connect(self.c.use_city)
        row.addWidget(use_city)
        box.addLayout(row)
        self.city_status = label("可以搜索同名城市，按省份和国家选择。", "subtle", True)
        box.addWidget(self.city_status)
        self.weather_enabled = QCheckBox("开启天气（每 30 分钟自动更新）")
        self.weather_enabled.setChecked(self.c.store.settings.weather)
        self.weather_enabled.toggled.connect(self.c.change_weather)
        box.addWidget(self.weather_enabled)
        refresh = button("现在更新天气")
        refresh.clicked.connect(self.c.refresh_weather)
        box.addWidget(refresh)
        source = QLabel('<a href="https://open-meteo.com/">天气：Open-Meteo · CC BY 4.0</a>')
        source.setOpenExternalLinks(True)
        source.setObjectName("subtle")
        box.addWidget(source)
        layout.addWidget(frame)
        frame, box = card()
        box.addWidget(label("不催你，只陪你", "section"))
        self.greeting_preview = label("橘子准备好今天的悄悄话了。", "hint", True)
        self.greeting_preview.setMinimumHeight(44)
        box.addWidget(self.greeting_preview)
        another = button("让橘子说一句")
        another.clicked.connect(self.c.say_something)
        box.addWidget(another)
        self.greetings_enabled = QCheckBox("按当地时间提醒问候、吃饭和休息")
        self.greetings_enabled.setChecked(self.c.store.settings.greetings)
        self.greetings_enabled.toggled.connect(self.c.change_greetings)
        box.addWidget(self.greetings_enabled)
        self.quotes_enabled = QCheckBox("偶尔分享一句温柔的鼓励")
        self.quotes_enabled.setChecked(self.c.store.settings.quotes)
        self.quotes_enabled.toggled.connect(self.c.change_quotes)
        box.addWidget(self.quotes_enabled)
        row = QHBoxLayout()
        row.addWidget(label("日常提示间隔"))
        self.reminder_interval = QSpinBox()
        self.reminder_interval.setRange(15, 180)
        self.reminder_interval.setSuffix(" 分钟")
        self.reminder_interval.setValue(self.c.store.settings.reminder_minutes)
        self.reminder_interval.valueChanged.connect(self.c.change_reminder_interval)
        row.addWidget(self.reminder_interval)
        box.addLayout(row)
        box.addWidget(label("使用电脑本地时区。进入新时段会问候一次；专注、播放音乐或隐藏小猫时暂缓主动提示。内置 98 条短句。", "subtle", True))
        layout.addWidget(frame)
        # Performance monitoring card
        frame, box = card()
        box.addWidget(label("电脑状态", "section"))
        self.perf_enabled = QCheckBox("显示 CPU、显卡、内存、磁盘和网速")
        self.perf_enabled.setChecked(self.c.store.settings.performance)
        self.perf_enabled.toggled.connect(self.c.change_performance)
        box.addWidget(self.perf_enabled)
        self.perf_widget = PerfWidget()
        box.addWidget(self.perf_widget)
        self.sensor_status = label("打开温度组件后，卡片会自动读取可用传感器。", "hint", True)
        box.addWidget(self.sensor_status)
        sensor_button = button("打开内置温度组件")
        sensor_button.clicked.connect(self.c.open_temperature_helper)
        box.addWidget(sensor_button)
        box.addWidget(label("温度需安装 LibreHardwareMonitor 或以管理员运行，否则只显示内存/磁盘/网速。", "subtle", True))
        layout.addWidget(frame)
        layout.addStretch()

    def task_page(self):
        layout = self.page("任务计划")
        layout.addWidget(label("今日待办与专注分布", "section"))
        # New task form
        frame, box = card()
        box.addWidget(label("新建任务", "section"))
        self.task_name = QLineEdit()
        self.task_name.setPlaceholderText("任务名称，如：复习最优化理论")
        self.task_name.setMaxLength(120)
        box.addWidget(self.task_name)
        form = QHBoxLayout()
        form.addWidget(label("分类", "hint"))
        self.task_category = QLineEdit()
        self.task_category.setPlaceholderText("如：学习 / 工作 / 阅读")
        self.task_category.setMaxLength(40)
        form.addWidget(self.task_category)
        form.addWidget(label("截止日期", "hint"))
        self.task_deadline = QDateEdit()
        self.task_deadline.setDate(QDate.currentDate())
        self.task_deadline.setCalendarPopup(True)
        self.task_deadline.setDisplayFormat("yyyy-MM-dd")
        self.task_deadline.setSpecialValueText("无")
        self.task_deadline.setMinimumDate(QDate.currentDate().addDays(-1))
        self.task_deadline.setDate(self.task_deadline.minimumDate())
        form.addWidget(self.task_deadline)
        box.addLayout(form)
        add_btn = button("添加任务")
        add_btn.clicked.connect(self.c.add_task)
        box.addWidget(add_btn)
        layout.addWidget(frame)
        # Task list
        frame, box = card()
        box.addWidget(label("任务列表", "section"))
        self.task_list = QVBoxLayout()
        box.addLayout(self.task_list)
        self.no_tasks = label("还没有任务，新建一个开始专注吧。", "hint", True)
        box.addWidget(self.no_tasks)
        layout.addWidget(frame)
        # Pie chart
        frame, box = card()
        box.addWidget(label("专注时长分布", "section"))
        self.pie = PieChart()
        box.addWidget(self.pie)
        layout.addWidget(frame)
        layout.addStretch()

    def settings_page(self):
        layout = self.page("小猫设置")
        frame, box = card()
        box.addWidget(label(f"版本与更新 · v{__version__}", "section"))
        self.update_repo = QLineEdit(self.c.store.settings.update_repository or bundled_repository())
        self.update_repo.setMaxLength(160)
        self.update_repo.setPlaceholderText("GitHub 仓库，例如 owner/OrangePet")
        self.update_repo.setAccessibleName("更新仓库")
        box.addWidget(self.update_repo)
        self.check_update = button("检查更新")
        self.check_update.clicked.connect(self.c.updates.check)
        box.addWidget(self.check_update)
        self.update_status = label("从 GitHub Releases 检查正式版本。", "hint", True)
        box.addWidget(self.update_status)
        layout.addWidget(frame)
        frame, box = card()
        box.addWidget(label("找到自己的节奏", "section"))
        self.durations = {}
        for key, title in (("focus", "专注时长"), ("short", "短休息"), ("long", "长休息")):
            row = QHBoxLayout()
            row.addWidget(label(title))
            row.addStretch()
            spin = QSpinBox()
            spin.setRange(1, 180)
            spin.setSuffix(" 分钟")
            spin.setValue(getattr(self.c.store.settings, key))
            spin.setAccessibleName(title)
            spin.valueChanged.connect(lambda value, k=key: self.c.change_duration(k, value))
            self.durations[key] = spin
            row.addWidget(spin)
            box.addLayout(row)
        box.addWidget(label("每完成 4 轮专注进入长休息；下一轮由你开始。修改时长从下一轮或重置后生效。", "subtle", True))
        # Pet size slider
        size_row = QHBoxLayout()
        size_row.addWidget(label("小猫大小"))
        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setRange(50, 200)
        self.size_slider.setValue(int(self.c.store.settings.pet_size * 100))
        self.size_slider.setSingleStep(10)
        self.size_slider.valueChanged.connect(self.c.change_pet_size)
        size_row.addWidget(self.size_slider)
        self.size_label = label(f"{self.c.store.settings.pet_size:.1f}x", "hint")
        self.size_label.setFixedWidth(36)
        size_row.addWidget(self.size_label)
        box.addLayout(size_row)
        # Character selector
        from .characters import CHARACTERS
        char_row = QHBoxLayout()
        char_row.addWidget(label("卡通形象"))
        self.char_select = QComboBox()
        for key, (name, _) in CHARACTERS.items():
            self.char_select.addItem(character_icon(key, 64), name, key)
        idx = self.char_select.findData(self.c.store.settings.character)
        if idx >= 0:
            self.char_select.setCurrentIndex(idx)
        self.char_select.currentIndexChanged.connect(
            lambda i: self.c.change_character(self.char_select.itemData(i)))
        char_row.addWidget(self.char_select)
        box.addLayout(char_row)
        self.walk = QCheckBox("允许小猫自动走动（独立于专注和听歌，随时生效）")
        self.walk.setChecked(self.c.store.settings.walking)
        self.walk.toggled.connect(self.c.change_walking)
        box.addWidget(self.walk)
        self.sound = QCheckBox("番茄钟结束时播放提示音")
        self.sound.setChecked(self.c.store.settings.sound)
        self.sound.toggled.connect(self.c.change_sound)
        box.addWidget(self.sound)
        layout.addWidget(frame)
        frame, box = card()
        box.addWidget(label("随时叫它出来", "section"))
        self.key_edits = {}
        for key, text in (("pet_hotkey", "显示 / 隐藏小猫"), ("panel_hotkey", "显示 / 隐藏面板")):
            box.addWidget(label(text, "hint"))
            edit = QKeySequenceEdit(QKeySequence(getattr(self.c.store.settings, key)))
            edit.setMaximumSequenceLength(1)
            edit.setAccessibleName(text + "快捷键")
            self.key_edits[key] = edit
            box.addWidget(edit)
        apply_keys = button("保存快捷键")
        apply_keys.clicked.connect(self.c.save_hotkeys)
        box.addWidget(apply_keys)
        self.hotkey_status = label("点击输入框，按下你的组合键。", "subtle", True)
        box.addWidget(self.hotkey_status)
        layout.addWidget(frame)
        layout.addWidget(label("关闭面板后，小猫和计时仍会继续。右键小猫或托盘图标可退出程序。", "subtle", True))
        layout.addStretch()

    def refresh_timer(self):
        model = self.c.timer
        self.refresh_preset_checks()
        self.dial.seconds = model.seconds
        self.dial.progress = model.progress
        self.dial.caption = {"ready": "准备好了，就开始吧", "running": "橘子正在陪你", "paused": "歇一会儿，随时继续"}[model.state]
        self.dial.update()
        self.start.setText("暂停" if model.state == "running" else "继续" if model.state == "paused"
                           else "开始专注" if model.phase == "focus" else "开始休息")
        for key, item in self.phase_buttons.items():
            item.setChecked(model.phase == key)
            item.setEnabled(model.state == "ready")
        self.cycle_label.setText(f"第 {model.completed % 4 + 1} / 4 轮")
        today = self.c.store.today()
        for item, value in zip(self.stat_labels, (today["count"], round(today["minutes"]),
                                                 round(today.get("rest", 0)), self.c.store.treats)):
            item.setText(str(value))
        self.refresh_bottle()

    def refresh_bottle(self):
        period = self.bottle_period.currentData() if hasattr(self, "bottle_period") else "day"
        today = QDate.currentDate()
        if period == "day":
            start, end = today, today
            label_text = "今天"
        elif period == "week":
            start = today.addDays(-(today.dayOfWeek() - 1))
            end = start.addDays(6)
            label_text = "本周"
        else:
            start = QDate(today.year(), today.month(), 1)
            end = start.addMonths(1).addDays(-1)
            label_text = "本月"
        from datetime import date as pydate
        stars = self.c.store.stars_in_range(pydate(start.year(), start.month(), start.day()),
                                            pydate(end.year(), end.month(), end.day()))
        total_min = sum(s["duration"] for s in stars) / 60
        self.bottle.set_data(stars, period)
        if stars:
            sizes = {"small": 0, "medium": 0, "large": 0}
            for s in stars:
                sizes[s["size"]] = sizes.get(s["size"], 0) + 1
            self.bottle_stats.setText(
                f"{label_text} · {len(stars)} 颗星星 · 专注 {total_min:.0f} 分钟 · "
                f"大 {sizes['large']} 中 {sizes['medium']} 小 {sizes['small']}")
        else:
            self.bottle_stats.setText(f"{label_text}还没有星星，完成专注来收集吧。")

    def refresh_task_choices(self):
        previous = self.task_choice.blockSignals(True)
        try:
            self.task_choice.clear()
            self.task_choice.addItem("下一轮不关联任务", "")
            for task in self.c.store.tasks:
                if not task.done:
                    name = " · ".join(part for part in (task.name, task.category, task.deadline) if part)
                    self.task_choice.addItem(name, task.id)
            index = self.task_choice.findData(self.c.store.settings.task_id)
            self.task_choice.setCurrentIndex(max(0, index))
        finally:
            self.task_choice.blockSignals(previous)

    def refresh_tasks(self):
        self.refresh_task_choices()
        # Clear existing widgets
        while self.task_list.count():
            item = self.task_list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        tasks = self.c.store.tasks
        self.no_tasks.setVisible(not tasks)
        for t in tasks:
            row = QHBoxLayout()
            check = QCheckBox(t.name)
            check.setChecked(t.done)
            check.toggled.connect(lambda checked, tid=t.id: self.c.toggle_task(tid, checked))
            row.addWidget(check)
            if t.category:
                cat = label(f"[{t.category}]", "badge")
                row.addWidget(cat)
            if t.deadline:
                dl = label(f"截止 {t.deadline}", "hint")
                row.addWidget(dl)
            if t.focus_seconds > 0:
                mins = int(t.focus_seconds / 60)
                fm = label(f"{mins}m", "hint")
                row.addWidget(fm)
            del_btn = button("删除")
            del_btn.setFixedWidth(60)
            del_btn.clicked.connect(lambda checked, tid=t.id: self.c.delete_task(tid))
            row.addWidget(del_btn)
            row.addStretch()
            container = QWidget()
            container.setLayout(row)
            self.task_list.addWidget(container)
        self.pie.set_data(self.c.store.task_focus_pie())

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self.c.pet.say("我在这里陪你。双击我打开面板。", seconds=3)


class PerfWidget(QWidget):
    """Compact real-time display of CPU/GPU temp, memory, disk and network speed."""

    def __init__(self):
        super().__init__()
        self._snapshot = None
        self._bars = {}
        self._labels = {}
        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(0, 4, 0, 4)
        for key, title in (
            ("cpu", "CPU"), ("gpu", "显卡"), ("mem", "内存"),
            ("disk", "磁盘"), ("net", "网络"),
        ):
            row = QHBoxLayout()
            row.addWidget(label(title, "hint"))
            row.addStretch()
            bar = _MiniBar()
            row.addWidget(bar, 1)
            val = label("--", "hint")
            val.setFixedWidth(130)
            val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(val)
            layout.addLayout(row)
            self._bars[key] = bar
            self._labels[key] = val
        self.set_data(None)

    def set_data(self, snap):
        self._snapshot = snap
        if snap is None:
            for key in self._bars:
                self._bars[key].set_value(0)
                self._labels[key].setText("--")
            return
        # CPU
        self._bars["cpu"].set_value(snap.cpu_temp / 100 if snap.cpu_temp else snap.cpu_percent / 100)
        cpu_text = f"{snap.cpu_temp:.0f}°C" if snap.cpu_temp is not None else f"{snap.cpu_percent:.0f}%"
        self._labels["cpu"].setText(cpu_text)
        # GPU
        if snap.gpu_temp is not None:
            self._bars["gpu"].set_value(snap.gpu_temp / 100)
            gpu_text = f"{snap.gpu_temp:.0f}°C" + (f" {snap.gpu_name}" if snap.gpu_name else "")
        else:
            self._bars["gpu"].set_value(0)
            gpu_text = "不可用"
        self._labels["gpu"].setText(gpu_text)
        # Memory
        self._bars["mem"].set_value(snap.memory_percent / 100)
        self._labels["mem"].setText(f"{snap.memory_used_gb:.1f}/{snap.memory_total_gb:.0f}G {snap.memory_percent:.0f}%")
        # Disk
        disk_pct = min(1.0, (snap.disk_read_mb + snap.disk_write_mb) / 200)
        self._bars["disk"].set_value(disk_pct)
        self._labels["disk"].setText(f"读 {snap.disk_read_mb:.1f} 写 {snap.disk_write_mb:.1f} MB/s")
        # Network
        net_pct = min(1.0, (snap.net_up_kb + snap.net_down_kb) / 10240)
        self._bars["net"].set_value(net_pct)
        self._labels["net"].setText(f"↑{snap.net_up_kb:.0f} ↓{snap.net_down_kb:.0f} KB/s")
        self.update()


class _MiniBar(QWidget):
    """A tiny horizontal progress bar with a soft green fill."""

    def __init__(self):
        super().__init__()
        self.setFixedHeight(10)
        self._value = 0.0

    def set_value(self, v):
        self._value = max(0.0, min(1.0, v))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0.5, 1, self.width() - 1, self.height() - 2)
        p.setPen(QPen(QColor(220, 225, 215, 140), 1))
        p.setBrush(QColor(245, 242, 232, 180))
        p.drawRoundedRect(rect, 4, 4)
        if self._value > 0.01:
            fill = QRectF(1, 1.5, (self.width() - 2) * self._value, self.height() - 3)
            grad = QLinearGradient(0, 0, 0, self.height())
            grad.setColorAt(0, QColor(120, 190, 150, 200))
            grad.setColorAt(1, QColor(80, 160, 120, 180))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(grad)
            p.drawRoundedRect(fill, 3, 3)


class StarBottle(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(180)
        self.stars = []
        self.period = "day"
        self._anim_time = 0.0
        self._new_star_time = 0.0
        self._anim = QTimer(self)
        self._anim.timeout.connect(self._tick)
        self._anim.start(33)

    def set_data(self, stars, period):
        old_count = len(self.stars)
        self.stars = stars
        self.period = period
        if len(stars) > old_count:
            self._new_star_time = 0.001  # trigger drop animation
        self.update()

    def _tick(self):
        import time as _time
        self._anim_time = _time.monotonic()
        if self._new_star_time > 0:
            self._new_star_time += 0.033
            if self._new_star_time > 2.0:
                self._new_star_time = 0
        self.update()

    def paintEvent(self, event):
        import math as _math
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx = self.width() / 2
        # Bottle body — glass with gradient
        bottle_rect = QRectF(cx - 42, 20, 84, 150)
        grad = QColor(255, 253, 248, 180)
        p.setPen(QPen(QColor(168, 184, 168, 160), 2))
        p.setBrush(grad)
        p.drawRoundedRect(bottle_rect, 22, 22)
        # Bottle neck
        p.setBrush(QColor(220, 224, 210, 160))
        p.drawRoundedRect(QRectF(cx - 32, 10, 64, 16), 6, 6)
        # Bottle shine
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 40))
        p.drawRoundedRect(QRectF(cx - 38, 28, 10, 120), 5, 5)
        # Stars inside with color gradient by duration
        for i, s in enumerate(self.stars[:80]):
            row = i // 7
            col = i % 7
            sx = cx - 32 + col * 10
            sy = 155 - row * 9
            # Drop animation for newest star
            drop_offset = 0
            if self._new_star_time > 0 and i == len(self.stars) - 1:
                t = min(1.0, self._new_star_time / 1.2)
                # Bounce easing: drop from top with bounce
                if t < 0.7:
                    drop_offset = -80 * (1 - (t / 0.7) ** 2)
                else:
                    bounce_t = (t - 0.7) / 0.3
                    drop_offset = 5 * _math.sin(bounce_t * _math.pi)
            sy += drop_offset
            # Color gradient: small=gold, medium=orange, large=deep gold
            size = s.get("size", "small")
            dur = s.get("duration", 0)
            if size == "large":
                color = QColor(237, 170, 100)
                glow = QColor(237, 170, 100, 60)
                r = 5
            elif size == "medium":
                color = QColor(240, 200, 122)
                glow = QColor(240, 200, 122, 50)
                r = 4
            else:
                color = QColor(245, 217, 160)
                glow = QColor(245, 217, 160, 40)
                r = 3
            # Glow for large stars
            if size == "large":
                p.setBrush(glow)
                p.drawEllipse(QRectF(sx - r - 3, sy - r - 3, (r + 3) * 2, (r + 3) * 2))
            # Gentle twinkle
            twinkle = 0.7 + 0.3 * _math.sin(self._anim_time * 3 + i * 0.5)
            twinkle_color = QColor(color)
            twinkle_color.setAlphaF(twinkle)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(twinkle_color)
            path = self._star_path(sx, sy, r)
            p.drawPath(path)
        # Count label above bottle
        p.setPen(QColor("#397761"))
        p.setFont(QFont("Microsoft YaHei UI", 10, QFont.Weight.Bold))
        p.drawText(QRectF(0, 0, self.width(), 15), Qt.AlignmentFlag.AlignCenter, f"× {len(self.stars)}")
        # Sparkle effect for new star
        if self._new_star_time > 0 and self._new_star_time < 1.5:
            sparkle_alpha = int(200 * (1 - self._new_star_time / 1.5))
            p.setPen(QPen(QColor(255, 220, 120, sparkle_alpha), 1.5))
            for angle in range(0, 360, 45):
                rad = _math.radians(angle)
                sx = cx + _math.cos(rad) * 15
                sy = 90 + _math.sin(rad) * 15
                p.drawLine(QPointF(sx, sy), QPointF(sx + _math.cos(rad) * 6, sy + _math.sin(rad) * 6))
        p.end()

    @staticmethod
    def _star_path(cx, cy, r):
        from PySide6.QtGui import QPainterPath
        import math as _math
        path = QPainterPath()
        for i in range(5):
            angle = -_math.pi / 2 + i * 2 * _math.pi / 5
            x = cx + r * _math.cos(angle)
            y = cy + r * _math.sin(angle)
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
            angle2 = angle + _math.pi / 5
            x2 = cx + r * 0.4 * _math.cos(angle2)
            y2 = cy + r * 0.4 * _math.sin(angle2)
            path.lineTo(x2, y2)
        path.closeSubpath()
        return path


class PieChart(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(200)
        self.data = []

    def set_data(self, data):
        self.data = data
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.data:
            p.setPen(QColor("#8a8f7e"))
            p.setFont(QFont("Microsoft YaHei UI", 10))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "完成专注后，这里会显示任务占比")
            p.end()
            return
        import math as _math
        total = sum(v for _, v in self.data) or 1
        cx = self.width() / 2
        cy = self.height() / 2
        radius = min(self.width(), self.height()) / 2 - 30
        colors = ["#397761", "#76a38a", "#edaa64", "#df8f85", "#8b9ad6", "#c4a8d4", "#e0c068", "#a0c4a0"]
        start = 90 * 16
        p.save()
        p.translate(cx, cy)
        for i, (label, value) in enumerate(self.data):
            angle = int(value / total * 360 * 16)
            color = QColor(colors[i % len(colors)])
            p.setPen(QPen(QColor("#fffdf8"), 2))
            p.setBrush(color)
            p.drawPie(QRectF(-radius, -radius, radius * 2, radius * 2), start, -angle)
            start -= angle
        p.restore()
        # Legend
        p.setFont(QFont("Microsoft YaHei UI", 9))
        ly = 10
        for i, (label, value) in enumerate(self.data):
            color = QColor(colors[i % len(colors)])
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            p.drawRoundedRect(QRectF(self.width() - 120, ly, 12, 12), 3, 3)
            p.setPen(QColor("#334a3f"))
            mins = int(value / 60)
            p.drawText(QRectF(self.width() - 104, ly - 2, 100, 16),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       f"{label} {mins}m")
            ly += 18
        p.end()
