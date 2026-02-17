"""
Lifeline Home Buyers - Opt-Out Manager

Manages property owner opt-out requests for privacy compliance
"""

import json
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

from config.settings import OPT_OUT_FILE
from config.logging_config import log_success, log_failure, get_logger


class OptOutManager:
    """
    Manage opt-out requests from property owners

    Allows property owners to request removal from lead database
    """

    def __init__(self, opt_out_file: Path = OPT_OUT_FILE):
        self.logger = get_logger(self.__class__.__name__)
        self.opt_out_file = opt_out_file
        self.opt_out_records = self._load_opt_outs()

    def _load_opt_outs(self) -> List[Dict]:
        """Load opt-out records from file"""
        if self.opt_out_file.exists():
            try:
                with open(self.opt_out_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                self.logger.error(f"Error loading opt-out file: {e}")
                return []
        return []

    def _save_opt_outs(self):
        """Save opt-out records to file"""
        try:
            # Ensure directory exists
            self.opt_out_file.parent.mkdir(parents=True, exist_ok=True)

            with open(self.opt_out_file, 'w') as f:
                json.dump(self.opt_out_records, f, indent=2)

            self.logger.info(f"Saved {len(self.opt_out_records)} opt-out records")
        except Exception as e:
            self.logger.error(f"Error saving opt-out file: {e}")

    def add_opt_out(
        self,
        address: str,
        owner_name: Optional[str] = None,
        reason: str = '',
        contact_email: Optional[str] = None
    ) -> bool:
        """
        Add an address to the opt-out list

        Args:
            address: Property address
            owner_name: Property owner name (optional)
            reason: Reason for opt-out (optional)
            contact_email: Contact email for confirmation (optional)

        Returns:
            True if successfully added
        """
        # Normalize address
        address_normalized = address.lower().strip()

        # Check if already opted out
        if self.is_opted_out(address):
            self.logger.warning(f"Address already opted out: {address}")
            return False

        # Create opt-out record
        record = {
            'address': address,
            'address_normalized': address_normalized,
            'owner_name': owner_name,
            'reason': reason,
            'contact_email': contact_email,
            'opt_out_date': datetime.now().isoformat(),
            'status': 'active'
        }

        self.opt_out_records.append(record)
        self._save_opt_outs()

        log_success(f"Added opt-out for: {address}")
        return True

    def remove_opt_out(self, address: str) -> bool:
        """
        Remove an address from opt-out list

        Args:
            address: Property address

        Returns:
            True if successfully removed
        """
        address_normalized = address.lower().strip()

        # Find and remove
        initial_count = len(self.opt_out_records)
        self.opt_out_records = [
            record for record in self.opt_out_records
            if record['address_normalized'] != address_normalized
        ]

        if len(self.opt_out_records) < initial_count:
            self._save_opt_outs()
            log_success(f"Removed opt-out for: {address}")
            return True
        else:
            self.logger.warning(f"Address not found in opt-out list: {address}")
            return False

    def is_opted_out(self, address: str) -> bool:
        """
        Check if an address is opted out

        Args:
            address: Property address

        Returns:
            True if address is opted out
        """
        address_normalized = address.lower().strip()

        return any(
            record['address_normalized'] == address_normalized and record['status'] == 'active'
            for record in self.opt_out_records
        )

    def get_opt_out_info(self, address: str) -> Optional[Dict]:
        """
        Get opt-out information for an address

        Args:
            address: Property address

        Returns:
            Opt-out record or None
        """
        address_normalized = address.lower().strip()

        for record in self.opt_out_records:
            if record['address_normalized'] == address_normalized and record['status'] == 'active':
                return record

        return None

    def filter_leads(self, leads: List[Dict]) -> List[Dict]:
        """
        Filter out opted-out addresses from lead list

        Args:
            leads: List of lead dictionaries

        Returns:
            Filtered list without opted-out addresses
        """
        initial_count = len(leads)

        filtered_leads = [
            lead for lead in leads
            if not self.is_opted_out(lead.get('address', ''))
        ]

        filtered_count = initial_count - len(filtered_leads)

        if filtered_count > 0:
            self.logger.info(f"Filtered out {filtered_count} opted-out addresses")

        return filtered_leads

    def get_all_opt_outs(self) -> List[Dict]:
        """Get all opt-out records"""
        return [record for record in self.opt_out_records if record['status'] == 'active']

    def export_opt_out_list(self, output_path: str = 'opt_out_list.csv'):
        """
        Export opt-out list to CSV

        Args:
            output_path: Output file path
        """
        import pandas as pd

        active_records = self.get_all_opt_outs()

        if not active_records:
            log_failure("No opt-out records to export")
            return

        df = pd.DataFrame(active_records)
        df.to_csv(output_path, index=False)

        log_success(f"Exported {len(active_records)} opt-out records to {output_path}")

    def generate_opt_out_form_html(self) -> str:
        """
        Generate HTML opt-out request form

        Returns:
            HTML string
        """
        html = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Opt-Out Request - Lifeline Home Buyers</title>
            <style>
                body { font-family: Arial, sans-serif; max-width: 600px; margin: 50px auto; padding: 20px; }
                h1 { color: #1e40af; }
                form { background: #f9fafb; padding: 20px; border-radius: 8px; }
                label { display: block; margin-top: 15px; font-weight: bold; }
                input, textarea { width: 100%; padding: 8px; margin-top: 5px; border: 1px solid #d1d5db; border-radius: 4px; }
                button { margin-top: 20px; padding: 10px 20px; background: #1e40af; color: white; border: none; border-radius: 4px; cursor: pointer; }
                button:hover { background: #1e3a8a; }
            </style>
        </head>
        <body>
            <h1>Opt-Out Request</h1>
            <p>If you are a property owner and would like to be removed from our database, please fill out the form below.</p>

            <form action="/opt-out/submit" method="POST">
                <label for="address">Property Address *</label>
                <input type="text" id="address" name="address" required
                       placeholder="123 Main St, Columbus, OH 43215">

                <label for="owner_name">Your Name *</label>
                <input type="text" id="owner_name" name="owner_name" required
                       placeholder="John Smith">

                <label for="contact_email">Email Address *</label>
                <input type="email" id="contact_email" name="contact_email" required
                       placeholder="your@email.com">

                <label for="reason">Reason (Optional)</label>
                <textarea id="reason" name="reason" rows="3"
                          placeholder="Optional: Let us know why you'd like to opt out"></textarea>

                <button type="submit">Submit Opt-Out Request</button>
            </form>

            <p style="margin-top: 30px; font-size: 14px; color: #6b7280;">
                We will process your request within 10 business days and send you a confirmation email.
            </p>
        </body>
        </html>
        """

        return html


# Example usage
if __name__ == '__main__':
    manager = OptOutManager()

    # Add opt-out
    manager.add_opt_out(
        address='123 Main St, Columbus, OH 43215',
        owner_name='John Smith',
        reason='Not interested in selling',
        contact_email='john@email.com'
    )

    # Check if opted out
    if manager.is_opted_out('123 Main St, Columbus, OH 43215'):
        print("✅ Address is opted out")

    # Sample leads
    sample_leads = [
        {'address': '123 Main St, Columbus, OH 43215', 'score': 85},
        {'address': '456 Oak Ave, Columbus, OH 43201', 'score': 72},
    ]

    # Filter leads
    filtered = manager.filter_leads(sample_leads)
    print(f"\nFiltered {len(sample_leads)} leads down to {len(filtered)}")

    # Export opt-out list
    manager.export_opt_out_list()

    # Show all opt-outs
    print(f"\nTotal opt-outs: {len(manager.get_all_opt_outs())}")
