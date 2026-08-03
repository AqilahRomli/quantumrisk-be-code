# Use official Python image
FROM python:3.11-slim

# Set environment variable
ENV APP_ENV=staging

# Set working directory
WORKDIR /app

# Copy requirements and install
COPY requirements2.txt .
RUN pip install --no-cache-dir -r requirements2.txt

# Copy the whole app
COPY . .

# Run FastAPI with uvicorn and --reload for development
CMD ["uvicorn", "routeQuantumRisk:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]

