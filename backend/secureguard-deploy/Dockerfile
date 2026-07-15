FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir fastapi uvicorn[standard] pydantic PyYAML
COPY secureguard ./secureguard
COPY config ./config
EXPOSE 8000 9000
CMD ["uvicorn", "secureguard.api:app", "--host", "0.0.0.0", "--port", "9000"]
