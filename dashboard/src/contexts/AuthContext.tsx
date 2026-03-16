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
import { useAccount, useSignMessage } from "wagmi";

type AuthState = "idle" | "signing" | "authenticated" | "error";

interface AuthContextValue {
  isAuthenticated: boolean;
  walletAddress: string | null;
  authState: AuthState;
  signIn: () => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue>({
  isAuthenticated: false,
  walletAddress: null,
  authState: "idle",
  signIn: async () => {},
  signOut: async () => {},
});

export function useAuth() {
  return useContext(AuthContext);
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const { address, isConnected } = useAccount();
  const { signMessageAsync } = useSignMessage();
  const [authState, setAuthState] = useState<AuthState>("idle");
  const [walletAddress, setWalletAddress] = useState<string | null>(null);
  const prevAddressRef = useRef<string | undefined>(undefined);

  // Check existing session on mount / address change
  useEffect(() => {
    if (!isConnected || !address) {
      setAuthState("idle");
      setWalletAddress(null);
      return;
    }

    const checkSession = async () => {
      try {
        const res = await fetch("/api/auth/check");
        if (res.ok) {
          const data = await res.json();
          // Verify the session matches current wallet
          if (data.address?.toLowerCase() === address.toLowerCase()) {
            setAuthState("authenticated");
            setWalletAddress(data.address);
            return;
          }
        }
      } catch {
        // Session check failed — not authenticated
      }
      setAuthState("idle");
      setWalletAddress(null);
    };

    checkSession();
  }, [isConnected, address]);

  // Watch for wallet switch → logout old session
  useEffect(() => {
    const prev = prevAddressRef.current;
    prevAddressRef.current = address;

    if (prev && address && prev.toLowerCase() !== address.toLowerCase()) {
      // Wallet changed — clear old session
      fetch("/api/auth/logout", { method: "POST" }).catch(() => {});
      setAuthState("idle");
      setWalletAddress(null);
    }
  }, [address]);

  // Watch for disconnect
  useEffect(() => {
    if (!isConnected) {
      fetch("/api/auth/logout", { method: "POST" }).catch(() => {});
      setAuthState("idle");
      setWalletAddress(null);
    }
  }, [isConnected]);

  const signIn = useCallback(async () => {
    if (!address) return;
    setAuthState("signing");
    try {
      const timestamp = Math.floor(Date.now() / 1000);
      const message = `Ouro Session\nWallet: ${address}\nTimestamp: ${timestamp}`;
      const signature = await signMessageAsync({ message });

      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ address, message, signature }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || "Login failed");
      }

      setAuthState("authenticated");
      setWalletAddress(address.toLowerCase());
    } catch {
      setAuthState("error");
    }
  }, [address, signMessageAsync]);

  const signOut = useCallback(async () => {
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } catch {
      // Best effort
    }
    setAuthState("idle");
    setWalletAddress(null);
  }, []);

  return (
    <AuthContext.Provider
      value={{
        isAuthenticated: authState === "authenticated",
        walletAddress,
        authState,
        signIn,
        signOut,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
