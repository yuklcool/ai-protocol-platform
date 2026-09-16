import { describe, expect, it } from "vitest";

import {
  TENANT_ADMIN_TRANSLATIONS,
  translateTenantAdmin,
} from "@/lib/i18n/tenantAdmin";

describe("Tenant admin i18n", () => {
  it("keeps English and Chinese dictionaries in runtime key parity", () => {
    expect(Object.keys(TENANT_ADMIN_TRANSLATIONS.en)).toEqual(
      Object.keys(TENANT_ADMIN_TRANSLATIONS["zh-CN"]),
    );
  });

  it("preserves existing English UI contracts used by component tests", () => {
    expect(translateTenantAdmin("en", "onboard.submit")).toBe("Onboard tenant");
    expect(translateTenantAdmin("en", "editor.save")).toBe("Save");
    expect(translateTenantAdmin("en", "access.emailAria")).toBe("User email to inspect");
    expect(translateTenantAdmin("en", "health.healthy")).toBe("✓ healthy");
  });

  it("renders Chinese copy while preserving technical identifiers", () => {
    expect(translateTenantAdmin("zh-CN", "page.title")).toBe("租户管理");
    expect(translateTenantAdmin("zh-CN", "page.adminOnlyDescription")).toContain("aitana-admin");
    expect(translateTenantAdmin("zh-CN", "page.adminOnlyDescription")).toContain("tenant-admin:<domain>");
    expect(translateTenantAdmin("zh-CN", "common.landingSkill")).toContain("default_skill");
  });

  it("interpolates tenant, access and count messages", () => {
    expect(
      translateTenantAdmin("zh-CN", "access.visibleSummary", {
        visible: 3,
        total: 5,
        email: "user@example.com",
      }),
    ).toContain("3/5");
    expect(
      translateTenantAdmin("zh-CN", "editor.deleteConfirm", { domain: "example.com" }),
    ).toContain("example.com");
  });
});
