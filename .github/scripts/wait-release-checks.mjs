// Release only the exact commit that passed the operation and persistence gates.
const workflows = [
  "ci.yml",
  "user-ownership.yml",
  "core-runtime-persistence.yml",
  "model-provider-gate.yml",
  "a2ui-live-acceptance.yml",
  "protocol-operation-acceptance.yml",
];
const { GITHUB_REPOSITORY: repository, GITHUB_SHA: sha, GH_TOKEN: token } = process.env;
if (!repository || !sha || !token) throw new Error("Missing GitHub release-check context");
const pending = new Set(workflows);
const deadline = Date.now() + 40 * 60_000;
while (pending.size) {
  for (const workflow of [...pending]) {
    const response = await fetch(`https://api.github.com/repos/${repository}/actions/workflows/${workflow}/runs?head_sha=${sha}&event=push&per_page=10`, {
      headers: { authorization: `Bearer ${token}`, accept: "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28" },
    });
    if (!response.ok) throw new Error(`${workflow}: GitHub API HTTP ${response.status}`);
    const { workflow_runs: runs } = await response.json();
    const run = runs?.filter(run => run.head_sha === sha).sort((a, b) => b.id - a.id)[0];
    if (!run || run.status !== "completed") continue;
    if (run.conclusion !== "success") throw new Error(`${workflow}: ${run.conclusion} (${run.html_url})`);
    pending.delete(workflow);
    console.log(`Passed ${workflow}: ${run.html_url}`);
  }
  if (!pending.size) break;
  if (Date.now() >= deadline) throw new Error(`Release checks timed out: ${[...pending].join(", ")}`);
  console.log(`Waiting for ${[...pending].join(", ")}`);
  await new Promise(resolve => setTimeout(resolve, 15_000));
}
