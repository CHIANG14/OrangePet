from __future__ import annotations

import json
import logging
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Qt, Signal
from PySide6.QtWidgets import QMessageBox

from . import __version__
from .updates import (
    RESULT_FILE, UpdateError, check_release, cleanup_stages, launch_executable,
    prepare_update, remove_stage, repository_name, version_key,
)

LOG = logging.getLogger(__name__)


class UpdateController(QObject):
    checked = Signal(object)
    downloaded = Signal(object)
    progress = Signal(int)
    failed = Signal(str)

    def __init__(self, companion):
        super().__init__(companion)
        self.c = companion
        self.busy = False
        self.checked.connect(self._checked)
        self.downloaded.connect(self._downloaded)
        self.progress.connect(self._progress)
        self.failed.connect(self._failed)

    @property
    def panel(self):
        return self.c.panel

    def startup(self):
        path = self.c.store.folder / RESULT_FILE
        try:
            result = json.loads(path.read_text(encoding="utf-8"))
            if result.get("ok") and version_key(result["tag"]) == version_key(__version__):
                status = f"已更新到 v{__version__}。"
            elif result.get("ok"):
                status = "实际版本与发布标签不符，请核对 Release 的 EXE。"
            else:
                status = str(result.get("message", "上次更新未完成。"))
            self.panel.update_status.setText(status)
            self.panel.footer.setText(status)
            path.unlink()
        except (OSError, ValueError, KeyError, TypeError, AttributeError, UpdateError):
            pass
        if getattr(sys, "frozen", False):
            QTimer.singleShot(3000, lambda: cleanup_stages(Path(sys.executable).resolve().parent))

    def _set_busy(self, busy: bool):
        self.busy = busy
        self.panel.check_update.setEnabled(not busy)
        self.panel.update_repo.setEnabled(not busy)

    def _background(self, action, signal):
        def run():
            try:
                signal.emit(action())
            except UpdateError as exc:
                self.failed.emit(str(exc))
            except Exception:
                LOG.info("Update operation failed", exc_info=True)
                self.failed.emit("更新未完成，请检查网络或程序目录的写入权限。")
        threading.Thread(target=run, name="OrangePetUpdate", daemon=True).start()

    def check(self):
        if self.busy:
            return
        try:
            repo = repository_name(self.panel.update_repo.text())
        except (ValueError, UpdateError) as exc:
            self.panel.update_status.setText(str(exc))
            self.panel.update_repo.setFocus()
            return
        self.panel.update_repo.setText(repo)
        self.c.store.settings.update_repository = repo
        self.c.save()
        self._set_busy(True)
        self.panel.update_status.setText(f"正在检查 {repo} 的正式发布…")
        self._background(lambda: check_release(repo), self.checked)

    def _checked(self, release):
        self._set_busy(False)
        if release is None:
            self.panel.update_status.setText(f"v{__version__} 已是最新版本。")
            return
        self.panel.update_status.setText(f"发现新版本 {release.tag}。")
        if not getattr(sys, "frozen", False) or sys.platform != "win32":
            self.panel.update_status.setText(f"发现 {release.tag}。请用 Windows EXE 版安装更新。")
            return
        dialog = QMessageBox(self.panel)
        dialog.setWindowTitle("发现橘子专注更新")
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setText(f"v{__version__} → {release.tag}（{release.size / 1024**2:.1f} MB）")
        repo = self.panel.update_repo.text()
        dialog.setInformativeText(f"来源：{repo}\n下载并校验后，程序会退出并启动新版。请确认你信任此仓库。")
        if release.notes:
            dialog.setDetailedText(release.notes)
        install = dialog.addButton("下载并安装", QMessageBox.ButtonRole.AcceptRole)
        cancel = dialog.addButton(QMessageBox.StandardButton.Cancel)
        dialog.setDefaultButton(cancel)
        dialog.exec()
        if dialog.clickedButton() is not install:
            return
        target = Path(sys.executable).resolve()
        self._set_busy(True)
        self.panel.update_status.setText("正在下载新版…")
        self._background(lambda: prepare_update(release, target, self.c.store.folder, self.progress.emit),
                         self.downloaded)

    def _progress(self, percent):
        self.panel.update_status.setText(f"正在下载新版 · {percent}%")

    def _failed(self, message):
        self._set_busy(False)
        self.panel.update_status.setText(message)

    def _downloaded(self, stage):
        if self.c.timer.state != "ready":
            answer = QMessageBox.question(self.panel, "安装更新",
                                          "安装会结束当前这轮计时。现在安装吗？",
                                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                          QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                remove_stage(stage)
                self._failed("已取消安装，当前计时继续。")
                return
        try:
            launch_executable(stage / "worker.exe", "--apply-update")
        except OSError:
            LOG.info("Cannot start update worker", exc_info=True)
            remove_stage(stage)
            self._failed("无法启动更新程序，当前版本仍可使用。")
            return
        self.c.quit()
