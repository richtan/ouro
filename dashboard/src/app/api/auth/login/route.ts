import { NextRequest, NextResponse } from "next/server";
import { verifyMessage } from "viem";
import { WALLET_COOKIE_NAME, signWalletJWT } from "@/lib/wallet-auth";

export const dynamic = "force-dynamic";

const MAX_AGE_S = 86400; // 24 hours
const TIMESTAMP_WINDOW_S = 300; // 5 minutes

export async function POST(request: NextRequest) {
  let body: { address?: string; message?: string; signature?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const { address, message, signature } = body;
  if (!address || !message || !signature) {
    return NextResponse.json(
      { error: "address, message, and signature required" },
      { status: 400 },
    );
  }

  // Verify message format: "Ouro Session\nWallet: {address}\nTimestamp: {timestamp}"
  const match = message.match(
    /^Ouro Session\nWallet: (0x[0-9a-fA-F]{40})\nTimestamp: (\d+)$/,
  );
  if (!match) {
    return NextResponse.json(
      { error: "Invalid message format" },
      { status: 400 },
    );
  }

  const [, msgAddress, msgTimestamp] = match;

  // Verify address in message matches claimed address
  if (msgAddress.toLowerCase() !== address.toLowerCase()) {
    return NextResponse.json(
      { error: "Address mismatch" },
      { status: 400 },
    );
  }

  // Verify timestamp within window
  const ts = parseInt(msgTimestamp, 10);
  const nowTs = Math.floor(Date.now() / 1000);
  if (Math.abs(nowTs - ts) > TIMESTAMP_WINDOW_S) {
    return NextResponse.json(
      { error: "Message timestamp expired" },
      { status: 400 },
    );
  }

  // Verify signature
  let valid: boolean;
  try {
    valid = await verifyMessage({
      address: address as `0x${string}`,
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

  const jwt = await signWalletJWT(address);

  const isProduction = process.env.NODE_ENV === "production";
  const cookieParts = [
    `${WALLET_COOKIE_NAME}=${jwt}`,
    "HttpOnly",
    "SameSite=Strict",
    "Path=/",
    `Max-Age=${MAX_AGE_S}`,
  ];
  if (isProduction) cookieParts.push("Secure");

  const res = NextResponse.json({ ok: true });
  res.headers.set("Set-Cookie", cookieParts.join("; "));
  return res;
}
