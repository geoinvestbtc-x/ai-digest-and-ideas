"""
Category Publisher — formats and sends one Telegram message per digest category.
Each message contains a numbered list of top posts with links and source labels.
"""
import os
import requests
from datetime import datetime, timezone

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHANNEL")

CATEGORY_EMOJIS = {
    "AI Marketing":    "📣",
    "AI Coding":       "⚡",
    "General AI":      "🧠",
    "AI Design":       "🎨",
    "AI Business":     "💰",
    "OpenClaw":        "🦞",
    "GitHub Projects": "🐙",
}

# Source labels and emoji
SOURCE_LABELS = {
    "X/Twitter":   "𝕏",
    "Reddit":      "🔴",
    "HN":          "🟠",
    "ProductHunt": "🐱",
    "IndieHackers": "🟣",
    "Habr":        "📘",
    "VC.ru":       "📗",
}

def _source_label(source: str) -> str:
    for key, emoji in SOURCE_LABELS.items():
        if key.lower() in source.lower():
            return f"{emoji} {source}"
    return source

def format_category_message(category: str, posts: list[dict], max_posts: int = 10) -> str:
    emoji = CATEGORY_EMOJIS.get(category, "📌")
    
    # Check if all posts are from one source to simplify the header
    sources = set()
    for p in posts[:max_posts]:
        s = _source_label(p.get("source", ""))
        sources.add(s)
    
    # Header requested format: 🦞 OpenClaw · 𝕏 — last 48h
    # If mixed sources, we'll list the category and maybe "ALL SOURCES".
    # Since we can't easily detect if it's purely X without hardcoding, 
    # we'll build a unified header.
    source_str = "𝕏" if len(sources) == 1 and list(sources)[0].startswith("𝕏") else "Sources"
    header = f"<b>{emoji} {category} · {source_str} — last 48h</b>\n\n"
    
    lines = [header]

    for i, post in enumerate(posts[:max_posts], 1):
        title  = post.get("title", "Untitled").strip()
        why    = post.get("why", "").strip()
        url    = post.get("url", "")
        # Remove HTML tags from title/why just in case to avoid parsing errors
        title = title.replace('<', '&lt;').replace('>', '&gt;')
        why = why.replace('<', '&lt;').replace('>', '&gt;')

        # 1. title
        lines.append(f"<b>{i}. {title}</b>")
        
        # Why: explanation
        if why:
            lines.append(f"Why: {why}")
            
        # Source : url
        if url:
             lines.append(f"Source : {url}")
             
        lines.append("") # Empty line between items
        
    return "\n".join(lines).strip()

def send_category(category: str, posts: list[dict], min_posts: int = 3, max_posts: int = 10) -> bool:
    """Send a single Telegram message for this category. Returns True on success."""
    if not BOT_TOKEN or not CHAT_ID:
        print("[cat_publisher] No Telegram credentials, skipping.")
        return False

    if len(posts) < min_posts:
        print(f"[cat_publisher] {category}: only {len(posts)} posts (min {min_posts}), skipping.")
        return False

    text = format_category_message(category, posts, max_posts=max_posts)

    try:
        r = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={
                "chat_id":                  CHAT_ID,
                "text":                     text,
                "parse_mode":               "HTML",
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        if r.status_code == 200:
            print(f"[cat_publisher] Sent '{category}' ({len(posts[:max_posts])} posts)")
            return True
        else:
            print(f"[cat_publisher] Error for '{category}': {r.text[:200]}")
            return False
    except Exception as e:
        print(f"[cat_publisher] Exception for '{category}': {e}")
        return False
