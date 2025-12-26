FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy requirements and install dependencies
COPY requirements.txt .
RUN uv pip install --system -r requirements.txt

# Copy application code
COPY mcp_server/ ./mcp_server/

# Set Python path
ENV PYTHONPATH=/app/mcp_server

# Expose MCP port
EXPOSE 8001

# Run MCP server
WORKDIR /app/mcp_server
CMD ["python", "server.py"]
