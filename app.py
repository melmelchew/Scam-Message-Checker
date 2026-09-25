import streamlit as st

from scamcheck import DEFAULT_CONFIG, CheckError, check

BADGES = {"scam": ("🚨 Likely scam", "red"), "suspicious": ("⚠️ Suspicious, verify first", "orange"), "legit": ("✅ Looks legit", "green")}
# Below this, the top label is shown with a caution naming the runner-up.
LOW_CONFIDENCE = 0.6

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
    d = result.details
    text, color = BADGES[v.label]
    st.markdown(f"## :{color}[{text}]")
    if d and d["confidence"] < LOW_CONFIDENCE:
        others = {k: p for k, p in d["label_probabilities"].items() if k != v.label}
        runner_up = max(others, key=others.get)
        st.warning(f"Jev isn't sure about this one: there's a {others[runner_up]:.0%} chance it's **{runner_up}**. Treat it with care.")
    st.progress(min(max(v.risk_score, 0), 100) / 100, text=f"Risk score {v.risk_score}/100")
    st.write(v.explanation)
    if v.red_flags:
        st.subheader("Red flags")
        for flag in v.red_flags:
            st.markdown(f"- {flag}")
    st.info(f"**What to do:** {v.advice}")

    with st.expander("Details"):
        if d:
            st.markdown("**How likely each verdict is**")
            for label in ("scam", "suspicious", "legit"):
                p = d["label_probabilities"].get(label, 0)
                st.progress(p, text=f"{BADGES[label][0]}: {p:.0%}")
            st.caption(f"Jev's confidence in its top answer: {d['confidence']:.0%}")

            if d["tactics"]:
                st.markdown("**Scam tactic checks** (how likely each one is present)")
                for name, p in sorted(d["tactics"].items(), key=lambda kv: -kv[1]):
                    st.markdown(f"{'⚠️' if p > 0.5 else '✅'} {name}: **{p:.0%}**")
            if d["injection"] is not None:
                icon = "⚠️" if d["injection"] > 0.5 else "✅"
                st.markdown(f"{icon} Tries to instruct the checker: **{d['injection']:.0%}**")
                if d["jev_label"] != v.label:
                    st.caption(f"Jev's own answer was '{d['jev_label']}'; it was raised to '{v.label}' because the message tries to manipulate the checker.")

        st.markdown("**Keyword hints** (simple pattern matches, passed to Jev as hints)")
        st.write(", ".join(result.signals) if result.signals else "No suspicious keywords found.")
        st.caption(f"{DEFAULT_CONFIG.model} · {DEFAULT_CONFIG.prompt_version} · {result.latency_s:.1f}s")

st.divider()
st.caption("This is a guide, not a guarantee. When in doubt, contact the organisation through its official number or app.")
