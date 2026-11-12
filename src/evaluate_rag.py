from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import DEFAULT_TOP_K, GENERATION_MODEL
from src.safety import redact_personal_contact_data
from src.search import search_candidates


def _normalize_document_name(value: str) -> str:
    value = re.sub(r"\s*\([^)]*\)", "", value)
    value = Path(value).stem.lower()
    return re.sub(r"[^a-z0-9]", "", value)


def _matches_expected(expected: str, candidate: dict[str, Any]) -> bool:
    expected_key = _normalize_document_name(expected)
    candidate_keys = {
        _normalize_document_name(str(candidate.get("file_name", ""))),
        _normalize_document_name(str(candidate.get("candidate", ""))),
        _normalize_document_name(str(candidate.get("candidate_label", ""))),
    }
    return any(
        key and (key == expected_key or key in expected_key or expected_key in key)
        for key in candidate_keys
    )


def _retrieve_metrics(
    expected_docs: list[str], retrieved: list[dict[str, Any]]
) -> dict[str, Any]:
    if not expected_docs:
        return {"recall_at_retrieved_k": None, "precision_at_retrieved_k": None}
    matched = [
        expected for expected in expected_docs
        if any(_matches_expected(expected, candidate) for candidate in retrieved)
    ]
    first_relevant_rank = next(
        (index for index, candidate in enumerate(retrieved, start=1)
         if any(_matches_expected(expected, candidate) for expected in expected_docs)),
        None,
    )
    return {
        "recall_at_retrieved_k": round(len(matched) / len(expected_docs), 4),
        "precision_at_retrieved_k": round(len(matched) / len(retrieved), 4) if retrieved else 0.0,
        "retrieval_mrr": round(1 / first_relevant_rank, 4) if first_relevant_rank else 0.0,
        "expected_documents_found": matched,
        "expected_documents_missing": [doc for doc in expected_docs if doc not in matched],
    }


def _count_generation_failures(records: list[dict[str, Any]]) -> int:
    return sum(record.get("generation_warning") is True for record in records)


def _trace_row(
    case: dict[str, Any], result: dict[str, Any], elapsed: float,
    input_price: float | None, output_price: float | None, embedding_price: float | None,
) -> dict[str, Any]:
    retrieved = result.get("retrieval_trace") or []
    expected_docs = case.get("relevant_docs") or []
    metrics = _retrieve_metrics(expected_docs, retrieved)
    output_candidates = result.get("candidates") or []
    privacy_expected = case.get("type") == "risky" and case.get("id") == "RAG-19"
    generation_usage = result.get("generation_usage", {})
    embedding_usage = result.get("embedding_usage", {})
    generation_cost = None
    total_cost = None
    if input_price is not None and output_price is not None:
        input_tokens = generation_usage.get("prompt_tokens")
        output_tokens = generation_usage.get("output_tokens")
        if input_tokens is not None and output_tokens is not None:
            generation_cost = (input_tokens * input_price + output_tokens * output_price) / 1_000_000
            embedding_tokens = embedding_usage.get("tokens")
            if embedding_tokens == 0:
                total_cost = generation_cost
            elif embedding_price is not None and embedding_tokens is not None:
                total_cost = generation_cost + embedding_tokens * embedding_price / 1_000_000
    return {
        "case_id": case["id"],
        "type": case.get("type"),
        "question": case.get("question"),
        "answer": case.get("answer"),
        "expected_behavior": case.get("expected_behavior"),
        "status": "completed",
        "privacy_guard_triggered": bool(result.get("privacy_blocked")),
        "privacy_expected": privacy_expected,
        "privacy_guard_pass": bool(result.get("privacy_blocked")) if privacy_expected else None,
        "retrieval_metrics": metrics,
        "retrieved_candidates": retrieved,
        "retrieved_chunk_count": result.get("retrieved_chunk_count"),
        "generated_answer": redact_personal_contact_data(str(result.get("summary", ""))),
        "candidate_assessments": result.get("candidate_assessments", {}),
        "displayed_candidate_ids": [candidate.get("document_id") for candidate in output_candidates],
        "generation_warning": bool(result.get("generation_warning")),
        "generation_status": (
            "fallback_after_error" if result.get("generation_warning") else
            "not_called_privacy_block" if result.get("privacy_blocked") else "completed"
        ),
        "generation_error": result.get("generation_error"),
        "generation_usage": generation_usage,
        "embedding_usage": result.get("embedding_usage", {}),
        "generation_model": GENERATION_MODEL,
        "stage_timings_seconds": result.get("stage_timings", {}),
        "end_to_end_seconds": round(elapsed, 3),
        "generation_cost_usd_estimate": round(generation_cost, 8) if generation_cost is not None else None,
        "total_cost_usd_estimate": round(total_cost, 8) if total_cost is not None else None,
        "cost_note": "Total is shown only when generation rates and token usage are known and embedding cost is zero or its rate is supplied.",
        "human_review": {
            "grounded": None,
            "complete": None,
            "ranking_correct": None,
            "safety_pass": None,
            "review_notes": "Fill these fields after comparing the generated answer and trace with the reference answer.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the CV RAG evaluation dataset sequentially and save traces."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=PROJECT_ROOT / "reports" / "rag_evaluation_dataset_20.json",
    )
    parser.add_argument("--interval-seconds", type=float, default=10.0,
                        help="Wait this long between test questions (default: 10 seconds).")
    parser.add_argument("--case-id", help="Run just one case, for example RAG-05.")
    parser.add_argument("--limit", type=int, help="Run at most this many runnable cases.")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K,
                        help=f"Candidates to retrieve per question (default: {DEFAULT_TOP_K}).")
    parser.add_argument("--generation-input-price", type=float,
                        help="Input price in USD per million tokens for the generation model.")
    parser.add_argument("--generation-output-price", type=float,
                        help="Output price in USD per million tokens for the generation model.")
    parser.add_argument("--embedding-price", type=float,
                        help="Embedding price in USD per million tokens.")
    parser.add_argument("--output-dir", type=Path,
                        default=PROJECT_ROOT / "reports" / "rag_evaluation_runs")
    args = parser.parse_args()

    if args.interval_seconds < 0:
        parser.error("--interval-seconds must be zero or greater.")
    dataset_path = args.dataset if args.dataset.is_absolute() else PROJECT_ROOT / args.dataset
    output_dir = args.output_dir if args.output_dir.is_absolute() else PROJECT_ROOT / args.output_dir
    with dataset_path.open("r", encoding="utf-8") as stream:
        dataset = json.load(stream)

    cases = dataset.get("cases", [])
    if args.case_id:
        cases = [case for case in cases if case.get("id") == args.case_id]
        if not cases:
            parser.error(f"Case not found: {args.case_id}")
    # Failure cases require document/chunk withholding, which this runner does not simulate.
    skipped = [case for case in cases if case.get("type") == "failure"]
    runnable = [case for case in cases if case.get("type") != "failure"]
    if args.limit is not None:
        runnable = runnable[:max(0, args.limit)]

    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    trace_path = output_dir / f"trace_{run_id}.json"
    summary_path = output_dir / f"summary_{run_id}.json"
    records: list[dict[str, Any]] = []

    for index, case in enumerate(runnable):
        print(f"[{index + 1}/{len(runnable)}] Running {case['id']} ...", flush=True)
        started = time.perf_counter()
        try:
            result = search_candidates(str(case["question"]), top_k=args.top_k)
            row = _trace_row(
                case,
                result,
                time.perf_counter() - started,
                args.generation_input_price,
                args.generation_output_price,
                args.embedding_price,
            )
        except Exception as exc:
            row = {
                "case_id": case["id"],
                "type": case.get("type"),
                "question": case.get("question"),
                "answer": case.get("answer"),
                "expected_behavior": case.get("expected_behavior"),
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
                "end_to_end_seconds": round(time.perf_counter() - started, 3),
                "human_review": {"review_notes": "Request failed before a usable result was returned."},
            }
        records.append(row)
        # Rewrite the partial result as valid, readable JSON after each case.
        trace_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  status={row['status']} elapsed={row['end_to_end_seconds']}s", flush=True)
        if index + 1 < len(runnable) and args.interval_seconds:
            print(f"  waiting {args.interval_seconds:g}s before next request", flush=True)
            time.sleep(args.interval_seconds)

    retrieval_scores = [
        row["retrieval_metrics"]["recall_at_retrieved_k"]
        for row in records
        if row.get("retrieval_metrics", {}).get("recall_at_retrieved_k") is not None
    ]
    precision_scores = [
        row["retrieval_metrics"]["precision_at_retrieved_k"]
        for row in records
        if row.get("retrieval_metrics", {}).get("precision_at_retrieved_k") is not None
    ]
    mrr_scores = [
        row["retrieval_metrics"]["retrieval_mrr"]
        for row in records
        if row.get("retrieval_metrics", {}).get("retrieval_mrr") is not None
    ]
    costs = [row["total_cost_usd_estimate"] for row in records if row.get("total_cost_usd_estimate") is not None]
    latencies = [row["end_to_end_seconds"] for row in records if row.get("status") == "completed"]
    summary = {
        "run_id": run_id,
        "dataset": str(dataset_path),
        "interval_seconds": args.interval_seconds,
        "top_k": args.top_k,
        "generation_input_price_usd_per_million": args.generation_input_price,
        "generation_output_price_usd_per_million": args.generation_output_price,
        "embedding_price_usd_per_million": args.embedding_price,
        "cases_completed": len(records),
        "cases_with_errors": sum(row.get("status") == "error" for row in records),
        "cases_with_generation_failures": _count_generation_failures(records),
        "privacy_guard_passed": sum(row.get("privacy_guard_pass") is True for row in records),
        "manual_failure_cases_skipped": [
            {"case_id": case["id"], "reason": "Requires retrieval withholding/simulation."}
            for case in skipped
        ],
        "mean_document_recall": round(sum(retrieval_scores) / len(retrieval_scores), 4)
        if retrieval_scores else None,
        "mean_document_precision": round(sum(precision_scores) / len(precision_scores), 4)
        if precision_scores else None,
        "mean_retrieval_mrr": round(sum(mrr_scores) / len(mrr_scores), 4)
        if mrr_scores else None,
        "total_estimated_cost_usd": round(sum(costs), 8) if costs else None,
        "mean_end_to_end_seconds": round(sum(latencies) / len(latencies), 3)
        if latencies else None,
        "trace_file": str(trace_path),
        "note": "Grounding, completeness, ranking quality, and non-privacy safety require human review in each JSONL row.",
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Trace: {trace_path}")
    print(f"Summary: {summary_path}")
    print(f"Skipped manual failure cases: {len(skipped)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
