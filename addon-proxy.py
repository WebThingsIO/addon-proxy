#!/usr/bin/env python3

"""
Add-on proxy server.

This server reads a set of add-on list entries from a git repo and serves them
back to a gateway, based on a set of filters.
"""

from collections import deque
from sanic import Sanic
from sanic.response import (
    empty as response_empty,
    html as response_html,
    json as response_json,
    text as response_text
)
from sanic_cors import CORS
from sanic_gzip import Compress
from threading import RLock, Thread
import argparse
import glob
import json
import os
import requests
import semver
import shutil
import subprocess
import sys
import time


_DEFAULT_PORT = 80
_DEFAULT_REPO = 'https://github.com/WebThingsIO/addon-list'
_DEFAULT_BRANCH = 'master'

_BASE_DIR = os.path.realpath(os.path.dirname(__file__))
_REPO_DIR = os.path.join(_BASE_DIR, 'repo')
_ADDONS_DIR = os.path.join(_REPO_DIR, 'addons')

_REFRESH_TIMEOUT = 60
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
        <h1>WebThings Gateway Add-ons</h1>
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
    """
    Escape a string for HTML insertion.

    s -- the string to escape

    Returns the escaped string.
    """
    return s\
        .replace('&', '&amp;')\
        .replace('<', '&lt;')\
        .replace('>', '&gt;')\
        .replace('"', '&quot;')\
        .replace("'", '&#39;')


def update_list(repo, branch):
    """
    Update the list.

    This will pull the latest commits from the configured git repository
    periodically.

    repo -- the git repo
    branch -- the git branch
    """
    global _LIST

    if os.path.exists(_REPO_DIR):
        try:
            shutil.rmtree(_REPO_DIR)
        except OSError:
            print('Failed to remove existing repo')
            sys.exit(1)

    code = subprocess.call(
        ['git', 'clone', '--single-branch', '--branch', branch, repo, 'repo'],
        cwd=_BASE_DIR,
    )

    if code != 0:
        print('Failed to clone git repository')
        sys.exit(1)

    while True:
        # Pull the latest release list
        code = subprocess.call(
            ['git', 'pull'],
            cwd=_REPO_DIR,
        )

        if code == 0:
            addon_list = []

            for path in sorted(glob.glob(os.path.join(_ADDONS_DIR, '*.json'))):
                try:
                    with open(path, 'rt') as f:
                        addon_list.append(json.load(f))
                except (IOError, OSError, ValueError) as e:
                    print('Failed to read {}: {}'.format(path, e))
                    continue

            with _LOCK:
                _LIST = addon_list

        # Clear out old items from the request list
        one_day_ago = time.time() - (24 * 60 * 60)
        while len(_REQUESTS) > 0:
            req = _REQUESTS.popleft()
            if req[0] >= one_day_ago:
                _REQUESTS.appendleft(req)
                break

        # Sleep for a bit to avoid Github's rate limiting
        time.sleep(_REFRESH_TIMEOUT)


def check_addon(addon, arch, node, python, test, query, type_, version):
    """
    Check if an add-on entry matches the provided filters.

    addon -- the entry to check
    arch -- the user's architecture
    node -- the user's Node.js version
    python -- the user's Python version(s)
    test -- whether or not to include test-only add-ons
    query -- a query string
    type_ -- add-on type filter
    version -- the user's gateway version

    Returns True if the entry matches the filter, else False.
    """
    results = []

    if query is not None:
        query = query.lower().strip()
        if query not in addon['id'].lower() and \
                query not in addon['name'].lower() and \
                query not in addon['description'].lower() and \
                query not in addon['author'].lower():
            return results

    if type_ is not None:
        type_ = type_.lower().strip()
        if type_ != addon['type'].lower():
            return results

    for package in addon['packages']:
        # Verify architecture
        if arch is not None and package['architecture'] not in ['any', arch]:
            continue

        # Only adapters were supported before 0.9
        if version.major == 0 and version.minor <= 8 and \
                addon['primary_type'] != 'adapter':
            continue

        # Only adapters and notifiers were supported in 0.9
        if version.major == 0 and version.minor == 9 and \
                addon['primary_type'] not in ['adapter', 'notifier']:
            continue

        # Only check gateway version starting with 0.10, since add-ons before
        # that point were unable to indicate compatible gateway versions.
        if (version.major == 0 and version.minor >= 10) or version.major > 0:
            # Verify minimum gateway version
            if package['gateway']['min'] != '*':
                try:
                    min_gw = semver.parse_version_info(
                        package['gateway']['min']
                    )
                except ValueError:
                    continue

                if version < min_gw:
                    continue

            # Verify maximum gateway version
            if package['gateway']['max'] != '*':
                try:
                    max_gw = semver.parse_version_info(
                        package['gateway']['max']
                    )
                except ValueError:
                    continue

                if version > max_gw:
                    continue
        elif 'api' not in package:
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
        if 'test_only' in package and package['test_only'] and not test:
            continue

        results.append(package)

    return results


# Create the sanic app
app = Sanic('addon-proxy')
CORS(app)
compress = Compress()


# Serve the list
@app.route('/addons')
@compress.compress()
async def get_list(request):
    """Get the add-on list which matches a set of filters."""
    args = request.args
    ua = request.headers.get('User-Agent', None)
    _REQUESTS.append((time.time(), ua))

    # Defaults based on 0.6.X
    arch = args['arch'][0] if 'arch' in args else None
    node = args['node'][0] if 'node' in args else '57'
    python = \
        args['python'][0].split(',') if 'python' in args else ['2.7', '3.5']
    test = args['test'][0] == '1' if 'test' in args else False
    query = args['query'][0] if 'query' in args else None
    type_ = args['type'][0] if 'type' in args else None

    if 'version' in args:
        version = args['version'][0]
    elif ua is not None and (ua.startswith('mozilla-iot-gateway/') or
                             ua.startswith('webthings-gateway/')):
        version = ua.split('/')[1].split(' ')[0]
    else:
        version = '0.6.1'

    version = semver.parse_version_info(version)

    results = []
    with _LOCK:
        for addon in _LIST:
            packages = check_addon(
                addon,
                arch,
                node,
                python,
                test,
                query,
                type_,
                version,
            )

            if packages:
                if version.major == 0 and version.minor <= 6:
                    results.append({
                        'name': addon['id'],
                        'display_name': addon['name'],
                        'description': addon['description'],
                        'author': addon['author'],
                        'homepage': addon['homepage_url'],
                        'packages': {
                            package['architecture']: {
                                'version': package['version'],
                                'url': package['url'],
                                'checksum': package['checksum'],
                            } for package in packages
                        },
                        'api': 2,
                    })
                elif version.major == 0 and version.minor <= 9:
                    results.extend([
                        {
                            'name': addon['id'],
                            'display_name': addon['name'],
                            'description': addon['description'],
                            'author': addon['author'],
                            'homepage': addon['homepage_url'],
                            'license': addon['license_url'],
                            'version': package['version'],
                            'url': package['url'],
                            'checksum': package['checksum'],
                            'type': addon['primary_type'],
                        } for package in packages
                    ])
                else:
                    results.extend([
                        {
                            'id': addon['id'],
                            'name': addon['name'],
                            'description': addon['description'],
                            'author': addon['author'],
                            'homepage_url': addon['homepage_url'],
                            'license_url': addon['license_url'],
                            'version': package['version'],
                            'url': package['url'],
                            'checksum': package['checksum'],
                            'primary_type': addon['primary_type'],
                        } for package in packages
                    ])

    return response_json(results)


# License route
@app.route('/addons/license/<addon_id>')
@compress.compress()
async def get_license(request, addon_id):
    """Get the license text for a specific add-on."""
    license_url = None

    with _LOCK:
        for addon in _LIST:
            if addon['id'] == addon_id:
                license_url = addon['license_url']
                break

    if not license_url:
        return response_empty(status=404)

    try:
        r = requests.get(license_url)
        return response_text(r.text)
    except requests.exceptions.RequestException:
        return response_empty(status=500)


# Analytics route
@app.route('/addons/analytics')
@compress.compress()
async def analytics(request):
    """Return some analytics."""
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
    return response_json(requests)


# Small UI to show available add-ons
@app.route('/addons/info')
@compress.compress()
async def info(request):
    """Return an HTML page with a list of all add-ons."""
    addons = ''
    with _LOCK:
        for addon in sorted(_LIST, key=lambda e: e['name']):
            addons += _LI_TEMPLATE.format(
                name=escape_html(addon['name']),
                description=escape_html(addon['description']),
                author=escape_html(addon['author']),
                homepage=escape_html(addon['homepage_url']),
            )

    return response_html(_HTML.format(css=_CSS, addons=addons))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Add-on proxy server for WebThings Gateway'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=_DEFAULT_PORT,
        help='port for server',
    )
    parser.add_argument(
        '--repo',
        type=str,
        default=_DEFAULT_REPO,
        help='URL of git repository',
    )
    parser.add_argument(
        '--branch',
        type=str,
        default=_DEFAULT_BRANCH,
        help='branch to use from git repository',
    )
    args = parser.parse_args()

    t = Thread(target=update_list, args=(args.repo, args.branch))
    t.daemon = True
    t.start()

    # Wait for the list to be populated before starting the server
    while _LIST is None:
        time.sleep(.1)

    app.run(host='0.0.0.0', port=args.port)
