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

QUERY = """
query($cursor: String) {
  search(
    query: "repo:PostHog/posthog is:pr is:merged merged:>=SINCE_DATE"
    type: ISSUE
    first: 50
    after: $cursor
  ) {
    pageInfo { hasNextPage endCursor }
    nodes {
      ... on PullRequest {
        number
        title
        author { login }
        additions
        deletions
        changedFiles
        createdAt
        mergedAt
        labels(first: 10) { nodes { name } }
        commits { totalCount }
        reviews(first: 20) {
          nodes {
            author { login }
            state
            submittedAt
            comments { totalCount }
          }
        }
        files(first: 50) {
          nodes { path }
        }
      }
    }
  }
}
"""


def fetch_all_prs():
    since = (datetime.now(timezone.utc) - timedelta(days=DAYS)).strftime("%Y-%m-%d")
    query = QUERY.replace("SINCE_DATE", since)

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Content-Type": "application/json",
    }

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
        nodes = search["nodes"]

        for pr in nodes:
            author = pr.get("author")
            login = author["login"] if author else None
            if login and login in BOT_LOGINS:
                continue
            if not login:
                continue

            all_prs.append({
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
            })

        print(f"Page {page}: fetched {len(nodes)} PRs ({len(all_prs)} total after bot filter)")

        if not search["pageInfo"]["hasNextPage"]:
            break
        cursor = search["pageInfo"]["endCursor"]

    return all_prs, since


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
