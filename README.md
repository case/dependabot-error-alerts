# Dependabot Error Alerts

[![Tests](https://github.com/case/dependabot-error-alerts/actions/workflows/tests.yml/badge.svg)](https://github.com/case/dependabot-error-alerts/actions/workflows/tests.yml)

A GitHub Action that checks for Dependabot workflow failures, and provides outputs for alerting.

It is a [composite action](https://docs.github.com/en/actions/tutorials/create-actions/create-a-composite-action) that runs a single standard-library Python script, so it needs Python 3.12 or newer as the runner's default `python3` (or `python` on Windows). `ubuntu-slim`, `ubuntu-24.04` and later, and current macOS and Windows runners have it. On older images such as `ubuntu-22.04` (Python 3.10), add an [`actions/setup-python`](https://github.com/actions/setup-python) step first.

## Why?

[Dependabot](https://github.com/dependabot) is a fantastic tool, but as of 2025-December, it lacks a critical feature: alerts for failures. It fails silently, which is a problem if you rely on it to keep your dependencies current.

[Here's a `dependabot-core` issue](https://github.com/dependabot/dependabot-core/issues/3509) filed in 2021, calling this out and asking for a solution.

Since [Dependabot now runs via GitHub Actions](https://github.blog/news-insights/product-news/dependabot-on-github-actions-and-self-hosted-runners-is-now-generally-available/), we can query the Actions API for failed runs, and alert accordingly.

## Usage

```yaml
name: Check Dependabot

on:
  schedule:
    - cron: '0 9 * * 1'  # Weekly on Monday at 9am
  workflow_dispatch: # Web trigger

permissions:
  actions: read

jobs:
  check:
    runs-on: ubuntu-slim

    steps:
      - name: Check for Dependabot failures
        id: check
        uses: case/dependabot-error-alerts@v2
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          lookback_days: '7' # Check for Dependabot failures from the past 7 days

      - name: Send notification
        if: steps.check.outputs.has_failures == 'true'
        run: |
          echo "Found ${{ steps.check.outputs.failure_count }} Dependabot failure(s)"
          # Add your notification logic here (Slack, email, etc.)
```

## Inputs

| Input | Description | Required | Default |
|-------|-------------|----------|---------|
| `github_token` | GitHub token for API access | Yes | `${{ github.token }}` |
| `lookback_days` | Number of days to look back for failures | No | `7` |
| `fail_on_error` | Fail the action if Dependabot failures are found | No | `false` |

## Outputs

| Output | Description |
|--------|-------------|
| `failure_count` | Number of Dependabot workflow failures found |
| `has_failures` | Whether any failures were found (`true`/`false`) |
| `failures_json` | JSON array of failure details (`id`, `name`, `html_url`, `created_at`) |

## Upgrading from v1

v2 replaces the TypeScript implementation with a standard-library Python script. The inputs and outputs are unchanged. Differences:

- The runner needs Python 3.12 or newer (`python3`, or `python` on Windows).
- Up to 1,000 failed runs in the lookback period are returned, which is GitHub's limit for this API query. v1 returned at most 30.
- `lookback_days` must be a whole positive number. v1 accepted values such as `7abc`.

## FAQ

**I have a failed Dependabot job, how do I debug it?**

Debugging failed Dependabot jobs is not in scope here - this tool is essentially a very simple failed Dependabot job detector. In my experience, the errors are often transient (e.g. due to network connectivity issues with upstream container image registries, etc.) - but sometimes they are due to typos or syntactic issues in manifest files like `package.json` and `go.mod`. Doing a web search for the error message will usually help you find other folks who've encountered the same issue already.

**Will this tool duplicate notifications for failed Dependabot jobs?**

Yes, this tool is "dumb" in the sense that it's only checking for the presence of _any_ failed Dependabot job during the lookback period. It isn't tracking any detection state or notification history. If that seems like a desirable feature to add, we could probably do it with [`actions/upload-artifact`](https://docs.github.com/en/actions/tutorials/store-and-share-data) - e.g. by storing the failed job ID.

## Alternatives

You don't actually need a fully fledged third-party Action from the Marketplace to do this - the `gh` CLI can easily access the same data as this action. Here's a prototype that you could save as a [composite action](https://docs.github.com/en/actions/tutorials/create-actions/create-a-composite-action), e.g. in your `.github/actions/dependabot-error-alerts/action.yaml`. It does roughly the same things as this action, but lacks the tests, etc.

```yaml
name: 'Dependabot Error Alerts'
description: 'Detect failed Dependabot update jobs and get failure details for alerting'
author: 'github.com/case'

branding:
  icon: 'alert-triangle'
  color: 'orange'

inputs:
  lookback_days:
    description: 'Days to look back for failures (1 = daily, 7 = weekly, 30 = monthly)'
    required: false
    default: '7'
  repo:
    description: 'Repository to check (owner/repo format). Defaults to current repository.'
    required: false
    default: ''

outputs:
  has_failures:
    description: 'Whether any Dependabot failures were found (true/false)'
    value: ${{ steps.check.outputs.has_failures }}
  failure_count:
    description: 'Number of Dependabot failures found'
    value: ${{ steps.check.outputs.failure_count }}

runs:
  using: 'composite'
  steps:
    - name: Check for Dependabot failures
      id: check
      shell: bash
      env:
        INPUT_LOOKBACK_DAYS: ${{ inputs.lookback_days }}
        INPUT_REPO: ${{ inputs.repo }}
        GITHUB_REPOSITORY: ${{ github.repository }}
      run: |
        # Determine which repo to check
        REPO="${INPUT_REPO}"
        if [ -z "$REPO" ]; then
          REPO="${GITHUB_REPOSITORY}"
        fi

        LOOKBACK_DAYS="${INPUT_LOOKBACK_DAYS:-7}"

        echo "Checking repository: $REPO"
        echo "Lookback period: ${LOOKBACK_DAYS} day(s)"

        # Calculate the timestamp for filtering
        SINCE=$(date -u -d "${LOOKBACK_DAYS} days ago" +%Y-%m-%dT%H:%M:%SZ)
        echo "Looking for failures since: $SINCE"

        # Get failed Dependabot runs from the last N days
        FAILURES=$(gh run list \
          --repo "$REPO" \
          --workflow "Dependabot Updates" \
          --json conclusion,createdAt,databaseId,displayTitle \
          --jq "[.[] | select(.conclusion == \"failure\" and .createdAt >= \"${SINCE}\") | {displayTitle, createdAt, runId: .databaseId, url: \"https://github.com/${REPO}/actions/runs/\(.databaseId)\"}]")

        COUNT=$(echo "$FAILURES" | jq 'length')

        echo "Found $COUNT Dependabot failure(s)"

        # Set outputs
        echo "failure_count=${COUNT}" >> $GITHUB_OUTPUT

        if [ "$COUNT" -gt 0 ]; then
          echo "has_failures=true" >> $GITHUB_OUTPUT
          echo ""
          echo "=== Failed Runs ==="
          echo "$FAILURES" | jq -r '.[] | "- \(.displayTitle)\n  Created: \(.createdAt)\n  URL: \(.url)\n"'
        else
          echo "has_failures=false" >> $GITHUB_OUTPUT
          echo "No Dependabot failures in the last ${LOOKBACK_DAYS} day(s)"
        fi
```

## Development

- `bin/setup` - runs `mise install` if mise is present, and checks for Python 3.12+ and the lint tools pinned in `mise.toml`
- `bin/lint` - runs `ruff check`, `ruff format --check`, `jactionlint`, and `shellcheck`. Fix formatting with `ruff format`
- `bin/test` - runs the unit tests with the standard library `unittest`
- `bin/ci` - runs all of the above, as CI does
- `bin/test-dependabot-fixture` - runs a real Dependabot gomod update (via Docker and the Dependabot CLI) against the fixture below, and checks it fails to parse. CI runs it weekly

`tests/fixtures/dependabot-failure/go.mod` is deliberately broken, so that Dependabot fails every week and the end-to-end test has a failure to find.

## License

MIT
