import { NextRequest, NextResponse } from "next/server";
import { createPublicClient, http } from "viem";
import { base } from "viem/chains";
import { parseSiweMessage } from "viem/siwe";
import { WALLET_COOKIE_NAME, signWalletJWT } from "@/lib/wallet-auth";

const publicClient = createPublicClient({
  chain: base,
  transport: http(),
});

export const dynamic = "force-dynamic";

const MAX_AGE_S = 86400; // 24 hours
const NONCE_COOKIE = "ouro-nonce";

export async function POST(request: NextRequest) {
  let body: { message?: string; signature?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const { message, signature } = body;
  if (!message || !signature) {
    return NextResponse.json(
      { error: "message and signature required" },
      { status: 400 },
    );
  }

  // Parse SIWE message
  const parsed = parseSiweMessage(message);
  if (!parsed.address || !parsed.nonce) {
    return NextResponse.json(
      { error: "Invalid SIWE message" },
      { status: 400 },
    );
  }

  // Verify nonce matches cookie
  const nonceCookie = request.cookies.get(NONCE_COOKIE)?.value;
  if (!nonceCookie || nonceCookie !== parsed.nonce) {
    return NextResponse.json(
      { error: "Invalid or expired nonce" },
      { status: 400 },
    );
  }

  // Verify signature
  let valid: boolean;
  try {
    valid = await publicClient.verifyMessage({
      address: parsed.address,
      message,
      signature: signature as `0x${string}`,
    });
  } catch {
    return NextResponse.json(
      { error: "Signature verification failed" },
      { status: 400 },
    );
  }

  if (!valid) {
    return NextResponse.json(
      { error: "Invalid signature" },
      { status: 403 },
    );
  }

  const jwt = await signWalletJWT(parsed.address);

  const isProduction = process.env.NODE_ENV === "production";
  const sessionParts = [
    `${WALLET_COOKIE_NAME}=${jwt}`,
    "HttpOnly",
    "SameSite=Strict",
    "Path=/",
    `Max-Age=${MAX_AGE_S}`,
  ];
  if (isProduction) sessionParts.push("Secure");

  // Clear nonce cookie
  const clearNonce = [
    `${NONCE_COOKIE}=`,
    "HttpOnly",
    "SameSite=Strict",
    "Path=/",
    "Max-Age=0",
  ];
  if (isProduction) clearNonce.push("Secure");

  const res = NextResponse.json({ ok: true });
  res.headers.append("Set-Cookie", sessionParts.join("; "));
  res.headers.append("Set-Cookie", clearNonce.join("; "));
  return res;
}
