import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
import json
import traceback

# Optional imports handled gracefully
try:
    from scrapling import Fetcher
except ImportError:
    Fetcher = None

from config import config

# Detect ROOT and add to sys.path to re-use discover.py / reddit_discover.py if needed
def _detect_root() -> Path:
    env_root = os.getenv('AI_DIGEST_ROOT')
    if env_root:
        return Path(env_root).expanduser()
    server_root = Path('/home/geo/.openclaw/workspace')
    if server_root.exists():
        return server_root
    return Path(__file__).resolve().parent.parent.parent

ROOT = _detect_root()
sys.path.insert(0, str(ROOT / 'scripts'))

try:
    import reddit_discover
except ImportError:
    reddit_discover = None

# ----------------- Hacker News -----------------
def scrape_hn_frontpage() -> list[dict]:
    """Scrape Hacker News frontpage for Ask HN, Show HN, and top discussions."""
    if not Fetcher:
        print("[radar] Scrapling not installed, skipping HN")
        return []
    
    print("[radar][collect] Scrape HN...")
    items = []
    try:
        fetcher = Fetcher(headless=True)
        # We can also use HN Firebase API for simpler JSON access. Let's do that for reliability
        # Actually, HN API is standard and doesn't even need Scrapling.
        import requests
        
        # Get top 30 stories
        top_url = "https://hacker-news.firebaseio.com/v0/topstories.json"
        ask_url = "https://hacker-news.firebaseio.com/v0/askstories.json"
        
        story_ids = requests.get(ask_url, timeout=10).json()[:20] + requests.get(top_url, timeout=10).json()[:15]
        
        for sid in story_ids:
            item = requests.get(f"https://hacker-news.firebaseio.com/v0/item/{sid}.json", timeout=5).json()
            if not item:
                continue
                
            title = item.get('title', '')
            text = item.get('text', '')
            score = item.get('score', 0)
            
            # For radar, we care about comments/pain points, not just the post
            comments = ""
            if item.get('kids'):
                for cid in item['kids'][:3]:  # Top 3 comments
                    c_item = requests.get(f"https://hacker-news.firebaseio.com/v0/item/{cid}.json", timeout=5).json()
                    if c_item and c_item.get('text'):
                        comments += f"\n- {c_item.get('text')}"
            
            if score > 20 or 'Ask HN' in title or 'Show HN' in title:
                items.append({
                    "id": f"hn_{sid}",
                    "source": "hn",
                    "url": f"https://news.ycombinator.com/item?id={sid}",
                    "timestamp": item.get('time', int(time.time())),
                    "raw_text": f"Title: {title}\nBody: {text}\nComments: {comments}"
                })
        
    except Exception as e:
        print(f"[radar][collect] Error scraping HN: {e}")
        
    print(f"[radar][collect] HN found {len(items)} items")
    return items

# ----------------- Reddit -----------------
def scrape_reddit() -> list[dict]:
    """Reuse reddit_discover.py logic with specific subreddits."""
    if not reddit_discover:
        print("[radar] reddit_discover module not found")
        return []

    print("[radar][collect] Scrape Reddit...")
    subreddits = ['Entrepreneur', 'SaaS', 'SideProject', 'Startups', 'indiehackers']
    items = []
    
    for sub in subreddits:
        try:
            posts = reddit_discover._fetch_subreddit(sub, 'hot', 20)
            for post in posts:
                # Need text and comments
                body = post.get('selftext', '')
                title = post.get('title', '')
                
                # We specifically want pain points. Fetching comments is crucial for Reddit
                comments_text = ""
                try:
                    comments = reddit_discover.fetch_top_comments(post['id'], sub, limit=5)
                    for c in comments:
                        comments_text += f"\n[Comment ⬆️{c.get('score',0)}]: {c.get('text','')}"
                except Exception:
                    pass
                
                items.append({
                    "id": f"reddit_{post['id']}",
                    "source": "reddit",
                    "url": f"https://reddit.com{post.get('permalink', '')}",
                    "timestamp": post.get('created_utc', int(time.time())),
                    "raw_text": f"Title: {title}\nBody: {body}\n{comments_text}"
                })
            time.sleep(1.5)
        except Exception as e:
            print(f"[radar][collect] Error on r/{sub}: {e}")
            
    print(f"[radar][collect] Reddit found {len(items)} items")
    return items

# ----------------- X / Twitter -----------------
def scrape_x() -> list[dict]:
    """Use the twitterapi.io to search for specific pain point keywords."""
    print("[radar][collect] Scrape X...")
    items = []
    
    # We want to find pain points. "is there a tool that", "I would pay for", "tired of doing X manually"
    queries = [
        '("tired of" OR "exhausted by" OR "hate doing") (manually OR spreadsheet OR copy paste) lang:en min_faves:5',
        '("I would pay" OR "shut up and take my money" OR "is there a saas") lang:en min_faves:5',
        '("why is it so hard to" OR "struggling to find a tool for" OR "looking for an alternative to") lang:en min_faves:5'
    ]
    
    try:
        import discover # From root scripts
        for q in queries:
            try:
                raw_tweets = discover._paginated_search("Radar", q, "Top", max_pages=1)
                for tw in raw_tweets:
                    items.append({
                        "id": f"x_{tw.get('id')}",
                        "source": "x",
                        "url": tw.get('url', ''),
                        "timestamp": int(datetime.strptime(tw.get('createdAt', ''), "%a %b %d %H:%M:%S %z %Y").timestamp()) if tw.get('createdAt') else int(time.time()),
                        "raw_text": tw.get('text', '')
                    })
            except Exception as e:
                print(f"[radar][collect] Error searching X for {q}: {e}")
            time.sleep(2)
    except Exception as e:
        print(f"[radar][collect] Error setting up X search: {e}")
        
    print(f"[radar][collect] X found {len(items)} items")
    return items

# ----------------- Product Hunt -----------------
def scrape_producthunt() -> list[dict]:
    """Use Scrapling to get recent PH comments."""
    if not Fetcher:
        return []
    
    print("[radar][collect] Scrape Product Hunt...")
    items = []
    try:
        fetcher = Fetcher(headless=True)
        # Fetching PH discussions or recent top products to read comments
        # This requires dynamic rendering sometimes, so Scrapling is perfect
        page = fetcher.get("https://www.producthunt.com/discussions")
        # Extract discussions
        # Note: Scrapling has adaptive parsing, but for brevity we'll do basic extraction 
        # or just rely on HN/Reddit/X for now if PH block us.
        # As an MVP, we can skip PH or implement a simple GraphQL call if needed.
        # Let's add a placeholder for now since PH GraphQL API needs auth usually.
        pass
    except Exception as e:
        print(f"[radar][collect] Error on PH: {e}")
        
    return items

def run_collection() -> list[dict]:
    """Run all enabled collectors."""
    sources = [s.strip().lower() for s in config.SOURCES.split(',')]
    all_items = []
    
    if 'hn' in sources:
        all_items.extend(scrape_hn_frontpage())
    if 'reddit' in sources:
        all_items.extend(scrape_reddit())
    if 'x' in sources:
        all_items.extend(scrape_x())
    # if 'producthunt' in sources:
    #    all_items.extend(scrape_producthunt())
        
    return all_items

if __name__ == "__main__":
    res = run_collection()
    print(f"Total collected: {len(res)}")
