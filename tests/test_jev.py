from unittest.mock import MagicMock

import pytest

from scamcheck.checker import CheckError, check
from scamcheck.config import JEV_FREE, CheckerConfig
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
    monkeypatch.setenv("OPENCODE_API_KEY", "test")


def test_v2_request_has_label_injection_and_flag_questions():
    req = jev.build_request(JEV_FREE, "v2_checklist", "hi", ["contains a link"])
    assert req["state"] == {"message": "hi", "keyword_hints": ["contains a link"]}
    assert req["questions"]["label"]["type"] == "choice"
    assert set(req["questions"]["label"]["criteria"]) == {"scam", "suspicious", "legit"}
    assert sum(q["type"] == "noul" for q in req["questions"].values()) == len(jev.RED_FLAGS) + 1


def test_v1_request_is_label_only():
    req = jev.build_request(JEV_FREE, "v1_zero_shot", "hi", [])
    assert list(req["questions"]) == ["label"]


def test_to_verdict_maps_flags_and_risk():
    v, conf = jev.to_verdict(answers(flags=(2,)))
    assert v.label == "scam" and conf == 0.9
    assert v.red_flags == [list(jev.RED_FLAGS)[2]]
    assert v.risk_score == 94


def test_injection_forces_scam():
    v, _ = jev.to_verdict(answers(choice="legit", probs={"scam": 0.1, "suspicious": 0.1, "legit": 0.8}, injection=0.9))
    assert v.label == "scam" and v.risk_score >= 70
    assert v.red_flags[0].startswith("Contains instructions")


def test_check_end_to_end_with_mock_http():
    http = fake_http({"answers": answers(), "usage": {"input_tokens": 400, "output_tokens": 60}})
    res = check("Pay $2 fee at bit.ly/x", CheckerConfig(model=JEV_FREE), client=http)
    assert res.verdict.label == "scam" and res.input_tokens == 400 and res.confidence == 0.9
    url = http.post.call_args.args[0]
    assert url == "https://opencode.ai/zen/v1/systemone"


@pytest.mark.parametrize("status", [429, 500])
def test_http_errors_become_friendly(status):
    with pytest.raises(CheckError):
        check("hi", CheckerConfig(model=JEV_FREE), client=fake_http({}, status))


def test_malformed_response_raises():
    with pytest.raises(CheckError, match="unexpected format"):
        check("hi", CheckerConfig(model=JEV_FREE), client=fake_http({"answers": {}}))


def test_missing_key(monkeypatch):
    monkeypatch.delenv("OPENCODE_API_KEY")
    with pytest.raises(CheckError, match="OPENCODE_API_KEY"):
        check("hi", CheckerConfig(model=JEV_FREE), client=fake_http({}))


def test_rate_limit_is_retried(monkeypatch):
    monkeypatch.setattr(jev.time, "sleep", lambda s: None)
    ok = MagicMock(status_code=200, json=lambda: {"answers": answers(), "usage": {}})
    busy = MagicMock(status_code=429, headers={})
    http = MagicMock()
    http.post.side_effect = [busy, busy, ok]
    res = check("hi", CheckerConfig(model=JEV_FREE), client=http)
    assert res.verdict.label == "scam" and http.post.call_count == 3


def test_quota_exhaustion_fails_fast_instead_of_sleeping(monkeypatch):
    slept = []
    monkeypatch.setattr(jev.time, "sleep", slept.append)
    http = MagicMock()
    http.post.return_value = MagicMock(status_code=429, headers={"retry-after": "64016"})
    with pytest.raises(CheckError, match="quota is used up"):
        check("hi", CheckerConfig(model=JEV_FREE), client=http)
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
