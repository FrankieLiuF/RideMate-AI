FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create a non-root user for security
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# Cloud Run provides the PORT environment variable
ENV PORT=8080
EXPOSE 8080

# Start the server
CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}
