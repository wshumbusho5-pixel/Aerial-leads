"""
Buyer Matcher - Match deals to interested buyers

Matches seller leads/deals to buyers based on their buy box criteria:
- Location (zip codes, neighborhoods)
- Property type (SFR, multi-family, etc.)
- Price range (min/max ARV, purchase price)
- Property condition preferences
- Speed to close requirements
"""

import pandas as pd
import os
import json
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path


class BuyerMatcher:
    """Match deals to buyers based on their criteria"""

    def __init__(self):
        self.data_dir = Path(__file__).parent / 'data'
        self.data_dir.mkdir(exist_ok=True)

        self.buyers_file = self.data_dir / 'buyers.csv'
        self.matches_file = self.data_dir / 'deal_matches.csv'
        self.blasts_file = self.data_dir / 'deal_blasts.csv'

        self._init_files()

    def _init_files(self):
        """Initialize data files if they don't exist"""
        if not self.buyers_file.exists():
            df = pd.DataFrame(columns=[
                'buyer_id', 'name', 'company', 'email', 'phone',
                'zip_codes', 'property_types', 'min_price', 'max_price',
                'min_arv', 'max_arv', 'condition_preference',
                'max_days_to_close', 'funding_type', 'notes',
                'deals_purchased', 'avg_response_time_hrs', 'status',
                'created_at', 'updated_at'
            ])
            df.to_csv(self.buyers_file, index=False)

        if not self.matches_file.exists():
            df = pd.DataFrame(columns=[
                'match_id', 'deal_id', 'buyer_id', 'match_score',
                'match_reasons', 'status', 'response', 'response_time',
                'created_at', 'updated_at'
            ])
            df.to_csv(self.matches_file, index=False)

        if not self.blasts_file.exists():
            df = pd.DataFrame(columns=[
                'blast_id', 'deal_id', 'deal_address', 'asking_price',
                'arv', 'buyers_notified', 'responses', 'status',
                'created_at', 'closed_at'
            ])
            df.to_csv(self.blasts_file, index=False)

    # ==================== BUYER MANAGEMENT ====================

    def add_buyer(self, name: str, email: str, phone: str,
                  zip_codes: List[str], property_types: List[str],
                  min_price: float = 0, max_price: float = 500000,
                  min_arv: float = 0, max_arv: float = 1000000,
                  condition_preference: str = 'any',
                  max_days_to_close: int = 30,
                  funding_type: str = 'cash',
                  company: str = '', notes: str = '') -> str:
        """Add a new buyer to the database"""

        df = pd.read_csv(self.buyers_file)

        # Generate buyer ID
        buyer_id = f"BUY-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        new_buyer = {
            'buyer_id': buyer_id,
            'name': name,
            'company': company,
            'email': email,
            'phone': phone,
            'zip_codes': ','.join(zip_codes) if isinstance(zip_codes, list) else zip_codes,
            'property_types': ','.join(property_types) if isinstance(property_types, list) else property_types,
            'min_price': min_price,
            'max_price': max_price,
            'min_arv': min_arv,
            'max_arv': max_arv,
            'condition_preference': condition_preference,
            'max_days_to_close': max_days_to_close,
            'funding_type': funding_type,
            'notes': notes,
            'deals_purchased': 0,
            'avg_response_time_hrs': 0,
            'status': 'active',
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }

        df = pd.concat([df, pd.DataFrame([new_buyer])], ignore_index=True)
        df.to_csv(self.buyers_file, index=False)

        return buyer_id

    def get_all_buyers(self, status: str = None) -> pd.DataFrame:
        """Get all buyers, optionally filtered by status"""
        df = pd.read_csv(self.buyers_file)
        if status:
            df = df[df['status'] == status]
        return df

    def get_buyer(self, buyer_id: str) -> Optional[Dict]:
        """Get a specific buyer by ID"""
        df = pd.read_csv(self.buyers_file)
        buyer = df[df['buyer_id'] == buyer_id]
        if len(buyer) > 0:
            return buyer.iloc[0].to_dict()
        return None

    def update_buyer(self, buyer_id: str, **kwargs) -> bool:
        """Update buyer information"""
        df = pd.read_csv(self.buyers_file)
        idx = df[df['buyer_id'] == buyer_id].index

        if len(idx) == 0:
            return False

        for key, value in kwargs.items():
            if key in df.columns:
                if key in ['zip_codes', 'property_types'] and isinstance(value, list):
                    value = ','.join(value)
                df.loc[idx, key] = value

        df.loc[idx, 'updated_at'] = datetime.now().isoformat()
        df.to_csv(self.buyers_file, index=False)
        return True

    def deactivate_buyer(self, buyer_id: str) -> bool:
        """Deactivate a buyer"""
        return self.update_buyer(buyer_id, status='inactive')

    def delete_buyer(self, buyer_id: str) -> bool:
        """Permanently delete a buyer"""
        df = pd.read_csv(self.buyers_file)
        df = df[df['buyer_id'] != buyer_id]
        df.to_csv(self.buyers_file, index=False)
        return True

    # ==================== DEAL MATCHING ====================

    def match_deal_to_buyers(self, deal: Dict) -> List[Dict]:
        """
        Find matching buyers for a deal

        Args:
            deal: Dict with keys like 'address', 'zip_code', 'property_type',
                  'asking_price', 'arv', 'condition'

        Returns:
            List of matched buyers with scores
        """
        buyers_df = self.get_all_buyers(status='active')

        if len(buyers_df) == 0:
            return []

        matches = []

        for _, buyer in buyers_df.iterrows():
            score, reasons = self._calculate_match_score(deal, buyer)

            if score > 0:
                matches.append({
                    'buyer_id': buyer['buyer_id'],
                    'name': buyer['name'],
                    'company': buyer.get('company', ''),
                    'email': buyer['email'],
                    'phone': buyer['phone'],
                    'score': score,
                    'reasons': reasons,
                    'deals_purchased': buyer.get('deals_purchased', 0),
                    'avg_response_time_hrs': buyer.get('avg_response_time_hrs', 0),
                    'funding_type': buyer.get('funding_type', 'cash')
                })

        # Sort by score (highest first), then by deals purchased
        matches.sort(key=lambda x: (x['score'], x['deals_purchased']), reverse=True)

        return matches

    def _calculate_match_score(self, deal: Dict, buyer: pd.Series) -> tuple:
        """Calculate match score between a deal and buyer"""
        score = 0
        reasons = []

        # ZIP code match (40 points)
        buyer_zips = str(buyer.get('zip_codes', '')).split(',')
        buyer_zips = [z.strip() for z in buyer_zips if z.strip()]
        deal_zip = str(deal.get('zip_code', ''))

        if deal_zip and deal_zip in buyer_zips:
            score += 40
            reasons.append(f"ZIP {deal_zip} in buy box")
        elif not buyer_zips or buyer_zips == ['']:
            # No zip restriction = matches all
            score += 20
            reasons.append("No ZIP restriction")
        else:
            # ZIP doesn't match - still include but lower score
            score += 5
            reasons.append("ZIP outside primary area")

        # Property type match (20 points)
        buyer_types = str(buyer.get('property_types', '')).lower().split(',')
        buyer_types = [t.strip() for t in buyer_types if t.strip()]
        deal_type = str(deal.get('property_type', '')).lower()

        if not buyer_types or buyer_types == [''] or 'any' in buyer_types:
            score += 15
            reasons.append("Accepts any property type")
        elif any(t in deal_type or deal_type in t for t in buyer_types):
            score += 20
            reasons.append(f"Property type matches")

        # Price range match (25 points)
        asking_price = float(deal.get('asking_price', 0) or 0)
        min_price = float(buyer.get('min_price', 0) or 0)
        max_price = float(buyer.get('max_price', 999999999) or 999999999)

        if min_price <= asking_price <= max_price:
            score += 25
            reasons.append(f"Price ${asking_price:,.0f} in range")
        elif asking_price < min_price:
            score += 10
            reasons.append(f"Price below min (${min_price:,.0f})")

        # ARV match (15 points)
        arv = float(deal.get('arv', 0) or 0)
        min_arv = float(buyer.get('min_arv', 0) or 0)
        max_arv = float(buyer.get('max_arv', 999999999) or 999999999)

        if arv > 0 and min_arv <= arv <= max_arv:
            score += 15
            reasons.append(f"ARV ${arv:,.0f} in range")
        elif arv == 0:
            score += 5
            reasons.append("ARV not specified")

        # Buyer track record bonus (up to 10 points)
        deals_purchased = int(buyer.get('deals_purchased', 0) or 0)
        if deals_purchased >= 10:
            score += 10
            reasons.append(f"Proven buyer ({deals_purchased} deals)")
        elif deals_purchased >= 5:
            score += 7
            reasons.append(f"Active buyer ({deals_purchased} deals)")
        elif deals_purchased >= 1:
            score += 5
            reasons.append(f"Has purchased before")

        return score, reasons

    # ==================== DEAL BLASTING ====================

    def create_deal_blast(self, deal: Dict, buyer_ids: List[str] = None) -> str:
        """
        Create a deal blast to notify buyers

        Args:
            deal: Deal information
            buyer_ids: Specific buyers to notify (None = all matched)

        Returns:
            blast_id
        """
        # Get matched buyers if not specified
        if buyer_ids is None:
            matches = self.match_deal_to_buyers(deal)
            buyer_ids = [m['buyer_id'] for m in matches]

        blast_id = f"BLAST-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        blast = {
            'blast_id': blast_id,
            'deal_id': deal.get('deal_id', ''),
            'deal_address': deal.get('address', ''),
            'asking_price': deal.get('asking_price', 0),
            'arv': deal.get('arv', 0),
            'buyers_notified': len(buyer_ids),
            'responses': 0,
            'status': 'sent',
            'created_at': datetime.now().isoformat(),
            'closed_at': ''
        }

        df = pd.read_csv(self.blasts_file)
        df = pd.concat([df, pd.DataFrame([blast])], ignore_index=True)
        df.to_csv(self.blasts_file, index=False)

        # Create match records
        matches_df = pd.read_csv(self.matches_file)

        for buyer_id in buyer_ids:
            match = {
                'match_id': f"M-{datetime.now().strftime('%Y%m%d%H%M%S%f')[:17]}",
                'deal_id': deal.get('deal_id', ''),
                'buyer_id': buyer_id,
                'match_score': 0,  # Will be calculated
                'match_reasons': '',
                'status': 'notified',
                'response': '',
                'response_time': '',
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }
            matches_df = pd.concat([matches_df, pd.DataFrame([match])], ignore_index=True)

        matches_df.to_csv(self.matches_file, index=False)

        return blast_id

    def record_buyer_response(self, blast_id: str, buyer_id: str,
                              response: str, interested: bool = False) -> bool:
        """Record a buyer's response to a deal blast"""

        # Update match record
        matches_df = pd.read_csv(self.matches_file)
        blast_df = pd.read_csv(self.blasts_file)

        # Find the blast to get deal_id
        blast = blast_df[blast_df['blast_id'] == blast_id]
        if len(blast) == 0:
            return False

        deal_id = blast.iloc[0]['deal_id']

        # Update match
        idx = matches_df[(matches_df['deal_id'] == deal_id) &
                         (matches_df['buyer_id'] == buyer_id)].index

        if len(idx) > 0:
            matches_df.loc[idx, 'status'] = 'interested' if interested else 'passed'
            matches_df.loc[idx, 'response'] = response
            matches_df.loc[idx, 'response_time'] = datetime.now().isoformat()
            matches_df.loc[idx, 'updated_at'] = datetime.now().isoformat()
            matches_df.to_csv(self.matches_file, index=False)

        # Update blast response count
        blast_idx = blast_df[blast_df['blast_id'] == blast_id].index
        if len(blast_idx) > 0:
            current_responses = int(blast_df.loc[blast_idx, 'responses'].iloc[0] or 0)
            blast_df.loc[blast_idx, 'responses'] = current_responses + 1
            blast_df.to_csv(self.blasts_file, index=False)

        return True

    def get_deal_responses(self, blast_id: str) -> pd.DataFrame:
        """Get all responses for a deal blast"""
        blast_df = pd.read_csv(self.blasts_file)
        matches_df = pd.read_csv(self.matches_file)
        buyers_df = pd.read_csv(self.buyers_file)

        blast = blast_df[blast_df['blast_id'] == blast_id]
        if len(blast) == 0:
            return pd.DataFrame()

        deal_id = blast.iloc[0]['deal_id']

        # Get matches for this deal
        deal_matches = matches_df[matches_df['deal_id'] == deal_id].copy()

        # Merge with buyer info
        if len(deal_matches) > 0:
            deal_matches = deal_matches.merge(
                buyers_df[['buyer_id', 'name', 'company', 'email', 'phone']],
                on='buyer_id',
                how='left'
            )

        return deal_matches

    # ==================== STATISTICS ====================

    def get_stats(self) -> Dict:
        """Get buyer matcher statistics"""
        buyers_df = pd.read_csv(self.buyers_file)
        matches_df = pd.read_csv(self.matches_file)
        blasts_df = pd.read_csv(self.blasts_file)

        active_buyers = len(buyers_df[buyers_df['status'] == 'active'])
        total_buyers = len(buyers_df)

        total_blasts = len(blasts_df)
        total_responses = int(blasts_df['responses'].sum()) if len(blasts_df) > 0 else 0

        interested = len(matches_df[matches_df['status'] == 'interested'])

        return {
            'total_buyers': total_buyers,
            'active_buyers': active_buyers,
            'total_blasts': total_blasts,
            'total_responses': total_responses,
            'interested_responses': interested,
            'response_rate': f"{(total_responses / max(total_blasts, 1) * 100):.1f}%"
        }

    def get_top_buyers(self, limit: int = 10) -> pd.DataFrame:
        """Get top buyers by deals purchased"""
        df = pd.read_csv(self.buyers_file)
        df = df[df['status'] == 'active']
        df = df.sort_values('deals_purchased', ascending=False)
        return df.head(limit)


# Quick test
if __name__ == '__main__':
    matcher = BuyerMatcher()

    # Add test buyer
    buyer_id = matcher.add_buyer(
        name="John Investor",
        email="john@investor.com",
        phone="614-555-1234",
        zip_codes=['43201', '43202', '43203'],
        property_types=['SFR', 'Duplex'],
        min_price=50000,
        max_price=150000,
        funding_type='cash'
    )
    print(f"Added buyer: {buyer_id}")

    # Test matching
    test_deal = {
        'address': '123 Main St',
        'zip_code': '43201',
        'property_type': 'SFR',
        'asking_price': 85000,
        'arv': 140000,
        'condition': 'needs_work'
    }

    matches = matcher.match_deal_to_buyers(test_deal)
    print(f"\nFound {len(matches)} matching buyers:")
    for m in matches:
        print(f"  - {m['name']}: Score {m['score']} ({', '.join(m['reasons'])})")

    print(f"\nStats: {matcher.get_stats()}")
