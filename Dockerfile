FROM python:3.8-slim

COPY . /app
RUN pip3 install --no-cache-dir -r /app/requirements.txt

ENTRYPOINT ["/app/addon-proxy.py"]
