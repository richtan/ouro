"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { WagmiProvider, http, cookieStorage, createStorage, type State } from "wagmi";
import { base } from "wagmi/chains";
import {
  RainbowKitProvider,
  darkTheme,
  getDefaultConfig,
  createAuthenticationAdapter,
  RainbowKitAuthenticationProvider,
  type Theme,
  type AuthenticationStatus,
} from "@rainbow-me/rainbowkit";
import {
  metaMaskWallet,
  coinbaseWallet,
  walletConnectWallet,
} from "@rainbow-me/rainbowkit/wallets";
import { createSiweMessage } from "viem/siwe";
import { AuthProvider } from "@/contexts/AuthContext";
import "@rainbow-me/rainbowkit/styles.css";

export const config = getDefaultConfig({
  appName: "Ouro",
  projectId: process.env.NEXT_PUBLIC_WALLETCONNECT_PROJECT_ID ?? "NO_WALLETCONNECT",
  chains: [base],
  transports: {
    [base.id]: http(),
  },
  ssr: true,
  storage: createStorage({ storage: cookieStorage }),
  wallets: [
    {
      groupName: "Recommended",
      wallets: [metaMaskWallet, coinbaseWallet, walletConnectWallet],
    },
  ],
});

const ouroTheme: Theme = {
  ...darkTheme({
    accentColor: "#0052ff",
    accentColorForeground: "#ffffff",
    borderRadius: "medium",
    fontStack: "system",
    overlayBlur: "none",
  }),
  colors: {
    ...darkTheme().colors,
    accentColor: "#0052ff",
    accentColorForeground: "#ffffff",
    connectButtonBackground: "#111316",
    connectButtonInnerBackground: "#191b1f",
    connectButtonText: "#f5f5f5",
    connectButtonTextError: "#ef4444",
    connectButtonBackgroundError: "#111316",
    connectionIndicator: "#22c55e",
    error: "#ef4444",
    generalBorder: "#1e2025",
    generalBorderDim: "#1e2025",
    menuItemBackground: "#191b1f",
    modalBackground: "#111316",
    modalBorder: "#1e2025",
    modalText: "#f5f5f5",
    modalTextDim: "#5b616e",
    modalTextSecondary: "#8a919e",
    modalBackdrop: "rgba(0, 0, 0, 0.6)",
    profileAction: "#191b1f",
    profileActionHover: "#1e2025",
    profileForeground: "#111316",
    closeButton: "#8a919e",
    closeButtonBackground: "#191b1f",
    actionButtonBorder: "#1e2025",
    actionButtonBorderMobile: "#1e2025",
    actionButtonSecondaryBackground: "#191b1f",
    downloadBottomCardBackground: "#0a0b0d",
    downloadTopCardBackground: "#111316",
    selectedOptionBorder: "#0052ff",
    standby: "#eab308",
  },
  fonts: {
    body: "var(--font-geist-sans), system-ui, sans-serif",
  },
  shadows: {
    connectButton: "none",
    dialog: "0 8px 32px rgba(0, 0, 0, 0.4)",
    profileDetailsAction: "none",
    selectedOption: "none",
    selectedWallet: "none",
    walletLogo: "none",
  },
};

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5_000,
      retry: 1,
    },
  },
});

export default function Web3Provider({
  children,
  initialState,
}: {
  children: React.ReactNode;
  initialState?: State;
}) {
  const [status, setStatus] = useState<AuthenticationStatus>("loading");
  const fetchingRef = useRef(false);
  const verifyingRef = useRef(false);

  const checkAuth = useCallback(async () => {
    if (fetchingRef.current) return;
    fetchingRef.current = true;
    try {
      const res = await fetch("/api/auth/check");
      if (res.ok) {
        const data = await res.json();
        if (data.address) {
          setStatus("authenticated");
          return;
        }
      }
      setStatus("unauthenticated");
    } catch {
      setStatus("unauthenticated");
    } finally {
      fetchingRef.current = false;
    }
  }, []);

  // Check auth on mount
  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  // Re-check on window focus (catches expired sessions in other tabs)
  useEffect(() => {
    const onFocus = () => checkAuth();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [checkAuth]);

  const adapter = useMemo(
    () =>
      createAuthenticationAdapter({
        getNonce: async () => {
          const res = await fetch("/api/auth/nonce");
          const { nonce } = await res.json();
          return nonce;
        },
        createMessage: ({ nonce, address, chainId }) => {
          return createSiweMessage({
            domain: window.location.host,
            address: address as `0x${string}`,
            statement: "Sign in to Ouro",
            uri: window.location.origin,
            version: "1",
            chainId,
            nonce,
          });
        },
        verify: async ({ message, signature }) => {
          if (verifyingRef.current) return false;
          verifyingRef.current = true;
          try {
            const res = await fetch("/api/auth/login", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ message, signature }),
            });
            if (res.ok) {
              setStatus("authenticated");
              window.dispatchEvent(new Event("ouro-auth-change"));
              return true;
            }
            return false;
          } catch {
            return false;
          } finally {
            verifyingRef.current = false;
          }
        },
        signOut: async () => {
          await fetch("/api/auth/logout", { method: "POST" });
          setStatus("unauthenticated");
        },
      }),
    [],
  );

  return (
    <WagmiProvider config={config} initialState={initialState}>
      <QueryClientProvider client={queryClient}>
        <RainbowKitAuthenticationProvider adapter={adapter} status={status}>
          <RainbowKitProvider theme={ouroTheme}>
            <AuthProvider>{children}</AuthProvider>
          </RainbowKitProvider>
        </RainbowKitAuthenticationProvider>
      </QueryClientProvider>
    </WagmiProvider>
  );
}
