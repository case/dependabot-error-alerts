# Dependabot Error Alerts

[![Tests](https://github.com/case/dependabot-error-alerts/actions/workflows/tests.yml/badge.svg)](https://github.com/case/dependabot-error-alerts/actions/workflows/tests.yml)

A GitHub Action that checks for Dependabot workflow failures, and provides outputs for alerting.

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

jobs:
  check:
    runs-on: ubuntu-slim

    steps:
      - name: Check for Dependabot failures
        id: check
        uses: case/dependabot-error-alerts@v1
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

## License

MIT
