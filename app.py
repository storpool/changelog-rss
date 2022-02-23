import os
import sys
import urllib.parse

from flask import Flask, abort, redirect, url_for
from pygerrit2 import GerritRestAPI, HTTPBasicAuth
from feedgen.feed import FeedGenerator

app = Flask(__name__)
fg = FeedGenerator()


def cleanup_markdown(change: str) -> str:
    return change.replace('`', '')


def create_changelog_object(gerrit_client: GerritRestAPI, gerrit_change: dict) -> dict:
    revision_id = list(gerrit_change["revisions"].keys())[0]
    file_name = list(gerrit_change["revisions"][revision_id]["files"].keys())[0]
    diff = gerrit_client.get("/changes/" + gerrit_change["id"] + "/revisions/" + revision_id + "/files/" + urllib.parse.quote_plus(file_name) + "/diff")
    change_lines = list(filter(lambda line: len(line), diff["content"][1]["b"]))

    changelog = {
        "revision": change_lines[1].split(" ")[2],
        "release_date": change_lines[3],
        "public_changes": [],
        "private_changes": []
    }

    private_changes_delimiter_line_index = [change_lines.index(line) for line in change_lines if ".. revision" in line][0]
    public_lines_slice = change_lines[4:private_changes_delimiter_line_index]
    private_lines_slice = change_lines[private_changes_delimiter_line_index+1:]

    for line in public_lines_slice:
        changelog["public_changes"].append(cleanup_markdown(line))

    return changelog


def build_feed():
    try:
        gerrit_auth = HTTPBasicAuth(os.environ.get('GERRIT_USERNAME'), os.environ.get('GERRIT_USERNAME'))
        gerrit_client = GerritRestAPI(os.environ.get('GERRIT_URL'), auth=gerrit_auth, verify=False)
    except KeyError as e:
        sys.exit(1)

    changes = gerrit_client.get("changes/?q=changelog-19:+and+status:merged&o=CURRENT_REVISION&o=CURRENT_FILES")
    for change in changes:
        changelog = create_changelog_object(gerrit_client, change)
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
