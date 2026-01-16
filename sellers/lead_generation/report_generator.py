"""
Aerial Leads - PDF Report Generator

Generates professional PDF reports for individual leads
Perfect for selling premium Tier 1 leads at $100+ each
"""

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Image, HRFlowable
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from datetime import datetime
from pathlib import Path
from typing import Dict

from shared.config.settings import REPORTS_DIR, APP_NAME, COMPANY_NAME
from shared.config.logging_config import log_success, get_logger


class InvestorReportGenerator:
    """
    Generate professional PDF investor reports

    Each report includes:
    - Property overview
    - Motivation score breakdown
    - Financial analysis
    - Contact information
    - Recommended strategy
    """

    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _setup_custom_styles(self):
        """Create custom paragraph styles"""

        # Title style
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1e40af'),
            spaceAfter=30,
            alignment=TA_CENTER
        ))

        # Section header
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Heading2'],
            fontSize=16,
            textColor=colors.HexColor('#1e40af'),
            spaceBefore=20,
            spaceAfter=12,
            borderWidth=1,
            borderColor=colors.HexColor('#1e40af'),
            borderPadding=5
        ))

        # Highlight box
        self.styles.add(ParagraphStyle(
            name='HighlightBox',
            parent=self.styles['Normal'],
            fontSize=14,
            textColor=colors.HexColor('#15803d'),
            backColor=colors.HexColor('#f0fdf4'),
            borderWidth=1,
            borderColor=colors.HexColor('#15803d'),
            borderPadding=10,
            spaceBefore=10,
            spaceAfter=10
        ))

    def generate_report(self, lead_data: Dict, output_filename: str = None) -> str:
        """
        Generate PDF report for a lead

        Args:
            lead_data: Dictionary with lead information
            output_filename: Optional custom filename

        Returns:
            Path to generated PDF
        """
        # Generate filename if not provided
        if not output_filename:
            address_safe = lead_data['address'].replace(' ', '_').replace(',', '')
            output_filename = f"lead_report_{address_safe}_{datetime.now().strftime('%Y%m%d')}.pdf"

        # Ensure reports directory exists
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)

        output_path = REPORTS_DIR / output_filename

        # Create PDF
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=letter,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=18
        )

        # Build content
        story = []

        # Header
        story.extend(self._build_header(lead_data))

        # Executive Summary
        story.extend(self._build_executive_summary(lead_data))

        # Property Details
        story.extend(self._build_property_details(lead_data))

        # Motivation Analysis
        story.extend(self._build_motivation_analysis(lead_data))

        # Financial Overview
        story.extend(self._build_financial_overview(lead_data))

        # Contact Information
        story.extend(self._build_contact_info(lead_data))

        # Investment Strategy
        story.extend(self._build_strategy(lead_data))

        # Footer
        story.extend(self._build_footer())

        # Generate PDF
        doc.build(story)

        log_success(f"Generated PDF report: {output_path}")
        return str(output_path)

    def _build_header(self, lead_data: Dict) -> list:
        """Build report header"""
        elements = []

        # Title
        title = Paragraph(
            f"{APP_NAME}<br/>INVESTMENT OPPORTUNITY REPORT",
            self.styles['CustomTitle']
        )
        elements.append(title)
        elements.append(Spacer(1, 0.2 * inch))

        # Property address (big and bold)
        address = Paragraph(
            f"<b>{lead_data['address']}</b>",
            self.styles['Heading2']
        )
        elements.append(address)

        # Tier badge
        tier = lead_data['tier']
        tier_colors = {
            1: '#15803d',  # Green
            2: '#1e40af',  # Blue
            3: '#ea580c',  # Orange
            4: '#6b7280'   # Gray
        }

        tier_text = Paragraph(
            f"<b>TIER {tier}</b> | Motivation Score: <b>{lead_data['motivation_score']}/100</b>",
            ParagraphStyle(
                name='TierBadge',
                parent=self.styles['Normal'],
                fontSize=14,
                textColor=colors.white,
                backColor=colors.HexColor(tier_colors.get(tier, '#6b7280')),
                alignment=TA_CENTER,
                borderPadding=8
            )
        )
        elements.append(Spacer(1, 0.2 * inch))
        elements.append(tier_text)
        elements.append(Spacer(1, 0.3 * inch))

        return elements

    def _build_executive_summary(self, lead_data: Dict) -> list:
        """Build executive summary section"""
        elements = []

        elements.append(Paragraph("EXECUTIVE SUMMARY", self.styles['SectionHeader']))

        # Key highlights
        summary_text = f"""
        <b>Rating:</b> {lead_data['rating']}<br/>
        <b>Recommended Action:</b> {lead_data['tier_name']}<br/>
        <b>Owner:</b> {lead_data['owner_name']}<br/>
        <b>Assessed Value:</b> ${lead_data['assessed_value']:,.0f}<br/>
        <b>Taxes Owed:</b> ${lead_data['taxes_owed']:,.0f}<br/>
        <b>Years Delinquent:</b> {lead_data['years_delinquent']} years
        """

        elements.append(Paragraph(summary_text, self.styles['Normal']))
        elements.append(Spacer(1, 0.2 * inch))

        return elements

    def _build_property_details(self, lead_data: Dict) -> list:
        """Build property details section"""
        elements = []

        elements.append(Paragraph("PROPERTY DETAILS", self.styles['SectionHeader']))

        # Property details table
        data = [
            ['Address:', lead_data['address']],
            ['Parcel Number:', lead_data.get('parcel_number', 'N/A')],
            ['Property Type:', lead_data.get('property_type', 'Residential')],
            ['Year Built:', str(lead_data.get('year_built', 'N/A'))],
            ['Square Feet:', f"{lead_data.get('square_feet', 0):,} sqft"],
            ['Bedrooms:', str(lead_data.get('bedrooms', 'N/A'))],
            ['Bathrooms:', str(lead_data.get('bathrooms', 'N/A'))],
        ]

        table = Table(data, colWidths=[2 * inch, 4 * inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f3f4f6')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
        ]))

        elements.append(table)
        elements.append(Spacer(1, 0.3 * inch))

        return elements

    def _build_motivation_analysis(self, lead_data: Dict) -> list:
        """Build motivation analysis section"""
        elements = []

        elements.append(Paragraph("MOTIVATION ANALYSIS", self.styles['SectionHeader']))

        # Motivation score breakdown
        score_text = Paragraph(
            f"<b>Overall Motivation Score: {lead_data['motivation_score']}/100</b>",
            self.styles['HighlightBox']
        )
        elements.append(score_text)

        # Reasons
        reasons = lead_data.get('reasons', '').split('|')

        elements.append(Spacer(1, 0.1 * inch))
        elements.append(Paragraph("<b>Distress Indicators:</b>", self.styles['Normal']))

        for reason in reasons:
            reason = reason.strip()
            if reason:
                bullet = Paragraph(f"• {reason}", self.styles['Normal'])
                elements.append(bullet)

        elements.append(Spacer(1, 0.2 * inch))

        return elements

    def _build_financial_overview(self, lead_data: Dict) -> list:
        """Build financial overview section"""
        elements = []

        elements.append(Paragraph("FINANCIAL OVERVIEW", self.styles['SectionHeader']))

        # Financial table
        tax_debt_ratio = lead_data.get('tax_debt_ratio', 0) * 100

        data = [
            ['Assessed Value:', f"${lead_data['assessed_value']:,.0f}"],
            ['Taxes Owed:', f"${lead_data['taxes_owed']:,.0f}"],
            ['Tax Debt Ratio:', f"{tax_debt_ratio:.1f}%"],
            ['Years Delinquent:', f"{lead_data['years_delinquent']} years"],
            ['Code Violations:', str(lead_data.get('code_violations', 0))],
        ]

        table = Table(data, colWidths=[2.5 * inch, 2.5 * inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f3f4f6')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
        ]))

        elements.append(table)
        elements.append(Spacer(1, 0.2 * inch))

        return elements

    def _build_contact_info(self, lead_data: Dict) -> list:
        """Build contact information section"""
        elements = []

        elements.append(Paragraph("CONTACT INFORMATION", self.styles['SectionHeader']))

        # Contact table
        data = [
            ['Owner Name:', lead_data['owner_name']],
            ['Mailing Address:', lead_data.get('mailing_address', 'N/A')],
            ['Phone:', lead_data.get('phone', 'Not available')],
            ['Email:', lead_data.get('email', 'Not available')],
            ['DNC Status:', lead_data.get('dnc_status', 'Unknown')],
        ]

        table = Table(data, colWidths=[2 * inch, 4 * inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f3f4f6')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
        ]))

        elements.append(table)
        elements.append(Spacer(1, 0.2 * inch))

        return elements

    def _build_strategy(self, lead_data: Dict) -> list:
        """Build recommended strategy section"""
        elements = []

        elements.append(Paragraph("RECOMMENDED STRATEGY", self.styles['SectionHeader']))

        # Strategy based on tier
        tier = lead_data['tier']

        if tier == 1:
            strategy = """
            <b>IMMEDIATE ACTION REQUIRED</b><br/><br/>
            This is a Tier 1 lead with extremely high motivation signals. Recommended approach:<br/>
            1. Call within 24 hours<br/>
            2. Lead with tax relief solution<br/>
            3. Offer quick close (7-14 days)<br/>
            4. Consider cash offer at 50-60% ARV<br/>
            5. Emphasize solving their tax problem<br/><br/>
            Expected conversion rate: 15-20%
            """
        elif tier == 2:
            strategy = """
            <b>HIGH PRIORITY</b><br/><br/>
            This is a Tier 2 lead with strong motivation signals. Recommended approach:<br/>
            1. Call within 48 hours<br/>
            2. Mention tax delinquency tactfully<br/>
            3. Offer flexible closing timeline<br/>
            4. Consider cash offer at 55-65% ARV<br/>
            5. Build rapport before discussing situation<br/><br/>
            Expected conversion rate: 8-12%
            """
        else:
            strategy = """
            <b>FOLLOW UP THIS WEEK</b><br/><br/>
            This is a moderate priority lead. Recommended approach:<br/>
            1. Call within 5-7 days<br/>
            2. General outreach, feel out situation<br/>
            3. Be prepared for negotiation<br/>
            4. Standard offer at 60-70% ARV<br/>
            5. May require multiple touches<br/><br/>
            Expected conversion rate: 3-6%
            """

        elements.append(Paragraph(strategy, self.styles['Normal']))
        elements.append(Spacer(1, 0.2 * inch))

        return elements

    def _build_footer(self) -> list:
        """Build report footer"""
        elements = []

        elements.append(HRFlowable(width="100%", thickness=1, color=colors.grey))
        elements.append(Spacer(1, 0.1 * inch))

        footer_text = f"""
        <para align=center>
        Report generated by {APP_NAME}<br/>
        {COMPANY_NAME} | Generated on {datetime.now().strftime('%B %d, %Y')}<br/>
        <font size=8 color="#6b7280">
        DISCLAIMER: Data sourced from public records. Buyer responsible for TCPA compliance.
        </font>
        </para>
        """

        elements.append(Paragraph(footer_text, self.styles['Normal']))

        return elements

    def generate_batch_reports(self, leads: list, top_n: int = None) -> list:
        """
        Generate PDF reports for multiple leads

        Args:
            leads: List of lead dictionaries
            top_n: Only generate for top N leads by score

        Returns:
            List of generated file paths
        """
        if top_n:
            # Sort by score and take top N
            leads = sorted(leads, key=lambda x: x.get('motivation_score', 0), reverse=True)[:top_n]

        generated_files = []

        for i, lead in enumerate(leads, 1):
            self.logger.info(f"Generating report {i}/{len(leads)}: {lead['address']}")

            try:
                path = self.generate_report(lead)
                generated_files.append(path)
            except Exception as e:
                self.logger.error(f"Error generating report for {lead['address']}: {e}")

        log_success(f"Generated {len(generated_files)} PDF reports")
        return generated_files


# Example usage
if __name__ == '__main__':
    # Sample lead data
    sample_lead = {
        'address': '123 Main St, Columbus, OH 43215',
        'owner_name': 'John Smith',
        'parcel_number': '010-012345',
        'property_type': 'Residential',
        'year_built': '1985',
        'square_feet': 1200,
        'bedrooms': 3,
        'bathrooms': 2,
        'assessed_value': 85000,
        'taxes_owed': 12500,
        'years_delinquent': 4,
        'tax_debt_ratio': 0.147,
        'code_violations': 2,
        'motivation_score': 87,
        'tier': 1,
        'tier_name': 'TIER 1 - CALL IMMEDIATELY',
        'rating': '⭐⭐⭐⭐⭐ EXTREMELY MOTIVATED',
        'reasons': '⚠️ 4 years tax delinquent | 💰 Owes 14.7% of value | 🚨 2 code violations | 🏠 Absentee owner',
        'mailing_address': '456 Oak Ave, Cleveland, OH 44101',
        'phone': '614-555-1234',
        'email': 'john@email.com',
        'dnc_status': 'NOT_ON_DNC'
    }

    generator = InvestorReportGenerator()
    pdf_path = generator.generate_report(sample_lead)
    print(f"✅ PDF generated: {pdf_path}")
