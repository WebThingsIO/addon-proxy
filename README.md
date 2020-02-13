# addon-proxy

This is the server used to proxy a gateway add-on list from GitHub.

## Usage

```sh
pip install sanic sanic-gzip semver
pip install --pre 'sanic-cors>0.9.99'
./addon-proxy.py [port]
```

## Data Stored

The only data stored by this server is the user-agent, which, when coming from
the gateway, is something like:
```
mozilla-iot-gateway/0.6.0
```

When the request comes from your browser, the user-agent is the same as your
browser's.
