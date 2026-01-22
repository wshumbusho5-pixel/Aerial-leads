"""
VA Application Portal - Standalone Entry Point
This runs the VA application form for potential applicants.
"""

import subprocess
import sys

if __name__ == "__main__":
    subprocess.run([
        sys.executable, "-m", "streamlit", "run",
        "recruiting/application_page.py",
        "--server.port", "8080",
        "--server.address", "0.0.0.0",
        "--server.headless", "true"
    ])
