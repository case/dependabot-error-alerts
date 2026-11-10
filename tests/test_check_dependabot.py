import io
import json
import tempfile
import unittest
import unittest.mock
import urllib.error
import urllib.parse
from contextlib import redirect_stdout
from datetime import date
from email.message import Message
from pathlib import Path

import check_dependabot as cd

FIXTURES = Path(__file__).parent / "fixtures"
FAILURES = json.loads((FIXTURES / "workflow-runs-failures.json").read_text())
EMPTY = json.loads((FIXTURES / "workflow-runs-empty.json").read_text())


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class FakeOpener:
    """Serves one JSON payload per request, in order, and records each request."""

    def __init__(self, *payloads):
        self.payloads = list(payloads)
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append(request)
        payload = self.payloads.pop(0)
        if isinstance(payload, Exception):
            raise payload
        return FakeResponse(json.dumps(payload).encode())

    def query(self, index=0):
        url = urllib.parse.urlsplit(self.requests[index].full_url)
        return dict(urllib.parse.parse_qsl(url.query))


def runs_page(count, start=0):
    return {
        "total_count": count,
        "workflow_runs": [
            {
                "id": start + i,
                "name": f"run {start + i}",
                "html_url": f"https://github.com/o/r/actions/runs/{start + i}",
                "created_at": "2026-11-01T00:00:00Z",
            }
            for i in range(count)
        ],
    }


def fixture_failures():
    return [
        {k: run[k] for k in ("id", "name", "html_url", "created_at")}
        for run in FAILURES["workflow_runs"]
    ]


class FetchFailuresTest(unittest.TestCase):
    def fetch(self, opener, api_url="https://api.github.com"):
        return cd.fetch_failures(
            api_url, "case/dependabot-error-alerts", "t0k", "2026-11-03", opener
        )

    def test_finds_failures(self):
        self.assertEqual(self.fetch(FakeOpener(FAILURES)), fixture_failures())

    def test_returns_empty_when_no_failures(self):
        self.assertEqual(self.fetch(FakeOpener(EMPTY)), [])

    def test_query_filters_dependabot_failures_since_cutoff(self):
        opener = FakeOpener(EMPTY)
        self.fetch(opener)
        request = opener.requests[0]
        self.assertTrue(
            request.full_url.startswith(
                "https://api.github.com/repos/case/dependabot-error-alerts/actions/runs?"
            )
        )
        self.assertEqual(
            opener.query(),
            {
                "actor": "dependabot[bot]",
                "status": "failure",
                "created": ">=2026-11-03",
                "per_page": "100",
                "page": "1",
            },
        )
        self.assertEqual(request.get_header("Authorization"), "Bearer t0k")

    def test_paginates_until_a_short_page(self):
        opener = FakeOpener(runs_page(100), runs_page(5, start=100))
        failures = self.fetch(opener)
        self.assertEqual(len(failures), 105)
        self.assertEqual([opener.query(i)["page"] for i in range(2)], ["1", "2"])

    def test_paginates_past_a_full_last_page(self):
        opener = FakeOpener(runs_page(100), EMPTY)
        self.assertEqual(len(self.fetch(opener)), 100)
        self.assertEqual(len(opener.requests), 2)

    def test_stops_at_github_result_cap(self):
        pages = [runs_page(100, start=100 * i) for i in range(11)]
        opener = FakeOpener(*pages)
        self.assertEqual(len(self.fetch(opener)), 1000)
        self.assertEqual(len(opener.requests), 10)

    def test_uses_enterprise_api_url(self):
        opener = FakeOpener(EMPTY)
        self.fetch(opener, api_url="https://ghe.example.com/api/v3/")
        self.assertTrue(
            opener.requests[0].full_url.startswith("https://ghe.example.com/api/v3/repos/")
        )

    def test_http_error_reports_status_and_message(self):
        body = io.BytesIO(b'{"message": "API rate limit exceeded"}')
        error = urllib.error.HTTPError("u", 403, "Forbidden", Message(), body)
        with self.assertRaisesRegex(cd.ActionError, "403 Forbidden: API rate limit exceeded"):
            self.fetch(FakeOpener(error))
        self.assertTrue(body.closed, "the HTTP error response must be closed")

    def test_network_error_is_reported(self):
        with self.assertRaisesRegex(cd.ActionError, "request failed: boom"):
            self.fetch(FakeOpener(urllib.error.URLError("boom")))


class ToFailureTest(unittest.TestCase):
    def run_with_name(self, name):
        return cd.to_failure({"id": 1, "name": name, "html_url": "u", "created_at": "c"})

    def test_null_name_becomes_unknown(self):
        self.assertEqual(self.run_with_name(None)["name"], "Unknown")

    def test_empty_name_is_kept(self):
        self.assertEqual(self.run_with_name("")["name"], "")


class InputParsingTest(unittest.TestCase):
    def test_lookback_defaults_when_empty_or_blank(self):
        self.assertEqual(cd.parse_lookback(None), 7)
        self.assertEqual(cd.parse_lookback("  "), 7)

    def test_lookback_is_trimmed(self):
        self.assertEqual(cd.parse_lookback(" 30 "), 30)

    def test_invalid_lookback_rejected(self):
        for raw in ("not-a-number", "0", "-1", "7abc", "1.5"):
            with (
                self.subTest(raw=raw),
                self.assertRaisesRegex(cd.ActionError, "Invalid lookback_days"),
            ):
                cd.parse_lookback(raw)

    def test_cutoff_date(self):
        self.assertEqual(cd.cutoff_date(3, today=date(2026, 11, 10)), "2026-11-07")

    def test_oversized_lookback_is_an_input_error(self):
        with self.assertRaisesRegex(cd.ActionError, "too large"):
            cd.cutoff_date(10**9)


class EscapeDataTest(unittest.TestCase):
    def test_newlines_and_percent_escaped(self):
        self.assertEqual(cd.escape_data("a%b\r\n::warning::x"), "a%25b%0D%0A::warning::x")


class RunTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.output_path = Path(tmp.name) / "output"
        self.env = {
            "INPUT_GITHUB_TOKEN": "t0k",
            "INPUT_LOOKBACK_DAYS": "7",
            "INPUT_FAIL_ON_ERROR": "false",
            "GITHUB_REPOSITORY": "case/dependabot-error-alerts",
            "GITHUB_OUTPUT": str(self.output_path),
        }

    def run_action(self, payload, **env):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = cd.run({**self.env, **env}, FakeOpener(payload))
        return code, stdout.getvalue()

    def outputs(self):
        lines = self.output_path.read_text(encoding="utf-8").splitlines()
        return dict(line.split("=", 1) for line in lines)

    def test_sets_outputs_when_failures_exist(self):
        code, log = self.run_action(FAILURES)
        self.assertEqual(code, 0)
        self.assertEqual(
            self.outputs(),
            {
                "failure_count": "3",
                "has_failures": "true",
                "failures_json": json.dumps(fixture_failures(), separators=(",", ":")),
            },
        )
        self.assertIn("::warning::Found 3 Dependabot workflow failure(s)", log)

    def test_sets_outputs_when_no_failures(self):
        code, log = self.run_action(EMPTY)
        self.assertEqual(code, 0)
        self.assertEqual(
            self.outputs(),
            {"failure_count": "0", "has_failures": "false", "failures_json": "[]"},
        )
        self.assertIn("No Dependabot workflow failures found", log)

    def test_fail_on_error_fails_when_failures_exist(self):
        code, log = self.run_action(FAILURES, INPUT_FAIL_ON_ERROR=" true ")
        self.assertEqual(code, 1)
        self.assertIn("::error::Found 3 Dependabot workflow failure(s)", log)

    def test_fail_on_error_ignored_without_failures(self):
        code, _ = self.run_action(EMPTY, INPUT_FAIL_ON_ERROR="true")
        self.assertEqual(code, 0)

    def test_only_exact_true_enables_fail_on_error(self):
        code, _ = self.run_action(FAILURES, INPUT_FAIL_ON_ERROR="yes")
        self.assertEqual(code, 0)

    def test_failure_names_cannot_inject_workflow_commands(self):
        payload = runs_page(1)
        payload["workflow_runs"][0]["name"] = "evil\n::error::injected ✨"
        _, log = self.run_action(payload)
        self.assertNotIn("\n::error::", log)
        self.assertIn("evil%0A::error::injected ✨", log)

    def test_unicode_written_to_output_file(self):
        payload = runs_page(1)
        payload["workflow_runs"][0]["name"] = "npm ✨ 更新"
        self.run_action(payload)
        self.assertIn("npm ✨ 更新", json.loads(self.outputs()["failures_json"])[0]["name"])

    def test_prints_outputs_without_output_file(self):
        env = {k: v for k, v in self.env.items() if k != "GITHUB_OUTPUT"}
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            cd.run(env, FakeOpener(EMPTY))
        self.assertIn("has_failures=false\n", stdout.getvalue())

    def test_missing_token_is_an_error(self):
        with self.assertRaisesRegex(cd.ActionError, "github_token"):
            self.run_action(EMPTY, INPUT_GITHUB_TOKEN=" ")

    def test_invalid_lookback_is_an_error(self):
        with self.assertRaisesRegex(cd.ActionError, "Invalid lookback_days"):
            self.run_action(EMPTY, INPUT_LOOKBACK_DAYS="0")


class MainTest(unittest.TestCase):
    def test_success_path_writes_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "output"
            env = {
                "INPUT_GITHUB_TOKEN": "t",
                "INPUT_LOOKBACK_DAYS": "",
                "GITHUB_REPOSITORY": "o/r",
                "GITHUB_OUTPUT": str(output),
            }
            stdout = io.StringIO()
            with (
                unittest.mock.patch.dict("os.environ", env, clear=True),
                unittest.mock.patch("urllib.request.urlopen", FakeOpener(FAILURES)),
                redirect_stdout(stdout),
            ):
                code = cd.main()
            self.assertEqual(code, 0)
            self.assertIn("has_failures=true\n", output.read_text(encoding="utf-8"))

    def test_action_error_becomes_single_error_annotation(self):
        env = {
            "INPUT_GITHUB_TOKEN": "t",
            "GITHUB_REPOSITORY": "o/r",
            "INPUT_LOOKBACK_DAYS": "x\n::warning::y",
        }
        stdout = io.StringIO()
        with (
            unittest.mock.patch.dict("os.environ", env, clear=True),
            redirect_stdout(stdout),
        ):
            code = cd.main()
        self.assertEqual(code, 1)
        self.assertEqual(stdout.getvalue().count("\n"), 1)
        self.assertTrue(stdout.getvalue().startswith("::error::Invalid lookback_days"))


if __name__ == "__main__":
    unittest.main()
