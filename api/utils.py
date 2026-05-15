"""
DeliverPro — Utilitaires : Audit Log + Génération PDF
"""
from io import BytesIO
from decimal import Decimal
from datetime import date, datetime

from .models import AuditLog


def log_action(user, action, table_name='', record_id=None, details=None, ip=None):
    """Enregistre une action dans le journal d'audit."""
    try:
        AuditLog.objects.create(
            user=user,
            action=action,
            table_name=table_name,
            record_id=record_id,
            details=details,
            ip_address=ip,
        )
    except Exception:
        pass  # Ne jamais bloquer l'action principale pour un log


def generate_pdf_report(
    transactions, type_export='transactions', date_debut=None, date_fin=None, signature_nom="Admin"
):
    """
    Génère un rapport PDF avec ReportLab.
    Retourne les bytes du PDF.
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph,
        Spacer, HRFlowable,
    )
    from reportlab.lib.enums import TA_CENTER

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.5*cm, leftMargin=1.5*cm,
        topMargin=2*cm, bottomMargin=2*cm,
    )

    styles = getSampleStyleSheet()
    ORANGE = colors.HexColor('#f97316')
    DARK   = colors.HexColor('#111318')
    GRAY   = colors.HexColor('#64748b')
    GREEN  = colors.HexColor('#22c55e')
    RED    = colors.HexColor('#ef4444')

    title_style = ParagraphStyle(
        'title',
        fontSize=22,
        leading=28,
        textColor=ORANGE,
        fontName='Helvetica-Bold',
        spaceAfter=8,
    )
    subtitle_style = ParagraphStyle(
        'subtitle',
        fontSize=10,
        leading=14,
        textColor=GRAY,
        spaceAfter=18,
    )
    section_style = ParagraphStyle('section', fontSize=13, textColor=DARK, fontName='Helvetica-Bold', spaceBefore=16, spaceAfter=8)
    normal_style = ParagraphStyle('normal', fontSize=9, textColor=DARK)

    elements = []

    transactions = list(transactions)

    # ── En-tête ──────────────────────────────────────────────────────────────
    def format_report_date(value):
        if not value:
            return ''
        if isinstance(value, datetime):
            parsed = value.date()
        elif isinstance(value, date):
            parsed = value
        else:
            try:
                parsed = date.fromisoformat(str(value)[:10])
            except ValueError:
                return str(value)
        return parsed.strftime('%d/%m/%Y')

    elements.append(Paragraph("DeliverPro Finance — Rapport", title_style))
    if date_debut and date_fin:
        period_str = f"Période du {format_report_date(date_debut)} au {format_report_date(date_fin)}"
    else:
        period_str = f"Généré le {format_report_date(date.today())}"
    elements.append(Paragraph(period_str, subtitle_style))
    elements.append(HRFlowable(width="100%", thickness=2, color=ORANGE, spaceAfter=16))

    # ── Résumé financier ─────────────────────────────────────────────────────
    revenus  = sum((t.montant for t in transactions if t.type == 'revenu'),  Decimal('0'))
    depenses = sum((t.montant for t in transactions if t.type == 'depense'), Decimal('0'))
    benefice = revenus - depenses
    marge = (benefice / revenus * 100) if revenus else Decimal('0')

    elements.append(Paragraph("RÉSUMÉ FINANCIER", section_style))
    summary_data = [
        ["Indicateur",        "Valeur"],
        ["Revenus totaux",  f"{revenus:.2f} MGA"],
        ["Dépenses totales", f"{depenses:.2f} MGA"],
        ["Bénéfice net",    f"{benefice:.2f} MGA"],
        ["Marge nette",        f"{marge:.2f} %"],
        ["Nb. transactions",   str(len(transactions))],
    ]
    summary_table = Table(summary_data, colWidths=[10*cm, 6*cm])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND',   (0, 0), (-1, 0),  ORANGE),
        ('TEXTCOLOR',    (0, 0), (-1, 0),  colors.white),
        ('FONTNAME',     (0, 0), (-1, 0),  'Helvetica-Bold'),
        ('FONTSIZE',     (0, 0), (-1, -1), 9),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#f8fafc'), colors.white]),
        ('GRID',         (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('PADDING',      (0, 0), (-1, -1), 8),
        ('TEXTCOLOR',    (1, 3), (1, 3), GREEN if benefice >= 0 else RED),
        ('FONTNAME',     (1, 3), (1, 3), 'Helvetica-Bold'),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 0.5*cm))

    # ── Transactions ──────────────────────────────────────────────────────────
    if type_export in ('transactions', 'complet', 'finance'):
        elements.append(Paragraph("JOURNAL DES TRANSACTIONS", section_style))
        txn_data = [["#", "Type", "Catégorie", "Libellé", "Entreprise", "Montant", "Date"]]
        for t in transactions:
            ent_nom = t.entreprise.nom if t.entreprise else 'Général'
            txn_data.append([
                str(t.id),
                t.type.capitalize(),
                t.categorie[:16],
                t.label[:28],
                ent_nom[:18],
                f"{'+' if t.type == 'revenu' else '-'}{t.montant:.2f} MGA",
                format_report_date(t.date),
            ])

        txn_table = Table(txn_data, colWidths=[1*cm, 2*cm, 2.5*cm, 4.2*cm, 3*cm, 2.8*cm, 2.3*cm])
        txn_table.setStyle(TableStyle([
            ('BACKGROUND',   (0, 0), (-1, 0),  ORANGE),
            ('TEXTCOLOR',    (0, 0), (-1, 0),  colors.white),
            ('FONTNAME',     (0, 0), (-1, 0),  'Helvetica-Bold'),
            ('FONTSIZE',     (0, 0), (-1, -1), 7.5),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#f8fafc'), colors.white]),
            ('GRID',         (0, 0), (-1, -1), 0.3, colors.HexColor('#e2e8f0')),
            ('PADDING',      (0, 0), (-1, -1), 5),
        ]))
        elements.append(txn_table)

    # ── Pied de page ─────────────────────────────────────────────────────────
    elements.append(Spacer(1, 0.8*cm))
    signature_data = [
        [f"Signature automatique: {signature_nom}", f"Date: {date.today()}"],
    ]
    signature_table = Table(signature_data, colWidths=[10*cm, 6*cm])
    signature_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('LINEABOVE', (0, 0), (-1, 0), 0.8, colors.HexColor('#cbd5e1')),
        ('PADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(signature_table)

    elements.append(Spacer(1, 1*cm))
    elements.append(HRFlowable(width="100%", thickness=1, color=GRAY))
    elements.append(Spacer(1, 0.2*cm))
    footer = ParagraphStyle('footer', fontSize=8, textColor=GRAY, alignment=TA_CENTER)
    elements.append(Paragraph(
        f"DeliverPro — Rapport généré le {date.today()} — Confidentiel",
        footer
    ))

    doc.build(elements)
    return buffer.getvalue()
