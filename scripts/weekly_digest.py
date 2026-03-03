#!/usr/bin/env python3
"""
Weekly Digest — deep analysis of 🔥 Interesting tweets from the past week.

Run on Saturday (cron) or manually:
    python3 scripts/weekly_digest.py

Flow:
1. Load all unsent bookmarks from data/bookmarks.jsonl (last 7 days)
2. Fetch full tweet + replies for each via TwitterAPI.io
3. Extract linked articles
4. Group by category → LLM deep analysis per category
5. Send formatted weekly digest to Telegram
6. Mark bookmarks as processed
"""
import json
import os
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

# ── Root detection ────────────────────────────────────────────

def _detect_root() -> Path:
    env_root = os.getenv('AI_DIGEST_ROOT')
    if env_root:
        return Path(env_root).expanduser()
    server_root = Path('/home/geo/.openclaw/workspace')
    if server_root.exists():
        return server_root
    return Path(__file__).resolve().parent.parent


ROOT = _detect_root()


def _load_env():
    p = ROOT / '.env'
    if not p.exists():
        return
    for line in p.read_text(encoding='utf-8').splitlines():
        if '=' in line and not line.strip().startswith('#'):
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip())


_load_env()

sys.path.insert(0, str(ROOT / 'scripts'))
from bookmarks_store import get_all, mark_deep_read_sent

# ── Config ────────────────────────────────────────────────────

TG_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN') or os.getenv('TELEGRAM_BOT_TOKEN')
TWITTERAPI_KEY = os.getenv('TWITTERAPI_IO_KEY')
OPENROUTER_KEY = os.getenv('OPENROUTER_API_KEY')
WEEKLY_MODEL = os.getenv('WEEKLY_LLM_MODEL', 'openai/gpt-4o')
TG_TARGET = os.getenv('TELEGRAM_CHAT_ID')
WEEKLY_LANG = os.getenv('WEEKLY_DIGEST_LANG', 'ru')  # 'ru' or 'en'
TG_API = f'https://api.telegram.org/bot{TG_TOKEN}'
TWITTER_API = 'https://api.twitterapi.io'

CAT_EMOJI = {
    'AI Marketing':   '📣',
    'AI Coding':      '⚡',
    'AI Design':      '🎨',
    'General AI':     '🧠',
    'AI Business':    '💰',
    'OpenClaw':       '🦞',
    'GitHubProjects': '🐙',
}

CAT_ORDER = ['AI Marketing', 'AI Coding', 'AI Design', 'General AI', 'AI Business', 'OpenClaw', 'GitHubProjects']


# ── Twitter API ───────────────────────────────────────────────

def _tw_headers():
    return {'X-API-Key': TWITTERAPI_KEY, 'Accept': 'application/json'}


def fetch_tweet(tweet_id: str) -> dict:
    r = requests.get(
        f'{TWITTER_API}/twitter/tweets',
        headers=_tw_headers(),
        params={'tweet_ids': tweet_id},
        timeout=30,
    )
    r.raise_for_status()
    tweets = r.json().get('tweets', [])
    return tweets[0] if tweets else {}


def fetch_replies(tweet_id: str, max_replies: int = 10) -> list:
    try:
        r = requests.get(
            f'{TWITTER_API}/twitter/tweet/replies/v2',
            headers=_tw_headers(),
            params={'tweet_id': tweet_id, 'sortBy': 'Likes'},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        replies = data.get('replies', data.get('tweets', []))
        return replies[:max_replies]
    except Exception as e:
        print(f"[weekly] fetch_replies error for {tweet_id}: {e}")
        return []


# ── Article extraction ────────────────────────────────────────

def _extract_urls_from_tweet(tweet: dict) -> list:
    urls = []
    entities = tweet.get('entities') or {}
    for u in entities.get('urls', []):
        expanded = u.get('expanded_url') or u.get('url', '')
        if expanded and 'x.com' not in expanded and 'twitter.com' not in expanded and 't.co' not in expanded:
            urls.append(expanded)
    text = tweet.get('text', '')
    for m in re.findall(r'https?://(?!t\.co|x\.com|twitter\.com)\S+', text):
        if m not in urls:
            urls.append(m)
    return urls


def extract_article(url: str, max_chars: int = 2000) -> str:
    try:
        import trafilatura
        r = requests.get(url, timeout=15, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; TrendDigestBot/1.0)'
        })
        if r.status_code != 200:
            return ''
        return (trafilatura.extract(r.text) or '')[:max_chars]
    except ImportError:
        return ''
    except Exception as e:
        print(f"[weekly] article extraction error for {url}: {e}")
        return ''


# ── Prepare tweet context ─────────────────────────────────────

def enrich_bookmark(bookmark: dict) -> dict:
    """Fetch full tweet + replies + article for a bookmark."""
    tweet_id = bookmark['tweet_id']
    print(f"[weekly] Enriching tweet {tweet_id}...")

    tweet = fetch_tweet(tweet_id)
    if not tweet:
        print(f"[weekly] ⚠ Could not fetch tweet {tweet_id}")
        return {**bookmark, 'tweet': {}, 'replies': [], 'article': ''}

    time.sleep(1)
    replies = fetch_replies(tweet_id)
    time.sleep(0.5)

    article = ''
    ext_urls = _extract_urls_from_tweet(tweet)
    if ext_urls:
        article = extract_article(ext_urls[0])
        if article:
            print(f"[weekly] Article: {len(article)} chars from {ext_urls[0]}")

    return {**bookmark, 'tweet': tweet, 'replies': replies, 'article': article}


# ── LLM Weekly Analysis ──────────────────────────────────────

_WEEKLY_SYSTEM_PROMPT_RU = """\
Ты — аналитик трендов в AI. Тебе дают подборку интересных твитов за неделю по одной категории.

Напиши УВЛЕКАТЕЛЬНЫЙ и ПОЛЕЗНЫЙ обзор на русском. Пиши как будто рассказываешь другу-разработчику за кофе — живо, с инсайтами, без воды.

Формат:

🔥 ГЛАВНОЕ ЗА НЕДЕЛЮ
2-3 самых важных вещи, которые произошли. Что реально стоит знать.

🛠 НОВЫЕ ИНСТРУМЕНТЫ
Какие новые тулы / релизы / обновления были. Для каждого:
- Название + что делает (1 строка)
- Чем полезно на практике

💡 ИНТЕРЕСНЫЕ ПОДХОДЫ
Какие workflow, техники, идеи люди пробуют и делятся. Конкретные примеры.

📊 МНЕНИЕ СООБЩЕСТВА
Что обсуждают в комментариях, какие споры, какие консенсусы.

🎯 ВЫВОД
1-2 предложения: что взять на заметку практику.

ПРАВИЛА:
- Пиши конкретно, без общих фраз типа "AI развивается"
- Упоминай авторов (@username) когда цитируешь
- Если инструмент — пиши что он делает, а не просто имя
- Каждая секция — 3-5 строк максимум
- Если данных мало — лучше короткий честный обзор чем раздутый
- Общий объём: 800-1500 символов
"""

_WEEKLY_SYSTEM_PROMPT_EN = """\
You are a trend analyst for AI. You receive a curated collection of interesting tweets from the past week in one category.

Write an ENGAGING and USEFUL review in English. Write as if you're telling a developer friend over coffee — lively, with insights, no fluff.

Format:

🔥 TOP OF THE WEEK
2-3 most important things that happened. What truly matters.

🛠 NEW TOOLS
Which new tools / releases / updates appeared. For each:
- Name + what it does (1 line)
- Why it's useful in practice

💡 INTERESTING APPROACHES
What workflows, techniques, ideas people are trying and sharing. Concrete examples.

📊 COMMUNITY OPINION
What's being discussed in comments, what debates, what consensus emerged.

🎯 TAKEAWAY
1-2 sentences: what to keep in mind as a practitioner.

RULES:
- Be specific, no generic phrases like "AI is evolving"
- Mention authors (@username) when quoting
- If a tool — say what it does, not just its name
- Each section max 3-5 lines
- If data is scarce — a short honest review beats a padded one
- Total length: 800-1500 characters
"""

WEEKLY_SYSTEM_PROMPT = _WEEKLY_SYSTEM_PROMPT_RU if WEEKLY_LANG == 'ru' else _WEEKLY_SYSTEM_PROMPT_EN

_WEEKLY_HEADERS_RU = ['🔥 ГЛАВНОЕ ЗА НЕДЕЛЮ', '🛠 НОВЫЕ ИНСТРУМЕНТЫ',
                      '💡 ИНТЕРЕСНЫЕ ПОДХОДЫ', '📊 МНЕНИЕ СООБЩЕСТВА', '🎯 ВЫВОД']
_WEEKLY_HEADERS_EN = ['🔥 TOP OF THE WEEK', '🛠 NEW TOOLS',
                      '💡 INTERESTING APPROACHES', '📊 COMMUNITY OPINION', '🎯 TAKEAWAY']
WEEKLY_HEADERS = _WEEKLY_HEADERS_RU if WEEKLY_LANG == 'ru' else _WEEKLY_HEADERS_EN


def _html_esc(text: str) -> str:
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _build_llm_context(enriched_tweets: list) -> str:
    """Build context string for LLM from enriched tweets."""
    parts = []
    for i, et in enumerate(enriched_tweets, 1):
        tweet = et.get('tweet', {})
        author = tweet.get('author', {})
        text = tweet.get('text', et.get('title', ''))

        parts.append(f"--- Tweet {i} ---")
        parts.append(f"Author: @{author.get('userName', '?')} ({author.get('followers', 0):,} followers)")
        parts.append(f"Text: {text}")
        parts.append(f"Metrics: {tweet.get('likeCount', 0)}❤️ {tweet.get('bookmarkCount', 0)}🔖 "
                     f"{tweet.get('retweetCount', 0)}🔄 {tweet.get('viewCount', 0)} views")

        if et.get('replies'):
            parts.append(f"Top comments:")
            for r in et['replies'][:5]:
                r_author = (r.get('author') or {}).get('userName', '?')
                r_text = (r.get('text', '') or '')[:150]
                parts.append(f"  @{r_author}: {r_text}")

        if et.get('article'):
            parts.append(f"Linked article excerpt: {et['article'][:500]}")

        parts.append("")

    return '\n'.join(parts)


def llm_weekly_analysis(category: str, enriched_tweets: list) -> str:
    """Run LLM analysis for one category."""
    context = _build_llm_context(enriched_tweets)

    user_msg = (
        f"Категория: {category}\n"
        f"Количество твитов: {len(enriched_tweets)}\n"
        f"Период: последние 7 дней\n\n"
        f"{context}"
    )

    headers = {
        'Authorization': f'Bearer {OPENROUTER_KEY}',
        'Content-Type': 'application/json',
        'HTTP-Referer': 'https://local.openclaw',
        'X-Title': 'ai-digest-weekly-digest',
    }
    payload = {
        'model': WEEKLY_MODEL,
        'messages': [
            {'role': 'system', 'content': WEEKLY_SYSTEM_PROMPT},
            {'role': 'user', 'content': user_msg},
        ],
        'max_tokens': 2000,
        'temperature': 0.4,
    }

    print(f"[weekly] LLM call: cat={category} tweets={len(enriched_tweets)} model={WEEKLY_MODEL}")
    r = requests.post(
        'https://openrouter.ai/api/v1/chat/completions',
        headers=headers,
        json=payload,
        timeout=120,
    )
    r.raise_for_status()
    data = r.json()

    content = data.get('choices', [{}])[0].get('message', {}).get('content', '')
    usage = data.get('usage', {})
    print(f"[weekly] LLM done: cat={category} tokens={usage.get('total_tokens', 0)} "
          f"len={len(content)}")

    return content.strip()


# ── Telegram sending ──────────────────────────────────────────

def tg_send(text: str, target: str = None) -> bool:
    target = target or TG_TARGET
    if not target:
        print("[weekly] No TELEGRAM_CHAT_ID set!")
        return False

    payload = {
        'chat_id': target,
        'text': text,
        'parse_mode': 'HTML',
        'disable_web_page_preview': True,
    }
    r = requests.post(f'{TG_API}/sendMessage', json=payload, timeout=20)
    ok = r.status_code == 200
    if not ok:
        print(f"[weekly] Telegram error: {r.status_code} {r.text[:300]}")
    return ok


def format_category_digest(category: str, analysis: str, tweet_count: int) -> str:
    """Format one category's weekly digest for Telegram."""
    emoji = CAT_EMOJI.get(category, '🔹')

    # Make section headers bold
    formatted = analysis
    for header in WEEKLY_HEADERS:
        formatted = formatted.replace(header, f'<b>{header}</b>')

    # Escape HTML but preserve our <b> tags
    # First escape, then restore <b>
    escaped = _html_esc(formatted)
    escaped = escaped.replace('&lt;b&gt;', '<b>').replace('&lt;/b&gt;', '</b>')

    subtitle = 'Weekly review' if WEEKLY_LANG == 'en' else 'Обзор за неделю'
    lines = [
        f'{emoji} <b>WEEKLY: {_html_esc(category)}</b>',
        f'📅 {subtitle} · {tweet_count} saved tweets',
        f'',
        f'━━━━━━━━━━━━━━━━━━━━',
        f'',
        escaped,
        f'',
        f'━━━━━━━━━━━━━━━━━━━━',
    ]
    return '\n'.join(lines)


# ── Main ──────────────────────────────────────────────────────

def main():
    if not TG_TOKEN:
        print("[weekly] ERROR: TELEGRAM_BOT_TOKEN not set"); sys.exit(1)
    if not TWITTERAPI_KEY:
        print("[weekly] ERROR: TWITTERAPI_IO_KEY not set"); sys.exit(1)
    if not OPENROUTER_KEY:
        print("[weekly] ERROR: OPENROUTER_API_KEY not set"); sys.exit(1)

    print(f"\n{'='*60}")
    print(f"[WEEKLY DIGEST]")
    print(f"{'='*60}")
    print(f"  ROOT:    {ROOT}")
    print(f"  Model:   {WEEKLY_MODEL}")
    print(f"  Target:  {TG_TARGET}")

    # 1. Load bookmarks from last 7 days that haven't been deep-read
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    all_bookmarks = get_all()
    pending = []
    for bk in all_bookmarks:
        if bk.get('deep_read_sent'):
            continue
        try:
            saved_at = datetime.fromisoformat(bk['saved_at'])
            if saved_at >= cutoff:
                pending.append(bk)
        except Exception:
            pending.append(bk)  # include if can't parse date

    print(f"  Total bookmarks: {len(all_bookmarks)}")
    print(f"  Pending (last 7d, not processed): {len(pending)}")

    if not pending:
        print("[weekly] No new bookmarks to process. Done.")
        return

    # 2. Enrich each bookmark (fetch tweet + replies + article)
    print(f"\n[weekly] Enriching {len(pending)} tweets...")
    enriched = []
    for bk in pending:
        try:
            enriched.append(enrich_bookmark(bk))
        except Exception as e:
            print(f"[weekly] ❌ Error enriching {bk.get('tweet_id')}: {e}")
            enriched.append({**bk, 'tweet': {}, 'replies': [], 'article': ''})
        time.sleep(1.5)

    # 3. Group by category
    by_category = {}
    uncategorized = []
    for et in enriched:
        cat = et.get('category', '').strip()
        if not cat:
            # Try to get from tweet data
            cat = et.get('tweet', {}).get('category', '')
        if cat:
            by_category.setdefault(cat, []).append(et)
        else:
            uncategorized.append(et)

    # Put uncategorized into General AI
    if uncategorized:
        by_category.setdefault('General AI', []).extend(uncategorized)

    print(f"\n[weekly] Categories:")
    for cat, tweets in by_category.items():
        print(f"  {cat}: {len(tweets)} tweets")

    # 4. LLM analysis per category + send to Telegram
    # Send header
    header = (
        f'📋 <b>WEEKLY DIGEST</b>\n'
        f'📅 {datetime.now().strftime("%d %B %Y")}\n'
        f'🔥 {len(pending)} interesting tweets this week'
    )
    tg_send(header)

    sent = 0
    for cat in CAT_ORDER:
        tweets = by_category.get(cat)
        if not tweets:
            continue

        print(f"\n[weekly] Analyzing {cat} ({len(tweets)} tweets)...")
        try:
            analysis = llm_weekly_analysis(cat, tweets)
            message = format_category_digest(cat, analysis, len(tweets))

            # Telegram message limit is 4096 chars
            if len(message) > 4000:
                message = message[:3990] + '\n…'

            if tg_send(message):
                sent += 1
                print(f"[weekly] ✅ Sent {cat}")
            else:
                print(f"[weekly] ❌ Failed to send {cat}")

            time.sleep(2)  # rate limit between categories
        except Exception as e:
            print(f"[weekly] ❌ Error analyzing {cat}: {e}")

    # Also handle categories not in ORDER
    for cat, tweets in by_category.items():
        if cat in CAT_ORDER:
            continue
        print(f"\n[weekly] Analyzing {cat} ({len(tweets)} tweets)...")
        try:
            analysis = llm_weekly_analysis(cat, tweets)
            message = format_category_digest(cat, analysis, len(tweets))
            if len(message) > 4000:
                message = message[:3990] + '\n…'
            if tg_send(message):
                sent += 1
            time.sleep(2)
        except Exception as e:
            print(f"[weekly] ❌ Error analyzing {cat}: {e}")

    # 5. Mark all as processed
    for bk in pending:
        mark_deep_read_sent(bk['tweet_id'])

    # 6. Send summary
    summary = (
        f'✅ <b>Weekly digest complete</b>\n'
        f'📊 {len(pending)} tweets analyzed · {sent} categories sent\n'
        f'🤖 Model: {WEEKLY_MODEL}'
    )
    tg_send(summary)

    print(f"\n{'='*60}")
    print(f"[weekly] Done! {sent} category digests sent.")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    main()
