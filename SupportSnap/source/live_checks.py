"""Read a handful of local measurements after the user agrees."""

from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
from pkgutil import get_data
import shutil
import subprocess
import sys
import time

LIVE_LABEL = "Live: Check this computer"
FIELDS = {
    "cpu_percent": ("CPU load", "Performance", "%", "Recent processor use; it does not identify a busy app."),
    "ram_percent": ("Memory in use", "Performance", "%", "Share of physical memory not available for new work."),
    "ram_free_gib": ("Available memory", "Performance", "GiB", "Physical memory currently available."),
    "disk_free_gib": ("Available drive space", "Storage", "GiB", "Space free on the system drive, not disk speed."),
    "disk_free_percent": ("Drive space free", "Storage", "%", "Proportion of the same drive that is free."),
    "uptime_hours": ("Time since OS boot", "System", "h", "Uptime is context only; a long uptime is not a fault."),
    "links_up": ("Active local network links", "Network", "links", "Local link state only; virtual links may count. No Internet test."),
    "spooler": ("Windows Print Spooler", "Services", "", "Windows reports the service state; no print job is sent."),
}

GIB = 1024**3
SPOOLER_STATES = ("Running", "Stopped", "Paused", "StartPending", "StopPending", "PausePending", "ContinuePending")


def system_drive():
    """Choose the drive that holds Windows even if the demo is on a USB stick.
    On other operating systems the equivalent location is the root directory.
    """
    return os.environ.get("SystemDrive", "C:") + "\\" if os.name == "nt" else "/"


def windows_values():
    """Ask PowerShell for the local counters in windows_readings.ps1. It sends
    back a small JSON object; a failure is handled separately from the drive read.
    """
    query = get_data(__name__, "windows_readings.ps1").decode("utf-8")
    powershell = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    result = subprocess.run([str(powershell), "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", query],
                            capture_output=True, check=True, timeout=12,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    values = json.loads(result.stdout.decode("utf-8-sig"))
    if not isinstance(values, dict):
        raise ValueError("Invalid local counter response.")
    return values


def cpu_ticks():
    """Read the cumulative CPU counters from Linux. Two samples let us calculate the busy
    portion of the interval rather than guessing from one total."""
    parts = Path("/proc/stat").read_text().splitlines()[0].split()
    ticks = [int(value) for value in parts[1:9]]
    return sum(ticks), ticks[3] + ticks[4]

def linux_values():
    """Read CPU, memory, uptime and local link state from Linux when available. Each
    group is independent so one blocked counter does not spoil the rest."""
    values = {}
    try:
        total1, idle1 = cpu_ticks()
        time.sleep(0.5)
        total2, idle2 = cpu_ticks()
        if total2 > total1:
            values["cpu_percent"] = 100 * (1 - (idle2 - idle1) / (total2 - total1))
    except (OSError, ValueError, IndexError):
        pass
    try:
        mem = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
        total, free = (int(mem[key].split()[0]) for key in ("MemTotal", "MemAvailable"))
        if 0 <= free <= total and total > 0:
            values.update(ram_percent=100 * (1 - free / total), ram_free_gib=free / 1024**2)
    except (OSError, KeyError, ValueError, IndexError):
        pass
    try:
        values["uptime_hours"] = float(Path("/proc/uptime").read_text().split()[0]) / 3600
    except (OSError, ValueError, IndexError):
        pass
    try:
        links = [p for p in Path("/sys/class/net").iterdir() if p.name != "lo"]
        values["links_up"] = sum((p / "operstate").read_text().strip() == "up" for p in links)
    except OSError:
        pass
    return values

def clean(key, value):
    """Accept only sensible values for each reading, such as percentages between zero and
    100. A bad or missing value becomes None instead of looking like a healthy zero."""
    if key == "spooler":
        return value if value in SPOOLER_STATES else None
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        return None
    if key in ("cpu_percent", "ram_percent", "disk_free_percent") and value > 100:
        return None
    if key == "links_up":
        return int(value) if float(value).is_integer() else None
    return value

def reference_from(case):
    """Keep the timestamp and current values of a real scan for the next comparison. A
    fictional case cannot become a device baseline."""
    if case.get("origin") != "live":
        raise ValueError("Only a live scan can be a live reference.")
    return {"at": case["captured_at"], "values": {r["id"]: r["current"] for r in case["evidence"]}}

def collect_live(consent=False, reference=None):
    """Read local counters only after consent. Keep the drive result even if the
    operating system reader fails, then pair each value with the earlier scan if one
    was provided."""
    if not consent:
        raise PermissionError("Approve the local scan first.")
    values, warnings = {}, []
    try:
        usage = shutil.disk_usage(system_drive())
        if not 0 <= usage.free <= usage.total or usage.total <= 0:
            raise ValueError("Invalid capacity")
        values.update(disk_free_gib=usage.free / GIB, disk_free_percent=100 * usage.free / usage.total)
    except (OSError, ValueError):
        warnings.append("System-drive counters were unavailable.")
    try:
        if os.name == "nt":
            values.update(windows_values())
        elif sys.platform.startswith("linux"):
            values.update(linux_values())
        else:
            warnings.append("This OS supports storage only in this build.")
    except (OSError, subprocess.SubprocessError, ValueError):
        warnings.append("The system counters could not be read; the independent drive check is still shown.")
    prior = reference["values"] if reference else {}
    evidence = []
    for key, (label, category, unit, detail) in FIELDS.items():
        value = clean(key, values.get(key))
        if value is None:
            detail += " Windows only." if os.name != "nt" and key == "spooler" else " This read did not return a usable value."
        evidence.append(dict(id=key, label=label, category=category, unit=unit, detail=detail,
                             baseline=prior.get(key), current=value, changed_at=None))
    return dict(label=LIVE_LABEL, origin="live", scope="device_snapshot", device="This computer", platform=sys.platform,
                baseline_at=reference["at"] if reference else None, captured_at=datetime.now(timezone.utc).isoformat(timespec="microseconds"),
                description="Read this computer's local checks.", tags=["Slow"], onset=None, modules=6,
                collection_notes=warnings, evidence=evidence)
