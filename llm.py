import os
import re
import json
import urllib.request
from html.parser import HTMLParser
from openai import OpenAI
from pathlib import Path


# ── URL fetching ───────────────────────────────────────────────────────────────

class _TextExtractor(HTMLParser):
    """Extract readable text from HTML, skipping script/style/nav blocks."""

    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "nav", "footer", "head"):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style", "nav", "footer", "head"):
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            stripped = data.strip()
            if stripped:
                self._parts.append(stripped)

    def get_text(self) -> str:
        return " ".join(self._parts)


def _fetch_url(url: str, max_chars: int = 3000) -> str:
    """Fetch a URL and return extracted plain text (best-effort, never raises)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = resp.read(60_000).decode("utf-8", errors="replace")
        parser = _TextExtractor()
        parser.feed(raw)
        text = " ".join(parser.get_text().split())
        return text[:max_chars]
    except Exception:
        return ""


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



def _load_whatsapp(edition_dir: Path) -> str:
    filtered = edition_dir / "whatsapp_filtered.txt"
    if filtered.exists():
        return _read_file(filtered)
    raw = edition_dir / "whatsapp_export.txt"
    if raw.exists():
        return _read_file(raw)
    return ""


def _enrich_link(link: dict) -> dict:
    """Fetch the link URL and add a 4-5 sentence newsletter description."""
    url = link.get("url", "")
    page_text = _fetch_url(url)
    existing_notes = link.get("notes", "")

    prompt = f"""You are writing content for a tech/community newsletter.

URL: {url}
Chat notes: {existing_notes}
Page content excerpt:
{page_text if page_text else "(could not fetch — infer from URL and chat notes)"}

Write a 4-5 sentence description of this link for a newsletter reader.
- What is this resource? (1-2 sentences)
- Why is it interesting or noteworthy — key insights, what makes it valuable? (2-3 sentences)
- Base it primarily on the page content when available, otherwise infer from the URL and chat notes.
- Do NOT start with "This link" or "This article" or "This is".
- Tone: concise, informative, engaging.

Return ONLY the description text, no JSON, no labels."""

    resp = _client().chat.completions.create(
        model=_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
    )
    link["description"] = _clean(resp.choices[0].message.content).strip()
    return link


def extract_whatsapp(edition_dir: Path, date_from: str, date_to: str) -> dict:
    chat = _load_whatsapp(edition_dir)

    prompt = f"""Analyze this WhatsApp group chat from {date_from} to {date_to} and extract structured content for a newsletter.

WHATSAPP CHAT:
{chat[:12000]}

Return ONLY valid JSON with this exact structure:
{{
  "summary": "2-3 sentence overview of what was discussed and shared in the chat",
  "highlights": [
    "most important thing that happened or was shared"
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
      "title": "descriptive title of the link — infer from the URL if not stated (e.g. GitHub: owner/repo name, arXiv: paper title if guessable, Twitter: @username's post)",
      "notes": "Write 2-4 sentences. If people discussed this link in the chat, summarize what they said and their reactions. If nobody commented, write a brief review based on what the URL reveals (domain, path, slug) and any surrounding messages that give context. Always give the reader something useful."
    }}
  ]
}}

Rules for shared_links:
- Extract EVERY content URL shared in the chat — none omitted.
- SKIP meeting/calendar links: zoom.us, meet.google.com, teams.microsoft.com, calendly.com, whereby.com, and similar video-conferencing or scheduling URLs. These are logistics, not content.
- Classify type by domain: github.com=repo, arxiv.org=paper, twitter.com/x.com=twitter, linkedin.com=linkedin, instagram.com=instagram, youtube.com=youtube, else article or other.
- For notes: first check if there are messages before/after the link where people reacted or discussed it — if yes, summarize what they said and their reactions. If nobody commented, analyze the URL path/slug and any nearby messages to write a short independent description of what this link likely is and why it may be relevant.
- If no links were shared, return an empty array."""

    resp = _client().chat.completions.create(
        model=_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    result = _parse_json(resp.choices[0].message.content)
    result["shared_links"] = [_enrich_link(link) for link in result.get("shared_links", [])]
    return result


