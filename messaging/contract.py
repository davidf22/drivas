"""
Generates a mock employment contract PDF for a Drivas job engagement.
Returns the PDF as bytes so it can be attached to emails or served as a download.
"""
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.enums import TA_CENTER, TA_LEFT


def generate_contract_pdf(job) -> bytes:
    """
    Generate a mock employment contract PDF for the given JobEngagement.
    Returns raw PDF bytes.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2.5 * cm,
        leftMargin=2.5 * cm,
        topMargin=2.5 * cm,
        bottomMargin=2.5 * cm,
    )

    styles = getSampleStyleSheet()
    brand_red = colors.HexColor("#e94560")
    dark = colors.HexColor("#1a1a2e")

    title_style = ParagraphStyle(
        "Title",
        parent=styles["Normal"],
        fontSize=20,
        textColor=dark,
        fontName="Helvetica-Bold",
        alignment=TA_CENTER,
        spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        "Subtitle",
        parent=styles["Normal"],
        fontSize=11,
        textColor=brand_red,
        fontName="Helvetica-Bold",
        alignment=TA_CENTER,
        spaceAfter=2,
    )
    section_style = ParagraphStyle(
        "Section",
        parent=styles["Normal"],
        fontSize=11,
        textColor=dark,
        fontName="Helvetica-Bold",
        spaceBefore=14,
        spaceAfter=4,
    )
    body_style = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontSize=10,
        leading=16,
        textColor=colors.HexColor("#333333"),
    )
    small_style = ParagraphStyle(
        "Small",
        parent=styles["Normal"],
        fontSize=9,
        leading=14,
        textColor=colors.HexColor("#666666"),
    )
    sign_style = ParagraphStyle(
        "Sign",
        parent=styles["Normal"],
        fontSize=10,
        leading=18,
        textColor=dark,
    )

    client = job.client
    driver = job.driver
    rate_text = f"${job.agreed_rate}/month" if job.agreed_rate else "As agreed between parties"
    from django.utils.timezone import now
    today = now().strftime("%B %d, %Y")

    story = []

    # ── Header ──
    story.append(Paragraph("DRIVAS", title_style))
    story.append(Paragraph("Driver Employment Platform", subtitle_style))
    story.append(Spacer(1, 0.3 * cm))
    story.append(HRFlowable(width="100%", thickness=2, color=brand_red))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph("DRIVER EMPLOYMENT CONTRACT", ParagraphStyle(
        "ContractTitle", parent=styles["Normal"], fontSize=14,
        fontName="Helvetica-Bold", alignment=TA_CENTER, textColor=dark,
    )))
    story.append(Paragraph(f"Job Reference: #{job.id}", ParagraphStyle(
        "JobRef", parent=styles["Normal"], fontSize=10,
        alignment=TA_CENTER, textColor=colors.grey, spaceAfter=6,
    )))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey))
    story.append(Spacer(1, 0.4 * cm))

    # ── Parties ──
    story.append(Paragraph("1. PARTIES", section_style))
    story.append(Paragraph(
        f"This contract is entered into on <b>{today}</b> between:", body_style
    ))
    story.append(Spacer(1, 0.2 * cm))

    party_data = [
        ["", "CLIENT", "DRIVER"],
        ["Name", client.get_full_name() or client.username,
         driver.get_full_name() if driver else "—"],
        ["Email", client.email or "—", driver.email if driver else "—"],
        ["Phone", str(client.phone) if client.phone else "—",
         str(driver.phone) if driver and driver.phone else "—"],
    ]
    party_table = Table(party_data, colWidths=[3.5 * cm, 7 * cm, 7 * cm])
    party_table.setStyle(TableStyle([
        ("BACKGROUND", (1, 0), (1, 0), dark),
        ("BACKGROUND", (2, 0), (2, 0), brand_red),
        ("TEXTCOLOR", (1, 0), (2, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("PADDING", (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f9f9f9"), colors.white]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
        ("ROUNDEDCORNERS", [4, 4, 4, 4]),
    ]))
    story.append(party_table)

    # ── Job Details ──
    story.append(Paragraph("2. JOB DETAILS", section_style))
    job_data = [
        ["Employment Type", job.get_employment_type_display()],
        ["Work Location", job.work_location],
        ["Requirements", job.requirements or "As discussed"],
        ["Agreed Rate", rate_text],
        ["Start Date", job.hired_at.strftime("%B %d, %Y") if job.hired_at else today],
    ]
    job_table = Table(job_data, colWidths=[5 * cm, 12.5 * cm])
    job_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("PADDING", (0, 0), (-1, -1), 7),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.HexColor("#f9f9f9"), colors.white]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
    ]))
    story.append(job_table)

    # ── Terms ──
    story.append(Paragraph("3. TERMS & CONDITIONS", section_style))
    terms = [
        "The Driver agrees to operate the Client's vehicle professionally and safely at all times.",
        "The Driver does not supply a vehicle — the Client provides the vehicle for all engagements.",
        "The Driver shall maintain a valid driver's licence throughout the duration of this contract.",
        "Either party may terminate this contract with 24 hours written notice via the Drivas platform.",
        "The Client agrees to pay the agreed rate promptly upon completion of each engagement.",
        "Drivas acts as an intermediary platform and is not liable for disputes between parties.",
        "Both parties agree to treat each other with professionalism and respect.",
        "This is a mock contract for demonstration purposes. Seek legal advice before signing legally binding agreements.",
    ]
    for i, term in enumerate(terms, 1):
        story.append(Paragraph(f"{i}. {term}", body_style))
        story.append(Spacer(1, 0.1 * cm))

    # ── Signatures ──
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph("4. SIGNATURES", section_style))
    story.append(Paragraph(
        "By signing below, both parties agree to the terms of this contract.", body_style
    ))
    story.append(Spacer(1, 0.6 * cm))

    sig_data = [
        ["CLIENT SIGNATURE", "", "DRIVER SIGNATURE", ""],
        ["", "", "", ""],
        ["", "", "", ""],
        ["_________________________", "", "_________________________", ""],
        [client.get_full_name() or client.username, "", driver.get_full_name() if driver else "—", ""],
        ["Date: ___________________", "", "Date: ___________________", ""],
    ]
    sig_table = Table(sig_data, colWidths=[7.5 * cm, 0.5 * cm, 7.5 * cm, 0.5 * cm])
    sig_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, 0), dark),
        ("TEXTCOLOR", (2, 0), (2, 0), brand_red),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(sig_table)

    # ── Footer ──
    story.append(Spacer(1, 0.6 * cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph(
        "This document was generated by Drivas — Driver Employment Platform. "
        "For support contact: fayankindavid@gmail.com",
        small_style,
    ))

    doc.build(story)
    return buffer.getvalue()
