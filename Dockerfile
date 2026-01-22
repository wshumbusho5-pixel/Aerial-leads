FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements-va-app.txt .
RUN pip install --no-cache-dir -r requirements-va-app.txt

# Copy application code
COPY recruiting/ ./recruiting/

# Create __init__.py if needed
RUN touch ./recruiting/__init__.py

# Set Python path to include recruiting folder
ENV PYTHONPATH=/app:/app/recruiting

# Set environment variable for port
ENV PORT=8080

# Run the application
CMD streamlit run recruiting/application_page.py --server.port=$PORT --server.address=0.0.0.0 --server.headless=true
