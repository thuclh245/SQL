from pathlib import Path

from t2s.benchmark.case_loader import BenchmarkCaseFilter, load_benchmark_cases


def test_benchmark_loader_exposes_only_inference_fields_to_runtime(tmp_path: Path) -> None:
    dataset_path = tmp_path / "dataset.jsonl"
    dataset_path.write_text(
        (
            '{"case_id":"case-1","question_id":7,"db_id":"db","question":"Q",'
            '"evidence":"hint","bird_gold_sql":"SECRET GOLD SQL",'
            '"bird_difficulty":"simple","t2s_stratum":"S1",'
            '"inference":{"question":"Q","db_id":"db","evidence":"hint"},'
            '"gold":{"sql_original":"SECRET GOLD SQL","sql_corrected":"SECRET CURATED SQL"}}\n'
        ),
        encoding="utf-8",
    )

    case_bundle = load_benchmark_cases(dataset_path)[0]

    assert case_bundle.inference_case.case_id == "case-1"
    assert case_bundle.inference_case.question_id == 7
    assert case_bundle.inference_case.db_id == "db"
    assert not hasattr(case_bundle.inference_case, "bird_gold_sql")
    assert not hasattr(case_bundle.inference_case, "gold")
    assert case_bundle.scoring_gold.official_sql == "SECRET GOLD SQL"


def test_benchmark_loader_filters_by_case_db_and_limit(tmp_path: Path) -> None:
    dataset_path = tmp_path / "dataset.jsonl"
    dataset_path.write_text(
        "\n".join(
            [
                (
                    '{"case_id":"case-1","source":{"question_id":1},'
                    '"inference":{"question":"Q1","db_id":"db_a"}}'
                ),
                (
                    '{"case_id":"case-2","source":{"question_id":2},'
                    '"inference":{"question":"Q2","db_id":"db_b"}}'
                ),
                (
                    '{"case_id":"case-3","source":{"question_id":3},'
                    '"inference":{"question":"Q3","db_id":"db_b"}}'
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    filtered_cases = load_benchmark_cases(
        dataset_path,
        BenchmarkCaseFilter(limit=1, db_ids=frozenset({"db_b"})),
    )

    assert [case.inference_case.case_id for case in filtered_cases] == ["case-2"]
