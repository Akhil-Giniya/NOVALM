# Use NVIDIA CUDA base image for vLLM support
FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# Install System Dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 \
    python3-pip \
    python3-venv \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python Dependencies
COPY novalm/requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy Application Code
COPY novalm/ ./novalm/

# Create a non-root user (Best Practice)
# However, vLLM sometimes needs specific permissions for GPU access, 
# usually root is fine in container, but let's stick to simple root for now 
# to avoid permission issues with mapped volumes or GPU devices if not configured perfectly.
# Setup ENV for app
ENV PYTHONPATH=/app

# Expose port
EXPOSE 8000

# Command to run the application
# We use shell form to allow variable expansion if needed, but array is better for signals.
CMD ["uvicorn", "novalm.fastapi_app.main:app", "--host", "0.0.0.0", "--port", "8000"]
