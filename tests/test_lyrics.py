import unittest

from orange_pet.lyrics import Lyrics, MediaState, TimelineStabilizer, artist_candidates, pick_synced


class LyricTests(unittest.TestCase):
    def test_timestamps_are_sorted_and_repeat_stanzas_are_expanded(self):
        lyrics = Lyrics.parse("[ar:Artist]\n[01:00.20]last\n[00:05.1][00:20.123]chorus\n[00:01]first")
        self.assertEqual(lyrics.times, [1.0, 5.1, 20.123, 60.2])
        self.assertEqual([x.text for x in lyrics.lines], ["first", "chorus", "chorus", "last"])

    def test_seek_backwards_and_exact_boundaries(self):
        lyrics = Lyrics.parse("[00:03]one\n[00:06]two\n[00:09]three")
        self.assertEqual(lyrics.at(0), ("", "one"))
        self.assertEqual(lyrics.at(3), ("one", "two"))
        self.assertEqual(lyrics.at(8.99), ("two", "three"))
        self.assertEqual(lyrics.at(100), ("three", ""))
        self.assertEqual(lyrics.at(4), ("one", "two"))

    def test_positive_file_offset_and_user_offset_advance_words(self):
        lyrics = Lyrics.parse("[offset:+1000]\n[00:05]first\n[00:08]next")
        self.assertEqual(lyrics.at(3.99), ("", "first"))
        self.assertEqual(lyrics.at(4), ("first", "next"))
        self.assertEqual(lyrics.at(3, offset=1), ("first", "next"))
        self.assertEqual(lyrics.at(4, offset=-1), ("", "first"))

    def test_negative_offset_delays_words(self):
        lyrics = Lyrics.parse("[offset:-500]\n[00:01.0]first")
        self.assertEqual(lyrics.at(1.49), ("", "first"))
        self.assertEqual(lyrics.at(1.5), ("first", ""))

    def test_translation_merges_same_timestamp_and_deduplicates_text(self):
        lyrics = Lyrics.parse("[00:01]Hello\n[00:01]你好\n[00:01]Hello")
        self.assertEqual(lyrics.at(1), ("Hello / 你好", ""))

    def test_blank_timestamp_clears_previous_line_during_interlude(self):
        lyrics = Lyrics.parse("[00:00]line\n[00:03]\n[00:10]next")
        self.assertEqual(lyrics.at(4), ("", "next"))

    def test_enhanced_lrc_word_timestamps_removed(self):
        lyrics = Lyrics.parse("[00:01]<00:01.00>hello <00:01.25>world")
        self.assertEqual(lyrics.at(2), ("hello world", ""))

    def test_invalid_timestamps_and_plain_text_cannot_be_mistaken_for_timed_lyrics(self):
        for text in ("ordinary untimed text", "[ar:artist]\n[ti:title]", "[00:61]invalid"):
            with self.subTest(text=text):
                self.assertEqual(Lyrics.parse(text).at(10), ("", ""))


class TimelineStabilizerTests(unittest.TestCase):
    def test_stuck_zero_position_still_advances(self):
        stabilizer = TimelineStabilizer()
        first = stabilizer.update("song", 0, 180, True, 100)
        later = stabilizer.update("song", 0, 180, True, 112)
        self.assertTrue(first.tracking)
        self.assertAlmostEqual(later.position, 12)
        self.assertEqual(later.duration, 180)

    def test_pause_freezes_and_resume_continues(self):
        stabilizer = TimelineStabilizer()
        stabilizer.update("song", 30, 180, True, 100)
        paused = stabilizer.update("song", 30, 180, False, 110)
        self.assertAlmostEqual(paused.position, 40)
        still = stabilizer.update("song", 30, 180, False, 140)
        self.assertAlmostEqual(still.position, 40)
        resumed = stabilizer.update("song", 40, 180, True, 140)
        self.assertAlmostEqual(resumed.position, 40)

    def test_fresh_seek_resyncs_the_clock(self):
        stabilizer = TimelineStabilizer()
        stabilizer.update("song", 10, 300, True, 100)
        stabilizer.update("song", 10, 300, True, 110)
        seek = stabilizer.update("song", 95, 300, True, 111)
        self.assertAlmostEqual(seek.position, 95)

    def test_new_track_resets_position_and_duration(self):
        stabilizer = TimelineStabilizer()
        stabilizer.update("a", 100, 300, True, 100)
        stabilizer.update("a", 100, 300, True, 120)
        other = stabilizer.update("b", 0, 200, True, 121)
        self.assertAlmostEqual(other.position, 0)
        self.assertEqual(other.duration, 200)

    def test_empty_key_stops_tracking(self):
        stabilizer = TimelineStabilizer()
        stabilizer.update("a", 5, 100, True, 1)
        self.assertFalse(stabilizer.update("", 0, 0, False, 2).tracking)


class ArtistCandidateTests(unittest.TestCase):
    def test_artist_album_concatenation_is_split(self):
        self.assertEqual(artist_candidates("赵雷 — 吉姆餐厅", "吉姆餐厅"),
                         ["赵雷", "赵雷 — 吉姆餐厅"])

    def test_multiple_artists_keep_full_string_as_fallback(self):
        self.assertEqual(artist_candidates("A / B"), ["A", "B", "A / B"])

    def test_plain_artist_is_unchanged(self):
        self.assertEqual(artist_candidates("周杰伦"), ["周杰伦"])

    def test_empty_artist_is_empty(self):
        self.assertEqual(artist_candidates("   "), [])


class LyricMatchTests(unittest.TestCase):
    def test_prefers_matching_artist_and_duration(self):
        items = [
            {"trackName": "晴天", "artistName": "某翻唱", "duration": 200, "syncedLyrics": "wrong"},
            {"trackName": "晴天", "artistName": "周杰伦", "duration": 269, "syncedLyrics": "right"},
        ]
        self.assertEqual(pick_synced(items, "晴天", "周杰伦", 269), "right")

    def test_accepts_title_containment_for_live_versions(self):
        items = [{"trackName": "晴天 (Live)", "artistName": "周杰伦",
                  "duration": 270, "syncedLyrics": "live"}]
        self.assertEqual(pick_synced(items, "晴天", "周杰伦", 269), "live")

    def test_rejects_unrelated_or_unsynced_entries(self):
        items = [
            {"trackName": "稻香", "artistName": "周杰伦", "duration": 223, "syncedLyrics": "other"},
            {"trackName": "晴天", "artistName": "其他歌手", "duration": 60, "syncedLyrics": "odd"},
            {"trackName": "晴天", "artistName": "周杰伦", "duration": 269, "syncedLyrics": ""},
        ]
        self.assertEqual(pick_synced(items, "晴天", "周杰伦", 269), "")

    def test_duration_tolerance_keeps_near_matches(self):
        items = [{"trackName": "晴天", "artistName": "周杰伦",
                  "duration": 272, "syncedLyrics": "near"}]
        self.assertEqual(pick_synced(items, "晴天", "周杰伦", 269), "near")


class MediaTimelineTests(unittest.TestCase):
    def test_running_timeline_extrapolates_and_caps_at_end(self):
        state = MediaState(position=20, duration=60, sampled_at=100, playing=True, timeline=True)
        self.assertEqual(state.position_at(104), 24)
        self.assertEqual(state.position_at(1000), 60)
        self.assertEqual(state.position_at(90), 20)

    def test_pause_does_not_extrapolate(self):
        state = MediaState(position=20, duration=60, sampled_at=100, playing=False, timeline=True)
        self.assertEqual(state.position_at(500), 20)

    def test_missing_timeline_does_not_fabricate_playback_progress(self):
        state = MediaState(position=0, sampled_at=100, playing=True, timeline=False)
        self.assertEqual(state.position_at(500), 0)

    def test_track_key_distinguishes_sources_and_albums(self):
        a = MediaState(title="Song", artist="Singer", album="Live", source="Apple")
        b = MediaState(title="Song", artist="Singer", album="Studio", source="Apple")
        c = MediaState(title="Song", artist="Singer", album="Live", source="Browser")
        self.assertNotEqual(a.key, b.key)
        self.assertNotEqual(a.key, c.key)
        self.assertEqual(MediaState(source="Apple").key, "")


if __name__ == "__main__":
    unittest.main()
