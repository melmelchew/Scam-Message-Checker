# Evaluation report: which Jev question set ships

## Decision this eval makes
Which question set the app uses with Jev (`jev-latest` via the TypeSafe API): `DEFAULT_CONFIG.prompt_version` in `src/scamcheck/config.py`.

- **v1_zero_shot**: one `choice` question ("Is this message a scam?") with one-line label definitions.
- **v2_checklist**: the same `choice` with detailed label definitions, plus 7 yes/no (`noul`) questions for scam tactics, a `noul` injection detector, and regex keyword hints in the state.

**Rule, fixed before any run:** ship a config only if scam recall ≥ 90%, legit false-positive rate ≤ 10%, and there are 0 errors. Between passing configs, prefer the cheaper one.

## Results: deciding run `20260925-142830-jev-typesafe` (60 messages × 3 repeats)

| config | acc | scam recall | scams missed as legit | legit FP | errors | cost | latency | bar |
|---|---|---|---|---|---|---|---|---|
| rules_only (regex baseline) | 0.57 | 0.44 | 0.28 | 0.20 | 0 | $0 | – | ✗ |
| jev-latest / v1_zero_shot | 0.75 | **1.00** | 0.00 | 0.20 ✗ | 0 | $0.003 | 0.29 s | ✗ |
| jev-latest / v2_checklist | **0.87** | 0.96 | **0.00** | **0.10** | 0 | $0.005 | 0.27 s | **✓** |

### Decision
**Ship `jev-latest` + `v2_checklist`** (already the `DEFAULT_CONFIG`). It is the only config that passes. The whole 360-call eval cost under $0.01.

### What the results show
- **v1 cries wolf.** It flags 20% of legit messages, including real OTP texts: m041 (DBS) was labelled `scam` in 3 of 3 runs and m042 (WhatsApp) `suspicious` in 3 of 3. It also pushes 9 of 15 edge cases up to `scam`.
- **v2 fixes the OTP case.** Both OTP messages are `legit` every time. The remaining legit false positives are the Uniqlo sale message (m053) and the Gov.sg flood alert (m057).
- **v2 is consistent.** It gave identical answers on all 3 repeats, while v1 changed its answer on 3 messages (m043, m048, m059).
- **The injection defence works.** m021 was caught in every v2 run.
- **v2's one scam miss** is m008, a "$300/day liking videos" job scam, labelled `suspicious` rather than `scam` (not let through as legit). The tactics checklist has no item for task-job scams. That is the next thing to fix.

### Earlier runs (for the record)
Run `20260925-134756` used `jev-1.13-free` through OpenCode Zen. v1 had 0.77 accuracy and 15% legit FP. v2 had 96 of 180 calls fail with rate-limit errors, so it wasn't a valid pass. The free quota then ran out, so the provider was switched to TypeSafe's direct API.

## Failed attempts and bugs the eval exposed
1. **Free-tier rate limit (run 1).** v2 sends 9 questions per call, and at 6 parallel workers 96 of 180 calls got HTTP 429. *Fix:* retry with backoff, and `--workers 2`.
2. **Retry hung the run for hours (run 2, killed).** After the burst limit, the free quota ran out. OpenCode then returned `429 FreeUsageLimitError` with `retry-after: 64016` (about 17.8 h), and the retry code slept for it. *Fix:* waits over 10 s now fail at once with "free quota is used up, try again in about N hours" (`test_quota_exhaustion_fails_fast_instead_of_sleeping`).
3. **The regex treated "Do not share this OTP" as asking for the OTP.** That wrong hint was fed to Jev in v2's state. *Fix:* negation check in `rules.py`. The baseline's legit false positives went from 25% to 20%.
4. **Contradictory verdicts.** A legit OTP (m041) showed the red flag "Plays on emotion or secrecy", and a legit verdict came with risk 48. *Fix:* no flags on legit verdicts, and the risk score is kept inside its label's band.

## Next iteration
Add a task-job-scam item ("pays for simple online tasks such as liking videos or writing reviews") to `RED_FLAGS` and the scam criteria, then re-run v2. Keep the change only if m008 becomes `scam` with legit FP still ≤ 10%.

## Limitations
- **Synthetic, small dataset.** The 60 messages were written by us in the style of public advisories. Real scams are messier.
- **Canned explanations.** Jev returns probabilities, not prose, so explanation and advice are templates chosen by label and flags.
- **Cost and quota.** `jev-latest` costs $0.042 per million input tokens (output free), about $0.005 per 180 checks. The free OpenCode tier was not viable (see earlier runs).
- **`suspicious` is subjective.** The decision rule uses only the scam and legit classes for this reason.
