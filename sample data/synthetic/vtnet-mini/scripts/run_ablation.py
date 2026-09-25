#!/usr/bin/env python3
"""Ablation of the verified-context pipeline on benchmark_v2.

Each configuration adds one component to the previous one, so the difference
between two rows is the contribution of that component:

    B0   hệ thống cũ (DuckDBRuntime của backend tại commit 8301397, đóng băng trong baselines/)
    C1   glossary linker, metadata M0 (chỉ tên + kiểu), không profiler/quy ước/kiểm chứng/cổng
    C2   + mô tả M1 (AI sinh, chưa kiểm chứng)
    C3   M2 + profiler (chỉ cột có dữ liệu, giá trị thật, phạm vi, grain)
    C4   + tri thức nghiệp vụ trong prompt: quy ước (registry) và định nghĩa thuật ngữ (glossary)
    C5   + kiểm chứng quy ước / lỗi / kết quả rỗng, 1 vòng sửa, không trả kết quả còn vi phạm
    C6   + cổng policy / mơ hồ / phạm vi thời gian và hợp đồng ABSTAIN/CLARIFY  (= hệ thống đầy đủ)
    C6m1 như C6 nhưng mô tả M1 thay vì M2 (độ tin cậy metadata trong hệ thống đầy đủ)
    C7   như C6 nhưng bảng lấy từ gold (cận trên của khối chọn bảng)
    C6r  chạy lại C6 để đo dao động giữa các lần chạy

Results are cached per (config, model, case) under reports/ablation/, so an
interrupted run resumes.  ``--today`` is fixed so relative dates are reproducible.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[2]
sys.path[:0] = [str(REPO / "src"), str(REPO)]

import duckdb  # noqa: E402

from t2s.evaluation.selective_scoring import disputed_case_ids, grade, score_case, summarise  # noqa: E402
from t2s.verified_context.llm import OpenAICompatibleCompleter  # noqa: E402
from t2s.verified_context.pipeline import (  # noqa: E402
    PipelineConfig,
    VerifiedContextAssets,
    VerifiedContextPipeline,
)

import httpx  # noqa: E402

# Lỗi phía nhà cung cấp (hết credit, rate limit, timeout) không phải kết quả của hệ thống:
# không ghi vào cache để lần chạy sau thử lại đúng các case đó.
PROVIDER_ERRORS = (httpx.HTTPStatusError, httpx.TransportError)

CASES = ROOT / "benchmark_v2" / "cases.jsonl"
OUT = ROOT / "reports" / "ablation"
TODAY = date(2026, 9, 24)

OFF = dict(profile=False, conventions=False, definitions=False, verify=False, gates=False)
CONFIGS = {
    "C1": PipelineConfig(name="C1", metadata="M0", **OFF),
    "C2": PipelineConfig(name="C2", metadata="M1", **OFF),
    "C3": PipelineConfig(name="C3", metadata="M2", profile=True, conventions=False, definitions=False, verify=False, gates=False),
    "C4": PipelineConfig(name="C4", metadata="M2", profile=True, conventions=True, verify=False, gates=False),
    "C5": PipelineConfig(name="C5", metadata="M2", profile=True, conventions=True, verify=True, gates=False),
    "C6": PipelineConfig(name="C6"),
    "C6m1": PipelineConfig(name="C6m1", metadata="M1"),
    "C7": PipelineConfig(name="C7", linker="oracle"),
    # Lặp lại C6 y hệt để đo dao động giữa hai lần chạy (provider không tất định dù temperature=0).
    "C6r": PipelineConfig(name="C6r"),
}


def load_env() -> tuple[str, str]:
    env = {}
    for line in (REPO / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    base = os.getenv("VLLM_BASE_URL") or env.get("VLLM_BASE_URL") or "https://openrouter.ai/api/v1"
    key = os.getenv("LLM_API_KEY") or env.get("LLM_API_KEY") or ""
    return base, key


def rows_of(con: duckdb.DuckDBPyConnection, sql: str) -> list[tuple]:
    return con.execute(sql).fetchall()


async def run_legacy(question: str, model: str) -> dict:
    """B0: DuckDBRuntime cũ, đóng băng trong scripts/baselines (commit 8301397)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent / "baselines"))
    from legacy_duckdb_runtime import DuckDBRuntime

    from t2s.configuration.settings import Settings

    rt = DuckDBRuntime(ROOT / "generated" / "vtnet.duckdb", model, Settings())
    res = await rt.run_pipeline(question, [])
    sql = res.get("candidate_sql") or ""
    status = "answered" if sql and not res.get("is_execution_failed") else "error"
    return {"status": status, "sql": sql, "message": res.get("error_message") or "", "trace": []}


async def run_case(case: dict, config_name: str, model: str, pipelines: dict, sem: asyncio.Semaphore) -> dict:
    async with sem:
        t0 = time.perf_counter()
        q = case["question_natural"]
        try:
            if config_name == "B0":
                out = await run_legacy(q, model)
            else:
                oracle = case.get("required_tables") if case["expected_outcome"] == "answer" else None
                res = await pipelines[config_name].run(q, oracle_tables=oracle, today=TODAY)
                out = {
                    "status": res.status, "sql": res.sql, "message": res.message,
                    "options": res.options, "tables": res.tables, "conventions": res.conventions,
                    "violations": res.violations, "repairs": res.repairs,
                    "prompt_tokens": res.prompt_tokens, "completion_tokens": res.completion_tokens,
                    "trace": [{"name": t.name, "status": t.status, "detail": t.detail[:300]} for t in res.trace],
                }
        except Exception as exc:  # noqa: BLE001 - một case lỗi không được dừng cả lượt chạy
            out = {"status": "error", "sql": "", "message": f"{type(exc).__name__}: {exc}"[:500], "trace": []}
            if isinstance(exc, PROVIDER_ERRORS):
                out["provider_failure"] = True
        out["latency_s"] = round(time.perf_counter() - t0, 2)
        return {"id": case["id"], **out}


def score(case: dict, rec: dict, con: duckdb.DuckDBPyConnection) -> dict:
    pred_rows = None
    status = rec["status"]
    if status == "answered":
        try:
            pred_rows = rows_of(con, rec["sql"])
        except duckdb.Error as exc:
            status, rec["message"] = "error", str(exc)
    gold_rows = rows_of(con, case["gold_sql_duckdb"]) if case["expected_outcome"] == "answer" else None
    options = [rows_of(con, o["gold_sql_duckdb"]) for o in case.get("clarification_options") or [] if o.get("gold_sql_duckdb")]
    s = score_case(case, status, pred_rows, gold_rows, options)
    return {**rec, "status": status, "verdict": s.verdict, "grade": grade(s), "silent_wrong": s.silent_wrong,
            "numbers_only": s.numbers_only, "expected": case["expected_outcome"],
            "pred_row_count": None if pred_rows is None else len(pred_rows)}, s


def rescore(folder: Path, cases: list[dict]) -> int:
    con = duckdb.connect(str(ROOT / "generated" / "vtnet.duckdb"), read_only=True)
    by_id = {c["id"]: c for c in cases}
    summary = {}
    for path in sorted(folder.glob("*.jsonl")):
        if path.name.endswith(".scored.jsonl"):
            continue
        recs = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            recs[rec["id"]] = rec
        scored, scores = [], []
        for cid in sorted(recs):
            if cid in by_id:
                rec, s = score(by_id[cid], dict(recs[cid]), con)
                scored.append(rec)
                scores.append(s)
        (folder / f"{path.stem}.scored.jsonl").write_text(
            "\n".join(json.dumps(r, ensure_ascii=False, default=str) for r in scored) + "\n", encoding="utf-8")
        summary[path.stem] = {**summarise(scores, disputed_case_ids(cases)), "scored_cases": len(scores)}
        print(f"[{path.stem}] n={len(scores)} EX={summary[path.stem]['execution_accuracy']}", flush=True)
    (folder / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--configs", default="C1,C2,C3,C4,C5,C6,C6m1,C7")
    ap.add_argument("--model", default="openai/gpt-oss-120b")
    ap.add_argument("--cases", default="all", help="all hoặc danh sách id, phân cách bởi dấu phẩy")
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--rescore", help="chỉ chấm lại mọi <config>.jsonl trong thư mục này, không gọi LLM")
    args = ap.parse_args()

    base, key = load_env()
    os.environ.setdefault("VLLM_BASE_URL", base)
    os.environ.setdefault("LLM_API_KEY", key)
    cases = [json.loads(x) for x in CASES.read_text(encoding="utf-8").splitlines() if x.strip()]
    cases = [c for c in cases if not c.get("exclude_from_scoring")]
    if args.cases != "all":
        wanted = set(args.cases.split(","))
        cases = [c for c in cases if c["id"] in wanted]

    if args.rescore:
        return rescore(Path(args.rescore), cases)

    assets = VerifiedContextAssets.from_dataset(ROOT)
    completer = OpenAICompatibleCompleter(base_url=base, api_key=key, model=args.model)
    names = args.configs.split(",")
    pipelines = {n: VerifiedContextPipeline(assets, completer, CONFIGS[n]) for n in names if n != "B0"}
    sem = asyncio.Semaphore(args.concurrency)
    con = duckdb.connect(str(assets.db_path), read_only=True)
    model_tag = args.model.split("/")[-1]
    summary = {}
    for name in names:
        path = OUT / model_tag / f"{name}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        done = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                rec = json.loads(line)
                done[rec["id"]] = rec
        todo = [c for c in cases if c["id"] not in done]
        failures = 0
        print(f"[{name}] {len(done)} có sẵn, chạy {len(todo)} case", flush=True)
        with path.open("a", encoding="utf-8") as fh:
            for coro in asyncio.as_completed([run_case(c, name, args.model, pipelines, sem) for c in todo]):
                rec = await coro
                if rec.get("provider_failure"):
                    failures += 1
                    continue
                done[rec["id"]] = rec
                fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
                fh.flush()
        if failures:
            print(f"[{name}] {failures} case lỗi phía provider, chưa ghi; chạy lại để bù", flush=True)
        by_id = {c["id"]: c for c in cases}
        scored, scores = [], []
        for cid in sorted(done):
            if cid not in by_id:
                continue
            rec, s = score(by_id[cid], dict(done[cid]), con)
            scored.append(rec)
            scores.append(s)
        (OUT / model_tag / f"{name}.scored.jsonl").write_text(
            "\n".join(json.dumps(r, ensure_ascii=False, default=str) for r in scored) + "\n", encoding="utf-8")
        summary[name] = summarise(scores, disputed_case_ids(cases))
        s = summary[name]
        print(f"[{name}] EX={s['execution_accuracy']} silent={s['silent_error_rate']} "
              f"coverage={s['coverage']} declineP={s['decline_precision']} declineR={s['decline_recall']}", flush=True)
    summary_path = OUT / model_tag / "summary.json"
    old = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    old.update(summary)
    summary_path.write_text(json.dumps(old, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
