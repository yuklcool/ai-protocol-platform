"use client";

import NextLink from "next/link";
import { SignInRequired } from "@/components/chat/SignInRequired";
import { useAuth } from "@/contexts/AuthContext";
import { useAdminScope } from "@/hooks/useAdminScope";

type Link = { href: string; label: string; note?: string };
type Area = { href: string; title: string; question: string; links: Link[]; platformOnly?: boolean };

const AREAS: Area[] = [
  {
    href: "/admin/tenants",
    title: "Your tenant",
    question: "What is my tenant configured to do, and what do my users actually see?",
    links: [
      { href: "/admin/tenants", label: "Tenant config", note: "enabled skills, landing skill, group tags, bucket" },
      { href: "/admin/tenants", label: "What your users actually see", note: "effective access for one user" },
    ],
  },
  {
    href: "/admin/users",
    title: "People & access",
    question: "Who is here, and what may they use?",
    links: [
      { href: "/admin/users", label: "Users", note: "grant and revoke group tags" },
      { href: "/admin/groups", label: "Group tags", note: "the registry, and who holds each tag" },
      { href: "/admin/tool-permissions", label: "Tool permissions", note: "which tools a user or domain may call" },
    ],
  },
  {
    href: "/skills/studio/new",
    title: "Skills & MCP",
    question: "What is published, what can it call, and to whom?",
    links: [
      { href: "/skills/studio/new", label: "Skill Studio", note: "model, tools, instructions, access" },
      { href: "/admin/mcp-servers", label: "MCP Servers", note: "endpoints, health, capabilities, Skill bindings" },
    ],
  },
  {
    href: "/admin/analytics",
    title: "Activity & audit",
    question: "What happened, and who changed what?",
    links: [
      { href: "/admin/analytics", label: "Sessions", note: "browse past sessions and their traces" },
      { href: "/admin/audit", label: "Audit trail", note: "who changed what, and when" },
    ],
  },
  {
    href: "/admin/settings",
    title: "Platform",
    question: "Settings that apply across every tenant.",
    links: [
      { href: "/admin/model-providers", label: "Model Providers", note: "OpenAI-compatible endpoints, dynamic models, completion and Tool Calling tests" },
      { href: "/admin/settings", label: "Platform preamble", note: "prepended to every skill's prompt" },
    ],
    platformOnly: true,
  },
];

export default function AdminHub() {
  const { user, loading } = useAuth();
  const { state, domains, isAdmin, isPlatform, recheck } = useAdminScope(!loading && !!user);

  if (loading || state === "loading") return <Centered>Loading…</Centered>;
  if (!user) return <SignInRequired />;
  if (state === "error") return <Centered><div className="max-w-md text-center"><h1 className="mb-2 text-lg font-semibold">Couldn&apos;t check your access</h1><p className="text-sm text-muted-foreground">We couldn&apos;t reach the admin service. This is a connection problem, not a permissions one — please reload to try again.</p></div></Centered>;
  if (!isAdmin) return <Centered><div className="max-w-md text-center"><h1 className="mb-2 text-lg font-semibold">Admins only</h1><p className="text-sm text-muted-foreground">The admin area requires the <code>aitana-admin</code> group, or <code>tenant-admin:&lt;your-domain&gt;</code> to administer your own tenant.</p><p className="mt-3 text-sm text-muted-foreground">Been granted access just now? A new group tag only lands when your sign-in token refreshes.</p><button type="button" onClick={() => void recheck()} className="mt-2 rounded border px-3 py-1.5 text-sm hover:bg-muted">Re-check my access</button></div></Centered>;

  const areas = AREAS.filter((area) => isPlatform || !area.platformOnly);
  return <main className="mx-auto max-w-4xl p-6">
    <header className="mb-6"><h1 className="text-xl font-semibold">Administration</h1><p className="text-sm text-muted-foreground">Manage tenants, skills, access, MCP integrations, model providers, and analytics.</p>{!isPlatform && domains.length > 0 && <p className="mt-1 text-xs text-muted-foreground">Scoped to {domains.join(", ")} — you&apos;re seeing your tenant only.</p>}</header>
    <div className="grid gap-4 sm:grid-cols-2">{areas.map((area) => <section key={area.title} className="rounded-lg border p-4"><h2 className="font-medium">{area.title}</h2><p className="mt-1 text-sm text-muted-foreground">{area.question}</p><ul className="mt-3 space-y-1.5">{area.links.map((link) => <li key={link.label}><NextLink href={link.href} className="text-sm text-foreground underline-offset-2 hover:underline">{link.label}</NextLink>{link.note && <span className="ml-2 text-xs text-muted-foreground">{link.note}</span>}</li>)}</ul></section>)}</div>
  </main>;
}

function Centered({ children }: { children: React.ReactNode }) { return <main className="flex min-h-screen items-center justify-center p-8">{children}</main>; }
