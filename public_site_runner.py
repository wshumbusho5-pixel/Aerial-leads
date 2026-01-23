#!/usr/bin/env python3
"""
Runner script for Lifeline Home Buyers public site on Railway.
Start command: python public_site_runner.py
"""
import os
import sys

# Add the current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    import uvicorn
    from public_site.app import app

    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
