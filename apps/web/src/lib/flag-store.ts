// meta: client lifecycle state for flags (zustand). Seeded from API flag
// payloads as they load; disposition mutations write optimistically, then
// reconcile with the server's returned {flag} (server is the source of
// truth; a 409/network error reverts the optimistic write and surfaces an
// inline per-flag error). No Undo anymore: the M4 lifecycle state machine
// has no reverse transitions (dismissed is terminal).

import { create } from "zustand";
import type { FlagState } from "@/lib/types";

export interface FlagLifecycle {
  state: FlagState;
  team: string | null;
  note: string | null;
}

interface FlagStore {
  lifecycles: Record<string, FlagLifecycle>;
  errors: Record<string, string | null>;
  seed: (entries: Record<string, FlagLifecycle>) => void;
  setLifecycle: (flagId: string, lifecycle: FlagLifecycle) => void;
  setError: (flagId: string, message: string | null) => void;
}

export const useFlagStore = create<FlagStore>((set) => ({
  lifecycles: {},
  errors: {},
  seed: (entries) =>
    set((s) => ({ lifecycles: { ...s.lifecycles, ...entries } })),
  setLifecycle: (flagId, lifecycle) =>
    set((s) => ({ lifecycles: { ...s.lifecycles, [flagId]: lifecycle } })),
  setError: (flagId, message) =>
    set((s) => ({ errors: { ...s.errors, [flagId]: message } })),
}));
