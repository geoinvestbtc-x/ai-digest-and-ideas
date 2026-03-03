"""
HN Fetcher — fetches Hacker News stories and classifies them into digest categories.
Uses the official Firebase HN API (no scraping needed).
"""
import requests
import time

# Per-category HN keywords for classification
CATEGORY_KEYWORDS = {
    "AI Marketing": ["marketing", "growth", "seo", "content", "ads", "campaign", "copywriting", "funnel", "email", "audience"],
    "AI Coding":    ["code", "coding", "developer", "programming", "python", "javascript", "github", "claude", "cursor", "mcp", "llm", "api", "open source", "devtools", "copilot"],
    "General AI":   ["ai", "artificial intelligence", "gpt", "openai", "anthropic", "gemini", "llama", "model", "agent", "inference", "benchmark", "research", "paper", "machine learning"],
    "AI Design":    ["design", "figma", "ui", "ux", "prototype", "css", "frontend", "typography", "animation", "creative", "midjourney"],
    "OpenClaw":     ["openclaw", "open claw", "automation", "workflow", "saas tool"],
    "GitHub Projects": ["github", "open source", "repo", "repository", "project", "library", "framework"],
}

HN_API = "https://hacker-news.firebaseio.com/v0"

def _classify(title: str, text: str = "") -> str:
    """Return the first matching category or None."""
    combined = (title + " " + text).lower()
    for cat, kws in CATEGORY_KEYWORDS.items():
        if any(kw in combined for kw in kws):
            return cat
    return None

def _fetch_item(item_id: int) -> dict:
    try:
        r = requests.get(f"{HN_API}/item/{item_id}.json", timeout=8)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

def fetch_hn_by_category(max_items: int = 100) -> dict[str, list[dict]]:
    """
    Returns a dict mapping category -> list of posts:
      { "AI Coding": [{title, url, score, source, source_url}, ...], ... }
    """
    by_cat: dict[str, list[dict]] = {cat: [] for cat in CATEGORY_KEYWORDS}

    try:
        r = requests.get(f"{HN_API}/topstories.json", timeout=10)
        r.raise_for_status()
        top_ids = r.json()[:max_items]
    except Exception as e:
        print(f"[hn_fetcher] Failed to fetch top stories: {e}")
        return by_cat

    for item_id in top_ids:
        item = _fetch_item(item_id)
        if not item or item.get("type") not in ("story", "ask", "show"):
            continue
        title = item.get("title", "")
        text  = item.get("text", "") or ""
        url   = item.get("url") or f"https://news.ycombinator.com/item?id={item_id}"
        score = item.get("score", 0)

        cat = _classify(title, text)
        if cat:
            snippet = text[:500] if text else title
            by_cat[cat].append({
                "title":      title,
                "url":        url,
                "snippet":    snippet,
                "score":      score,
                "engagement": score,
                "source":     "HN",
                "source_url": f"https://news.ycombinator.com/item?id={item_id}",
            })

    return by_cat
