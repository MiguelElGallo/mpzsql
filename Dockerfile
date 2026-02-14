FROM python:3.13-slim AS base

# Install system libraries required by DuckDB Azure extension (curl transport + CA certs)
RUN apt-get update && \
    apt-get install -y --no-install-recommends libcurl4 ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Install UV for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:0.7 /uv /uvx /bin/

# Create non-root user
RUN groupadd --gid 1000 lakehouse && \
    useradd --uid 1000 --gid lakehouse --create-home lakehouse

WORKDIR /app

# Install dependencies first (cached layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --no-install-project --frozen

# Copy source code
COPY README.md ./
COPY src/ src/
COPY proto/ proto/
RUN uv sync --no-dev --frozen

# Switch to non-root
USER lakehouse

# Prevent uv run from trying to sync missing dev dependencies
ENV UV_NO_SYNC=1

# Tell DuckDB's bundled libcurl where to find CA certificates
ENV CURL_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
ENV CURL_CA_INFO=/etc/ssl/certs/ca-certificates.crt
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt

# Flight SQL port + health check port
EXPOSE 31337 8081

ENTRYPOINT ["uv", "run", "lakehouse"]
CMD []
