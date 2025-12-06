import { describe, it, expect, vi, beforeEach } from 'vitest'
import * as core from '@actions/core'
import { run } from '../src/main.js'

import failuresFixture from './fixtures/workflow-runs-failures.json'
import type { CheckResult } from '../src/check-dependabot.js'

vi.mock('@actions/core')
vi.mock('@actions/github', () => ({
  getOctokit: vi.fn(),
  context: {
    repo: {
      owner: 'case',
      repo: 'dependabot-error-alerts',
    },
  },
}))

vi.mock('../src/check-dependabot.js', () => ({
  checkDependabotFailures: vi.fn(),
}))

import { checkDependabotFailures } from '../src/check-dependabot.js'
import { getOctokit } from '@actions/github'

// Derive test data from fixtures
const fixtureFailures = failuresFixture.workflow_runs.map((run) => ({
  id: run.id,
  name: run.name,
  html_url: run.html_url,
  created_at: run.created_at,
}))

const failuresResult: CheckResult = {
  failureCount: fixtureFailures.length,
  hasFailures: true,
  failures: fixtureFailures,
}

const emptyResult: CheckResult = {
  failureCount: 0,
  hasFailures: false,
  failures: [],
}

describe('run', () => {
  // Reset mocks and set default action inputs before each test.
  // Individual tests can override these defaults as needed.
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(core.getInput).mockImplementation((name: string) => {
      const inputs: Record<string, string> = {
        github_token: 'fake-token',
        lookback_days: '7',
        fail_on_error: 'false',
      }
      return inputs[name] ?? ''
    })
    vi.mocked(getOctokit).mockReturnValue({} as any)
  })

  // When Dependabot failures are found, the action should output the count,
  // a boolean flag, and JSON details of each failure.
  it('sets outputs correctly when failures exist', async () => {
    vi.mocked(checkDependabotFailures).mockResolvedValue(failuresResult)

    await run()

    expect(core.setOutput).toHaveBeenCalledWith('failure_count', fixtureFailures.length)
    expect(core.setOutput).toHaveBeenCalledWith('has_failures', 'true')
    expect(core.setOutput).toHaveBeenCalledWith('failures_json', JSON.stringify(fixtureFailures))
  })

  // When no Dependabot failures exist, outputs should indicate zero failures.
  it('sets outputs correctly when no failures', async () => {
    vi.mocked(checkDependabotFailures).mockResolvedValue(emptyResult)

    await run()

    expect(core.setOutput).toHaveBeenCalledWith('failure_count', 0)
    expect(core.setOutput).toHaveBeenCalledWith('has_failures', 'false')
    expect(core.setOutput).toHaveBeenCalledWith('failures_json', '[]')
  })

  // With fail_on_error enabled, the action should fail the workflow
  // when Dependabot failures are detected.
  it('fails action when fail_on_error is true and failures exist', async () => {
    vi.mocked(core.getInput).mockImplementation((name: string) => {
      const inputs: Record<string, string> = {
        github_token: 'fake-token',
        lookback_days: '7',
        fail_on_error: 'true',
      }
      return inputs[name] ?? ''
    })

    vi.mocked(checkDependabotFailures).mockResolvedValue(failuresResult)

    await run()

    expect(core.setFailed).toHaveBeenCalledWith(
      expect.stringContaining(String(fixtureFailures.length))
    )
  })

  // With fail_on_error disabled (default), the action should succeed
  // even when failures are found - allowing downstream steps to handle them.
  it('succeeds when fail_on_error is false even with failures', async () => {
    vi.mocked(core.getInput).mockImplementation((name: string) => {
      const inputs: Record<string, string> = {
        github_token: 'fake-token',
        lookback_days: '7',
        fail_on_error: 'false',
      }
      return inputs[name] ?? ''
    })

    vi.mocked(checkDependabotFailures).mockResolvedValue(failuresResult)

    await run()

    expect(core.setFailed).not.toHaveBeenCalled()
  })

  // Invalid lookback_days should throw an error with a clear message.
  it('throws error for invalid lookback_days', async () => {
    vi.mocked(core.getInput).mockImplementation((name: string) => {
      const inputs: Record<string, string> = {
        github_token: 'fake-token',
        lookback_days: 'not-a-number',
        fail_on_error: 'false',
      }
      return inputs[name] ?? ''
    })

    await expect(run()).rejects.toThrow('Invalid lookback_days')
  })

  // Zero or negative lookback_days should throw an error.
  it('throws error for zero lookback_days', async () => {
    vi.mocked(core.getInput).mockImplementation((name: string) => {
      const inputs: Record<string, string> = {
        github_token: 'fake-token',
        lookback_days: '0',
        fail_on_error: 'false',
      }
      return inputs[name] ?? ''
    })

    await expect(run()).rejects.toThrow('Invalid lookback_days')
  })
})
