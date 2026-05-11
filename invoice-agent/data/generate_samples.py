"""Generate 5 sample PDF invoices for testing and benchmarking.

Run from invoice-agent/: python data/generate_samples.py
"""
from __future__ import annotations
import os
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
)
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

W, H = A4
styles = getSampleStyleSheet()
OUT = os.path.join(os.path.dirname(__file__), "sample_invoices")


def _build_invoice(
    filename: str,
    vendor: str,
    invoice_number: str,
    date: str,
    due_date: str,
    po_number: str | None,
    line_items: list[tuple[str, float]],
    total: float,
    note: str = "",
) -> None:
    path = os.path.join(OUT, filename)
    doc = SimpleDocTemplate(path, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    story = []

    story.append(Paragraph(f"<b>INVOICE</b>", styles["Title"]))
    story.append(Spacer(1, 0.4*cm))

    meta = [
        ["Vendor:", vendor],
        ["Invoice #:", invoice_number],
        ["Invoice Date:", date],
        ["Due Date:", due_date],
        ["PO Number:", po_number or "N/A"],
    ]
    meta_table = Table(meta, colWidths=[4*cm, 12*cm])
    meta_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 0.6*cm))

    story.append(Paragraph("<b>Line Items</b>", styles["Heading2"]))
    header = [["Description", "Amount (USD)"]]
    rows = [[desc, f"${amount:,.2f}"] for desc, amount in line_items]
    footer = [["", f"<b>Total: ${total:,.2f}</b>"]]
    line_table = Table(header + rows + footer, colWidths=[13*cm, 4*cm])
    line_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.whitesmoke, colors.white]),
        ("GRID", (0, 0), (-1, -2), 0.5, colors.lightgrey),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("LINEABOVE", (0, -1), (-1, -1), 1, colors.black),
    ]))
    story.append(line_table)

    if note:
        story.append(Spacer(1, 0.5*cm))
        story.append(Paragraph(f"<i>Note: {note}</i>", styles["Normal"]))

    story.append(Spacer(1, 1*cm))
    story.append(Paragraph(
        "Payment terms: Net 30. Bank transfer to Account #: 12-3456-789.",
        styles["Normal"]
    ))

    doc.build(story)
    print(f"Created: {path}")


def main():
    os.makedirs(OUT, exist_ok=True)

    # 1. Clean invoice with PO — no flags expected
    _build_invoice(
        filename="INV001_clean.pdf",
        vendor="Acme Supplies Ltd",
        invoice_number="INV-2024-001",
        date="2024-03-12",
        due_date="2024-04-12",
        po_number="PO-2024-100",
        line_items=[
            ("Office chairs x5", 1000.00),
            ("Ergonomic keyboards x10", 450.00),
            ("Delivery & handling", 50.00),
        ],
        total=1500.00,
        note="Thank you for your business.",
    )

    # 2. Missing PO number — MISSING_PO flag
    _build_invoice(
        filename="INV002_missing_po.pdf",
        vendor="TechGear Direct",
        invoice_number="INV-TG-0042",
        date="2024-03-14",
        due_date="2024-04-14",
        po_number=None,
        line_items=[
            ("Laptop stand x3", 225.00),
            ("USB-C hubs x3", 135.00),
        ],
        total=360.00,
        note="PO to be confirmed.",
    )

    # 3. Over threshold, missing PO — AMOUNT_THRESHOLD + MISSING_PO flags
    _build_invoice(
        filename="INV003_over_threshold_no_po.pdf",
        vendor="Enterprise Fixtures Co",
        invoice_number="EFC-20240315",
        date="2024-03-15",
        due_date="2024-04-15",
        po_number=None,
        line_items=[
            ("Standing desks x10", 6500.00),
            ("Monitor arms x10", 1200.00),
            ("Cable management kits x10", 300.00),
            ("White-glove delivery", 400.00),
        ],
        total=8400.00,
    )

    # 4. Line item mismatch — LINE_ITEM_MISMATCH flag
    _build_invoice(
        filename="INV004_line_item_mismatch.pdf",
        vendor="Stationery World",
        invoice_number="SW-INV-0091",
        date="2024-03-18",
        due_date="2024-04-18",
        po_number="PO-2024-205",
        line_items=[
            ("A4 paper reams x20", 160.00),
            ("Ballpoint pens x100", 45.00),
            ("Sticky notes x50 packs", 75.00),
        ],
        total=295.00,  # actual sum = 280.00 → mismatch
    )

    # 5. Duplicate of invoice 2 (same vendor + amount within 30 days)
    _build_invoice(
        filename="INV005_duplicate_of_inv002.pdf",
        vendor="TechGear Direct",
        invoice_number="INV-TG-0043",
        date="2024-03-20",
        due_date="2024-04-20",
        po_number=None,
        line_items=[
            ("Laptop stand x3", 225.00),
            ("USB-C hubs x3", 135.00),
        ],
        total=360.00,
        note="Re-issued — original lost in transit.",
    )


if __name__ == "__main__":
    main()
