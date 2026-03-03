FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir .

RUN groupadd --system app && useradd --system --gid app app \
    && chown -R app:app /app
USER app

ENV PORT=8080

EXPOSE 8080

CMD ["ouro-mcp"]
