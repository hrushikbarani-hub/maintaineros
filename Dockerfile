FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY maintaineros ./maintaineros
RUN pip install --no-cache-dir . && useradd --create-home --uid 10001 workbench && mkdir /app/data && chown workbench /app/data
USER workbench
EXPOSE 8000
CMD ["uvicorn", "maintaineros.main:app", "--host", "0.0.0.0", "--port", "8000"]

