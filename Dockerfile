FROM python:3.8

RUN pip3 install sanic sanic-gzip semver
RUN pip3 install --pre 'sanic-cors>0.9.99'
COPY addon-proxy.py /addon-proxy.py

ENTRYPOINT ["/addon-proxy.py"]
