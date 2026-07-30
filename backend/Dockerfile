FROM python:3.13-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml README.md ./
RUN uv sync --no-dev

COPY app ./app

EXPOSE 8000

CMD ["uv", "run", "eventcommerce-backend"]
