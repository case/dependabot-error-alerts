/**
 * Main entry point for the GitHub Action.
 * Reads inputs, runs the Dependabot failure check, and sets outputs.
 */

import * as core from '@actions/core'
import { getOctokit, context } from '@actions/github'
import { checkDependabotFailures } from './check-dependabot.js'

export async function run(): Promise<void> {
  // Read and validate action inputs
  const token = core.getInput('github_token', { required: true })
  const lookbackDaysInput = core.getInput('lookback_days') || '7'
  const lookbackDays = parseInt(lookbackDaysInput, 10)
  if (isNaN(lookbackDays) || lookbackDays < 1) {
    throw new Error(`Invalid lookback_days: "${lookbackDaysInput}" - must be a positive integer`)
  }
  const failOnError = core.getInput('fail_on_error') === 'true'

  // Initialize GitHub API client and get repo context
  const octokit = getOctokit(token)
  const { owner, repo } = context.repo

  // Check for Dependabot failures
  const result = await checkDependabotFailures(octokit, {
    owner,
    repo,
    lookbackDays,
  })

  // Set action outputs for use by subsequent workflow steps
  core.setOutput('failure_count', result.failureCount)
  core.setOutput('has_failures', result.hasFailures ? 'true' : 'false')
  core.setOutput('failures_json', JSON.stringify(result.failures))

  // Log results and optionally fail the action
  if (result.hasFailures) {
    core.warning(`Found ${result.failureCount} Dependabot workflow failure(s)`)
    for (const failure of result.failures) {
      core.warning(`  - ${failure.name}: ${failure.html_url}`)
    }

    if (failOnError) {
      core.setFailed(`Found ${result.failureCount} Dependabot workflow failure(s)`)
    }
  } else {
    core.info('No Dependabot workflow failures found')
  }
}
