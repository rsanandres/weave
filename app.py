"""PostHog Engineering Impact Dashboard — Streamlit app."""

import altair as alt
import pandas as pd
import streamlit as st

from analyze import (
    format_cycle_time,
    generate_llm_summary,
    load_and_analyze,
    WEIGHTS,
    WEIGHT_LABELS,
)

st.set_page_config(page_title="PostHog Engineering Impact", layout="wide")


CACHE_VERSION = "v3"


@st.cache_data(ttl=3600)
def get_data(cache_version=CACHE_VERSION):
    data, stats = load_and_analyze()
    return data, stats


data, stats = get_data()

total_prs = data["total_prs"]
period_start = data["period_start"]
n_engineers = len(stats)

# --- Header ---
st.title("PostHog Engineering Impact")
st.caption(
    f"Last 90 days (since {period_start}) · {total_prs} merged PRs · "
    f"{n_engineers} qualifying contributors (≥3 PRs)"
)

# --- LLM Summary ---
summary = generate_llm_summary(stats)
st.info(summary)

# --- Controls ---
top_n = st.slider(
    "Show top N engineers",
    min_value=3,
    max_value=min(25, n_engineers),
    value=min(10, n_engineers),
)

# --- Build ranked data ---
ranked = sorted(stats.items(), key=lambda x: x[1]["vor"], reverse=True)


def _type_icons(type_str):
    icons = ""
    if "Ceiling" in type_str:
        icons += "\u25c6"  # ◆ Builder
    if "Floor" in type_str:
        icons += "\u25cf"  # ● Enabler
    return icons


# ============================================================
# Leaderboard + Charts — three columns
# ============================================================

col_lb, col1, col2 = st.columns([1, 1, 1])

# --- VOR Leaderboard ---
with col_lb:
    st.subheader("Impact Leaderboard")
    st.caption(
        "50 = median, higher = more impact. "
        "◆ Builder (large PRs, broad areas, net code output) · "
        "● Enabler (reviews, comments, fast cycle time)"
    )

    lb_rows = []
    for rank, (eng, s) in enumerate(ranked[:top_n], 1):
        icon = _type_icons(s["type"])
        label = f"{eng} {icon}" if icon else eng
        lb_rows.append({
            "Rank": rank,
            "Engineer": label,
            "Impact Score": s["impact_score"],
        })

    lb_df = pd.DataFrame(lb_rows)

    st.dataframe(
        lb_df,
        use_container_width=True,
        hide_index=True,
        height=min(420, 35 * top_n + 40),
        column_config={
            "Rank": st.column_config.NumberColumn(
                "Rank", help="Ranked by Impact Score", width="small"
            ),
            "Engineer": st.column_config.TextColumn(
                "Engineer",
                help="◆ Builder = top 20% in large PRs, areas touched, net lines. ● Enabler = top 20% in reviews, comments, cycle time.",
            ),
            "Impact Score": st.column_config.ProgressColumn(
                "Impact Score",
                help="Sigmoid-scaled VOR. 50 = median contributor, 70+ = strong, 85+ = standout.",
                min_value=0,
                max_value=100,
                format="%0.0f",
            ),
        },
    )

# --- Authoring vs Reviewing Scatter ---
with col1:
    st.subheader("Authoring vs. Reviewing")
    st.caption("Bubble size = unique teammates unblocked via reviews")
    scatter_df = pd.DataFrame({
        "Engineer": [e for e, _ in ranked],
        "PRs Authored": [s["prs_authored"] for _, s in ranked],
        "PRs Reviewed": [s["prs_reviewed"] for _, s in ranked],
        "Unblock Breadth": [s["unique_authors_reviewed"] for _, s in ranked],
        "Impact": [s["impact_score"] for _, s in ranked],
    })

    scatter = (
        alt.Chart(scatter_df)
        .mark_circle()
        .encode(
            x=alt.X("PRs Authored:Q"),
            y=alt.Y("PRs Reviewed:Q"),
            size=alt.Size("Unblock Breadth:Q", scale=alt.Scale(range=[30, 400]), legend=None),
            tooltip=["Engineer", "PRs Authored", "PRs Reviewed", "Unblock Breadth", "Impact"],
            color=alt.Color("Impact:Q", scale=alt.Scale(scheme="redyellowgreen"), legend=None),
        )
        .properties(height=380)
        .interactive()
    )

    label_df = scatter_df.head(min(top_n, 5))
    labels = (
        alt.Chart(label_df)
        .mark_text(align="left", dx=7, fontSize=10)
        .encode(
            x="PRs Authored:Q",
            y="PRs Reviewed:Q",
            text="Engineer:N",
        )
    )

    st.altair_chart(scatter + labels, use_container_width=True)

# --- Impact Breakdown Stacked Bar ---
with col2:
    st.subheader("Impact Breakdown")
    breakdown_n = min(top_n, 5)
    top_engineers = [e for e, _ in ranked[:breakdown_n]]

    breakdown_rows = []
    for eng in top_engineers:
        z = stats[eng]["z_scores"]
        impact = stats[eng]["impact_score"]
        # Get positive contributions, allocate impact score proportionally
        contribs = {k: max(z.get(k, 0) * w, 0) for k, w in WEIGHTS.items()}
        total = sum(contribs.values()) or 1
        for metric_key in WEIGHTS:
            breakdown_rows.append({
                "Engineer": eng,
                "Component": WEIGHT_LABELS.get(metric_key, metric_key),
                "Contribution": round(contribs[metric_key] / total * impact, 1),
            })

    bd_df = pd.DataFrame(breakdown_rows)

    breakdown_chart = (
        alt.Chart(bd_df)
        .mark_bar()
        .encode(
            y=alt.Y("Engineer:N", sort=top_engineers, title=None),
            x=alt.X("Contribution:Q", title="Impact Score Contribution", stack="zero"),
            color=alt.Color(
                "Component:N",
                scale=alt.Scale(scheme="tableau10"),
                legend=alt.Legend(orient="bottom", columns=4, title=None),
            ),
            tooltip=["Engineer", "Component", alt.Tooltip("Contribution:Q", format=".1f")],
        )
        .properties(height=380)
    )
    st.altair_chart(breakdown_chart, use_container_width=True)

# ============================================================
# Metric Explorer — in expander
# ============================================================
with st.expander("Metric Explorer"):
    metric_options = {
        "PRs Authored": "prs_authored",
        "PRs Reviewed": "prs_reviewed",
        "Review Comments": "review_comments",
        "Large PRs (L+XL)": "large_prs",
        "Areas Touched": "areas_touched",
        "Net Lines": "net_lines",
        "Avg Cycle Time (hrs)": "avg_cycle_time",
    }

    selected_label = st.selectbox("Select metric", list(metric_options.keys()))
    selected_metric = metric_options[selected_label]

    lower_is_better = {"avg_cycle_time"}
    reverse = selected_metric not in lower_is_better

    metric_ranked = sorted(
        stats.items(),
        key=lambda x: x[1].get(selected_metric, 0) or 0,
        reverse=reverse,
    )[:top_n]
    chart_df = pd.DataFrame({
        "Engineer": [e for e, _ in metric_ranked],
        selected_label: [s.get(selected_metric, 0) or 0 for _, s in metric_ranked],
    })

    st.bar_chart(chart_df, x="Engineer", y=selected_label, horizontal=True)

# --- Full Stats Table ---
with st.expander("Full Stats Table"):
    all_rows = []
    for eng, s in ranked:
        all_rows.append({
            "Engineer": eng,
            "Impact Score": s["impact_score"],
            "Type": s["type"],
            "PRs Authored": s["prs_authored"],
            "PRs Reviewed": s["prs_reviewed"],
            "Review Comments": s["review_comments"],
            "Avg Cycle Time": format_cycle_time(s["avg_cycle_time"]),
            "Avg Review Turnaround": format_cycle_time(s["avg_review_turnaround_hours"]),
            "Large PRs": s["large_prs"],
            "Areas Touched": s["areas_touched"],
            "Net Lines": s["net_lines"],
            "Size Dist": (
                f"S:{s['size_distribution']['S']} M:{s['size_distribution']['M']} "
                f"L:{s['size_distribution']['L']} XL:{s['size_distribution']['XL']}"
            ),
        })
    st.dataframe(pd.DataFrame(all_rows), use_container_width=True, hide_index=True)

# --- Methodology ---
with st.expander("Methodology"):
    st.markdown("""
### Impact Score (VOR)

The Impact Score measures how much an engineer exceeds the typical (median) contributor across multiple dimensions. Raw VOR z-scores are passed through a sigmoid function to produce a 0-100 scale: **50 = median, 70+ = strong, 85+ = standout**.

**Formula:** For each metric, we compute a z-score: `z = (value - median) / stddev`. The final VOR is a weighted sum of these z-scores, then scaled: `score = 100 / (1 + e^(-VOR * 1.5))`.

| Metric | Weight | Rationale |
|--------|--------|-----------|
| PRs Authored | 0.20 | Raw output volume |
| PRs Reviewed | 0.20 | Team multiplier — unblocking others |
| Review Comments | 0.10 | Depth of review engagement |
| Areas Touched | 0.15 | Cross-cutting breadth of contribution |
| Cycle Time (inv) | 0.10 | PR creation to merge — faster = higher score |
| Net Lines (dampened) | 0.10 | Scale of change, log-dampened to avoid rewarding bloat |
| Large PRs (L+XL) | 0.15 | Willingness to tackle substantial changes |

**Log dampening** on net lines: `sign(x) * log(1 + |x|)` — prevents an engineer who adds 50K lines from dominating the score.

### PR Size Tiers
- **S**: < 50 lines changed · **M**: 50-249 · **L**: 250-999 · **XL**: 1000+

### Builder vs. Enabler

- **Builder ◆** (top 20th percentile): High z-scores in large PRs, net lines, and areas touched. Pushes the product forward with ambitious, broad contributions.
- **Enabler ●** (top 20th percentile): High z-scores in PRs reviewed, review comments, and cycle time. Keeps quality high and unblocks the team.
- Engineers can be both, neither, or one.

### Known Limitations
- **Label-dependent metrics removed**: PostHog labels <10% of PRs, so bug fix and feature PR counts were excluded from scoring as unreliable signals.
- **90-day window**: Does not account for vacations, on-call rotations, or parental leave.
- **File truncation**: GitHub API returns max 50 files per PR. Large PRs with 100+ files may have undercounted area coverage.
- **Review turnaround**: Measured from PR creation to first review, not from when review was requested. Displayed in Full Stats Table for context but not included in Impact Score. Cycle time (creation to merge) is used instead.

### Qualification
Engineers must have authored ≥3 merged PRs in the period to qualify. Bot accounts are excluded.
""")
