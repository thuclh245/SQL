"""Robust incremental runner for Phase P2 with live progress and automatic resume."""

import asyncio
import json
import os
import sqlite3
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from t2s.integrations.openai_compatible import OpenAICompatibleChatClient
from t2s.solver.solver_response import build_sql_candidate_json_schema
from t2s.benchmark.scoring import evaluate_candidate_vs_gold

ROOT = Path(__file__).resolve().parents[2]
BENCH_DIR = ROOT / "benchmarks" / "synthetic_solver_ceiling"
RESULTS_DIR = ROOT / "results" / "solver_capability_boundary"
PAYLOADS_DIR = RESULTS_DIR / "payloads"
OUT_FILE = RESULTS_DIR / "case_results.jsonl"

RESULTS_DIR.mkdir(parents=True, exist_ok=True)
PAYLOADS_DIR.mkdir(parents=True, exist_ok=True)

DB_DIR = BENCH_DIR / "databases"
META_DIR = BENCH_DIR / "metadata"
CASES_FILE = BENCH_DIR / "datasets" / "cases.jsonl"

SYSTEM_PROMPT = """You are a read-only enterprise SQL solver.

Use only the authorized database information, relationships, values, glossary, and schema supplied in the user message.
Use sql_identifier values when writing SQL relation references; catalog_fqn values are provenance and authorization identities, not executable SQL names.
Do not invent tables, columns, business definitions, literal values, credentials, or infrastructure details.
Generate exactly one read-only SQL statement for the requested dialect.
Choose the necessary joins, filters, grouping, set operations and query structure yourself.
Do not assume a database fact that is not supported by supplied context.
Return only the required structured output fields."""


def get_db_schema_summary(db_path: Path) -> str:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    tables = [r[0] for r in cur.fetchall()]
    schema_parts = []
    for t in tables:
        cur.execute(f"PRAGMA table_info({t});")
        cols = cur.fetchall()
        cur.execute(f"PRAGMA foreign_key_list({t});")
        fks = cur.fetchall()
        col_strs = [f"  - name: {c[1]}; type: {c[2]}; nullable: {not c[3]}; primary_key: {bool(c[5])}" for c in cols]
        fk_strs = [f"  - from_column: {fk[3]}; to_table: {fk[2]}; to_column: {fk[4]}" for fk in fks]
        t_str = f"table: {t}\ncolumns:\n" + "\n".join(col_strs)
        if fk_strs:
            t_str += "\nforeign_keys:\n" + "\n".join(fk_strs)
        schema_parts.append(t_str)
    conn.close()
    return "\n\n".join(schema_parts)


def build_arm_contexts(case: dict) -> dict[str, str]:
    db_id = case["db_id"]
    domain = case["domain"]
    q = case["question"]
    db_path = DB_DIR / f"{db_id}.sqlite"
    full_raw_schema = get_db_schema_summary(db_path)
    
    meta_path = META_DIR / domain
    glossary = json.loads((meta_path / "glossary.json").read_text(encoding="utf-8"))
    grain = json.loads((meta_path / "grain.json").read_text(encoding="utf-8"))
    time_sem = json.loads((meta_path / "time_semantics.json").read_text(encoding="utf-8"))
    val_dict = json.loads((meta_path / "value_dictionary.json").read_text(encoding="utf-8"))
    
    fs_prompt = f"""Question:
<user_question>
{q}
</user_question>

Target dialect:
sqlite

Authorized schema:
<authorized_schema>
{full_raw_schema}
</authorized_schema>

Return a structured SqlCandidate with:
- sql
- dialect
- referenced_tables
- referenced_columns
- expected_columns
- assumptions
- unresolved
"""

    glossary_str = "\n".join(f"- {k}: {v}" for k, v in glossary.items())
    grain_str = "\n".join(f"- {k}: {v}" for k, v in grain.items())
    time_str = "\n".join(f"- {k}: {v}" for k, v in time_sem.items())
    val_str = "\n".join(f"- {k}: {', '.join(v)}" for k, v in val_dict.items())
    
    mg_prompt = f"""Question:
<user_question>
{q}
</user_question>

Target dialect:
sqlite

Authorized schema:
<authorized_schema>
{full_raw_schema}
</authorized_schema>

Authoritative Business Glossary:
<glossary>
{glossary_str}
</glossary>

Table Grain & Cardinality:
<grain>
{grain_str}
</grain>

Valid Enumerations & Code Mappings:
<value_dictionary>
{val_str}
</value_dictionary>

Time Semantics:
<time_semantics>
{time_str}
</time_semantics>

Return a structured SqlCandidate with:
- sql
- dialect
- referenced_tables
- referenced_columns
- expected_columns
- assumptions
- unresolved
"""

    gold_sql = case["gold_sql"].lower()
    all_table_blocks = full_raw_schema.split("\n\n")
    oracle_table_blocks = []
    for blk in all_table_blocks:
        lines = blk.splitlines()
        if lines and lines[0].startswith("table: "):
            t_name = lines[0].replace("table: ", "").strip()
            if t_name in gold_sql:
                oracle_table_blocks.append(blk)
    oracle_schema_str = "\n\n".join(oracle_table_blocks) if oracle_table_blocks else full_raw_schema
    
    or_prompt = f"""Question:
<user_question>
{q}
</user_question>

Target dialect:
sqlite

Diagnostic Context (Strictly Relevant Database Facts):
<authorized_schema>
{oracle_schema_str}
</authorized_schema>

Relevant Business Glossary:
<glossary>
{glossary_str}
</glossary>

Table Grain:
<grain>
{grain_str}
</grain>

Valid Enumerations & Code Mappings:
<value_dictionary>
{val_str}
</value_dictionary>

Return a structured SqlCandidate with:
- sql
- dialect
- referenced_tables
- referenced_columns
- expected_columns
- assumptions
- unresolved
"""
    return {"FS": fs_prompt, "MG": mg_prompt, "OR": or_prompt}


async def main():
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")
    model_name = os.getenv("T2S_LLM_MODEL", "openai/gpt-oss-120b")
    
    # Load completed keys
    completed_keys = set()
    if OUT_FILE.exists():
        with open(OUT_FILE, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        r = json.loads(line)
                        completed_keys.add((r["case_id"], r["arm"], r["replicate"]))
                    except Exception:
                        pass
                        
    print(f"=== Starting P2 Benchmark Execution (Total: 162 calls, Completed so far: {len(completed_keys)}) ===")
    print(f"Model: {model_name} | Concurrency: 8\n")
    
    chat_client = OpenAICompatibleChatClient(
        base_url=base_url,
        api_key=api_key,
        request_timeout_seconds=60.0,
        temperature=0.0
    )
    
    cases = []
    with open(CASES_FILE, encoding="utf-8") as f:
        for line in f:
            cases.append(json.loads(line))
            
    jobs = []
    for case in cases:
        case_id = case["case_id"]
        arm_contexts = build_arm_contexts(case)
        
        case_payload_dir = PAYLOADS_DIR / case_id
        case_payload_dir.mkdir(parents=True, exist_ok=True)
        for arm_name, prompt_text in arm_contexts.items():
            (case_payload_dir / f"{arm_name}.txt").write_text(prompt_text, encoding="utf-8")
            
        for arm_name in ["FS", "MG", "OR"]:
            for rep in range(1, 4):
                if (case_id, arm_name, rep) not in completed_keys:
                    jobs.append((case, arm_name, rep, arm_contexts[arm_name]))
                    
    print(f"Remaining jobs to run: {len(jobs)}")
    if not jobs:
        print("All 162 jobs are already completed!")
        return

    sem = asyncio.Semaphore(8) # 8 concurrent requests
    lock = asyncio.Lock()
    done_counter = len(completed_keys)
    
    async def worker(c, arm, rep, p_text):
        nonlocal done_counter
        cid = c["case_id"]
        db_id = c["db_id"]
        gold_sql = c["gold_sql"]
        db_path = DB_DIR / f"{db_id}.sqlite"
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": p_text},
        ]
        
        async with sem:
            t0 = time.perf_counter()
            cand_sql = ""
            assumptions = []
            cand_error = None
            is_correct = False
            cand_ok = False
            cand_rows = 0
            gold_rows = 0
            
            for attempt in range(3):
                try:
                    resp = await chat_client.generate_structured_response(
                        messages=messages,
                        response_schema=build_sql_candidate_json_schema(),
                        model_name=model_name,
                        reasoning_effort=None,
                        max_output_tokens=2048,
                    )
                    content = resp.content
                    if isinstance(content, str):
                        content = json.loads(content)
                    cand_sql = content.get("sql", "").strip()
                    assumptions = content.get("assumptions", [])
                    break
                except Exception as e:
                    if attempt == 2:
                        cand_error = f"API Error: {e}"
                    await asyncio.sleep(1.5 * (attempt + 1))
            
            elapsed = time.perf_counter() - t0
            
            if cand_sql:
                is_correct, cand_res, gold_res = evaluate_candidate_vs_gold(
                    candidate_sql=cand_sql,
                    gold_sql=gold_sql,
                    db_path=db_path,
                )
                cand_ok = cand_res.ok
                cand_error = cand_res.error
                cand_rows = len(cand_res.rows) if cand_res.ok else 0
                gold_rows = len(gold_res.rows) if gold_res.ok else 0
            
            record = {
                "case_id": cid,
                "domain": c["domain"],
                "arm": arm,
                "replicate": rep,
                "is_correct": is_correct,
                "cand_ok": cand_ok,
                "cand_error": cand_error,
                "cand_rows": cand_rows,
                "gold_rows": gold_rows,
                "cand_sql": cand_sql,
                "gold_sql": gold_sql,
                "assumptions": assumptions,
                "elapsed_seconds": round(elapsed, 2),
                "complexity_tags": c.get("complexity_tags", {})
            }
            
            async with lock:
                done_counter += 1
                with open(OUT_FILE, "a", encoding="utf-8") as out_f:
                    out_f.write(json.dumps(record) + "\n")
                status = "CORRECT" if is_correct else ("EXEC_ERR" if not cand_ok else "WRONG")
                print(f"[{done_counter:03d}/162] {cid} | {arm} r{rep} -> {status} ({elapsed:.2f}s)", flush=True)

    await asyncio.gather(*(worker(c, arm, rep, p_text) for c, arm, rep, p_text in jobs))
    print(f"\nAll 162 runs finished successfully!")

if __name__ == "__main__":
    asyncio.run(main())
