"""Read-only access to the Bear SQLite database."""

import os
import sqlite3
from pathlib import Path

DB_PATH = os.path.expanduser(
    "~/Library/Group Containers/9K33E3U3T4.net.shinyfrog.bear"
    "/Application Data/database.sqlite"
)


def _connect() -> sqlite3.Connection:
    if not Path(DB_PATH).exists():
        raise FileNotFoundError(f"Bear database not found at {DB_PATH}")
    return sqlite3.connect(DB_PATH)


def read_note(title: str) -> str | None:
    """Read note content by exact title. Returns None if not found."""
    db = _connect()
    try:
        row = db.execute(
            "SELECT ZTEXT FROM ZSFNOTE WHERE ZTITLE = ? AND ZTRASHED = 0",
            (title,),
        ).fetchone()
        return row[0] if row else None
    finally:
        db.close()


def search_notes(query: str, limit: int = 20) -> list[dict]:
    """Search notes by text content. Returns list of {title, snippet}."""
    db = _connect()
    try:
        rows = db.execute(
            "SELECT ZTITLE, SUBSTR(ZTEXT, 1, 200) FROM ZSFNOTE "
            "WHERE ZTEXT LIKE ? AND ZTRASHED = 0 "
            "ORDER BY ZMODIFICATIONDATE DESC LIMIT ?",
            (f"%{query}%", limit),
        ).fetchall()
        return [{"title": r[0], "snippet": r[1]} for r in rows]
    finally:
        db.close()


def list_notes_by_tag(tag: str) -> list[str]:
    """List note titles that contain a given tag."""
    # Tags are inline in note text as #tag or #tag/subtag
    tag_pattern = f"%#{tag}%"
    db = _connect()
    try:
        rows = db.execute(
            "SELECT ZTITLE FROM ZSFNOTE "
            "WHERE ZTEXT LIKE ? AND ZTRASHED = 0 "
            "ORDER BY ZMODIFICATIONDATE DESC",
            (tag_pattern,),
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        db.close()


def list_tags() -> list[str]:
    """List all tags in Bear."""
    db = _connect()
    try:
        rows = db.execute(
            "SELECT ZTITLE FROM ZSFNOTETAG ORDER BY ZTITLE"
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        db.close()


def get_note_uuid(title: str) -> str | None:
    """Get the UUID of a note by title. Used for trash operations."""
    db = _connect()
    try:
        row = db.execute(
            "SELECT ZUNIQUEIDENTIFIER FROM ZSFNOTE "
            "WHERE ZTITLE = ? AND ZTRASHED = 0",
            (title,),
        ).fetchone()
        return row[0] if row else None
    finally:
        db.close()


def get_invoice_notes(year: int) -> list[dict]:
    """Query invoice notes for a given year from the Bear database.

    Looks for notes tagged #documents/work with title pattern 'Faktura MM/YYYY'.
    Parses netto/VAT/brutto from note text.
    """
    import re

    db = _connect()
    try:
        rows = db.execute(
            "SELECT ZTITLE, ZTEXT FROM ZSFNOTE "
            "WHERE ZTEXT LIKE '%#documents/work%' "
            "AND ZTITLE LIKE ? "
            "AND ZTRASHED = 0 "
            "ORDER BY ZTITLE",
            (f"Faktura %/{year}",),
        ).fetchall()
    finally:
        db.close()

    invoices = []
    for title, text in rows:
        inv = {"title": title, "text": text}

        # Parse month from title
        m = re.search(r"Faktura (\d{2})/(\d{4})", title)
        if m:
            inv["month"] = int(m.group(1))
            inv["year"] = int(m.group(2))

        # Parse amounts from note text
        for field in ("Netto", "VAT", "Brutto"):
            pattern = rf"\*\*{field}:\*\*\s*([\d\s\u00a0]+,\d{{2}})"
            match = re.search(pattern, text)
            if match:
                val_str = match.group(1).replace("\u00a0", " ").replace(" ", "").replace(",", ".")
                inv[field.lower()] = float(val_str)

        # Parse contractor
        cm = re.search(r"\*\*Kontrahent:\*\*\s*(.+)", text)
        if cm:
            inv["contractor"] = cm.group(1).strip()

        # Parse date
        dm = re.search(r"\*\*Data wystawienia:\*\*\s*(.+)", text)
        if dm:
            inv["date"] = dm.group(1).strip()

        invoices.append(inv)

    return invoices
