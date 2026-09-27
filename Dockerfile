FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install ripgrep
RUN curl -LO https://github.com/BurntSushi/ripgrep/releases/download/14.1.0/ripgrep_14.1.0-1_amd64.deb \
    && dpkg -i ripgrep_14.1.0-1_amd64.deb \
    && rm ripgrep_14.1.0-1_amd64.deb

WORKDIR /app

COPY pyproject.toml ./
COPY src/ ./src/

RUN pip install --no-cache-dir -e .

EXPOSE 8000

CMD ["uvicorn", "code_analyser.api:app", "--host", "0.0.0.0", "--port", "8000"]
