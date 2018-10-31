FROM python:3.6

RUN pip3 install sanic requests
COPY addon-proxy.py /addon-proxy.py

ENTRYPOINT ["/addon-proxy.py"]
