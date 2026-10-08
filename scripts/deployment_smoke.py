"""Small stdlib-only smoke test for the core container deployment."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path


def request(base_url: str, path: str, method: str = "GET", payload: dict | None = None, token: str | None = None) -> dict:
    body = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request_object = urllib.request.Request(f"{base_url.rstrip('/')}{path}", data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request_object, timeout=10) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{method} {path} returned HTTP {exc.code}") from exc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--token-file")
    args = parser.parse_args()

    ready = request(args.base_url, "/ready")
    if ready.get("status") != "ready":
        raise RuntimeError("deployment is not ready")

    if args.token_file and Path(args.token_file).is_file():
        with open(args.token_file, encoding="utf-8") as token_handle:
            token = token_handle.read().strip()
    else:
        identifier = f"ci-{uuid.uuid4().hex[:12]}@example.test"
        password = "deployment-smoke-password"
        request(args.base_url, "/api/auth/register", "POST", {"identifier": identifier, "password": password})
        token = request(args.base_url, "/api/auth/login", "POST", {"identifier": identifier, "password": password})["access_token"]
        if args.token_file:
            with open(args.token_file, "w", encoding="utf-8") as output:
                output.write(token)
        request(args.base_url, "/api/tasks", "POST", {"title": "deployment smoke task", "duration_minutes": 30}, token)

    tasks = request(args.base_url, "/api/tasks", token=token)
    if not any(task.get("title") == "deployment smoke task" for task in tasks):
        raise RuntimeError("persistent smoke task was not returned")
    print("deployment smoke passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, ValueError) as exc:
        print(f"deployment smoke failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
