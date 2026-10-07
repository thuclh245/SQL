"""Kiem dinh he thong PK / FK / relationship / cardinality / kha nang do luong.

Bo sung cho validate.py: validate.py kiem tra ~20 quan he chon tay va cac bat bien
so hoc; script nay quet TOAN BO khoa va quan he, roi do xem du lieu co du kha nang
phan biet SQL dung voi SQL sai hay khong.

    python3 audit_integrity.py                # 10 schema dau
    python3 audit_integrity.py --all          # toan bo 20 schema
    python3 audit_integrity.py --json out.json
"""
from __future__ import annotations
import argparse, collections, json, os, re, sqlite3, sys

HERE = os.path.dirname(os.path.abspath(__file__))
GEN = os.path.join(HERE, "generated")
FIRST_10 = ["aaa", "aam", "acs", "billing", "capacity", "core",
            "customer", "energy", "experience", "fault"]


class Audit:
    def __init__(self, scope: list[str] | None):
        self.con = sqlite3.connect(os.path.join(GEN, "telecom.sqlite"))
        self.catalog = json.load(open(os.path.join(GEN, "catalog.json")))
        self.rel = json.load(open(os.path.join(GEN, "schema_relationships.json")))
        self.counts = json.load(open(os.path.join(GEN, "counts.json")))
        self.by_fqn = {f"{e['schema']}.{e['table']}": e for e in self.catalog}
        self.scope = scope or sorted({e["schema"] for e in self.catalog})
        self.tables = [e for e in self.catalog if e["schema"] in self.scope]
        self.db_tables = {r[0] for r in self.con.execute(
            "select name from sqlite_master where type='table'")}
        self.findings: dict[str, list[str]] = collections.defaultdict(list)
        self.stats: dict[str, object] = {}

    # -- tien ich ------------------------------------------------------------
    def add(self, code: str, msg: str) -> None:
        self.findings[code].append(msg)

    def scalar(self, sql: str):
        return self.con.execute(sql).fetchone()[0]

    def cols(self, table: str) -> dict[str, str]:
        return {r[1]: r[2] for r in self.con.execute(f'PRAGMA table_info("{table}")')}

    # -- 1. khoa chinh -------------------------------------------------------
    def check_primary_keys(self) -> None:
        for e in self.tables:
            fqn, t = f"{e['schema']}.{e['table']}", e["sqlite_table"]
            if t not in self.db_tables:
                self.add("T_MISSING", f"{fqn}: khong ton tai trong sqlite")
                continue
            pk, columns = e["primary_key"], self.cols(t)
            if not pk:
                self.add("PK_NONE", f"{fqn}: khong khai bao PK")
                continue
            if missing := [k for k in pk if k not in columns]:
                self.add("PK_COL_MISSING", f"{fqn}: PK khai {missing} nhung cot khong ton tai")
                continue
            n = self.scalar(f'select count(*) from "{t}"')
            if n == 0:
                self.add("T_EMPTY", f"{fqn}: bang rong")
            for k in pk:
                if nulls := self.scalar(f'select count(*) from "{t}" where "{k}" is null'):
                    self.add("PK_NULL", f"{fqn}.{k}: {nulls}/{n} dong NULL trong PK")
            expr = ", ".join(f'"{k}"' for k in pk)
            dup = self.scalar(
                f'select count(*) from (select {expr} from "{t}" group by {expr} having count(*)>1)')
            if dup:
                self.add("PK_DUP", f"{fqn}: PK({','.join(pk)}) trung tai {dup} gia tri")
            if e.get("row_count") not in (None, n):
                self.add("ROWCOUNT_MISMATCH", f"{fqn}: catalog ghi {e['row_count']}, sqlite co {n}")
            if self.counts.get(fqn) not in (None, n):
                self.add("ROWCOUNT_MISMATCH", f"{fqn}: counts.json ghi {self.counts[fqn]}, sqlite co {n}")

    # -- 2. khoa ngoai -------------------------------------------------------
    def check_foreign_keys(self) -> list[tuple]:
        edges, fan_in, coverage = [], [], []
        for e in self.tables:
            fqn, t = f"{e['schema']}.{e['table']}", e["sqlite_table"]
            if t not in self.db_tables:
                continue
            src_cols = self.cols(t)
            for fk in e["foreign_keys"]:
                col, ref = fk["column"], fk["references"]
                parts = ref.split(".")
                if len(parts) != 3:
                    self.add("FK_REF_MALFORMED", f"{fqn}.{col} -> '{ref}' sai dang schema.table.column")
                    continue
                rschema, rtable, rcol = parts
                rfqn = f"{rschema}.{rtable}"
                edges.append((fqn, col, rfqn, rcol))
                if col not in src_cols:
                    self.add("FK_COL_MISSING", f"{fqn}.{col} -> {ref}: cot nguon khong ton tai")
                    continue
                target = self.by_fqn.get(rfqn)
                if target is None or target["sqlite_table"] not in self.db_tables:
                    self.add("FK_TARGET_TABLE_MISSING", f"{fqn}.{col} -> {ref}: bang dich khong ton tai")
                    continue
                tt = target["sqlite_table"]
                tgt_cols = self.cols(tt)
                if rcol not in tgt_cols:
                    self.add("FK_TARGET_COL_MISSING", f"{fqn}.{col} -> {ref}: cot dich khong ton tai")
                    continue
                if src_cols[col].lower() != tgt_cols[rcol].lower():
                    self.add("FK_TYPE_MISMATCH",
                             f"{fqn}.{col}({src_cols[col]}) -> {ref}({tgt_cols[rcol]}): lech kieu")
                if rcol not in (target["primary_key"] or []):
                    self.add("FK_TARGET_NOT_PK",
                             f"{fqn}.{col} -> {ref}: cot dich khong phai PK (PK={target['primary_key']})")
                distinct = self.scalar(f'select count(distinct "{rcol}") from "{tt}" where "{rcol}" is not null')
                non_null = self.scalar(f'select count(*) from "{tt}" where "{rcol}" is not null')
                if distinct != non_null:
                    self.add("FK_TARGET_NOT_UNIQUE",
                             f"{fqn}.{col} -> {ref}: cot dich khong duy nhat ({distinct}/{non_null})")

                n = self.scalar(f'select count(*) from "{t}"')
                bound = self.scalar(f'select count(*) from "{t}" where "{col}" is not null')
                if n and bound == 0:
                    self.add("FK_ALL_NULL", f"{fqn}.{col} -> {ref}: toan bo {n} dong NULL")
                    continue
                orphan = self.scalar(
                    f'select count(*) from "{t}" s where s."{col}" is not null '
                    f'and not exists (select 1 from "{tt}" d where d."{rcol}" = s."{col}")')
                if orphan:
                    self.add("FK_ORPHAN", f"{fqn}.{col} -> {ref}: {orphan}/{bound} dong mo coi")
                mx = self.scalar(
                    f'select coalesce(max(c),0) from (select count(*) c from "{t}" '
                    f'where "{col}" is not null group by "{col}")')
                fan_in.append((mx, f"{fqn}.{col} -> {ref}"))
                used = self.scalar(f'select count(distinct "{col}") from "{t}" where "{col}" is not null')
                tgt_rows = self.scalar(f'select count(*) from "{tt}"')
                if tgt_rows:
                    coverage.append((used / tgt_rows, f"{fqn}.{col} -> {ref}", used, tgt_rows))
        flat = sum(1 for mx, _ in fan_in if mx <= 1)
        self.stats["fan_in"] = {"n_fk": len(fan_in), "flat_1_to_1": flat,
                                "distribution": dict(sorted(collections.Counter(m for m, _ in fan_in).items()))}
        self.stats["coverage_below_50pct"] = sum(1 for c in coverage if c[0] < 0.5)
        for mx, name in sorted(fan_in)[:0]:
            pass
        if flat:
            for mx, name in fan_in:
                if mx <= 1:
                    self.add("FANIN_FLAT", f"{name}: max fan-in = 1, du lieu khong co phia many")
        for ratio, name, used, total in sorted(coverage):
            if ratio < 0.2:
                self.add("FK_LOW_COVERAGE", f"{name}: chi {used}/{total} dong dich duoc tham chieu ({ratio:.1%})")
        return edges

    # -- 3. do thi quan he ---------------------------------------------------
    def check_relationship_graph(self, fk_edges: list[tuple]) -> None:
        seen = collections.Counter()
        graph_edges = set()
        for r in self.rel["relationships"]:
            key = (r["from_table"], r["from_column"], r["to_table"], r["to_column"])
            seen[key] += 1
            if key[0].split(".")[0] in self.scope:
                graph_edges.add(key)
        for key, n in seen.items():
            if n > 1 and key[0].split(".")[0] in self.scope:
                self.add("REL_DUPLICATE", f"{key[0]}.{key[1]} -> {key[2]}.{key[3]}: khai {n} lan")
        catalog_edges = set(fk_edges)
        for k in sorted(catalog_edges - graph_edges):
            self.add("REL_MISSING_IN_GRAPH",
                     f"{k[0]}.{k[1]} -> {k[2]}.{k[3]}: co trong catalog.json, thieu trong schema_relationships.json")
        for k in sorted(graph_edges - catalog_edges):
            self.add("REL_EXTRA_IN_GRAPH",
                     f"{k[0]}.{k[1]} -> {k[2]}.{k[3]}: co trong schema_relationships.json, khong co trong catalog.json")

        for r in self.rel["relationships"]:
            ft, fc, tt_, tc_ = r["from_table"], r["from_column"], r["to_table"], r["to_column"]
            if ft.split(".")[0] not in self.scope:
                continue
            src, tgt = self.by_fqn.get(ft), self.by_fqn.get(tt_)
            if not src or not tgt:
                continue
            a, b = src["sqlite_table"], tgt["sqlite_table"]
            if a not in self.db_tables or b not in self.db_tables:
                continue
            if fc not in self.cols(a) or tc_ not in self.cols(b):
                continue
            a_unique = self.scalar(f'select count(*)=count(distinct "{fc}") from "{a}" where "{fc}" is not null')
            b_unique = self.scalar(f'select count(*)=count(distinct "{tc_}") from "{b}" where "{tc_}" is not null')
            observed = ("one" if a_unique else "many") + "_to_" + ("one" if b_unique else "many")
            declared = r.get("cardinality")
            if declared and declared != observed:
                self.add("CARD_MISMATCH", f"{ft}.{fc} -> {tt_}.{tc_}: khai '{declared}', do duoc '{observed}'")

    # -- 4. grain ------------------------------------------------------------
    def check_grain(self) -> None:
        declared = {t["name"]: t.get("grain", "") for t in self.rel["tables"]}
        for e in self.tables:
            fqn, t = f"{e['schema']}.{e['table']}", e["sqlite_table"]
            if t not in self.db_tables:
                continue
            grain = declared.get(fqn, "")
            if not grain.startswith("unique by "):
                continue
            keys = [k.strip() for k in grain[len("unique by "):].split(",")]
            columns = self.cols(t)
            if not all(k in columns for k in keys):
                self.add("GRAIN_COL_MISSING", f"{fqn}: grain '{grain}' tham chieu cot khong ton tai")
                continue
            expr = ", ".join(f'"{k}"' for k in keys)
            dup = self.scalar(
                f'select count(*) from (select {expr} from "{t}" group by {expr} having count(*)>1)')
            if dup:
                self.add("GRAIN_VIOLATED", f"{fqn}: grain '{grain}' bi vi pham tai {dup} to hop")

    # -- 5. kha nang do luong ------------------------------------------------
    def check_measurability(self) -> None:
        """Du lieu co du de phan biet SQL dung voi SQL sai khong."""
        total_cols = real_nulls = empty_str = dead = const = 0
        nullable_fk = 0
        scd_empty = []
        for e in self.tables:
            t = e["sqlite_table"]
            if t not in self.db_tables:
                continue
            rows = self.scalar(f'select count(*) from "{t}"')
            if rows == 0:
                continue
            fk_cols = {fk["column"] for fk in e["foreign_keys"]}
            for c in e["columns"]:
                name = c["name"]
                if name not in self.cols(t):
                    continue
                total_cols += 1
                nulls = self.scalar(f'select count(*) from "{t}" where "{name}" is null')
                blanks = self.scalar(f'select count(*) from "{t}" where "{name}" = \'\'')
                distinct = self.scalar(f'select count(distinct "{name}") from "{t}"')
                if nulls:
                    real_nulls += 1
                    if name in fk_cols:
                        nullable_fk += 1
                if blanks:
                    empty_str += 1
                if blanks == rows:
                    dead += 1
                elif distinct <= 1:
                    const += 1
                if re.search(r"(_to|_until|_end)$", name) and blanks == rows:
                    scd_empty.append(f"{e['schema']}.{e['table']}.{name}")
            if rows < 10:
                self.add("T_TOO_SMALL", f"{e['schema']}.{e['table']}: chi {rows} dong")
        self.stats["columns"] = {
            "total": total_cols, "with_real_null": real_nulls, "with_empty_string": empty_str,
            "dead_all_blank": dead, "constant_single_value": const,
        }
        self.stats["nullable_fk_columns"] = nullable_fk
        if nullable_fk == 0:
            self.add("NO_NULLABLE_FK",
                     "Khong FK nao co NULL va khong co dong mo coi => LEFT JOIN tuong duong INNER JOIN "
                     "tren toan bo du lieu; moi loi chon sai kieu join deu vo hinh.")
        if real_nulls <= 1:
            self.add("NO_NULL_SEMANTICS",
                     f"Chi {real_nulls}/{total_cols} cot co NULL that => khong kiem duoc COUNT(col) vs COUNT(*), "
                     "IS NULL, COALESCE hay khac biet LEFT/INNER JOIN.")
        for name in scd_empty:
            self.add("SCD_WINDOW_UNUSABLE",
                     f"{name}: 100% chuoi rong, khong co ban ghi da dong => 'WHERE ... IS NULL' tra 0 dong, "
                     "SQL loc cua so hieu luc DUNG se bi cham SAI")

    # -- 6. bang la ----------------------------------------------------------
    def check_stray_tables(self) -> None:
        known = {e["sqlite_table"] for e in self.catalog}
        for t in sorted(self.db_tables - known):
            self.add("T_STRAY_IN_DB", f"{t}: co trong sqlite nhung khong co trong catalog.json")

    def run(self) -> None:
        self.check_primary_keys()
        edges = self.check_foreign_keys()
        self.check_relationship_graph(edges)
        self.check_grain()
        self.check_measurability()
        self.check_stray_tables()


SEVERITY = {
    "BLOCKER": ["T_MISSING", "PK_NONE", "PK_COL_MISSING", "PK_NULL", "PK_DUP",
                "FK_REF_MALFORMED", "FK_COL_MISSING", "FK_TARGET_TABLE_MISSING",
                "FK_TARGET_COL_MISSING", "FK_ORPHAN", "GRAIN_VIOLATED",
                "REL_MISSING_IN_GRAPH", "REL_EXTRA_IN_GRAPH"],
    "CAO":     ["SCD_WINDOW_UNUSABLE", "NO_NULL_SEMANTICS", "NO_NULLABLE_FK",
                "FK_TARGET_NOT_PK", "FK_TARGET_NOT_UNIQUE", "T_STRAY_IN_DB",
                "ROWCOUNT_MISMATCH", "FK_TYPE_MISMATCH", "FK_ALL_NULL"],
    "TRUNG":   ["CARD_MISMATCH", "FANIN_FLAT", "T_TOO_SMALL", "FK_LOW_COVERAGE",
                "T_EMPTY", "GRAIN_COL_MISSING", "REL_DUPLICATE"],
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="quet ca 20 schema")
    ap.add_argument("--json", metavar="FILE", help="ghi ket qua ra JSON")
    ap.add_argument("--max-lines", type=int, default=8, help="so dong vi du moi nhom")
    args = ap.parse_args()

    audit = Audit(None if args.all else FIRST_10)
    audit.run()

    n_fk = sum(len(e["foreign_keys"]) for e in audit.tables)
    print(f"PHAM VI: {len(audit.scope)} schema · {len(audit.tables)} bang · {n_fk} FK\n")
    total = 0
    for level, codes in SEVERITY.items():
        hits = [(c, audit.findings[c]) for c in codes if c in audit.findings]
        if not hits:
            continue
        print(f"{'='*70}\n{level}\n{'='*70}")
        for code, msgs in hits:
            total += len(msgs)
            print(f"\n[{code}] {len(msgs)} truong hop")
            for m in msgs[:args.max_lines]:
                print(f"   - {m}")
            if len(msgs) > args.max_lines:
                print(f"   ... con {len(msgs) - args.max_lines}")
        print()
    unknown = set(audit.findings) - {c for cs in SEVERITY.values() for c in cs}
    for code in sorted(unknown):
        total += len(audit.findings[code])
        print(f"[{code}] {len(audit.findings[code])}")

    print(f"\nTHONG KE: {json.dumps(audit.stats, ensure_ascii=False)}")
    print(f"TONG PHAT HIEN: {total}")

    if args.json:
        with open(args.json, "w") as fh:
            json.dump({"scope": audit.scope, "stats": audit.stats,
                       "findings": {k: v for k, v in audit.findings.items()}}, fh,
                      ensure_ascii=False, indent=2)
        print(f"Da ghi {args.json}")
    return 1 if any(c in audit.findings for c in SEVERITY["BLOCKER"]) else 0


if __name__ == "__main__":
    sys.exit(main())
