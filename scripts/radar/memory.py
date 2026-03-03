import json
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from config import config

def _detect_root() -> Path:
    env_root = os.getenv('AI_DIGEST_ROOT')
    if env_root:
        return Path(env_root).expanduser()
    server_root = Path('/home/geo/.openclaw/workspace')
    if server_root.exists():
        return server_root
    return Path(__file__).resolve().parent.parent.parent

ROOT = _detect_root()
MEMORY_FILE = ROOT / 'memory' / 'idea-radar.jsonl'

def _load_memory() -> list[dict]:
    if not MEMORY_FILE.exists():
        return []
    records = []
    try:
        with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    except Exception as e:
        print(f"[radar][memory] Error loading: {e}")
    return records

def _save_memory(records: list[dict]):
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')

def cleanup():
    """Remove ideas older than IDEA_MEMORY_DAYS."""
    records = _load_memory()
    cutoff_ts = int((datetime.now(timezone.utc) - timedelta(days=config.IDEA_MEMORY_DAYS)).timestamp())
    kept = [r for r in records if r.get('timestamp', 0) >= cutoff_ts]
    
    if len(kept) != len(records):
        _save_memory(kept)
        print(f"[radar][memory] Cleanup: {len(records)} -> {len(kept)}")

def match_and_merge(new_idea: dict) -> dict:
    """
    Checks if an idea is already in memory using basic string matching on title/problem.
    If it exists, updates signal count.
    Rules:
    - If similarity > 0.85 -> duplicate (unless new angle)
    - If duplicate but signal_count > 30% growth -> marked as 'Growing'
    - If new ICP or workaround -> marked as 'Reframed'
    """
    records = _load_memory()
    
    # Simple text normalization for basic matching
    def norm(t):
        return str(t).lower().replace(' ', '').replace('\n', '')[:100]
        
    new_norm = norm(new_idea.get('title', ''))
    
    for r in records:
        r_norm = norm(r.get('title', ''))
        
        # Super naive match for now. LLM matching would be better in process.py, 
        # but we do a quick check here.
        if new_norm == r_norm or new_norm in r_norm or r_norm in new_norm:
            # Match found!
            old_rating = r.get('rating', 50)
            new_rating = new_idea.get('rating', 50)
            
            # Did rating grow?
            growth = (new_rating - old_rating) / old_rating if old_rating else 0
            
            # Did ICP change?
            old_icp = r.get('icp', '')
            new_icp = new_idea.get('icp', '')
            icp_changed = new_icp and old_icp and new_icp.lower()[:20] != old_icp.lower()[:20]
            
            r['rating'] = new_rating
            r['timestamp'] = int(time.time())
            
            if icp_changed and config.IDEA_ALLOW_REFRAMED:
                new_idea['status'] = 'reframed'
                r['status'] = 'reframed'
                r['icp'] = new_icp
            elif growth >= config.IDEA_GROWING_THRESHOLD:
                new_idea['status'] = 'growing'
                r['status'] = 'growing'
            else:
                new_idea['status'] = 'stale'
                r['status'] = 'stale'
                
            _save_memory(records)
            return new_idea
            
    # New idea
    new_idea['status'] = 'new'
    new_idea['timestamp'] = int(time.time())
    records.append(new_idea)
    _save_memory(records)
    
    return new_idea

def mark_status(idea_title: str, status: str):
    """Update status (e.g., 'solved', 'interested') from Telegram callback."""
    records = _load_memory()
    norm_target = str(idea_title).lower().replace(' ', '')[:100]
    
    found = False
    for r in records:
        if norm_target in str(r.get('title', '')).lower().replace(' ', ''):
            r['status'] = status
            r['user_feedback_ts'] = int(time.time())
            found = True
            
    if found:
        _save_memory(records)
        return True
    return False

def get_weekly_stats():
    """Return ideas for the weekly report."""
    records = _load_memory()
    cutoff_ts = int((datetime.now(timezone.utc) - timedelta(days=7)).timestamp())
    
    week_records = [r for r in records if r.get('timestamp', 0) >= cutoff_ts]
    
    interested = [r for r in week_records if r.get('status') == 'interested']
    growing = [r for r in week_records if r.get('status') == 'growing']
    stale = [r for r in week_records if r.get('status') == 'stale']
    
    # Top by score
    top = sorted(week_records, key=lambda x: x.get('rating', 0), reverse=True)[:5]
    
    return {
        'total': len(week_records),
        'interested': interested,
        'growing': growing,
        'stale': stale,
        'top': top
    }
