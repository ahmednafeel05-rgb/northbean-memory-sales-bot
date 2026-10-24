FROM python:3.12-slim

WORKDIR /app

COPY api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY api/app ./app
COPY db ./db
COPY data ./data

CMD ["sh", "-c", "python db/seed.py && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
