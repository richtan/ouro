import { useQuery } from "@tanstack/react-query";
import { fetchStats, fetchWallet, fetchAttribution } from "@/lib/api";

export function useStats() {
  return useQuery({
    queryKey: ["stats"],
    queryFn: fetchStats,
    refetchInterval: 10_000,
  });
}

export function useWallet() {
  return useQuery({
    queryKey: ["wallet"],
    queryFn: fetchWallet,
    refetchInterval: 10_000,
  });
}

export function useAttribution() {
  return useQuery({
    queryKey: ["attribution"],
    queryFn: fetchAttribution,
    staleTime: 10_000,
    refetchInterval: 15_000,
  });
}
