import { describe, it, expect, vi } from 'vitest'
import { checkDependabotFailures } from '../src/check-dependabot.js'

import failuresFixture from './fixtures/workflow-runs-failures.json'
import emptyFixture from './fixtures/workflow-runs-empty.json'

describe('checkDependabotFailures', () => {
  it('finds failures within lookback period', async () => {
    const mockOctokit = {
      rest: {
        actions: {
          listWorkflowRunsForRepo: vi.fn().mockResolvedValue({ data: failuresFixture }),
        },
      },
    }

    const result = await checkDependabotFailures(mockOctokit as any, {
      owner: 'case',
      repo: 'dependabot-error-alerts',
      lookbackDays: 7,
    })

    expect(result.failureCount).toBeGreaterThan(0)
    expect(result.hasFailures).toBe(true)
    expect(result.failures).toHaveLength(failuresFixture.workflow_runs.length)
  })

  it('returns zero when no failures', async () => {
    // When querying for failures on a repo with only successful runs,
    // the API returns an empty list (status=failure filter excludes them)
    const mockOctokit = {
      rest: {
        actions: {
          listWorkflowRunsForRepo: vi.fn().mockResolvedValue({ data: emptyFixture }),
        },
      },
    }

    const result = await checkDependabotFailures(mockOctokit as any, {
      owner: 'case',
      repo: 'iana-data',
      lookbackDays: 7,
    })

    expect(result.failureCount).toBe(0)
    expect(result.hasFailures).toBe(false)
  })

  it('returns zero when empty response', async () => {
    const mockOctokit = {
      rest: {
        actions: {
          listWorkflowRunsForRepo: vi.fn().mockResolvedValue({ data: emptyFixture }),
        },
      },
    }

    const result = await checkDependabotFailures(mockOctokit as any, {
      owner: 'case',
      repo: 'some-repo',
      lookbackDays: 7,
    })

    expect(result.failureCount).toBe(0)
    expect(result.hasFailures).toBe(false)
    expect(result.failures).toHaveLength(0)
  })

  it('respects lookback_days filter', async () => {
    const mockOctokit = {
      rest: {
        actions: {
          listWorkflowRunsForRepo: vi.fn().mockResolvedValue({ data: failuresFixture }),
        },
      },
    }

    await checkDependabotFailures(mockOctokit as any, {
      owner: 'case',
      repo: 'dependabot-error-alerts',
      lookbackDays: 3,
    })

    // Verify the API was called with the correct created filter
    expect(mockOctokit.rest.actions.listWorkflowRunsForRepo).toHaveBeenCalledWith(
      expect.objectContaining({
        owner: 'case',
        repo: 'dependabot-error-alerts',
        actor: 'dependabot[bot]',
        status: 'failure',
      })
    )

    // The created parameter should be set based on lookbackDays
    const callArgs = mockOctokit.rest.actions.listWorkflowRunsForRepo.mock.calls[0][0]
    expect(callArgs.created).toMatch(/^>=\d{4}-\d{2}-\d{2}$/)
  })

  it('handles API errors gracefully', async () => {
    const mockOctokit = {
      rest: {
        actions: {
          listWorkflowRunsForRepo: vi.fn().mockRejectedValue(new Error('API rate limit exceeded')),
        },
      },
    }

    await expect(
      checkDependabotFailures(mockOctokit as any, {
        owner: 'case',
        repo: 'dependabot-error-alerts',
        lookbackDays: 7,
      })
    ).rejects.toThrow('API rate limit exceeded')
  })
})
