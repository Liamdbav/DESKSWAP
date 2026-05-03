FROM python:3.11-alpine

WORKDIR /app

RUN apk add --no-cache gcc python3-dev musl-dev linux-headers curl

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY templates ./templates

RUN addgroup -g 1000 appuser && \
    adduser -D -u 1000 -G appuser appuser && \
    mkdir -p /home/user && \
    chown -R appuser:appuser /app /home/user

USER appuser

EXPOSE 8080

CMD ["python", "app.py"]
