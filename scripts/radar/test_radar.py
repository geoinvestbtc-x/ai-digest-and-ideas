import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

from radar import collect, process

# Mock items
mock_items = [
    {
        "id": "mock_reddit_1",
        "source": "reddit",
        "url": "https://reddit.com/r/SaaS/comments/fake",
        "timestamp": 123456789,
        "raw_text": "I am so tired of copy pasting from PDF to Excel. I pay a VA $500/mo just to do this manually. Is there a tool that does this with AI?"
    },
    {
        "id": "mock_hn_1",
        "source": "hn",
        "url": "https://news.ycombinator.com/item?id=fake",
        "timestamp": 123456799,
        "raw_text": "Parsing unstructured invoices is still a nightmare. The existing OCR tools are $2k/year and still fail on weird layouts."
    }
]

print("Testing Gemini integration...")
ideas = process.process_items(mock_items)
print("\nFinal Output:")
import json
print(json.dumps(ideas, indent=2, ensure_ascii=False))
