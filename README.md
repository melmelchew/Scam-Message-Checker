# Scam-Message-Checker
For Claude Agentic Coding Course

Paste a message into a Streamlit page and get a verdict (scam / suspicious / legit), a risk score, red flags and advice. Uses TypeSafe AI's Jev model (`jev-1.13-free`) through OpenCode Zen. Claude models remain available as an optional provider.

## Setup
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # then set OPENCODE_API_KEY
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

## Agent-engineering method: Evaluation
`evals/run_eval.py` compares two Jev question sets on 60 labelled messages (with repeats) and applies a decision rule written in advance: scam recall ≥ 90%, legit false-positive rate ≤ 10%, and no errors. The winner becomes `DEFAULT_CONFIG`. Results, the iteration and the limitations are in `evals/results/REPORT.md`.
