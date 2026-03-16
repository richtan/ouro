"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { WagmiProvider, http, cookieStorage, createStorage, type State } from "wagmi";
import { base } from "wagmi/chains";
import { RainbowKitProvider, darkTheme, getDefaultConfig, type Theme } from "@rainbow-me/rainbowkit";
import {
  metaMaskWallet,
  coinbaseWallet,
  walletConnectWallet,
} from "@rainbow-me/rainbowkit/wallets";
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
  return (
    <WagmiProvider config={config} initialState={initialState}>
      <QueryClientProvider client={queryClient}>
        <RainbowKitProvider
          theme={ouroTheme}
        >
          <AuthProvider>{children}</AuthProvider>
        </RainbowKitProvider>
      </QueryClientProvider>
    </WagmiProvider>
  );
}
