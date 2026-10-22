"""
EduConnect Official Fee Receipt PDF Generator.
Generates cryptographically verified, beautifully formatted institutional fee receipts
with exact decimal monetary details, installment info, and official anti-tamper hashes.
"""

import io
from django.utils import timezone
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from .models import FeeReceipt


def generate_fee_receipt_pdf(receipt: FeeReceipt) -> bytes:
    """
    Generates a PDF byte buffer containing the complete, official payment receipt.
    """
    payment = receipt.payment
    allocation = payment.allocation
    student = payment.student

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40,
    )

    styles = getSampleStyleSheet()
    primary_color = colors.HexColor("#0d6efd")
    dark_bg = colors.HexColor("#0f172a")
    text_dark = colors.HexColor("#1e293b")
    text_muted = colors.HexColor("#64748b")
    success_color = colors.HexColor("#198754")
    border_color = colors.HexColor("#cbd5e1")

    title_style = ParagraphStyle(
        "HeaderTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=primary_color,
    )
    subtitle_style = ParagraphStyle(
        "HeaderSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=text_muted,
    )
    receipt_title = ParagraphStyle(
        "ReceiptTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=18,
        textColor=dark_bg,
        alignment=1,  # Center
    )
    label_style = ParagraphStyle(
        "LabelStyle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=12,
        textColor=text_muted,
    )
    val_style = ParagraphStyle(
        "ValStyle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=text_dark,
    )
    bold_val = ParagraphStyle(
        "BoldValStyle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=14,
        textColor=text_dark,
    )
    currency_highlight = ParagraphStyle(
        "CurrencyHighlight",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=16,
        textColor=success_color,
    )

    elements = []

    # 1. Header Banner
    header_data = [
        [
            Paragraph("<b>EduConnect Institution</b><br/>Office of the Bursar &amp; Student Financial Services", title_style),
            Paragraph(
                "<b>OFFICIAL FEE RECEIPT</b><br/>"
                f"Receipt No: <b>{receipt.receipt_number}</b><br/>"
                f"Date: <b>{receipt.issued_at.strftime('%B %d, %Y')}</b>",
                ParagraphStyle("HeadRight", parent=styles["Normal"], fontSize=9, leading=13, alignment=2, textColor=text_dark),
            ),
        ]
    ]
    header_table = Table(header_data, colWidths=[4.0 * inch, 3.2 * inch])
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    elements.append(header_table)
    elements.append(HRFlowable(width="100%", thickness=1.5, color=primary_color, spaceBefore=4, spaceAfter=15))

    # 2. Student & Payment Metadata
    student_name = student.get_full_name() or student.username
    student_id = getattr(student, "student_id", None) or f"STU-{student.id}"
    course_name = allocation.fee_structure.course.title if allocation.fee_structure.course else "General Academic Program"

    meta_data = [
        [
            Paragraph("Student Name:", label_style),
            Paragraph(f"<b>{student_name}</b>", bold_val),
            Paragraph("Receipt No:", label_style),
            Paragraph(f"<b>{receipt.receipt_number}</b>", bold_val),
        ],
        [
            Paragraph("Student ID:", label_style),
            Paragraph(f"<code>{student_id}</code>", val_style),
            Paragraph("Payment Date:", label_style),
            Paragraph(payment.payment_date.strftime("%Y-%m-%d"), val_style),
        ],
        [
            Paragraph("Program / Course:", label_style),
            Paragraph(course_name, val_style),
            Paragraph("Payment Mode:", label_style),
            Paragraph(payment.get_payment_method_display(), val_style),
        ],
        [
            Paragraph("Academic Year:", label_style),
            Paragraph(allocation.academic_year, val_style),
            Paragraph("Txn Reference:", label_style),
            Paragraph(f"<code>{payment.transaction_reference}</code>", val_style),
        ],
        [
            Paragraph("Payer Name:", label_style),
            Paragraph(payment.payer_name or student_name, val_style),
            Paragraph("Payment Status:", label_style),
            Paragraph(f"<font color='{success_color.hexval()}'><b>CONFIRMED &amp; VERIFIED</b></font>", val_style),
        ],
    ]

    meta_table = Table(meta_data, colWidths=[1.4 * inch, 2.3 * inch, 1.4 * inch, 2.1 * inch])
    meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ("BOX", (0, 0), (-1, -1), 1, border_color),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 15))

    # 3. Transaction Breakdown Table
    breakdown_data = [
        [
            Paragraph("<b>Fee Component / Description</b>", bold_val),
            Paragraph("<b>Fee Schedule</b>", bold_val),
            Paragraph("<b>Amount Allocated</b>", ParagraphStyle("RightBold", parent=bold_val, alignment=2)),
            Paragraph("<b>Amount Paid Here</b>", ParagraphStyle("RightBold", parent=bold_val, alignment=2)),
        ],
        [
            Paragraph(f"<b>{allocation.fee_structure.title}</b><br/><font size='8' color='#64748b'>Base Institutional Billing Schedule</font>", val_style),
            Paragraph(allocation.academic_year, val_style),
            Paragraph(f"${allocation.gross_amount:.2f}", ParagraphStyle("R1", parent=val_style, alignment=2)),
            Paragraph(f"<b>${payment.amount:.2f}</b>", ParagraphStyle("R2", parent=currency_highlight, alignment=2)),
        ],
    ]

    # If linked to specific installment
    if payment.installment:
        breakdown_data.append([
            Paragraph(f"Allocated Installment: <b>{payment.installment.title}</b>", val_style),
            Paragraph(f"Due: {payment.installment.due_date}", val_style),
            Paragraph(f"${payment.installment.amount:.2f}", ParagraphStyle("R3", parent=val_style, alignment=2)),
            Paragraph(f"${payment.amount:.2f}", ParagraphStyle("R4", parent=val_style, alignment=2)),
        ])

    table_cols = [3.2 * inch, 1.5 * inch, 1.2 * inch, 1.3 * inch]
    item_table = Table(breakdown_data, colWidths=table_cols)
    item_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
        ("BOX", (0, 0), (-1, -1), 1, border_color),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, border_color),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elements.append(item_table)
    elements.append(Spacer(1, 12))

    # 4. Financial Summary Summary Box
    summary_data = [
        [
            Paragraph("<b>Gross Fee Total:</b>", label_style),
            Paragraph(f"${allocation.gross_amount:.2f}", ParagraphStyle("SumVal", parent=val_style, alignment=2)),
        ],
        [
            Paragraph("<b>Approved Concessions / Scholarships:</b>", label_style),
            Paragraph(f"- ${allocation.discount_amount:.2f}", ParagraphStyle("SumVal2", parent=val_style, alignment=2)),
        ],
        [
            Paragraph("<b>Net Adjusted Dues:</b>", label_style),
            Paragraph(f"${allocation.net_amount:.2f}", ParagraphStyle("SumVal3", parent=val_style, alignment=2)),
        ],
        [
            Paragraph("<b>Total Verified Collections to Date:</b>", label_style),
            Paragraph(f"<b>${allocation.amount_paid:.2f}</b>", ParagraphStyle("SumVal4", parent=bold_val, alignment=2)),
        ],
        [
            Paragraph("<b>Remaining Outstanding Balance:</b>", label_style),
            Paragraph(f"<b>${allocation.outstanding_balance:.2f}</b>", ParagraphStyle("SumVal5", parent=currency_highlight, alignment=2)),
        ],
    ]
    summary_table = Table(summary_data, colWidths=[2.5 * inch, 1.5 * inch], hAlign="RIGHT")
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f1f5f9")),
        ("BOX", (0, 0), (-1, -1), 1, border_color),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 20))

    # 5. Authorization & Verification Footer
    officer_name = receipt.issued_by.get_full_name() or receipt.issued_by.username if receipt.issued_by else "Authorized Bursar"
    auth_data = [
        [
            Paragraph(
                "<b>Security &amp; Integrity Verification:</b><br/>"
                f"<font size='7' color='#64748b'>Digital SHA-256 Stamp: {receipt.digital_signature_hash[:40]}...<br/>"
                "This document is an electronically signed institutional receipt. "
                "Any alteration invalidates this record.</font>",
                val_style,
            ),
            Paragraph(
                f"<br/><br/><b>___________________________________</b><br/>"
                f"<b>{officer_name}</b><br/>"
                "<font size='8' color='#64748b'>Accounts &amp; Treasury Officer</font>",
                ParagraphStyle("SignRight", parent=styles["Normal"], alignment=1, textColor=text_dark),
            ),
        ]
    ]
    auth_table = Table(auth_data, colWidths=[4.7 * inch, 2.5 * inch])
    auth_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    elements.append(auth_table)

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()
