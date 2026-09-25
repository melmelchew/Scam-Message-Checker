from scamcheck.rules import signals


def test_otp_request_detected():
    assert "asks for OTP, PIN or password" in signals("Please reply with the 6-digit OTP to cancel.")


def test_legit_otp_notice_is_not_a_request():
    assert "asks for OTP, PIN or password" not in signals("Your OTP is 123456. Do not share it with anyone.")


def test_shortener_and_urgency():
    s = signals("URGENT: account suspended, verify at bit.ly/abc")
    assert {"uses a link shortener", "urgency or threat language", "contains a link"} <= set(s)


def test_payment_and_chat_app():
    s = signals("Buy Google Play cards and add me on WhatsApp")
    assert {"unusual payment method", "asks to move to another chat app"} <= set(s)


def test_plain_message_has_no_signals():
    assert signals("Are we still on for dinner tonight?") == []


def test_negated_share_is_a_warning_not_a_request():
    assert "asks for OTP, PIN or password" not in signals("Your OTP is 482913. Do not share this OTP with anyone.")
    assert "asks for OTP, PIN or password" not in signals("Never share your PIN with anyone.")
    assert "asks for OTP, PIN or password" in signals("Please share this OTP with our officer.")
