"""Compute engineering impact stats, VOR, and ceiling/floor classifications."""

import json
import math
import os
from collections import defaultdict
from datetime import datetime

import anthropic
from dotenv import load_dotenv

load_dotenv()

MIN_PRS = 3

# VOR weights — bug_fixes/feature_prs dropped because PostHog barely labels PRs.
# Replaced with avg_review_turnaround (inverted: lower = better = higher z-score).
WEIGHTS = {
    "prs_authored": 0.20,
    "prs_reviewed": 0.20,
    "review_comments": 0.10,
    "areas_touched": 0.15,
    "review_turnaround_inv": 0.10,
    "net_lines_dampened": 0.10,
    "large_prs": 0.15,
}


def classify_pr_size(additions, deletions):
    total = additions + deletions
    if total < 50:
        return "S"
    elif total < 250:
        return "M"
    elif total < 1000:
        return "L"
    return "XL"


def compute_stats(data):
    """Compute per-engineer stats from raw PR data."""
    prs = data["prs"]

    # Per-engineer accumulators
    authored = defaultdict(list)
    reviewed = defaultdict(lambda: {"count": 0, "comments": 0, "turnarounds": []})

    for pr in prs:
        author = pr["author"]
        authored[author].append(pr)

        # Track reviews
        seen_reviewers = set()
        for review in pr["reviews"]:
            reviewer = review["author"]
            if not reviewer or reviewer == author:
                continue
            if reviewer in seen_reviewers:
                # Count additional comments but don't double-count review
                reviewed[reviewer]["comments"] += review["commentCount"]
                continue
            seen_reviewers.add(reviewer)
            reviewed[reviewer]["count"] += 1
            reviewed[reviewer]["comments"] += review["commentCount"]

            # Review turnaround
            if review["submittedAt"] and pr["createdAt"]:
                created = datetime.fromisoformat(pr["createdAt"].replace("Z", "+00:00"))
                submitted = datetime.fromisoformat(review["submittedAt"].replace("Z", "+00:00"))
                hours = (submitted - created).total_seconds() / 3600
                if hours >= 0:
                    reviewed[reviewer]["turnarounds"].append(hours)

    # Build stats for qualifying engineers
    all_engineers = set(authored.keys()) | set(reviewed.keys())
    stats = {}

    for eng in all_engineers:
        eng_prs = authored.get(eng, [])
        eng_reviews = reviewed.get(eng, {"count": 0, "comments": 0, "turnarounds": []})

        if len(eng_prs) < MIN_PRS:
            continue

        areas = set()
        bug_fixes = 0
        feature_prs = 0
        net_lines = 0
        large_count = 0
        size_dist = {"S": 0, "M": 0, "L": 0, "XL": 0}

        for pr in eng_prs:
            # Areas
            for f in pr["files"]:
                parts = f.split("/")
                if parts:
                    areas.add(parts[0])

            # Labels
            labels_lower = [l.lower() for l in pr["labels"]]
            if any("bug" in l for l in labels_lower):
                bug_fixes += 1
            if any(l in ("feature", "enhancement") or "feature" in l for l in labels_lower):
                feature_prs += 1

            net_lines += pr["additions"] - pr["deletions"]
            size = classify_pr_size(pr["additions"], pr["deletions"])
            size_dist[size] += 1
            if size in ("L", "XL"):
                large_count += 1

        turnarounds = eng_reviews["turnarounds"]
        avg_turnaround = sum(turnarounds) / len(turnarounds) if turnarounds else None

        stats[eng] = {
            "prs_authored": len(eng_prs),
            "prs_reviewed": eng_reviews["count"],
            "review_comments": eng_reviews["comments"],
            "avg_review_turnaround_hours": round(avg_turnaround, 1) if avg_turnaround else None,
            "areas_touched": len(areas),
            "area_list": sorted(areas),
            "bug_fixes": bug_fixes,
            "feature_prs": feature_prs,
            "net_lines": net_lines,
            "large_prs": large_count,
            "size_distribution": size_dist,
        }

    return stats


def log_dampen(x):
    """Sign-preserving log dampening."""
    return math.copysign(math.log1p(abs(x)), x)


def compute_vor(stats):
    """Compute VOR z-scores for each engineer."""
    import statistics

    metrics = list(WEIGHTS.keys())
    engineers = list(stats.keys())

    # Collect raw values
    raw = {}
    for m in metrics:
        if m == "net_lines_dampened":
            raw[m] = [log_dampen(stats[e]["net_lines"]) for e in engineers]
        elif m == "review_turnaround_inv":
            # Invert turnaround: lower hours = better. Use negative so higher z = faster.
            # Engineers with no reviews get median (0 z-score) via fallback.
            median_ta = statistics.median([
                stats[e]["avg_review_turnaround_hours"]
                for e in engineers
                if stats[e]["avg_review_turnaround_hours"] is not None
            ]) if any(stats[e]["avg_review_turnaround_hours"] is not None for e in engineers) else 0
            raw[m] = [
                -(stats[e]["avg_review_turnaround_hours"])
                if stats[e]["avg_review_turnaround_hours"] is not None
                else -median_ta
                for e in engineers
            ]
        else:
            raw[m] = [stats[e][m] for e in engineers]

    # Compute z-scores
    medians = {}
    stdevs = {}
    for m in metrics:
        medians[m] = statistics.median(raw[m])
        stdevs[m] = statistics.stdev(raw[m]) if len(raw[m]) > 1 else 1

    for i, eng in enumerate(engineers):
        vor = 0
        z_scores = {}
        for m in metrics:
            std = stdevs[m] if stdevs[m] > 0 else 1
            z = (raw[m][i] - medians[m]) / std
            z_scores[m] = round(z, 2)
            vor += WEIGHTS[m] * z

        stats[eng]["vor"] = round(vor, 2)
        stats[eng]["z_scores"] = z_scores

    return stats


def classify_ceiling_floor(stats):
    """Classify engineers as ceiling raisers, floor raisers, or both."""
    engineers = list(stats.keys())

    # Ceiling composite: ambitious, broad contributions
    ceiling_keys = ["large_prs", "net_lines_dampened", "areas_touched"]
    # Floor composite: team enablement and review quality
    floor_keys = ["prs_reviewed", "review_comments", "review_turnaround_inv"]

    for eng in engineers:
        z = stats[eng]["z_scores"]
        ceiling_score = sum(z.get(k, 0) for k in ceiling_keys) / len(ceiling_keys)
        floor_score = sum(z.get(k, 0) for k in floor_keys) / len(floor_keys)
        stats[eng]["ceiling_score"] = round(ceiling_score, 2)
        stats[eng]["floor_score"] = round(floor_score, 2)

    # Thresholds: 80th percentile
    ceiling_scores = sorted([stats[e]["ceiling_score"] for e in engineers])
    floor_scores = sorted([stats[e]["floor_score"] for e in engineers])

    ceiling_threshold = ceiling_scores[int(len(ceiling_scores) * 0.80)] if ceiling_scores else 0
    floor_threshold = floor_scores[int(len(floor_scores) * 0.80)] if floor_scores else 0

    for eng in engineers:
        tags = []
        if stats[eng]["ceiling_score"] >= ceiling_threshold:
            tags.append("Ceiling Raiser")
        if stats[eng]["floor_score"] >= floor_threshold:
            tags.append("Floor Raiser")
        stats[eng]["type"] = ", ".join(tags) if tags else "—"

    return stats


def generate_llm_summary(stats, cache_path="data/llm_summary.txt"):
    """Generate LLM narrative for top engineers."""
    if os.path.exists(cache_path):
        with open(cache_path) as f:
            return f.read()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        try:
            import streamlit as st
            api_key = st.secrets.get("ANTHROPIC_API_KEY")
        except Exception:
            pass

    if not api_key:
        return "LLM summary unavailable — no API key configured."

    # Top 5 by VOR
    ranked = sorted(stats.items(), key=lambda x: x[1]["vor"], reverse=True)[:5]
    profile = "\n".join(
        f"- {eng}: VOR={s['vor']}, PRs={s['prs_authored']}, Reviews={s['prs_reviewed']}, "
        f"Areas={s['areas_touched']}, Large PRs={s['large_prs']}, "
        f"Avg Review Turnaround={s['avg_review_turnaround_hours']}h, Type={s['type']}"
        for eng, s in ranked
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=300,
            messages=[{
                "role": "user",
                "content": (
                    f"You're analyzing engineering impact at PostHog over the last 90 days. "
                    f"Here are the top 5 engineers by Value Over Replacement (VOR) score:\n\n"
                    f"{profile}\n\n"
                    f"Write 2-3 sentences summarizing who stands out and why. Be specific about "
                    f"what makes each person impactful. Don't use superlatives — use the numbers.\n\n"
                    f'Example tone: "X authored 47 PRs across 8 areas, suggesting a generalist role, '
                    f"while Y's 92 reviews and 4-hour median turnaround made them the team's primary unlocker.\""
                ),
            }],
        )
        summary = resp.content[0].text
    except Exception as e:
        summary = f"LLM summary unavailable — {e}"

    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "w") as f:
        f.write(summary)

    return summary


def compute_area_matrix(data, engineers, top_n_areas=15):
    """Build engineer x directory matrix of PR counts for top directories."""
    from collections import Counter

    # Count total PRs per top-level directory across all engineers
    dir_counts = Counter()
    eng_dir_counts = defaultdict(Counter)

    for pr in data["prs"]:
        author = pr["author"]
        if author not in engineers:
            continue
        dirs_in_pr = set()
        for f in pr["files"]:
            parts = f.split("/")
            if parts and not parts[0].startswith("."):
                dirs_in_pr.add(parts[0])
        for d in dirs_in_pr:
            dir_counts[d] += 1
            eng_dir_counts[author][d] += 1

    top_dirs = [d for d, _ in dir_counts.most_common(top_n_areas)]
    return top_dirs, eng_dir_counts


def load_and_analyze(data_path="data/posthog_data.json"):
    """Full pipeline: load data, compute stats, VOR, classifications."""
    with open(data_path) as f:
        data = json.load(f)

    stats = compute_stats(data)
    stats = compute_vor(stats)
    stats = classify_ceiling_floor(stats)

    return data, stats
