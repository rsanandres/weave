"""PostHog Engineering Impact Dashboard — Streamlit app."""

import pandas as pd
import streamlit as st

from analyze import generate_llm_summary, load_and_analyze, WEIGHTS

st.set_page_config(page_title="PostHog Engineering Impact", layout="wide")


@st.cache_data
def get_data():
    data, stats = load_and_analyze()
    return data, stats


data, stats = get_data()

total_prs = data["total_prs"]
period_start = data["period_start"]
n_engineers = len(stats)

# --- Header ---
st.title("PostHog Engineering Impact")
st.caption(f"Last 90 days (since {period_start}) · {total_prs} merged PRs · {n_engineers} qualifying contributors (≥3 PRs)")

# --- LLM Summary ---
summary = generate_llm_summary(stats)
st.info(summary)

# --- Controls ---
top_n = st.slider("Show top N engineers", min_value=3, max_value=min(25, n_engineers), value=min(10, n_engineers))

# --- Build leaderboard dataframe ---
ranked = sorted(stats.items(), key=lambda x: x[1]["vor"], reverse=True)

rows = []
for rank, (eng, s) in enumerate(ranked[:top_n], 1):
    rows.append({
        "Rank": rank,
        "Engineer": eng,
        "Impact (VOR)": s["vor"],
        "Type": s["type"],
        "PRs Authored": s["prs_authored"],
        "PRs Reviewed": s["prs_reviewed"],
        "Large PRs": s["large_prs"],
        "Areas": s["areas_touched"],
        "Review Comments": s["review_comments"],
        "Avg Turnaround (hrs)": s["avg_review_turnaround_hours"] or "—",
        "Net Lines": s["net_lines"],
    })

df = pd.DataFrame(rows)

# --- VOR Leaderboard ---
st.subheader("VOR Leaderboard")
st.caption("Value Over Replacement — how much each engineer exceeds the median contributor. 0 = median, positive = above.")
st.dataframe(
    df,
    use_container_width=True,
    hide_index=True,
    height=min(400, 35 * top_n + 38),
    column_config={
        "Impact (VOR)": st.column_config.ProgressColumn(
            "Impact (VOR)", format="%.2f", min_value=-2, max_value=3,
        ),
    },
)

# --- Metric Explorer ---
st.subheader("Metric Explorer")

metric_options = {
    "PRs Authored": "prs_authored",
    "PRs Reviewed": "prs_reviewed",
    "Review Comments": "review_comments",
    "Large PRs (L+XL)": "large_prs",
    "Areas Touched": "areas_touched",
    "Net Lines": "net_lines",
    "Avg Review Turnaround (hrs)": "avg_review_turnaround_hours",
}

selected_label = st.selectbox("Select metric", list(metric_options.keys()))
selected_metric = metric_options[selected_label]

# Get top N for selected metric
metric_ranked = sorted(stats.items(), key=lambda x: x[1].get(selected_metric, 0), reverse=True)[:top_n]
chart_df = pd.DataFrame({
    "Engineer": [e for e, _ in metric_ranked],
    selected_label: [s.get(selected_metric, 0) for _, s in metric_ranked],
})

st.bar_chart(chart_df, x="Engineer", y=selected_label, horizontal=True)

# --- Full Stats Table ---
with st.expander("Full Stats Table"):
    all_rows = []
    for eng, s in ranked:
        all_rows.append({
            "Engineer": eng,
            "Impact (VOR)": s["vor"],
            "Type": s["type"],
            "PRs Authored": s["prs_authored"],
            "PRs Reviewed": s["prs_reviewed"],
            "Review Comments": s["review_comments"],
            "Avg Review Turnaround (hrs)": s["avg_review_turnaround_hours"] or "—",
            "Large PRs": s["large_prs"],
            "Areas Touched": s["areas_touched"],
            "Net Lines": s["net_lines"],
            "Size Dist": f"S:{s['size_distribution']['S']} M:{s['size_distribution']['M']} L:{s['size_distribution']['L']} XL:{s['size_distribution']['XL']}",
        })
    st.dataframe(pd.DataFrame(all_rows), use_container_width=True, hide_index=True)

# --- Methodology ---
with st.expander("Methodology"):
    st.markdown("""
### Value Over Replacement (VOR)

VOR measures how much an engineer exceeds the typical (median) contributor across multiple dimensions of impact. A VOR of 0 means median performance; positive values indicate above-replacement impact.

**Formula:** For each metric, we compute a z-score: `z = (value - median) / stddev`. The final VOR is a weighted sum of these z-scores:

| Metric | Weight | Rationale |
|--------|--------|-----------|
| PRs Authored | 0.20 | Raw output volume |
| PRs Reviewed | 0.20 | Team multiplier — unblocking others |
| Review Comments | 0.10 | Depth of review engagement |
| Areas Touched | 0.15 | Cross-cutting breadth of contribution |
| Review Turnaround (inv) | 0.10 | Speed of first review — faster = higher score |
| Net Lines (dampened) | 0.10 | Scale of change, log-dampened to avoid rewarding bloat |
| Large PRs (L+XL) | 0.15 | Willingness to tackle substantial changes |

*Note: Bug fixes and feature PRs were initially planned as metrics but dropped because PostHog uses very few PR labels (<10% of PRs), making label-based signals unreliable. Review turnaround replaced bug fixes as a more data-rich measure of team enablement.*

**Log dampening** on net lines: `sign(x) * log(1 + |x|)` — prevents an engineer who adds 50K lines from dominating the score. The signal is "do they make meaningful-sized changes?" not "who wrote the most code."

### PR Size Tiers
- **S**: < 50 lines changed
- **M**: 50–249 lines
- **L**: 250–999 lines
- **XL**: 1000+ lines

### Ceiling Raiser vs. Floor Raiser

- **Ceiling Raiser** (top 20th percentile): High z-scores in large PRs, net lines, and areas touched. These engineers push the product forward with ambitious, broad contributions.
- **Floor Raiser** (top 20th percentile): High z-scores in PRs reviewed, review comments, and review turnaround speed. These engineers keep quality high and unblock the team.
- Engineers can be both, neither, or one.

### Qualification
Engineers must have authored ≥3 merged PRs in the period to qualify. Bot accounts are excluded.
""")
