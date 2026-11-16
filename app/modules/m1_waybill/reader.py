"""流式拆表：保留原始行号、识别段表头（列序可重排）、标记尾行截断。

拼接文件规则（S1）：凡归一化后列名集合与首表头相同的行都是段表头，
列序不同不当作数据行；每个段按自己的列序取值，段摘要随运行清单落库。
"""

from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass, field, replace
from typing import Any

from app import config
from app.errors import DomainError

EMPTY_FILE = "empty_file"
HEADER_ONLY = "header_only"
BLANK_ROWS = "blank_rows"
READY = "ready"


@dataclass(frozen=True)
class Record:
    line_no: int
    cells: list[str]
    raw: str
    segment: int
    arity_ok: bool = True
    truncated: bool = False


@dataclass
class SegmentInfo:
    segment: int
    header_line: int
    layout: list[str]
    reordered: bool
    digest: Any = field(default_factory=lambda: hashlib.sha256())

    def feed(self, text: str) -> None:
        self.digest.update(text.encode("utf-8"))
        self.digest.update(b"\n")

    def describe(self) -> dict:
        return {
            "segment": self.segment,
            "header_line": self.header_line,
            "layout": list(self.layout),
            "reordered": self.reordered,
            "sha256": self.digest.hexdigest(),
        }


@dataclass
class Sheet:
    header: list[str] = field(default_factory=list)
    records: list[Record] = field(default_factory=list)
    layouts: dict = field(default_factory=dict)
    segment_info: list = field(default_factory=list)
    segments: int = 1
    duplicate_headers: int = 0
    empty_rows: int = 0
    state: str = READY
    codes: list[str] = field(default_factory=list)

    def layout_for(self, segment: int) -> list[str]:
        return self.layouts.get(segment) or self.header


def normalize_header(cells: list[str]) -> list[str]:
    names: list[str] = []
    for cell in cells:
        name = (cell or "").strip().lstrip("﻿").strip().lower()
        name = config.HEADER_ALIASES.get(name, name)
        names.append(name)
    return names


def is_header_line(cells: list[str], canonical: list[str]) -> bool:
    """列名集合与首表头相同即段表头；列序任意（拼接文件不保证列序）。"""
    return sorted(normalize_header(cells)) == sorted(canonical)


def read_sheet(text: str, codes: list[str] | None = None) -> Sheet:
    sheet = Sheet(codes=list(codes or []))
    if not text.strip():
        sheet.state = EMPTY_FILE
        raise DomainError("EMPTY_FILE", "输入为空，没有可采信的记录", 422)

    lines = text.split("\n")
    reader = csv.reader(io.StringIO(text, newline=""))
    previous_line = 0
    header: list[str] | None = None
    current: SegmentInfo | None = None
    segment = 0

    for cells in reader:
        start = previous_line + 1
        end = reader.line_num
        raw = "\n".join(lines[start - 1:end])
        previous_line = end

        if header is None:
            if not any((c or "").strip() for c in cells):
                sheet.empty_rows += 1
                continue
            header = normalize_header(cells)
            sheet.header = header
            segment = 1
            current = SegmentInfo(segment, end, header, False)
            current.feed(raw)
            continue

        if not any((c or "").strip() for c in cells):
            sheet.empty_rows += 1
            continue

        if is_header_line(cells, header):
            layout = normalize_header(cells)
            sheet.duplicate_headers += 1
            sheet.segment_info.append(current.describe())
            segment += 1
            if layout == header:
                sheet.codes.append("DUPLICATE_HEADER")
                current = SegmentInfo(segment, end, layout, False)
            else:
                sheet.codes.append("SEGMENT_REORDERED")
                current = SegmentInfo(segment, end, layout, True)
            current.feed(raw)
            continue

        arity_ok = len(cells) == len(current.layout)
        sheet.records.append(
            Record(
                line_no=end,
                cells=[(c or "") for c in cells],
                raw=raw[:400],
                segment=segment,
                arity_ok=arity_ok,
            )
        )
        current.feed(raw)

    if header is None:
        sheet.state = EMPTY_FILE
        raise DomainError("EMPTY_FILE", "输入没有表头，无法确定列位置", 422)

    sheet.segment_info.append(current.describe())
    sheet.segments = segment
    sheet.layouts = {info["segment"]: info["layout"] for info in sheet.segment_info}
    if sheet.records:
        last = sheet.records[-1]
        if len(last.cells) < len(header):
            sheet.records[-1] = replace(last, arity_ok=False, truncated=True)
    elif sheet.empty_rows:
        sheet.state = BLANK_ROWS
    else:
        sheet.state = HEADER_ONLY
    return sheet


def column_index(header: list[str], name: str) -> int:
    try:
        return header.index(name)
    except ValueError:
        return -1


def cell(record: Record, header: list[str], name: str) -> str:
    index = column_index(header, name)
    if index < 0 or index >= len(record.cells):
        return ""
    return record.cells[index]
