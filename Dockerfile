FROM python:3.11-slim

# Install WeasyPrint system dependencies
RUN apt-get update && apt-get install -y \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install Python dependencies
COPY blogpack-web/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the blogpack library
COPY blogpack/ ./blogpack/

# Copy the web app
COPY blogpack-web/ ./blogpack-web/

# Create temp directory
RUN mkdir -p /tmp/blogpack

WORKDIR /app/blogpack-web

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
