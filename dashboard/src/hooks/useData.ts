import { useQuery } from "@tanstack/react-query";
import { fetchStats, fetchWallet, fetchPrice } from "@/lib/api";

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

export function usePricing() {
  return useQuery({
    queryKey: ["pricing"],
    queryFn: fetchPrice,
    staleTime: 60_000,
    refetchInterval: 60_000,
  });
}
