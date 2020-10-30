FROM python:3.9

COPY addon-proxy.py requirements.txt /app/
ARG DEBIAN_FRONTEND=noninteractive
RUN apt update && \
    apt dist-upgrade -y && \
    apt install -y git && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* && \
    pip3 install --no-cache-dir -r /app/requirements.txt

ENTRYPOINT ["/app/addon-proxy.py"]
