import unittest

from orange_pet.hotkeys import GlobalHotkeys, parse_hotkey


class FakeApplication:
    def installNativeEventFilter(self, event_filter):
        self.event_filter = event_filter


class FakeUser32:
    """No OS hotkeys are touched by these conflict/rollback checks."""
    def __init__(self):
        self.registrations = {}
        self.reserved = set()

    def RegisterHotKey(self, window, identity, modifiers, virtual_key):
        binding = (modifiers, virtual_key)
        if binding in self.reserved or binding in self.registrations.values():
            return False
        self.registrations[identity] = binding
        return True

    def UnregisterHotKey(self, window, identity):
        return self.registrations.pop(identity, None) is not None


class HotkeyParsingTests(unittest.TestCase):
    def test_default_keys_use_ctrl_alt_and_norepeat(self):
        self.assertEqual(parse_hotkey("Ctrl+Alt+O"), (0x4003, ord("O")))
        self.assertEqual(parse_hotkey("Ctrl+Alt+P"), (0x4003, ord("P")))

    def test_number_function_and_shift_combinations(self):
        self.assertEqual(parse_hotkey("Alt+1"), (0x4001, ord("1")))
        self.assertEqual(parse_hotkey("Ctrl+Shift+F12"), (0x4006, 0x7B))

    def test_invalid_keys_and_chords_rejected(self):
        for key in ("", "A", "Shift+A", "Meta+A", "Ctrl+Space", "Ctrl+F13", "Ctrl+K, Ctrl+C"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                parse_hotkey(key)


class HotkeyTransactionTests(unittest.TestCase):
    def setUp(self):
        self.keys = GlobalHotkeys(FakeApplication(), lambda: None, lambda: None)
        self.native = FakeUser32()
        self.keys.user32 = self.native

    def tearDown(self):
        self.keys.clear()

    def test_conflict_on_second_binding_restores_both_old_shortcuts(self):
        self.assertTrue(self.keys.apply("Ctrl+Alt+O", "Ctrl+Alt+P")[0])
        original = self.native.registrations.copy()
        self.native.reserved.add(parse_hotkey("Ctrl+Alt+L"))
        ok, text = self.keys.apply("Ctrl+Alt+K", "Ctrl+Alt+L")
        self.assertFalse(ok)
        self.assertIn("占用", text)
        self.assertEqual(self.native.registrations, original)
        self.assertEqual(self.keys.registered, original)

    def test_swapping_shortcuts_succeeds(self):
        self.keys.apply("Ctrl+Alt+O", "Ctrl+Alt+P")
        self.assertTrue(self.keys.apply("Ctrl+Alt+P", "Ctrl+Alt+O")[0])
        self.assertEqual(self.native.registrations[self.keys.IDS[0]], parse_hotkey("Ctrl+Alt+P"))

    def test_duplicate_keys_leave_previous_shortcuts_untouched(self):
        self.keys.apply("Ctrl+Alt+O", "Ctrl+Alt+P")
        original = self.native.registrations.copy()
        self.assertFalse(self.keys.apply("Ctrl+Alt+K", "Ctrl+Alt+K")[0])
        self.assertEqual(self.native.registrations, original)

    def test_clear_unregisters_everything(self):
        self.keys.apply("Ctrl+Alt+O", "Ctrl+Alt+P")
        self.keys.clear()
        self.assertEqual(self.native.registrations, {})
        self.assertEqual(self.keys.registered, {})


if __name__ == "__main__":
    unittest.main()
