"""PostHog Engineering Impact Dashboard — Streamlit app."""

import altair as alt
import pandas as pd
import streamlit as st

from analyze import (
    compute_area_matrix,
    generate_llm_summary,
    load_and_analyze,
)

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
        icons += "\u25b2"  # ▲
    if "Floor" in type_str:
        icons += "\u25bc"  # ▼
    return icons


# ============================================================
# VOR Leaderboard — slim 3-column table
# ============================================================
st.subheader("VOR Leaderboard")
st.caption(
    "Value Over Replacement — how much each engineer exceeds the median contributor. "
    "0 = median, positive = above.  "
    "▲ = Ceiling Raiser (top 20% in output & breadth) · ▼ = Floor Raiser (top 20% in reviews & speed)"
)

lb_rows = []
for rank, (eng, s) in enumerate(ranked[:top_n], 1):
    icon = _type_icons(s["type"])
    label = f"{eng} {icon}" if icon else eng
    lb_rows.append({
        "Rank": rank,
        "Engineer": label,
        "Impact (VOR)": s["vor"],
    })

lb_df = pd.DataFrame(lb_rows)

st.dataframe(
    lb_df,
    use_container_width=True,
    hide_index=True,
    height=min(400, 35 * top_n + 38),
    column_config={
        "Rank": st.column_config.NumberColumn(
            "Rank", help="Ranked by Impact (VOR) score"
        ),
        "Engineer": st.column_config.TextColumn(
            "Engineer",
            help="GitHub username. ▲ = ceiling raiser (pushes product forward). ▼ = floor raiser (maintains quality).",
        ),
        "Impact (VOR)": st.column_config.ProgressColumn(
            "Impact (VOR)",
            help="Weighted z-score across authoring, reviewing, breadth, and complexity. 0 = median contributor.",
            format="%.2f",
            min_value=-2,
            max_value=3,
        ),
    },
)

# ============================================================
# Three Graphs — side by side
# ============================================================

top_data = ranked[:top_n]
col1, col2, col3 = st.columns(3)

# --- Graph 1: VOR Bar Chart ---
with col1:
    st.subheader("Impact Scores")
    vor_df = pd.DataFrame({
        "Engineer": [e for e, _ in top_data],
        "VOR": [s["vor"] for _, s in top_data],
    })
    vor_df["color"] = vor_df["VOR"].apply(lambda v: "positive" if v >= 0 else "negative")

    vor_chart = (
        alt.Chart(vor_df)
        .mark_bar()
        .encode(
            y=alt.Y("Engineer:N", sort="-x", title=None),
            x=alt.X("VOR:Q", title="Impact (VOR)"),
            color=alt.Color(
                "color:N",
                scale=alt.Scale(domain=["positive", "negative"], range=["#2ecc71", "#e74c3c"]),
                legend=None,
            ),
            tooltip=["Engineer", "VOR"],
        )
        .properties(height=max(250, top_n * 28))
    )
    st.altair_chart(vor_chart, use_container_width=True)

# --- Graph 2: Authoring vs Reviewing Scatter ---
with col2:
    st.subheader("Authoring vs. Reviewing")
    scatter_df = pd.DataFrame({
        "Engineer": [e for e, _ in ranked],
        "PRs Authored": [s["prs_authored"] for _, s in ranked],
        "PRs Reviewed": [s["prs_reviewed"] for _, s in ranked],
        "VOR": [s["vor"] for _, s in ranked],
    })

    scatter = (
        alt.Chart(scatter_df)
        .mark_circle(size=60)
        .encode(
            x=alt.X("PRs Authored:Q"),
            y=alt.Y("PRs Reviewed:Q"),
            tooltip=["Engineer", "PRs Authored", "PRs Reviewed", "VOR"],
            color=alt.Color("VOR:Q", scale=alt.Scale(scheme="redyellowgreen"), legend=None),
        )
        .properties(height=max(250, top_n * 28))
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

# --- Graph 3: Areas Touched Heatmap ---
with col3:
    st.subheader("Area Coverage")
    top_engineers = [e for e, _ in ranked[:top_n]]
    top_dirs, eng_dir_counts = compute_area_matrix(data, set(stats.keys()), top_n_areas=10)

    heat_rows = []
    for eng in top_engineers:
        for d in top_dirs:
            heat_rows.append({
                "Engineer": eng,
                "Directory": d,
                "PRs": eng_dir_counts[eng].get(d, 0),
            })

    heat_df = pd.DataFrame(heat_rows)

    heatmap = (
        alt.Chart(heat_df)
        .mark_rect()
        .encode(
            x=alt.X("Directory:N", title=None, axis=alt.Axis(labelAngle=-45)),
            y=alt.Y("Engineer:N", sort=top_engineers, title=None),
            color=alt.Color("PRs:Q", scale=alt.Scale(scheme="blues"), title="PRs"),
            tooltip=["Engineer", "Directory", "PRs"],
        )
        .properties(height=max(250, top_n * 28))
    )
    st.altair_chart(heatmap, use_container_width=True)

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
        "Avg Review Turnaround (hrs)": "avg_review_turnaround_hours",
    }

    selected_label = st.selectbox("Select metric", list(metric_options.keys()))
    selected_metric = metric_options[selected_label]

    metric_ranked = sorted(
        stats.items(),
        key=lambda x: x[1].get(selected_metric, 0) or 0,
        reverse=True,
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
            "Impact (VOR)": s["vor"],
            "Type": s["type"],
            "PRs Authored": s["prs_authored"],
            "PRs Reviewed": s["prs_reviewed"],
            "Review Comments": s["review_comments"],
            "Avg Review Turnaround (hrs)": s["avg_review_turnaround_hours"] or "—",
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

- **Ceiling Raiser ▲** (top 20th percentile): High z-scores in large PRs, net lines, and areas touched. These engineers push the product forward with ambitious, broad contributions.
- **Floor Raiser ▼** (top 20th percentile): High z-scores in PRs reviewed, review comments, and review turnaround speed. These engineers keep quality high and unblock the team.
- Engineers can be both, neither, or one.

### Qualification
Engineers must have authored ≥3 merged PRs in the period to qualify. Bot accounts are excluded.
""")
