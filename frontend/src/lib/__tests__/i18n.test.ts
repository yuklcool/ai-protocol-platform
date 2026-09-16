import { describe, expect, it } from "vitest";
import {
  normalizeLocale,
  SUPPORTED_LOCALES,
  TRANSLATIONS,
  translate,
} from "@/lib/i18n";

describe("i18n", () => {
  it("keeps every locale dictionary key-complete", () => {
    const englishKeys = Object.keys(TRANSLATIONS.en).sort();
    for (const locale of SUPPORTED_LOCALES) {
      expect(Object.keys(TRANSLATIONS[locale]).sort()).toEqual(englishKeys);
    }
  });

  it("normalizes supported browser/config locale variants", () => {
    expect(normalizeLocale("zh")).toBe("zh-CN");
    expect(normalizeLocale("zh-Hans")).toBe("zh-CN");
    expect(normalizeLocale("en-US")).toBe("en");
    expect(normalizeLocale("fr-FR")).toBeNull();
  });

  it("interpolates translated parameters", () => {
    expect(translate("zh-CN", "home.skillsAvailable", { count: 3 })).toBe(
      "共 3 个可用",
    );
    expect(
      translate("en", "admin.scopedTo", { domains: "tenant.example" }),
    ).toContain("tenant.example");
  });
});
