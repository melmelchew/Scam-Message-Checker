# Scam-Message-Checker
For Claude Agentic Coding Course

Paste a message into a Streamlit page and get a verdict (scam / suspicious / legit), a risk score, red flags and advice. Uses TypeSafe AI's Jev model (`jev-latest`) through the TypeSafe API. Claude models remain available as an optional provider.

## Setup
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # then set TYPESAFE_API_KEY
```

## Run
```bash
streamlit run app.py           # web UI
pytest                         # offline tests (the API is mocked)
python -m evals.run_eval --workers 2   # v1 vs v2 question sets on Jev
python -m evals.run_eval --rules-only   # free regex baseline
```

## Layout
```
src/scamcheck/checker.py   check(message, config): the one function the app and the eval share
src/scamcheck/rules.py     regex hints (never the final verdict)
src/scamcheck/providers/jev.py  Jev question sets (v1, v2) and answer -> Verdict mapping
src/scamcheck/prompts/     Claude prompts (optional provider)
src/scamcheck/config.py    models, pricing, DEFAULT_CONFIG (chosen by the eval)
evals/                     dataset.jsonl, run_eval.py, metrics.py, results/REPORT.md
```

## Extra-knowledge build: Evaluation (option 4)
This project's extra agent-engineering piece is a **small, repeatable evaluation** that compares Jev question sets (input formats) and uses the results to make project decisions.

- **What:** `evals/run_eval.py` runs every message in `evals/dataset.jsonl` (72 labelled messages) through the same `check()` function the app uses. It repeats each config to measure run-to-run variation and scores it against a pass bar written down before each run: scam recall ≥ 90%, legit false positives ≤ 10%, 0 errors.
- **Decisions it made:**
  1. **v2 over v1:** v1 flagged 20% of real messages, including bank OTP texts.
  2. **v3 over v2:** after a user review found wrong-number / friendly-opener scams missing, v3 got 27 of 30 target messages right against v2's 10 of 30, and legit false positives fell from 8% to 3%.
- **Evidence:** raw runs in `evals/results/*.json`; write-up, failed attempts and limitations in [`evals/results/REPORT.md`](evals/results/REPORT.md).
- **Failed attempt:** the free OpenCode tier rate-limited the first run (96 of 180 calls failed), then the retry code slept through a 17.8-hour quota reset until it was fixed to fail fast.
- **Limitation:** 72 messages written by us are cleaner than real scams, and wrong-number scams depend on who sent them, which the checker can't see.

```bash
python -m evals.run_eval --repeats 3 --workers 4   # v2 vs v3, about $0.015
```
