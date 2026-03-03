import os
import json
import requests
from datetime import datetime, timezone

from config import config

def _detect_root() -> str:
    env_root = os.getenv('AI_DIGEST_ROOT')
    if env_root:
        return env_root
    server_root = '/home/geo/.openclaw/workspace'
    if os.path.exists(server_root):
        return server_root
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = _detect_root()
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN') or os.getenv('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID') or os.getenv('TELEGRAM_CHAT_ID') or os.getenv('TELEGRAM_CHANNEL')

def format_card(idea: dict) -> str:
    """Format a single idea into the Russian Business Idea Radar card."""
    title = idea.get('idea_title', 'Unknown Idea')
    score = idea.get('rating', 0)
    
    text = f"🔥 <b>{title}</b>\n\n"
    text += f"<b>В чем боль (User Stories & Problem):</b>\n{idea.get('problem_description', '')}\n\n"
    text += f"<b>Решение (Proposed Solution):</b>\n{idea.get('proposed_solution', '')}\n\n"
    text += f"<b>Кто платит (ICP):</b> {idea.get('icp', '')}\n\n"
    if idea.get('sources'):
        text += f"<b>📌 Источники:</b> {idea.get('sources')}\n\n"
    text += f"📊 <b>Score:</b> {score}/100\n"
    
    return text

def save_payload(ideas: list[dict]):
    """Save raw runs to out_trends."""
    dt_str = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    out_dir = os.path.join(ROOT, 'out_trends')
    os.makedirs(out_dir, exist_ok=True)
    
    # Full payload
    path_payload = os.path.join(out_dir, f'ideas-payload-{dt_str}.json')
    with open(path_payload, 'w', encoding='utf-8') as f:
        json.dump(ideas, f, ensure_ascii=False, indent=2)
        
    # Markdown Digest
    path_digest = os.path.join(out_dir, f'ideas-digest-{dt_str}.md')
    with open(path_digest, 'w', encoding='utf-8') as f:
        f.write("# Business Idea Radar\n\n")
        num_new = sum(1 for i in ideas if i.get('status') in ['new', 'growing', 'reframed'])
        f.write(f"Generated {len(ideas)} ideas ({num_new} fresh).\n\n")
        
        for idea in ideas:
            f.write(f"## {idea.get('idea_title')}\n")
            f.write(f"**Score:** {idea.get('rating')} | **Status:** {idea.get('status')}\n")
            f.write(f"**Problem:** {idea.get('problem_description')}\n")
            f.write(f"**Solution:** {idea.get('proposed_solution')}\n\n")

def publish_to_telegram(final_ideas: list[dict], token_usage: dict = None):
    if not BOT_TOKEN or not CHAT_ID:
        print("[radar][publish] Telegram credentials missing, skipping broadcast")
        return
        
    print(f"[radar][publish] Sending {len(final_ideas)} ideas to Telegram...")
    
    for idea in final_ideas:
        text = format_card(idea)
        
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        
        try:
            r = requests.post(url, json=payload, timeout=10)
            if r.status_code != 200:
                print(f"[radar][publish] Telegram error: {r.text}")
        except Exception as e:
            print(f"[radar][publish] Failed to send: {e}")
    
    if token_usage:
        send_cost_summary(token_usage)

def send_cost_summary(token_usage: dict):
    """Send a cost/token summary message at the end of the pipeline run."""
    if not BOT_TOKEN or not CHAT_ID:
        return
    
    prompt_tokens = token_usage.get('prompt_tokens', 0)
    completion_tokens = token_usage.get('completion_tokens', 0)
    total_tokens = token_usage.get('total_tokens', 0)
    
    # gemini-3-flash-preview pricing via OpenRouter: ~$0.075/1M input, ~$0.30/1M output
    input_cost = (prompt_tokens / 1_000_000) * 0.075
    output_cost = (completion_tokens / 1_000_000) * 0.30
    total_cost = input_cost + output_cost
    
    model = config.LLM_MODEL
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    
    text = (
        f"💸 <b>Radar Pipeline Cost Summary</b>\n"
        f"🕐 {now}\n\n"
        f"<b>Модель:</b> {model}\n"
        f"<b>Токены:</b>\n"
        f"  • Input: {prompt_tokens:,}\n"
        f"  • Output: {completion_tokens:,}\n"
        f"  • Total: {total_tokens:,}\n\n"
        f"<b>Стоимость:</b>\n"
        f"  • Input: ${input_cost:.5f}\n"
        f"  • Output: ${output_cost:.5f}\n"
        f"  • 💰 Total: <b>${total_cost:.5f}</b>"
    )
    
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=10
        )
        print(f"[radar][publish] Cost summary sent. Total: ${total_cost:.5f}")
    except Exception as e:
        print(f"[radar][publish] Failed to send cost summary: {e}")
