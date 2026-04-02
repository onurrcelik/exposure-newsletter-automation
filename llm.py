import os
import re
import json
from openai import OpenAI
from pathlib import Path

_MODEL = os.environ.get("MINIMAX_MODEL", "MiniMax-M2.7")


def _clean(text: str) -> str:
    """Strip <think>...</think> reasoning blocks from model output."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _client() -> OpenAI:
    return OpenAI(
        api_key=os.environ["MINIMAX_API_KEY"],
        base_url="https://api.minimax.io/v1",
    )


def _read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _load_transcript(edition_dir: Path) -> str:
    for ext in (".txt", ".md"):
        p = edition_dir / f"transcript{ext}"
        if p.exists():
            return _read_text_file(p)
    return ""


def _load_whatsapp(edition_dir: Path) -> str:
    # Prefer the date-filtered version
    filtered = edition_dir / "whatsapp_filtered.txt"
    if filtered.exists():
        return _read_text_file(filtered)
    raw = edition_dir / "whatsapp_export.txt"
    if raw.exists():
        return _read_text_file(raw)
    return ""


def extract(edition_id: str, date_from: str, date_to: str, uploads_dir: Path) -> dict:
    edition_dir = uploads_dir / edition_id
    transcript = _load_transcript(edition_dir)
    whatsapp = _load_whatsapp(edition_dir)

    prompt = f"""You are preparing content for a newsletter covering the period {date_from} to {date_to}.

Below are two sources from that period:

--- MEETING TRANSCRIPT (Fathom) ---
{transcript[:10000]}

--- WHATSAPP GROUP CHAT ---
{whatsapp[:10000]}

Analyze both sources and extract the most relevant content for a newsletter.
Return ONLY a valid JSON object with this exact structure:
{{
  "summary": "2-3 sentence overview of this period",
  "highlights": ["highlight 1", "highlight 2"],
  "topics": ["topic discussed 1", "topic discussed 2"],
  "decisions": ["decision or announcement 1"],
  "action_items": ["follow-up item 1"],
  "notable_quotes": [{{"text": "quote", "source": "transcript or whatsapp", "author": "name if known"}}]
}}"""

    resp = _client().chat.completions.create(
        model=_MODEL,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.3,
    )

    return json.loads(_clean(resp.choices[0].message.content))


def generate_draft(extracted: dict, date_from: str, date_to: str) -> str:
    prompt = f"""Write a newsletter for the period {date_from} to {date_to}.

Use these extracted highlights as your source material:
{json.dumps(extracted, indent=2)}

Guidelines:
- Warm, professional tone
- Structure: intro → highlights → topics & discussions → decisions/updates → closing
- No markdown headers with # symbols — use natural section titles in prose
- Keep it concise and engaging, suitable for a team or community newsletter
- Return plain text only"""

    resp = _client().chat.completions.create(
        model=_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )

    return _clean(resp.choices[0].message.content)
