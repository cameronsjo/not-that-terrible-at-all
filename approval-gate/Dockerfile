FROM python:3.12-slim

WORKDIR /app

# Install docker CLI for pulling images and oras for config artifacts
RUN apt-get update && apt-get install -y --no-install-recommends \
    docker.io \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && curl -LO "https://github.com/oras-project/oras/releases/download/v1.2.0/oras_1.2.0_linux_amd64.tar.gz" \
    && tar -xzf oras_1.2.0_linux_amd64.tar.gz -C /usr/local/bin oras \
    && rm oras_1.2.0_linux_amd64.tar.gz

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY setup.py .

EXPOSE 9999

CMD ["python", "app.py"]
