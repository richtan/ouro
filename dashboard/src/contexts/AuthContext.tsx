"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useAccount } from "wagmi";

interface AuthContextValue {
  isAuthenticated: boolean;
  walletAddress: string | null;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue>({
  isAuthenticated: false,
  walletAddress: null,
  signOut: async () => {},
});

export function useAuth() {
  return useContext(AuthContext);
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const { address, isConnected } = useAccount();
  const [walletAddress, setWalletAddress] = useState<string | null>(null);
  const [authenticated, setAuthenticated] = useState(false);
  const prevAddressRef = useRef<string | undefined>(undefined);

  // Check existing session on mount / address change
  useEffect(() => {
    if (!isConnected || !address) {
      setAuthenticated(false);
      setWalletAddress(null);
      return;
    }

    const checkSession = async () => {
      try {
        const res = await fetch("/api/auth/check");
        if (res.ok) {
          const data = await res.json();
          if (data.address?.toLowerCase() === address.toLowerCase()) {
            setAuthenticated(true);
            setWalletAddress(data.address);
            return;
          }
        }
      } catch {
        // Session check failed
      }
      setAuthenticated(false);
      setWalletAddress(null);
    };

    checkSession();
  }, [isConnected, address]);

  // Watch for wallet switch → logout old session
  useEffect(() => {
    const prev = prevAddressRef.current;
    prevAddressRef.current = address;

    if (prev && address && prev.toLowerCase() !== address.toLowerCase()) {
      fetch("/api/auth/logout", { method: "POST" }).catch(() => {});
      setAuthenticated(false);
      setWalletAddress(null);
    }
  }, [address]);

  // Watch for disconnect
  useEffect(() => {
    if (!isConnected) {
      fetch("/api/auth/logout", { method: "POST" }).catch(() => {});
      setAuthenticated(false);
      setWalletAddress(null);
    }
  }, [isConnected]);

  // Re-check session when SIWE verify succeeds
  useEffect(() => {
    const onAuthChange = () => {
      if (isConnected && address) {
        // Session cookie was just set — re-check
        fetch("/api/auth/check")
          .then((r) => (r.ok ? r.json() : null))
          .then((data) => {
            if (data?.address?.toLowerCase() === address.toLowerCase()) {
              setAuthenticated(true);
              setWalletAddress(data.address);
            }
          })
          .catch(() => {});
      }
    };
    window.addEventListener("ouro-auth-change", onAuthChange);
    return () => window.removeEventListener("ouro-auth-change", onAuthChange);
  }, [isConnected, address]);

  const signOut = useCallback(async () => {
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } catch {
      // Best effort
    }
    setAuthenticated(false);
    setWalletAddress(null);
  }, []);

  return (
    <AuthContext.Provider
      value={{
        isAuthenticated: authenticated,
        walletAddress,
        signOut,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
