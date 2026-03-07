import { useState, useEffect } from "react";
import { useAccount } from "wagmi";

export function useWalletReady() {
  const { isConnected, address, status } = useAccount();
  const [mounted, setMounted] = useState(false);
  useEffect(() => { setMounted(true); }, []);
  return {
    isConnected,
    address,
    // Ready only after mount AND wagmi has settled to a final state
    isReady: mounted && (status === "connected" || status === "disconnected"),
  };
}
