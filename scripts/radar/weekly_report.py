#!/usr/bin/env python3
"""
Generates the weekly Idea Radar retrospective.
"""

import sys
import os
from pathlib import Path
from datetime import datetime

def _detect_root() -> Path:
    env_root = os.getenv('AI_DIGEST_ROOT')
    if env_root:
        return Path(env_root).expanduser()
    return Path(__file__).resolve().parent.parent.parent

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

from . import memory
from . import publish

def main():
    stats = memory.get_weekly_stats()
    
    # Format Weekly Digest
    text = f"📊 <b>Business Idea Radar: Weekly Report</b>\n\n"
    text += f"Всего идей проанализировано за 7 дней: {stats['total']}\n\n"
    
    if stats['interested']:
        text += "💡 <b>Отмечено интересно:</b>\n"
        for i in stats['interested']:
            text += f"- {i.get('idea_title')} (Score: {i.get('rating')})\n"
        text += "\n"
        
    if stats['growing']:
        text += "📈 <b>Быстрорастущие проблемы:</b>\n"
        for i in stats['growing'][:3]:
            text += f"- {i.get('idea_title')} (Score: {i.get('rating')})\n"
        text += "\n"
        
    if stats['top']:
        text += "🔥 <b>Топ идей по Score:</b>\n"
        for i in stats['top'][:5]:
            text += f"- {i.get('idea_title')} (Score: {i.get('rating')})\n"
            
    # Send via exactly the same mechanism as normal
    import requests
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    
    if bot_token and chat_id:
        requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML"
            },
            timeout=10
        )
        print("[radar] Weekly report sent to Telegram.")
    else:
        print("[radar] Could not send. Missing tokens.")
        print(text)

if __name__ == '__main__':
    main()
