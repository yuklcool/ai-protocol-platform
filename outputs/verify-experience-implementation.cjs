#!/usr/bin/env node
"use strict";

// Read-only checks by default. --snapshot exports existing verification records;
// it does not rerun tests, build, start services, or modify application files.
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const { spawnSync } = require("node:child_process");
const assert = require("node:assert/strict");

const root = path.resolve(__dirname, "..");
const evidencePath = path.join(__dirname, "experience-implementation-evidence.json");
const scopes = [
  "frontend", "backend", "README.md", "docs/configuration-guide.md",
  "docs/module-simplification.md", ".github/workflows/model-provider-gate.yml",
];
const e2e = [
  "frontend/e2e/model-provider-studio-live.spec.js",
  "frontend/e2e/ui-responsive-live.spec.js",
];

function execute(command, args) {
  const result = spawnSync(command, args, { cwd: root, encoding: "utf8", windowsHide: true, maxBuffer: 8 * 1024 * 1024 });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(`${command} ${args.join(" ")} exited ${result.status}\n${result.stdout}\n${result.stderr}`);
  return result.stdout.trim();
}
function sha256(file) {
  return crypto.createHash("sha256").update(fs.readFileSync(path.join(root, file))).digest("hex");
}
function sourceFiles() {
  const changed = execute("git", ["diff", "--name-only", "--", ...scopes]);
  const added = execute("git", ["ls-files", "--others", "--exclude-standard", "--", ...scopes]);
  return [...new Set(`${changed}\n${added}`.split(/\r?\n/).filter(Boolean))]
    .filter((file) => fs.statSync(path.join(root, file)).isFile()).sort();
}
function staticChecks() {
  const checks = [];
  for (const file of e2e) {
    execute(process.execPath, ["--check", file]);
    checks.push({ name: `JavaScript syntax: ${file}`, passed: true });
  }
  execute("git", ["diff", "--check", "--", ...scopes]);
  checks.push({ name: "Scoped tracked diff whitespace check", passed: true });
  const yaml = require(path.join(root, "frontend/node_modules/js-yaml"));
  const workflow = yaml.load(fs.readFileSync(path.join(root, ".github/workflows/model-provider-gate.yml"), "utf8"));
  for (const event of ["pull_request", "push"]) {
    const paths = workflow.on[event].paths;
    for (const expected of [
      "frontend/src/app/workspace/**", "frontend/src/app/sessions/**", "frontend/src/app/results/**",
      "backend/config/platform_config.py", "backend/protocols/sessions_route.py",
    ]) assert(paths.includes(expected), `${event} missing ${expected}`);
  }
  const browserSteps = workflow.jobs["model-provider-studio-live"].steps;
  const fixture = browserSteps.findIndex((step) => step.name === "Start isolated HTTP protocol test provider");
  const browser = browserSteps.findIndex((step) => step.name === "Run Root model, Skill content and console browser acceptance");
  assert(fixture >= 0 && browser > fixture, "HTTP fixture must start before browser acceptance");
  const frontendSteps = workflow.jobs["model-provider-frontend"].steps;
  const unit = frontendSteps.find((step) => step.name === "Verify provider management and workspace continuity");
  assert(unit, "Workspace unit test CI step missing");
  const testFiles = [...unit.run.matchAll(/src\/[^\s\\]+\.(?:tsx|ts)/g)].map((match) => match[0]);
  assert.equal(new Set(testFiles).size, 21);
  for (const file of testFiles) assert(fs.existsSync(path.join(root, "frontend", file)), `CI test does not exist: ${file}`);
  const backendStep = workflow.jobs["model-provider"].steps.find((step) => step.name === "Run model-provider, user-ownership and admin-role tests");
  assert(backendStep.run.includes("MODEL_REGISTRY_BACKEND=database"));
  assert(backendStep.run.includes("AIP_TEST_ISOLATED_NETWORK=1"));
  for (const file of ["test_sessions_route.py", "test_sessions_recent.py", "test_platform_config.py"]) {
    assert(backendStep.run.includes(file), `Backend CI coverage missing: ${file}`);
  }
  checks.push({ name: "Workflow YAML, trigger paths, fixture order and 21 existing frontend test paths", passed: true });
  checks.push({ name: "Backend CI database-registry mode and session/config regression paths", passed: true });
  return checks;
}
function historicalEvidence(transcriptPath) {
  const records = fs.readFileSync(transcriptPath, "utf8").split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line));
  const definitions = [
    ["frontend-unit", "y77efu", "completed", "287 passed (287)", 287],
    ["backend-api", "hvzb43", "completed", "144 passed", 144],
    ["backend-config", "47xnge", "completed", "10 passed", 10],
    ["typescript", "6yw7xh", "completed", "(no output)", null],
    ["frontend-lint", "o5knsb", "completed", "No ESLint warnings or errors", null],
    ["backend-ruff", "m00ics", "completed", "5 files already formatted", null],
    ["production-build", "lcg0kw", "failed", "SAFE_DELETE_BULK_CONFIRM_REQUIRED", null],
  ];
  return definitions.map(([id, taskId, status, marker, passed]) => {
    const found = records.filter((record) => record.type === "function_call_result" && record.name === "TaskOutput")
      .map((record) => ({ record, text: record.output?.text || "" }))
      .filter(({ text }) => text.startsWith(`Shell ID: ${taskId}\n`) && text.includes(`Status: ${status}\n`) && text.includes(marker)).at(-1);
    assert(found, `Missing executed evidence: ${id}`);
    const text = found.text;
    return {
      id, taskId, status, passed, sourceRecordId: found.record.id,
      command: /^Command: (.*)$/m.exec(text)?.[1] || null,
      recordedAt: /^Timestamp: (.*)$/m.exec(text)?.[1] || null,
      output: text,
    };
  });
}

const mode = process.argv[2] || "--check";
if (mode === "--snapshot") {
  const transcript = process.argv[3];
  assert(transcript, "Usage: node outputs/verify-experience-implementation.cjs --snapshot <transcript.jsonl>");
  const evidence = {
    schemaVersion: 1,
    generatedAt: new Date().toISOString(),
    project: "ai-protocol-platform",
    branch: execute("git", ["branch", "--show-current"]),
    baselineCommit: execute("git", ["rev-parse", "HEAD"]),
    verdict: "implementation-delivered-production-acceptance-blocked",
    claims: {
      frontendUnitPassed: 287, backendApiPassed: 144, backendConfigPassed: 10,
      localProductionBuildPassed: false, realBrowserExecuted: false,
      postgresAcceptanceExecuted: false, realExternalProviderCalled: false,
      committed: false, pushed: false, deployed: false,
    },
    observedChecks: staticChecks(),
    historicalRuns: historicalEvidence(path.resolve(transcript)),
    manifest: [...sourceFiles(), "outputs/verify-experience-implementation.cjs"].map((file) => ({ file, sha256: sha256(file) })),
    exclusions: ["infrastructure/mcp-sandbox/serve.ts", "start-local.ps1", "stop-local.ps1", ".workbuddy-ai/**", "outputs/glass-workspace-design.html"],
    limitations: [
      "Unit/API results were executed earlier in this same session; raw outputs are exported, not invented or rerun here.",
      "API tests use memory persistence with database model registry; they are not PostgreSQL acceptance.",
      "Browser scripts have syntax/static verification only, not a live browser pass.",
      "Default browser provider is an HTTP protocol fixture, not a real external LLM.",
      "Production build stopped in cleanup of the existing .next due to safe-delete protection; protection was not disabled.",
      "A copied build with node_modules junction was considered but not executed; no substitute build pass is claimed.",
      "Results support selected-session A2UI metadata, not general file downloads, full-history search or per-surface deep links.",
      "Source hashes identify local working-tree contents; the baseline commit alone does not contain these uncommitted changes.",
    ],
  };
  fs.writeFileSync(evidencePath, `${JSON.stringify(evidence, null, 2)}\n`, { flag: "wx" });
  console.log(JSON.stringify({ evidencePath, checks: evidence.observedChecks.length, sourceFiles: evidence.manifest.length, historicalRuns: evidence.historicalRuns.length, verdict: evidence.verdict }, null, 2));
} else if (mode === "--check") {
  const evidence = JSON.parse(fs.readFileSync(evidencePath, "utf8"));
  for (const item of evidence.manifest) assert.equal(sha256(item.file), item.sha256, `Source changed: ${item.file}`);
  const checks = staticChecks();
  console.log(JSON.stringify({ passed: true, checks: checks.length, matchedSourceFiles: evidence.manifest.length, note: "Fingerprints and static checks only; does not rerun unit/API/build/browser acceptance." }, null, 2));
} else {
  throw new Error("Use --check or --snapshot <transcript.jsonl>");
}
