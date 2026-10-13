"""Run a dataset through the real ingest + retrieval (+ optional ask) path."""

import re
import time
from collections.abc import Callable

import psycopg

from app import llm
from app.ask import build_messages, is_endpoint_question
from app.embed import Embedder
from app.graph import list_endpoints
from app.ingest.service import ingest_repo
from app.rerank import Reranker
from app.retrieval import Hit, hybrid_search
from evals import metrics
from evals.dataset import Dataset, Question

TOP_K = 10
_CITATION = re.compile(r"\[(\d+)\]")


def hit_id(hit: Hit) -> str:
    return f"{hit.file}::{hit.qualified_name}"


def _answer_checks(question: Question, answer: str, hits: list[Hit]) -> dict:
    refs = {int(n) for n in _CITATION.findall(answer)}
    valid = bool(refs) and all(1 <= r <= len(hits) for r in refs)
    cited_relevant = any(
        hit_id(hits[r - 1]) in question.relevant for r in refs if 1 <= r <= len(hits)
    )
    lowered = answer.lower()
    mentions = [m for m in question.must_mention if m.lower() in lowered]
    return {
        "citations_valid": valid,
        "cites_relevant_source": cited_relevant,
        "must_mention_hit": (len(mentions) / len(question.must_mention))
        if question.must_mention
        else None,
    }


def run_eval(
    conn: psycopg.Connection,
    dataset: Dataset,
    embedder: Embedder,
    reranker: Reranker | None = None,
    *,
    answers: bool = False,
    chat: Callable[[list[dict[str, str]]], str] | None = None,
    keep: bool = False,
) -> dict:
    t0 = time.perf_counter()
    stats = ingest_repo(conn, dataset.repo_path, embedder)
    repo_id = stats["repo_id"]
    ingest_s = time.perf_counter() - t0

    try:
        per_question = []
        latencies, context_chars = [], []
        endpoints = list_endpoints(conn, repo_id)

        for q in dataset.questions:
            started = time.perf_counter()
            hits = hybrid_search(conn, repo_id, q.question, embedder, reranker, top_k=TOP_K)
            latencies.append((time.perf_counter() - started) * 1000)
            retrieved = [hit_id(h) for h in hits]
            context_chars.append(sum(len(h.content) for h in hits[:6]))

            entry = {
                "id": q.id,
                "question": q.question,
                "first_relevant_rank": metrics.first_relevant_rank(retrieved, set(q.relevant)),
                "retrieved": retrieved[:5],
                "relevant": sorted(q.relevant),
                "hit@1": metrics.hit_at_k(retrieved, set(q.relevant), 1),
                "hit@3": metrics.hit_at_k(retrieved, set(q.relevant), 3),
                "recall@5": metrics.recall_at_k(retrieved, set(q.relevant), 5),
                "recall@10": metrics.recall_at_k(retrieved, set(q.relevant), 10),
                "mrr": metrics.reciprocal_rank(retrieved, set(q.relevant)),
            }
            if answers:
                ep = endpoints if is_endpoint_question(q.question) else None
                try:
                    text = (chat or llm.chat)(build_messages(q.question, hits[:6], ep))
                    entry["answer"] = text
                    entry["answer_checks"] = _answer_checks(q, text, hits[:6])
                except llm.LLMError as e:
                    entry["answer_error"] = str(e)
            per_question.append(entry)

        report = {
            "dataset": dataset.name,
            "ingest": {**stats, "seconds": round(ingest_s, 2)},
            "retrieval": {
                k: round(metrics.mean([e[k] for e in per_question]), 4)
                for k in ("hit@1", "hit@3", "recall@5", "recall@10", "mrr")
            },
            "endpoints": metrics.score_endpoints(dataset.endpoints, endpoints)
            if dataset.endpoints
            else None,
            "latency_ms": {
                "p50": round(metrics.percentile(latencies, 50), 1),
                "p95": round(metrics.percentile(latencies, 95), 1),
            },
            "context_tokens_est": round(metrics.mean(context_chars) / 4),
            "answers": _summarize_answers(per_question) if answers else None,
            "questions": per_question,
        }
        return report
    finally:
        if not keep:
            conn.execute("DELETE FROM repos WHERE id = %s", (repo_id,))
            conn.commit()


def _summarize_answers(per_question: list[dict]) -> dict:
    graded = [e["answer_checks"] for e in per_question if "answer_checks" in e]
    mention = [c["must_mention_hit"] for c in graded if c["must_mention_hit"] is not None]
    return {
        "answered": len(graded),
        "errors": sum("answer_error" in e for e in per_question),
        "citations_valid": round(metrics.mean([float(c["citations_valid"]) for c in graded]), 4),
        "cites_relevant_source": round(
            metrics.mean([float(c["cites_relevant_source"]) for c in graded]), 4
        ),
        "must_mention": round(metrics.mean(mention), 4),
    }


def flatten(report: dict) -> dict[str, float]:
    """Numeric metrics keyed 'section.name' for threshold checks."""
    flat = {f"retrieval.{k}": v for k, v in report["retrieval"].items()}
    ep = report.get("endpoints")
    if ep:
        flat["endpoints.detection_recall"] = ep["detection"]["recall"]
        flat["endpoints.detection_precision"] = ep["detection"]["precision"]
        flat["endpoints.classification_accuracy"] = ep["classification_accuracy"]
        flat["endpoints.auth_f1"] = ep["handles_authentication"]["f1"]
        flat["endpoints.requires_auth_f1"] = ep["requires_auth"]["f1"]
    ans = report.get("answers")
    if ans and ans["answered"]:
        flat["answers.citations_valid"] = ans["citations_valid"]
        flat["answers.cites_relevant_source"] = ans["cites_relevant_source"]
        flat["answers.must_mention"] = ans["must_mention"]
    return flat


def check_thresholds(flat: dict[str, float], limits: dict) -> list[str]:
    """Return human-readable failures (empty list = pass)."""
    failures = []
    for key, floor in limits.get("min", {}).items():
        if key not in flat:
            failures.append(f"{key}: not measured (floor {floor})")
        elif flat[key] < floor - 1e-9:
            failures.append(f"{key}: {flat[key]:.3f} < floor {floor:.3f}")
    for key, ceiling in limits.get("max", {}).items():
        if key in flat and flat[key] > ceiling + 1e-9:
            failures.append(f"{key}: {flat[key]:.3f} > ceiling {ceiling:.3f}")
    return failures
