import type { Metadata } from "next";
import { headers } from "next/headers";
import { cookieToInitialState } from "wagmi";
import "./globals.css";
import Web3Provider, { config } from "@/components/Web3Provider";
import NavBar from "@/components/NavBar";

export const metadata: Metadata = {
  title: "Ouro — Proof-of-Compute Oracle",
  description:
    "Self-sustaining autonomous HPC agent on Base. Submit compute jobs, pay with USDC via x402, and get verifiable on-chain proofs.",
};

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const headersList = await headers();
  const cookie = headersList.get("cookie");
  const initialState = cookieToInitialState(config, cookie);

  return (
    <html lang="en" className="dark">
      <head>
        <meta name="base:app_id" content="6997ee68820ae5633e55081a" />
        <link rel="icon" href="/favicon.svg" type="image/svg+xml" />
      </head>
      <body className="min-h-screen antialiased relative">
        <Web3Provider initialState={initialState}>
          <NavBar />
          {children}
        </Web3Provider>
      </body>
    </html>
  );
}
