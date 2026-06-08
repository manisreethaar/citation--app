"""
push_to_github.py
==================
Pushes all v2 files to github.com/manisreethaar/citation--app
under a v2/ subfolder using the GitHub REST API.

Usage:
  python push_to_github.py --token YOUR_PAT

Get a PAT at: GitHub → Settings → Developer settings →
              Personal access tokens → repo scope
"""

import argparse
import base64
import json
import os
import urllib.request
import urllib.error
from pathlib import Path

OWNER = "manisreethaar"
REPO  = "citation--app"
BRANCH = "main"

# Files to push (relative to this script's directory → uploaded to v2/ in repo)
FILES = [
    "document_model.py",
    "reference_model.py",
    "scoring_engine.py",
    "citation_inventory.py",
    "coverage_audit.py",
    "style_engine.py",
    "pipeline.py",
    "file_io.py",
    "cli.py",
    "app.py",
    "requirements.txt",
]


def api_request(url: str, token: str, data: dict = None, method: str = "GET"):
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "auto-citer-pusher",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read()), resp.status
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        return json.loads(body) if body else {}, e.code


def get_existing_sha(path: str, token: str) -> str | None:
    """Return SHA of existing file (needed to update), or None if new."""
    url = f"https://api.github.com/repos/{OWNER}/{REPO}/contents/{path}?ref={BRANCH}"
    data, status = api_request(url, token)
    if status == 200:
        return data.get("sha")
    return None


def push_file(local_path: str, repo_path: str, token: str, message: str):
    content = Path(local_path).read_bytes()
    encoded = base64.b64encode(content).decode()
    sha = get_existing_sha(repo_path, token)

    payload = {
        "message": message,
        "content": encoded,
        "branch": BRANCH,
    }
    if sha:
        payload["sha"] = sha  # required for update

    url = f"https://api.github.com/repos/{OWNER}/{REPO}/contents/{repo_path}"
    data, status = api_request(url, token, payload, method="PUT")

    if status in (200, 201):
        action = "Updated" if sha else "Created"
        print(f"  ✓  {action}: {repo_path}")
    else:
        msg = data.get("message", str(data))
        print(f"  ✗  Failed {repo_path}: {status} — {msg}")


def main():
    parser = argparse.ArgumentParser(description="Push auto-citer v2 to GitHub")
    parser.add_argument("--token", "-t", required=True, help="GitHub Personal Access Token")
    args = parser.parse_args()

    base_dir = Path(__file__).parent
    token = args.token.strip()

    print(f"\nPushing to https://github.com/{OWNER}/{REPO}/tree/{BRANCH}/v2/\n")

    for filename in FILES:
        local = base_dir / filename
        if not local.exists():
            print(f"  ⚠  Skipped (not found): {filename}")
            continue
        repo_path = f"v2/{filename}"
        push_file(str(local), repo_path, token,
                  message=f"Add v2/{filename} — auto-citer rebuilt foundation")

    print(f"\nDone. View at: https://github.com/{OWNER}/{REPO}\n")


if __name__ == "__main__":
    main()
