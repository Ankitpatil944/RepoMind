"""CLI: python -m evals.run [--embedder hashing|fastembed] [--answers] ...

Exit code 1 if any metric falls below the committed floor in
evals/thresholds.json (the CI regression gate)."""

import argparse
import json
import sys
from pathlib import Path

from app import db
from app.embed import Embedder, FastEmbedEmbedder, HashingEmbedder
from app.rerank import FastEmbedReranker, Reranker
from evals.dataset import load_dataset
from evals.runner import check_thresholds, flatten, run_eval

ROOT = Path(__file__).resolve().parent
TOLERANCE = 0.05  # margin subtracted when writing a baseline


def _embedder(name: str) -> Embedder:
    return HashingEmbedder() if name == "hashing" else FastEmbedEmbedder()


def _reranker(name: str) -> Reranker | None:
    return None if name == "none" else FastEmbedReranker()


def print_report(report: dict, config: str) -> None:
    r, ep = report["retrieval"], report["endpoints"]
    print(f"\n=== {report['dataset']} [{config}] ===")
    print(
        f"ingest: {report['ingest']['files_indexed']} files, "
        f"{report['ingest']['chunks']} chunks in {report['ingest']['seconds']}s"
    )
    print(
        f"retrieval  hit@1={r['hit@1']:.2f}  hit@3={r['hit@3']:.2f}  "
        f"recall@5={r['recall@5']:.2f}  recall@10={r['recall@10']:.2f}  mrr={r['mrr']:.2f}"
    )
    print(
        f"latency    p50={report['latency_ms']['p50']}ms  p95={report['latency_ms']['p95']}ms  "
        f"context~{report['context_tokens_est']} tokens/question"
    )
    if ep:
        print(
            f"endpoints  detect P={ep['detection']['precision']:.2f} R={ep['detection']['recall']:.2f}  "
            f"class-acc={ep['classification_accuracy']:.2f}  "
            f"auth-F1={ep['handles_authentication']['f1']:.2f}  "
            f"requires-auth-F1={ep['requires_auth']['f1']:.2f}"
        )
        for m in ep["mismatches"]:
            print(f"  ! {m['route']}: {m['field']} expected {m['expected']}, got {m['got']}")
        for item in ep["missing"]:
            print(f"  ! missing endpoint {item}")
        for item in ep["spurious"]:
            print(f"  ! spurious endpoint {item}")
    if report["answers"]:
        a = report["answers"]
        print(
            f"answers    n={a['answered']} errors={a['errors']}  citations_valid={a['citations_valid']:.2f}  "
            f"cites_relevant={a['cites_relevant_source']:.2f}  must_mention={a['must_mention']:.2f}"
        )
    misses = [q for q in report["questions"] if q["first_relevant_rank"] not in (1,)]
    for q in misses:
        print(f"  ~ {q['id']}: first relevant at rank {q['first_relevant_rank']}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="evals.run")
    p.add_argument("--dataset", type=Path, default=ROOT / "datasets" / "shop_api.json")
    p.add_argument("--embedder", choices=["hashing", "fastembed"], default="hashing")
    p.add_argument("--reranker", choices=["none", "fastembed"], default="none")
    p.add_argument("--answers", action="store_true", help="also call the LLM (LLM_BASE_URL/...)")
    p.add_argument("--out", type=Path, help="write the full JSON report here")
    p.add_argument("--thresholds", type=Path, default=ROOT / "thresholds.json")
    p.add_argument("--no-gate", action="store_true", help="report only; never fail")
    p.add_argument("--write-baseline", action="store_true", help="store current metrics as floors")
    p.add_argument("--keep", action="store_true", help="leave the indexed repo in the database")
    args = p.parse_args(argv)

    config = f"{args.embedder}+{args.reranker}"
    with db.connect() as conn:
        db.init_schema(conn)
        report = run_eval(
            conn,
            load_dataset(args.dataset),
            _embedder(args.embedder),
            _reranker(args.reranker),
            answers=args.answers,
            keep=args.keep,
        )
    report["config"] = config

    print_report(report, config)
    if args.out:
        args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    flat = flatten(report)
    table = json.loads(args.thresholds.read_text()) if args.thresholds.exists() else {}

    if args.write_baseline:
        table[config] = {
            "min": {k: max(round(v - TOLERANCE, 2), 0.0) for k, v in sorted(flat.items())}
        }
        args.thresholds.write_text(json.dumps(table, indent=2) + "\n", encoding="utf-8")
        print(f"\nwrote baseline for '{config}' to {args.thresholds}")
        return 0

    if args.no_gate:
        return 0
    if config not in table:
        print(f"\nno thresholds for '{config}' in {args.thresholds}; not gating")
        return 0
    failures = check_thresholds(flat, table[config])
    if failures:
        print(f"\nREGRESSION ({config}):")
        for f in failures:
            print(f"  FAIL {f}")
        return 1
    print(f"\nOK: all {len(table[config].get('min', {}))} floors met for '{config}'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
