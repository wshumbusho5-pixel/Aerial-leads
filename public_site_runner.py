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
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse, JSONResponse
    from pathlib import Path

    # Create a minimal test app first
    test_app = FastAPI(title="Lifeline Test")

    @test_app.get("/")
    def home():
        """Minimal home page."""
        return HTMLResponse("""
        <html>
        <head><title>Lifeline Home Buyers</title></head>
        <body style="font-family: sans-serif; max-width: 800px; margin: 50px auto; padding: 20px;">
            <h1>Lifeline Home Buyers</h1>
            <p>Site is running! Full version coming soon.</p>
            <p><a href="/health">Check Health</a></p>
        </body>
        </html>
        """)

    @test_app.get("/health")
    def health():
        """Health check with diagnostics."""
        base_dir = Path(__file__).parent
        public_site_dir = base_dir / "public_site"
        templates_dir = public_site_dir / "templates"

        return JSONResponse({
            "status": "ok",
            "cwd": os.getcwd(),
            "base_dir": str(base_dir),
            "public_site_exists": public_site_dir.exists(),
            "templates_dir": str(templates_dir),
            "templates_exist": templates_dir.exists(),
            "template_files": [f.name for f in templates_dir.glob("*.html")] if templates_dir.exists() else [],
            "env_vars": {
                "PORT": os.environ.get("PORT", "not set"),
                "DATABASE_URL": "set" if os.environ.get("DATABASE_URL") else "not set"
            }
        })

    port = int(os.environ.get("PORT", 8080))
    print(f"Starting server on port {port}")
    uvicorn.run(test_app, host="0.0.0.0", port=port)
