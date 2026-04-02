"""
Filters a WhatsApp chat export to only include messages within a date range.

Supports:
  - iOS:     [DD/MM/YYYY, HH:MM:SS] Name: message
  - Android: DD/MM/YYYY, HH:MM - Name: message
  - Variants with AM/PM, 2-digit years, dot or dash separators
  - Both .txt files and .zip exports
"""

import re
import zipfile
from datetime import datetime, date
from pathlib import Path


# Matches the date portion at the start of a WhatsApp message line.
# Handles optional leading "[", and date separators / . -
_LINE_RE = re.compile(
    r'^\[?(\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4})'   # date
    r'[,\s]\s*\d{1,2}:\d{2}'                        # time (HH:MM)
)

# Try DD/MM before MM/DD — more common internationally (and in Turkey)
_DATE_FORMATS = [
    '%d/%m/%Y', '%d/%m/%y',
    '%m/%d/%Y', '%m/%d/%y',
    '%d.%m.%Y', '%d.%m.%y',
    '%d-%m-%Y', '%d-%m-%y',
    '%Y/%m/%d', '%Y-%m-%d',
]


def _parse_date(date_str: str) -> date | None:
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None


def _read_chat(file_path: Path) -> str:
    """Extract raw chat text from either a .txt or .zip file."""
    if file_path.suffix.lower() == '.zip':
        with zipfile.ZipFile(file_path) as zf:
            txt_names = [n for n in zf.namelist() if n.endswith('.txt')]
            if not txt_names:
                raise ValueError("No .txt file found inside the WhatsApp zip export.")
            # Prefer the file named _chat.txt if present
            chat_file = next((n for n in txt_names if '_chat' in n.lower()), txt_names[0])
            with zf.open(chat_file) as f:
                return f.read().decode('utf-8', errors='replace')
    else:
        return file_path.read_text(encoding='utf-8', errors='replace')


def filter_by_date_range(
    file_path: Path,
    date_from: date,
    date_to: date,
) -> tuple[str, dict]:
    """
    Returns (filtered_text, stats) where stats contains message counts.
    Multi-line messages are kept together — continuation lines follow
    their parent message's in-range status.
    """
    raw = _read_chat(file_path)
    lines = raw.splitlines()

    filtered = []
    in_range = False
    total_messages = 0
    kept_messages = 0

    for line in lines:
        m = _LINE_RE.match(line)
        if m:
            # New message — determine if it falls in the range
            msg_date = _parse_date(m.group(1))
            total_messages += 1
            if msg_date is not None:
                in_range = date_from <= msg_date <= date_to
            else:
                in_range = False

            if in_range:
                kept_messages += 1

        if in_range:
            filtered.append(line)

    stats = {
        "total_messages": total_messages,
        "kept_messages": kept_messages,
        "dropped_messages": total_messages - kept_messages,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
    }

    return '\n'.join(filtered), stats
