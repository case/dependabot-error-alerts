/**
 * Action entry point.
 * Wraps the main function with top-level error handling to ensure any uncaught errors properly fail the GitHub Action.
 */

import * as core from '@actions/core'
import { run } from './main.js'

run().catch((error) => {
  core.setFailed(error instanceof Error ? error.message : String(error))
})
