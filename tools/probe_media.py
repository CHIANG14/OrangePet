"""Read-only Windows media probe. Never changes playback or prints lyrics."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json


async def probe():
    import winrt.windows.foundation
    import winrt.windows.foundation.collections
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as Manager,
        GlobalSystemMediaTransportControlsSessionPlaybackStatus as Status,
        GlobalSystemMediaTransportControlsSession as Session,
    )

    manager = await asyncio.wait_for(Manager.request_async(), 8)
    sessions = list(manager.get_sessions())
    result = {"manager_ok": True, "session_count": len(sessions),
              "playing_enum": str(Status.PLAYING),
              "control_methods": {name: hasattr(Session, name) for name in (
                  "try_toggle_play_pause_async", "try_skip_previous_async", "try_skip_next_async")},
              "sessions": []}
    for session in sessions:
        properties = await asyncio.wait_for(session.try_get_media_properties_async(), 4)
        timeline = session.get_timeline_properties()
        info = session.get_playback_info()
        stamp = timeline.last_updated_time
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        result["sessions"].append({
            "source": session.source_app_user_model_id,
            "has_title": bool(properties.title), "has_artist": bool(properties.artist),
            "has_album": bool(properties.album_title),
            "playing": info.playback_status == Status.PLAYING,
            "position_seconds": timeline.position.total_seconds(),
            "end_seconds": timeline.end_time.total_seconds(),
            "timestamp_type": type(timeline.last_updated_time).__name__,
            "timestamp_age_seconds": (datetime.now(timezone.utc) - stamp).total_seconds(),
        })
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(probe())
