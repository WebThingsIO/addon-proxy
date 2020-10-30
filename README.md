# addon-proxy

This is the server used to proxy a gateway add-on list from GitHub.

## Usage

```sh
pip3 install -r requirements.txt
./addon-proxy.py
```

## Data Stored

The only data stored by this server is the user-agent, which, when coming from
the gateway, is something like:
```
webthings-gateway/1.0.0 (linux-arm; linux-raspbian)
```

When the request comes from your browser, the user-agent is the same as your
browser's.
