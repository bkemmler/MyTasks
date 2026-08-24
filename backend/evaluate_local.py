#!/usr/bin/env python3
"""Eval-Skript für die lokale Pipeline (kein LLM, sofort).

Nutzung:
    python evaluate_local.py [--limit N] [--output results.json]
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from app.services.local_extract import local_extract


def load_eval_set() -> list[dict]:
    path = Path(__file__).parent / "eval_set.json"
    with open(path) as f:
        return json.load(f)


def score_field(expected, actual, field: str) -> float:
    exp_val = expected.get(field)
    act_val = actual.get(field)

    if field == "title":
        if not exp_val or not act_val:
            return 1.0 if exp_val == act_val else 0.0
        exp_lower = exp_val.lower().strip()
        act_lower = act_val.lower().strip()
        if exp_lower == act_lower:
            return 1.0
        if exp_lower in act_lower or act_lower in exp_lower:
            return 0.8
        return 0.3

    if field == "status":
        return 1.0 if exp_val == act_val else 0.0

    if field == "priority":
        if exp_val is None:
            return 1.0 if act_val is None else 0.5
        if act_val is None:
            return 0.0
        diff = abs(exp_val - act_val)
        if diff == 0:
            return 1.0
        if diff == 1:
            return 0.5
        return 0.0

    if field == "subtasks":
        if not exp_val:
            return 1.0 if not act_val else 0.5
        if not act_val:
            return 0.0
        exp_set = {s.lower().strip() for s in exp_val}
        act_set = {s.lower().strip() for s in act_val}
        if not exp_set:
            return 1.0
        overlap = len(exp_set & act_set)
        return overlap / max(len(exp_set), len(act_set))

    if field == "waiting_for":
        if not exp_val:
            return 1.0 if not act_val else 0.5
        if not act_val:
            return 0.0
        return 1.0 if exp_val.lower() in act_val.lower() or act_val.lower() in exp_val.lower() else 0.0

    if field == "due_at":
        # Datum exakt = 1.0; ±1 Tag oder falsche Uhrzeit = 0.5
        if not exp_val:
            return 1.0 if not act_val else 0.0
        if not act_val:
            return 0.0
        try:
            exp_dt = datetime.fromisoformat(str(exp_val))
            act_dt = datetime.fromisoformat(str(act_val))
        except ValueError:
            return 0.0
        day_diff = abs((exp_dt.date() - act_dt.date()).days)
        time_ok = (exp_dt.hour, exp_dt.minute) == (act_dt.hour, act_dt.minute)
        if day_diff == 0 and time_ok:
            return 1.0
        if day_diff == 0 or (day_diff <= 1 and time_ok):
            return 0.5
        return 0.0

    return 0.0


def score_example(result: dict, expected: dict) -> dict:
    actual = result
    fields = ["title", "status", "priority", "subtasks", "waiting_for", "due_at"]
    field_scores = {}
    total = 0.0
    for field in fields:
        if field in expected:
            s = score_field(expected, actual, field)
            field_scores[field] = s
            total += s
    overall = total / max(len(field_scores), 1)
    return {"overall": round(overall, 3), "fields": field_scores}


def main():
    parser = argparse.ArgumentParser(description="MyTasks lokale Pipeline Eval")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--output", help="JSON-Output")
    args = parser.parse_args()

    examples = load_eval_set()
    if args.limit:
        examples = examples[: args.limit]

    results = []
    total_time = 0.0
    total_score = 0.0
    success_count = 0

    print(f"Eval-Samples: {len(examples)}")
    print("-" * 60)

    for i, example in enumerate(examples):
        start = time.monotonic()
        ref = example.get("reference_date")
        result = local_extract(
            example["source_text"],
            now=datetime.fromisoformat(ref) if ref else None,
        )
        elapsed = time.monotonic() - start

        scoring = score_example(result, example["expected"])
        results.append(
            {
                "source_text": example["source_text"],
                "expected": example["expected"],
                "actual": result,
                "duration_seconds": elapsed,
                "scoring": scoring,
            }
        )

        total_time += elapsed
        total_score += scoring["overall"]
        success_count += 1

        status = "OK"
        score_str = f"{scoring['overall']:.3f}"
        print(f"[{i+1:2d}/{len(examples)}] {status} {score_str}  conf={result['confidence']:.2f}  {example['source_text'][:55]}")

    print("-" * 60)
    avg_score = total_score / max(success_count, 1)
    avg_time_ms = (total_time / max(len(results), 1)) * 1000
    print(f"Feldgenauigkeit: {avg_score:.3f}")
    print(f"Zeit ∅:          {avg_time_ms:.2f} ms (rein lokal, kein Netzwerk)")

    field_totals: dict[str, float] = {}
    field_counts: dict[str, int] = {}
    for r in results:
        for field, score in r["scoring"]["fields"].items():
            field_totals[field] = field_totals.get(field, 0) + score
            field_counts[field] = field_counts.get(field, 0) + 1

    print()
    print("Feldgenauigkeit:")
    for field in sorted(field_totals):
        avg = field_totals[field] / max(field_counts[field], 1)
        print(f"  {field:20s} {avg:.3f}")

    confidences = [r["actual"]["confidence"] for r in results]
    if confidences:
        print()
        print("Confidence-Verteilung:")
        print(f"  ≥0.6 (kein LLM nötig): {sum(1 for c in confidences if c >= 0.6)}/{len(confidences)}")
        print(f"  <0.6 (LLM-Fallback):   {sum(1 for c in confidences if c < 0.6)}/{len(confidences)}")
        print(f"  Ø Confidence:          {sum(confidences)/len(confidences):.2f}")

    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\nErgebnisse gespeichert in: {args.output}")


if __name__ == "__main__":
    main()
