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

    try:
        # Try to import the full app
        from public_site.app import app
        print("Successfully imported full app")
    except Exception as e:
        print(f"Error importing app: {e}")
        # Fall back to minimal app
        from fastapi import FastAPI
        from fastapi.responses import HTMLResponse
        app = FastAPI()

        @app.get("/")
        def home():
            return HTMLResponse(f"""
            <html>
            <body>
                <h1>Error loading full app</h1>
                <p>Error: {e}</p>
            </body>
            </html>
            """)

    port = int(os.environ.get("PORT", 8080))
    print(f"Starting server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
