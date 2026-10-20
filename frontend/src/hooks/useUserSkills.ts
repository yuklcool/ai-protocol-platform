"use client";

import { useEffect, useRef, useState } from "react";
import { fetchWithAuth } from "@/lib/apiClient";
import type { Skill } from "@/types/skill";

interface UseUserSkillsReturn {
  skills: Skill[];
  isLoading: boolean;
  error: string | null;
}


export function useUserSkills(uid: string | null): UseUserSkillsReturn {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!uid) {
      setSkills([]);
      setError(null);
      return;
    }

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setIsLoading(true);
    setError(null);

    fetchWithAuth(
      "/api/proxy/api/skills",
      { signal: controller.signal },
    ).then((res) => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json() as Promise<Skill[]>;
    })
      .then((visibleSkills) => setSkills(visibleSkills))
      .catch((err: Error) => {
        if (err.name !== "AbortError") {
          setError("Could not load skills.");
          setSkills([]);
        }
      })
      .finally(() => setIsLoading(false));

    return () => abortRef.current?.abort();
  }, [uid]);

  return { skills, isLoading, error };
}
