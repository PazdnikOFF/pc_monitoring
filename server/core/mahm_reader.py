"""
MSI Afterburner / MAHM Shared Memory reader.

On Windows uses ctypes to open the "MAHMSharedMemory" file mapping.
On macOS / Linux returns deterministic mock data for development.
"""

from __future__ import annotations

import platform
import random
import struct
import time
from dataclasses import dataclass, field
from typing import Dict


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class SensorEntry:
    value: float
    unit: str
    label: str
    gpu: int = 0
    src_id: int = 0


# ---------------------------------------------------------------------------
# MAHM Shared Memory layout (Windows)
# ---------------------------------------------------------------------------

MAHM_SIGNATURE = b"MAHM"

# Header offsets (all little-endian)
_HDR_FMT = "<4sIIIII"   # signature, version, header_size, entry_size, num_entries, time
_HDR_SIZE = struct.calcsize(_HDR_FMT)

# Entry layout
#   src_name          260 bytes  (char[260])
#   src_units         260 bytes
#   local_name        260 bytes
#   recommended_format 260 bytes
#   recommended_format_len 4 bytes (DWORD)
#   data              4 bytes  (float)
#   min_limit         4 bytes  (float)
#   max_limit         4 bytes  (float)
#   flags             4 bytes  (DWORD)
#   gpu               4 bytes  (DWORD)
#   src_id            4 bytes  (DWORD)

_ENTRY_FMT = "<260s260s260s260sIfff III"
_ENTRY_SIZE = struct.calcsize(_ENTRY_FMT)


def _decode(b: bytes) -> str:
    """Decode a null-terminated char array."""
    return b.split(b"\x00", 1)[0].decode("latin-1", errors="replace")


# ---------------------------------------------------------------------------
# Platform implementations
# ---------------------------------------------------------------------------

class _WindowsReader:
    """Reads sensors from MAHM shared memory on Windows."""

    _MEM_NAME = "MAHMSharedMemory"

    def read_all(self) -> Dict[str, SensorEntry]:
        import ctypes
        import ctypes.wintypes as wt

        FILE_MAP_READ = 0x0004
        k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

        h = k32.OpenFileMappingW(FILE_MAP_READ, False, self._MEM_NAME)
        if not h:
            return {}

        try:
            size = 0  # map entire object
            view = k32.MapViewOfFile(h, FILE_MAP_READ, 0, 0, size)
            if not view:
                return {}
            try:
                return self._parse(view)
            finally:
                k32.UnmapViewOfFile(view)
        finally:
            k32.CloseHandle(h)

    def _parse(self, view: int) -> Dict[str, SensorEntry]:
        import ctypes

        def read_bytes(offset: int, length: int) -> bytes:
            buf = (ctypes.c_char * length).from_address(view + offset)
            return bytes(buf)

        hdr_raw = read_bytes(0, _HDR_SIZE)
        sig, version, header_size, entry_size, num_entries, ts = struct.unpack(
            _HDR_FMT, hdr_raw
        )
        if sig != MAHM_SIGNATURE:
            return {}

        results: Dict[str, SensorEntry] = {}
        for i in range(num_entries):
            offset = header_size + i * entry_size
            raw = read_bytes(offset, _ENTRY_SIZE)
            (
                src_name_b,
                src_units_b,
                local_name_b,
                rec_fmt_b,
                rec_fmt_len,
                data,
                min_limit,
                max_limit,
                flags,
                gpu,
                src_id,
            ) = struct.unpack(_ENTRY_FMT, raw)

            src_name = _decode(src_name_b)
            src_units = _decode(src_units_b)
            local_name = _decode(local_name_b)

            key = f"{src_name}_{src_id}_gpu{gpu}"
            results[key] = SensorEntry(
                value=data,
                unit=src_units,
                label=local_name or src_name,
                gpu=gpu,
                src_id=src_id,
            )

        return results


class _MockReader:
    """Returns deterministic mock sensor data for macOS / Linux development."""

    _SENSORS = [
        ("cpu_temp",     "CPU Temperature",        "°C",  0,  0),
        ("cpu_usage",    "CPU Usage",              "%",   0,  1),
        ("cpu_clock",    "CPU Clock",              "MHz", 0,  2),
        ("gpu_temp",     "GPU Temperature",        "°C",  0,  3),
        ("gpu_usage",    "GPU Usage",              "%",   0,  4),
        ("gpu_clock",    "GPU Core Clock",         "MHz", 0,  5),
        ("gpu_mem_clock","GPU Memory Clock",       "MHz", 0,  6),
        ("gpu_mem_usage","GPU Memory Usage",       "MB",  0,  7),
        ("fps",          "Framerate",              "FPS", 0,  8),
        ("fps_1low",     "1% Low Framerate",       "FPS", 0,  9),
        ("ram_usage",    "RAM Usage",              "MB",  0, 10),
        ("gpu_power",    "GPU Power",              "W",   0, 11),
        ("gpu_fan",      "GPU Fan Speed",          "RPM", 0, 12),
        ("cpu_fan",      "CPU Fan Speed",          "RPM", 0, 13),
    ]

    # Baseline values for each sensor
    _BASELINES: Dict[str, float] = {
        "cpu_temp":      62.0,
        "cpu_usage":     45.0,
        "cpu_clock":     3800.0,
        "gpu_temp":      74.0,
        "gpu_usage":     80.0,
        "gpu_clock":     1950.0,
        "gpu_mem_clock": 8000.0,
        "gpu_mem_usage": 6144.0,
        "fps":           120.0,
        "fps_1low":      95.0,
        "ram_usage":     16384.0,
        "gpu_power":     180.0,
        "gpu_fan":       1800.0,
        "cpu_fan":       1200.0,
    }

    def read_all(self) -> Dict[str, SensorEntry]:
        result: Dict[str, SensorEntry] = {}
        for key, label, unit, gpu, src_id in self._SENSORS:
            base = self._BASELINES[key]
            jitter = random.uniform(-base * 0.03, base * 0.03)
            result[key] = SensorEntry(
                value=round(base + jitter, 1),
                unit=unit,
                label=label,
                gpu=gpu,
                src_id=src_id,
            )
        return result


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

class MAHMReader:
    """
    Singleton-friendly reader.

    Usage::

        reader = MAHMReader()
        data = reader.read_all()   # -> dict[str, SensorEntry]
    """

    def __init__(self) -> None:
        if platform.system() == "Windows":
            self._impl: _WindowsReader | _MockReader = _WindowsReader()
        else:
            self._impl = _MockReader()

    def read_all(self) -> Dict[str, SensorEntry]:
        """Return current sensor readings as {key: SensorEntry}."""
        return self._impl.read_all()

    def is_mock(self) -> bool:
        return isinstance(self._impl, _MockReader)
