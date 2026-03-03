"""
IndieHackers Fetcher — scrapes milestones, failures and top posts from IndieHackers.
"""
import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; DigestBot/1.0)"}
BASE_URL = "https://www.indiehackers.com"

CATEGORY_KEYWORDS = {
    "AI Marketing": ["marketing", "growth", "seo", "content", "ads", "email", "audience"],
    "AI Coding":    ["code", "coding", "developer", "api", "saas", "tool", "open source"],
    "General AI":   ["ai", "gpt", "llm", "machine learning", "automation", "agent"],
    "AI Design":    ["design", "ui", "ux", "figma", "prototype"],
    "OpenClaw":     ["openclaw", "workflow", "automation tool"],
    "GitHub Projects": ["github", "open source", "repo"],
}

def _classify(title: str, body: str = "") -> str:
    combined = (title + " " + body).lower()
    for cat, kws in CATEGORY_KEYWORDS.items():
        if any(kw in combined for kw in kws):
            return cat
    return None

def _scrape_posts(path: str, label: str) -> list[dict]:
    results = []
    try:
        r = requests.get(f"{BASE_URL}{path}", headers=HEADERS, timeout=12)
        if r.status_code != 200:
            return results
        soup = BeautifulSoup(r.text, "html.parser")
        post_els = soup.select("a.feed-item__title-link, a.post__title-link, h2 a")[:15]
        seen = set()
        for el in post_els:
            title = el.get_text(strip=True)
            href  = el.get("href", "")
            if not href.startswith("http"):
                href = BASE_URL + href
            if not title or href in seen:
                continue
            seen.add(href)
            results.append({
                "title":      title,
                "url":        href,
                "snippet":    title,  # IH post lists don't have snippets by default, use title for now
                "score":      0,
                "engagement": 0,
                "source":     f"IndieHackers ({label})",
                "source_url": href,
            })
    except Exception as e:
        print(f"[ih_fetcher] {label}: {e}")
    return results

def fetch_ih_by_category() -> dict[str, list[dict]]:
    by_cat: dict[str, list[dict]] = {cat: [] for cat in CATEGORY_KEYWORDS}
    
    all_posts = (
        _scrape_posts("/posts", "posts")
        + _scrape_posts("/milestones", "milestones")
    )
    
    for post in all_posts:
        cat = _classify(post["title"])
        if cat:
            by_cat[cat].append(post)
    
    return by_cat
