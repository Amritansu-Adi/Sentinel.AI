FROM python:3.12-slim

WORKDIR /app

# Install deps first so this layer caches independent of app code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ./app ./app

EXPOSE 8000

# Matches DETECTION_SERVICE_URL=http://localhost:8000 default in project.md's
# env var table. No PORT env var introduced here — Task 2.1 scope is the
# contract only; making this configurable is not required by project.md and
# would be an unrequested config addition.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
