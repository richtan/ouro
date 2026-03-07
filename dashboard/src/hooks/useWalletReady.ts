import { useAccount } from "wagmi";

export function useWalletReady() {
  const { isConnected, isReconnecting, address } = useAccount();
  return {
    isConnected,
    address,
    // True when we know the final connection state (not still reconnecting from cookies)
    isReady: !isReconnecting,
  };
}
