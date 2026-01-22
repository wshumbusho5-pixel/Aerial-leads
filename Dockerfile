FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements-va-app.txt .
RUN pip install --no-cache-dir -r requirements-va-app.txt

# Copy application code
COPY recruiting/ ./recruiting/
COPY .env* ./

# Set environment variable for port
ENV PORT=8080

# Run the application using shell form to expand $PORT
CMD streamlit run recruiting/application_page.py --server.port=$PORT --server.address=0.0.0.0 --server.headless=true
