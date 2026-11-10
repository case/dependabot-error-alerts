"""Find failed Dependabot workflow runs and report them as GitHub Action outputs."""

from __future__ import annotations

import io
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

DEFAULT_API_URL = "https://api.github.com"
DEFAULT_LOOKBACK_DAYS = 7
PER_PAGE = 100
MAX_RESULTS = 1000  # GitHub caps filtered workflow-run listings at this many results.
TIMEOUT_SECONDS = 30

Opener = Callable[..., Any]


class ActionError(Exception):
    """An error reported to the workflow as an annotation, without a traceback."""


def escape_data(value: str) -> str:
    """Escape a workflow command message so it stays on one line."""
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def annotate(level: str, message: str) -> None:
    print(f"::{level}::{escape_data(message)}")


def parse_lookback(raw: str | None) -> int:
    value = (raw or "").strip()
    if not value:
        return DEFAULT_LOOKBACK_DAYS
    try:
        days = int(value)
    except ValueError:
        days = 0
    if days < 1:
        raise ActionError(f'Invalid lookback_days: "{value}" - must be a positive integer')
    return days


def cutoff_date(lookback_days: int, today: date | None = None) -> str:
    today = today or datetime.now(UTC).date()
    try:
        return (today - timedelta(days=lookback_days)).isoformat()
    except OverflowError:
        raise ActionError(f'Invalid lookback_days: "{lookback_days}" - too large') from None


def to_failure(run: dict[str, Any]) -> dict[str, Any]:
    name = run.get("name")
    return {
        "id": run["id"],
        "name": "Unknown" if name is None else name,
        "html_url": run["html_url"],
        "created_at": run["created_at"],
    }


def _api_error(error: urllib.error.HTTPError) -> ActionError:
    detail = ""
    try:
        body = json.loads(error.read().decode("utf-8"))
        detail = f": {body.get('message', '')}" if isinstance(body, dict) else ""
    except (OSError, ValueError):
        pass
    finally:
        error.close()
    return ActionError(f"GitHub API request failed: {error.code} {error.reason}{detail}")


def fetch_failures(
    api_url: str,
    repo: str,
    token: str,
    created_since: str,
    opener: Opener | None = None,
) -> list[dict[str, Any]]:
    """Return failed Dependabot runs created on or after created_since, up to MAX_RESULTS."""
    opener = opener or urllib.request.urlopen
    failures: list[dict[str, Any]] = []
    page = 1
    while True:
        query = urllib.parse.urlencode(
            {
                "actor": "dependabot[bot]",
                "status": "failure",
                "created": f">={created_since}",
                "per_page": PER_PAGE,
                "page": page,
            }
        )
        request = urllib.request.Request(  # noqa: S310 - api_url comes from the runner
            f"{api_url.rstrip('/')}/repos/{repo}/actions/runs?{query}",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "User-Agent": "dependabot-error-alerts",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with opener(request, timeout=TIMEOUT_SECONDS) as response:
                runs = json.loads(response.read().decode("utf-8"))["workflow_runs"]
        except urllib.error.HTTPError as error:
            raise _api_error(error) from None
        except urllib.error.URLError as error:
            raise ActionError(f"GitHub API request failed: {error.reason}") from None
        failures.extend(to_failure(run) for run in runs)
        if len(runs) < PER_PAGE or page * PER_PAGE >= MAX_RESULTS:
            return failures
        page += 1


def write_outputs(outputs: dict[str, str], path: str | None) -> None:
    lines = "".join(f"{key}={value}\n" for key, value in outputs.items())
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(lines)
    else:
        print(lines, end="")


def run(env: dict[str, str], opener: Opener | None = None) -> int:
    token = env.get("INPUT_GITHUB_TOKEN", "").strip()
    if not token:
        raise ActionError("Input required and not supplied: github_token")
    repo = env.get("GITHUB_REPOSITORY", "").strip()
    if not repo:
        raise ActionError("GITHUB_REPOSITORY is not set")
    lookback_days = parse_lookback(env.get("INPUT_LOOKBACK_DAYS"))
    fail_on_error = env.get("INPUT_FAIL_ON_ERROR", "").strip() == "true"
    api_url = env.get("GITHUB_API_URL") or DEFAULT_API_URL

    failures = fetch_failures(api_url, repo, token, cutoff_date(lookback_days), opener)
    count = len(failures)
    write_outputs(
        {
            "failure_count": str(count),
            "has_failures": "true" if failures else "false",
            "failures_json": json.dumps(failures, separators=(",", ":")),
        },
        env.get("GITHUB_OUTPUT"),
    )

    if not failures:
        print("No Dependabot workflow failures found")
        return 0
    annotate("warning", f"Found {count} Dependabot workflow failure(s)")
    for failure in failures:
        annotate("warning", f"  - {failure['name']}: {failure['html_url']}")
    if fail_on_error:
        annotate("error", f"Found {count} Dependabot workflow failure(s)")
        return 1
    return 0


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")
    try:
        return run(dict(os.environ))
    except ActionError as error:
        annotate("error", str(error))
        return 1


if __name__ == "__main__":
    sys.exit(main())
