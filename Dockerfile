FROM mcr.microsoft.com/playwright/python:v1.55.0-noble
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=Asia/Ho_Chi_Minh
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY migrations /app/migrations
COPY agent /app/agent
COPY config /app/config
COPY tools /app/tools
COPY samples /app/samples
COPY assets /app/assets
COPY tests /app/tests
RUN mkdir -p /app/data /app/output
# No privileged mode, no account credentials, no site bypass.
CMD ["python", "-m", "agent.cli", "preview"]
