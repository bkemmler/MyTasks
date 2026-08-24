#!/usr/bin/env python3
"""
tasky LLM Eval-Skript.

Nutzung:
    python evaluate.py                     # alle Beispiele evaluieren
    python evaluate.py --model gemma4:e2b  # mit bestimmtem Modell
    python evaluate.py --prompt-version 2  # mit bestimmter Prompt-Version
    python evaluate.py --compare           # Vergleich: alle Modelle
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

from app.services.normalizer import normalize_extraction
from app.services.ollama import OllamaClient
from app.services.prompt import render_prompt


def load_eval_set() -> list[dict]:
    path = Path(__file__).parent / "eval_set.json"
    with open(path) as f:
        return json.load(f)


async def evaluate_single(
    client: OllamaClient,
    example: dict,
    model: str,
    default_due_time: str = "17:00",
) -> dict:
    source_text = example["source_text"]
    expected = example["expected"]

    prompt = render_prompt(
        user_text=source_text,
        categories=[],
        user_context="",
        default_due_time=default_due_time,
        tz_name="Europe/Berlin",
    )

    start = time.monotonic()
    try:
        raw = await client.extract_task(prompt, source_text, model=model)
        normalized = normalize_extraction(
            raw, user_categories=[], default_due_time=default_due_time
        )
        elapsed = time.monotonic() - start
        return {
            "source_text": source_text,
            "expected": expected,
            "actual": normalized,
            "raw": raw,
            "duration_seconds": elapsed,
            "success": True,
        }
    except Exception as e:
        return {
            "source_text": source_text,
            "expected": expected,
            "error": str(e),
            "duration_seconds": time.monotonic() - start,
            "success": False,
        }


def _evaluate_local(examples: list[dict]) -> tuple[list[dict], float, float]:
    """Evaluiert nur die lokale Pipeline (kein LLM)."""
    from app.services.local_extract import local_extract

    results = []
    total_time = 0.0
    total_score = 0.0

    for i, example in enumerate(examples):
        start = time.monotonic()
        result = local_extract(example["source_text"])
        elapsed = time.monotonic() - start

        scoring = score_example(
            {"success": True, "expected": example["expected"], "actual": result}
        )
        results.append(
            {
                "source_text": example["source_text"],
                "expected": example["expected"],
                "actual": result,
                "duration_seconds": elapsed,
                "success": True,
                "scoring": scoring,
            }
        )

        total_time += elapsed
        total_score += scoring["overall"]
        score_str = f"{scoring['overall']:.3f}"
        print(f"[{i+1:2d}/{len(examples)}] OK {score_str}  conf={result['confidence']:.2f}  {example['source_text'][:55]}")

    avg_score = total_score / max(len(results), 1)
    avg_time_ms = (total_time / max(len(results), 1)) * 1000
    print("-" * 60)
    print(f"Erfolgsrate:    {len(results)}/{len(examples)} (100%)")
    print(f"Durchschnitt:   {avg_score:.3f} (Feldgenauigkeit)")
    print(f"Zeit ∅:         {avg_time_ms:.2f} ms (rein lokal, kein LLM)")
    print()

    field_totals: dict[str, float] = {}
    field_counts: dict[str, int] = {}
    for r in results:
        for field, score in r["scoring"]["fields"].items():
            field_totals[field] = field_totals.get(field, 0) + score
            field_counts[field] = field_counts.get(field, 0) + 1
    print("Feldgenauigkeit:")
    for field in sorted(field_totals):
        avg = field_totals[field] / max(field_counts[field], 1)
        print(f"  {field:20s} {avg:.3f}")

    confidences = [r["actual"]["confidence"] for r in results]
    if confidences:
        print()
        print("Confidence-Verteilung:")
        print(f"  ≥0.6 (lokal ausreichend): {sum(1 for c in confidences if c >= 0.6)}/{len(confidences)}")
        print(f"  Ø Confidence:              {sum(confidences)/len(confidences):.2f}")

    return results, avg_score, avg_time_ms / 1000


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
        exp_words = set(exp_lower.split())
        act_words = set(act_lower.split())
        if exp_words and act_words:
            overlap = len(exp_words & act_words)
            ratio = overlap / max(len(exp_words), len(act_words))
            if ratio >= 0.7:
                return 0.6
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

    return 0.0


def score_example(result: dict) -> dict:
    if not result.get("success"):
        return {"overall": 0.0, "fields": {}}

    expected = result["expected"]
    actual = result["actual"]
    fields = ["title", "status", "priority", "subtasks", "waiting_for"]
    field_scores = {}
    total = 0.0

    for field in fields:
        if field in expected:
            s = score_field(expected, actual, field)
            field_scores[field] = s
            total += s

    overall = total / max(len(fields), 1)
    return {"overall": round(overall, 3), "fields": field_scores}


async def evaluate(
    model: str | None = None,
    prompt_version: int | None = None,
    limit: int | None = None,
    base_url: str = "http://localhost:11434",
) -> tuple[list[dict], float, float]:
    examples = load_eval_set()
    if limit:
        examples = examples[:limit]

    # Kein Modell angegeben → nur lokale Pipeline evaluieren
    if not model:
        print("Modell:         (kein LLM — nur lokale Pipeline)")
        print(f"Beispiele:      {len(examples)}")
        print("-" * 60)
        return _evaluate_local(examples)

    client = OllamaClient(base_url=base_url)
    print(f"Modell:         {model}")
    print(f"Beispiele:      {len(examples)}")
    print(f"Prompt-Version: {prompt_version or 'default'}")
    print("-" * 60)

    results = []
    total_time = 0.0
    total_score = 0.0
    success_count = 0

    for i, example in enumerate(examples):
        result = await evaluate_single(client, example, model)
        scoring = score_example(result)
        result["scoring"] = scoring
        results.append(result)

        total_time += result.get("duration_seconds", 0)
        if result["success"]:
            success_count += 1
            total_score += scoring["overall"]

        status = "OK" if result["success"] else "ERR"
        score_str = f"{scoring['overall']:.3f}" if result["success"] else "FAIL"
        print(f"[{i+1:2d}/{len(examples)}] {status} {score_str}  {example['source_text'][:60]}")

    print("-" * 60)
    avg_score = total_score / max(success_count, 1)
    avg_time = total_time / max(len(results), 1)
    print(f"Erfolgsrate:    {success_count}/{len(examples)} ({100*success_count/len(examples):.0f}%)")
    print(f"Durchschnitt:   {avg_score:.3f} (Feldgenauigkeit)")
    print(f"Zeit ∅:         {avg_time:.1f}s")

    field_totals: dict[str, float] = {}
    field_counts: dict[str, int] = {}
    for r in results:
        if r["success"]:
            for field, score in r["scoring"]["fields"].items():
                field_totals[field] = field_totals.get(field, 0) + score
                field_counts[field] = field_counts.get(field, 0) + 1

    print()
    print("Feldgenauigkeit:")
    for field in sorted(field_totals):
        avg = field_totals[field] / max(field_counts[field], 1)
        print(f"  {field:20s} {avg:.3f}")

    return results, avg_score, avg_time


async def compare_models(models: list[str]):
    for model in models:
        print(f"\n{'='*60}")
        print(f"  Modell: {model}")
        print(f"{'='*60}")
        _results, score, elapsed = await evaluate(model=model)
        print(f"  → Gesamt: {score:.3f} in {elapsed:.1f}s\n")


def main():
    parser = argparse.ArgumentParser(description="tasky LLM Eval")
    parser.add_argument("--model", help="Ollama-Modell")
    parser.add_argument("--base-url", default="http://192.168.100.91:11434", help="Ollama-Server")
    parser.add_argument("--prompt-version", type=int, help="Prompt-Version")
    parser.add_argument("--limit", type=int, help="Max Beispiele (für schnellen Test)")
    parser.add_argument("--compare", action="store_true", help="Mehrere Modelle vergleichen")
    parser.add_argument("--output", help="Ergebnisse als JSON speichern")
    args = parser.parse_args()

    if args.compare:
        models = ["gemma4:e2b", "granite4.1:3b", "qwen2.5:3b"]
        asyncio.run(compare_models(models))
        return

    results, score, _elapsed = asyncio.run(
        evaluate(
            model=args.model,
            prompt_version=args.prompt_version,
            limit=args.limit,
            base_url=args.base_url,
        )
    )

    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\nErgebnisse gespeichert in: {args.output}")

    if score >= 0.85:
        print("\n✅ Eval-Schwelle (≥85%) erreicht!")
    else:
        print(f"\n❌ Eval-Schwelle (≥85%) NICHT erreicht ({score:.3f})")


if __name__ == "__main__":
    main()
