FROM python:3.7

RUN pip3 install sanic==18.12 sanic_compress sanic-cors semver
COPY addon-proxy.py /addon-proxy.py

ENTRYPOINT ["/addon-proxy.py"]
