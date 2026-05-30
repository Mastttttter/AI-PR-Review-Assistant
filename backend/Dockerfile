FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml ./
RUN uv pip install --system -e ".[dev]"
RUN pip install --no-cache-dir psycopg2-binary

COPY . .

EXPOSE 8000

CMD ["uv", "run", "apr-api"]
