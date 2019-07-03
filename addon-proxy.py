#!/usr/bin/env python3

from collections import deque
from sanic import Sanic
from sanic.response import html, json
from sanic_compress import Compress
from sanic_cors import CORS
from threading import RLock, Thread
import requests
import semver
import time
import argparse


_REFRESH_TIMEOUT = 60
_UPSTREAM = 'https://raw.githubusercontent.com/mozilla-iot/addon-list/master/list.json'  # noqa
_LIST = None
_LOCK = RLock()
_REQUESTS = deque()

_CSS = '''
<style>
    html, body {
        background-color: #5d9bc7;
        color: white;
        font-family: 'Open Sans', sans-serif;
        font-size: 10px;
        padding: 2rem;
        text-align: center;
    }

    h1 {
        font-family: 'Zilla Slab', 'Open Sans', sans-serif;
    }

    ul {
        list-style-type: none;
    }

    li {
        background-color: #5288af;
        padding: 2rem;
        margin: 1rem auto;
        border-radius: 0.5rem;
        text-align: left;
        width: 60rem;
    }

    .addon-name {
        display: block;
        font-size: 1.8rem;
        padding-bottom: 0.5rem;
    }

    .addon-description {
        display: block;
        font-size: 1.8rem;
        color: #ddd;
        padding-bottom: 0.5rem;
    }

    .addon-author {
        font-size: 1.4rem;
        font-style: italic;
        color: #ddd;
    }

    a:link,
    a:visited,
    a:hover,
    a:active {
        color: white;
    }
</style>
'''

_HTML = '''
<!DOCTYPE html>
<html lang="en">
    <head>
        <title>Add-ons - WebThings Gateway</title>
        {css}
    </head>
    <body>
        <h1>Mozilla WebThings Gateway Add-ons</h1>
        <ul>
        {addons}
        </ul>
    </body>
</html>
'''

_LI_TEMPLATE = '''
<li>
    <span class="addon-name">{name}</span>
    <span class="addon-description">{description}</span>
    <span class="addon-author">by <a href="{homepage}">{author}</a></span>
</li>
'''


def escape_html(s):
    return s\
        .replace('&', '&amp;')\
        .replace('<', '&lt;')\
        .replace('>', '&gt;')\
        .replace('"', '&quot;')\
        .replace("'", '&#39;')


# Refresh the release list every 60 seconds
def update_list(url=_UPSTREAM):
    global _LIST

    while True:
        # Pull the latest release list
        try:
            r = requests.get(url)
            if r.status_code == 200:
                with _LOCK:
                    _LIST = r.json()

            # Clear out old items from the request list
            one_day_ago = time.time() - (24 * 60 * 60)
            while len(_REQUESTS) > 0:
                req = _REQUESTS.popleft()
                if req[0] >= one_day_ago:
                    _REQUESTS.appendleft(req)
                    break
        except Exception as e:
            print(e)
            pass

        # Sleep for a bit to avoid Github's rate limiting
        time.sleep(_REFRESH_TIMEOUT)


def check_addon(addon, arch, api, node, python, test, query, type_):
    results = []

    if query is not None:
        query = query.lower().strip()
        if query not in addon['name'].lower() and \
                query not in addon['display_name'].lower() and \
                query not in addon['description'].lower() and \
                query not in addon['author'].lower():
            return results

    if type_ is not None:
        type_ = type_.lower().strip()
        if type_ != addon['type'].lower():
            return results

    for package in addon['packages']:
        # Verify architecture
        if arch is not None and \
                package['architecture'] != 'any' and \
                package['architecture'] != arch:
            continue

        # Verify API version
        if package['api']['min'] > api or package['api']['max'] < api:
            continue

        # Verify node version
        if package['language']['name'] == 'nodejs' and \
                'any' not in package['language']['versions'] and \
                node not in package['language']['versions']:
            continue

        # Verify python version
        if package['language']['name'] == 'python' and \
                'any' not in package['language']['versions'] and \
                len(set(package['language']['versions']) & set(python)) == 0:
            continue

        # Check test flag
        if 'testOnly' in package and package['testOnly'] and not test:
            continue

        results.append(package)

    return results


# Create the sanic app
app = Sanic()
Compress(app)
CORS(app)


# Serve the list
@app.route('/addons')
async def get_list(request):
    args = request.raw_args
    ua = request.headers.get('User-Agent', None)
    _REQUESTS.append((time.time(), ua))

    # Defaults based on 0.6.X
    arch = args['arch'] if 'arch' in args else None
    api = int(args['api']) if 'api' in args else 2
    node = args['node'] if 'node' in args else '57'
    python = args['python'].split(',') if 'python' in args else ['2.7', '3.5']
    test = args['test'] == '1' if 'test' in args else False
    query = args['query'] if 'query' in args else None
    type_ = args['type'] if 'type' in args else None

    if 'version' in args:
        version = args['version']
    elif ua is not None and ua.startswith('mozilla-iot-gateway/'):
        version = ua.split('/')[1]
    else:
        version = '0.6.1'

    version = semver.parse(version)

    results = []
    with _LOCK:
        for addon in _LIST:
            packages = \
                check_addon(addon, arch, api, node, python, test, query, type_)

            if packages:
                if version['major'] == 0 and version['minor'] <= 6:
                    results.append({
                        'name': addon['name'],
                        'display_name': addon['display_name'],
                        'description': addon['description'],
                        'author': addon['author'],
                        'homepage': addon['homepage'],
                        'packages': {
                            package['architecture']: {
                                'version': package['version'],
                                'url': package['url'],
                                'checksum': package['checksum'],
                            } for package in packages
                        },
                        'api': packages[0]['api'],
                    })
                else:
                    results.extend([
                        {
                            'name': addon['name'],
                            'display_name': addon['display_name'],
                            'description': addon['description'],
                            'author': addon['author'],
                            'homepage': addon['homepage'],
                            'license': addon['license'],
                            'version': package['version'],
                            'url': package['url'],
                            'checksum': package['checksum'],
                            'type': addon['type'],
                        } for package in packages
                    ])

    return json(results)


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
    return json(requests)


@app.route('/addons/info')
async def info(request):
    addons = ''
    with _LOCK:
        for addon in sorted(_LIST, key=lambda e: e['display_name']):
            addons += _LI_TEMPLATE.format(
                name=escape_html(addon['display_name']),
                description=escape_html(addon['description']),
                author=escape_html(addon['author']),
                homepage=escape_html(addon['homepage']),
            )

    return html(_HTML.format(css=_CSS, addons=addons))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Override default params')
    parser.add_argument('--port', type=int, nargs='?',
                        default=80,
                        help='Port for server')
    parser.add_argument('--url', type=str, nargs='?',
                        default=_UPSTREAM,
                        help='URL to serve list')
    args = parser.parse_args()

    t = Thread(target=update_list, args=(args.url,))
    t.daemon = True
    t.start()

    # Wait for the list to be populated before starting the server
    while _LIST is None:
        time.sleep(.1)

    app.run(host='0.0.0.0', port=args.port)
