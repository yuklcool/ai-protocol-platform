"use client";

import { useCallback, useEffect, useState } from "react";
import { fetchWithAuth } from "@/lib/apiClient";
import type { Skill } from "@/types/skill";

interface UseUserSkillsReturn {
  skills: Skill[];
  isLoading: boolean;
  error: string | null;
  retry: () => void;
}

export function useUserSkills(uid: string | null): UseUserSkillsReturn {
  const [state, setState] = useState<{
    uid: string | null;
    skills: Skill[];
    isLoading: boolean;
    error: string | null;
  }>({ uid, skills: [], isLoading: !!uid, error: null });
  const [revision, setRevision] = useState(0);
  const retry = useCallback(() => setRevision((value) => value + 1), []);

  useEffect(() => {
    const controller = new AbortController();
    setState({ uid, skills: [], isLoading: !!uid, error: null });
    if (!uid) return () => controller.abort();

    fetchWithAuth("/api/proxy/api/skills", { signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json() as Promise<Skill[]>;
      })
      .then((skills) => {
        if (!controller.signal.aborted) {
          setState({ uid, skills, isLoading: false, error: null });
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setState({ uid, skills: [], isLoading: false, error: "Could not load skills." });
        }
      });

    return () => controller.abort();
  }, [uid, revision]);

  return {
    ...(state.uid === uid ? state : { skills: [], isLoading: !!uid, error: null }),
    retry,
  };
}
