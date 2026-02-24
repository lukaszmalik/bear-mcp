# bear-mcp

MCP server for Bear notes on macOS. Provides tools for note management, invoice import, and yearly summaries.

## Tools

### Notes (CRUD)
- `bear_read(title)` — read note by title
- `bear_search(query, limit?)` — search notes by content
- `bear_list_tag(tag)` — list notes with a tag
- `bear_tags()` — list all tags
- `bear_create(title, body, tags?)` — create a note
- `bear_append(title, text)` — append to a note
- `bear_trash(title)` — trash by UUID lookup

### Save Chat
- `bear_save_chat(title, content, subtag?)` — save under `#ai/claude/chats`

### Invoices
- `bear_import_invoice(pdf_path)` — import single PDF invoice
- `bear_import_invoices(directory?)` — batch import from directory
- `bear_generate_yearly_summary(year)` — create summary with chart + table
- `bear_rebuild_summary(year)` — trash old summary and regenerate

## Setup

```bash
cd ~/Projects/bear-mcp
uv venv && uv pip install -e .
claude mcp add --scope user bear-mcp -- ~/Projects/bear-mcp/.venv/bin/python -m bear_mcp.server
```
