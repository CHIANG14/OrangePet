"""Read-only Apple Music / Windows media integration and optional LRCLIB lookup."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import queue
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from .lyrics import Lyrics, MediaState, TimelineStabilizer, artist_candidates, pick_synced

LOG = logging.getLogger(__name__)


def _is_apple_music(session) -> bool:
    try:
        ident = session.source_app_user_model_id.lower()
    except Exception:
        return False
    return "apple" in ident and "music" in ident


def choose_session(sessions, current, playing_status):
    """Follow the player that is actually playing; Apple Music wins ties.

    A stale Apple Music session used to hide the track another app was
    playing, which also meant lyrics were never requested.
    """
    statuses = []
    for session in sessions:
        try:
            playing = session.get_playback_info().playback_status == playing_status
        except Exception:
            playing = False
        statuses.append((session, playing))
    active = [session for session, playing in statuses if playing]
    apple_active = [session for session in active if _is_apple_music(session)]
    if apple_active:
        return apple_active[0]
    if current is not None:
        try:
            current_id = current.source_app_user_model_id
        except Exception:
            current_id = ""
        for session in active:
            try:
                if session.source_app_user_model_id == current_id:
                    return session
            except Exception:
                continue
    if active:
        return active[0]
    apple = [session for session, _ in statuses if _is_apple_music(session)]
    if apple:
        return apple[0]
    if current is not None:
        return current
    return statuses[0][0] if statuses else None


class MediaBridge(QObject):
    updated = Signal(object)
    command_result = Signal(str)

    def __init__(self):
        super().__init__()
        self.enabled = True
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.commands: queue.Queue = queue.Queue(maxsize=4)
        self.timeline = TimelineStabilizer()
        self.logged_key = ""

    def command(self, action: str, source: str):
        if action not in ("toggle", "previous", "next") or not source:
            return
        try:
            self.commands.put_nowait((action, source))
        except queue.Full:
            self.command_result.emit("操作太快，等等播放器。")

    def start(self):
        if self.thread is not None and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self._run, name="WindowsMedia", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()

    def _run(self):
        try:
            asyncio.run(self._poll())
        except Exception:
            LOG.exception("Media integration unavailable")
            self.updated.emit(MediaState(error="系统媒体连接暂不可用，可先体验演示或稍后重启。"))

    async def _poll(self):
        import winrt.windows.foundation  # noqa: F401 — required by projected return types
        import winrt.windows.foundation.collections  # noqa: F401
        from winrt.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionManager as Manager,
            GlobalSystemMediaTransportControlsSessionPlaybackStatus as Status,
        )

        manager = await Manager.request_async()
        while not self.stop_event.is_set():
            if not self.enabled:
                self.timeline.reset()
                await asyncio.sleep(0.65)
                continue
            try:
                sessions = list(manager.get_sessions())
                session = choose_session(sessions, manager.get_current_session(), Status.PLAYING)
                while not self.commands.empty():
                    action, source = self.commands.get_nowait()
                    target = next((s for s in sessions if s.source_app_user_model_id == source), None)
                    if target is None:
                        self.command_result.emit("播放器断开了，请重开。")
                        continue
                    methods = {"toggle": target.try_toggle_play_pause_async,
                               "previous": target.try_skip_previous_async,
                               "next": target.try_skip_next_async}
                    success = await asyncio.wait_for(methods[action](), 4.0)
                    if not success:
                        self.command_result.emit("播放器不支持这个操作。")
                if session is None:
                    self.timeline.reset()
                    self.updated.emit(MediaState())
                else:
                    source = session.source_app_user_model_id
                    title = artist = album = ""
                    try:
                        props = await asyncio.wait_for(session.try_get_media_properties_async(), 4.0)
                        title = props.title or ""
                        artist = props.artist or ""
                        album = props.album_title or ""
                    except Exception:
                        # A slow or unsupported properties call must not hide
                        # the timeline and the play state from the rest of the
                        # pipeline; the next poll can try again.
                        LOG.debug("Media properties unavailable for %s", source, exc_info=True)
                    try:
                        playing = session.get_playback_info().playback_status == Status.PLAYING
                    except Exception:
                        playing = False
                    position = duration = 0.0
                    try:
                        timeline = session.get_timeline_properties()
                        position = timeline.position.total_seconds()
                        duration = timeline.end_time.total_seconds()
                        if playing and duration > 0:
                            # last_updated_time lets us age the reported
                            # position a little; the stabilizer smooths the rest.
                            stamp = timeline.last_updated_time
                            if stamp.tzinfo is None:
                                stamp = stamp.replace(tzinfo=timezone.utc)
                            elapsed = (datetime.now(timezone.utc) - stamp).total_seconds()
                            if 0 <= elapsed <= duration + 5:
                                position += elapsed
                    except Exception:
                        LOG.debug("Media timeline unavailable for %s", source, exc_info=True)
                    now = time.monotonic()
                    key = "\x1f".join((source, title, artist, album)) if title else ""
                    progress = self.timeline.update(key, position, duration, playing, now)
                    state = MediaState(
                        title=title, artist=artist, album=album, source=source,
                        position=max(0.0, progress.position),
                        duration=max(0.0, progress.duration),
                        playing=playing, sampled_at=now, timeline=progress.tracking,
                    )
                    self.updated.emit(state)
                    if state.key != self.logged_key:
                        self.logged_key = state.key
                        LOG.info("Media track %r / %r [%s] playing=%s position=%.1f duration=%.1f",
                                 title, artist, source, playing, state.position, state.duration)
            except Exception:
                LOG.debug("Media session changed or unavailable", exc_info=True)
                self.timeline.reset()
                self.updated.emit(MediaState(error="正在重新连接播放器…"))
            await asyncio.sleep(0.65)


def track_id(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


class LyricLoader(QObject):
    loaded = Signal(str, str, str)

    def __init__(self, folder: Path):
        super().__init__()
        self.folder = folder
        self.requests: queue.Queue = queue.Queue(maxsize=1)
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, name="LyricLookup", daemon=True)
        self.cache_lock = threading.Lock()
        self.manual_keys = set()
        self.thread.start()

    def request(self, media: MediaState, online: bool):
        try:
            self.requests.get_nowait()
        except queue.Empty:
            pass
        self.requests.put_nowait((media, online))

    def path(self, key: str) -> Path:
        return self.folder / (track_id(key) + ".lrc")

    def save(self, key: str, text: str, manual=False):
        with self.cache_lock:
            if manual:
                self.manual_keys.add(key)
            elif key in self.manual_keys:
                return
            self.folder.mkdir(parents=True, exist_ok=True)
            target = self.path(key)
            temporary = target.with_suffix(".tmp")
            temporary.write_text(text, encoding="utf-8")
            temporary.replace(target)

    def _get_json(self, path: str, params: dict):
        url = "https://lrclib.net/api/" + path + "?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(url, headers={"User-Agent": "OrangePet/1.0 (Windows desktop companion)",
                                                       "Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=8) as response:
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ValueError("Response too large")
            return json.loads(raw)

    def _lookup(self, media: MediaState) -> str:
        if not media.title:
            return ""
        artists = artist_candidates(media.artist, media.album) or [media.artist]
        for artist in artists:
            content = self._lookup_artist(media, artist)
            if content:
                return content
        # Last resort: LRCLIB free-text search can still find a song when the
        # structured fields are mangled by the player.
        query = " ".join(part for part in (media.title, artists[0]) if part)
        try:
            items = self._get_json("search", {"q": query})
        except urllib.error.HTTPError:
            return ""
        return pick_synced(items, media.title, artists[0], media.duration)

    def _lookup_artist(self, media: MediaState, artist: str) -> str:
        base = {"track_name": media.title}
        if artist:
            base["artist_name"] = artist
        # Album and duration make the exact lookup strict; retry without them
        # because players often round the duration or use a different album
        # title (deluxe editions, compilations).  The get endpoint needs an
        # artist, so missing artist metadata goes straight to search.
        attempts = []
        if artist and media.album and media.duration > 0:
            attempts.append({**base, "album_name": media.album, "duration": round(media.duration)})
        if artist and media.duration > 0:
            attempts.append({**base, "duration": round(media.duration)})
        if artist:
            attempts.append(base)
        seen = set()
        for params in attempts:
            signature = tuple(sorted(params.items()))
            if signature in seen:
                continue
            seen.add(signature)
            try:
                item = self._get_json("get", params)
            except urllib.error.HTTPError as error:
                if error.code == 404:
                    continue
                raise
            if isinstance(item, dict) and item.get("syncedLyrics"):
                return item["syncedLyrics"]
        items = self._get_json("search", base)
        return pick_synced(items, media.title, artist, media.duration)

    def _run(self):
        while not self.stop_event.is_set():
            try:
                media, online = self.requests.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                path = self.path(media.key)
                if path.exists():
                    content = path.read_text(encoding="utf-8")
                    if Lyrics.parse(content).lines:
                        LOG.info("Lyrics for %r / %r: cache", media.title, media.artist)
                        self.loaded.emit(media.key, content, "本地歌词")
                        continue
                if not online:
                    LOG.info("Lyrics for %r / %r: online lookup disabled", media.title, media.artist)
                    self.loaded.emit(media.key, "", "可导入 LRC，或开启自动找歌词")
                    continue
                content = self._lookup(media)
                if content and Lyrics.parse(content).lines:
                    try:
                        self.save(media.key, content)
                    except OSError:
                        LOG.exception("Cannot cache lyrics")
                    LOG.info("Lyrics for %r / %r: found on LRCLIB", media.title, media.artist)
                    self.loaded.emit(media.key, content, "歌词来自 LRCLIB")
                else:
                    LOG.info("Lyrics for %r / %r: not found", media.title, media.artist)
                    self.loaded.emit(media.key, "", "未找到逐句歌词，可以导入 LRC")
            except Exception as error:
                LOG.info("Lyrics lookup failed for %r / %r: %s", media.title, media.artist, error)
                LOG.debug("Lyrics lookup traceback", exc_info=True)
                self.loaded.emit(media.key, "", "歌词服务暂不可用，可以导入 LRC")

    def stop(self):
        self.stop_event.set()
