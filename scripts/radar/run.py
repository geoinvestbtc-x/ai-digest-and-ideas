#!/usr/bin/env python3
"""
Main entry point for the Business Idea Radar pipeline.

Run as:
    python3 scripts/radar/run.py
"""
import sys
import os
import traceback
from datetime import datetime
from pathlib import Path

def _detect_root() -> Path:
    env_root = os.getenv('X_TREND_ROOT')
    if env_root:
        return Path(env_root).expanduser()
    server_root = Path('/home/geo/.openclaw/workspace')
    if server_root.exists():
        return server_root
    return Path(__file__).resolve().parent.parent.parent

ROOT = _detect_root()

# Ensure we can load from root `.env` before we do anything else
def _load_env():
    p = ROOT / '.env'
    if not p.exists():
        return
    for line in p.read_text(encoding='utf-8').splitlines():
        if '=' in line and not line.strip().startswith('#'):
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip())

_load_env()

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import config

if not config.IDEA_MODE:
    print("[radar] Disabled via IDEA_MODE=0")
    sys.exit(0)

import collect
import process
import memory
import publish

def main():
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] --- Starting Radar Pipeline ---")
    
    try:
        # Step 1: Collect
        raw_items = collect.run_collection()
        if not raw_items:
            print("[radar] No items collected.")
            return

        # Step 2: Process & Score
        generated_ideas, token_usage = process.process_items(raw_items)
        if not generated_ideas:
            print("[radar] No ideas generated from LLM.")
            return
            
        print(f"[radar] Generated {len(generated_ideas)} hypotheses prior to filtering.")

        # Step 3: Dedup via memory, collect all that pass
        memory.cleanup()
        pool = []
        for idea in generated_ideas:
            processed_idea = memory.match_and_merge(idea)
            st = processed_idea.get('status', 'new')
            # Only keep genuinely new or evolved ideas
            if st in ['new', 'growing', 'reframed']:
                pool.append(processed_idea)

        print(f"[radar] Pool after dedup: {len(pool)} ideas (target: {config.IDEA_TARGET_RAW}).")

        if not pool:
            print("[radar] No ideas passed dedup.")
            return

        # Sort by LLM rating and pick top N to send
        pool.sort(key=lambda x: x.get('rating', 0), reverse=True)
        final_ideas = pool[:config.IDEA_MAX_PER_DAY]

        print(f"[radar] Sending top {len(final_ideas)} ideas to Telegram.")


        # Step 4: Publish
        publish.save_payload(final_ideas)
        if final_ideas:
            publish.publish_to_telegram(final_ideas, token_usage)
            
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] --- Radar Pipeline Complete ---")
        
    except Exception as e:
        print(f"[radar] CRITICAL ERROR: {e}")
        traceback.print_exc()

if __name__ == '__main__':
    main()
