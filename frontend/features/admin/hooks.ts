"use client";
import { useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { api } from "@/lib/api";
import { errorMessage, useToast } from "./ui";

/** Invalidate admin-related caches (and anything that depends on configuration). */
export function useAdminInvalidate() {
  const qc = useQueryClient();
  return useCallback(
    (...prefixes: string[]) =>
      qc.invalidateQueries({
        predicate: (q) => typeof q.queryKey[0] === "string" && ["/admin", "/meta", "/azure", "/anomalies", ...prefixes].some((p) => (q.queryKey[0] as string).startsWith(p)),
      }),
    [qc],
  );
}

/** Run a mutation with toast feedback; returns true on success. */
export function useMutate() {
  const toast = useToast();
  const invalidate = useAdminInvalidate();
  return useCallback(
    async (fn: () => Promise<unknown>, success: string, ...prefixes: string[]) => {
      try {
        await fn();
        toast(success);
        invalidate(...prefixes);
        return true;
      } catch (e) {
        toast(errorMessage(e), "error");
        return false;
      }
    },
    [toast, invalidate],
  );
}

export { api };
