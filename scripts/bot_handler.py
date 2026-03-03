#!/usr/bin/env python3
"""
Telegram Bot long-polling handler for 🔥 Interesting button callbacks.

Run as a persistent process on the server:
    python3 scripts/bot_handler.py

Flow:
1. Listen for callback_query with data "interesting:{tweet_id}"
2. Save tweet to bookmarks.jsonl
3. Update inline keyboard: 🪨 → 🔥
4. Answer with "🔥 Saved!"

Weekly digest (weekly_digest.py) will later batch-analyze all saved tweets.
"""
import json
import os
import sys
import time
import traceback
from pathlib import Path

import requests

# ── Radar imports ─────────────────────────────────────────────
try:
    from radar import memory as radar_memory
except ImportError:
    radar_memory = None

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
from bookmarks_store import save as bk_save, exists as bk_exists, remove as bk_remove

# ── Config ────────────────────────────────────────────────────

TG_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN') or os.getenv('TELEGRAM_BOT_TOKEN')
TG_API = f'https://api.telegram.org/bot{TG_TOKEN}'
POLL_TIMEOUT = 30


# ── Telegram helpers ──────────────────────────────────────────

def tg_get_updates(offset=None):
    params = {
        'timeout': POLL_TIMEOUT,
        'allowed_updates': json.dumps(['callback_query']),
    }
    if offset is not None:
        params['offset'] = offset
    r = requests.get(f'{TG_API}/getUpdates', params=params, timeout=POLL_TIMEOUT + 10)
    r.raise_for_status()
    return r.json().get('result', [])


def tg_answer_callback(callback_query_id, text=''):
    requests.post(f'{TG_API}/answerCallbackQuery', json={
        'callback_query_id': callback_query_id,
        'text': text,
        'show_alert': False,
    }, timeout=10)


def tg_edit_reply_markup(chat_id, message_id, reply_markup):
    r = requests.post(f'{TG_API}/editMessageReplyMarkup', json={
        'chat_id': chat_id,
        'message_id': message_id,
        'reply_markup': reply_markup,
    }, timeout=10)
    if r.status_code != 200:
        print(f"[bot] ❌ editMessageReplyMarkup failed: {r.status_code} {r.text}")
    return r.status_code == 200


def _update_keyboard_toggle(existing_markup, activated_tweet_id, activate: bool):
    """Clone keyboard, toggle 🪨↔🔥 for the activated tweet."""
    if not existing_markup:
        return None
    new_rows = []
    for row in existing_markup.get('inline_keyboard', []):
        new_row = []
        for btn in row:
            cb = btn.get('callback_data', '')
            text = btn.get('text', '')
            if cb == f'interesting:{activated_tweet_id}':
                if activate:
                    text = text.replace('🪨', '🔥')
                else:
                    text = text.replace('🔥', '🪨')
            new_row.append({'text': text, 'callback_data': cb})
        new_rows.append(new_row)
    return {'inline_keyboard': new_rows}


# ── Callback handler ─────────────────────────────────────────

import re as _re
_KNOWN_CATS = ['AI Marketing', 'AI Coding', 'AI Design', 'General AI',
               'AI Business', 'OpenClaw', 'GitHubProjects']


def _extract_item_info_from_message(message: dict, item_key: str, platform: str) -> dict:
    """Extract URL and category from the Telegram message text.

    item_key: for Twitter = tweet_id, for Reddit = 'reddit:{post_id}'
    platform: 'twitter' or 'reddit'
    """
    text = message.get('text', '')
    url = ''

    if platform == 'reddit':
        post_id = item_key[len('reddit:'):]
        # Match reddit.com permalink containing the post id
        for m in _re.finditer(
            r'https?://(?:www\.)?reddit\.com/r/\S+/comments/' + _re.escape(post_id) + r'[^\s]*',
            text
        ):
            url = m.group(0)
            break
    else:
        for m in _re.finditer(r'https?://x\.com/\S+/status/' + _re.escape(item_key), text):
            url = m.group(0)
            break

    category = ''
    first_line = text.split('\n')[0] if text else ''
    for cat in _KNOWN_CATS:
        if cat in first_line:
            category = cat
            break
    return {'url': url, 'category': category}


def handle_interesting(callback_query):
    cb_data = callback_query.get('data', '')
    # Formats: "interesting:{tweet_id}" or "interesting:reddit:{post_id}"
    item_key = cb_data.split(':', 1)[1] if ':' in cb_data else ''
    if not item_key:
        return

    # Determine platform from item_key prefix
    platform = 'reddit' if item_key.startswith('reddit:') else 'twitter'

    cq_id = callback_query.get('id')
    message = callback_query.get('message', {})
    chat_id = message.get('chat', {}).get('id')
    message_id = message.get('message_id')

    if bk_exists(item_key):
        # Already saved → UNDO
        bk_remove(item_key)
        existing_markup = message.get('reply_markup')
        if existing_markup and message_id:
            new_markup = _update_keyboard_toggle(existing_markup, item_key, activate=False)
            if new_markup:
                tg_edit_reply_markup(chat_id, message_id, new_markup)
        tg_answer_callback(cq_id, text='🪨 Removed!')
        print(f"[bot] 🪨 Removed {platform} item {item_key}")
        return

    # Extract URL and category from the message
    info = _extract_item_info_from_message(message, item_key, platform)

    # Fallback URL if extraction failed
    if not info.get('url'):
        if platform == 'reddit':
            post_id = item_key[len('reddit:'):]
            fallback_url = f'https://reddit.com/comments/{post_id}'
        else:
            fallback_url = f'https://x.com/i/status/{item_key}'
        info['url'] = fallback_url

    # Save to bookmarks
    bk_save(
        tweet_id=item_key,
        url=info['url'],
        category=info.get('category', ''),
        source=platform,
    )

    # Update keyboard: 🪨 → 🔥
    existing_markup = message.get('reply_markup')
    if existing_markup and message_id:
        new_markup = _update_keyboard_toggle(existing_markup, item_key, activate=True)
        if new_markup:
            tg_edit_reply_markup(chat_id, message_id, new_markup)

    tg_answer_callback(cq_id, text='🔥 Saved!')
    print(f"[bot] 🔥 Saved {platform} item {item_key} (cat={info.get('category', '?')})")


# ── Radar Handlers ───────────────────────────────────────────

def _get_radar_idea(short_title: str) -> dict:
    cache_dir = os.path.join(ROOT, 'data', 'radar_cache')
    path = os.path.join(cache_dir, f"{short_title}.json")
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def handle_radar_callback(callback_query):
    cq_id = callback_query.get('id')
    cb_data = callback_query.get('data', '')
    
    # radar_interest:TITLE, radar_solved:TITLE, radar_mvp:TITLE, radar_val:TITLE, radar_anti:TITLE
    parts = cb_data.split(':', 1)
    if len(parts) != 2:
        return
        
    action, short_title = parts[0], parts[1]
    
    # Status updates via Memory module
    if action == 'radar_interest':
        if radar_memory:
            radar_memory.mark_status(short_title.replace('_', ' '), 'interested')
        tg_answer_callback(cq_id, text='✨ Буду искать похожие!')
        print(f"[bot][radar] Marked {short_title} as interested")
        return
        
    if action == 'radar_solved':
        if radar_memory:
            radar_memory.mark_status(short_title.replace('_', ' '), 'solved')
        tg_answer_callback(cq_id, text='✅ Отметил как решено')
        print(f"[bot][radar] Marked {short_title} as solved")
        return
        
    # Detail lookups
    idea = _get_radar_idea(short_title)
    if not idea:
        tg_answer_callback(cq_id, text='❌ Данные не найдены в кэше')
        return
        
    # For MVP, Validation, Anti-thesis we send a new message
    chat_id = callback_query.get('message', {}).get('chat', {}).get('id')
    text = ""
    
    if action == 'radar_mvp':
        text = f"🛠 <b>MVP ({idea.get('idea_title', '')})</b>\n\n{idea.get('mvp_7_days', 'Нет данных')}"
    elif action == 'radar_val':
        text = f"🧪 <b>Validation ({idea.get('idea_title', '')})</b>\n\n<b>Threshold:</b> {idea.get('decision_threshold', '')}\n\n<b>Distribution:</b> {idea.get('distribution', '')}\n\n<b>Monetization:</b> {idea.get('monetization', '')}"
    elif action == 'radar_anti':
        text = f"🛑 <b>Anti-thesis ({idea.get('idea_title', '')})</b>\n\n{idea.get('anti_thesis', 'Нет данных')}"
        
    if chat_id and text:
        url = f"{TG_API}/sendMessage"
        requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}, timeout=10)
        tg_answer_callback(cq_id)
        print(f"[bot][radar] Sent {action} details for {short_title}")
    else:
        tg_answer_callback(cq_id, text='Ошибка отправки')

# ── Main polling loop ────────────────────────────────────────

def main():
    if not TG_TOKEN:
        print("[bot] ERROR: No TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN set")
        sys.exit(1)

    print(f"[bot] 🤖 Bot handler started")
    print(f"[bot]    ROOT: {ROOT}")
    print(f"[bot] Listening for 🔥 Interesting callbacks...")

    offset = None

    while True:
        try:
            updates = tg_get_updates(offset=offset)
            for update in updates:
                offset = update['update_id'] + 1
                cq = update.get('callback_query')
                if not cq:
                    continue
                data = cq.get('data', '')
                if data.startswith('interesting:'):
                    try:
                        handle_interesting(cq)
                    except Exception as e:
                        print(f"[bot] ❌ Error: {e}")
                        traceback.print_exc()
                elif data.startswith('radar_'):
                    try:
                        handle_radar_callback(cq)
                    except Exception as e:
                        print(f"[bot] ❌ Radar Error: {e}")
                        traceback.print_exc()

        except requests.exceptions.Timeout:
            continue
        except requests.exceptions.ConnectionError as e:
            print(f"[bot] Connection error: {e}, retrying in 5s...")
            time.sleep(5)
        except Exception as e:
            print(f"[bot] ❌ Poll error: {e}")
            traceback.print_exc()
            time.sleep(5)


if __name__ == '__main__':
    main()
