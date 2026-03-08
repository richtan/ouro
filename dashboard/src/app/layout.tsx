import type { Metadata } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import { headers } from "next/headers";
import { cookieToInitialState } from "wagmi";
import "./globals.css";
import Web3Provider, { config } from "@/components/Web3Provider";
import NavBar from "@/components/NavBar";
import Footer from "@/components/Footer";

export const metadata: Metadata = {
  title: "Ouro",
  description:
    "Autonomous HPC compute on Base. Submit jobs, pay with USDC via x402.",
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
    <html
      lang="en"
      className={`dark ${GeistSans.variable} ${GeistMono.variable}`}
    >
      <head>
        <meta name="base:app_id" content="6997ee68820ae5633e55081a" />
        <link rel="icon" href="/favicon.svg" type="image/svg+xml" />
      </head>
      <body className="min-h-screen antialiased font-sans flex flex-col">
        <Web3Provider initialState={initialState}>
          <NavBar />
          {children}
          <Footer />
        </Web3Provider>
      </body>
    </html>
  );
}
