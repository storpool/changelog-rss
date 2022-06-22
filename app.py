import os
import re
import sys
import urllib.parse
import logging

from functools import reduce

from flask import Flask, abort, redirect, url_for
from pygerrit2 import GerritRestAPI, HTTPBasicAuth
from feedgen.feed import FeedGenerator

fg = FeedGenerator()
app = Flask(__name__)
app.logger.setLevel(logging.DEBUG)

change_id_blacklist = ["Iceab8ffe2b0e6e0ea074ca7da0743562d8d30f04"]
revision_pattern = re.compile(r"[0-9]{2}\.[0-9]{2}\.[0-9]{1,5}\.[0-9a-f]{9}")
public_change_pattern = re.compile(r"- .*")
private_change_pattern = re.compile(r"\.\. ([0-9]{2}\.[0-9]{2}\.[0-9]{1,5}\.)?[0-9a-f]{9}.*")


def reduce_diff_lines(lines: list, diff_line: dict) -> list:
    if isinstance(diff_line["b"], str) and len(diff_line["b"]):
        lines.extend(diff_line["b"])
    elif isinstance(diff_line["b"], list) and len(diff_line["b"]):
        lines.extend(filter(lambda line: len(line), diff_line["b"]))

    return lines


def cleanup_markdown(change: str) -> str:
    return change.replace('`', '')


def create_changelog_object(gerrit_client: GerritRestAPI, gerrit_change: dict) -> dict:
    revision_id = list(gerrit_change["revisions"].keys())[0]
    file_path = list(gerrit_change["revisions"][revision_id]["files"].keys())[0]
    diff = gerrit_client.get(
        "/changes/" + gerrit_change["id"] + "/revisions/" + revision_id + "/files/" + urllib.parse.quote_plus(
            file_path) + "/diff?whitespace=IGNORE_LEADING_AND_TRAILING")
    change_lines_all = reduce(reduce_diff_lines, filter(lambda line: "b" in line, diff["content"]), [])

    changelog = {
        "revision": None,
        "release_date": gerrit_change["updated"],
        "public_changes": [],
        "private_changes": []
    }

    try:
        change_lines_start_index = \
            [change_lines_all.index(line) for line in change_lines_all if ".. _changelog_" in line][0]

        if len(change_lines_all[change_lines_start_index:]) > 3:
            change_lines = change_lines_all[change_lines_start_index:]
        else:
            change_lines = change_lines_all
    except IndexError:
        app.logger.warning(f"Could not find the _changelog delimiter for change {gerrit_change['_number']}, starting "
                           f"from the begging of the diff")
        change_lines = change_lines_all

    for line in change_lines:
        revision_match = revision_pattern.search(line)
        if revision_match is not None:
            changelog["revision"] = revision_match[0]

        public_change_match = public_change_pattern.search(line)

        if public_change_match is not None:
            changelog["public_changes"].append(public_change_match.string)

        private_change_match = private_change_pattern.search(line)

        if private_change_match is not None:
            changelog["private_changes"].append(private_change_match.string)

    if changelog["revision"] is None:
        try:
            if len(changelog["private_changes"]):
                changelog["revision"] = revision_pattern.search(changelog["private_changes"][0])[0]
        except Exception as e:
            app.logger.exception(e)
            return None

    return changelog


def build_feed():
    try:
        gerrit_auth = HTTPBasicAuth(os.environ.get('GERRIT_USERNAME'), os.environ.get('GERRIT_PASSWORD'))
        gerrit_client = GerritRestAPI(os.environ.get('GERRIT_URL'), auth=gerrit_auth, verify=False)
    except KeyError as e:
        app.logger.exception(e)
        sys.exit(1)

    changes = gerrit_client.get("changes/?q=changelog-19+up&o=CURRENT_REVISION&o=CURRENT_FILES")
    for change in filter(lambda element: element["change_id"] not in change_id_blacklist, changes):
        changelog = create_changelog_object(gerrit_client, change)
        feed_entry = fg.add_entry()
        feed_entry.author({"name": "StorPool QA Team", "email": "support@storpool.com"})


@app.route('/rebuild', methods=['POST'])
def rebuild_feed():
    try:
        build_feed()
    except Exception as e:
        app.logger.exception(e)
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
