"""
Data Archiver - Automatically archives old data before new scrapes
"""

import os
import shutil
from pathlib import Path
from datetime import datetime
import pandas as pd
from typing import Optional, List, Dict
import logging

logger = logging.getLogger(__name__)

# Archive directory
ARCHIVE_DIR = Path(__file__).parent.parent.parent.parent / 'data' / 'archive'


class DataArchiver:
    """Handles archiving and restoring of lead data."""

    def __init__(self):
        self.archive_dir = ARCHIVE_DIR
        self.archive_dir.mkdir(parents=True, exist_ok=True)

    def archive_file(self, file_path: Path, category: str = 'general') -> Optional[str]:
        """
        Archive a file before it gets overwritten.

        Args:
            file_path: Path to the file to archive
            category: Category folder (e.g., 'delinquent', 'probate', 'sheriff')

        Returns:
            Path to archived file, or None if file doesn't exist
        """
        if not file_path.exists():
            logger.info(f"No file to archive: {file_path}")
            return None

        # Create category folder
        category_dir = self.archive_dir / category
        category_dir.mkdir(parents=True, exist_ok=True)

        # Create timestamped filename
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        original_name = file_path.stem
        extension = file_path.suffix

        archive_name = f"{original_name}_{timestamp}{extension}"
        archive_path = category_dir / archive_name

        # Copy file to archive
        shutil.copy2(file_path, archive_path)

        logger.info(f"Archived {file_path.name} to {archive_path}")
        return str(archive_path)

    def archive_leads_before_scrape(self, lead_type: str) -> Dict[str, str]:
        """
        Archive all relevant lead files before a new scrape.

        Args:
            lead_type: 'delinquent', 'probate', 'sheriff', or 'all'

        Returns:
            Dict of archived files
        """
        from shared.config.settings import PROCESSED_DATA_DIR

        archived = {}

        files_to_archive = {
            'delinquent': [
                'columbus_oh_all_leads.csv',
                'columbus_oh_tier_1_leads.csv',
                'columbus_oh_tier_2_leads.csv',
                'columbus_oh_tier_3_leads.csv',
            ],
            'probate': [
                'probate_leads.csv',
            ],
            'sheriff': [
                'sheriff_sale_leads.csv',
            ]
        }

        if lead_type == 'all':
            types_to_archive = ['delinquent', 'probate', 'sheriff']
        else:
            types_to_archive = [lead_type]

        for ltype in types_to_archive:
            if ltype in files_to_archive:
                for filename in files_to_archive[ltype]:
                    file_path = PROCESSED_DATA_DIR / filename
                    result = self.archive_file(file_path, category=ltype)
                    if result:
                        archived[filename] = result

        return archived

    def get_archives(self, category: Optional[str] = None) -> List[Dict]:
        """
        Get list of all archived files.

        Args:
            category: Filter by category, or None for all

        Returns:
            List of archive info dicts
        """
        archives = []

        if category:
            categories = [category]
        else:
            categories = [d.name for d in self.archive_dir.iterdir() if d.is_dir()]

        for cat in categories:
            cat_dir = self.archive_dir / cat
            if not cat_dir.exists():
                continue

            for file_path in cat_dir.glob('*.csv'):
                # Parse filename to get original name and timestamp
                name_parts = file_path.stem.rsplit('_', 2)
                if len(name_parts) >= 3:
                    original_name = '_'.join(name_parts[:-2])
                    date_str = name_parts[-2]
                    time_str = name_parts[-1]
                    timestamp = f"{date_str} {time_str.replace('-', ':')}"
                else:
                    original_name = file_path.stem
                    timestamp = "Unknown"

                # Get file info
                stat = file_path.stat()

                # Count rows
                try:
                    df = pd.read_csv(file_path, nrows=0)
                    row_count = sum(1 for _ in open(file_path)) - 1  # Subtract header
                except:
                    row_count = 0

                archives.append({
                    'category': cat,
                    'original_name': original_name,
                    'filename': file_path.name,
                    'filepath': str(file_path),
                    'timestamp': timestamp,
                    'size_kb': round(stat.st_size / 1024, 1),
                    'rows': row_count,
                    'archived_date': datetime.fromtimestamp(stat.st_mtime)
                })

        # Sort by date, newest first
        archives.sort(key=lambda x: x['archived_date'], reverse=True)

        return archives

    def restore_archive(self, archive_path: str, overwrite: bool = False) -> bool:
        """
        Restore an archived file to the processed data directory.

        Args:
            archive_path: Path to the archived file
            overwrite: If True, overwrite current file. If False, archive current first.

        Returns:
            True if successful
        """
        from shared.config.settings import PROCESSED_DATA_DIR

        archive_file = Path(archive_path)
        if not archive_file.exists():
            logger.error(f"Archive file not found: {archive_path}")
            return False

        # Parse original filename from archive name
        name_parts = archive_file.stem.rsplit('_', 2)
        if len(name_parts) >= 3:
            original_name = '_'.join(name_parts[:-2]) + archive_file.suffix
        else:
            original_name = archive_file.name

        dest_path = PROCESSED_DATA_DIR / original_name

        # Archive current file first if it exists and not overwriting
        if dest_path.exists() and not overwrite:
            category = archive_file.parent.name
            self.archive_file(dest_path, category=f"{category}_before_restore")

        # Copy archived file to destination
        shutil.copy2(archive_file, dest_path)

        logger.info(f"Restored {archive_file.name} to {dest_path}")
        return True

    def delete_archive(self, archive_path: str) -> bool:
        """Delete an archived file."""
        archive_file = Path(archive_path)
        if archive_file.exists():
            archive_file.unlink()
            logger.info(f"Deleted archive: {archive_path}")
            return True
        return False

    def cleanup_old_archives(self, days: int = 30, category: Optional[str] = None) -> int:
        """
        Delete archives older than specified days.

        Args:
            days: Delete archives older than this many days
            category: Only clean specific category, or None for all

        Returns:
            Number of files deleted
        """
        from datetime import timedelta

        cutoff = datetime.now() - timedelta(days=days)
        deleted = 0

        archives = self.get_archives(category)

        for archive in archives:
            if archive['archived_date'] < cutoff:
                if self.delete_archive(archive['filepath']):
                    deleted += 1

        logger.info(f"Cleaned up {deleted} archives older than {days} days")
        return deleted


# Convenience function
def archive_before_scrape(lead_type: str) -> Dict[str, str]:
    """Quick function to archive before scraping."""
    archiver = DataArchiver()
    return archiver.archive_leads_before_scrape(lead_type)
