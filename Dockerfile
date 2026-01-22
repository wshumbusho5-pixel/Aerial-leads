FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements-va-app.txt .
RUN pip install --no-cache-dir -r requirements-va-app.txt

# Copy application code
COPY recruiting/ ./recruiting/
COPY .env* ./

# Expose port
EXPOSE 8080

# Run the application
CMD ["streamlit", "run", "recruiting/application_page.py", "--server.port=8080", "--server.address=0.0.0.0", "--server.headless=true"]
