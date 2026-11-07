FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY assistant ./assistant
COPY docs ./docs

# The index needs GEMINI_API_KEY, which only exists at runtime (set it in the host's environment),
# so it is built on the first start instead of during the image build.
EXPOSE 8000
CMD ["sh", "-c", "uvicorn assistant.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
