FROM node:22-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web ./
RUN npm run build

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY tests ./tests
COPY --from=web /web/dist ./web/dist
RUN pip install --upgrade pip && pip install -e ".[dev]"
EXPOSE 8000
CMD ["uvicorn", "adjutant.main:app", "--host", "0.0.0.0", "--port", "8000"]
