"""
VA Application Runner - Simple entry point for Railway
Sets up paths correctly before running the Streamlit app.
"""
import sys
import os

# Add the recruiting folder to Python path BEFORE any imports
current_dir = os.path.dirname(os.path.abspath(__file__))
recruiting_dir = os.path.join(current_dir, 'recruiting')
sys.path.insert(0, recruiting_dir)
sys.path.insert(0, current_dir)

# Now run streamlit
if __name__ == "__main__":
    from streamlit.web import cli as stcli
    sys.argv = [
        "streamlit", "run",
        os.path.join(recruiting_dir, "application_page.py"),
        "--server.port", os.environ.get("PORT", "8080"),
        "--server.address", "0.0.0.0",
        "--server.headless", "true"
    ]
    sys.exit(stcli.main())
