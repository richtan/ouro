"use client";

import { createContext, useContext, useMemo, type ReactNode } from "react";
import { useAccount } from "wagmi";
import type { AuthenticationStatus } from "@rainbow-me/rainbowkit";

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

interface AuthProviderProps {
  children: ReactNode;
  authStatus: AuthenticationStatus;
  onSignOut: () => Promise<void>;
}

export function AuthProvider({ children, authStatus, onSignOut }: AuthProviderProps) {
  const { address } = useAccount();

  const value = useMemo<AuthContextValue>(
    () => ({
      isAuthenticated: authStatus === "authenticated",
      isLoading: authStatus === "loading",
      walletAddress:
        authStatus === "authenticated" ? (address?.toLowerCase() ?? null) : null,
      signOut: onSignOut,
    }),
    [authStatus, address, onSignOut],
  );

  return (
    <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
  );
}
