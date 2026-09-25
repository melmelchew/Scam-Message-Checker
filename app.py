import streamlit as st

from scamcheck import DEFAULT_CONFIG, CheckError, check

BADGES = {"scam": ("🚨 Likely scam", "red"), "suspicious": ("⚠️ Suspicious, verify first", "orange"), "legit": ("✅ Looks legit", "green")}

st.set_page_config(page_title="Scam Message Checker", page_icon="🛡️")
st.title("🛡️ Scam Message Checker")
st.caption("Paste an SMS, email, or chat message. It is sent to the Jev model (TypeSafe AI) for checking; this app does not store it.")

message = st.text_area("Message", height=180, placeholder="e.g. Your parcel is held at customs, pay $1.99 at bit.ly/...")

if st.button("Check message", type="primary"):
    with st.spinner("Checking..."):
        try:
            result = check(message)
        except CheckError as e:
            st.error(str(e))
            st.stop()

    v = result.verdict
    text, color = BADGES[v.label]
    st.markdown(f"## :{color}[{text}]")
    st.progress(min(max(v.risk_score, 0), 100) / 100, text=f"Risk score {v.risk_score}/100")
    st.write(v.explanation)
    if v.red_flags:
        st.subheader("Red flags")
        for flag in v.red_flags:
            st.markdown(f"- {flag}")
    st.info(f"**What to do:** {v.advice}")
    with st.expander("Details"):
        st.write("Pattern signals:", result.signals or "none")
        conf = f" · confidence {result.confidence:.0%}" if result.confidence is not None else ""
        st.caption(f"{DEFAULT_CONFIG.model} · {DEFAULT_CONFIG.prompt_version}{conf} · {result.latency_s:.1f}s")

st.divider()
st.caption("This is a guide, not a guarantee. When in doubt, contact the organisation through its official number or app.")
