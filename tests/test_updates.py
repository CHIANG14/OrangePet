import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import patch

from orange_pet.updates import (
    RESULT_FILE, Release, UpdateError, allowed_url, apply_update, check_release, download,
    release_from_json, repository_name,
)


class GitHubReleaseTests(unittest.TestCase):
    def test_public_repo_without_stable_release_has_clear_status(self):
        missing = HTTPError("https://api.github.com/", 404, "Not Found", {}, None)
        with patch("orange_pet.updates._open", side_effect=[missing, io.BytesIO(b"{}")]):
            with self.assertRaisesRegex(UpdateError, "已连接仓库，暂未发布正式版本"):
                check_release("demo/pet")

    def test_missing_repo_is_distinct_from_empty_release_list(self):
        missing = HTTPError("https://api.github.com/", 404, "Not Found", {}, None)
        with patch("orange_pet.updates._open", side_effect=[missing, missing]):
            with self.assertRaisesRegex(UpdateError, "找不到公开仓库"):
                check_release("demo/pet")

    def test_repository_accepts_only_github_public_repo_syntax(self):
        self.assertEqual(repository_name("https://github.com/demo/OrangePet.git"), "demo/OrangePet")
        for value in ("demo@example.com", "https://example.org/demo/pet",
                      "https://github.com/demo/pet/releases", "demo/../pet"):
            with self.subTest(value=value), self.assertRaises(UpdateError):
                repository_name(value)

    def test_latest_stable_tag_uses_numeric_version_comparison(self):
        payload = {"tag_name": "v1.10.0", "body": "说明", "assets": [
            {"name": "OrangePet.exe", "state": "uploaded", "size": 1024, "digest": "sha256:" + "a" * 64}
        ]}
        release = release_from_json(payload, "demo/pet", "1.9.9")
        self.assertEqual(release.url, "https://github.com/demo/pet/releases/download/v1.10.0/OrangePet.exe")
        self.assertEqual(release.sha256, "a" * 64)
        self.assertIsNone(release_from_json(payload, "demo/pet", "1.10.1"))
        with self.assertRaises(UpdateError):
            release_from_json(dict(payload, prerelease=True), "demo/pet", "1.9.9")
        del payload["assets"][0]["digest"]
        with self.assertRaises(UpdateError):
            release_from_json(payload, "demo/pet", "1.9.9")

    def test_redirects_stay_on_allowed_https_hosts(self):
        self.assertTrue(allowed_url("https://release-assets.githubusercontent.com/a?signature=x"))
        self.assertFalse(allowed_url("http://github.com/demo/pet"))
        self.assertFalse(allowed_url("https://github.com@elsewhere.test/file"))


class UpdateFilesTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.data = self.root / "data"
        self.data.mkdir()
        (self.data / "state.json").write_text('{"untouched": true}', encoding="utf-8")
        self.stage = self.root / ".orangepet-update-test"
        self.stage.mkdir()
        self.old = b"MZ original executable fixture"
        self.new = b"MZ upgraded executable fixture"
        self.digest = hashlib.sha256(self.new).hexdigest()
        self.target = self.root / "My pet.exe"
        self.worker = self.stage / "worker.exe"
        self.backup = self.root / "My pet.exe.previous"
        self.target.write_bytes(self.old)
        self.worker.write_bytes(self.old)
        (self.stage / "job.json").write_text(json.dumps({
            "target": self.target.name, "data_dir": str(self.data),
            "size": len(self.new), "sha256": self.digest, "tag": "v99.0.0",
        }), encoding="utf-8")

    def test_download_verifies_digest_and_size(self):
        release = Release("v99.0.0", "", "https://github.com/demo/pet", len(self.new), self.digest)
        with patch("orange_pet.updates._open", return_value=io.BytesIO(self.new)):
            download(release, self.stage / "incoming.exe", lambda percent: None)
        self.assertEqual((self.stage / "incoming.exe").read_bytes(), self.new)
        with patch("orange_pet.updates._open", return_value=io.BytesIO(b"MZ truncated")):
            with self.assertRaises(UpdateError):
                download(release, self.stage / "bad.exe", lambda percent: None)

    def test_replacement_preserves_backup_and_user_state(self):
        (self.stage / "incoming.exe").write_bytes(self.new)
        with patch("orange_pet.updates.launch_executable") as launch:
            self.assertEqual(apply_update(self.worker), 0)
        launch.assert_called_once_with(self.target, "--data-dir", str(self.data))
        self.assertEqual(self.target.read_bytes(), self.new)
        self.assertEqual(self.backup.read_bytes(), self.old)
        self.assertEqual((self.data / "state.json").read_text(), '{"untouched": true}')

    def test_failed_launch_restores_previous_executable(self):
        (self.stage / "incoming.exe").write_bytes(self.new)
        with patch("orange_pet.updates.launch_executable", side_effect=[OSError("launch failed"), None]):
            self.assertEqual(apply_update(self.worker), 1)
        self.assertEqual(self.target.read_bytes(), self.old)
        self.assertFalse(json.loads((self.data / RESULT_FILE).read_text(encoding="utf-8"))["ok"])

    def test_transient_windows_sharing_error_retries_restart(self):
        (self.stage / "incoming.exe").write_bytes(self.new)
        error = OSError("temporarily occupied")
        error.winerror = 32
        with (patch("orange_pet.updates.launch_executable", side_effect=[error, None]) as launch,
              patch("orange_pet.updates.time.sleep")):
            self.assertEqual(apply_update(self.worker), 0)
        self.assertEqual(launch.call_count, 2)
        self.assertEqual(self.target.read_bytes(), self.new)

    def test_changed_download_does_not_replace_original(self):
        (self.stage / "incoming.exe").write_bytes(b"MZ modified")
        with patch("orange_pet.updates.launch_executable"):
            self.assertEqual(apply_update(self.worker), 1)
        self.assertEqual(self.target.read_bytes(), self.old)
        self.assertFalse(self.backup.exists())
