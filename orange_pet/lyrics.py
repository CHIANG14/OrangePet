"""Timestamped lyrics and playback estimation; no GUI or network required."""
from __future__ import annotations

import bisect
import re
import unicodedata
from dataclasses import dataclass

STAMP = re.compile(r"\[(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?\]")


@dataclass(frozen=True)
class LyricLine:
    seconds: float
    text: str


class Lyrics:
    def __init__(self, lines: list[LyricLine]):
        # Translation and original lines sharing a timestamp belong together.
        grouped: dict[float, list[str]] = {}
        for line in lines:
            values = grouped.setdefault(line.seconds, [])
            if line.text and line.text not in values:
                values.append(line.text)
        self.lines = [LyricLine(t, " / ".join(v)) for t, v in sorted(grouped.items())]
        self.times = [line.seconds for line in self.lines]

    @classmethod
    def parse(cls, text: str) -> "Lyrics":
        offset_match = re.search(r"\[offset:\s*([+-]?\d+)\]", text, re.I)
        offset = int(offset_match.group(1)) / 1000 if offset_match else 0.0
        lines = []
        for row in text.splitlines():
            stamps = list(STAMP.finditer(row))
            if not stamps:
                continue
            content = row[stamps[-1].end():].strip()
            content = re.sub(r"<\d+:\d+(?:\.\d+)?>", "", content)
            for stamp in stamps:
                minutes, seconds, fraction = stamp.groups()
                if int(seconds) >= 60:
                    continue
                value = int(minutes) * 60 + int(seconds)
                if fraction:
                    value += int(fraction) / (10 ** len(fraction))
                # Positive LRC offset advances the words; matches the UI offset.
                lines.append(LyricLine(value - offset, content))
        return cls(lines)

    def at(self, position: float, offset: float = 0.0) -> tuple[str, str]:
        index = bisect.bisect_right(self.times, position + offset) - 1
        current = self.lines[index].text if index >= 0 else ""
        following = self.lines[index + 1].text if index + 1 < len(self.lines) else ""
        return current, following

    def at_detail(self, position: float, offset: float = 0.0) -> tuple[str, str, int, int]:
        """Return (current_text, following_text, char_index, total_chars) for word mode."""
        index = bisect.bisect_right(self.times, position + offset) - 1
        if index < 0:
            following = self.lines[0].text if self.lines else ""
            return "", following, 0, 0
        current = self.lines[index].text
        following = self.lines[index + 1].text if index + 1 < len(self.lines) else ""
        line_start = self.times[index]
        line_end = self.times[index + 1] if index + 1 < len(self.times) else line_start + 8
        line_duration = max(0.5, line_end - line_start)
        elapsed = max(0, position + offset - line_start)
        total = max(1, len(current))
        char_index = min(total - 1, int(elapsed / line_duration * total))
        return current, following, char_index, total


def normalize_name(value: str) -> str:
    """Fold width, case and punctuation so metadata variants still match."""
    return "".join(c for c in unicodedata.normalize("NFKC", value).casefold() if c.isalnum())


ARTIST_SPLIT = re.compile(r"\s+[—–－]\s+|\s+-\s+|\s*/\s*|\s*、\s*|\s*&\s*|\s*;\s*|\s*,\s*")


def artist_candidates(artist: str, album: str = "") -> list[str]:
    """Return plausible artist names from the possibly dirty player metadata.

    Apple Music for Windows sometimes reports the artist as
    ``赵雷 — 吉姆餐厅`` (artist — album) instead of just ``赵雷``; sending that
    whole string to LRCLIB never matches.  Split on common separators and put
    the individual names first while keeping the original string as a last try.
    The album is skipped when it shows up as one of the segments.
    """
    artist = " ".join(artist.split())
    if not artist:
        return []
    album_key = normalize_name(album)
    result = []
    for part in (segment.strip() for segment in ARTIST_SPLIT.split(artist)):
        if not part:
            continue
        if album_key and normalize_name(part) == album_key:
            continue
        if part not in result:
            result.append(part)
    if artist not in result:
        result.append(artist)
    return result


def _same_artist(left: str, right: str) -> bool:
    left, right = normalize_name(left), normalize_name(right)
    return bool(left and right) and (left == right or left in right or right in left)


def pick_synced(items, title: str, artist: str, duration: float) -> str:
    """Pick the synced lyrics most likely to belong to the playing track.

    LRCLIB search results often disagree on punctuation, featured artists or
    duration by a second or two.  Score every titled match and only accept a
    confident winner instead of demanding an exact string match.
    """
    wanted_title = normalize_name(title)
    if not wanted_title or not isinstance(items, list):
        return ""
    best, best_score = "", 0
    for item in items:
        if not isinstance(item, dict) or not item.get("syncedLyrics"):
            continue
        item_title = normalize_name(str(item.get("trackName") or ""))
        if not item_title:
            continue
        if item_title == wanted_title:
            score = 4
        elif wanted_title in item_title or item_title in wanted_title:
            score = 2
        else:
            continue
        item_artist = str(item.get("artistName") or "")
        if item_artist and artist:
            if _same_artist(item_artist, artist):
                score += 4 if normalize_name(item_artist) == normalize_name(artist) else 2
            else:
                score -= 1
        item_duration = item.get("duration")
        if duration and isinstance(item_duration, (int, float)):
            gap = abs(float(item_duration) - duration)
            if gap <= 2:
                score += 3
            elif gap <= 5:
                score += 1
            elif gap > 12:
                score -= 2
        if score > best_score:
            best, best_score = item["syncedLyrics"], score
    # An exact title alone (artist missing or different) is still the best clue
    # we have; a containment match needs artist or duration support on top.
    return best if best_score >= 3 else ""


@dataclass(frozen=True)
class TimelineProgress:
    position: float
    duration: float
    tracking: bool


class TimelineStabilizer:
    """Keep a playback clock when the player's SMTC timeline is unreliable.

    Apple Music for Windows in particular often reports a zero end time and a
    stale or zero position.  The stabilizer anchors on the last meaningful
    position, advances it in wall time while the player is playing, freezes it
    while paused and re-syncs when the player reports a genuinely new non-zero
    position (a seek or fresh sample).  This keeps line lyrics moving even when
    the raw timeline cannot be trusted.
    """

    def __init__(self):
        self.reset()

    def reset(self):
        self.key = ""
        self.position = 0.0
        self.sampled_at = 0.0
        self.reported = 0.0
        self.duration = 0.0
        self.playing = False

    def update(self, key: str, position: float, duration: float,
               playing: bool, now: float) -> TimelineProgress:
        position = max(0.0, float(position))
        duration = max(0.0, float(duration))
        if not key:
            self.reset()
            return TimelineProgress(0.0, 0.0, False)
        if key != self.key:
            self.key = key
            self.position = position
            self.sampled_at = now
            self.reported = position
            self.duration = duration
            self.playing = playing
            return TimelineProgress(position, duration, True)
        elapsed = now - self.sampled_at if self.playing else 0.0
        estimate = self.position + elapsed
        if self.duration > 0:
            estimate = min(self.duration, estimate)
        if abs(position - self.reported) >= 0.4:
            if position == 0.0 and not playing and self.reported > 1.0:
                # Rewound to the start while paused.
                estimate = 0.0
            elif position > 0 and abs(position - estimate) > 1.5:
                # The player supplied a fresh position that disagrees with the
                # estimate: trust it so seeks stay in sync.
                estimate = position
        if playing and not self.playing and self.duration > 0 and estimate >= self.duration - 1.0:
            # Pressing play at the end restarts the track from its position.
            estimate = position
        self.position = estimate
        self.sampled_at = now
        self.reported = position
        if duration > 0:
            self.duration = duration
        self.playing = playing
        return TimelineProgress(estimate, self.duration, True)


@dataclass(frozen=True)
class MediaState:
    title: str = ""
    artist: str = ""
    album: str = ""
    source: str = ""
    position: float = 0.0
    duration: float = 0.0
    playing: bool = False
    sampled_at: float = 0.0
    timeline: bool = False
    error: str = ""

    @property
    def key(self) -> str:
        return "\x1f".join((self.source, self.title, self.artist, self.album)) if self.title else ""

    def position_at(self, now: float) -> float:
        value = self.position + (max(0, now - self.sampled_at) if self.playing and self.timeline else 0)
        return min(self.duration, value) if self.duration > 0 else max(0, value)
