# SPDX-License-Identifier: LicenseRef-EvilKey-Manager-1.0
"""Local decoder for EvilKey USB Tool loot.bin and loot.idx files."""
from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Iterable

from .models import UserError

MAX_LOOT_SIZE = 16 * 1024 * 1024
VARIABLE_MODE = "variable_exfil_le16"
REFLECTION_MODE = "keystroke_reflection_raw"
INDEXED_MODE = "indexed_sidecar"

INDEX_MAGIC = b"PFLOOTI1"
INDEX_VERSION = 1
INDEX_HEADER_SIZE = 64
INDEX_RECORD_SIZE = 12
INDEX_MAX_SEGMENTS = 256
KIND_VARIABLE = 1
KIND_REFLECTION = 2
KIND_LEGACY = 3


@dataclass(frozen=True)
class LootSegment:
    offset: int
    length: int
    kind: int


@dataclass(frozen=True)
class LootIndex:
    path: Path
    loot_size: int
    digest: bytes
    segments: tuple[LootSegment, ...]


def read_loot(path: Path) -> bytes:
    if not path.is_file():
        raise UserError("Select an existing loot.bin file.")
    if path.stat().st_size > MAX_LOOT_SIZE:
        raise UserError("loot.bin exceeds the 16 MiB safety limit.")
    return path.read_bytes()


def index_path_for(path: Path) -> Path:
    return path.with_suffix(".idx")


def read_loot_index(path: Path, data: bytes) -> LootIndex | None:
    index_path = index_path_for(path)
    if not index_path.exists():
        return None
    if not index_path.is_file():
        raise UserError(f"{index_path.name} is not a regular file.")
    raw = index_path.read_bytes()
    if len(raw) < INDEX_HEADER_SIZE:
        raise UserError(f"{index_path.name} has a truncated header.")
    if raw[:8] != INDEX_MAGIC or raw[8] != INDEX_VERSION:
        raise UserError(f"{index_path.name} has an unsupported format or version.")
    if raw[9] != INDEX_HEADER_SIZE or raw[10] != INDEX_RECORD_SIZE or raw[11] != 0:
        raise UserError(f"{index_path.name} has invalid format parameters.")
    loot_size = int.from_bytes(raw[12:16], "little")
    count = int.from_bytes(raw[16:18], "little")
    if count > INDEX_MAX_SEGMENTS:
        raise UserError(f"{index_path.name} exceeds the limit of {INDEX_MAX_SEGMENTS} segments.")
    expected_size = INDEX_HEADER_SIZE + count * INDEX_RECORD_SIZE
    if len(raw) != expected_size or raw[18:20] != b"\0\0" or any(raw[52:64]):
        raise UserError(f"{index_path.name} has an invalid length or reserved fields.")
    digest = raw[20:52]
    if loot_size != len(data) or digest != hashlib.sha256(data).digest():
        raise UserError(f"{index_path.name} does not match {path.name} (size or SHA-256).")

    segments: list[LootSegment] = []
    cursor = 0
    for number in range(count):
        start = INDEX_HEADER_SIZE + number * INDEX_RECORD_SIZE
        record = raw[start:start + INDEX_RECORD_SIZE]
        offset = int.from_bytes(record[0:4], "little")
        length = int.from_bytes(record[4:8], "little")
        kind = record[8]
        if record[9:12] != b"\0\0\0" or kind not in (KIND_VARIABLE, KIND_REFLECTION, KIND_LEGACY):
            raise UserError(f"{index_path.name}: segment {number + 1} has an unknown format.")
        if offset != cursor or length <= 0 or length > len(data) - cursor:
            raise UserError(f"{index_path.name}: segment {number + 1} has an invalid range.")
        segments.append(LootSegment(offset, length, kind))
        cursor += length
    if cursor != len(data) or (len(data) == 0) != (count == 0):
        raise UserError(f"{index_path.name} does not cover the entire {path.name} file.")
    return LootIndex(index_path, loot_size, digest, tuple(segments))


def _format_name(kind: int) -> str:
    return {
        KIND_VARIABLE: "Variable values",
        KIND_REFLECTION: "Return data",
        KIND_LEGACY: "Legacy or unknown format",
    }[kind]


def _decode_variable(data: bytes, base_offset: int, segment: object = "") -> list[dict[str, object]]:
    if len(data) % 2:
        where = f" in segment {segment}" if segment != "" else ""
        raise UserError(f"Variable data{where} requires an even byte count; the final record is incomplete.")
    return [
        {"index": i // 2, "offset": base_offset + i, "hex": data[i:i + 2].hex(" ").upper(),
         "value": int.from_bytes(data[i:i + 2], "little"), "ascii": "",
         "segment": segment, "format": "Variable values"}
        for i in range(0, len(data), 2)
    ]


def _decode_bytes(data: bytes, base_offset: int, segment: object = "",
                  format_name: str = "Return data") -> list[dict[str, object]]:
    return [
        {"index": i, "offset": base_offset + i, "hex": f"{value:02X}", "value": value,
         "ascii": chr(value) if 32 <= value <= 126 else ".", "segment": segment,
         "format": format_name}
        for i, value in enumerate(data)
    ]


def decode_rows(data: bytes, mode: str, index: LootIndex | None = None) -> list[dict[str, object]]:
    if mode == VARIABLE_MODE:
        return _decode_variable(data, 0)
    if mode == REFLECTION_MODE:
        return _decode_bytes(data, 0)
    if mode == INDEXED_MODE:
        if index is None:
            raise UserError("No matching .idx file; manually select the data format.")
        rows: list[dict[str, object]] = []
        for number, segment in enumerate(index.segments, 1):
            chunk = data[segment.offset:segment.offset + segment.length]
            if segment.kind == KIND_VARIABLE:
                decoded = _decode_variable(chunk, segment.offset, number)
            else:
                decoded = _decode_bytes(chunk, segment.offset, number, _format_name(segment.kind))
            for row in decoded:
                row["index"] = len(rows)
                rows.append(row)
        return rows
    raise UserError("Unknown data file format.")


def describe(data: bytes, mode: str, index: LootIndex | None = None) -> str:
    digest = hashlib.sha256(data).hexdigest().upper()
    if mode == INDEXED_MODE:
        if index is None:
            raise UserError("No matching .idx file.")
        return f"{len(data)} B · {len(index.segments)} segments from {index.path.name} · SHA-256 {digest}"
    kind = "16-bit records" if mode == VARIABLE_MODE else "bytes of feedback data"
    count = len(data) // 2 if mode == VARIABLE_MODE else len(data)
    return f"{len(data)} B · {count} {kind} · SHA-256 {digest}"


def export_csv(path: Path, rows: Iterable[dict[str, object]], mode: str) -> None:
    if mode == INDEXED_MODE:
        fields = ["index", "segment", "format", "offset", "raw_hex", "value", "ascii"]
    elif mode == VARIABLE_MODE:
        fields = ["index", "offset", "raw_hex", "uint16_le"]
    else:
        fields = ["index", "offset", "raw_hex", "byte_decimal", "ascii"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(fields)
        for row in rows:
            if mode == INDEXED_MODE:
                writer.writerow([row["index"], row["segment"], row["format"], row["offset"],
                                 row["hex"], row["value"], row["ascii"]])
            elif mode == VARIABLE_MODE:
                writer.writerow([row["index"], row["offset"], row["hex"], row["value"]])
            else:
                writer.writerow([row["index"], row["offset"], row["hex"], row["value"], row["ascii"]])
