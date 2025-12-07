import * as core from "@actions/core";
import { context, getOctokit } from "@actions/github";

//#region src/check-dependabot.ts
/**
* Queries the GitHub Actions API for Dependabot workflow failures.
* Filters by actor (`dependabot[bot]`), status (`failure`), and created date.
*/
async function checkDependabotFailures(octokit, options) {
	const { owner, repo, lookbackDays } = options;
	const lookbackDate = /* @__PURE__ */ new Date();
	lookbackDate.setDate(lookbackDate.getDate() - lookbackDays);
	const created = `>=${lookbackDate.toISOString().split("T")[0]}`;
	const failures = (await octokit.rest.actions.listWorkflowRunsForRepo({
		owner,
		repo,
		actor: "dependabot[bot]",
		status: "failure",
		created
	})).data.workflow_runs.map((run$1) => ({
		id: run$1.id,
		name: run$1.name ?? "Unknown",
		html_url: run$1.html_url,
		created_at: run$1.created_at
	}));
	return {
		failureCount: failures.length,
		hasFailures: failures.length > 0,
		failures
	};
}

//#endregion
//#region src/main.ts
/**
* Main entry point for the GitHub Action.
* Reads inputs, runs the Dependabot failure check, and sets outputs.
*/
async function run() {
	const token = core.getInput("github_token", { required: true });
	const lookbackDaysInput = core.getInput("lookback_days") || "7";
	const lookbackDays = parseInt(lookbackDaysInput, 10);
	if (isNaN(lookbackDays) || lookbackDays < 1) throw new Error(`Invalid lookback_days: "${lookbackDaysInput}" - must be a positive integer`);
	const failOnError = core.getInput("fail_on_error") === "true";
	const octokit = getOctokit(token);
	const { owner, repo } = context.repo;
	const result = await checkDependabotFailures(octokit, {
		owner,
		repo,
		lookbackDays
	});
	core.setOutput("failure_count", result.failureCount);
	core.setOutput("has_failures", result.hasFailures ? "true" : "false");
	core.setOutput("failures_json", JSON.stringify(result.failures));
	if (result.hasFailures) {
		core.warning(`Found ${result.failureCount} Dependabot workflow failure(s)`);
		for (const failure of result.failures) core.warning(`  - ${failure.name}: ${failure.html_url}`);
		if (failOnError) core.setFailed(`Found ${result.failureCount} Dependabot workflow failure(s)`);
	} else core.info("No Dependabot workflow failures found");
}

//#endregion
//#region src/index.ts
/**
* Action entry point.
* Wraps the main function with top-level error handling to ensure any uncaught errors properly fail the GitHub Action.
*/
run().catch((error) => {
	core.setFailed(error instanceof Error ? error.message : String(error));
});

//#endregion
export {  };