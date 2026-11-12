from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
import random
import sys
import time

from PySide6.QtCore import QObject, QLockFile, QTimer, Qt
from PySide6.QtGui import QFont, QKeySequence
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QFileDialog, QMenu, QMessageBox, QSystemTrayIcon

from .art import app_icon
from .care import CareScheduler
from .hotkeys import GlobalHotkeys
from .lyrics import Lyrics, MediaState
from .model import Pomodoro, Store
from .monitor import PerfMonitor
from .music import LyricLoader, MediaBridge
from .panel import Panel, STYLE
from .pet import Pet
from .update_ui import UpdateController
from .weather import WeatherWorker, weather_name, weather_tip

LOG = logging.getLogger(__name__)
DEMO_LRC = """[ti:橘子的午后（原创演示）]
[00:00.00]窗边的光，落在小小爪尖
[00:05.00]把今天，过成一颗橘子
[00:10.00]陪你慢慢走，陪你慢慢唱
[00:15.00]每一小步，都值得被看见
[00:20.00]歇一会儿，再一起向前
"""


def mmss(seconds):
    seconds = max(0, int(seconds))
    return f"{seconds // 60:02}:{seconds % 60:02}"


class Companion(QObject):
    def __init__(self, app: QApplication, folder: Path, services=True):
        super().__init__()
        self.app = app
        self.store = Store(folder)
        self.timer = Pomodoro(self.store.settings, completed=self.store.completed)
        self.services = services
        self.care = CareScheduler(self.store.settings)
        self.weather_worker = WeatherWorker()
        self.weather_data = None
        self.weather_pending = False
        self.next_weather_fetch = time.monotonic() + 1800
        self.last_clock_text = ""
        self.pet = Pet()
        self.pet.walking_enabled = self.store.settings.walking
        self.pet.lyric_font = self.store.settings.lyric_font
        self.pet.lyric_mode = self.store.settings.lyric_mode
        self.pet.apply_size(self.store.settings.pet_size)
        self.pet.apply_character(self.store.settings.character)
        self.bridge = MediaBridge()
        self.bridge.enabled = self.store.settings.music
        self.loader = LyricLoader(folder / "lyrics")
        self.perf = PerfMonitor()
        self.perf.enabled = self.store.settings.performance
        self.perf.updated.connect(self.receive_perf)
        self.media = MediaState()
        self.live_media = MediaState()
        self.lyrics = Lyrics([])
        self.lyric_status = "等待播放音乐"
        self.manual_key = ""
        self.demo = False
        self.demo_position = 0.0
        self.demo_started = 0.0
        self.demo_playing = True
        self.music_notice_until = 0.0
        self.music_notice_text = ""
        self.rest_started = None
        self.round_task = None
        self.round_note = ""
        self.updates = UpdateController(self)
        self.panel = Panel(self)
        self.hotkeys = GlobalHotkeys(app, self.toggle_pet, self.toggle_panel)
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip("橘子专注 · 右键打开菜单")
        self.tray.activated.connect(self.tray_activated)
        self.tray_menu = QMenu()
        self.tray_menu.aboutToShow.connect(lambda: self.fill_menu(self.tray_menu))
        self.tray.setContextMenu(self.tray_menu)
        self.pet.petted.connect(self.pet_cat)
        self.pet.panel_requested.connect(self.show_panel)
        self.pet.menu_requested.connect(self.show_menu)
        self.pet.moved.connect(self.save_position)
        self.pet.media_requested.connect(self.pet_media_command)
        self.pet.timer_toggle_requested.connect(self.toggle_timer)
        self.pet.lyric_close_requested.connect(self.close_lyrics)
        self.bridge.updated.connect(self.receive_media)
        self.bridge.command_result.connect(self.music_notice)
        self.loader.loaded.connect(self.receive_lyrics)
        self.weather_worker.result.connect(self.receive_weather)
        self.weather_worker.failed.connect(self.weather_failed)
        self.heartbeat = QTimer(self)
        self.heartbeat.timeout.connect(self.tick)
        self.heartbeat.start(100)
        app.aboutToQuit.connect(self.cleanup)
        if services:
            ok, text = self.hotkeys.apply(self.store.settings.pet_hotkey, self.store.settings.panel_hotkey)
            self.panel.hotkey_status.setText(text)
            if not ok:
                self.panel.footer.setText("快捷键未注册，可到设置中修改")
            if self.store.settings.music:
                self.bridge.start()
            self.perf.start()
            if QSystemTrayIcon.isSystemTrayAvailable():
                self.tray.show()
            self.load_weather_cache()
            if self.store.settings.weather:
                QTimer.singleShot(800, self.refresh_weather)
        if self.store.warning:
            self.panel.focus_hint.setText(self.store.warning)
        self.panel.refresh_tasks()
        self.panel.refresh_timer()

    def show(self):
        self.pet.home()
        if self.store.position:
            self.pet.move(*self.store.position)
            self.pet.clamp()
        self.pet.show()
        if self.store.settings.greetings:
            message = self.care.welcome()
            self.pet.say(message, seconds=8)
            self.panel.greeting_preview.setText(message)
        self.panel.refresh_tasks()
        self.show_panel()

    def show_panel(self):
        self.panel.showNormal()
        rect = self.panel.screen().availableGeometry()
        if not rect.intersects(self.panel.frameGeometry()):
            self.panel.move(rect.center() - self.panel.rect().center())
        self.panel.raise_()
        self.panel.activateWindow()

    def toggle_panel(self):
        if self.panel.isVisible() and not self.panel.isMinimized():
            self.panel.hide()
        else:
            self.show_panel()

    def toggle_pet(self):
        self.pet.setVisible(not self.pet.isVisible())
        if self.pet.isVisible():
            self.pet.clamp()

    def locate_pet(self):
        self.pet.home()
        self.pet.show()
        self.pet.say("我在这里！", happy=True)
        self.save_position()

    def save(self):
        try:
            self.store.save()
        except OSError:
            LOG.exception("Cannot save state")
            self.panel.footer.setText("记录保存失败，请检查 data 目录权限")

    def save_position(self):
        self.store.position = [self.pet.x(), self.pet.y()]
        self.save()

    def save_task(self):
        self.store.settings.task = self.panel.task.text().strip()
        self.save()

    def toggle_timer(self):
        self.save_task()
        if self.timer.state == "running":
            event = self.timer.pause()
            if event:
                self.complete(event)
            else:
                if self.timer.phase == "focus":
                    self.rest_started = time.monotonic()
                self.pet.say("歇一会儿，我等你。")
        else:
            self.flush_rest()
            if self.timer.state == "ready" and self.timer.phase == "focus":
                selected = self.store.settings.task_id
                self.round_task = next((t for t in self.store.tasks if t.id == selected and not t.done), None)
                self.round_note = self.store.settings.task
            self.timer.start()
            self.pet.say("专心做你的事，我来陪你。" if self.timer.phase == "focus" else "站起来，伸个懒腰吧。")
        self.tick()

    def flush_rest(self):
        """Record the time spent paused during a focus session as rest."""
        if self.rest_started is None:
            return
        elapsed = time.monotonic() - self.rest_started
        self.rest_started = None
        if elapsed >= 1 and self.timer.phase == "focus":
            self.store.add_rest(elapsed)
            self.save()

    def reset_timer(self):
        self.flush_rest()
        self.timer.reset()
        self.round_task = None
        self.pet.say("没关系，我们重新开始。")
        self.tick()

    def switch_phase(self, phase):
        if self.timer.state == "ready":
            self.timer.reset(phase)
            self.tick()

    def complete(self, event):
        self.store.reward(event, self.round_task, self.round_note)
        self.round_task = None
        if event.phase != "focus":
            self.store.add_rest(event.seconds)
        self.save()
        text = "这一轮完成啦，休息一下。" if event.phase == "focus" else "休息结束，准备好再开始。"
        self.pet.say(text, happy=True, seconds=10)
        self.panel.focus_hint.setText(text)
        if self.store.settings.sound:
            QApplication.beep()
        if self.tray.isVisible():
            self.tray.showMessage("橘子专注", text, QSystemTrayIcon.MessageIcon.Information, 6000)
        # Star collection notification
        if event.phase == "focus":
            from .model import star_size
            size = star_size(event.seconds)
            size_text = {"small": "小星星", "medium": "中星星", "large": "大星星"}[size]
            minutes = int(event.seconds / 60)
            self.pet.say(f"星星+1！{minutes}分钟。", happy=True, seconds=6)
            self.panel.focus_hint.setText(f"收获一颗{size_text}！专注 {minutes} 分钟，已放进星愿瓶。")
        self.panel.refresh_tasks()
        self.panel.refresh_bottle()

    def pet_cat(self):
        self.pet.say(random.choice(("呼噜呼噜…最喜欢你啦。", "今天也有好好努力呢。", "摸摸充电完成，喵！", "再摸一下，就陪你学习。")), happy=True)

    def feed(self):
        if self.store.treats > 0:
            self.store.treats -= 1
            self.pet.say("啊呜！小鱼干真好吃！", happy=True, seconds=4)
            self.pet.celebrate()
            self.save()
        else:
            self.pet.say("完成专注，就有小鱼干啦。")
        self.panel.refresh_timer()

    def change_duration(self, key, value):
        setattr(self.store.settings, key, value)
        if self.timer.state == "ready" and self.timer.phase == key:
            self.timer.reset()
        self.save()
        spin = getattr(self.panel, "durations", {}).get(key)
        if spin is not None and spin.value() != value:
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)
        self.panel.refresh_timer()

    def add_focus_preset(self, minutes):
        presets = self.store.settings.focus_presets
        if minutes not in presets:
            if len(presets) >= 12:
                self.pet.say("快捷时长最多 12 个。")
                return
            presets.append(minutes)
            presets.sort()
            self.save()
            self.panel.rebuild_focus_presets()
        self.change_duration("focus", minutes)

    def change_walking(self, value):
        self.store.settings.walking = value
        self.pet.walking_enabled = value
        self.save()

    def change_sound(self, value):
        self.store.settings.sound = value
        self.save()

    def change_offset(self, value):
        self.store.settings.lyric_offset = value
        self.save()

    def change_font(self, index):
        family = self.panel.font_select.itemData(index)
        self.store.settings.lyric_font = family
        self.pet.lyric_font = family
        self.save()

    def change_lyric_mode(self, index):
        mode = self.panel.mode_select.itemData(index)
        self.store.settings.lyric_mode = mode
        self.pet.lyric_mode = mode
        self.save()
        self.update_music()

    def set_lyrics_visible(self, visible):
        if self.store.settings.lyrics_visible == visible:
            return
        self.store.settings.lyrics_visible = visible
        self.save()
        self.update_music()
        if not visible:
            self.pet.say("歌词区收起了，右键打开。", seconds=5)

    def show_lyrics(self):
        self.set_lyrics_visible(True)

    def close_lyrics(self):
        self.set_lyrics_visible(False)

    def change_pet_size(self, value):
        scale = value / 100.0
        self.store.settings.pet_size = scale
        self.pet.apply_size(scale)
        self.pet.clamp()
        self.panel.size_label.setText(f"{scale:.1f}x")
        self.save()

    def change_character(self, key):
        self.store.settings.character = key
        self.pet.apply_character(key)
        self.save()

    def add_task(self):
        name = self.panel.task_name.text().strip()
        if not name:
            self.panel.task_name.setPlaceholderText("先输入任务名称")
            return
        deadline = ""
        d = self.panel.task_deadline.date()
        if d > self.panel.task_deadline.minimumDate():
            deadline = f"{d.year():04d}-{d.month():02d}-{d.day():02d}"
        category = self.panel.task_category.text().strip()
        task = self.store.add_task(name, category, deadline)
        self.store.settings.task_id = task.id
        self.save()
        self.panel.task_name.clear()
        self.panel.task_category.clear()
        self.panel.task_deadline.setDate(self.panel.task_deadline.minimumDate())
        self.panel.refresh_tasks()
        self.pet.say("任务已记下，开始专注吧。")

    def select_task(self, index):
        self.store.settings.task_id = self.panel.task_choice.itemData(index) or ""
        self.save()

    def toggle_task(self, task_id, done):
        self.store.set_task_done(task_id, done)
        if done and self.store.settings.task_id == task_id:
            self.store.settings.task_id = ""
        self.save()
        self.panel.refresh_tasks()
        if done:
            self.pet.say("任务完成，真棒！")

    def delete_task(self, task_id):
        self.store.delete_task(task_id)
        if self.store.settings.task_id == task_id:
            self.store.settings.task_id = ""
        self.save()
        self.panel.refresh_tasks()

    def refresh_bottle(self):
        if hasattr(self.panel, "bottle"):
            self.panel.refresh_bottle()

    def save_hotkeys(self):
        values = {key: item.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
                  for key, item in self.panel.key_edits.items()}
        ok, text = self.hotkeys.apply(values["pet_hotkey"], values["panel_hotkey"])
        self.panel.hotkey_status.setText(text)
        if ok:
            for key, value in values.items():
                setattr(self.store.settings, key, value)
            self.save()

    def change_music(self, value):
        self.store.settings.music = value
        self.bridge.enabled = value
        if not value:
            self.demo = False
            self.panel.demo_button.setText("跟唱演示")
            self.receive_media(MediaState())
            self.media = MediaState()
            self.lyrics = Lyrics([])
        else:
            self.media = MediaState()
            if self.services:
                self.bridge.start()
            self.receive_media(self.live_media)
        self.save()
        self.update_music()

    def change_online(self, value):
        self.store.settings.online_lyrics = value
        self.save()
        self.retry_lyrics()

    def receive_media(self, media):
        self.live_media = media
        if self.demo or not self.store.settings.music:
            return
        old_key = self.media.key
        self.media = media
        if media.key != old_key:
            self.lyrics = Lyrics([])
            self.manual_key = ""
            self.lyric_status = "正在寻找逐句歌词…" if media.title else "等待播放音乐"
            if media.key:
                self.loader.request(media, self.store.settings.online_lyrics)
        self.update_music()

    def receive_lyrics(self, key, text, status):
        if self.demo or key != self.media.key or key == self.manual_key:
            return
        self.lyrics = Lyrics.parse(text)
        self.lyric_status = status
        self.update_music()

    def retry_lyrics(self):
        if not self.demo and self.media.key:
            self.manual_key = ""
            self.lyric_status = "正在读取歌词…"
            self.loader.request(self.media, self.store.settings.online_lyrics)

    def import_lyrics(self):
        if self.demo or not self.media.key:
            self.music_notice("播放歌曲后再导入LRC。")
            return
        path, _ = QFileDialog.getOpenFileName(self.panel, "为当前歌曲导入逐句歌词", "", "LRC 歌词 (*.lrc);;文本 (*.txt)")
        if not path:
            return
        try:
            data = Path(path).read_bytes()
            if len(data) > 1_000_000:
                raise ValueError("歌词文件太大（限 1 MB）。")
            for encoding in ("utf-8-sig", "utf-16", "gb18030"):
                try:
                    text = data.decode(encoding)
                    parsed = Lyrics.parse(text)
                    if parsed.lines:
                        break
                except UnicodeError:
                    continue
            else:
                raise ValueError("需要带时间标签的 LRC。")
            self.manual_key = self.media.key
            self.lyrics = parsed
            self.loader.save(self.media.key, text, manual=True)
            self.lyric_status = "已导入本地歌词 · " + Path(path).name
            self.update_music()
        except (OSError, ValueError) as error:
            self.music_notice(str(error))

    def toggle_demo(self):
        self.demo = not self.demo
        if self.demo:
            if not self.store.settings.music:
                self.panel.music_enabled.setChecked(True)
            self.demo_started = time.monotonic()
            self.demo_position = 0.0
            self.demo_playing = True
            self.lyrics = Lyrics.parse(DEMO_LRC)
            self.lyric_status = "原创演示歌词 · 仅动画，无声音"
            self.pet.message_until = 0
            self.pet.show()
            self.panel.demo_button.setText("结束演示")
        else:
            self.panel.demo_button.setText("跟唱演示")
            self.media = MediaState()
            self.lyrics = Lyrics([])
            self.receive_media(self.live_media)
        self.update_music()

    def demo_time(self):
        return (self.demo_position + (time.monotonic() - self.demo_started if self.demo_playing else 0)) % 25

    def pet_media_command(self, action):
        if self.demo or (self.store.settings.music and self.media.source):
            self.media_command(action)
        else:
            self.pet.say("打开音乐，或点跟唱演示。", seconds=5)

    def media_command(self, action):
        if self.demo:
            current = self.demo_time()
            if action == "toggle":
                self.demo_position = current
                self.demo_started = time.monotonic()
                self.demo_playing = not self.demo_playing
            else:
                self.demo_position = (current + (5 if action == "next" else -5)) % 25
                self.demo_started = time.monotonic()
            self.update_music()
        elif self.store.settings.music and self.media.source:
            self.bridge.command(action, self.media.source)

    def music_notice(self, text):
        self.music_notice_until = time.monotonic() + 8
        self.music_notice_text = text
        self.panel.lyric_source.setText(text)
        self.pet.say(text, seconds=5)

    def update_music(self):
        now = time.monotonic()
        enabled = self.store.settings.music
        media = self.media
        position = self.demo_time() if self.demo else media.position_at(now)
        playing = self.demo_playing if self.demo else media.playing and now - media.sampled_at < 4
        connected = enabled and (self.demo or bool(media.title))
        timeline = self.demo or media.timeline
        char_index, char_total = 0, 0
        if timeline and self.lyrics.lines and self.store.settings.lyric_mode == "word":
            current, following, char_index, char_total = self.lyrics.at_detail(
                position, self.store.settings.lyric_offset)
        else:
            current, following = self.lyrics.at(position, self.store.settings.lyric_offset) if timeline else ("", "")
        self.pet.singing = connected and playing
        self.pet.lyric = current if connected else ""
        self.pet.lyric_char_index = char_index if connected else 0
        self.pet.lyric_char_total = char_total if connected else 0
        self.pet.music_hint = ("♪ " + media.title) if connected and not current and not self.demo else ""
        # A paused song keeps the strip open; only the user (double-click or
        # the right-click menu) or losing the player closes it.
        self.pet.set_music_visible(connected and self.store.settings.lyrics_visible)
        self.panel.track_title.setText("橘子的午后 · 演示" if self.demo else media.title or "等待 Apple Music")
        self.panel.track_artist.setText("原创演示 / 不会播放声音" if self.demo else media.artist or "在播放器中播放一首歌，橘子会自动连接。")
        status = "正在播放" if playing else "已暂停"
        if not enabled:
            status = "音乐联动已关闭"
        elif not connected:
            status = media.error or "尚未连接 · 支持 Windows 系统媒体会话"
        elif not self.demo:
            source = "Apple Music" if "apple" in media.source.lower() else "系统媒体"
            status = source + " · " + status
        self.panel.playback_status.setText(status)
        self.panel.lyric_current.setText(current or ("♪  前奏 / 间奏" if self.lyrics.lines and connected else "让音乐陪你一会儿"))
        self.panel.lyric_next.setText(following or ("逐句歌词会显示在小猫头顶" if not self.lyrics.lines else ""))
        total = 25 if self.demo else media.duration
        self.panel.music_time.setText(mmss(position) + (" / " + mmss(total) if total > 0 else ""))
        self.panel.play.setText("暂停" if playing else "播放")
        for item in (self.panel.previous, self.panel.play, self.panel.next):
            item.setEnabled(connected)
        self.panel.import_button.setEnabled(connected and not self.demo)
        self.panel.lyric_source.setText(self.music_notice_text if now < self.music_notice_until else self.lyric_status)

    def location_key(self):
        s = self.store.settings
        return f"{s.city}|{s.latitude:.4f}|{s.longitude:.4f}"

    def load_weather_cache(self):
        path = self.store.folder / "weather.json"
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                if data.get("location_key") == self.location_key():
                    self.weather_data = data
                    self.render_weather()
        except (OSError, ValueError, AttributeError, TypeError, KeyError):
            LOG.info("Weather cache unavailable")

    def refresh_weather(self):
        if not self.store.settings.weather:
            self.panel.weather_update.setText("天气已关闭，可勾选后查询。")
            return
        if self.weather_pending:
            return
        self.weather_pending = True
        self.next_weather_fetch = time.monotonic() + 1800
        self.panel.weather_update.setText("正在更新天气…")
        s = self.store.settings
        self.weather_worker.request("weather", city=s.city, latitude=s.latitude,
                                    longitude=s.longitude, location_key=self.location_key())

    def search_city(self):
        query = self.panel.city_input.text().strip()
        if len(query) < 2:
            self.panel.city_status.setText("请输入至少两个字的城市名。")
            return
        self.panel.city_status.setText("正在搜索城市…")
        self.weather_worker.request("cities", query=query[:100])

    def use_city(self):
        data = self.panel.city_results.currentData()
        if not data:
            self.panel.city_status.setText("先搜索城市，再从结果中选择。")
            return
        s = self.store.settings
        s.city = data["name"]
        s.latitude = float(data["latitude"])
        s.longitude = float(data["longitude"])
        self.panel.city_input.setText(s.city)
        self.panel.city_status.setText("已设置为 " + self.panel.city_results.currentText())
        self.weather_data = None
        self.panel.weather_title.setText(s.city + " · 等待天气")
        self.panel.weather_detail.setText("")
        self.panel.weather_tip.setText("")
        self.weather_pending = False
        self.save()
        self.refresh_weather()

    def receive_weather(self, kind, data):
        if kind == "cities":
            if data.get("query") != self.panel.city_input.text().strip():
                return
            self.panel.city_results.clear()
            for city in data.get("results", []):
                text = " · ".join(dict.fromkeys(str(city[key]) for key in ("name", "admin1", "country") if city.get(key)))
                self.panel.city_results.addItem(text, city)
            self.panel.city_status.setText("选择省份和国家相符的城市。" if self.panel.city_results.count()
                                           else "没有找到，试试城市英文名，例如 Beijing。")
            return
        self.weather_pending = False
        if data.get("location_key") != self.location_key() or not self.store.settings.weather:
            return
        current = data.get("current", {})
        if not isinstance(current.get("temperature_2m"), (int, float)):
            self.weather_failed("weather", "暂时没有有效天气数据，请稍后重试。")
            return
        self.weather_data = data
        self.render_weather()
        try:
            path = self.store.folder / "weather.json"
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            temporary.replace(path)
        except OSError:
            LOG.info("Cannot cache weather")

    def render_weather(self):
        data = self.weather_data
        if not data:
            return
        current = data["current"]
        daily = data.get("daily", {})
        temperature = current["temperature_2m"]
        condition = weather_name(current.get("weather_code", -1))
        self.panel.weather_title.setText(f"{data['city']} · {temperature:g}°C · {condition}")
        low = daily.get("temperature_2m_min", [None])[0]
        high = daily.get("temperature_2m_max", [None])[0]
        detail = f"体感 {current.get('apparent_temperature', '—')}°C · 风速 {current.get('wind_speed_10m', '—')} km/h"
        if low is not None and high is not None:
            detail += f"\n今日 {low:g} ~ {high:g}°C"
        self.panel.weather_detail.setText(detail)
        self.panel.weather_tip.setText(weather_tip(data))
        stamp = datetime.fromisoformat(data["fetched_at"]).astimezone()
        self.panel.weather_update.setText(f"更新于 {stamp:%m-%d %H:%M} · 30 分钟自动更新")

    def weather_failed(self, kind, text):
        if kind == "cities":
            self.panel.city_status.setText(text)
        else:
            self.weather_pending = False
            if self.weather_data:
                stamp = datetime.fromisoformat(self.weather_data["fetched_at"]).astimezone()
                text += f" 显示 {stamp:%m-%d %H:%M} 的缓存。"
            self.panel.weather_update.setText(text)

    def change_weather(self, value):
        self.store.settings.weather = value
        self.save()
        if value:
            self.refresh_weather()
        else:
            self.panel.weather_update.setText("天气已关闭，保留上次显示结果。")

    def change_greetings(self, value):
        self.store.settings.greetings = value
        self.care.last_time = time.monotonic()
        self.save()

    def change_quotes(self, value):
        self.store.settings.quotes = value
        self.save()

    def change_reminder_interval(self, value):
        self.store.settings.reminder_minutes = value
        self.save()

    def change_performance(self, value):
        self.store.settings.performance = value
        self.perf.enabled = value
        if not value:
            self.panel.perf_widget.set_data(None)
        self.save()

    def receive_perf(self, snap):
        if self.store.settings.performance:
            self.panel.perf_widget.set_data(snap)
            if snap and snap.temps_available:
                self.panel.sensor_status.setText("已读取可用的硬件温度。")
            elif snap:
                self.panel.sensor_status.setText("等待温度传感器。CPU 使用率、内存等指标会继续更新。")

    def open_temperature_helper(self):
        exe = project_root() / "components" / "LibreHardwareMonitor" / "LibreHardwareMonitor.exe"
        if not exe.is_file():
            self.panel.sensor_status.setText("温度组件未随此副本分发。请从完整项目目录启动。")
            return
        try:
            os.startfile(str(exe), cwd=str(exe.parent))
        except OSError:
            LOG.info("Unable to launch LibreHardwareMonitor", exc_info=True)
            self.panel.sensor_status.setText("温度组件未启动，请检查 Windows 提示。")
            return
        self.panel.sensor_status.setText("已请求打开温度组件。启动后请保持组件运行。")
        QTimer.singleShot(5000, self.perf.refresh_temperatures)

    def say_something(self):
        message = self.care.choose()
        if self.store.settings.weather and self.weather_data and random.random() < 0.25:
            stamp = datetime.fromisoformat(self.weather_data["fetched_at"])
            if (datetime.now(timezone.utc) - stamp).total_seconds() < 7200:
                message = weather_tip(self.weather_data)
        self.panel.greeting_preview.setText(message)
        self.pet.say(message, seconds=8)
        self.pet.show()
        self.care.last_time = time.monotonic()

    def tick(self):
        event = self.timer.tick()
        if event:
            self.complete(event)
        self.pet.focused = self.timer.phase == "focus" and self.timer.state == "running"
        self.panel.refresh_timer()
        self.update_music()
        now = datetime.now().astimezone()
        text = f"{now:%m月%d日  %H:%M} · 当地时间"
        if text != self.last_clock_text:
            self.last_clock_text = text
            self.panel.local_clock.setText(text)
            # Check task deadlines once per minute
            self._check_deadlines(now)
        # Update the held alarm clock and the hourglass countdown on the pet
        self.pet.set_clock_text(f"{now:%H:%M}")
        if self.timer.state == "running":
            remaining = max(0.0, self.timer.deadline - self.timer.clock())
        else:
            remaining = self.timer.remaining
        self.pet.countdown_total = max(1, int(self.timer.duration))
        self.pet.countdown_remaining = remaining
        self.pet.countdown_state = self.timer.state
        self.pet.countdown_phase = "focus" if self.timer.phase == "focus" else "rest"
        busy = (self.pet.focused or self.pet.singing or not self.pet.isVisible()
                or time.monotonic() < self.pet.message_until)
        message = self.care.due(now, busy=busy)
        if message:
            self.pet.say(message, seconds=8)
            self.panel.greeting_preview.setText(message)
        if self.services and self.store.settings.weather and time.monotonic() >= self.next_weather_fetch:
            self.refresh_weather()

    def _check_deadlines(self, now):
        today = now.date().isoformat()
        for t in self.store.tasks:
            if t.done or not t.deadline:
                continue
            if t.deadline == today:
                if not getattr(t, "_notified", False):
                    t._notified = True
                    self.pet.say("任务今天截止，记得处理。", seconds=8)

    def fill_menu(self, menu):
        menu.clear()
        menu.addAction("打开番茄钟", self.show_panel)
        menu.addAction("摸摸橘子", self.pet_cat)
        menu.addAction(f"喂小鱼干（{self.store.treats}）", self.feed)
        menu.addSeparator()
        for caption, command in (("上一曲", "previous"), ("暂停 / 播放", "toggle"), ("下一曲", "next")):
            action = menu.addAction(caption)
            action.setEnabled(self.store.settings.music and (self.demo or bool(self.media.source)))
            action.triggered.connect(lambda checked=False, cmd=command: self.media_command(cmd))
        menu.addSeparator()
        if self.pet.music_visible:
            lyrics = menu.addAction("关闭歌词区", self.close_lyrics)
        else:
            lyrics = menu.addAction("显示歌词区", self.show_lyrics)
        lyrics.setEnabled(self.store.settings.music and (self.demo or bool(self.media.source)))
        walk = menu.addAction("允许自动走动")
        walk.setCheckable(True)
        walk.setChecked(self.store.settings.walking)
        walk.triggered.connect(self.panel.walk.setChecked)
        menu.addAction("隐藏小猫" if self.pet.isVisible() else "显示小猫", self.toggle_pet)
        menu.addAction("叫小猫回来", self.locate_pet)
        menu.addAction("说一句暖心话", self.say_something)
        menu.addSeparator()
        menu.addAction("退出橘子专注", self.quit)

    def show_menu(self, point):
        menu = QMenu(self.pet)
        self.fill_menu(menu)
        menu.exec(point)
        menu.deleteLater()

    def tray_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_panel()

    def cleanup(self):
        self.flush_rest()
        self.heartbeat.stop()
        self.hotkeys.clear()
        self.app.removeNativeEventFilter(self.hotkeys)
        self.bridge.stop()
        self.perf.stop()
        self.loader.stop()
        self.weather_worker.stop()
        self.tray.hide()
        self.store.settings.task = self.panel.task.text().strip()
        self.store.position = [self.pet.x(), self.pet.y()]
        self.save()

    def quit(self):
        # Closing an individual window hides it. Explicit Quit must end the event loop.
        self.app.exit(0)


def project_root():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description="橘子专注 · 桌面宠物")
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--demo", action="store_true", help="show original silent singing demo")
    parser.add_argument("--exit-after", type=int, help="close after N seconds for smoke testing")
    args = parser.parse_args()
    folder = args.data_dir or project_root() / "data"
    folder.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(folder / "app.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[handler], format="%(asctime)s %(levelname)s %(message)s")
    app = QApplication(sys.argv[:1])
    app.setApplicationName("OrangePet")
    app.setApplicationDisplayName("橘子专注")
    app.setQuitOnLastWindowClosed(False)
    app.setFont(QFont("Microsoft YaHei UI", 10))
    app.setStyleSheet(STYLE)
    app.setWindowIcon(app_icon())
    identity = "OrangePet-" + hashlib.sha256(str(folder.resolve()).casefold().encode()).hexdigest()[:20]
    lock = QLockFile(str(folder / "instance.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        socket = QLocalSocket()
        socket.connectToServer(identity)
        if socket.waitForConnected(1500):
            socket.write(b"show")
            socket.waitForBytesWritten(1000)
        return 0
    QLocalServer.removeServer(identity)
    server = QLocalServer()
    server.listen(identity)

    def exception_hook(kind, value, traceback):
        LOG.error("Unhandled exception", exc_info=(kind, value, traceback))
        QMessageBox.critical(None, "橘子专注", "发生了错误，详情已写入 data/app.log。\n" + str(value))

    sys.excepthook = exception_hook
    companion = Companion(app, folder)

    def new_connection():
        socket = server.nextPendingConnection()
        if socket:
            socket.disconnectFromServer()
            socket.deleteLater()
        companion.show_panel()

    server.newConnection.connect(new_connection)
    companion.show()
    companion.updates.startup()
    if args.demo:
        companion.panel.tabs.setCurrentIndex(1)
        companion.toggle_demo()
    if args.exit_after:
        QTimer.singleShot(args.exit_after * 1000, companion.quit)
    result = app.exec()
    server.close()
    lock.unlock()
    return result
