FROM python:3.12-slim

# Install SSH client
RUN apt-get update && apt-get install -y openssh-client && rm -rf /var/lib/apt/lists/*

# Install rsync
# RUN apt-get update && apt-get install -y rsync && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN python -m venv /app/venv
ENV PATH="/app/venv/bin:$PATH"
COPY ./cert /app/cert
COPY ./app/identityFile/id_rsa /app/app/identityFile/id_rsa
COPY requirements-linux.txt .

COPY . .
RUN chmod 600 /app/app/identityFile/id_rsa
RUN pip install -r requirements-linux.txt


# Use uvicorn to run the FastAPI application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]