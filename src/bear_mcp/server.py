"""MCP server exposing Bear notes tools."""

import json
from mcp.server.fastmcp import FastMCP

from . import bear_db, bear_url, invoice, summary

mcp = FastMCP(
    "bear-mcp",
    instructions="Bear notes management: CRUD, search, invoice import, yearly summaries",
)


# ── bear-notes: read operations ──────────────────────────────────────────────


@mcp.tool()
def bear_read(title: str) -> str:
    """Read a Bear note's content by exact title."""
    content = bear_db.read_note(title)
    if content is None:
        return f"Note not found: {title}"
    return content


@mcp.tool()
def bear_search(query: str, limit: int = 20) -> str:
    """Search Bear notes by text content. Returns matching titles and snippets."""
    results = bear_db.search_notes(query, limit)
    if not results:
        return "No notes found."
    return json.dumps(results, ensure_ascii=False, indent=2)


@mcp.tool()
def bear_list_tag(tag: str) -> str:
    """List Bear note titles that have a specific tag (e.g. 'documents/work')."""
    titles = bear_db.list_notes_by_tag(tag)
    if not titles:
        return f"No notes found with tag: #{tag}"
    return "\n".join(titles)


@mcp.tool()
def bear_tags() -> str:
    """List all tags in Bear."""
    tags = bear_db.list_tags()
    if not tags:
        return "No tags found."
    return "\n".join(tags)


# ── bear-notes: write operations ─────────────────────────────────────────────


@mcp.tool()
def bear_create(title: str, body: str, tags: str | None = None) -> str:
    """Create a new Bear note.

    Args:
        title: Note title.
        body: Markdown body content.
        tags: Optional comma-separated tags without # (e.g. 'ai/claude/chats,documents/work').
    """
    bear_url.create_note(title, body, tags)
    return f"Created note: {title}"


@mcp.tool()
def bear_append(title: str, text: str) -> str:
    """Append text to an existing Bear note."""
    bear_url.append_text(title, text)
    return f"Appended to note: {title}"


@mcp.tool()
def bear_trash(title: str) -> str:
    """Trash a Bear note. Looks up UUID from the database first (never trashes by title directly)."""
    try:
        uuid = bear_url.trash_note(title)
        return f"Trashed note: {title} (UUID: {uuid})"
    except ValueError as e:
        return str(e)


# ── save-to-bear ─────────────────────────────────────────────────────────────


@mcp.tool()
def bear_save_chat(title: str, content: str, subtag: str | None = None) -> str:
    """Save content as a Bear note under #ai/claude/chats.

    Args:
        title: Note title.
        content: Markdown content to save.
        subtag: Optional subtag: devops, code, work, or howto.
    """
    bear_url.save_chat(title, content, subtag)
    tag_str = f"#ai/claude/chats/{subtag}" if subtag else "#ai/claude/chats"
    return f"Saved to Bear: {title} ({tag_str})"


# ── bear-invoice-importer ────────────────────────────────────────────────────


@mcp.tool()
def bear_import_invoice(pdf_path: str) -> str:
    """Import a single PDF invoice into Bear.

    Extracts metadata (contractor, date, netto/VAT/brutto), creates a Bear note
    with embedded PDF and summary, tagged #documents/work.

    Args:
        pdf_path: Path to the PDF file.
    """
    try:
        result = invoice.import_invoice(pdf_path)
        parts = [f"Imported: {result['title']}"]
        if result.get("contractor"):
            parts.append(f"  Contractor: {result['contractor']}")
        if result.get("netto") is not None:
            parts.append(f"  Netto: {invoice.fmt_amount(result['netto'])} PLN")
        if result.get("brutto") is not None:
            parts.append(f"  Brutto: {invoice.fmt_amount(result['brutto'])} PLN")
        return "\n".join(parts)
    except Exception as e:
        return f"Error importing invoice: {e}"


@mcp.tool()
def bear_import_invoices(directory: str | None = None) -> str:
    """Batch import all PDF invoices from a directory into Bear.

    Each PDF gets its own note with extracted metadata and embedded PDF.
    Default directory: ~/Downloads/firma/Faktury/

    Args:
        directory: Path to directory with PDFs. Uses default if not provided.
    """
    try:
        results = invoice.import_invoices(directory)
        if not results:
            return "No PDFs found in directory."
        lines = [f"Imported {len(results)} invoice(s):"]
        for r in results:
            netto_str = invoice.fmt_amount(r["netto"]) if r.get("netto") is not None else "?"
            lines.append(f"  - {r['title']} ({netto_str} PLN netto)")
        return "\n".join(lines)
    except Exception as e:
        return f"Error during batch import: {e}"


@mcp.tool()
def bear_generate_yearly_summary(year: int) -> str:
    """Generate a yearly invoice summary note in Bear with chart and table.

    Queries existing invoice notes from the Bear database, generates a matplotlib
    line chart (netto over months), and creates a summary note with the chart
    image and a markdown table. Tagged #documents/work.

    Args:
        year: The year to summarize (e.g. 2024).
    """
    try:
        result = summary.generate_yearly_summary(year)
        if result.get("error"):
            return result["error"]
        return (
            f"Generated summary for {year}:\n"
            f"  Invoices: {result['invoice_count']}\n"
            f"  Total netto: {result['total_netto']} PLN\n"
            f"  Total VAT: {result['total_vat']} PLN\n"
            f"  Total brutto: {result['total_brutto']} PLN"
        )
    except Exception as e:
        return f"Error generating summary: {e}"


@mcp.tool()
def bear_rebuild_summary(year: int) -> str:
    """Trash the existing yearly summary and regenerate from current invoice notes.

    Use this after importing new invoices to update the summary.

    Args:
        year: The year to rebuild (e.g. 2024).
    """
    try:
        result = summary.rebuild_summary(year)
        if result.get("error"):
            return result["error"]
        return (
            f"Rebuilt summary for {year}:\n"
            f"  Invoices: {result['invoice_count']}\n"
            f"  Total netto: {result['total_netto']} PLN\n"
            f"  Total VAT: {result['total_vat']} PLN\n"
            f"  Total brutto: {result['total_brutto']} PLN"
        )
    except Exception as e:
        return f"Error rebuilding summary: {e}"


# ── prompts ──────────────────────────────────────────────────────────────────


@mcp.prompt()
def weekly_review() -> str:
    """Review notes modified this week across work, projects, and tasks."""
    results = bear_db.search_notes("", limit=50)
    titles = [r["title"] for r in results]
    note_list = "\n".join(f"- {t}" for t in titles) if titles else "(no recent notes)"
    tags = bear_db.list_tags()
    tag_list = ", ".join(f"#{t}" for t in tags if t.startswith("work/")) if tags else "(none)"
    return (
        "Review my recent Bear notes and summarize what I worked on.\n\n"
        f"## Recently modified notes\n{note_list}\n\n"
        f"## Work tags\n{tag_list}\n\n"
        "Read the most relevant ones and give me a concise weekly summary. "
        "Group by theme. Highlight open tasks and action items."
    )


@mcp.prompt()
def work_tasks() -> str:
    """Show current work tasks and their status."""
    in_progress = bear_db.list_notes_by_tag("work/tasks/in-progress")
    done = bear_db.list_notes_by_tag("work/tasks/done")
    all_tasks = bear_db.list_notes_by_tag("work/tasks")
    # Pending = all tasks minus in-progress and done
    known = set(in_progress + done)
    pending = [t for t in all_tasks if t not in known]
    def fmt(notes: list[str]) -> str:
        return "\n".join(f"- {t}" for t in notes) if notes else "(none)"
    return (
        "Here are my current work tasks from Bear. "
        "Read the in-progress ones and summarize status.\n\n"
        f"## In Progress\n{fmt(in_progress)}\n\n"
        f"## Pending\n{fmt(pending)}\n\n"
        f"## Done\n{fmt(done)}"
    )


@mcp.prompt()
def invoice_status(year: str = "2026") -> str:
    """Check invoice status for a given year."""
    invoices = bear_db.get_invoice_notes(int(year))
    if not invoices:
        return f"No invoices found for {year}. Check if they've been imported."
    months_present = sorted(inv.get("month", 0) for inv in invoices)
    total_netto = sum(inv.get("netto", 0) for inv in invoices)
    all_months = set(range(1, 13))
    missing = sorted(all_months - set(months_present))
    missing_str = ", ".join(str(m).zfill(2) for m in missing) if missing else "none"
    return (
        f"Invoice status for {year}:\n\n"
        f"- **Imported:** {len(invoices)} invoices\n"
        f"- **Months present:** {', '.join(str(m).zfill(2) for m in months_present)}\n"
        f"- **Missing months:** {missing_str}\n"
        f"- **Total netto so far:** {total_netto:,.2f} PLN\n\n"
        "Should I import missing invoices or rebuild the yearly summary?"
    )


@mcp.prompt()
def save_this_chat(topic: str = "") -> str:
    """Save the current conversation to Bear."""
    return (
        "Summarize our conversation in clean markdown and save it to Bear "
        f"using bear_save_chat.{f' Topic: {topic}.' if topic else ''} "
        "Pick an appropriate title and subtag (devops, code, work, or howto)."
    )


def main():
    mcp.run()


if __name__ == "__main__":
    main()
