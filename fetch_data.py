"""Fetch merged PRs from PostHog/posthog via GitHub GraphQL API."""

import json
import os
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
REPO = "PostHog/posthog"
DAYS = 90
OUTPUT = "data/posthog_data.json"

BOT_LOGINS = {
    "posthog-bot",
    "dependabot[bot]",
    "github-actions[bot]",
    "posthog-contributions-bot",
    "codecov[bot]",
    "codecov-commenter",
    "mendral-app",
}

QUERY_TEMPLATE = """
query($cursor: String) {{
  search(
    query: "repo:PostHog/posthog is:pr is:merged merged:{date_filter}"
    type: ISSUE
    first: 50
    after: $cursor
  ) {{
    pageInfo {{ hasNextPage endCursor }}
    nodes {{
      ... on PullRequest {{
        number
        title
        author {{ login }}
        additions
        deletions
        changedFiles
        createdAt
        mergedAt
        labels(first: 10) {{ nodes {{ name }} }}
        commits {{ totalCount }}
        reviews(first: 20) {{
          nodes {{
            author {{ login }}
            state
            submittedAt
            comments {{ totalCount }}
          }}
        }}
        files(first: 50) {{
          nodes {{ path }}
        }}
      }}
    }}
  }}
}}
"""


def _parse_pr(pr):
    """Parse a single PR node into our format. Returns None if bot/invalid."""
    author = pr.get("author")
    login = author["login"] if author else None
    if not login or login in BOT_LOGINS:
        return None
    return {
        "number": pr["number"],
        "title": pr["title"],
        "author": login,
        "additions": pr["additions"],
        "deletions": pr["deletions"],
        "changedFiles": pr["changedFiles"],
        "createdAt": pr["createdAt"],
        "mergedAt": pr["mergedAt"],
        "labels": [l["name"] for l in pr["labels"]["nodes"]],
        "commits": pr["commits"]["totalCount"],
        "reviews": [
            {
                "author": r["author"]["login"] if r.get("author") else None,
                "state": r["state"],
                "submittedAt": r["submittedAt"],
                "commentCount": r["comments"]["totalCount"],
            }
            for r in pr["reviews"]["nodes"]
        ],
        "files": [f["path"] for f in pr["files"]["nodes"]],
    }


def _fetch_date_range(date_filter, headers):
    """Fetch all PRs matching a date filter string like '2025-12-12..2026-01-15'."""
    query = QUERY_TEMPLATE.format(date_filter=date_filter)
    all_prs = []
    cursor = None
    page = 0

    while True:
        page += 1
        variables = {"cursor": cursor}
        resp = requests.post(
            "https://api.github.com/graphql",
            json={"query": query, "variables": variables},
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        if "errors" in data:
            print(f"GraphQL errors: {data['errors']}")
            break

        search = data["data"]["search"]
        for pr in search["nodes"]:
            parsed = _parse_pr(pr)
            if parsed:
                all_prs.append(parsed)

        print(f"  [{date_filter}] page {page}: {len(all_prs)} PRs so far")

        if not search["pageInfo"]["hasNextPage"]:
            break
        cursor = search["pageInfo"]["endCursor"]

    return all_prs


def fetch_all_prs():
    since_date = datetime.now(timezone.utc) - timedelta(days=DAYS)
    now = datetime.now(timezone.utc)

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Content-Type": "application/json",
    }

    # Split into 15-day chunks to stay well under 1000-result search limit
    chunks = []
    chunk_start = since_date
    while chunk_start < now:
        chunk_end = min(chunk_start + timedelta(days=15), now)
        chunks.append((chunk_start.strftime("%Y-%m-%d"), chunk_end.strftime("%Y-%m-%d")))
        chunk_start = chunk_end + timedelta(days=1)

    all_prs = []
    seen_numbers = set()
    for start, end in chunks:
        date_filter = f"{start}..{end}"
        print(f"Fetching chunk: {date_filter}")
        chunk_prs = _fetch_date_range(date_filter, headers)
        for pr in chunk_prs:
            if pr["number"] not in seen_numbers:
                seen_numbers.add(pr["number"])
                all_prs.append(pr)
        print(f"  -> {len(chunk_prs)} in chunk, {len(all_prs)} total unique")

    return all_prs, since_date.strftime("%Y-%m-%d")


def main():
    if not GITHUB_TOKEN:
        print("Error: GITHUB_TOKEN not set in .env")
        return

    os.makedirs("data", exist_ok=True)
    prs, since = fetch_all_prs()

    output = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "period_start": since,
        "repo": REPO,
        "days": DAYS,
        "total_prs": len(prs),
        "prs": prs,
    }

    with open(OUTPUT, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nSaved {len(prs)} PRs to {OUTPUT}")


if __name__ == "__main__":
    main()
