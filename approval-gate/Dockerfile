FROM python:3.12-slim

WORKDIR /app

# Install docker CLI for pulling images
RUN apt-get update && apt-get install -y --no-install-recommends \
    docker.io \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY setup.py .

EXPOSE 9999

CMD ["python", "app.py"]
