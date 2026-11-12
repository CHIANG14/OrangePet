"""Opt-in city-level Open-Meteo weather. No IP or device geolocation."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import queue
import threading
import urllib.parse
import urllib.request

from PySide6.QtCore import QObject, Signal


def weather_name(code):
    if code == 0:
        return "晴"
    if code in (1, 2):
        return "晴间多云"
    if code == 3:
        return "阴"
    if code in (45, 48):
        return "雾"
    if code in (51, 53, 55, 56, 57):
        return "毛毛雨"
    if code in (61, 63, 65, 66, 67, 80, 81, 82):
        return "雨"
    if code in (71, 73, 75, 77, 85, 86):
        return "雪"
    if code in (95, 96, 99):
        return "雷雨"
    return "天气变化中"


def weather_tip(data):
    current = data.get("current", {})
    code = current.get("weather_code", -1)
    temp = current.get("temperature_2m", 20)
    wind = current.get("wind_speed_10m", 0)
    if code in (95, 96, 99):
        return "雷雨了，先在室内待着吧。"
    if code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82):
        return "有雨，出门记得带伞。"
    if code in (71, 73, 75, 77, 85, 86):
        return "下雪了，穿暖慢慢走。"
    if temp <= 5:
        return "天冷了，记得加件衣服。"
    if temp >= 30:
        return "天热，记得喝水找阴凉。"
    if wind >= 30:
        return "风大，出门拢好外套。"
    if code in (45, 48):
        return "有雾，出门慢一点。"
    return "天气不错，出去走走吧。"


class WeatherWorker(QObject):
    result = Signal(str, object)
    failed = Signal(str, str)

    def __init__(self):
        super().__init__()
        self.jobs = queue.Queue(maxsize=2)
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True, name="Weather")
        self.thread.start()

    def request(self, kind, **kwargs):
        try:
            self.jobs.put_nowait((kind, kwargs))
        except queue.Full:
            self.failed.emit(kind, "正在查询，请稍候再试。")

    @staticmethod
    def get(url, params):
        request = urllib.request.Request(url + "?" + urllib.parse.urlencode(params),
                                         headers={"User-Agent": "OrangePet/1.0"})
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read(1_000_000))

    def _run(self):
        while not self.stop_event.is_set():
            try:
                kind, args = self.jobs.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                if kind == "cities":
                    data = self.get("https://geocoding-api.open-meteo.com/v1/search",
                                    {"name": args["query"], "count": 10, "language": "zh", "format": "json"})
                    data["query"] = args["query"]
                else:
                    data = self.get("https://api.open-meteo.com/v1/forecast", {
                        "latitude": args["latitude"], "longitude": args["longitude"],
                        "current": "temperature_2m,apparent_temperature,is_day,precipitation,weather_code,wind_speed_10m",
                        "daily": "temperature_2m_max,temperature_2m_min", "timezone": "auto", "forecast_days": 1,
                    })
                    data["city"] = args["city"]
                    data["location_key"] = args["location_key"]
                    data["fetched_at"] = datetime.now(timezone.utc).isoformat()
                self.result.emit(kind, data)
            except Exception:
                self.failed.emit(kind, "天气服务暂不可用，请稍后重试；其他功能不受影响。")

    def stop(self):
        self.stop_event.set()
