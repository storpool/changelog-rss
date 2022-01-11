import os
import sys

from flask import Flask, abort, redirect, url_for
from pygerrit2 import GerritRestAPI, HTTPBasicAuth
from feedgen.feed import FeedGenerator

app = Flask(__name__)
fg = FeedGenerator()


def build_feed():
    try:
        gerrit_auth = HTTPBasicAuth(os.environ.get('GERRIT_USERNAME'), os.environ.get('GERRIT_USERNAME'))
        gerrit_client = GerritRestAPI(os.environ.get('GERRIT_URL'), auth=gerrit_auth, verify=False)
    except KeyError as e:
        sys.exit(1)

    changes = gerrit_client.get("changes/?q=changelog-19.01:+and+status:merged")
    for change in changes:
        feed_entry = fg.add_entry()


@app.route('/rebuild', methods=['POST'])
def rebuild_feed():
    build_feed()
    try:
        build_feed()
    except Exception:
        abort(500)
    finally:
        return "", 201


@app.route('/feed', methods=['GET'])
def get_feed():
    return fg.rss_str()


@app.route('/')
def default_route():
    return redirect(url_for('get_feed'))


if __name__ == '__main__':
    build_feed()
    app.run()
