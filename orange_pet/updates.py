"""GitHub release verification and the Windows executable replacement worker."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from . import __version__

LOG = logging.getLogger(__name__)
ASSET = "OrangePet.exe"
RESULT_FILE = "update-result.json"
MAX_SIZE = 200 * 1024 * 1024
STAGE_PREFIX = ".orangepet-update-"
GITHUB_HOSTS = {
    "api.github.com", "github.com", "release-assets.githubusercontent.com",
    "objects.githubusercontent.com", "github-releases.githubusercontent.com",
}


class UpdateError(Exception):
    pass


@dataclass(frozen=True)
class Release:
    tag: str
    notes: str
    url: str
    size: int
    sha256: str


def repository_name(value: str) -> str:
    value = value.strip()
    if "://" in value:
        url = urlsplit(value)
        if url.scheme != "https" or url.netloc.lower() != "github.com" or url.query or url.fragment:
            raise UpdateError("请输入 GitHub 公开仓库地址。")
        value = url.path.strip("/")
    if value.endswith(".git"):
        value = value[:-4]
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_][A-Za-z0-9_.-]{0,79}", value):
        raise UpdateError("请输入用户名/仓库名，例如 owner/OrangePet。")
    return value


def version_key(value: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"v?(0|[1-9]\d{0,5})\.(0|[1-9]\d{0,5})\.(0|[1-9]\d{0,5})", value)
    if not match:
        raise UpdateError("发行标签应使用 v主版本.次版本.修订号，例如 v1.1.1。")
    return tuple(map(int, match.groups()))


def bundled_repository() -> str:
    root = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
    try:
        value = (root / "orange-pet-update-repository.txt").read_text(encoding="utf-8-sig")
        return repository_name(value)
    except (OSError, ValueError, UpdateError):
        return ""


def release_from_json(payload: object, repo: str, current=__version__) -> Release | None:
    if not isinstance(payload, dict) or payload.get("draft") or payload.get("prerelease"):
        raise UpdateError("没有可用的正式版本。")
    tag = payload.get("tag_name")
    if not isinstance(tag, str):
        raise UpdateError("发行版本缺少有效标签。")
    if version_key(tag) <= version_key(current):
        return None
    assets = payload.get("assets")
    asset = next((item for item in assets if isinstance(item, dict) and item.get("name") == ASSET
                  and item.get("state") == "uploaded"), None) if isinstance(assets, list) else None
    if asset is None:
        raise UpdateError(f"{tag} 尚未上传 {ASSET}。")
    digest = asset.get("digest")
    if not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest):
        raise UpdateError("GitHub 尚未提供安装文件的 SHA-256，暂不能安装。")
    size = asset.get("size")
    if type(size) is not int or not 2 <= size <= MAX_SIZE:
        raise UpdateError("安装文件大小无效。")
    notes = payload.get("body")
    return Release(tag, notes.strip()[:2200] if isinstance(notes, str) else "",
                   f"https://github.com/{repo}/releases/download/{tag}/{ASSET}", size, digest[7:].lower())


def allowed_url(value: str) -> bool:
    try:
        url = urlsplit(value)
        return url.scheme == "https" and url.netloc.lower() in GITHUB_HOSTS
    except ValueError:
        return False


class GitHubRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not allowed_url(newurl):
            raise UpdateError("GitHub 返回了未预期的下载地址。")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open(url: str, accept: str):
    if not allowed_url(url):
        raise UpdateError("更新必须通过 GitHub HTTPS 下载。")
    request = Request(url, headers={"User-Agent": f"OrangePet/{__version__}", "Accept": accept})
    return build_opener(GitHubRedirects()).open(request, timeout=15)


def check_release(repo: str) -> Release | None:
    repo = repository_name(repo)
    api = f"https://api.github.com/repos/{repo}"
    try:
        with _open(f"{api}/releases/latest", "application/vnd.github+json") as response:
            body = response.read(2_000_001)
    except HTTPError as exc:
        if exc.code == 404:
            try:
                with _open(api, "application/vnd.github+json"):
                    pass
            except HTTPError as repo_error:
                if repo_error.code == 404:
                    raise UpdateError("找不到公开仓库，请检查仓库地址和可见性。") from repo_error
                if repo_error.code in (403, 429):
                    raise UpdateError("GitHub 暂时限制了查询，请稍后重试。") from repo_error
                raise
            raise UpdateError("已连接仓库，暂未发布正式版本。") from exc
        if exc.code in (403, 429):
            raise UpdateError("GitHub 暂时限制了查询，请稍后重试。") from exc
        raise
    if len(body) > 2_000_000:
        raise UpdateError("GitHub 返回的发行信息过大。")
    return release_from_json(json.loads(body), repo)


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_file(path: Path, size: int, digest: str) -> None:
    with path.open("rb") as stream:
        if stream.read(2) != b"MZ":
            raise UpdateError("下载内容不是 Windows 可执行文件。")
    if path.stat().st_size != size or file_hash(path) != digest:
        raise UpdateError("下载文件大小或 SHA-256 不符，已取消更新。")


def download(release: Release, path: Path, progress) -> None:
    digest = hashlib.sha256()
    count = 0
    last_percent = -1
    deadline = time.monotonic() + 300
    with _open(release.url, "application/octet-stream") as response, path.open("xb") as stream:
        while block := response.read(256 * 1024):
            count += len(block)
            if count > release.size or time.monotonic() > deadline:
                raise UpdateError("下载大小异常或超时，已取消更新。")
            digest.update(block)
            stream.write(block)
            percent = count * 100 // release.size
            if percent != last_percent:
                progress(percent)
                last_percent = percent
        stream.flush()
        os.fsync(stream.fileno())
    if count != release.size or digest.hexdigest() != release.sha256:
        raise UpdateError("下载未完成或 SHA-256 不符，已取消更新。")
    with path.open("rb") as stream:
        if stream.read(2) != b"MZ":
            raise UpdateError("下载内容不是 Windows 可执行文件。")


def write_json(path: Path, data: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def remove_stage(stage: Path) -> None:
    for name in ("incoming.exe", "worker.exe", "job.json", "job.tmp", "done"):
        try:
            (stage / name).unlink(missing_ok=True)
        except OSError:
            return
    try:
        stage.rmdir()
    except OSError:
        pass


def cleanup_stages(root: Path) -> None:
    for stage in root.glob(STAGE_PREFIX + "*"):
        try:
            if stage.is_dir() and not stage.is_symlink() and not stage.is_junction() and (
                (stage / "done").is_file() or time.time() - stage.stat().st_mtime > 86_400
            ):
                remove_stage(stage)
        except OSError:
            pass


def prepare_update(release: Release, target: Path, data_dir: Path, progress) -> Path:
    stage = Path(tempfile.mkdtemp(prefix=STAGE_PREFIX, dir=target.parent))
    try:
        download(release, stage / "incoming.exe", progress)
        shutil.copyfile(target, stage / "worker.exe")
        write_json(stage / "job.json", {"target": target.name, "data_dir": str(data_dir.resolve()),
                                         "size": release.size, "sha256": release.sha256, "tag": release.tag})
    except Exception:
        remove_stage(stage)
        raise
    return stage


def launch_executable(executable: Path, *arguments: str):
    return subprocess.Popen([str(executable), *arguments], cwd=executable.parent,
                            env={**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"},
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _backup_path(target: Path) -> Path:
    return target.with_name(target.name + ".previous")


def restart_after_replace(target: Path, data_dir: Path) -> None:
    deadline = time.monotonic() + 8
    while True:
        try:
            launch_executable(target, "--data-dir", str(data_dir))
            return
        except OSError as exc:
            # Windows or a file scanner can briefly hold a newly replaced EXE.
            if getattr(exc, "winerror", None) not in (5, 32, 33) or time.monotonic() >= deadline:
                raise
            time.sleep(0.3)


def apply_update(worker: Path) -> int:
    """Run from the separate copy after the running EXE releases its file lock."""
    stage = worker.parent
    if worker.name != "worker.exe" or not stage.name.startswith(STAGE_PREFIX):
        return 1
    data_dir = None
    target = None
    original_checked = False
    try:
        job = json.loads((stage / "job.json").read_text(encoding="utf-8"))
        name = job["target"]
        if (not isinstance(name, str) or not re.fullmatch(r"[^\\/:]+\.exe", name, re.IGNORECASE)
                or version_key(job["tag"]) <= version_key(__version__)):
            raise UpdateError("更新任务无效。")
        data_dir = Path(job["data_dir"])
        target = stage.parent / name
        if target.is_symlink() or file_hash(target) != file_hash(worker):
            raise UpdateError("当前 EXE 已变化，请重新检查更新。")
        original_stat = target.stat()
        original_checked = True
        incoming = stage / "incoming.exe"
        verify_file(incoming, job["size"], job["sha256"])
        backup = _backup_path(target)
        with tempfile.NamedTemporaryFile(dir=stage, delete=False) as copy:
            temporary_backup = Path(copy.name)
        try:
            shutil.copyfile(worker, temporary_backup)
            temporary_backup.replace(backup)
        finally:
            temporary_backup.unlink(missing_ok=True)
        deadline = time.monotonic() + 25
        while True:
            if (data_dir / "instance.lock").exists():
                if time.monotonic() >= deadline:
                    raise UpdateError("原程序尚未退出，未替换。请退出后重试。")
                time.sleep(0.25)
                continue
            current_stat = target.stat()
            if (current_stat.st_ino, current_stat.st_size, current_stat.st_mtime_ns) != (
                original_stat.st_ino, original_stat.st_size, original_stat.st_mtime_ns
            ):
                original_checked = False
                raise UpdateError("当前 EXE 已变化，请重新检查更新。")
            try:
                incoming.replace(target)
                break
            except PermissionError as exc:
                if time.monotonic() >= deadline:
                    raise UpdateError("原 EXE 仍被占用，未替换。请退出程序后重试。") from exc
                time.sleep(0.25)
        try:
            write_json(data_dir / RESULT_FILE, {"ok": True, "tag": job["tag"]})
            restart_after_replace(target, data_dir)
        except OSError as exc:
            backup.replace(target)
            error = getattr(exc, "winerror", None)
            message = "无法启动新版，已恢复上一版。"
            if error is not None:
                message += f" Windows 错误 {error}。"
            raise UpdateError(message) from exc
        return 0
    except Exception as exc:
        message = str(exc) if isinstance(exc, UpdateError) else "更新未能完成，请检查程序目录的写入权限。"
        if data_dir is not None:
            try:
                write_json(data_dir / RESULT_FILE, {"ok": False, "message": message})
            except OSError:
                pass
        if original_checked and target and target.is_file() and data_dir is not None:
            try:
                launch_executable(target, "--data-dir", str(data_dir))
            except OSError:
                pass
        return 1
    finally:
        try:
            (stage / "done").touch()
        except OSError:
            pass
