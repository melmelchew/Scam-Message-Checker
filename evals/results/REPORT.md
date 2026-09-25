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

## Iteration 2: v2 vs v3 on an expanded dataset (rule written before the run)
**Why:** two gaps. v2's one scam miss was a task-job scam (m008). A user review also pointed out that wrong-number / friendly-opener scams ("Hi Emily, are we still meeting for lunch?"), which lead into pig-butchering investment pitches, weren't covered. v2 labelled m026 ("Hi, is this Jessica?") `legit` in 3 of 3 runs.

**Dataset change:** 12 messages added (m061–m072), giving 72 in total:
- the user's 4 templates: delivery fee, bank overseas login, FairPrice voucher, wrong-number opener (×2);
- 3 more wrong-number openers and a wrong-number pivot to a gold-trading pitch;
- 2 more task-job scams;
- 2 **hard legit twins**: a real lunch reminder from a church friend, and a real "sorry, wrong number".

**v3_checklist** = v2 plus two tactic checks (task-job scams, wrong-number / friendly openers from an unknown sender) and label definitions that name them.

**Decision rule (fixed before running):** adopt v3 only if all of these hold:
1. It passes the bar on the 72-message set (scam recall ≥ 90%, legit FP ≤ 10%, 0 errors).
2. Its legit FP is no higher than v2's on the same run.
3. It gets more of the target messages right than v2. Targets: task-job m008, m069, m070; wrong-number m026, m027, m064–m068.

Otherwise keep v2 and record why.

### Result: run `20260925-145342-v2-vs-v3` (72 messages × 3 repeats, 0 errors, $0.015)

| config | acc | scam recall | scams missed as legit | legit FP | target msgs right | bar |
|---|---|---|---|---|---|---|
| rules_only | 0.53 | 0.42 | 0.32 | 0.18 | – | ✗ |
| v2_checklist | 0.83 | 0.91 | 0.00 | 0.08 | 10 / 30 | ✓ |
| **v3_checklist** | **0.92** | **1.00** | 0.00 | **0.03** | **27 / 30** | ✓ |

**Decision: adopt v3.** All three conditions hold, and `DEFAULT_CONFIG` is now `v3_checklist`.
- **Task-job scams are fixed.** m008 and m069 went from mostly `suspicious` to `scam` in 3 of 3 runs.
- **Wrong-number openers are fixed.** m026, m064 and m065 ("Hi Emily…", "is this David?") went from `legit` ×3 to `suspicious` ×3. The gold-trading pivot (m068) is now `scam`.
- **No new false alarms.** All three hard legit twins (m050 dinner, m071 church lunch, m072 "sorry, wrong number") stayed `legit` every run. Legit FP fell from 8% to 3%.
- **Still missed:** m067, "Good morning! Long time no talk, how have you been? 😊", is `legit` every run. That's arguably correct from the text alone: without knowing whether the sender is a stranger, it can't be told apart from a real friend. The remaining errors are 4 edge cases pushed up to `scam` and the Uniqlo sale flagged `suspicious`.

**Partial fix, found when trying it in the app:** "Hi Emily, are we still meeting for lunch?" (m064) is now labelled `suspicious`, but its opener check scores only 0.13. Jev reads the check literally and can't know that "Emily" isn't the recipient. The label comes from v3's label definitions, not the tactic check, so the page showed a verdict with no reason. The explanation now says so ("No single warning sign stood out…"). Rewording that check is a candidate for the next eval run.

**Fix found while recording the demo GIFs:** in **Details**, legit OTP messages showed ⚠️ on "Plays on emotion or secrecy". Jev read "Do not share this OTP" as a request for secrecy, scoring 0.66–0.90 on m041–m043. The check was reworded to exclude standard "don't share your code" warnings.
- **Targeted check:** m041–m043 went from 0.66–0.90 to 0.02–0.03. The real secrecy scams m010 ("don't tell dad") and m016 (romance) stayed at 0.97–0.98.
- **Full re-run `20260925-152808-v3-secrecy-fix` (72 × 3):** accuracy 0.93 (was 0.92), scam recall 1.00 (unchanged), legit FP 0.01 (was 0.03), 0 errors, and the same set of wrong messages. No regression, so the change is kept.

**Limitation this exposed:** wrong-number scams are defined by *who sent them*, which the checker can't see. "Are we still meeting for lunch?" is a scam opener from a stranger and a normal message from a friend. A future version could ask the user "Do you know this sender?" and pass the answer to Jev as state.

## Limitations
- **Synthetic, small dataset.** The 60 messages were written by us in the style of public advisories. Real scams are messier.
- **Canned explanations.** Jev returns probabilities, not prose, so explanation and advice are templates chosen by label and flags.
- **Cost and quota.** `jev-latest` costs $0.042 per million input tokens (output free), about $0.005 per 180 checks. The free OpenCode tier was not viable (see earlier runs).
- **`suspicious` is subjective.** The decision rule uses only the scam and legit classes for this reason.
