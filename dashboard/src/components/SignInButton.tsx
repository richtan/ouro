"use client";

import { ConnectButton } from "@rainbow-me/rainbowkit";

/** Shows "Sign In" and opens the RainbowKit modal (which triggers the SIWE sign flow). */
export default function SignInButton() {
  return (
    <ConnectButton.Custom>
      {({ openConnectModal }) => (
        <button
          onClick={openConnectModal}
          type="button"
          className="px-6 py-3 bg-o-blue text-white border border-o-blue rounded-lg text-sm font-medium hover:bg-o-blueHover transition-colors"
        >
          Sign In
        </button>
      )}
    </ConnectButton.Custom>
  );
}
