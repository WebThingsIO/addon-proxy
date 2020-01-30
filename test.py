#!/usr/bin/env python3

"""Test the add-on proxy server."""

from urllib.request import Request, urlopen
import json
import os
import subprocess
import sys
import time


def start_server():
    """Start up the proxy server."""
    args = [
        sys.executable,
        os.path.realpath(os.path.join(os.path.dirname(__file__), 'addon-proxy.py')),  # noqa
        '--port',
        '8080',
    ]

    if 'LIST_REPO' in os.environ:
        args.extend(['--repo', os.environ['LIST_REPO']])

    if 'LIST_BRANCH' in os.environ:
        args.extend(['--branch', os.environ['LIST_BRANCH']])

    return subprocess.Popen(args, stdout=sys.stdout, stderr=sys.stderr)


def request_list(version):
    """
    Request the add-on list from the server.

    version -- gateway version to simulate

    Returns the list.
    """
    arch = 'linux-arm'
    node_version = '57'
    py_versions = '2.7,3.5'

    url = 'http://localhost:8080/addons?arch={}&node={}&python={}&version={}'.format(  # noqa
        arch,
        node_version,
        py_versions,
        version,
    )

    r = Request(url, headers={'Accept': 'application/json'})
    f = urlopen(r)
    return json.load(f)


def test_0_6_1():
    """Test as gateway version 0.6.1."""
    addons = request_list('0.6.1')

    assert len(addons) > 0

    addon = addons[0]

    assert 'name' in addon and addon['name']
    assert 'display_name' in addon and addon['display_name']
    assert 'description' in addon and addon['description']
    assert 'author' in addon and addon['author']
    assert 'homepage' in addon and addon['homepage']
    assert 'packages' in addon and addon['packages']

    packages = addon['packages']

    package = None
    if 'linux-arm' in packages:
        package = packages['linux-arm']
    elif 'any' in packages:
        package = packages['any']

    assert package is not None
    assert 'version' in package and package['version']
    assert 'url' in package and package['url']
    assert 'checksum' in package and package['checksum']


def test_0_9_2():
    """Test as gateway version 0.9.2."""
    addons = request_list('0.9.2')

    assert len(addons) > 0

    addon = addons[0]

    assert 'name' in addon and addon['name']
    assert 'display_name' in addon and addon['display_name']
    assert 'description' in addon and addon['description']
    assert 'author' in addon and addon['author']
    assert 'homepage' in addon and addon['homepage']
    assert 'license' in addon and addon['license']
    assert 'version' in addon and addon['version']
    assert 'url' in addon and addon['url']
    assert 'checksum' in addon and addon['checksum']
    assert 'type' in addon and addon['type']


def test_0_10_0():
    """Test as gateway version 0.10.0."""
    addons = request_list('0.10.0')

    assert len(addons) > 0

    addon = addons[0]

    assert 'id' in addon and addon['id']
    assert 'name' in addon and addon['name']
    assert 'description' in addon and addon['description']
    assert 'author' in addon and addon['author']
    assert 'homepage_url' in addon and addon['homepage_url']
    assert 'license_url' in addon and addon['license_url']
    assert 'version' in addon and addon['version']
    assert 'url' in addon and addon['url']
    assert 'checksum' in addon and addon['checksum']
    assert 'primary_type' in addon and addon['primary_type']


if __name__ == '__main__':
    # Start the server
    p = start_server()

    # Wait a few seconds for things to start up
    time.sleep(5)

    # Test different output formats
    test_0_6_1()
    test_0_9_2()
    test_0_10_0()

    # Kill the server
    p.terminate()
