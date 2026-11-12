"""Global Windows shortcuts, with transactional conflict handling."""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter
from PySide6.QtGui import QKeySequence


def parse_hotkey(text: str) -> tuple[int, int]:
    sequence = QKeySequence.fromString(text, QKeySequence.SequenceFormat.PortableText)
    portable = sequence.toString(QKeySequence.SequenceFormat.PortableText)
    if sequence.count() != 1 or not portable:
        raise ValueError("请设置单组快捷键，例如 Ctrl+Alt+O。")
    parts = portable.split("+")
    modifiers = 0
    for item in parts[:-1]:
        if item not in ("Ctrl", "Alt", "Shift"):
            raise ValueError("请使用 Ctrl、Alt、Shift；不使用 Windows 键。")
        modifiers |= {"Ctrl": 2, "Alt": 1, "Shift": 4}[item]
    if not modifiers & 3:
        raise ValueError("快捷键至少需要包含 Ctrl 或 Alt。")
    key = parts[-1].upper()
    if len(key) == 1 and ("A" <= key <= "Z" or "0" <= key <= "9"):
        code = ord(key)
    elif key.startswith("F") and key[1:].isdigit() and 1 <= int(key[1:]) <= 12:
        code = 0x70 + int(key[1:]) - 1
    else:
        raise ValueError("主键请选择字母、数字，或 F1–F12。")
    return modifiers | 0x4000, code


class GlobalHotkeys(QAbstractNativeEventFilter):
    IDS = (0x4011, 0x4012)

    def __init__(self, app, on_pet, on_panel):
        super().__init__()
        self.app = app
        self.actions = dict(zip(self.IDS, (on_pet, on_panel)))
        self.registered: dict[int, tuple[int, int]] = {}
        self.user32 = ctypes.WinDLL("user32", use_last_error=True) if sys.platform == "win32" else None
        if self.user32:
            self.user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
            self.user32.RegisterHotKey.restype = wintypes.BOOL
            self.user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
            self.user32.UnregisterHotKey.restype = wintypes.BOOL
        app.installNativeEventFilter(self)

    def apply(self, pet: str, panel: str) -> tuple[bool, str]:
        try:
            bindings = [parse_hotkey(pet), parse_hotkey(panel)]
            if bindings[0] == bindings[1]:
                return False, "两个操作需要不同的快捷键。"
        except ValueError as error:
            return False, str(error)
        if not self.user32:
            return False, "全局快捷键需要 Windows。"
        old = self.registered.copy()
        self.clear()
        for identity, binding in zip(self.IDS, bindings):
            if not self.user32.RegisterHotKey(None, identity, *binding):
                self.clear()
                for old_id, old_binding in old.items():
                    if self.user32.RegisterHotKey(None, old_id, *old_binding):
                        self.registered[old_id] = old_binding
                return False, "快捷键被其他程序占用，请换一组。原有快捷键已保留。"
            self.registered[identity] = binding
        return True, "快捷键已保存，在其他软件里也能使用。"

    def clear(self):
        if self.user32:
            for identity in self.registered:
                self.user32.UnregisterHotKey(None, identity)
        self.registered = {}

    def nativeEventFilter(self, event_type, message):
        if self.user32 and bytes(event_type) in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x0312 and msg.wParam in self.actions:
                self.actions[msg.wParam]()
                return True, 0
        return False, 0
