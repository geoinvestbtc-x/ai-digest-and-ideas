"""
X/Twitter Per-Category Fetcher — wraps existing discover.py to fetch per-category tweets.
Returns the same format as all other source fetchers for unified merging.
"""
import sys
import os
from pathlib import Path

# Import existing discover module
_scripts_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_scripts_dir))

try:
    from discover import _paginated_search, CATEGORY_QUERIES
    _HAS_DISCOVER = True
except ImportError:
    _HAS_DISCOVER = False

def fetch_x_by_category() -> dict[str, list[dict]]:
    """Fetch top tweets per category using the existing CATEGORY_QUERIES."""
    if not _HAS_DISCOVER:
        print("[x_fetcher] discover.py not available, skipping X.")
        return {}

    by_cat: dict[str, list[dict]] = {}

    for cat, queries in CATEGORY_QUERIES.items():
        results = []
        for q_type in ("Top", "Latest"):
            query = queries.get(q_type)
            if not query:
                continue
            try:
                items = _paginated_search(
                    cat, query, q_type, 2  # Positional: category, query, query_type, max_pages
                )
                for item in items:
                    tweet_url = item.get("url") or item.get("tweetUrl", "")
                    text      = item.get("text", "")
                    title     = text[:200]
                    likes     = item.get("likeCount", 0) or 0
                    rt        = item.get("retweetCount", 0) or 0
                    results.append({
                        "title":      title,
                        "url":        tweet_url,
                        "snippet":    text,
                        "score":      likes + rt * 2,
                        "engagement": likes + rt * 2,
                        "source":     "X/Twitter",
                        "source_url": tweet_url,
                    })
            except Exception as e:
                print(f"[x_fetcher] cat={cat} type={q_type}: {e}")
        by_cat[cat] = results

    return by_cat
