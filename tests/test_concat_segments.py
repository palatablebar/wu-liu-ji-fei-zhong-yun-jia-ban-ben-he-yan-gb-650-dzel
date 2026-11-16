"""拼接文件结算：段识别、列序重排、值级换位兜底、段级对账、重试幂等。

TRAP-27：承运商把多次生成的运单文件拼成一份，后段表头字段相同但列序
不保证；列序重排的表头不能被当成数据行，本段按自己的列序取值。
TRAP-28：件数与声明价值换位后保价照常生成却不正确；表头重排由段布局
修复，表头未变的值级换位由件数上界兜底进隔离区。
"""

from __future__ import annotations

from decimal import Decimal

from fixtures import samples
from fixtures.expected import (
    CONCAT_AMOUNT_TOTAL,
    CONCAT_DUPLICATE_HEADERS,
    CONCAT_ROWS_IN,
    CONCAT_ROWS_OK,
    CONCAT_ROWS_QUARANTINED,
    CONCAT_SEGMENT_AMOUNTS,
    CONCAT_SEGMENT_ROWS,
    CONCAT_SEGMENTS,
    CONCAT_WAYBILLS,
)

from app import store
from app.modules.m1_waybill import normalize, reader
from app.modules.m1_waybill import service as waybills
from app.modules.m4_weights import service as weights
from app.modules.m5_charges import service as charges
from app.modules.m6_reconcile import service as reconcile
from app.modules.m7_export import csv_out, invoice_out

REORDERED_HEADER = (
    "waybill_no,carrier,service,zone,pickup_date,weight,weight_unit,"
    "length,width,height,dim_unit,pieces,declared_value"
)


def _concat_row(waybill_no: str, declared: str = "0", pieces: str = "1") -> str:
    """按重排列序（pieces 在 declared_value 前）写一行数据。"""
    return (
        f"{waybill_no},SF,standard,Z1,2026-04-05T10:00:00+08:00,1,kg,"
        f"10,10,10,cm,{pieces},{declared}"
    )


def test_reordered_header_is_segment_boundary(sample_bytes):
    """TRAP-27：列序重排的表头是段边界，不是数据行。"""
    raw = sample_bytes("waybills_concat.csv")
    sheet = reader.read_sheet(raw.decode("utf-8"))
    assert sheet.segments == CONCAT_SEGMENTS
    assert sheet.duplicate_headers == CONCAT_DUPLICATE_HEADERS
    assert len(sheet.records) == CONCAT_ROWS_IN
    assert sheet.segment_info[1]["reordered"] is True
    assert sheet.segment_info[1]["layout"] != sheet.header
    assert sorted(sheet.segment_info[1]["layout"]) == sorted(sheet.header)
    # 重排表头行本身不产生记录
    assert all(record.line_no != 5 for record in sheet.records)


def test_segment_digests_are_distinct_and_stable(sample_bytes):
    """每段有独立摘要，同一份文件两次解析摘要一致。"""
    raw = sample_bytes("waybills_concat.csv")
    first = reader.read_sheet(raw.decode("utf-8"))
    second = reader.read_sheet(raw.decode("utf-8"))
    digests = [info["sha256"] for info in first.segment_info]
    assert digests == [info["sha256"] for info in second.segment_info]
    assert len(set(digests)) == CONCAT_SEGMENTS
    assert all(len(digest) == 64 for digest in digests)


def test_concat_import_counts_and_segments(concat_pipeline):
    ingest = concat_pipeline["ingest"]
    assert ingest["rows_in"] == CONCAT_ROWS_IN
    assert ingest["rows_ok"] == CONCAT_ROWS_OK
    assert ingest["rows_quarantined"] == CONCAT_ROWS_QUARANTINED


def test_reordered_segment_values_land_in_right_columns(concat_pipeline):
    """段 2 列序重排后，声明价值与件数仍按本段表头取值。"""
    rows = {row["waybill_no"]: row for row in store.waybills(concat_pipeline["run_id"])}
    for waybill_no, expect in CONCAT_WAYBILLS.items():
        row = rows[waybill_no]
        assert row["segment"] == expect["segment"]
        assert row["declared_value"] == expect["declared"]
        assert row["pieces"] == expect["pieces"]
    assert "SEGMENT_REORDERED" in rows["WB-3004"]["codes"]
    assert "SEGMENT_REORDERED" not in rows["WB-3001"]["codes"]


def test_insurance_uses_true_declared_value(concat_pipeline):
    """TRAP-28：保价必须按真实申报价值计，不按换位后的值。"""
    lines = {row["waybill_no"]: row for row in store.charge_lines(concat_pipeline["run_id"])}
    for waybill_no, expect in CONCAT_WAYBILLS.items():
        assert lines[waybill_no]["insurance_amount"] == expect["insurance"]
        assert lines[waybill_no]["total_amount"] == expect["total"]
        assert lines[waybill_no]["segment"] == expect["segment"]
    assert concat_pipeline["charges"]["amount_total"] == CONCAT_AMOUNT_TOTAL


def test_value_level_swap_quarantined(concat_pipeline):
    """表头未变但数据换位：件数吞下金额级数值，PIECES_RANGE 阻断。"""
    items = store.quarantine(concat_pipeline["run_id"])
    assert [item["code"] for item in items] == ["PIECES_RANGE"]
    assert items[0]["waybill_no"] == "WB-3008"
    assert items[0]["segment"] == 3
    billed = {row["waybill_no"] for row in store.charge_lines(concat_pipeline["run_id"])}
    assert "WB-3008" not in billed


def test_pieces_bound():
    """件数上界是结构校验：合理值放行，越界记 PIECES_RANGE。"""
    assert normalize.to_pieces("3") == (3, "")
    assert normalize.to_pieces("") == (1, "")
    assert normalize.to_pieces("abc") == (1, "")
    assert normalize.to_pieces("2400.00") == (1, "PIECES_RANGE")


def test_reordered_segment_without_boundary_row_bills_correctly():
    """只有两段且第二段重排：整段按重排列序解析，不错位。"""
    raw = samples.csv_bytes([samples.row("WB-9401", declared="100")]).decode("utf-8")
    raw = raw + "\n" + REORDERED_HEADER + "\n" + _concat_row("WB-9403", declared="300", pieces="3")
    ingest = waybills.import_bytes(raw.encode("utf-8"), "reorder.csv")
    assert ingest["rows_ok"] == 2
    run_id = ingest["run_id"]
    rows = {row["waybill_no"]: row for row in store.waybills(run_id)}
    assert rows["WB-9403"]["declared_value"] == "300.00"
    assert rows["WB-9403"]["pieces"] == 3
    weights.compute_weights(run_id)
    charges.compute_charges(run_id)
    lines = {row["waybill_no"]: row for row in store.charge_lines(run_id)}
    # SF standard Z1 v2 保价费率 0.003：300 × 0.003 = 0.90
    assert lines["WB-9403"]["insurance_amount"] == "0.90"


def test_duplicate_waybill_across_segments_keeps_first():
    """跨段重复运单：文件顺序即证据顺序，留首条，后条进隔离区。"""
    raw = samples.csv_bytes([samples.row("WB-9501", declared="100")]).decode("utf-8")
    raw = raw + "\n" + REORDERED_HEADER + "\n" + _concat_row("WB-9501", declared="100")
    ingest = waybills.import_bytes(raw.encode("utf-8"), "dup_segments.csv")
    assert ingest["rows_ok"] == 1
    assert ingest["rows_quarantined"] == 1
    items = store.quarantine(ingest["run_id"])
    assert items[0]["code"] == "DUPLICATE_WAYBILL"
    assert items[0]["segment"] == 2


def test_segment_account_and_view(concat_pipeline):
    """分段账与段视图：每段 采信 = 计费 + 隔离，分段应收之和 = 总应收。"""
    report = reconcile.reconcile(concat_pipeline["run_id"])
    account = {a["key"]: a for a in report["accounts"]}["segments"]
    assert account["left_value"] == CONCAT_ROWS_IN
    parts = {part["label"]: part["value"] for part in account["parts"]}
    assert parts == {f"段{seg}": rows for seg, rows in CONCAT_SEGMENT_ROWS.items()}
    assert account["balanced"] is True
    segs = {seg["segment"]: seg for seg in report["segments"]}
    for number, rows in CONCAT_SEGMENT_ROWS.items():
        assert segs[number]["rows_in"] == rows
        assert segs[number]["amount_total"] == CONCAT_SEGMENT_AMOUNTS[number]
        assert segs[number]["balanced"] is True
    assert segs[2]["reordered"] is True
    total = sum(Decimal(seg["amount_total"]) for seg in report["segments"])
    assert str(total) == CONCAT_AMOUNT_TOTAL


def test_retry_same_file_never_double_bills(concat_pipeline):
    """同一文件重试：run_id 复用，重算各阶段行数与合计不变。"""
    run_id = concat_pipeline["run_id"]
    before_lines = len(store.charge_lines(run_id))
    before_total = store.get_run(run_id)["amount_total"]

    again = waybills.import_sample("waybills_concat.csv")
    assert again["run_id"] == run_id
    assert again["reused"] is True
    weights.compute_weights(run_id)
    charges.compute_charges(run_id)
    charges.compute_charges(run_id)

    assert len(store.charge_lines(run_id)) == before_lines
    assert store.get_run(run_id)["amount_total"] == before_total == CONCAT_AMOUNT_TOTAL


def test_exports_carry_segment(concat_pipeline):
    """账单 CSV、证据 CSV、运行清单都带段号，可按段切片核对。"""
    run_id = concat_pipeline["run_id"]
    invoice = invoice_out.invoice_csv(run_id)
    assert invoice.splitlines()[0].split(",")[:2] == ["waybill_no", "segment"]
    evidence = csv_out.csv_text(run_id)
    assert evidence.splitlines()[0].startswith("line_no,segment")
    doc = invoice_out.manifest_doc(run_id)
    assert len(doc["segments"]) == CONCAT_SEGMENTS
    assert all(len(seg["sha256"]) == 64 for seg in doc["segments"])
