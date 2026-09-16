import { describe, expect, it } from "vitest";

import {
  MCP_ADMIN_TRANSLATIONS,
  translateMcpAdmin,
} from "@/lib/i18n/mcpAdmin";

describe("MCP admin i18n", () => {
  it("keeps English and Chinese dictionaries in runtime key parity", () => {
    expect(Object.keys(MCP_ADMIN_TRANSLATIONS.en)).toEqual(
      Object.keys(MCP_ADMIN_TRANSLATIONS["zh-CN"]),
    );
  });

  it("preserves the existing English contract", () => {
    expect(translateMcpAdmin("en", "title")).toBe("MCP Servers");
    expect(
      translateMcpAdmin("en", "delete.confirm", { id: "maps" }),
    ).toBe('Delete MCP Server "maps"?');
    expect(translateMcpAdmin("en", "form.headersHelp")).toContain("${ENV_VAR}");
  });

  it("renders Chinese text and interpolation without changing technical references", () => {
    expect(translateMcpAdmin("zh-CN", "title")).toBe("MCP Server 管理");
    expect(translateMcpAdmin("zh-CN", "form.headersHelp")).toContain("${ENV_VAR}");
    expect(
      translateMcpAdmin("zh-CN", "binding.bound", {
        server: "maps",
        skill: "城市照明分析",
      }),
    ).toBe("已将 maps 绑定到 城市照明分析。");
  });
});
