"""Background hardware monitoring: memory, disk, network and optional CPU/GPU temperature."""
from __future__ import annotations

import json
import logging
import math
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Signal

LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class PerfSnapshot:
    cpu_percent: float = 0.0
    cpu_temp: float | None = None
    gpu_temp: float | None = None
    gpu_name: str = ""
    memory_percent: float = 0.0
    memory_used_gb: float = 0.0
    memory_total_gb: float = 0.0
    disk_read_mb: float = 0.0
    disk_write_mb: float = 0.0
    net_up_kb: float = 0.0
    net_down_kb: float = 0.0
    temps_available: bool = False


class PerfMonitor(QObject):
    """Poll system metrics in a daemon thread and emit snapshots as Qt signals."""

    updated = Signal(object)

    def __init__(self):
        super().__init__()
        self.enabled = True
        self.stop_event = threading.Event()
        self._temp_wake = threading.Event()
        self.thread: threading.Thread | None = None
        self._psutil = None
        self._temperatures = (None, None, "", False)

    def start(self):
        if self.thread is not None:
            return
        try:
            import psutil  # noqa: F401
            self._psutil = psutil
        except ImportError:
            LOG.info("psutil not available, performance monitoring disabled")
            self.updated.emit(None)
            return
        self.thread = threading.Thread(target=self._run, name="PerfMonitor", daemon=True)
        self.thread.start()
        if sys.platform == "win32":
            threading.Thread(target=self._poll_temps, name="TemperatureMonitor", daemon=True).start()

    def stop(self):
        self.stop_event.set()
        self._temp_wake.set()

    def refresh_temperatures(self):
        self._temp_wake.set()

    def _run(self):
        psutil = self._psutil
        prev_disk = prev_net = None
        prev_time = time.monotonic()
        while not self.stop_event.wait(2.0):
            if not self.enabled:
                prev_disk = prev_net = None
                continue
            now = time.monotonic()
            elapsed = max(0.1, now - prev_time)
            try:
                cpu = psutil.cpu_percent(percpu=False)
                mem = psutil.virtual_memory()
                disk = psutil.disk_io_counters()
                net = psutil.net_io_counters()
                disk_read_rate = disk_write_rate = 0.0
                if disk and prev_disk:
                    disk_read_rate = max(0, (disk.read_bytes - prev_disk.read_bytes)) / elapsed / 1_048_576
                    disk_write_rate = max(0, (disk.write_bytes - prev_disk.write_bytes)) / elapsed / 1_048_576
                net_up = net_down = 0.0
                if net and prev_net:
                    net_up = max(0, (net.bytes_sent - prev_net.bytes_sent)) / elapsed / 1024
                    net_down = max(0, (net.bytes_recv - prev_net.bytes_recv)) / elapsed / 1024
                cpu_temp, gpu_temp, gpu_name, temps_ok = self._temperatures
                snap = PerfSnapshot(
                    cpu_percent=cpu,
                    cpu_temp=cpu_temp,
                    gpu_temp=gpu_temp,
                    gpu_name=gpu_name,
                    memory_percent=mem.percent,
                    memory_used_gb=mem.used / 1_073_741_824,
                    memory_total_gb=mem.total / 1_073_741_824,
                    disk_read_mb=disk_read_rate,
                    disk_write_mb=disk_write_rate,
                    net_up_kb=net_up,
                    net_down_kb=net_down,
                    temps_available=temps_ok,
                )
                if self.enabled and not self.stop_event.is_set():
                    self.updated.emit(snap)
                prev_disk = disk
                prev_net = net
                prev_time = now
            except Exception:
                LOG.debug("Perf poll failed", exc_info=True)

    def _poll_temps(self):
        while not self.stop_event.is_set():
            if self.enabled:
                self._temperatures = self._read_temps()
            self._temp_wake.wait(30 if self.enabled else 2)
            self._temp_wake.clear()

    def _read_wmi(self):
        windows = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        powershell = windows / "System32/WindowsPowerShell/v1.0/powershell.exe"
        script = """
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$sensors = foreach ($namespace in 'root/LibreHardwareMonitor', 'root/OpenHardwareMonitor') {
    Get-CimInstance -Namespace $namespace -ClassName Sensor -Filter "SensorType='Temperature'" -ErrorAction SilentlyContinue |
        Select-Object Name, Identifier, Value
}
ConvertTo-Json -InputObject @($sensors) -Compress
"""
        try:
            result = subprocess.run(
                [str(powershell), "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True, encoding="utf-8", errors="replace", timeout=6,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            items = json.loads(result.stdout.lstrip("\ufeff"))
        except (OSError, ValueError, subprocess.TimeoutExpired):
            return None, None
        if not isinstance(items, list):
            return None, None
        cpu = []
        gpu = []
        for item in items:
            if not isinstance(item, dict):
                continue
            value = item.get("Value")
            if type(value) not in (int, float) or not math.isfinite(value):
                continue
            identity = str(item.get("Identifier", "")).lower()
            if "gpu" in identity:
                gpu.append(value)
            elif "cpu" in identity:
                cpu.append(value)
        return max(cpu, default=None), max(gpu, default=None)

    def _read_temps(self) -> tuple[float | None, float | None, str, bool]:
        """Read named hardware sensors, leaving unsupported temperatures blank."""
        cpu_temp, gpu_temp = self._read_wmi()
        gpu_name = ""
        # Try NVIDIA GPU temperature via nvidia-smi
        if gpu_temp is None:
            try:
                result = subprocess.run("nvidia-smi --query-gpu=temperature.gpu,name --format=csv,noheader,nounits",
                                        capture_output=True, text=True, timeout=3,
                                        creationflags=subprocess.CREATE_NO_WINDOW)
                if result.returncode == 0 and result.stdout.strip():
                    parts = result.stdout.strip().split(",")
                    if len(parts) >= 2:
                        gpu_temp = float(parts[0].strip())
                        gpu_name = parts[1].strip()[:40]
            except Exception:
                pass
        return cpu_temp, gpu_temp, gpu_name, cpu_temp is not None or gpu_temp is not None
