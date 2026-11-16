"""M6 编排：取五份账的输入，算账并附带归因；段视图把证据、结果与账单对齐。"""

from __future__ import annotations

import json

from app import store
from app.modules.m6_reconcile import compare, explain, totals


def reconcile(run_id: str) -> dict:
    run = store.get_run(run_id) or {}
    quarantine_rows = store.quarantine(run_id)
    weight_rows = store.weight_lines(run_id)
    charge_rows = store.charge_lines(run_id)
    waybill_rows = store.waybills(run_id)
    accounts = compare.accounts(run, quarantine_rows, weight_rows, charge_rows, waybill_rows)
    explain.annotated(accounts)
    return {
        "run_id": run_id,
        "accounts": accounts,
        "verdict": explain.verdict(accounts),
        "segments": segments(run_id),
        "total": str(totals.grand_total(charge_rows)),
        "conserved": totals.conserved(charge_rows),
        "rows_in": int(run.get("rows_in") or 0),
        "rows_ok": int(run.get("rows_ok") or 0),
        "amount_total": str(run.get("amount_total") or "0.00"),
    }


def segments(run_id: str) -> list[dict]:
    """逐段对账：采信时写入清单的段证据 vs 库里的运单结果与账单行。

    balanced 表示段证据行数与落库行数一致，且该段账单行不超出可计费行。
    """
    run = store.get_run(run_id) or {}
    try:
        notes = json.loads(run.get("notes") or "{}")
    except ValueError:
        notes = {}
    meta = {}
    noted_segments = notes.get("segments", [])
    if not isinstance(noted_segments, list):  # 旧清单里 segments 是计数而非列表
        noted_segments = []
    for item in noted_segments:
        if isinstance(item, dict) and item.get("segment") is not None:
            meta[int(item["segment"])] = item

    waybill_rows = store.waybills(run_id)
    quarantine_rows = store.quarantine(run_id)
    charge_rows = store.charge_lines(run_id)
    numbers = sorted(
        {int(row.get("segment") or 1) for row in waybill_rows}
        | {int(row.get("segment") or 1) for row in quarantine_rows}
        | set(meta)
    )

    result = []
    for number in numbers:
        ok = sum(1 for row in waybill_rows if int(row.get("segment") or 1) == number)
        bad = len({row["line_no"] for row in quarantine_rows
                   if int(row.get("segment") or 1) == number})
        charges = [row for row in charge_rows if int(row.get("segment") or 1) == number]
        noted = meta.get(number, {}).get("rows_in")
        result.append({
            "segment": number,
            "header_line": meta.get(number, {}).get("header_line", 0),
            "reordered": bool(meta.get(number, {}).get("reordered", False)),
            "sha256": meta.get(number, {}).get("sha256", ""),
            "rows_in": ok + bad,
            "rows_ok": ok,
            "rows_quarantined": bad,
            "billed": len(charges),
            "amount_total": str(totals.grand_total(charges)),
            "balanced": (noted is None or int(noted) == ok + bad) and len(charges) <= ok,
        })
    return result
