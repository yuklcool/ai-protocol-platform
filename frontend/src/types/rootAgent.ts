export interface RootAgentInteraction {
  a2uiEnabled: boolean;
  defaultSurface: string;
  defaultUpdateMode: "replace" | "patch";
  allowSurfaceContextWrites: boolean;
  allowActionTriggeredRuns: boolean;
  welcomeMessage: string;
  voiceEnabled: boolean;
}

export interface RootAgentConfig {
  displayName: string;
  description: string;
  model: string;
  instructions: string;
  skills: string[];
  tools: string[];
  mcpServers: string[];
  knowledge: string[];
  interaction: RootAgentInteraction;
  permissions: Record<string, unknown>;
  specialistAgents: string[];
  tenantOverrides: Record<string, unknown>;
}

export const DEFAULT_ROOT_AGENT_CONFIG: RootAgentConfig = {
  displayName: "Root Agent",
  description: "The platform's single user-facing AI assistant.",
  model: "smart",
  instructions: "",
  skills: [],
  tools: [],
  mcpServers: [],
  knowledge: [],
  interaction: {
    a2uiEnabled: true,
    defaultSurface: "chat",
    defaultUpdateMode: "replace",
    allowSurfaceContextWrites: false,
    allowActionTriggeredRuns: false,
    welcomeMessage: "",
    voiceEnabled: false,
  },
  permissions: { failClosed: false },
  specialistAgents: [],
  tenantOverrides: {},
};

export function normalizeRootAgentConfig(value: unknown): RootAgentConfig {
  const raw = value && typeof value === "object" ? value as Partial<RootAgentConfig> : {};
  const interaction = raw.interaction && typeof raw.interaction === "object"
    ? raw.interaction as Partial<RootAgentInteraction>
    : {};
  return {
    ...DEFAULT_ROOT_AGENT_CONFIG,
    ...raw,
    skills: Array.isArray(raw.skills) ? raw.skills.map(String) : [],
    tools: Array.isArray(raw.tools) ? raw.tools.map(String) : [],
    mcpServers: Array.isArray(raw.mcpServers) ? raw.mcpServers.map(String) : [],
    knowledge: Array.isArray(raw.knowledge) ? raw.knowledge.map(String) : [],
    specialistAgents: Array.isArray(raw.specialistAgents) ? raw.specialistAgents.map(String) : [],
    permissions: raw.permissions && typeof raw.permissions === "object" ? raw.permissions : {},
    interaction: {
      ...DEFAULT_ROOT_AGENT_CONFIG.interaction,
      ...interaction,
    },
    tenantOverrides: raw.tenantOverrides && typeof raw.tenantOverrides === "object" ? raw.tenantOverrides : {},
  };
}
