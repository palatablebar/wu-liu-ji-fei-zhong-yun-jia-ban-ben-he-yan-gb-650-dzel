"""样例脏运单的确定性期望值。数值都由运价表与规则手工复算过。"""

HEADER = (
    "waybill_no,carrier,service,zone,pickup_date,weight,weight_unit,"
    "length,width,height,dim_unit,declared_value,pieces"
)

ROWS_IN = 27
ROWS_OK = 15
ROWS_QUARANTINED = 12
DUPLICATE_HEADERS = 1
SEGMENTS = 2

AMOUNT_TOTAL = "1521.04"
PARTS = {
    "base": "244.82",
    "step": "1104.48",
    "remote": "16.50",
    "fuel": "119.24",
    "insurance": "36.00",
}

# 每一票的实重、体积重、计费重、段数与应收
WAYBILLS = {
    "WB-1001": {"actual": "3.200", "volume": "5.000", "billable": "5.000", "steps": 8, "total": "42.67"},
    "WB-1002": {"actual": "0.800", "volume": "0.167", "billable": "1.000", "steps": 0, "total": "20.62"},
    "WB-1003": {"actual": "2.500", "volume": "12.000", "billable": "12.000", "steps": 22, "total": "108.74"},
    "WB-1004": {"actual": "12.500", "volume": "16.000", "billable": "16.000", "steps": 30, "total": "112.97"},
    "WB-1005": {"actual": "5.200", "volume": "72.000", "billable": "72.000", "steps": 142, "total": "697.05"},
    "WB-1006": {"actual": "1.200", "volume": "1.800", "billable": "2.000", "steps": 2, "total": "23.05"},
    "WB-1011": {"actual": "2.000", "volume": "1.333", "billable": "2.000", "steps": 2, "total": "19.44"},
    "WB-1012": {"actual": "1.000", "volume": "0.167", "billable": "1.000", "steps": 0, "total": "20.62"},
    "WB-1013": {"actual": "1.000", "volume": "0.167", "billable": "1.000", "steps": 0, "total": "19.44"},
    "WB-1015": {"actual": "3.000", "volume": "12.800", "billable": "13.000", "steps": 24, "total": "181.92"},
    "WB-1016": {"actual": "4.000", "volume": "20.833", "billable": "21.000", "steps": 40, "total": "156.24"},
    "WB-1017": {"actual": "3.200", "volume": "5.000", "billable": "5.000", "steps": 8, "total": "40.37"},
    "WB-1018": {"actual": "3.200", "volume": "5.000", "billable": "5.000", "steps": 8, "total": "36.67"},
    "WB-1019": {"actual": "2.000", "volume": "1.333", "billable": "2.000", "steps": 2, "total": "20.62"},
    "WB-1020": {"actual": "1.000", "volume": "0.167", "billable": "1.000", "steps": 0, "total": "20.62"},
}

BILLABLE_TOTAL = "159.000"
VOLUMETRIC_HITS = 9
ACTUAL_HITS = 6

QUARANTINE_CODES = [
    "ARITY_MISMATCH",
    "DATE_UNPARSEABLE",
    "DIM_RANGE",
    "DUP_CONFLICT",
    "NUM_UNPARSEABLE",
    "RATE_MISSING",
    "SENTINEL_VALUE",
    "TRUNCATED_TAIL",
    "UNIT_UNKNOWN",
    "UNKNOWN_CARRIER",
    "ZERO_DIMENSION",
]

VERSION_WINDOWS = {
    "v1": ("2026-01-01T00:00:00Z", "2026-04-01T00:00:00Z"),
    "v2": ("2026-04-01T00:00:00Z", "2026-07-01T00:00:00Z"),
}

RATE_CARD_ROWS = 38
RATE_KEYS = 19
RATE_SET_VERSION = 3

# 拼接样例 waybills_concat.csv：3 段，段 2 表头列序重排（件数↔声明价值），
# 段 3 有一行值级换位（件数吞下 2400）。数值由运价表 v2 手工复算。
CONCAT_ROWS_IN = 8
CONCAT_ROWS_OK = 7
CONCAT_ROWS_QUARANTINED = 1
CONCAT_SEGMENTS = 3
CONCAT_DUPLICATE_HEADERS = 2
CONCAT_AMOUNT_TOTAL = "679.85"
CONCAT_SEGMENT_ROWS = {1: 3, 2: 3, 3: 2}
CONCAT_SEGMENT_AMOUNTS = {1: "264.38", 2: "394.85", 3: "20.62"}
CONCAT_WAYBILLS = {
    "WB-3001": {"segment": 1, "declared": "2000.00", "pieces": 2, "insurance": "6.00", "total": "42.67"},
    "WB-3002": {"segment": 1, "declared": "5000.00", "pieces": 3, "insurance": "15.00", "total": "108.74"},
    "WB-3003": {"segment": 1, "declared": "1200.00", "pieces": 1, "insurance": "3.60", "total": "112.97"},
    "WB-3004": {"segment": 2, "declared": "800.00", "pieces": 1, "insurance": "2.40", "total": "349.38"},
    "WB-3005": {"segment": 2, "declared": "1500.00", "pieces": 1, "insurance": "4.50", "total": "23.05"},
    "WB-3006": {"segment": 2, "declared": "600.00", "pieces": 2, "insurance": "1.80", "total": "22.42"},
    "WB-3007": {"segment": 3, "declared": "0.00", "pieces": 1, "insurance": "0.00", "total": "20.62"},
}
