"""System probe for Spartina Earth.

Reports the host resources relevant to project planning: CPU, RAM, disk,
GPUs, driver/CUDA versions, and the Python / PyTorch environment.

Design constraints (M0):
    * Python standard library only -- no third-party imports required.
    * Read-only: never starts, stops, or modifies anything.
    * Safe on machines without NVIDIA drivers or torch (fields then report
      ``None`` / ``unavailable`` rather than failing).

Usage:
    python scripts/system/probe.py            # human-readable report
    python scripts/system/probe.py --json     # machine-readable JSON
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from typing import Any

GIB = 1024**3


def _read_meminfo() -> dict[str, int] | None:
    """Return Linux /proc/meminfo values in bytes, or None off-Linux."""
    path = "/proc/meminfo"
    if not os.path.exists(path):
        return None
    info: dict[str, int] = {}
    with open(path, encoding="ascii") as handle:
        for line in handle:
            key, _, rest = line.partition(":")
            parts = rest.strip().split()
            if not parts:
                continue
            value = int(parts[0])
            # /proc/meminfo reports kB (except a few counters); convert to B.
            info[key] = value * 1024
    return info


def cpu_report() -> dict[str, Any]:
    return {
        "processor": platform.processor() or platform.machine(),
        "logical_cpus": os.cpu_count(),
    }


def memory_report() -> dict[str, Any]:
    meminfo = _read_meminfo()
    if meminfo is None:
        return {"available": None}
    total = meminfo.get("MemTotal")
    available = meminfo.get("MemAvailable")
    swap_total = meminfo.get("SwapTotal")
    swap_free = meminfo.get("SwapFree")
    return {
        "total_gib": round(total / GIB, 1) if total is not None else None,
        "available_gib": round(available / GIB, 1) if available is not None else None,
        "swap_total_gib": round(swap_total / GIB, 1) if swap_total is not None else None,
        "swap_free_gib": round(swap_free / GIB, 1) if swap_free is not None else None,
    }


def disk_report(path: str = "/data") -> dict[str, Any]:
    target = path if os.path.exists(path) else "/"
    usage = shutil.disk_usage(target)
    return {
        "path": target,
        "total_gib": round(usage.total / GIB, 1),
        "used_gib": round(usage.used / GIB, 1),
        "free_gib": round(usage.free / GIB, 1),
        "percent_used": round(100.0 * usage.used / usage.total, 1),
    }


def gpu_report() -> dict[str, Any]:
    """Query GPUs through nvidia-smi. Returns an 'available' flag."""
    fields = [
        "index",
        "name",
        "memory.total",
        "memory.used",
        "memory.free",
        "utilization.gpu",
        "pci.bus_id",
    ]
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                f"--query-gpu={','.join(fields)}",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return {"available": False, "gpus": [], "driver_version": None, "cuda_version": None}

    gpus: list[dict[str, Any]] = []
    for line in completed.stdout.strip().splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != len(fields):
            continue
        gpus.append(
            {
                "index": int(parts[0]),
                "name": parts[1],
                "memory_total_mib": int(float(parts[2])),
                "memory_used_mib": int(float(parts[3])),
                "memory_free_mib": int(float(parts[4])),
                "utilization_gpu_percent": int(float(parts[5])),
                "pci_bus_id": parts[6],
            }
        )

    driver_version = None
    cuda_version = None
    try:
        top = subprocess.run(
            ["nvidia-smi"],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
        for out_line in top.stdout.splitlines():
            if "Driver Version:" in out_line and "CUDA Version:" in out_line:
                tokens = out_line.split()
                for idx, token in enumerate(tokens):
                    if token == "Driver" and idx + 2 < len(tokens):
                        driver_version = tokens[idx + 2]
                    if token == "CUDA" and idx + 2 < len(tokens):
                        cuda_version = tokens[idx + 2]
                break
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass

    return {
        "available": bool(gpus),
        "count": len(gpus),
        "gpus": gpus,
        "driver_version": driver_version,
        "cuda_version": cuda_version,
    }


def python_report() -> dict[str, Any]:
    report: dict[str, Any] = {
        "version": sys.version.split()[0],
        "executable": sys.executable,
        "implementation": platform.python_implementation(),
    }
    try:
        import torch
    except ImportError:
        report["torch"] = None
    else:
        report["torch"] = {
            "version": getattr(torch, "__version__", "unknown"),
            "cuda_available": bool(torch.cuda.is_available()),
            "cuda_runtime": (
                getattr(torch.version, "cuda", None) if hasattr(torch, "version") else None
            ),
            "device_count": int(torch.cuda.device_count()) if torch.cuda.is_available() else 0,
        }
    return report


def collect() -> dict[str, Any]:
    return {
        "probe": "spartina-earth-system-probe",
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "cpu": cpu_report(),
        "memory": memory_report(),
        "disk": disk_report("/data"),
        "gpu": gpu_report(),
        "python": python_report(),
    }


def _format_human(report: dict[str, Any]) -> str:
    lines: list[str] = ["Spartina Earth system probe", "=" * 34]
    plat = report["platform"]
    lines.append(f"Platform : {plat['system']} {plat['release']} ({plat['machine']})")
    cpu = report["cpu"]
    lines.append(f"CPU      : {cpu['processor']} — {cpu['logical_cpus']} logical CPUs")
    mem = report["memory"]
    if mem.get("total_gib") is not None:
        lines.append(
            f"RAM      : {mem['total_gib']} GiB total, {mem['available_gib']} GiB available; "
            f"swap {mem['swap_total_gib']} GiB ({mem['swap_free_gib']} free)"
        )
    disk = report["disk"]
    lines.append(
        f"Disk     : {disk['path']} {disk['total_gib']} GiB, "
        f"{disk['percent_used']}% used, {disk['free_gib']} GiB free"
    )
    gpu = report["gpu"]
    if not gpu["available"]:
        lines.append("GPU      : nvidia-smi unavailable")
    else:
        lines.append(
            f"GPU      : {gpu['count']} device(s); driver {gpu['driver_version']}, "
            f"CUDA {gpu['cuda_version']}"
        )
        for device in gpu["gpus"]:
            lines.append(
                f"  [{device['index']}] {device['name']} ({device['pci_bus_id']}) "
                f"{device['memory_used_mib']}/{device['memory_total_mib']} MiB used, "
                f"{device['utilization_gpu_percent']}% util"
            )
    py = report["python"]
    lines.append(f"Python   : {py['version']} ({py['executable']})")
    if py["torch"] is None:
        lines.append("PyTorch  : not importable in this interpreter")
    else:
        torch_info = py["torch"]
        lines.append(
            f"PyTorch  : {torch_info['version']}, cuda_available={torch_info['cuda_available']}, "
            f"devices={torch_info['device_count']}"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    args = parser.parse_args()
    report = collect()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(_format_human(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
