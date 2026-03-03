"""
Reddit Per-Category Fetcher — wraps reddit_discover.py to fetch subreddits per category.
"""
import sys
import os
import time
from pathlib import Path

# Resolve the scripts root so we can import reddit_discover
_scripts_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_scripts_dir))

import requests

HEADERS = {
    "User-Agent": os.getenv("REDDIT_USER_AGENT", "x-trend-digest/1.0 (digest bot)"),
    "Accept": "application/json",
}
SLEEP = float(os.getenv("REDDIT_SLEEP", "1.1"))
MIN_SCORE = int(os.getenv("REDDIT_MIN_SCORE", "10"))

# Per-category subreddits
CATEGORY_SUBREDDITS = {
    "AI Marketing":    ["marketing", "Entrepreneur", "SaaS", "copywriting", "digital_marketing"],
    "AI Coding":       ["programming", "MachineLearning", "LocalLLaMA", "OpenAI", "learnpython", "webdev"],
    "General AI":      ["artificial", "MachineLearning", "ChatGPT", "OpenAI", "singularity"],
    "AI Design":       ["userexperience", "web_design", "graphic_design", "UI_Design", "Frontend"],
    "OpenClaw":        ["SaaS", "startups", "nocode", "Entrepreneur"],
    "GitHub Projects": ["github", "programming", "opensource", "coolgithubprojects"],
}

def _fetch_subreddit(sub: str, limit: int = 20) -> list[dict]:
    results = []
    for sort in ("hot", "top"):
        params = {"limit": limit, "t": "day"} if sort == "top" else {"limit": limit}
        try:
            r = requests.get(
                f"https://www.reddit.com/r/{sub}/{sort}.json",
                headers=HEADERS, params=params, timeout=10
            )
            if r.status_code != 200:
                continue
            posts = r.json().get("data", {}).get("children", [])
            for p in posts:
                d = p.get("data", {})
                score = d.get("score", 0)
                if score < MIN_SCORE:
                    continue
                title = d.get("title", "")
                selftext = d.get("selftext", "")
                snippet = selftext[:500] if selftext else title
                url   = d.get("url") or f"https://www.reddit.com{d.get('permalink', '')}"
                results.append({
                    "title":      title,
                    "url":        url,
                    "snippet":    snippet,
                    "score":      score,
                    "engagement": score,
                    "source":     f"Reddit r/{sub}",
                    "source_url": f"https://www.reddit.com{d.get('permalink', '')}",
                })
        except Exception as e:
            print(f"[reddit_fetcher] r/{sub} {sort}: {e}")
        finally:
            time.sleep(SLEEP)
    return results

def fetch_reddit_by_category() -> dict[str, list[dict]]:
    by_cat: dict[str, list[dict]] = {cat: [] for cat in CATEGORY_SUBREDDITS}
    seen_urls: set[str] = set()

    for cat, subs in CATEGORY_SUBREDDITS.items():
        for sub in subs[:3]:  # Max 3 subreddits per category per run
            posts = _fetch_subreddit(sub, limit=15)
            for post in posts:
                url = post["url"].split("?")[0]
                if url not in seen_urls:
                    seen_urls.add(url)
                    by_cat[cat].append(post)

    return by_cat
