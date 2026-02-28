"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { WagmiProvider, http, cookieStorage, createStorage, type State } from "wagmi";
import { base } from "wagmi/chains";
import { RainbowKitProvider, darkTheme, getDefaultConfig } from "@rainbow-me/rainbowkit";
import "@rainbow-me/rainbowkit/styles.css";

export const config = getDefaultConfig({
  appName: "Ouro Compute",
  projectId: process.env.NEXT_PUBLIC_WALLETCONNECT_PROJECT_ID ?? "NO_WALLETCONNECT",
  chains: [base],
  transports: {
    [base.id]: http(),
  },
  ssr: true,
  storage: createStorage({ storage: cookieStorage }),
});

const queryClient = new QueryClient();

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
          theme={darkTheme({
            accentColor: "#22d3ee",
            accentColorForeground: "#0a0e17",
            borderRadius: "medium",
          })}
        >
          {children}
        </RainbowKitProvider>
      </QueryClientProvider>
    </WagmiProvider>
  );
}
