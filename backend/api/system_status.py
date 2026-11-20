from __future__ import annotations

import subprocess
from pathlib import Path
from shutil import which

import psutil


def read_system_status() -> dict[str, float | None]:
    """Return host CPU, memory, and optional NVIDIA GPU utilization."""
    memory = psutil.virtual_memory()
    gpu_percent = _read_gpu_percent()
    return {
        "cpu_percent": psutil.cpu_percent(interval=0.1),
        "gpu_percent": gpu_percent,
        "ram_percent": memory.percent,
        "ram_used_gb": round((memory.total - memory.available) / (1024**3), 1),
        "ram_total_gb": round(memory.total / (1024**3), 1),
    }


def _read_gpu_percent() -> float | None:
    nvidia_smi = which("nvidia-smi")
    if nvidia_smi is None:
        wsl_nvidia_smi = Path("/usr/lib/wsl/lib/nvidia-smi")
        if wsl_nvidia_smi.is_file():
            nvidia_smi = str(wsl_nvidia_smi)
        else:
            return None

    try:
        result = subprocess.run(
            [
                nvidia_smi,
                "--query-gpu=utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=1.5,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None

    try:
        values = [
            float(line.strip()) for line in result.stdout.splitlines() if line.strip()
        ]
    except ValueError:
        return None
    return round(sum(values) / len(values), 1) if values else None
