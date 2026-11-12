import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from orange_pet.model import Completion, Pomodoro, Settings, Store


class Clock:
    def __init__(self, value=1000.0):
        self.value = value

    def __call__(self):
        return self.value

    def advance(self, amount):
        self.value += amount


class TimerTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.settings = Settings(focus=1, short=2, long=3)
        self.timer = Pomodoro(self.settings, self.clock)

    def test_pause_resume_preserves_fractional_remaining_time(self):
        self.timer.start()
        self.clock.advance(17.25)
        self.assertIsNone(self.timer.pause())
        self.assertEqual(self.timer.state, "paused")
        self.assertAlmostEqual(self.timer.remaining, 42.75)
        self.clock.advance(500)
        self.assertEqual(self.timer.seconds, 43)
        self.timer.start()
        self.clock.advance(42.74)
        self.assertIsNone(self.timer.tick())
        self.clock.advance(0.02)
        self.assertEqual(self.timer.tick(), Completion("focus", 60))

    def test_pause_at_deadline_completes_instead_of_sticking_at_zero(self):
        self.timer.start()
        self.clock.advance(60)
        self.assertEqual(self.timer.pause(), Completion("focus", 60))
        self.assertEqual((self.timer.phase, self.timer.state), ("short", "ready"))
        self.assertEqual(self.timer.completed, 1)
        self.assertIsNone(self.timer.pause())

    def test_delayed_tick_gives_one_completion_and_waits_for_next_start(self):
        self.timer.start()
        self.clock.advance(24 * 3600)
        self.assertEqual(self.timer.seconds, 0)
        self.assertEqual(self.timer.tick(), Completion("focus", 60))
        for _ in range(5):
            self.clock.advance(10000)
            self.assertIsNone(self.timer.tick())
        self.assertEqual(self.timer.completed, 1)
        self.assertEqual(self.timer.seconds, 120)

    def test_fourth_focus_gets_long_break_and_breaks_do_not_count(self):
        for completed in range(1, 9):
            self.assertEqual(self.timer.phase, "focus")
            self.timer.start()
            self.clock.advance(60)
            self.timer.tick()
            expected_break = "long" if completed % 4 == 0 else "short"
            self.assertEqual(self.timer.phase, expected_break)
            self.assertEqual(self.timer.completed, completed)
            self.timer.start()
            self.clock.advance(getattr(self.settings, expected_break) * 60)
            self.timer.tick()
            self.assertEqual(self.timer.completed, completed)

    def test_completed_count_restores_cycle_on_restart(self):
        timer = Pomodoro(self.settings, self.clock, completed=7)
        timer.start()
        self.clock.advance(60)
        timer.tick()
        self.assertEqual((timer.completed, timer.phase), (8, "long"))

    def test_repeated_start_does_not_extend_running_deadline(self):
        self.timer.start()
        deadline = self.timer.deadline
        self.clock.advance(30)
        self.timer.start()
        self.assertEqual(self.timer.deadline, deadline)

    def test_settings_change_waits_until_reset_or_next_round(self):
        self.timer.start()
        self.clock.advance(10)
        self.settings.focus = 10
        self.settings.short = 3
        self.assertEqual(self.timer.seconds, 50)
        self.clock.advance(50)
        self.assertEqual(self.timer.tick(), Completion("focus", 60))
        self.assertEqual(self.timer.seconds, 180)
        self.timer.reset("focus")
        self.assertEqual(self.timer.seconds, 600)

    def test_reset_abandons_round_without_earning_completion(self):
        self.timer.start()
        self.clock.advance(40)
        self.timer.reset()
        self.assertEqual(self.timer.completed, 0)
        self.assertEqual(self.timer.seconds, 60)
        self.assertEqual(self.timer.progress, 0)
        self.clock.advance(1000)
        self.assertIsNone(self.timer.tick())

    def test_invalid_phase_cannot_modify_timer(self):
        with self.assertRaises(ValueError):
            self.timer.reset("invalid")
        self.assertEqual(self.timer.phase, "focus")


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_round_trip_preserves_preferences_rewards_and_pet_position(self):
        store = Store(self.folder)
        store.settings.task = "认真完成这一页"
        store.settings.focus = 35
        store.settings.music = False
        store.settings.lyrics_visible = False
        store.settings.character = "frog"
        store.settings.city = "杭州"
        store.settings.latitude = 30.25
        store.settings.longitude = 120.16
        store.settings.pet_hotkey = "Ctrl+Alt+K"
        store.settings.focus_presets = [10, 15, 25, 30, 45, 60, 90]
        store.position = [-500, 50]
        store.reward(Completion("focus", 2100))
        store.reward(Completion("short", 300))
        store.save()
        restored = Store(self.folder)
        self.assertEqual(restored.today(), {"count": 1, "minutes": 35})
        self.assertEqual((restored.completed, restored.treats), (1, 4))
        self.assertEqual(restored.settings.task, "认真完成这一页")
        self.assertEqual(restored.settings.city, "杭州")
        self.assertEqual(restored.settings.latitude, 30.25)
        self.assertEqual(restored.settings.pet_hotkey, "Ctrl+Alt+K")
        self.assertEqual(restored.settings.focus_presets, [10, 15, 25, 30, 45, 60, 90])
        self.assertFalse(restored.settings.music)
        self.assertFalse(restored.settings.lyrics_visible)
        self.assertEqual(restored.settings.character, "frog")
        self.assertEqual(restored.position, [-500, 50])
        self.assertFalse((self.folder / "state.tmp").exists())

    def test_corrupt_json_is_preserved_before_fresh_state_is_saved(self):
        damaged = b'{"settings": bad json'
        (self.folder / "state.json").write_bytes(damaged)
        restored = Store(self.folder)
        backups = list(self.folder.glob("state.damaged-*.json"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), damaged)
        self.assertTrue(restored.warning)
        restored.save()
        self.assertIsInstance(json.loads((self.folder / "state.json").read_text(encoding="utf-8")), dict)
        self.assertEqual(backups[0].read_bytes(), damaged)

    def test_non_object_json_is_backed_up(self):
        (self.folder / "state.json").write_text("[]", encoding="utf-8")
        self.assertTrue(Store(self.folder).warning)
        self.assertEqual(len(list(self.folder.glob("state.damaged-*.json"))), 1)

    def test_invalid_fields_are_rejected_without_crashing(self):
        raw = {
            "completed": True, "treats": -10, "position": [True, 2],
            "settings": {"focus": -3, "short": True, "long": 181, "music": "yes",
                         "lyric_offset": float("inf"), "latitude": 100, "longitude": -300,
                         "focus_presets": [10, "x", 0, 181, 15, 15, True, 30],
                         "task": "a" * 200},
            "days": {date.today().isoformat(): {"count": -1, "minutes": float("nan")},
                     "bad-type": {"count": True, "minutes": 5},
                     "valid": {"count": 2, "minutes": 50}},
        }
        (self.folder / "state.json").write_text(json.dumps(raw), encoding="utf-8")
        store = Store(self.folder)
        self.assertEqual((store.completed, store.treats, store.position), (0, 3, None))
        self.assertEqual((store.settings.focus, store.settings.short, store.settings.long), (25, 5, 15))
        self.assertEqual(store.settings.lyric_offset, 0)
        self.assertEqual(store.settings.latitude, 39.9042)
        self.assertEqual(store.settings.focus_presets, [10, 15, 30])
        self.assertEqual(len(store.settings.task), 120)
        self.assertEqual(store.days, {"valid": {"count": 2, "minutes": 50}})

    def test_state_save_creates_missing_data_directory(self):
        folder = self.folder / "a" / "b"
        store = Store(folder)
        store.save()
        self.assertTrue((folder / "state.json").is_file())

    def test_read_settings_clamps_lyric_offset_and_ignores_unknown_keys(self):
        settings = Settings.read({"lyric_offset": 123, "unknown": "nope"})
        self.assertEqual(settings.lyric_offset, 60)
        self.assertFalse(hasattr(settings, "unknown"))

    def test_focus_is_saved_under_selected_id_even_when_tasks_share_a_name(self):
        store = Store(self.folder)
        first = store.add_task("阅读", "学习")
        second = store.add_task("阅读", "工作")
        store.settings.task_id = second.id
        store.reward(Completion("focus", 1500), task=second)
        store.save()
        restored = Store(self.folder)
        self.assertEqual(restored.settings.task_id, second.id)
        self.assertEqual({t.id: t.focus_seconds for t in restored.tasks},
                         {first.id: 0, second.id: 1500})
        self.assertEqual(restored.task_focus_pie(), [("工作", 1500)])
        restored.delete_task(second.id)
        self.assertEqual(restored.task_focus_pie(), [("工作", 1500)])

    def test_unlinked_note_matching_existing_task_is_counted_as_other(self):
        store = Store(self.folder)
        store.add_task("阅读")
        store.reward(Completion("focus", 900), note="阅读")
        self.assertEqual(store.task_focus_pie(), [("其他", 900)])


if __name__ == "__main__":
    unittest.main()
