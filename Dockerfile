FROM python:3.11-slim

# Install system dependencies, ca-certificates, openssl, and Node.js 20
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    openssl \
    ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python requirements (including GCP, AWS S3, and Azure Blob SDKs)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source repository (respecting .dockerignore)
COPY . .

# Set execution permissions across all cloud provider runners
RUN chmod +x scripts/*.sh scripts/*/*.sh

# Environment configuration
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["/bin/bash", "scripts/cloud_job.sh"]
