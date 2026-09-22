"""Telecom Perturbation Suite for catching 'accidental correctness' in SQL queries.

Based on test-suite accuracy principles (Zhong, Yu & Klein, EMNLP 2020):
A query might yield identical output on static sample data, but contain severe logical bugs
(e.g. missing SCD2 valid_to filter, ignoring test SIMs, or duplicate CDRs).

Injecting telecom-specific perturbations into data verifies if the generated SQL is genuinely sound.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class TelecomPerturbation:
    name: str
    bug_description: str
    setup_queries: list[str] = field(default_factory=list)


TELECOM_PERTURBATIONS: list[TelecomPerturbation] = [
    TelecomPerturbation(
        name="msisdn_reassigned",
        bug_description="JOIN bảng thuê bao không kèm khoảng hiệu lực (SCD2) -> gán nhầm chủ thuê bao cũ",
        setup_queries=[
            "INSERT INTO dim_sub (msisdn, sub_id, segment, valid_from, valid_to) "
            "SELECT msisdn, sub_id || '_old', segment, '2019-01-01', '2019-12-31' "
            "FROM dim_sub WHERE valid_to = '9999-12-31'"
        ],
    ),
    TelecomPerturbation(
        name="prepaid_postpaid_switch",
        bug_description="Gộp sai hai nhánh trả trước/trả sau -> đếm trùng hoặc thiếu thuê bao chuyển loại",
        setup_queries=[
            "UPDATE dim_sub SET segment='POSTPAID' "
            "WHERE msisdn IN (SELECT msisdn FROM dim_sub LIMIT 1)"
        ],
    ),
    TelecomPerturbation(
        name="cdr_duplicate",
        bug_description="Thiếu dedup khi hệ thống mediation cước chạy lại -> nhân đôi số phút/dung lượng",
        setup_queries=[
            "INSERT INTO cdr_voice SELECT * FROM cdr_voice LIMIT 3"
        ],
    ),
    TelecomPerturbation(
        name="billing_cycle_edge",
        bug_description="Nhầm chu kỳ cước (ví dụ ngày 16 tháng trước đến 15 tháng này) với tháng dương lịch",
        setup_queries=[
            "INSERT INTO cdr_voice (msisdn, call_ts, duration, dt) "
            "SELECT msisdn, '2026-09-15 00:00:00', 60, '2026-09-15' FROM cdr_voice LIMIT 1"
        ],
    ),
    TelecomPerturbation(
        name="test_sim",
        bug_description="Quên loại trừ SIM nội bộ hoặc tài khoản kỹ thuật trong báo cáo doanh thu",
        setup_queries=[
            "INSERT INTO dim_sub (msisdn, sub_id, segment, valid_from, valid_to) "
            "VALUES ('TEST0001', 'test_1', 'INTERNAL', '2020-01-01', '9999-12-31')",
            "INSERT INTO cdr_voice (msisdn, call_ts, duration, dt) "
            "VALUES ('TEST0001', '2026-09-02 10:00:00', 9999, '2026-09-02')"
        ],
    ),
    TelecomPerturbation(
        name="late_arriving_cdr",
        bug_description="Dùng sai cột thời gian: ngày nạp hệ thống thay vì ngày thực tế phát sinh cước",
        setup_queries=[
            "INSERT INTO cdr_voice (msisdn, call_ts, duration, dt) "
            "SELECT msisdn, '2026-08-31 23:59:00', 120, '2026-09-01' FROM cdr_voice LIMIT 1"
        ],
    ),
    TelecomPerturbation(
        name="null_join_key",
        bug_description="Khóa JOIN bị NULL -> mất dòng hoặc INNER/LEFT JOIN ra kết quả sai lệch",
        setup_queries=[
            "INSERT INTO cdr_voice (msisdn, call_ts, duration, dt) "
            "VALUES (NULL, '2026-09-02 11:00:00', 30, '2026-09-02')"
        ],
    ),
]


@dataclass
class PerturbOutcome:
    name: str
    stable_gold: bool      # Gold SQL kết quả có giữ nguyên không
    pred_matches: bool     # Candidate SQL có còn khớp Gold sau nhiễu loạn không
    plausible: bool        # Kết quả candidate sau nhiễu loạn có trông hợp lý (sai ngầm) không
