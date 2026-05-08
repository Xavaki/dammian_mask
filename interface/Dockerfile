FROM oven/bun:1 AS frontend-build

WORKDIR /frontend
COPY dammian-mask-frontend/package.json dammian-mask-frontend/bun.lock* ./
RUN bun install

COPY dammian-mask-frontend/ .
RUN bun run build

FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .
COPY --from=frontend-build /frontend/dist ./frontend_dist

CMD ["gunicorn", "-b", "0.0.0.0:5000", "run:app"]
