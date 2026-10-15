from pathlib import Path

import pytest

from app.embed import HashingEmbedder
from app.ingest.analysis import analyze_source
from app.ingest.parser import parse_source
from app.ingest.walker import iter_source_files
from evals import metrics
from evals.dataset import load_dataset
from evals.runner import check_thresholds, flatten, run_eval

DATASETS_DIR = Path(__file__).parent.parent / "evals" / "datasets"
DATASET = DATASETS_DIR / "shop_api.json"
ALL_DATASETS = sorted(DATASETS_DIR.glob("*.json"))


# ------------------------------------------------------------------ metrics


def test_rank_and_recall_metrics():
    retrieved = ["a", "b", "c", "d"]
    relevant = {"c", "z"}

    assert metrics.first_relevant_rank(retrieved, relevant) == 3
    assert metrics.hit_at_k(retrieved, relevant, 2) == 0.0
    assert metrics.hit_at_k(retrieved, relevant, 3) == 1.0
    assert metrics.recall_at_k(retrieved, relevant, 4) == 0.5
    assert metrics.reciprocal_rank(retrieved, relevant) == pytest.approx(1 / 3)
    assert metrics.reciprocal_rank(["x"], relevant) == 0.0


def test_percentile_nearest_rank():
    values = [10, 20, 30, 40, 50]

    assert metrics.percentile(values, 50) == 30
    assert metrics.percentile(values, 95) == 50
    assert metrics.percentile([], 95) == 0.0


def test_score_endpoints_reports_missing_spurious_and_mismatches():
    expected = [
        {"method": "POST", "path": "/login", "handles_authentication": True, "requires_auth": False},
        {"method": "GET", "path": "/me", "handles_authentication": False, "requires_auth": True},
        {"method": "GET", "path": "/gone", "handles_authentication": False, "requires_auth": False},
    ]
    found = [
        {"method": "POST", "path": "/login", "handles_authentication": True, "requires_auth": False},
        {"method": "GET", "path": "/me", "handles_authentication": False, "requires_auth": False,
         "evidence": []},
        {"method": "GET", "path": "/extra", "handles_authentication": False, "requires_auth": False},
    ]

    s = metrics.score_endpoints(expected, found)

    assert s["missing"] == ["GET /gone"]
    assert s["spurious"] == ["GET /extra"]
    assert s["detection"]["recall"] == pytest.approx(2 / 3)
    assert s["classification_accuracy"] == 0.5
    assert [m["route"] for m in s["mismatches"]] == ["GET /me"]
    assert s["requires_auth"]["recall"] == 0.0


def test_check_thresholds():
    flat = {"retrieval.hit@1": 0.7, "endpoints.auth_f1": 1.0}

    assert check_thresholds(flat, {"min": {"retrieval.hit@1": 0.7, "endpoints.auth_f1": 0.9}}) == []
    failures = check_thresholds(flat, {"min": {"retrieval.hit@1": 0.8, "answers.must_mention": 0.5}})
    assert len(failures) == 2
    assert "0.700 < floor 0.800" in failures[0]
    assert "not measured" in failures[1]
    assert check_thresholds({"latency_ms.p95": 900}, {"max": {"latency_ms.p95": 500}})


# --------------------------------------- dataset labels vs the benchmark app
# These run offline: they catch a mislabelled dataset before it can corrupt
# every future eval number.


def _repo_facts(path: Path = DATASET):
    ds = load_dataset(path)
    chunk_ids, endpoints = set(), set()
    for rel, language, path in iter_source_files(ds.repo_path):
        data = path.read_bytes()
        chunk_ids |= {f"{rel}::{c.qualified_name}" for c in parse_source(data, language)}
        endpoints |= {(e.method, e.path) for e in analyze_source(data, language).endpoints}
    return ds, chunk_ids, endpoints


@pytest.mark.parametrize("path", ALL_DATASETS, ids=lambda p: p.stem)
def test_every_relevant_label_points_at_a_real_chunk(path):
    ds, chunk_ids, _ = _repo_facts(path)

    unknown = {r for q in ds.questions for r in q.relevant} - chunk_ids

    assert unknown == set()


@pytest.mark.parametrize("path", ALL_DATASETS, ids=lambda p: p.stem)
def test_labelled_endpoints_match_what_the_analyzer_detects(path):
    ds, _, detected = _repo_facts(path)

    expected = {(e["method"], e["path"]) for e in ds.endpoints}

    assert expected == detected


# ----------------------------------------------------------- full run (DB)


def test_run_eval_end_to_end(conn):
    ds = load_dataset(DATASET)

    def fake_chat(messages):
        return "See [1] for details; it mentions /auth/login and charge_card."

    report = run_eval(conn, ds, HashingEmbedder(), None, answers=True, chat=fake_chat)

    assert report["dataset"] == "shop_api"
    assert report["ingest"]["files_indexed"] > 10
    assert len(report["questions"]) == len(ds.questions)
    for key, value in report["retrieval"].items():
        assert 0.0 <= value <= 1.0, key
    assert report["endpoints"]["detection"]["recall"] == 1.0
    assert report["endpoints"]["detection"]["precision"] == 1.0
    assert report["answers"]["answered"] == len(ds.questions)
    assert report["answers"]["citations_valid"] == 1.0

    flat = flatten(report)
    assert "retrieval.mrr" in flat and "endpoints.classification_accuracy" in flat

    # run_eval cleans up the repo it indexed
    left = conn.execute("SELECT count(*) FROM repos WHERE path = %s", (str(ds.repo_path),)).fetchone()[0]
    assert left == 0


def test_every_dataset_is_covered_by_the_gate():
    import json

    table = json.loads((DATASETS_DIR.parent / "thresholds.json").read_text())
    for config, entry in table.items():
        for path in ALL_DATASETS:
            name = load_dataset(path).name
            assert name in entry.get("datasets", {}) or "min" in entry, (config, name)
