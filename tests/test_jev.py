from unittest.mock import MagicMock

import pytest

from scamcheck.checker import CheckError, check
from scamcheck.config import JEV, CheckerConfig
from scamcheck.providers import jev


def answers(choice="scam", probs=None, flags=(), injection=0.0):
    probs = probs or {"scam": 0.9, "suspicious": 0.08, "legit": 0.02}
    a = {"label": {"type": "choice", "choice": choice, "confidence": 0.9, "probabilities": probs}, "injection": {"noul": injection}}
    for i in range(len(jev.RED_FLAGS)):
        a[f"flag_{i}"] = {"noul": 0.9 if i in flags else 0.1}
    return a


def fake_http(payload, status=200):
    http = MagicMock()
    http.post.return_value = MagicMock(status_code=status, headers={"retry-after": "0"}, json=lambda: payload)
    return http


@pytest.fixture(autouse=True)
def api_key(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test")


def test_v2_request_has_label_injection_and_flag_questions():
    req = jev.build_request(JEV, "v2_checklist", "hi", ["contains a link"])
    assert req["state"] == {"message": "hi", "keyword_hints": ["contains a link"]}
    assert req["questions"]["label"]["type"] == "choice"
    assert set(req["questions"]["label"]["criteria"]) == {"scam", "suspicious", "legit"}
    assert sum(q["type"] == "noul" for q in req["questions"].values()) == len(jev.RED_FLAGS) + 1


def test_v1_request_is_label_only():
    req = jev.build_request(JEV, "v1_zero_shot", "hi", [])
    assert list(req["questions"]) == ["label"]


def test_to_verdict_maps_flags_and_risk():
    v, details = jev.to_verdict(answers(flags=(2,)))
    assert v.label == "scam" and details["confidence"] == 0.9
    assert v.red_flags == [list(jev.RED_FLAGS)[2]]
    assert v.risk_score == 94


def test_injection_forces_scam():
    v, _ = jev.to_verdict(answers(choice="legit", probs={"scam": 0.1, "suspicious": 0.1, "legit": 0.8}, injection=0.9))
    assert v.label == "scam" and v.risk_score >= 70
    assert v.red_flags[0].startswith("Contains instructions")


def test_check_end_to_end_with_mock_http():
    http = fake_http({"answers": answers(), "usage": {"input_tokens": 400, "output_tokens": 60}})
    res = check("Pay $2 fee at bit.ly/x", CheckerConfig(model=JEV), client=http)
    assert res.verdict.label == "scam" and res.input_tokens == 400 and res.confidence == 0.9
    url = http.post.call_args.args[0]
    assert url == "https://api.typesafe.ai/v1/systemone"


@pytest.mark.parametrize("status", [429, 500])
def test_http_errors_become_friendly(status):
    with pytest.raises(CheckError):
        check("hi", CheckerConfig(model=JEV), client=fake_http({}, status))


def test_malformed_response_raises():
    with pytest.raises(CheckError, match="unexpected format"):
        check("hi", CheckerConfig(model=JEV), client=fake_http({"answers": {}}))


def test_missing_key(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY")
    with pytest.raises(CheckError, match="TYPESAFE_API_KEY"):
        check("hi", CheckerConfig(model=JEV), client=fake_http({}))


def test_rate_limit_is_retried(monkeypatch):
    monkeypatch.setattr(jev.time, "sleep", lambda s: None)
    ok = MagicMock(status_code=200, json=lambda: {"answers": answers(), "usage": {}})
    busy = MagicMock(status_code=429, headers={})
    http = MagicMock()
    http.post.side_effect = [busy, busy, ok]
    res = check("hi", CheckerConfig(model=JEV), client=http)
    assert res.verdict.label == "scam" and http.post.call_count == 3


def test_quota_exhaustion_fails_fast_instead_of_sleeping(monkeypatch):
    slept = []
    monkeypatch.setattr(jev.time, "sleep", slept.append)
    http = MagicMock()
    http.post.return_value = MagicMock(status_code=429, headers={"retry-after": "64016"})
    with pytest.raises(CheckError, match="quota is used up"):
        check("hi", CheckerConfig(model=JEV), client=http)
    assert slept == [] and http.post.call_count == 1


@pytest.mark.parametrize("choice,probs,low,high", [
    ("legit", {"scam": 0.4, "suspicious": 0.15, "legit": 0.45}, 0, 29),
    ("suspicious", {"scam": 0.05, "suspicious": 0.5, "legit": 0.45}, 30, 69),
    ("scam", {"scam": 0.5, "suspicious": 0.0, "legit": 0.5}, 70, 100),
])
def test_risk_score_stays_in_label_band(choice, probs, low, high):
    v, _ = jev.to_verdict(answers(choice=choice, probs=probs))
    assert low <= v.risk_score <= high


def test_legit_verdict_has_no_red_flags():
    v, _ = jev.to_verdict(answers(choice="legit", probs={"scam": 0.01, "suspicious": 0.01, "legit": 0.98}, flags=(6,)))
    assert v.red_flags == [] and "Warning signs" not in v.explanation


def test_details_keep_full_breakdown():
    probs = {"scam": 0.0, "suspicious": 0.34, "legit": 0.66}
    v, d = jev.to_verdict(answers(choice="legit", probs=probs, flags=(6,)))
    assert v.red_flags == []  # hidden in the verdict ...
    assert d["tactics"][list(jev.RED_FLAGS)[6]] == 0.9  # ... but still in the breakdown
    assert len(d["tactics"]) == len(jev.RED_FLAGS)
    assert d["label_probabilities"] == probs and d["injection"] == 0.0 and d["jev_label"] == "legit"


def test_details_for_label_only_question_set():
    a = {"label": {"choice": "scam", "confidence": 0.8, "probabilities": {"scam": 0.8, "suspicious": 0.2, "legit": 0.0}}}
    _, d = jev.to_verdict(a)
    assert d["tactics"] == {} and d["injection"] is None


def test_check_result_carries_details():
    http = fake_http({"answers": answers(), "usage": {}})
    res = check("hi", CheckerConfig(model=JEV), client=http)
    assert res.details["label_probabilities"]["scam"] == 0.9


def test_v3_adds_task_job_and_wrong_number_checks():
    v2 = jev.build_request(JEV, "v2_checklist", "hi", [])["questions"]
    v3 = jev.build_request(JEV, "v3_checklist", "hi", [])["questions"]
    assert set(v3) - set(v2) == {f"flag_{len(jev.RED_FLAGS)}", f"flag_{len(jev.RED_FLAGS) + 1}"}
    assert "online tasks" in v3["label"]["criteria"]["scam"]
    assert "wrong-number" in v3["label"]["criteria"]["suspicious"]


def test_v3_answers_map_to_new_flag_names():
    a = answers(choice="suspicious", probs={"scam": 0.2, "suspicious": 0.7, "legit": 0.1})
    a[f"flag_{len(jev.RED_FLAGS) + 1}"] = {"noul": 0.8}
    v, d = jev.to_verdict(a)
    assert "Friendly or wrong-number opener from a stranger" in v.red_flags
    assert len(d["tactics"]) == len(jev.RED_FLAGS) + 1  # only the flags present in the answers


def test_flagless_non_legit_verdict_explains_itself():
    v, _ = jev.to_verdict(answers(choice="suspicious", probs={"scam": 0.1, "suspicious": 0.6, "legit": 0.3}))
    assert v.red_flags == [] and "message as a whole" in v.explanation


def test_secrecy_check_excludes_standard_code_warnings():
    # "Do not share this OTP" scored 0.66-0.90 as secrecy before this exclusion was added.
    text = jev.RED_FLAGS["Plays on emotion or secrecy"]
    assert "not to share a code, OTP, PIN or password does not count" in text
