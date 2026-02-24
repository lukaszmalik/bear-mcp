"""PDF invoice parsing and import into Bear notes."""

import base64
import os
import re
from pathlib import Path

import pdfplumber

from . import bear_url

# Default invoice directory
INVOICE_DIR = os.path.expanduser("~/Downloads/firma/Faktury/")

# User's NIP for column detection
USER_NIP = "5213262293"


def _parse_title_from_filename(fname: str) -> str:
    """Convert filename to Bear note title.

    'Malik_01.2025.pdf' → 'Faktura 01/2025'
    Fallback: replace underscores with spaces, strip extension.
    """
    m = re.match(r"Malik_(\d{2})\.(\d{4})", fname)
    if m:
        return f"Faktura {m.group(1)}/{m.group(2)}"
    return Path(fname).stem.replace("_", " ")


def _extract_metadata(pdf_path: str) -> dict:
    """Extract invoice metadata from a PDF using pdfplumber.

    Handles two-column Polish invoices (Sprzedawca | Nabywca layout)
    and single-column invoices.

    Returns dict with keys: contractor, date, netto, vat, brutto.
    """
    result = {
        "contractor": None,
        "date": None,
        "netto": None,
        "vat": None,
        "brutto": None,
    }

    with pdfplumber.open(pdf_path) as pdf:
        if not pdf.pages:
            return result

        page = pdf.pages[0]
        words = page.extract_words()
        full_text = page.extract_text() or ""
        mid_x = page.width / 2

        # Determine layout: find user NIP position
        malik_on_left = False
        for w in words:
            if USER_NIP in w["text"]:
                malik_on_left = w["x0"] < mid_x
                break

        # Extract contractor from opposite column
        contractor = _extract_contractor(words, mid_x, malik_on_left, full_text)
        if contractor:
            result["contractor"] = contractor

        # Extract date
        date_match = re.search(
            r"(?:Data wystawienia|Data sprzeda.y)[:\s]*(\d{2}[./]\d{2}[./]\d{4})",
            full_text,
        )
        if date_match:
            result["date"] = date_match.group(1)

        # Extract amounts from RAZEM line or DO ZAPŁATY
        amounts = _extract_amounts(full_text)
        result.update(amounts)

    return result


def _extract_contractor(
    words: list[dict],
    mid_x: float,
    malik_on_left: bool,
    full_text: str,
) -> str | None:
    """Extract contractor name from the opposite column of the user's info."""
    # Determine which header to look for in which column
    if malik_on_left:
        # User is seller (left), contractor is buyer (right)
        target_header = "Nabywca"
        col_filter = lambda w: w["x0"] > mid_x - 20
    else:
        # User is buyer (right), contractor is seller (left)
        target_header = "Sprzedawca"
        col_filter = lambda w: w["x0"] < mid_x + 20

    col_words = [w for w in words if col_filter(w)]

    # Sort by vertical position
    col_words.sort(key=lambda w: (w["top"], w["x0"]))

    # Find header position
    header_idx = None
    for i, w in enumerate(col_words):
        if target_header in w["text"]:
            header_idx = i
            break

    if header_idx is None:
        # Fallback: try regex on full text
        m = re.search(r"(?:Nabywca|Sprzedawca)[:\s]*\n?(.+?)(?:\n|NIP)", full_text)
        return m.group(1).strip() if m else None

    # Collect words between header and NIP marker
    name_parts = []
    for w in col_words[header_idx + 1 :]:
        text = w["text"].strip()
        if "NIP" in text:
            break
        # Skip address patterns: postal codes, common street prefixes
        if re.match(r"\d{2}-\d{3}", text):
            break
        if text.lower().startswith(("ul.", "ul ", "al.", "al ")):
            break
        if text:
            name_parts.append(text)

    return " ".join(name_parts).strip() or None


def _extract_amounts(text: str) -> dict:
    """Extract netto, VAT, brutto amounts from invoice text."""
    result = {}

    # Try RAZEM line first: "RAZEM ... netto ... vat ... brutto"
    razem = re.search(
        r"RAZEM\s+([\d\s,]+\d{2})\s+([\d\s,]+\d{2})\s+([\d\s,]+\d{2})",
        text,
    )
    if razem:
        result["netto"] = _parse_amount(razem.group(1))
        result["vat"] = _parse_amount(razem.group(2))
        result["brutto"] = _parse_amount(razem.group(3))
        return result

    # Fallback: DO ZAPŁATY line
    zaplaty = re.search(r"DO ZAP.ATY[:\s]*([\d\s,]+\d{2})\s*PLN", text)
    if zaplaty:
        result["brutto"] = _parse_amount(zaplaty.group(1))

    # Try individual field patterns
    for field, label in [("netto", "Netto"), ("vat", "VAT"), ("brutto", "Brutto")]:
        if field not in result:
            m = re.search(rf"{label}[:\s]*([\d\s,]+\d{{2}})", text)
            if m:
                result[field] = _parse_amount(m.group(1))

    return result


def _parse_amount(s: str) -> float:
    """Parse Polish-formatted amount to float: '28 037,01' → 28037.01"""
    return float(s.replace("\u00a0", "").replace(" ", "").replace(",", "."))


def fmt_amount(v: float) -> str:
    """Format float as Polish number: 28037.01 → '28 037,01'"""
    s = f"{v:,.2f}"
    return s.replace(",", " ").replace(".", ",")


def import_invoice(pdf_path: str) -> dict:
    """Import a single PDF invoice into Bear.

    Creates a Bear note with:
    - Title derived from filename
    - Extracted metadata summary
    - Embedded PDF attachment
    - Tagged #documents/work

    Returns dict with title and extracted metadata.
    """
    pdf_path = os.path.expanduser(pdf_path)
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    fname = os.path.basename(pdf_path)
    title = _parse_title_from_filename(fname)

    # Extract metadata
    meta = _extract_metadata(pdf_path)

    # Build summary lines
    summary_lines = []
    if meta["contractor"]:
        summary_lines.append(f"**Kontrahent:** {meta['contractor']}")
    if meta["date"]:
        summary_lines.append(f"**Data wystawienia:** {meta['date']}")
    if meta["netto"] is not None:
        summary_lines.append(f"**Netto:** {fmt_amount(meta['netto'])} PLN")
    if meta["vat"] is not None:
        summary_lines.append(f"**VAT:** {fmt_amount(meta['vat'])} PLN")
    if meta["brutto"] is not None:
        summary_lines.append(f"**Brutto:** {fmt_amount(meta['brutto'])} PLN")

    body = "\n" + "\n".join(summary_lines) + "\n\n---\n"

    # Base64 encode the PDF
    with open(pdf_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")

    # Create Bear note with embedded PDF
    bear_url.create_note_with_file(
        title=title,
        tags="documents/work",
        file_b64=b64,
        filename=fname,
        body=body,
    )

    return {"title": title, **meta}


def import_invoices(directory: str | None = None) -> list[dict]:
    """Batch import all PDF invoices from a directory.

    Args:
        directory: Path to directory with PDFs. Defaults to ~/Downloads/firma/Faktury/.

    Returns list of dicts with title and metadata for each imported invoice.
    """
    directory = os.path.expanduser(directory or INVOICE_DIR)
    if not os.path.isdir(directory):
        raise FileNotFoundError(f"Directory not found: {directory}")

    pdfs = sorted(Path(directory).glob("*.pdf"))
    if not pdfs:
        return []

    results = []
    for pdf_path in pdfs:
        result = import_invoice(str(pdf_path))
        results.append(result)
        bear_url.batch_sleep()

    return results
