"""
Habr & VC.ru Fetcher — scrapes top articles from Russian-language tech news sites.
Uses simple HTTP + BeautifulSoup (no JS needed).
"""
import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; DigestBot/1.0)"}

# Per-category keywords for Russian article classification
CATEGORY_KEYWORDS_RU = {
    "AI Marketing": ["маркетинг", "продвижение", "реклама", "контент", "seo", "смм", "аудитория", "pr", "growth"],
    "AI Coding":    ["разработка", "программирование", "код", "python", "javascript", "github", "api", "llm", "ml", "нейро"],
    "General AI":   ["искусственный интеллект", "нейросеть", "gpt", "openai", "anthropic", "gemini", "llama", "модель", "ии", "ai"],
    "AI Design":    ["дизайн", "figma", "ui", "ux", "прототип", "фронтенд", "анимация"],
    "OpenClaw":     ["openclaw", "автоматизация", "workflow", "саас"],
    "GitHub Projects": ["github", "open source", "опенсорс", "репозиторий"],
}

def _classify_ru(title: str) -> str:
    combined = title.lower()
    for cat, kws in CATEGORY_KEYWORDS_RU.items():
        if any(kw in combined for kw in kws):
            return cat
    return None

def _scrape_habr() -> list[dict]:
    """Scrape Habr top articles from relevant hubs."""
    results = []
    hubs = ["machine_learning", "artificial_intelligence", "programming", "startup", "marketing"]
    for hub in hubs[:3]:  # limit to 3 hubs per run
        try:
            url = f"https://habr.com/ru/hubs/{hub}/articles/"
            r = requests.get(url, headers=HEADERS, timeout=10)
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            articles = soup.select("article.tm-articles-list__item")[:5]
            for a in articles:
                title_el = a.select_one("h2 a, h3 a")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                href = title_el.get("href", "")
                if not href.startswith("http"):
                    href = "https://habr.com" + href
                # Score by bookmarks or views if available
                score_el = a.select_one(".tm-votes-meter__value")
                score = int(score_el.get_text(strip=True).replace("−", "-").replace("+", "") or 0) if score_el else 0
                # Try to find snippet/lead text
                snippet_el = a.select_one(".tm-article-snippet__lead")
                snippet = snippet_el.get_text(strip=True) if snippet_el else title

                results.append({
                    "title": title,
                    "url": href,
                    "snippet": snippet,
                    "score": score,
                    "engagement": score,
                    "source": "Habr",
                    "source_url": href,
                })
        except Exception as e:
            print(f"[ru_fetcher] Habr hub {hub}: {e}")
    return results

def _scrape_vcru() -> list[dict]:
    """Scrape VC.ru top articles."""
    results = []
    try:
        url = "https://vc.ru/"
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return results
        soup = BeautifulSoup(r.text, "html.parser")
        # VC.ru renders titles in anchor tags with class patterns
        links = soup.select("a.content-title, a.article__title, h2 a")[:15]
        seen = set()
        for el in links:
            title = el.get_text(strip=True)
            href = el.get("href", "")
            if not href.startswith("http"):
                href = "https://vc.ru" + href
            key = href.split("?")[0]
            if not title or key in seen:
                continue
            seen.add(key)
            results.append({
                "title": title,
                "url": href,
                "snippet": title, # VC.ru lists often lack easy snippets without jumping into blocks
                "score": 0,
                "engagement": 0,
                "source": "VC.ru",
                "source_url": href,
            })
    except Exception as e:
        print(f"[ru_fetcher] VC.ru: {e}")
    return results

def fetch_ru_by_category() -> dict[str, list[dict]]:
    """Returns per-category articles from Habr and VC.ru."""
    by_cat: dict[str, list[dict]] = {cat: [] for cat in CATEGORY_KEYWORDS_RU}
    
    all_articles = _scrape_habr() + _scrape_vcru()
    
    for article in all_articles:
        cat = _classify_ru(article["title"])
        if cat:
            by_cat[cat].append(article)
    
    return by_cat
