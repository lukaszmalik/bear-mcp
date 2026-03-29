"""Write operations to Bear via URL scheme."""

import re
import subprocess
import time
import urllib.parse

from . import bear_db

# Always use quote_via=urllib.parse.quote so spaces become %20, not +
# Bear reads + literally.
_QUOTE = urllib.parse.quote


def _open_url(url: str) -> None:
    """Open a bear:// URL via macOS `open` command."""
    subprocess.run(["open", url], check=True)


def _encode_params(**kwargs: str) -> str:
    return urllib.parse.urlencode(kwargs, quote_via=_QUOTE)


def _strip_leading_h1(body: str) -> str:
    """Strip a leading h1 heading from body — the title is already the h1."""
    return re.sub(r"^#\s+.+\n*", "", body.lstrip("\n"), count=1)


def create_note(title: str, body: str, tags: str | None = None) -> None:
    """Create a new Bear note.

    Args:
        title: Note title (will be shown as # heading).
        body: Markdown body content.
        tags: Comma-separated tags (without #), e.g. 'ai/chats'.
    """
    text = f"# {title}\n\n{_strip_leading_h1(body)}"
    if tags:
        text += f"\n\n#{tags}"

    params = _encode_params(
        text=text,
        open_note="no",
        show_window="no",
    )
    _open_url(f"bear://x-callback-url/create?{params}")


def create_note_with_file(
    title: str,
    tags: str,
    file_b64: str,
    filename: str,
    body: str | None = None,
) -> None:
    """Create a Bear note with an embedded file attachment (base64)."""
    kw = {
        "title": title,
        "tags": tags,
        "file": file_b64,
        "filename": filename,
        "open_note": "no",
        "show_window": "no",
    }
    if body:
        kw["text"] = body
    params = _encode_params(**kw)
    _open_url(f"bear://x-callback-url/create?{params}")


def append_text(title: str, text: str) -> None:
    """Append text to an existing Bear note."""
    params = _encode_params(
        title=title,
        text=text,
        mode="append",
        open_note="no",
        show_window="no",
    )
    _open_url(f"bear://x-callback-url/add-text?{params}")


def trash_note(title: str) -> str:
    """Trash a note by looking up its UUID first (never trash by title directly).

    Returns the UUID of the trashed note, or raises if not found.
    """
    uuid = bear_db.get_note_uuid(title)
    if not uuid:
        raise ValueError(f"Note not found: {title}")

    params = _encode_params(id=uuid, show_window="no")
    _open_url(f"bear://x-callback-url/trash?{params}")
    return uuid


def save_chat(title: str, content: str, subtag: str | None = None) -> None:
    """Save content as a Bear note under #ai/chats.

    Args:
        title: Note title.
        content: Markdown content to save.
        subtag: Optional subtag (devops/code/work/howto).
    """
    tags_line = "#ai/chats"
    if subtag:
        tags_line += f"/{subtag}"

    text = f"# {title}\n\n{_strip_leading_h1(content)}\n\n{tags_line}"
    params = _encode_params(
        text=text,
        open_note="no",
        show_window="no",
    )
    _open_url(f"bear://x-callback-url/create?{params}")


def batch_sleep() -> None:
    """Sleep between Bear URL scheme calls in batch operations."""
    time.sleep(0.7)
