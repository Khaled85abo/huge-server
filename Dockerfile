FROM python:3.12-slim

WORKDIR /app

RUN python -m venv /app/venv
ENV PATH="/app/venv/bin:$PATH"
COPY ./cert /app/cert
COPY ./app/identityFile /app/identityFile
COPY requirements-linux.txt .

RUN pip install -r requirements-linux.txt

COPY . .

# Use uvicorn to run the FastAPI application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]