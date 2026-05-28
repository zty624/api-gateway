FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml README.md config.example.yaml ./
COPY src ./src

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

EXPOSE 18080

ENV GATEWAY_CONFIG=/app/config.yaml

ENTRYPOINT ["python", "-m", "api_gateway"]
