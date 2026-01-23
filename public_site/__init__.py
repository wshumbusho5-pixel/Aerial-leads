"""
Aerial Leads - Public Facing Website

This module provides a public-facing website that:
1. Generates SEO-optimized pages for each property
2. Captures inbound leads from motivated sellers
3. Provides landing pages for probate, tax delinquent, etc.

Run with:
    cd public_site
    uvicorn app:app --reload --port 8080

Or:
    python app.py
"""

from public_site.app import app

__all__ = ['app']
