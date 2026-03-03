import os
import json
import requests
from typing import List, Dict, Any

from pydantic import BaseModel, Field

from config import config

# --------- Prompts ---------

STEP1_PROMPT = """
You are a Business Intelligence Analyst. Extract ONLY high-value problem signals from the following texts.
We are looking for:
- People paying for bad workarounds (Weight: +3)
- Manual grueling work / explicit workarounds (Weight: +2)
- Mentioning budget or willingness to pay (Weight: +2)
- High frequency / urgency or severe pain ("tired of", "no good tool") (Weight: +1)

Ignore generic complaints without a specific problem.
Return the extracted signals.
"""

STEP2_PROMPT = """
Take the following raw problem signals (which come from HN, Reddit, X, IndieHackers, etc).
Group them into distinct "Problems" or "Ideas".
For each one, focus heavily on the real user stories and problems being faced. Mention the real workarounds people use in the comments.
Propose a simple actionable solution that a solo founder could build.
"""

STEP3_PROMPT = """
Take the following Problems and Solutions.
Rate each idea from 0 to 100 based on the severity of the pain and willingness to pay.

BUILDER PROFILE:
- Solo founder or very small team (1-2 people)
- Can build: web apps, bots, scrapers, automations, API integrations, simple SaaS
- Cannot build: hardware, regulated fintech/identity, enterprise infra, marketplace with cold start problem

Discard any idea violating the BUILDER PROFILE constraints.

IMPORTANT: Output as many ideas as possible — aim for at least 60 distinct ideas.
The pipeline will then rank them and pick the top 20 to send.
Do NOT filter aggressively — output all plausible ideas with a rating.

Finally, output a JSON array of ALL ideas (include ALL ideas, do not filter by score).
"""

# --------- Models ---------
# We are currently using basic string manipulation / json extraction, 
# but could theoretically use `instructor` here if the endpoint supports tool calling.
# For Gemini via OpenRouter, we will just use JSON mode.

class RadarProcessor:
    def __init__(self):
        self.api_key = config.OPENROUTER_API_KEY
        self.model = config.IDEA_MODEL
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        
    def _call_llm(self, sys_prompt: str, user_prompt: str, expect_json: bool = False) -> str:
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
            'HTTP-Referer': 'https://local.openclaw', # Required by OpenRouter
            'X-Title': 'business-idea-radar',
        }
        
        payload = {
            'model': self.model,
            'messages': [
                {'role': 'system', 'content': sys_prompt},
                {'role': 'user', 'content': user_prompt}
            ],
            'temperature': 0.2
        }
        
        if expect_json:
            payload['response_format'] = {'type': 'json_object'}
            
        r = requests.post(
            'https://openrouter.ai/api/v1/chat/completions', 
            headers=headers, 
            json=payload, 
            timeout=120
        )
        r.raise_for_status()
        
        resp = r.json()
        usage = resp.get('usage', {})
        self.total_prompt_tokens += usage.get('prompt_tokens', 0)
        self.total_completion_tokens += usage.get('completion_tokens', 0)
        
        return resp['choices'][0]['message']['content']

    def extract_signals(self, raw_items: List[Dict]) -> str:
        if not raw_items:
            return ""
            
        print(f"[radar][process] Step 1: Extracting signals from {len(raw_items)} items...")
        
        # Batch items to avoid massive context
        # For MVP, just dump them all if it's < 50, otherwise we'd Map-Reduce
        text_batch = []
        for i, item in enumerate(raw_items[:150]):  # Process up to 150 signals
            text_batch.append(f"--- Item {i} ({item['source']}) ---\n{item['raw_text']}")
            
        user_prompt = "Find the signals in these items:\n\n" + "\n".join(text_batch)
        
        return self._call_llm(STEP1_PROMPT, user_prompt)

    def generate_hypotheses(self, signals_text: str) -> str:
        if not signals_text.strip():
            return ""
            
        print("[radar][process] Step 2: Generating problems and hypotheses...")
        return self._call_llm(STEP2_PROMPT, signals_text)

    def score_and_format(self, hypotheses_text: str) -> List[Dict]:
        if not hypotheses_text.strip():
            return []
            
        print("[radar][process] Step 3: Scoring and formulating Anti-thesis...")
        
        schema = {
            "ideas": [
                {
                    "idea_title": "String - Short value proposition name",
                    "problem_description": "String - Description of the pain / workaround based on the real user stories",
                    "proposed_solution": "String - What could be built to solve it",
                    "icp": "String - Who exactly has this problem",
                    "sources": "String - Which platforms / communities this idea came from (e.g. Reddit r/SaaS, HN Ask HN, X/Twitter). Be specific.",
                    "rating": "Int 0-100"
                }
            ]
        }
        
        sys_p = STEP3_PROMPT
        sys_p += f"\n\nYou MUST return a JSON object matching this schema:\n{json.dumps(schema)}"
        
        raw_json_str = self._call_llm(sys_p, hypotheses_text, expect_json=True)
        
        try:
            # Clean up markdown format if present
            if "```json" in raw_json_str:
                raw_json_str = raw_json_str.split("```json\n")[1].split("\n```")[0]
            elif "```" in raw_json_str:
                raw_json_str = raw_json_str.split("```\n")[1].split("\n```")[0]
                
            data = json.loads(raw_json_str)
            return data.get("ideas", [])
        except Exception as e:
            print(f"[radar][process] Error parsing Step 3 JSON: {e}\nRaw: {raw_json_str[:200]}...")
            return []

    def run_pipeline(self, raw_items: list[dict]) -> tuple[list[dict], dict]:
        """Run the 3-step reasoning chain. Returns (ideas, token_usage)."""
        signals = self.extract_signals(raw_items)
        hypos = self.generate_hypotheses(signals)
        final_ideas = self.score_and_format(hypos)
        
        print(f"[radar][process] Pipeline generated {len(final_ideas)} ideas")
        
        token_usage = {
            'prompt_tokens': self.total_prompt_tokens,
            'completion_tokens': self.total_completion_tokens,
            'total_tokens': self.total_prompt_tokens + self.total_completion_tokens,
        }
        return final_ideas, token_usage

def process_items(items: list[dict]) -> tuple[list[dict], dict]:
    p = RadarProcessor()
    return p.run_pipeline(items)
