FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY fia ./fia
RUN pip install --no-cache-dir .
RUN mkdir -p /app/data
ENV API_HOST=0.0.0.0 API_PORT=8000
EXPOSE 8000
CMD ["uvicorn", "fia.api:app", "--host", "0.0.0.0", "--port", "8000"]
