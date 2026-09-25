"""Compare prompt versions and models on the labelled dataset.

    python -m evals.run_eval                      # full 2x2 grid + rules-only baseline
    python -m evals.run_eval --limit 5 --yes      # smoke test
"""

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from evals.metrics import passes, summarize
from scamcheck import rules
from scamcheck.checker import CheckError, check
from scamcheck.config import JEV, PRICING, PROVIDERS, config_for

HERE = Path(__file__).parent
EST_TOKENS_PER_CALL = (1300, 700)  # (input, output) upper-ish estimate for LLMs


def load_dataset(limit: int | None) -> list[dict]:
    rows = [json.loads(line) for line in (HERE / "dataset.jsonl").read_text().splitlines() if line.strip()]
    return rows[:limit] if limit else rows


def rules_only(text: str) -> str:
    n = len(rules.signals(text))
    return "scam" if n >= 2 else "suspicious" if n == 1 else "legit"


def run_one(item: dict, model: str, prompt: str) -> dict:
    row = {"id": item["id"], "category": item["category"], "gold": item["label"], "text": item["text"]}
    try:
        res = check(item["text"], config_for(model, prompt))
    except CheckError as e:
        return row | {"pred": None, "error": str(e), "cost_usd": 0.0, "latency_s": 0.0}
    price_in, price_out = PRICING[model]
    return row | {
        "pred": res.verdict.label,
        "risk_score": res.verdict.risk_score,
        "red_flags": res.verdict.red_flags,
        "explanation": res.verdict.explanation,
        # Upper bound: cache reads are billed at a discount but counted at full input price here.
        "cost_usd": (res.input_tokens * price_in + res.output_tokens * price_out) / 1e6,
        "latency_s": round(res.latency_s, 2),
        "confidence": res.confidence,
        "cache_read_tokens": res.cache_read_tokens,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompts", nargs="+", default=["v2_checklist", "v3_checklist"])
    ap.add_argument("--models", nargs="+", default=[JEV], choices=sorted(PROVIDERS))
    ap.add_argument("--limit", type=int)
    ap.add_argument("--repeats", type=int, default=1, help="run each config N times to measure run-to-run variation")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--tag", default="")
    ap.add_argument("--yes", action="store_true", help="skip the cost confirmation")
    ap.add_argument("--rules-only", action="store_true", help="score only the free regex baseline (no API calls)")
    args = ap.parse_args()

    data = load_dataset(args.limit)
    configs = [] if args.rules_only else [(m, p) for m in args.models for p in args.prompts]
    est = args.repeats * sum(len(data) * (EST_TOKENS_PER_CALL[0] * PRICING[m][0] + EST_TOKENS_PER_CALL[1] * PRICING[m][1]) / 1e6 for m, _ in configs)
    n_calls = len(data) * len(configs) * args.repeats
    print(f"{len(data)} messages x {len(configs)} configs x {args.repeats} repeats = {n_calls} calls, est. <= ${est:.2f}")
    if configs and est > 0 and not args.yes and input("Run? [y/N] ").strip().lower() != "y":
        sys.exit(0)

    results: dict = {"rules_only": {"rows": [{"id": d["id"], "category": d["category"], "gold": d["label"], "text": d["text"], "pred": rules_only(d["text"])} for d in data]}}
    try:
        for model, prompt in configs:
            name = f"{model}/{prompt}"
            results[name] = {"model": model, "prompt": prompt, "rows": []}
            for rep in range(args.repeats):
                with ThreadPoolExecutor(args.workers) as pool:
                    for i, r in enumerate(pool.map(lambda d: run_one(d, model, prompt), data), 1):
                        results[name]["rows"].append(r | {"repeat": rep})
                        print(f"\r{name} repeat {rep + 1}/{args.repeats}: {i}/{len(data)}", end="", flush=True)
                errs = sum(r["pred"] is None for r in results[name]["rows"] if r["repeat"] == rep)
                print(f"  ({errs} errors)" if errs else "", flush=True)
    except KeyboardInterrupt:
        print("\ninterrupted, saving partial results")
        args.tag = (args.tag + "-partial").lstrip("-")
    results = {k: v for k, v in results.items() if v["rows"]}

    for r in results.values():
        r["summary"] = summarize(r["rows"])
        runs = sorted({row.get("repeat", 0) for row in r["rows"]})
        if len(runs) > 1:
            r["summary"]["accuracy_by_repeat"] = [summarize([x for x in r["rows"] if x["repeat"] == k])["accuracy"] for k in runs]
        r["summary"]["passes_bar"] = passes(r["summary"])

    out_dir = HERE / "results"
    out_dir.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S") + (f"-{args.tag}" if args.tag else "")
    (out_dir / f"{stamp}.json").write_text(json.dumps(results, indent=2))
    print_table(results)
    print(f"\nsaved evals/results/{stamp}.json")


def print_table(results: dict) -> None:
    print(f"\n{'config':42} {'acc':>6} {'scamR':>6} {'miss':>6} {'legitFP':>8} {'err':>4} {'cost$':>7} {'lat s':>6} bar")
    for name, r in results.items():
        s = r["summary"]
        print(
            f"{name:42} {s['accuracy']:6.2f} {s['scam_recall']:6.2f} {s['scam_miss_rate']:6.2f} {s['legit_fp_rate']:8.2f} "
            f"{s['errors']:4d} {s['cost_usd']:7.3f} {str(s['mean_latency_s']):>6} {'PASS' if s['passes_bar'] else 'fail'}"
        )


if __name__ == "__main__":
    main()
