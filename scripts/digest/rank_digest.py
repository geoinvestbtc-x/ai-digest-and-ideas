import os
import json
import requests
from typing import List, Dict

# Import config from radar module
import sys
from pathlib import Path
_scripts_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scripts_dir / "radar"))
from config import config

GLOBAL_CONTEXT = """
The reader is a solo developer or small team (1-3 people) building SaaS or web/mobile apps. 
They read this digest every morning and act on it the same day. 
They need posts that are immediately actionable — a tool they can try today, a technique they can apply this week, or news that changes a decision they need to make right now. 
They do NOT need inspiration, theory, or enterprise content.
"""

PROMPTS = {
    "AI Marketing": """
Select the top 5-10 most actionable and relevant posts from the provided list.

* INCLUDE: AI tools for marketing automation, growth tactics for SaaS/apps, real case studies with numbers, new AI marketing tools, user acquisition strategies for solo dev products.
* EXCLUDE: general marketing without AI, corporate and offline marketing, PR and brand strategy without product context.
* FINAL FILTER: Can a solo founder or small dev team use this today to get more users for their app?
""",
    "AI Coding": """
Select the top 5-10 most actionable and relevant posts from the provided list.

* INCLUDE: new features and workflows of agentic tools (Cursor, Claude Code, Cline and similar), code generation techniques that actually save time, patterns for integrating LLMs into apps, architectural solutions for AI SaaS, real "built X in Y hours with Z" stories, new libraries for AI apps.
* EXCLUDE: general programming tutorials without AI, DevOps and infrastructure not directly tied to AI development, academic CS and algorithms, enterprise architecture.
* FINAL FILTER: Does this help a solo developer or small dev team build or ship faster using AI?
""",
    "General AI": """
Select the top 5-10 most actionable and relevant posts from the provided list.

* INCLUDE: new models with practical API access, new AI APIs and SDKs that can be integrated now, benchmarks affecting model choice, practical use cases in products, AI infrastructure updates affecting developers (pricing, context, speed).
* EXCLUDE: AI regulation and policy, corporate strategies and M&A, academic research without practical application, general AI hype without actionable content, AI art and video without a developer tool angle.
* FINAL FILTER: Does this change the choice of AI tools or models for a developer right now?
""",
    "AI Design": """
Select the top 5-10 most actionable and relevant posts from the provided list.

* INCLUDE: AI tools for generating UI components and layouts, design-to-code tools, prompts for UI generation, component libraries for SaaS, real examples like "designed an app using X", web design inspiration specifically for SaaS and apps.
* EXCLUDE: graphic and print design, branding without a UI component, motion and video, Figma tutorials without AI, design theory without practical tools.
* FINAL FILTER: Can a solo developer or small dev team use this to make their app look better or build UI faster?
""",
    "OpenClaw": """
Select the top 5-10 most actionable and relevant posts from the provided list.

* INCLUDE: OpenClaw updates and releases, new skills and capabilities, infrastructure improvements, real automation use cases, integrations with other tools, tips and workflows, MCP server updates.
* EXCLUDE: general Claude or Anthropic news unrelated to OpenClaw, other AI agents explicitly not related to OpenClaw, general automation without OpenClaw.
* FINAL FILTER: Is this directly about OpenClaw or immediately applicable for someone using it?
""",
    "GitHub Projects": """
Select the top 5-10 most actionable and relevant posts from the provided list.

* INCLUDE: boilerplates and starter templates for SaaS and web/mobile apps, time-saving developer tools, new open source libraries with practical production use, AI dev tools, Show HN posts with practically useful projects, tools simplifying deployment, auth, payments, or databases for small teams.
* EXCLUDE: academic and research projects, enterprise-only tools, hardware and embedded systems, lists and collections without a specific tool, discussions about GitHub as a platform.
* FINAL FILTER: Would a solo developer or small dev team star this repo and use it in their next project?
"""
}

class LLMRanker:
    def __init__(self):
        self.api_key = config.OPENROUTER_API_KEY
        self.model = "google/gemini-3-flash-preview"
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        
    def filter_category(self, category: str, posts: List[Dict]) -> List[Dict]:
        if not posts:
            return []
            
        sys_prompt = GLOBAL_CONTEXT + "\n" + PROMPTS.get(category, "")
        if not PROMPTS.get(category, ""):
            print(f"[rank_digest] Warning: No LLM prompt found for category '{category}'. Falling back to engagement sort.")
            return sorted(posts, key=lambda x: x.get("engagement", 0), reverse=True)[:10]

        # Construct the user prompt with the post candidates
        # We number them so the LLM can just return a list of IDs or URLs
        user_prompt = "Here are the candidate posts collected from various sources:\n\n"
        url_map = {}
        for i, post in enumerate(posts):
            post_id = f"POST_{i}"
            url_map[post_id] = post
            user_prompt += f"--- {post_id} ---\n"
            user_prompt += f"Title: {post.get('title', 'Unknown')}\n"
            user_prompt += f"URL: {post.get('url', 'Unknown')}\n"
            user_prompt += f"Source: {post.get('source', 'Unknown')} (Engagement: {post.get('engagement', 0)})\n"
            snippet = str(post.get('snippet', ''))
            user_prompt += f"Snippet/Content: {snippet[:600]}\n\n"

        user_prompt += """
Based on your system instructions, select the 5 to 10 most relevant and actionable posts for the user profile.
If there are fewer than 5 good posts, return only the good ones. Do NOT include fluff.

For each selected post, provide:
1. The `id` (e.g. "POST_4")
2. `rewritten_title`: Rewrite the title to be extremely clear and understandable about what the tool/post is. (e.g. instead of "I built a sub-500ms latency voice agent", write "Low-latency open source voice agent built from scratch"). It should be cleaner and more descriptive than the original title.
3. `why`: A 1-sentence explanation of why this is valuable for a solo developer/SaaS builder based on our criteria.

Return your response strictly as a JSON object with a single key "selections" containing an array of objects. Order them from best to worst.
Example:
{
  "selections": [
    {
      "id": "POST_4",
      "rewritten_title": "Clone Any Pro Trader Strategy Using OpenClaw",
      "why": "This demonstrates how to leverage OpenClaw for profitable trading automation."
    }
  ]
}
"""

        try:
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json',
                'HTTP-Referer': 'https://local.openclaw', 
                'X-Title': 'x-trend-digest',
            }
            
            payload = {
                'model': self.model,
                'messages': [
                    {'role': 'system', 'content': sys_prompt},
                    {'role': 'user', 'content': user_prompt}
                ],
                'temperature': 0.1,
                'response_format': {'type': 'json_object'}
            }
            
            print(f"[rank_digest] Calling LLM for '{category}' with {len(posts)} candidates...")
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
            
            content = resp['choices'][0]['message']['content']
            parsed = json.loads(content)
            selections = parsed.get("selections", [])
            
            selected_posts = []
            for sel in selections:
                pid = sel.get("id")
                if pid in url_map:
                    post = url_map[pid].copy()  # Create a copy so we don't mutate original if cached
                    if sel.get("rewritten_title"):
                         post["title"] = sel.get("rewritten_title")
                    post["why"] = sel.get("why", "")
                    selected_posts.append(post)
                
            print(f"[rank_digest] LLM selected {len(selected_posts)} posts out of {len(posts)} for '{category}'.")
            return selected_posts
            
        except Exception as e:
            print(f"[rank_digest] LLM failed for '{category}': {e}. Falling back to engagement sort.")
            return sorted(posts, key=lambda x: x.get("engagement", 0), reverse=True)[:10]

