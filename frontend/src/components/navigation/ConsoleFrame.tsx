"use client";

import type { ReactNode } from "react";
import { usePathname } from "next/navigation";
import { ConsoleMobileNav, ConsoleSidebar } from "./ConsoleSidebar";

const PUBLIC_PATHS = ["/", "/auth"];

function isPublicPath(pathname: string) {
  return PUBLIC_PATHS.some((path) => pathname === path || pathname.startsWith(`${path}/`));
}

export function ConsoleFrame({ children }: { children: ReactNode }) {
  const pathname = usePathname() || "/";
  if (isPublicPath(pathname)) return <>{children}</>;

  return (
    <div className="console-frame">
      <ConsoleSidebar />
      <div className="console-main">
        <ConsoleMobileNav />
        <div className="console-content">{children}</div>
      </div>
    </div>
  );
}
