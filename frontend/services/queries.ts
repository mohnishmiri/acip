"use client";
import { keepPreviousData, useMutation, useQuery, useQueryClient, type UseQueryOptions } from "@tanstack/react-query";
import { api, type Params } from "@/lib/api";
import type { Envelope, ExplorerData, FilterOptions, Freshness, Kpi, Me } from "@/lib/types";

/** Generic GET hook. The query key includes the path and params, so identical requests share one cache entry. */
export function useApi<T>(path: string | null, params?: Params, opts?: Partial<UseQueryOptions<T>>) {
  return useQuery<T>({
    queryKey: [path, params ?? {}],
    queryFn: ({ signal }) => api<T>(path as string, { params, signal }),
    enabled: !!path,
    placeholderData: keepPreviousData,
    ...opts,
  });
}

export const useMe = () => useApi<Me>("/meta/me", undefined, { staleTime: 300_000 });
export const useFilterOptions = () => useApi<FilterOptions>("/meta/filters", undefined, { staleTime: 120_000 });
export const useFreshness = () => useApi<Freshness>("/meta/freshness", undefined, { staleTime: 60_000, refetchInterval: 120_000 });
export const useExplorer = (params: Params) => useApi<Envelope<ExplorerData>>("/costs/explorer", params);
export const useOverview = (params: Params) => useApi<Envelope<{ kpis: Kpi[]; sparklines: Record<string, { bucket: string; value: number }[]>; forecast_method: string }>>("/dashboard/overview", params);

export function useApiMutation<TBody, TResult = unknown>(path: string | ((b: TBody) => string), method = "POST", invalidate: string[] = []) {
  const qc = useQueryClient();
  return useMutation<TResult, Error, TBody>({
    mutationFn: (body: TBody) => api<TResult>(typeof path === "function" ? path(body) : path, { method, body }),
    onSuccess: () => {
      for (const p of invalidate) qc.invalidateQueries({ predicate: (q) => typeof q.queryKey[0] === "string" && (q.queryKey[0] as string).startsWith(p) });
    },
  });
}
