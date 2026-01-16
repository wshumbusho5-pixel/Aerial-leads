"""
Aerial Leads - Motivation Scoring Engine

Calculates a 0-100 motivation score for property owners based on multiple distress signals.

Algorithm:
- Tax Delinquency (0-35 points): Years behind on taxes
- Tax Debt Ratio (0-30 points): Debt as % of property value
- Code Violations (0-20 points): Property neglect indicators
- Absentee Owner (0-15 points): Owner doesn't live at property
- Ownership Lifecycle (0-10 points): Estate planning probability
- Vacancy Indicators (0-25 points): Property appears vacant
- Out-of-State Owner (0-10 points): Long-distance landlord
- Inheritance Indicators (0-15 points): Estate/trust/heir in name
- Corporate Owner (0-8 points): LLC/Corp owner (tired investor)
- PROBATE (0-40 points): Property in probate (HIGHEST VALUE)
- PRE-FORECLOSURE (0-35 points): Sheriff sale scheduled (URGENT)

Total: Up to 243 points possible, capped at 100
"""

from typing import Dict, List, Tuple
from shared.config.settings import (
    MOTIVATION_SCORE_WEIGHTS,
    TIER_1_THRESHOLD,
    TIER_2_THRESHOLD,
    TIER_3_THRESHOLD,
    TIER_1_PRICE,
    TIER_2_PRICE,
    TIER_3_PRICE
)
from shared.config.logging_config import get_logger


class MotivationScorer:
    """
    Calculate motivation scores for property leads

    Analyzes multiple distress signals to predict owner motivation to sell
    """

    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)
        self.weights = MOTIVATION_SCORE_WEIGHTS
        self.max_score = 100

    def calculate_score(self, property_data: Dict) -> Dict:
        """
        Calculate motivation score for a property

        Args:
            property_data: Dictionary with property information

        Returns:
            Dictionary with score, rating, tier, and reasons
        """
        score = 0
        reasons = []

        # 1. Tax delinquency score
        tax_score, tax_reasons = self._score_tax_delinquency(property_data)
        score += tax_score
        reasons.extend(tax_reasons)

        # 2. Tax debt ratio score
        ratio_score, ratio_reasons = self._score_tax_debt_ratio(property_data)
        score += ratio_score
        reasons.extend(ratio_reasons)

        # 3. Code violations score
        violation_score, violation_reasons = self._score_code_violations(property_data)
        score += violation_score
        reasons.extend(violation_reasons)

        # 4. Absentee owner score
        absentee_score, absentee_reasons = self._score_absentee_owner(property_data)
        score += absentee_score
        reasons.extend(absentee_reasons)

        # 5. Ownership lifecycle score (age proxy)
        lifecycle_score, lifecycle_reasons = self._score_ownership_lifecycle(property_data)
        score += lifecycle_score
        reasons.extend(lifecycle_reasons)

        # 6. Vacancy score
        vacancy_score, vacancy_reasons = self._score_vacancy(property_data)
        score += vacancy_score
        reasons.extend(vacancy_reasons)

        # 7. Out-of-state owner score
        oos_score, oos_reasons = self._score_out_of_state(property_data)
        score += oos_score
        reasons.extend(oos_reasons)

        # 8. Inheritance/estate indicators
        inherit_score, inherit_reasons = self._score_inheritance_indicators(property_data)
        score += inherit_score
        reasons.extend(inherit_reasons)

        # 9. Corporate owner score (tired landlords)
        corp_score, corp_reasons = self._score_corporate_owner(property_data)
        score += corp_score
        reasons.extend(corp_reasons)

        # 10. Probate score (HIGHEST VALUE - inherited properties)
        probate_score, probate_reasons = self._score_probate(property_data)
        score += probate_score
        reasons.extend(probate_reasons)

        # 11. Pre-foreclosure score (sheriff sale scheduled)
        foreclosure_score, foreclosure_reasons = self._score_pre_foreclosure(property_data)
        score += foreclosure_score
        reasons.extend(foreclosure_reasons)

        # Cap at max score
        final_score = min(score, self.max_score)

        return {
            'score': final_score,
            'rating': self._get_rating(final_score),
            'tier': self._get_tier(final_score),
            'tier_name': self._get_tier_name(final_score),
            'reasons': reasons,
            'price_tier': self._get_price_tier(final_score),
            'component_scores': {
                'tax_delinquency': tax_score,
                'tax_debt_ratio': ratio_score,
                'code_violations': violation_score,
                'absentee_owner': absentee_score,
                'ownership_lifecycle': lifecycle_score,
                'vacancy': vacancy_score,
                'out_of_state': oos_score,
                'inheritance': inherit_score,
                'corporate_owner': corp_score,
                'probate': probate_score,
                'pre_foreclosure': foreclosure_score
            }
        }

    def _score_tax_delinquency(self, data: Dict) -> Tuple[int, List[str]]:
        """
        Score based on years tax delinquent

        Years behind = stronger distress signal
        """
        years = data.get('years_delinquent', 0)
        max_points = self.weights['tax_delinquency']
        reasons = []

        if years >= 5:
            points = max_points
            reasons.append(f"⚠️ {years} years tax delinquent (EXTREME distress)")
        elif years >= 4:
            points = max_points
            reasons.append(f"⚠️ {years} years tax delinquent (Very high distress)")
        elif years == 3:
            points = int(max_points * 0.75)
            reasons.append(f"⚠️ {years} years tax delinquent (High distress)")
        elif years == 2:
            points = int(max_points * 0.50)
            reasons.append(f"⚠️ {years} years tax delinquent (Moderate distress)")
        elif years == 1:
            points = int(max_points * 0.25)
            reasons.append(f"⚠️ {years} year tax delinquent")
        else:
            points = 0

        return points, reasons

    def _score_tax_debt_ratio(self, data: Dict) -> Tuple[int, List[str]]:
        """
        Score based on tax debt as % of property value

        Higher ratio = owner more underwater = more motivated
        """
        taxes_owed = data.get('taxes_owed', 0)
        assessed_value = data.get('assessed_value', 1)
        max_points = self.weights['tax_debt_ratio']
        reasons = []

        if assessed_value > 0:
            ratio = taxes_owed / assessed_value

            if ratio >= 0.20:
                points = max_points
                reasons.append(f"💰 Owes {ratio*100:.1f}% of property value (EXTREME)")
            elif ratio >= 0.15:
                points = max_points
                reasons.append(f"💰 Owes {ratio*100:.1f}% of property value (Very high)")
            elif ratio >= 0.10:
                points = int(max_points * 0.67)
                reasons.append(f"💰 Owes {ratio*100:.1f}% of property value (High)")
            elif ratio >= 0.05:
                points = int(max_points * 0.33)
                reasons.append(f"💰 Owes {ratio*100:.1f}% of property value")
            else:
                points = 0
        else:
            points = 0

        return points, reasons

    def _score_code_violations(self, data: Dict) -> Tuple[int, List[str]]:
        """
        Score based on code violations

        More violations = more neglect = higher motivation
        """
        violations = data.get('code_violations', 0)
        max_points = self.weights['code_violations']
        reasons = []

        if violations >= 3:
            points = max_points
            reasons.append(f"🚨 {violations} code violations (Severely neglected)")
        elif violations >= 2:
            points = int(max_points * 0.75)
            reasons.append(f"🚨 {violations} code violations (Property neglected)")
        elif violations == 1:
            points = int(max_points * 0.50)
            reasons.append(f"🚨 {violations} code violation")
        else:
            points = 0

        return points, reasons

    def _score_absentee_owner(self, data: Dict) -> Tuple[int, List[str]]:
        """
        Score if owner doesn't live at property

        Absentee owners often more motivated to sell
        """
        prop_addr = str(data.get('address', '')).lower().strip()
        mail_addr = str(data.get('mailing_address', '')).lower().strip()
        max_points = self.weights['absentee_owner']
        reasons = []

        # Compare addresses (basic comparison)
        if prop_addr and mail_addr and prop_addr != mail_addr:
            # Extract street address for comparison (ignore suite/apt)
            prop_street = prop_addr.split(',')[0] if ',' in prop_addr else prop_addr
            mail_street = mail_addr.split(',')[0] if ',' in mail_addr else mail_addr

            if prop_street != mail_street:
                points = max_points
                reasons.append("🏠 Absentee owner (doesn't live at property)")
            else:
                points = 0
        else:
            points = 0

        return points, reasons

    def _score_ownership_lifecycle(self, data: Dict) -> Tuple[int, List[str]]:
        """
        Score based on ownership lifecycle stage

        Uses age as proxy for estate planning timeline
        Safe language to comply with Fair Housing Act
        """
        age = data.get('owner_age', None)
        max_points = self.weights['ownership_lifecycle']
        reasons = []

        if age:
            if age >= 75:
                points = max_points
                reasons.append("📊 Elevated estate transition probability")
            elif age >= 65:
                points = int(max_points * 0.80)
                reasons.append("📊 Ownership lifecycle stage indicates potential transition")
            else:
                points = 0
        else:
            points = 0

        return points, reasons

    def _score_vacancy(self, data: Dict) -> Tuple[int, List[str]]:
        """
        Score if property appears vacant

        Vacant properties = no rental income = higher motivation
        """
        is_vacant = data.get('is_vacant', False)
        vacancy_indicator = data.get('vacancy_indicator', '')
        max_points = self.weights['vacancy']
        reasons = []

        if is_vacant:
            points = max_points
            if vacancy_indicator:
                reasons.append(f"🏚️ Property vacant ({vacancy_indicator})")
            else:
                reasons.append("🏚️ Property appears vacant")
        else:
            points = 0

        return points, reasons

    def _score_out_of_state(self, data: Dict) -> Tuple[int, List[str]]:
        """
        Score if owner is out of state

        Out-of-state owners often more motivated to sell distant properties
        """
        property_state = data.get('property_state', 'OH')
        mailing_address = str(data.get('mailing_address', ''))
        owner_address = str(data.get('owner_address', ''))
        max_points = self.weights.get('out_of_state', 10)
        reasons = []

        # Check mailing address for state
        address_to_check = mailing_address or owner_address

        # Common out-of-state indicators
        out_of_state = False

        if address_to_check:
            # Check for common out-of-state patterns
            address_upper = address_to_check.upper()

            # List of other states (not property state)
            other_states = [
                'CA', 'FL', 'TX', 'NY', 'AZ', 'GA', 'NC', 'VA', 'WA', 'CO',
                'NJ', 'MI', 'PA', 'IL', 'TN', 'MD', 'NV', 'SC', 'AL', 'OR'
            ]

            # Check if mailing state differs from property state
            for state in other_states:
                # Check for state at end or followed by zip
                if (f', {state} ' in address_upper or
                    f' {state} ' in address_upper or
                    address_upper.endswith(f' {state}')):
                    out_of_state = True
                    break

        if out_of_state:
            points = max_points
            reasons.append("✈️ Out-of-state owner (long-distance landlord)")
        else:
            points = 0

        return points, reasons

    def _score_inheritance_indicators(self, data: Dict) -> Tuple[int, List[str]]:
        """
        Score based on inheritance/estate indicators in owner name

        Estate/trust ownership often indicates motivation to liquidate
        """
        owner_name = str(data.get('owner_name', '')).upper()
        max_points = self.weights.get('inheritance', 15)
        reasons = []

        # Inheritance/estate indicators
        estate_indicators = [
            (' TR', 'Trust ownership'),
            (' TRUST', 'Trust ownership'),
            (' EST ', 'Estate'),
            (' ESTATE', 'Estate'),
            (' HEIR', 'Heir ownership'),
            (' HEIRS', 'Heirs ownership'),
            (' DECD', 'Deceased owner'),
            (' DECEASED', 'Deceased owner'),
            (' SUCC', 'Successor'),
            (' SUCCESSOR', 'Successor'),
            (' C/O ', 'Care of (possible estate)'),
            (' ADMIN', 'Administrator'),
            (' EXEC', 'Executor'),
            (' EXECUTOR', 'Executor'),
            (' TRUSTEE', 'Trustee'),
        ]

        found_indicator = None
        for indicator, description in estate_indicators:
            if indicator in owner_name or owner_name.endswith(indicator.strip()):
                found_indicator = description
                break

        if found_indicator:
            points = max_points
            reasons.append(f"📜 {found_indicator} - likely motivated to settle")
        else:
            points = 0

        return points, reasons

    def _score_corporate_owner(self, data: Dict) -> Tuple[int, List[str]]:
        """
        Score based on corporate/LLC ownership

        Small LLCs with distressed properties = tired landlords
        """
        owner_name = str(data.get('owner_name', '')).upper()
        max_points = self.weights.get('corporate_owner', 8)
        reasons = []

        # Corporate indicators
        corporate_indicators = [
            (' LLC', 'LLC'),
            (' L.L.C', 'LLC'),
            (' INC', 'Corporation'),
            (' CORP', 'Corporation'),
            (' COMPANY', 'Company'),
            (' CO ', 'Company'),
            (' CO.', 'Company'),
            (' PROPERTIES', 'Property company'),
            (' HOLDINGS', 'Holdings company'),
            (' INVESTMENTS', 'Investment company'),
            (' REALTY', 'Realty company'),
            (' VENTURES', 'Ventures'),
            (' PARTNERS', 'Partnership'),
            (' LTD', 'Limited'),
        ]

        found_indicator = None
        for indicator, description in corporate_indicators:
            if indicator in owner_name or owner_name.endswith(indicator.strip()):
                found_indicator = description
                break

        if found_indicator:
            points = max_points
            reasons.append(f"🏢 {found_indicator} owner - possible tired investor")
        else:
            points = 0

        return points, reasons

    def _score_probate(self, data: Dict) -> Tuple[int, List[str]]:
        """
        Score if property is in probate or has probate case.

        Probate properties are HIGHEST VALUE leads:
        - Heirs often want quick cash
        - 60% of probate properties are free and clear
        - ~40% conversion rate to listing
        """
        is_probate = data.get('is_probate', False)
        probate_case = data.get('probate_case_number', '')
        decedent_name = data.get('decedent_name', '')
        max_points = self.weights.get('probate', 40)
        reasons = []

        if is_probate or probate_case:
            points = max_points
            if probate_case:
                reasons.append(f"⚰️ PROBATE PROPERTY - Case #{probate_case} (HIGHEST VALUE)")
            else:
                reasons.append("⚰️ PROBATE PROPERTY - Inherited, heirs likely motivated (HIGHEST VALUE)")
        elif decedent_name:
            points = int(max_points * 0.75)
            reasons.append(f"⚰️ Possible probate - Decedent: {decedent_name}")
        else:
            points = 0

        return points, reasons

    def _score_pre_foreclosure(self, data: Dict) -> Tuple[int, List[str]]:
        """
        Score if property is in pre-foreclosure or scheduled for sheriff sale.

        Pre-foreclosure properties are extremely motivated:
        - Facing auction deadline
        - Want to avoid credit damage
        - 30-40% list within 12 months
        """
        is_pre_foreclosure = data.get('is_pre_foreclosure', False)
        is_sheriff_sale = data.get('is_sheriff_sale', False)
        auction_date = data.get('auction_date', '')
        foreclosure_case = data.get('foreclosure_case_number', '')
        max_points = self.weights.get('pre_foreclosure', 35)
        reasons = []

        if is_sheriff_sale or auction_date:
            points = max_points
            if auction_date:
                reasons.append(f"🔨 SHERIFF SALE SCHEDULED - Auction: {auction_date} (URGENT)")
            else:
                reasons.append("🔨 SHERIFF SALE SCHEDULED - Facing auction (URGENT)")
        elif is_pre_foreclosure or foreclosure_case:
            points = int(max_points * 0.85)
            if foreclosure_case:
                reasons.append(f"📋 PRE-FORECLOSURE - Case #{foreclosure_case}")
            else:
                reasons.append("📋 PRE-FORECLOSURE - Lis pendens filed")
        else:
            points = 0

        return points, reasons

    def _get_rating(self, score: int) -> str:
        """Convert score to star rating"""
        if score >= 80:
            return "⭐⭐⭐⭐⭐ EXTREMELY MOTIVATED"
        elif score >= 60:
            return "⭐⭐⭐⭐ HIGHLY MOTIVATED"
        elif score >= 40:
            return "⭐⭐⭐ MODERATELY MOTIVATED"
        elif score >= 20:
            return "⭐⭐ SOMEWHAT MOTIVATED"
        else:
            return "⭐ LOW MOTIVATION"

    def _get_tier(self, score: int) -> int:
        """Get numeric tier (1-4)"""
        if score >= TIER_1_THRESHOLD:
            return 1
        elif score >= TIER_2_THRESHOLD:
            return 2
        elif score >= TIER_3_THRESHOLD:
            return 3
        else:
            return 4

    def _get_tier_name(self, score: int) -> str:
        """Get tier description"""
        tier = self._get_tier(score)

        tier_names = {
            1: "TIER 1 - CALL IMMEDIATELY",
            2: "TIER 2 - CALL WITHIN 48 HOURS",
            3: "TIER 3 - CALL THIS WEEK",
            4: "TIER 4 - LOW PRIORITY"
        }

        return tier_names[tier]

    def _get_price_tier(self, score: int) -> int:
        """Get recommended price based on score"""
        tier = self._get_tier(score)

        price_tiers = {
            1: TIER_1_PRICE,
            2: TIER_2_PRICE,
            3: TIER_3_PRICE,
            4: TIER_3_PRICE
        }

        return price_tiers[tier]

    def score_batch(self, properties: List[Dict]) -> List[Dict]:
        """
        Score multiple properties at once

        Args:
            properties: List of property dictionaries

        Returns:
            List of properties with score data added
        """
        scored_properties = []

        for prop in properties:
            score_result = self.calculate_score(prop)

            # Add score data to property
            prop['motivation_score'] = score_result['score']
            prop['rating'] = score_result['rating']
            prop['tier'] = score_result['tier']
            prop['tier_name'] = score_result['tier_name']
            prop['reasons'] = ' | '.join(score_result['reasons'])
            prop['price_tier'] = score_result['price_tier']

            scored_properties.append(prop)

        # Sort by score (highest first)
        scored_properties.sort(key=lambda x: x['motivation_score'], reverse=True)

        return scored_properties


# Example usage
if __name__ == '__main__':
    # Test with sample data
    sample_property = {
        'address': '123 Main St, Columbus, OH 43215',
        'owner_name': 'John Smith',
        'mailing_address': '456 Oak Ave, Cleveland, OH 44101',
        'assessed_value': 85000,
        'taxes_owed': 12500,
        'years_delinquent': 4,
        'code_violations': 2,
        'owner_age': 72,
        'is_vacant': True,
        'vacancy_indicator': 'Utilities disconnected'
    }

    scorer = MotivationScorer()
    result = scorer.calculate_score(sample_property)

    print("🎯 Motivation Score Result:")
    print(f"Score: {result['score']}/100")
    print(f"Rating: {result['rating']}")
    print(f"Tier: {result['tier_name']}")
    print(f"Price: ${result['price_tier']}")
    print(f"\nReasons:")
    for reason in result['reasons']:
        print(f"  - {reason}")
