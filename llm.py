import os
import re
import json
from openai import OpenAI
from pathlib import Path

_MODEL = os.environ.get("MINIMAX_MODEL", "MiniMax-M2.7")


def _client() -> OpenAI:
    return OpenAI(
        api_key=os.environ["MINIMAX_API_KEY"],
        base_url="https://api.minimax.io/v1",
    )


def _clean(text: str) -> str:
    """Strip <think>...</think> reasoning blocks from model output."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _parse_json(text: str) -> dict:
    """Extract and parse the first JSON object found in the text."""
    cleaned = _clean(text)
    # Find the outermost { ... } block
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object found in response. Got: {cleaned[:200]}")
    return json.loads(cleaned[start:end + 1])


def _read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _load_transcript(edition_dir: Path) -> str:
    for ext in (".txt", ".md"):
        p = edition_dir / f"transcript{ext}"
        if p.exists():
            return _read_file(p)
    return ""


def _load_whatsapp(edition_dir: Path) -> str:
    filtered = edition_dir / "whatsapp_filtered.txt"
    if filtered.exists():
        return _read_file(filtered)
    raw = edition_dir / "whatsapp_export.txt"
    if raw.exists():
        return _read_file(raw)
    return ""


def extract_whatsapp(edition_dir: Path, date_from: str, date_to: str) -> dict:
    chat = _load_whatsapp(edition_dir)

    prompt = f"""Analyze this WhatsApp group chat from {date_from} to {date_to} and extract structured content for a newsletter.

WHATSAPP CHAT:
{chat[:12000]}

Return ONLY valid JSON with this exact structure:
{{
  "summary": "2-3 sentence overview of what was discussed and shared in the chat",
  "highlights": [
    "most important thing that happened or was shared",
    "second most important"
  ],
  "topics": [
    "topic or theme discussed"
  ],
  "notable_quotes": [
    {{
      "text": "exact quote from the chat",
      "author": "person's name or username"
    }}
  ],
  "shared_links": [
    {{
      "url": "full url",
      "type": "repo | article | paper | linkedin | twitter | instagram | youtube | other",
      "title": "title or short description of what this link is",
      "notes": "why it was shared or what the group said about it"
    }}
  ]
}}

For shared_links: extract every URL shared in the chat. Identify the type based on the domain.
If someone commented on a link, include that in notes. If no links were shared, return an empty array."""

    resp = _client().chat.completions.create(
        model=_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    return _parse_json(resp.choices[0].message.content)


def extract_transcript(edition_dir: Path, date_from: str, date_to: str) -> dict:
    transcript = _load_transcript(edition_dir)

    prompt = f"""Analyze this meeting transcript from {date_from} to {date_to} and extract structured content for a newsletter.

TRANSCRIPT:
{transcript[:12000]}

Return ONLY valid JSON with this exact structure:
{{
  "summary": "2-3 sentence overview of the meeting — what was discussed and what was the overall outcome",
  "highlights": [
    "key highlight or moment from the meeting"
  ],
  "topics": [
    "main topic or agenda item discussed"
  ],
  "decisions": [
    "a decision that was made or an announcement"
  ],
  "action_items": [
    "a task or follow-up item, include owner if mentioned"
  ],
  "notable_quotes": [
    {{
      "text": "exact quote worth including in the newsletter",
      "author": "speaker name"
    }}
  ]
}}"""

    resp = _client().chat.completions.create(
        model=_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    return _parse_json(resp.choices[0].message.content)


def generate_draft(extracted: dict, date_from: str, date_to: str) -> str:
    prompt = f"""Write a newsletter for the period {date_from} to {date_to}.

You have two sources of extracted content:

MEETING NOTES:
{json.dumps(extracted.get('transcript', {}), indent=2)}

WHATSAPP HIGHLIGHTS:
{json.dumps(extracted.get('whatsapp', {}), indent=2)}

Guidelines:
- Warm, professional tone
- Two clear sections: one for meeting notes, one for community highlights from WhatsApp
- Include highlights, key decisions, notable quotes where relevant
- Mention shared links naturally in the WhatsApp section
- No markdown # headers — use natural prose section titles
- Keep it concise and engaging
- Return plain text only"""

    resp = _client().chat.completions.create(
        model=_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )
    return _clean(resp.choices[0].message.content)
