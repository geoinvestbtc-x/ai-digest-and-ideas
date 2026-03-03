"""
Product Hunt Fetcher — scrapes top products of the day and their categories.
Uses the public Product Hunt homepage (no API key required).
"""
import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; DigestBot/1.0)"}
BASE_URL = "https://www.producthunt.com"

# Map PH tags → our digest categories
PH_TAG_MAP = {
    "AI Marketing":    ["marketing", "growth", "seo", "analytics", "content", "social media", "email"],
    "AI Coding":       ["developer tools", "productivity", "api", "open source", "devops", "coding"],
    "General AI":      ["artificial intelligence", "machine learning", "chatbot", "llm", "ai"],
    "AI Design":       ["design", "ui", "ux", "figma", "prototype", "creative"],
    "OpenClaw":        ["automation", "workflow", "saas"],
    "GitHub Projects": ["open source", "developer tools", "github"],
}

def _classify_ph(tags: list[str], name: str, tagline: str) -> str:
    combined = " ".join(tags + [name, tagline]).lower()
    for cat, kws in PH_TAG_MAP.items():
        if any(kw in combined for kw in kws):
            return cat
    return None

def fetch_ph_by_category() -> dict[str, list[dict]]:
    """Scrape Product Hunt today's top products and classify by category."""
    by_cat: dict[str, list[dict]] = {cat: [] for cat in PH_TAG_MAP}

    try:
        r = requests.get(BASE_URL, headers=HEADERS, timeout=12)
        if r.status_code != 200:
            print(f"[ph_fetcher] HTTP {r.status_code}")
            return by_cat

        soup = BeautifulSoup(r.text, "html.parser")
        # PH renders products in list items — try multiple selectors as PH changes markup
        items = soup.select("div[data-test='homepage-section-0'] li, section li")
        if not items:
            # fallback: grab all named anchor links with upvote patterns
            items = soup.select("li")

        seen = set()
        for li in items[:40]:
            name_el   = li.select_one("h3, h2, strong")
            url_el    = li.select_one("a[href*='/posts/']")
            votes_el  = li.find(lambda t: t.name in ("button", "span") and any(c in t.get("class", []) for c in ("vote", "upvote", "count")))
            
            if not name_el or not url_el:
                continue
            
            name = name_el.get_text(strip=True)
            href = url_el.get("href", "")
            if not href.startswith("http"):
                href = BASE_URL + href
            
            if href in seen or not name:
                continue
            seen.add(href)

            # Extract tagline (usually the next sibling after name)
            tagline_el = li.select_one("p")
            tagline = tagline_el.get_text(strip=True) if tagline_el else ""

            # Extract tags (usually in small spans)
            tag_els = li.select("a[href*='/topics/']")
            tags = [t.get_text(strip=True).lower() for t in tag_els]

            votes = 0
            if votes_el:
                try:
                    votes = int(votes_el.get_text(strip=True).replace(",", ""))
                except Exception:
                    votes = 0

            cat = _classify_ph(tags, name, tagline)
            if cat:
                by_cat[cat].append({
                    "title":      f"{name} — {tagline}" if tagline else name,
                    "url":        href,
                    "snippet":    tagline or name,
                    "score":      votes,
                    "engagement": votes,
                    "source":     "ProductHunt",
                    "source_url": href,
                })

    except Exception as e:
        print(f"[ph_fetcher] Error: {e}")

    return by_cat
