FROM python:3.12-slim

WORKDIR /code

# Install dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Run the API with uvicorn. Configure via environment variables
# (DATABASE_URL, SECRET_KEY, ...). Never bake secrets into the image.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
