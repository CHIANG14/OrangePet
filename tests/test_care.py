from datetime import datetime
import random
import unittest

from orange_pet.care import CareScheduler, ENCOURAGEMENT, GENTLE, GREETINGS, MESSAGE_COUNT, period
from orange_pet.model import Settings
from tests.test_model import Clock


class CareTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.settings = Settings(reminder_minutes=45)
        self.care = CareScheduler(self.settings, self.clock, random.Random(42))

    def test_local_hour_boundaries(self):
        expected = {0: "night", 4: "night", 5: "morning", 10: "morning", 11: "noon",
                    13: "noon", 14: "afternoon", 17: "afternoon", 18: "evening", 21: "evening",
                    22: "late", 23: "late"}
        for hour, slot in expected.items():
            with self.subTest(hour=hour):
                self.assertEqual(period(hour), slot)

    def test_welcome_uses_current_local_time_group(self):
        for hour, slot in ((8, "morning"), (12, "noon"), (19, "evening"), (23, "late")):
            with self.subTest(hour=hour):
                text = self.care.welcome(datetime(2026, 11, 11, hour))
                self.assertIn(text, GREETINGS[slot])

    def test_normal_reminders_obey_minute_interval(self):
        now = datetime(2026, 11, 11, 14)
        self.care.welcome(now)
        self.clock.advance(44 * 60 + 59)
        self.assertIsNone(self.care.due(now))
        self.clock.advance(1)
        self.assertIsInstance(self.care.due(now), str)
        self.assertIsNone(self.care.due(now))

    def test_crossing_period_can_remind_early_but_has_five_minute_cooldown(self):
        self.care.welcome(datetime(2026, 11, 11, 10, 59))
        self.clock.advance(299)
        self.assertIsNone(self.care.due(datetime(2026, 11, 11, 11, 3)))
        self.clock.advance(1)
        self.assertIn(self.care.due(datetime(2026, 11, 11, 11, 4)), GREETINGS["noon"])

    def test_busy_period_defers_message_without_consuming_it(self):
        self.care.welcome(datetime(2026, 11, 11, 8))
        self.clock.advance(3600)
        self.assertIsNone(self.care.due(datetime(2026, 11, 11, 9), busy=True))
        self.assertIsInstance(self.care.due(datetime(2026, 11, 11, 9), busy=False), str)
        self.assertIsNone(self.care.due(datetime(2026, 11, 11, 9), busy=False))

    def test_disabled_greetings_emit_nothing(self):
        self.settings.greetings = False
        self.clock.advance(100000)
        self.assertIsNone(self.care.due(datetime(2026, 11, 12, 12)))

    def test_same_time_period_next_day_is_new_greeting(self):
        self.care.welcome(datetime(2026, 11, 11, 8))
        self.clock.advance(86400)
        self.assertIn(self.care.due(datetime(2026, 11, 12, 8)), GREETINGS["morning"])

    def test_quote_toggle_removes_quotes_without_removing_gentle_messages(self):
        self.settings.quotes = False
        for _ in range(100):
            text = self.care.choose(datetime(2026, 11, 11, 15))
            self.assertIn(text, GREETINGS["afternoon"] + GENTLE)
            self.assertNotIn(text, ENCOURAGEMENT)

    def test_consecutive_messages_do_not_repeat(self):
        last = None
        for _ in range(100):
            text = self.care.choose(datetime(2026, 11, 11, 15))
            self.assertNotEqual(text, last)
            last = text

    def test_message_count_and_nonempty_groups(self):
        self.assertGreaterEqual(MESSAGE_COUNT, 90)
        self.assertEqual(MESSAGE_COUNT, sum(map(len, GREETINGS.values())) + len(GENTLE) + len(ENCOURAGEMENT))
        self.assertTrue(all(GREETINGS[group] for group in ("morning", "noon", "afternoon", "evening", "late", "night")))

    def test_messages_fit_the_small_speech_bubble(self):
        messages = [text for group in GREETINGS.values() for text in group] + GENTLE + ENCOURAGEMENT
        too_long = [text for text in messages if len(text) > 12]
        self.assertEqual(too_long, [])


if __name__ == "__main__":
    unittest.main()
