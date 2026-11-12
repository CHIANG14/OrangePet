"""Pure timing and persistence logic, independent of the GUI."""
from __future__ import annotations

import json
import math
import time
import uuid
from dataclasses import asdict, dataclass, field, fields
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable


# Five built-in focus durations (minutes); users can append their own.
FOCUS_PRESETS = (15, 25, 30, 45, 60)


@dataclass
class Settings:
    update_repository: str = ""
    focus: int = 25
    short: int = 5
    long: int = 15
    focus_presets: list[int] = field(default_factory=lambda: list(FOCUS_PRESETS))
    walking: bool = True
    sound: bool = True
    music: bool = True
    online_lyrics: bool = True
    lyrics_visible: bool = True
    lyric_offset: float = 0.0
    lyric_font: str = "Microsoft YaHei UI"
    lyric_mode: str = "line"
    pet_size: float = 0.6
    character: str = "cat"
    task: str = ""
    task_id: str = ""
    pet_hotkey: str = "Ctrl+Alt+O"
    panel_hotkey: str = "Ctrl+Alt+P"
    greetings: bool = True
    quotes: bool = True
    reminder_minutes: int = 45
    weather: bool = True
    performance: bool = True
    city: str = "北京"
    latitude: float = 39.9042
    longitude: float = 116.4074

    @classmethod
    def read(cls, raw: object) -> "Settings":
        obj = cls()
        if not isinstance(raw, dict):
            return obj
        for f in fields(cls):
            value = raw.get(f.name, getattr(obj, f.name))
            if f.name in ("focus", "short", "long", "reminder_minutes"):
                if type(value) is int and 1 <= value <= 180:
                    setattr(obj, f.name, value)
            elif f.name in ("walking", "sound", "music", "online_lyrics", "lyrics_visible",
                            "greetings", "quotes", "weather", "performance"):
                if type(value) is bool:
                    setattr(obj, f.name, value)
            elif f.name == "lyric_offset":
                if type(value) in (float, int) and math.isfinite(value):
                    obj.lyric_offset = max(-60.0, min(60.0, float(value)))
            elif f.name == "lyric_font":
                if isinstance(value, str) and value in FONTS:
                    obj.lyric_font = value
            elif f.name == "lyric_mode":
                if value in ("line", "word"):
                    obj.lyric_mode = value
            elif f.name == "pet_size":
                if type(value) in (float, int) and math.isfinite(value):
                    obj.pet_size = max(0.5, min(2.0, float(value)))
            elif f.name == "character":
                if isinstance(value, str) and value in ("cat", "frog", "puppy", "bunny", "milk_frog"):
                    obj.character = value
            elif f.name == "focus_presets":
                if isinstance(value, list):
                    cleaned: list[int] = []
                    for item in value:
                        if type(item) is int and 1 <= item <= 180 and item not in cleaned:
                            cleaned.append(item)
                        if len(cleaned) >= 12:
                            break
                    if cleaned:
                        obj.focus_presets = cleaned
            elif f.name in ("latitude", "longitude"):
                limit = 90 if f.name == "latitude" else 180
                if type(value) in (float, int) and math.isfinite(value) and -limit <= value <= limit:
                    setattr(obj, f.name, float(value))
            elif isinstance(value, str):
                setattr(obj, f.name, value[:120])
        return obj


@dataclass(frozen=True)
class Completion:
    phase: str
    seconds: float


FONTS = {
    "Microsoft YaHei UI": "微软雅黑",
    "Microsoft YaHei": "微软雅黑 (旧)",
    "SimSun": "宋体",
    "SimHei": "黑体",
    "KaiTi": "楷体",
    "FangSong": "仿宋",
    "DengXian": "等线",
}


def star_size(seconds: float) -> str:
    if seconds < 600:
        return "small"
    if seconds <= 1500:
        return "medium"
    return "large"


@dataclass
class TaskItem:
    id: str
    name: str
    category: str = ""
    created_at: str = ""
    deadline: str = ""
    done: bool = False
    focus_seconds: float = 0.0

    @classmethod
    def create(cls, name: str, category: str = "", deadline: str = "") -> "TaskItem":
        return cls(id=uuid.uuid4().hex[:12], name=name[:120], category=category[:40],
                   created_at=date.today().isoformat(), deadline=deadline)


class Pomodoro:
    """A deadline-based clock. Next intervals wait for explicit user input."""

    def __init__(self, settings: Settings, clock: Callable[[], float] = time.monotonic,
                 completed: int = 0):
        self.settings = settings
        self.clock = clock
        self.phase = "focus"
        self.state = "ready"
        self.completed = completed
        self.duration = settings.focus * 60.0
        self.remaining = self.duration
        self.deadline = 0.0

    @property
    def seconds(self) -> int:
        value = self.deadline - self.clock() if self.state == "running" else self.remaining
        return max(0, math.ceil(value))

    @property
    def progress(self) -> float:
        return max(0.0, min(1.0, 1 - self.seconds / self.duration))

    def start(self) -> None:
        if self.state != "running":
            self.deadline = self.clock() + self.remaining
            self.state = "running"

    def pause(self) -> Completion | None:
        result = self.tick()
        if self.state == "running":
            self.remaining = max(0.0, self.deadline - self.clock())
            self.state = "paused"
        return result

    def reset(self, phase: str | None = None) -> None:
        if phase is not None:
            if phase not in ("focus", "short", "long"):
                raise ValueError("Unknown timer phase")
            self.phase = phase
        self.state = "ready"
        self.duration = getattr(self.settings, self.phase) * 60.0
        self.remaining = self.duration

    def tick(self) -> Completion | None:
        if self.state != "running" or self.clock() < self.deadline:
            return None
        result = Completion(self.phase, self.duration)
        if self.phase == "focus":
            self.completed += 1
            self.reset("long" if self.completed % 4 == 0 else "short")
        else:
            self.reset("focus")
        return result


class Store:
    def __init__(self, folder: Path):
        self.folder = folder
        self.path = folder / "state.json"
        self.warning = ""
        self.settings = Settings()
        self.days: dict[str, dict] = {}
        self.completed = 0
        self.treats = 3
        self.stars: list[dict] = []
        self.tasks: list[TaskItem] = []
        self.position: list[int] | None = None
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("Not an object")
            self.settings = Settings.read(raw.get("settings"))
            for key in ("completed", "treats"):
                value = raw.get(key, getattr(self, key))
                if type(value) is int and 0 <= value <= 10_000_000:
                    setattr(self, key, value)
            days = raw.get("days", {})
            if isinstance(days, dict):
                for key, value in days.items():
                    if (isinstance(key, str) and isinstance(value, dict)
                            and type(value.get("count")) is int
                            and type(value.get("minutes")) in (int, float)
                            and value["count"] >= 0
                            and math.isfinite(value["minutes"]) and value["minutes"] >= 0):
                        entry = {"count": value["count"], "minutes": value["minutes"]}
                        rest = value.get("rest")
                        if type(rest) in (int, float) and math.isfinite(rest) and rest >= 0:
                            entry["rest"] = float(rest)
                        self.days[key] = entry
            pos = raw.get("position")
            if isinstance(pos, list) and len(pos) == 2 and all(type(x) is int for x in pos):
                self.position = pos
            stars = raw.get("stars", [])
            if isinstance(stars, list):
                for s in stars:
                    if isinstance(s, dict) and isinstance(s.get("date"), str):
                        dur = s.get("duration", 0)
                        if type(dur) in (int, float) and math.isfinite(dur) and dur > 0:
                            star = {"date": s["date"][:10], "duration": float(dur),
                                    "size": star_size(dur), "task": str(s.get("task", ""))[:120]}
                            if isinstance(s.get("task_id"), str):
                                star["task_id"] = s["task_id"][:120]
                                star["category"] = str(s.get("category", ""))[:40]
                            self.stars.append(star)
            tasks = raw.get("tasks", [])
            if isinstance(tasks, list):
                for t in tasks:
                    if isinstance(t, dict) and isinstance(t.get("id"), str) and isinstance(t.get("name"), str):
                        self.tasks.append(TaskItem(
                            id=t["id"], name=t["name"][:120], category=str(t.get("category", ""))[:40],
                            created_at=str(t.get("created_at", ""))[:10], deadline=str(t.get("deadline", ""))[:10],
                            done=bool(t.get("done", False)),
                            focus_seconds=float(t.get("focus_seconds", 0)) if type(t.get("focus_seconds")) in (int, float) else 0,
                        ))
        except (ValueError, OSError, TypeError):
            backup = self.path.with_name(f"state.damaged-{datetime.now():%Y%m%d-%H%M%S-%f}.json")
            self.path.replace(backup)
            self.warning = "旧记录无法读取，已备份；这次从新记录开始。"

    def today(self) -> dict:
        return self.days.get(date.today().isoformat(), {"count": 0, "minutes": 0})

    def reward(self, event: Completion, task: TaskItem | None = None, note: str | None = None) -> None:
        if event.phase != "focus":
            return
        key = date.today().isoformat()
        entry = self.days.setdefault(key, {"count": 0, "minutes": 0})
        entry["count"] += 1
        entry["minutes"] += event.seconds / 60
        self.completed += 1
        self.treats += 1
        if task:
            task.focus_seconds += event.seconds
        self.stars.append({"date": key, "duration": event.seconds,
                           "size": star_size(event.seconds),
                           "task": task.name if task else (self.settings.task if note is None else note)[:120],
                           "task_id": task.id if task else "",
                           "category": task.category if task else ""})

    def add_rest(self, seconds: float) -> None:
        """Record rest time (in minutes) for today."""
        if seconds <= 0:
            return
        key = date.today().isoformat()
        entry = self.days.setdefault(key, {"count": 0, "minutes": 0})
        entry["rest"] = entry.get("rest", 0) + seconds / 60

    def add_task(self, name: str, category: str = "", deadline: str = "") -> TaskItem:
        task = TaskItem.create(name, category, deadline)
        self.tasks.append(task)
        return task

    def set_task_done(self, task_id: str, done: bool) -> None:
        for t in self.tasks:
            if t.id == task_id:
                t.done = done
                break

    def delete_task(self, task_id: str) -> None:
        self.tasks = [t for t in self.tasks if t.id != task_id]

    def stars_in_range(self, start: date, end: date) -> list[dict]:
        return [s for s in self.stars if start.isoformat() <= s["date"] <= end.isoformat()]

    def task_focus_pie(self) -> list[tuple[str, float]]:
        """Return (label, seconds) pairs for pie chart."""
        buckets: dict[str, float] = {}
        for t in self.tasks:
            if t.focus_seconds > 0:
                key = t.category or t.name or "未分类"
                buckets[key] = buckets.get(key, 0) + t.focus_seconds
        ids = {t.id for t in self.tasks}
        names = {t.name for t in self.tasks}
        for star in self.stars:
            if "task_id" in star:
                if star["task_id"] in ids:
                    continue  # Already counted in the task's accumulated time.
                label = (star["category"] or star["task"]) if star["task_id"] else "其他"
            else:
                if star["task"] and star["task"] in names:
                    continue  # Older records linked focus time by name.
                label = "其他"
            buckets[label] = buckets.get(label, 0) + star["duration"]
        return sorted(buckets.items(), key=lambda x: -x[1])

    def save(self) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        raw = {"version": 2, "settings": asdict(self.settings), "days": self.days,
               "completed": self.completed, "treats": self.treats, "position": self.position,
               "stars": self.stars, "tasks": [asdict(t) for t in self.tasks]}
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)
