"""Cheap regex signals passed to the model as hints. They never decide the verdict alone."""

import re

_PATTERNS: dict[str, re.Pattern[str]] = {
    "contains a link": re.compile(r"https?://|www\.|\b[\w-]+\.(com|net|org|xyz|top|info|link|click|io|ly|gd|gy|at|sg|co)\b", re.I),
    "uses a link shortener": re.compile(r"\b(bit\.ly|tinyurl\.com|t\.co|goo\.gl|is\.gd|rb\.gy|cutt\.ly|shorturl\.at)\b", re.I),
    "urgency or threat language": re.compile(
        r"\b(urgent|immediately|within \d+ ?(hours?|hrs?|mins?|minutes?)|suspended|locked|final (notice|warning)|"
        r"act now|expires? today|legal action|arrest|warrant)\b",
        re.I,
    ),
    "asks for OTP, PIN or password": re.compile(
        r"\b(send|share|reply with|provide|give|tell)\b.{0,40}\b(otp|one[- ]time (password|code)|pin|password|passcode|verification code)\b",
        re.I,
    ),
    "unusual payment method": re.compile(r"\b(gift ?cards?|itunes|google play cards?|bitcoin|btc|usdt|crypto|wire transfer|western union)\b", re.I),
    "prize or too-good-to-be-true offer": re.compile(
        r"\b(you('ve| have)? won|winner|lucky draw|claim your (prize|reward)|free (iphone|gift)|earn \$?\d+.{0,20}(per|a) (day|hour))\b",
        re.I,
    ),
    "asks to move to another chat app": re.compile(r"\b(add me on|contact me on|message me on|chat on) (whatsapp|telegram|signal|line|wechat)\b", re.I),
}


# "Do not share this OTP" is a warning, not a request.
_NEGATION = re.compile(r"\b(not|never|don't|dont|do not)\s+$", re.I)
_NEGATABLE = {"asks for OTP, PIN or password"}


def _matches(name: str, pattern: re.Pattern[str], message: str) -> bool:
    for m in pattern.finditer(message):
        if name not in _NEGATABLE or not _NEGATION.search(message[max(0, m.start() - 12) : m.start()]):
            return True
    return False


def signals(message: str) -> list[str]:
    return [name for name, pattern in _PATTERNS.items() if _matches(name, pattern, message)]
