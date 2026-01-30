#!/bin/bash
# Start dashboard - loads environment from .env file automatically

cd /Users/willyshumbusho/columbus-wholesaling

# Dashboard uses python-dotenv to load .env automatically
python3 -m streamlit run dashboard.py
