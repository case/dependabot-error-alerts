/**
 * Core logic for checking Dependabot workflow failures.
 * This module queries the GitHub Actions API to find failed workflow runs triggered by Dependabot within a specified time period.
 */

import type { GitHub } from '@actions/github/lib/utils.js'

// Options for the Dependabot failure check
export interface CheckOptions {
  owner: string
  repo: string
  lookbackDays: number
}

// Represents a single failed workflow run
export interface WorkflowRunFailure {
  id: number
  name: string
  html_url: string
  created_at: string
}

// Result of the Dependabot failure check
export interface CheckResult {
  failureCount: number
  hasFailures: boolean
  failures: WorkflowRunFailure[]
}

/**
 * Queries the GitHub Actions API for Dependabot workflow failures.
 * Filters by actor (`dependabot[bot]`), status (`failure`), and created date.
 */
export async function checkDependabotFailures(
  octokit: InstanceType<typeof GitHub>,
  options: CheckOptions
): Promise<CheckResult> {
  const { owner, repo, lookbackDays } = options

  // Build the date filter for the lookback period (e.g., ">=2025-01-01")
  const lookbackDate = new Date()
  lookbackDate.setDate(lookbackDate.getDate() - lookbackDays)
  const created = `>=${lookbackDate.toISOString().split('T')[0]}`

  // Query the GitHub API for failed Dependabot workflow runs
  const response = await octokit.rest.actions.listWorkflowRunsForRepo({
    owner,
    repo,
    actor: 'dependabot[bot]',
    status: 'failure',
    created,
  })

  // Extract the relevant fields from each workflow run
  const failures: WorkflowRunFailure[] = response.data.workflow_runs.map((run) => ({
    id: run.id,
    name: run.name ?? 'Unknown',
    html_url: run.html_url,
    created_at: run.created_at,
  }))

  return {
    failureCount: failures.length,
    hasFailures: failures.length > 0,
    failures,
  }
}
