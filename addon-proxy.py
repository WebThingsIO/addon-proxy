#!/usr/bin/env python3

from collections import deque
from sanic import Sanic
from sanic.response import json, text
from threading import Thread
import requests
import time


_REFRESH_TIMEOUT = 60
_UPSTREAM = 'https://raw.githubusercontent.com/mozilla-iot/addon-list/master/list.json'
_LIST = None
_REQUESTS = deque()


# Refresh the release list every 60 seconds
def update_list():
    global _LIST

    while True:
        # Pull the latest release list
        try:
            r = requests.get(_UPSTREAM)
            if r.status_code == 200:
                _LIST = r.text
        except requests.exceptions.RequestException as e:
            print(e)
            pass

        # Clear out old items from the request list
        one_day_ago = time.time() - (24 * 60 * 60)
        while len(_REQUESTS) > 0:
            req = _REQUESTS.popleft()
            if req[0] >= one_day_ago:
                _REQUESTS.appendleft(req)
                break

        # Sleep for a bit to avoid Github's rate limiting
        time.sleep(_REFRESH_TIMEOUT)


# Create the sanic app
app = Sanic()


# Serve the list
@app.route('/addons')
async def get_list(request):
    _REQUESTS.append((time.time(), request.headers.get('User-Agent', None)))
    return text(_LIST, content_type='application/json; charset=utf-8',
                headers={'Access-Control-Allow-Origin': '*'})


# Analytics route
@app.route('/addons/analytics')
async def analytics(request):
    requests = {}
    total = 0
    for req in _REQUESTS:
        ua = req[1]
        if ua not in requests:
            requests[ua] = 1
        else:
            requests[ua] += 1

        total += 1

    requests['total'] = total
    return json(requests, headers={'Access-Control-Allow-Origin': '*'})


if __name__ == '__main__':
    t = Thread(target=update_list)
    t.daemon = True
    t.start()

    # Wait for the list to be populated before starting the server
    while _LIST is None:
        time.sleep(.1)

    app.run(host='0.0.0.0', port=80)
