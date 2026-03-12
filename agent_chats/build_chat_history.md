# Weave Engineering Impact Dashboard — Build Chat History

## Session: 2026-03-12, 10:37–11:21 PDT (~1h 11m)

### Build Sequence

1. **10:37** — Wrote `fetch_data.py`, `analyze.py`, `app.py` in parallel
2. **10:39** — Fetched 1000 PRs (hit GitHub search API 1000-result limit)
3. **10:39** — Caught `mendral-app` as a bot (55 CI/test PRs), added to filter, re-fetched → 945 PRs
4. **10:41** — Verified analysis: 81 qualifying engineers, rankings look reasonable
5. **10:42** — Generated LLM summary via Claude API, cached to file
6. **10:43** — First commit + push. Started chunked data fetch (30-day chunks) in background
7. **10:47** — Fixed matplotlib crash on Streamlit Cloud (`background_gradient` → `ProgressColumn`)
8. **10:49** — Chunked fetch completed: **2,912 PRs** (up from 945). Committed expanded dataset
9. **10:50** — Applied review_instructions.md fixes:
   - Removed dead `feature_prs` z-score from ceiling composite
   - Replaced `bug_fixes` (PostHog labels <10% of PRs) with `review_turnaround_inv`
   - Added VOR caption for readability
   - Improved LLM prompt with example tone
10. **10:55** — Applied layout_instructions.md:
    - Slim leaderboard (3 columns: Rank, Engineer, Impact)
    - Three charts side by side: VOR bars, scatter, heatmap
    - Metric explorer demoted to expander
11. **10:59** — Dropped VOR bar chart (redundant with leaderboard ProgressColumn)
12. **11:00** — Put leaderboard + 2 charts in 3-column layout
13. **11:01** — Heatmap too cramped at 1/3 width, decided to replace
14. **11:03** — Renamed Ceiling/Floor Raiser → Builder (◆) / Enabler (●)
15. **11:05** — Applied final_instructions.md:
    - Sigmoid Impact Score (0-100 scale, 50=median)
    - `avg_cycle_time` metric (PR creation to merge)
    - VOR breakdown stacked bar chart
    - Known Limitations in methodology
16. **11:08** — Fixed Streamlit Cloud cache issue (stale data missing `impact_score`)
17. **11:12** — Added unblock breadth (unique authors reviewed) as bubble size on scatter
18. **11:15** — Fixed cache bust (`_` prefix params ignored by Streamlit)
19. **11:16** — Simplified VOR breakdown → Impact Score bar chart → then back to stacked bar (user preference)
20. **11:17** — Fixed stacked bar scaling so bars sum to exactly Impact Score
21. **11:18** — Regenerated LLM summary with Impact Score references, fixed methodology wording

### Key Decisions Made During Build

- **Bot filtering**: Added `mendral-app` to bot list after discovering it was a CI automation tool
- **Label metrics dropped**: PostHog labels <10% of PRs — `bug_fixes` and `feature_prs` were dead weight
- **Cycle time over review turnaround**: Cycle time (creation→merge) is a better quality signal than review turnaround (creation→first review)
- **Sigmoid scaling**: Raw VOR z-scores are meaningless to readers; 0-100 scale with 50=median is intuitive
- **Builder/Enabler naming**: More positive and self-explanatory than Ceiling/Floor Raiser
- **◆/● icons**: Both read as positive (vs ▲/▼ which implied up=good, down=bad)
- **Unblock breadth as bubble size**: Unique teammates reviewed is a proxy for team enablement breadth
- **15-day fetch chunks**: 30-day chunks still hit 1000 limit on the most recent month; 15-day fix attempted but hit GitHub 502 — 2,912 PRs is sufficient

### Final Architecture

```
weave/
  fetch_data.py       # GraphQL paginated fetch, 15-day chunked, bot filtering
  analyze.py          # Stats, VOR z-scores, sigmoid Impact Score, Builder/Enabler classification
  app.py              # Streamlit dashboard — leaderboard + bubble scatter + stacked breakdown
  data/
    posthog_data.json  # 2,912 merged PRs
    llm_summary.txt    # Cached Claude summary
```

### Bugs Encountered & Fixed

1. `background_gradient` needs matplotlib (not installed on Streamlit Cloud) → used `ProgressColumn`
2. `feature_prs` never got z-score (not in WEIGHTS) → removed from ceiling composite
3. Streamlit Cloud cache persists across deploys → added `cache_version` param
4. `_`-prefixed params ignored by `@st.cache_data` → renamed to `cache_version`
5. Stacked bar contributions exceeded 100 → proportional allocation from positive contributions
6. `defaultdict` lambda doesn't apply on `.get()` fallback → explicit fallback dict with `authors_reviewed`

### Commits (chronological)

1. `70026de` — Add engineering impact dashboard with VOR scoring
2. `475b5e2` → `52d3f21` — Fix matplotlib dependency
3. `6f2d588` — Expand dataset to 2912 PRs via chunked fetching
4. `3c1e917` — Fix review feedback (drop labels, add turnaround, improve readability)
5. `ffb801b` — Redesign layout (slim leaderboard, 3 charts, heatmap)
6. `6302175` — Drop redundant VOR bar chart
7. `f7aabbe` — Leaderboard + charts in 3 columns
8. `9d5a2d4` — Impact Score, cycle time, Builder/Enabler icons
9. `8b74701` → `3c4ecb8` — Cache bust fixes
10. `0743777` — Unblock breadth bubble chart
11. `254c87f` → `fb82ae1` — Impact breakdown stacked bar, fixed scaling
12. `d8c657a` — Final LLM summary + methodology fix
