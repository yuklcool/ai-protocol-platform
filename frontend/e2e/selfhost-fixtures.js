// Provision the administrator's tenant through the same API used by the console.
// Account bootstrap deliberately does not create a tenant or grant resources.
async function provisionAdminTenant(backend, login) {
  const tenantId = login.user.tenantId;
  if (!tenantId) throw new Error("Acceptance administrator must have a stable tenant ID");
  const headers = {
    authorization: `Bearer ${login.access_token}`,
    "content-type": "application/json",
  };
  const created = await fetch(`${backend}/api/admin/tenants`, {
    method: "POST",
    headers,
    body: JSON.stringify({ tenant_id: tenantId, display_name: "自托管验收租户" }),
  });
  if (!created.ok && created.status !== 409) {
    throw new Error(`Provision acceptance tenant: ${created.status} ${await created.text()}`);
  }
  const response = await fetch(`${backend}/api/admin/tenants/${encodeURIComponent(tenantId)}`, { headers });
  if (!response.ok) throw new Error(`Read acceptance tenant: ${response.status} ${await response.text()}`);
  return response.json();
}

module.exports = { provisionAdminTenant };
