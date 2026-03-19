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
  isLoading: boolean;
  walletAddress: string | null;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue>({
  isAuthenticated: false,
  isLoading: true,
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
  const [loading, setLoading] = useState(true);
  const prevAddressRef = useRef<string | undefined>(undefined);
  const sessionCheckRef = useRef<AbortController | null>(null);

  // Check existing session on mount / address change
  useEffect(() => {
    if (!isConnected || !address) {
      setAuthenticated(false);
      setWalletAddress(null);
      // Don't set loading = false here — pages check !isConnected before authLoading
      return;
    }

    const controller = new AbortController();
    sessionCheckRef.current = controller;
    setLoading(true);

    const checkSession = async () => {
      try {
        const res = await fetch("/api/auth/check", { signal: controller.signal });
        if (controller.signal.aborted) return;
        if (res.ok) {
          const data = await res.json();
          if (controller.signal.aborted) return;
          if (data.address?.toLowerCase() === address.toLowerCase()) {
            setAuthenticated(true);
            setWalletAddress(data.address);
            return;
          }
        }
      } catch {
        if (controller.signal.aborted) return;
      }
      if (!controller.signal.aborted) {
        setAuthenticated(false);
        setWalletAddress(null);
      }
    };

    checkSession().finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });

    return () => { controller.abort(); };
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

  // Watch for disconnect — abortable logout prevents race with rapid reconnect
  const wasConnectedRef = useRef(false);
  const logoutAbortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (isConnected) {
      wasConnectedRef.current = true;
      // Cancel any in-flight logout from a previous disconnect
      logoutAbortRef.current?.abort();
      logoutAbortRef.current = null;
    } else if (wasConnectedRef.current) {
      // Was connected, now disconnected — actual disconnect
      wasConnectedRef.current = false;
      const controller = new AbortController();
      logoutAbortRef.current = controller;
      fetch("/api/auth/logout", { method: "POST", signal: controller.signal }).catch(() => {});
      setAuthenticated(false);
      setWalletAddress(null);
    }
  }, [isConnected]);

  // Re-check session when SIWE verify succeeds
  useEffect(() => {
    const onAuthChange = () => {
      if (isConnected && address) {
        sessionCheckRef.current?.abort(); // Cancel stale in-flight session check
        // Optimistic — event only fires after successful login POST
        setAuthenticated(true);
        setWalletAddress(address);
        setLoading(false);
        // Background confirmation
        fetch("/api/auth/check")
          .then((r) => (r.ok ? r.json() : null))
          .then((data) => {
            if (!data || data.address?.toLowerCase() !== address.toLowerCase()) {
              setAuthenticated(false);
              setWalletAddress(null);
            }
          })
          .catch(() => {});
      }
    };
    window.addEventListener("ouro-auth-change", onAuthChange);
    return () => window.removeEventListener("ouro-auth-change", onAuthChange);
  }, [isConnected, address]);

  // Re-check session on window focus (catches expired sessions, cross-tab sign-ins)
  useEffect(() => {
    let controller: AbortController | null = null;
    const onFocus = () => {
      if (isConnected && address) {
        controller?.abort();
        controller = new AbortController();
        const signal = controller.signal;
        fetch("/api/auth/check", { signal })
          .then((r) => (r.ok ? r.json() : null))
          .then((data) => {
            if (signal.aborted) return;
            if (data?.address?.toLowerCase() === address.toLowerCase()) {
              setAuthenticated(true);
              setWalletAddress(data.address);
            } else {
              setAuthenticated(false);
              setWalletAddress(null);
            }
          })
          .catch(() => {});
      }
    };
    window.addEventListener("focus", onFocus);
    return () => {
      window.removeEventListener("focus", onFocus);
      controller?.abort();
    };
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
        isLoading: loading,
        walletAddress,
        signOut,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
