"""Yearly invoice summary generation with matplotlib charts."""

import base64
import io
import tempfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

from . import bear_db, bear_url
from .invoice import fmt_amount

BEAR_RED = (214 / 255, 76 / 255, 79 / 255)

POLISH_MONTHS_SHORT = [
    "Sty", "Lut", "Mar", "Kwi", "Maj", "Cze",
    "Lip", "Sie", "Wrz", "Paź", "Lis", "Gru",
]

POLISH_MONTHS_FULL = [
    "Styczeń", "Luty", "Marzec", "Kwiecień", "Maj", "Czerwiec",
    "Lipiec", "Sierpień", "Wrzesień", "Październik", "Listopad", "Grudzień",
]


def _generate_chart(invoices: list[dict], year: int) -> str:
    """Generate a netto line chart as base64-encoded PNG.

    Style: Bear red line with white-filled markers, area fill below.
    X-axis: Polish month abbreviations.
    Y-axis: formatted with space thousands separator.
    """
    # Sort by month, collect netto values
    sorted_inv = sorted(invoices, key=lambda x: x.get("month", 0))
    months = [inv.get("month", 0) for inv in sorted_inv]
    nettos = [inv.get("netto", 0) for inv in sorted_inv]

    fig, ax = plt.subplots(figsize=(10, 4))

    ax.plot(
        months,
        nettos,
        "o-",
        color=BEAR_RED,
        linewidth=2.5,
        markersize=8,
        markerfacecolor="white",
        markeredgewidth=2.5,
        markeredgecolor=BEAR_RED,
    )
    ax.fill_between(months, nettos, alpha=0.1, color=BEAR_RED)

    # Value labels above each point
    for m, n in zip(months, nettos):
        ax.annotate(
            fmt_amount(n),
            (m, n),
            textcoords="offset points",
            xytext=(0, 12),
            ha="center",
            fontsize=8,
        )

    # X-axis: Polish month abbreviations
    ax.set_xticks(months)
    ax.set_xticklabels([POLISH_MONTHS_SHORT[m - 1] for m in months])

    # Y-axis: space thousands separator
    ax.yaxis.set_major_formatter(
        ticker.FuncFormatter(lambda x, _: fmt_amount(x))
    )

    ax.set_title(f"Netto {year}", fontsize=14, fontweight="bold")
    ax.grid(axis="y", alpha=0.3)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


def _build_table(invoices: list[dict]) -> str:
    """Build a markdown summary table from invoice data."""
    sorted_inv = sorted(invoices, key=lambda x: x.get("month", 0))

    lines = [
        "| Miesiąc | Data | Netto | VAT | Brutto |",
        "|---------|------|------:|----:|-------:|",
    ]

    total_netto = 0.0
    total_vat = 0.0
    total_brutto = 0.0

    for inv in sorted_inv:
        month_idx = inv.get("month", 1) - 1
        month_name = POLISH_MONTHS_FULL[month_idx] if 0 <= month_idx < 12 else "?"
        date = inv.get("date", "—")
        netto = inv.get("netto", 0)
        vat = inv.get("vat", 0)
        brutto = inv.get("brutto", 0)

        total_netto += netto
        total_vat += vat
        total_brutto += brutto

        lines.append(
            f"| {month_name} | {date} "
            f"| {fmt_amount(netto)} PLN "
            f"| {fmt_amount(vat)} PLN "
            f"| {fmt_amount(brutto)} PLN |"
        )

    lines.append(
        f"| **RAZEM** | "
        f"| **{fmt_amount(total_netto)} PLN** "
        f"| **{fmt_amount(total_vat)} PLN** "
        f"| **{fmt_amount(total_brutto)} PLN** |"
    )

    return "\n".join(lines)


def generate_yearly_summary(year: int) -> dict:
    """Generate a yearly invoice summary note in Bear.

    Queries existing invoice notes from the DB, generates a matplotlib chart,
    and creates a two-step Bear note (chart first, then table appended).

    Returns dict with year, invoice_count, and totals.
    """
    invoices = bear_db.get_invoice_notes(year)
    if not invoices:
        return {"year": year, "invoice_count": 0, "error": "No invoices found"}

    title = f"ALM Services - podsumowanie {year}"

    # Generate chart
    chart_b64 = _generate_chart(invoices, year)

    # Step 1: Create note with chart image
    bear_url.create_note_with_file(
        title=title,
        tags="documents/work",
        file_b64=chart_b64,
        filename=f"netto_{year}.png",
    )
    bear_url.batch_sleep()

    # Step 2: Append table below chart
    table = _build_table(invoices)
    append_text = f"\n---\n{table}"
    bear_url.append_text(title, append_text)

    # Calculate totals
    total_netto = sum(inv.get("netto", 0) for inv in invoices)
    total_vat = sum(inv.get("vat", 0) for inv in invoices)
    total_brutto = sum(inv.get("brutto", 0) for inv in invoices)

    return {
        "year": year,
        "invoice_count": len(invoices),
        "total_netto": fmt_amount(total_netto),
        "total_vat": fmt_amount(total_vat),
        "total_brutto": fmt_amount(total_brutto),
    }


def rebuild_summary(year: int) -> dict:
    """Trash the existing yearly summary note and regenerate it.

    Returns the same dict as generate_yearly_summary.
    """
    title = f"ALM Services - podsumowanie {year}"

    # Try to trash the existing summary
    try:
        bear_url.trash_note(title)
        bear_url.batch_sleep()
    except ValueError:
        pass  # No existing summary, that's fine

    return generate_yearly_summary(year)
