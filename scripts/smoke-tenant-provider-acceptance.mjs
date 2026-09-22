#!/usr/bin/env node
/**
 * Billable, manual-only Tenant A/B real Provider acceptance.
 *
 * This deliberately exercises the public Root Agent stream rather than an
 * internal helper. It proves that two first-class tenants with the same uid
 * each invoke their own MCP tool, A's budget exhaustion does not affect B,
 * and Tenant B cannot select Tenant A's private capability.
 *
 * Preconditions:
 *   - a running Docker Compose backend with BUDGET_ENFORCER=tenant-repository
 *   - a reachable OpenAI-compatible provider in REAL_PROVIDER_BASE_URL
 *   - OPENAI_API_KEY present in the backend container and this process
 *
 * The script creates only run-id-scoped Provider, model, MCP and Skill
 * documents, then removes them together with its seeded tenant fixtures.
 */

import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";

function required(name) {
  const value = String(process.env[name] || "").trim();
  if (!value) throw new Error(name + " must be configured");
  return value;
}

function positiveNumber(name, fallback) {
  const value = Number(process.env[name] || fallback);
  if (!Number.isFinite(value) || value <= 0) {
    throw new Error(name + " must be a positive number");
  }
  return value;
}

function runId() {
  const raw = String(process.env.TENANT_E2E_RUN_ID || Date.now())
    .toLowerCase()
    .replace(/[^a-z0-9-]/g, "-")
    .slice(0, 20);
  return (raw + "-" + randomUUID().slice(0, 8)).replace(/-+/g, "-").slice(0, 31);
}

function kebabCase(value) {
  const normalized = String(value)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  if (!normalized) throw new Error("value must contain at least one lowercase kebab-case character");
  return normalized;
}

const BACKEND_URL = String(process.env.BACKEND_URL || "http://127.0.0.1:1956").replace(/\/+$/, "");
const ADMIN_EMAIL = String(process.env.SELFHOST_ADMIN_EMAIL || "admin@example.com");
const ADMIN_PASSWORD = required("SELFHOST_ADMIN_PASSWORD");
const PROVIDER_BASE_URL = required("REAL_PROVIDER_BASE_URL").replace(/\/+$/, "");
const MODEL_API_NAME = required("REAL_PROVIDER_MODEL");
const MODEL_SUPPORTS_REASONING = String(process.env.REAL_PROVIDER_SUPPORTS_REASONING || "false") === "true";
const INITIAL_QUOTA_USD = positiveNumber("TENANT_E2E_INITIAL_QUOTA_USD", "1");
const BUDGET_MULTIPLIER = positiveNumber("TENANT_E2E_BUDGET_MULTIPLIER", "1");
const MCP_URL = String(process.env.TENANT_E2E_MCP_URL || "http://mcp-example-map:8080/mcp");
const RUN_ID = runId();
const PROVIDER_ID = "tenant-provider-" + RUN_ID;
const MODEL_A = "tenant-provider-model-a-" + RUN_ID;
const MODEL_B = "tenant-provider-model-b-" + RUN_ID;
const SERVER_A = "tenant-provider-mcp-a-" + RUN_ID;
const SERVER_B = "tenant-provider-mcp-b-" + RUN_ID;
const MARKER_A = "TENANT-A-ROOT-MCP-PASS-" + RUN_ID;
const MARKER_B = "TENANT-B-ROOT-MCP-PASS-" + RUN_ID;

required("OPENAI_API_KEY");

function ok(message) {
  console.log("✓ " + message);
}

function backendExec(args, envPairs = []) {
  const dockerArgs = ["compose", "exec", "-T"];
  for (const pair of envPairs) dockerArgs.push("-e", pair);
  dockerArgs.push("backend", ...args);
  return execFileSync("docker", dockerArgs, { encoding: "utf8" });
}

function parseLastJson(output) {
  for (const line of String(output).trim().split("\n").reverse()) {
    try {
      return JSON.parse(line);
    } catch {
      // Setup emits logs before the final fixture payload.
    }
  }
  throw new Error("command did not emit a final JSON document");
}

async function api(path, init = {}, expected = null) {
  const headers = new Headers(init.headers || {});
  const response = await fetch(BACKEND_URL + path, { ...init, headers });
  const text = await response.text();
  let body = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }
  if (expected !== null && response.status !== expected) {
    throw new Error((init.method || "GET") + " " + path + " returned " + response.status + ": " + text);
  }
  if (expected === null && !response.ok) {
    throw new Error((init.method || "GET") + " " + path + " returned " + response.status + ": " + text);
  }
  return { response, body, text };
}

function jsonHeaders(token) {
  const headers = { "content-type": "application/json" };
  if (token) headers.Authorization = "Bearer " + token;
  return headers;
}

async function jsonApi(token, path, method, body, expected = null) {
  return api(
    path,
    {
      method,
      headers: jsonHeaders(token),
      body: body === undefined ? undefined : JSON.stringify(body),
    },
    expected,
  );
}

function parseSse(body) {
  return String(body || "")
    .replace(/\r\n/g, "\n")
    .split(/\n\n+/)
    .map((chunk) => chunk.trim())
    .filter((chunk) => chunk.startsWith("data:"))
    .map((chunk) => {
      try {
        return JSON.parse(chunk.slice("data:".length).trim());
      } catch {
        return null;
      }
    })
    .filter(Boolean);
}

async function rootStream(token, capability, label) {
  const result = await jsonApi(token, "/api/agent/stream", "POST", {
    message: "Show a map of San Francisco. Use the available show-map MCP tool before answering. This is " + label + ".",
    threadId: "tenant-provider-" + RUN_ID + "-" + randomUUID().slice(0, 8),
    forwardedProps: {
      agent_id: "root-agent",
      capability_hint: capability,
    },
  });
  assert.equal(result.response.status, 200);
  return parseSse(result.text);
}

function textFrom(events) {
  return events
    .filter((event) => event.type === "TEXT_MESSAGE_CONTENT")
    .map((event) => String(event.delta || event.content || ""))
    .join("");
}

function assertSuccessfulToolRun(events, marker, label) {
  const types = events.map((event) => event.type);
  const errors = events.filter((event) => event.type === "RUN_ERROR");
  assert(types.includes("RUN_STARTED"), label + " did not start an AG-UI run");
  assert.equal(errors.length, 0, label + " emitted RUN_ERROR: " + JSON.stringify(errors));
  assert(types.includes("RUN_FINISHED"), label + " did not finish");
  const toolNames = events
    .filter((event) => event.type === "TOOL_CALL_START")
    .map((event) => String(event.toolCallName || event.tool_call_name || ""));
  assert(
    toolNames.some((name) => name.includes("show-map")),
    label + " did not call show-map: " + JSON.stringify(toolNames),
  );
  assert(textFrom(events).includes(marker), label + " did not return its required final marker");
}

function ledgerRows(tenantId) {
  const code = [
    "import json,sys",
    "from db.persistence import get_repository",
    "rows=get_repository().query_documents('tenant_budget_ledger', filters=[('tenantId','==',sys.argv[1])], limit=None)",
    "print(json.dumps(rows))",
  ].join("; ");
  return JSON.parse(backendExec(["uv", "run", "python", "-c", code, tenantId]));
}

function assertPositiveRecordedUsage(tenantId, label) {
  const rows = ledgerRows(tenantId);
  const charged = rows.reduce((total, row) => total + Number(row.chargedCostUsd || 0), 0);
  const actual = rows.reduce((total, row) => total + Number(row.actualCostUsd || 0), 0);
  assert(charged > 0, label + " has no positive quota charge. Use a model present in the platform pricing table.");
  assert(
    actual > 0,
    label + " has no recorded provider token usage. A held projection is not enough for this live acceptance.",
  );
  return { charged, actual, rows };
}

async function deleteBestEffort(token, path) {
  if (!token || !path) return;
  try {
    const result = await api(path, { method: "DELETE", headers: { Authorization: "Bearer " + token } }, null);
    if (![200, 202, 204, 404].includes(result.response.status)) {
      console.warn("cleanup " + path + " returned " + result.response.status);
    }
  } catch (error) {
    console.warn("cleanup " + path + " failed: " + error.message);
  }
}

async function main() {
  let adminToken = "";
  let tokenA = "";
  let tokenB = "";
  let seeded = false;
  let providerCreated = false;
  let modelACreated = false;
  let modelBCreated = false;
  let serverACreated = false;
  let serverBCreated = false;
  let skillA = "";
  let skillB = "";

  try {
    backendExec([
      "sh",
      "-ec",
      "test \"$BUDGET_ENFORCER\" = \"tenant-repository\"; test -n \"$OPENAI_API_KEY\"",
    ]);
    await api("/health");
    ok("Backend health and tenant repository budget enforcer");

    const login = await jsonApi("", "/api/auth/login", "POST", {
      email: ADMIN_EMAIL,
      password: ADMIN_PASSWORD,
    });
    adminToken = String(login.body.access_token || "");
    assert(adminToken, "platform admin login did not return an access token");
    assert(
      Array.isArray(login.body.user && login.body.user.groupTags) && login.body.user.groupTags.includes("aitana-admin"),
      "configured admin is not a platform admin",
    );
    ok("Platform admin login");

    await jsonApi(adminToken, "/api/admin/model-providers/" + PROVIDER_ID, "PUT", {
      name: "Tenant Provider Acceptance " + RUN_ID,
      kind: "openai-compatible",
      base_url: PROVIDER_BASE_URL,
      api_key_ref: "${OPENAI_API_KEY}",
      enabled: true,
    });
    providerCreated = true;
    const providerProbe = await jsonApi(adminToken, "/api/admin/model-providers/" + PROVIDER_ID + "/test", "POST");
    assert.equal(providerProbe.body.ok, true, "real provider /models probe failed");

    for (const modelId of [MODEL_A, MODEL_B]) {
      await jsonApi(adminToken, "/api/admin/model-providers/models/" + modelId, "PUT", {
        api_name: MODEL_API_NAME,
        provider_id: PROVIDER_ID,
        tier: "default",
        context_window: 32000,
        max_output_tokens: 1024,
        description: "Ephemeral tenant provider acceptance model",
        supports_tools: true,
        supports_reasoning: MODEL_SUPPORTS_REASONING,
        supports_responses_api: false,
        supports_vision: false,
        residency: "global",
        enabled: true,
      });
      if (modelId === MODEL_A) modelACreated = true;
      else modelBCreated = true;
    }
    const toolProbe = await jsonApi(
      adminToken,
      "/api/admin/model-providers/models/" + MODEL_A + "/test",
      "POST",
      { mode: "tool_call", prompt: "Call the provided platform_probe tool now." },
    );
    assert.equal(toolProbe.body.ok, true, "real provider tool-call probe failed");
    assert.equal(toolProbe.body.tool_called, true, "real provider did not select the probe tool");
    ok("Two real provider model registrations and tool-call probe");

    const seedOutput = backendExec(
      ["uv", "run", "python", "scripts/seed_tenant_acceptance.py", "--run-id", RUN_ID],
      [
        "TENANT_E2E_PASSWORD_A=tenant-e2e-a-" + RUN_ID + "-password",
        "TENANT_E2E_PASSWORD_B=tenant-e2e-b-" + RUN_ID + "-password",
        "TENANT_E2E_MODEL_A=" + MODEL_A,
        "TENANT_E2E_MODEL_B=" + MODEL_B,
        "TENANT_E2E_QUOTA_USD_A=" + INITIAL_QUOTA_USD,
        "TENANT_E2E_QUOTA_USD_B=" + INITIAL_QUOTA_USD,
      ],
    );
    const fixture = parseLastJson(seedOutput);
    seeded = true;
    const tenantA = fixture.tenant_a;
    const tenantB = fixture.tenant_b;
    const passwordA = "tenant-e2e-a-" + RUN_ID + "-password";
    const passwordB = "tenant-e2e-b-" + RUN_ID + "-password";

    const loginA = await jsonApi("", "/api/auth/login", "POST", { email: fixture.email_a, password: passwordA });
    const loginB = await jsonApi("", "/api/auth/login", "POST", { email: fixture.email_b, password: passwordB });
    tokenA = String(loginA.body.access_token || "");
    tokenB = String(loginB.body.access_token || "");
    assert(tokenA && tokenB, "tenant fixture logins did not return access tokens");
    assert.equal(loginA.body.user.uid, loginB.body.user.uid, "fixture must retain the deliberate uid collision");
    assert.notEqual(loginA.body.user.tenantId, loginB.body.user.tenantId, "fixture tenants unexpectedly match");
    ok("Same-uid Tenant A/B fixture login");

    for (const [token, tenantId, serverId, label] of [
      [tokenA, tenantA, SERVER_A, "Tenant A"],
      [tokenB, tenantB, SERVER_B, "Tenant B"],
    ]) {
      await jsonApi(token, "/api/admin/tool-permissions/" + encodeURIComponent("tenant:" + tenantId), "PUT", {
        type: "tenant",
        tools: ["geocode", "show-map"],
        denied: [],
      });
      await jsonApi(token, "/api/admin/mcp-servers/" + serverId, "PUT", {
        url: MCP_URL,
        transport: "streamable-http",
        scope: "tenant",
        enabled: true,
        description: label + " real provider acceptance",
      });
      if (serverId === SERVER_A) serverACreated = true;
      else serverBCreated = true;
      const discovered = await jsonApi(token, "/api/admin/mcp-servers/" + serverId + "/discover", "POST");
      assert(
        Array.isArray(discovered.body.tools) && discovered.body.tools.some((tool) => tool.name === "show-map"),
        label + " MCP discovery did not expose show-map",
      );
    }
    ok("Tenant-scoped MCP bindings and fail-closed Tool Permissions");

    async function createTenantSkill(token, label, model, serverId, marker) {
      const name = kebabCase("tenant-provider-" + label + "-" + RUN_ID);
      assert.match(name, /^[a-z0-9]+(?:-[a-z0-9]+)*$/, label + " generated an invalid Skill name");
      const created = await jsonApi(token, "/api/skills", "POST", {
        name,
        displayName: label + " provider acceptance",
        description: "Ephemeral Tenant A/B real provider acceptance",
        instructions:
          "This is a tenant isolation acceptance capability. When asked for a map, you MUST call the available show-map MCP tool before answering. Never claim success before that tool completes. After a successful tool call include the exact marker " +
          marker +
          " in the final response.",
        accessControl: { type: "private" },
        skillMetadata: {
          model,
          thinking: "off",
          enableConfirmation: false,
          toolConfigs: {
            defaults: { artifacts: false, memory: false },
            mcp: { servers: [serverId] },
            budget: {
              identity_key: "tenant_id",
              missing_identity_policy: "block",
              cost_multiplier: BUDGET_MULTIPLIER,
            },
          },
        },
      });
      assert(created.body.skillId, label + " Skill creation did not return skillId");
      return created.body.skillId;
    }

    skillA = await createTenantSkill(tokenA, "Tenant A", MODEL_A, SERVER_A, MARKER_A);
    skillB = await createTenantSkill(tokenB, "Tenant B", MODEL_B, SERVER_B, MARKER_B);
    ok("Tenant-private Root Agent capabilities created");

    const firstA = await rootStream(tokenA, skillA, "Tenant A first budgeted tool run");
    assertSuccessfulToolRun(firstA, MARKER_A, "Tenant A first run");
    const firstB = await rootStream(tokenB, skillB, "Tenant B first budgeted tool run");
    assertSuccessfulToolRun(firstB, MARKER_B, "Tenant B first run");
    const chargeA = assertPositiveRecordedUsage(tenantA, "Tenant A");
    const chargeB = assertPositiveRecordedUsage(tenantB, "Tenant B");
    assert(chargeA.rows.every((row) => row.tenantId === tenantA), "Tenant A ledger query returned another tenant");
    assert(chargeB.rows.every((row) => row.tenantId === tenantB), "Tenant B ledger query returned another tenant");
    ok("Both tenants recorded positive real-provider quota usage in separate ledgers");

    const cross = await api("/api/agent/stream", {
      method: "POST",
      headers: jsonHeaders(tokenB),
      body: JSON.stringify({
        message: "Attempt a cross-tenant capability.",
        threadId: "tenant-provider-cross-" + RUN_ID,
        forwardedProps: { agent_id: "root-agent", capability_hint: skillA },
      }),
    }, 404);
    assert.equal(cross.response.status, 404, "Tenant B could select Tenant A private Root Agent capability");
    ok("Cross-tenant Root Agent capability selection is rejected with 404");

    const depletedCap = chargeA.charged / 2;
    await jsonApi(tokenA, "/api/admin/tenants/" + tenantA, "PATCH", {
      quota: {
        acceptanceBucket: "A",
        llmBudgetUsd: depletedCap,
        llmBudgetPeriod: "daily",
      },
    });
    const exhausted = await rootStream(tokenA, skillA, "Tenant A exhausted budget run");
    const budgetError = exhausted.find((event) => event.type === "RUN_ERROR" && event.code === "BUDGET_EXCEEDED");
    assert(budgetError, "Tenant A did not emit typed BUDGET_EXCEEDED after reducing its cap below recorded spend");
    assert(
      !exhausted.some((event) => event.type === "TOOL_CALL_START"),
      "Tenant A invoked a tool after its budget was exhausted",
    );
    ok("Tenant A budget blocks before a second Tool Calling attempt");

    const secondB = await rootStream(tokenB, skillB, "Tenant B remains independent after Tenant A exhaustion");
    assertSuccessfulToolRun(secondB, MARKER_B, "Tenant B independent run");
    const afterB = assertPositiveRecordedUsage(tenantB, "Tenant B after Tenant A exhaustion");
    assert(afterB.charged >= chargeB.charged, "Tenant B ledger regressed after its independent run");
    ok("Tenant B remains able to call its own MCP tool after Tenant A exhausts quota");

    console.log("\nReal Tenant A/B Provider acceptance passed.");
    console.log("Covered: Root Agent capability ACL, tenant Tool Calling, recorded quota usage, typed budget block, and cross-tenant quota independence.");
  } finally {
    await deleteBestEffort(tokenA, skillA ? "/api/skills/" + skillA : "");
    await deleteBestEffort(tokenB, skillB ? "/api/skills/" + skillB : "");
    await deleteBestEffort(tokenA, serverACreated ? "/api/admin/mcp-servers/" + SERVER_A : "");
    await deleteBestEffort(tokenB, serverBCreated ? "/api/admin/mcp-servers/" + SERVER_B : "");
    await deleteBestEffort(adminToken, modelACreated ? "/api/admin/model-providers/models/" + MODEL_A : "");
    await deleteBestEffort(adminToken, modelBCreated ? "/api/admin/model-providers/models/" + MODEL_B : "");
    await deleteBestEffort(adminToken, providerCreated ? "/api/admin/model-providers/" + PROVIDER_ID : "");
    if (seeded) {
      try {
        backendExec(["uv", "run", "python", "scripts/seed_tenant_acceptance.py", "--run-id", RUN_ID, "--cleanup"]);
      } catch (error) {
        console.warn("fixture cleanup failed: " + error.message);
      }
    }
  }
}

main().catch((error) => {
  console.error("Tenant real-provider acceptance failed: " + error.stack);
  process.exitCode = 1;
});
