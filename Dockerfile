FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY iachat ./iachat
RUN python -m pip install --no-cache-dir .
ENV PYTHONUNBUFFERED=1
ENV IACHAT_DB=/data/iachat.db
VOLUME ["/data"]
EXPOSE 8000
CMD ["uvicorn", "iachat.app:app", "--host", "0.0.0.0", "--port", "8000"]
