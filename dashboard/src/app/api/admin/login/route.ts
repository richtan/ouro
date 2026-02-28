import { NextRequest, NextResponse } from "next/server";
import { verifyMessage } from "viem";
import {
  ADMIN_COOKIE_NAME,
  isAdminAuthEnabled,
  signAdminJWT,
} from "@/lib/admin-auth";

export const dynamic = "force-dynamic";

const MAX_AGE_S = 86400; // 24 hours
const TIMESTAMP_WINDOW_S = 300; // 5 minutes

export async function POST(request: NextRequest) {
  if (!isAdminAuthEnabled()) {
    return NextResponse.json({ error: "Admin auth not configured" }, { status: 503 });
  }

  const adminAddress = process.env.NEXT_PUBLIC_ADMIN_ADDRESS;
  if (!adminAddress) {
    return NextResponse.json({ error: "Admin address not configured" }, { status: 503 });
  }

  let body: { address?: string; message?: string; signature?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const { address, message, signature } = body;
  if (!address || !message || !signature) {
    return NextResponse.json({ error: "address, message, and signature required" }, { status: 400 });
  }

  if (address.toLowerCase() !== adminAddress.toLowerCase()) {
    return NextResponse.json({ error: "Not an admin address" }, { status: 403 });
  }

  const tsMatch = message.match(/Ouro Admin Auth (\d+)/);
  if (!tsMatch) {
    return NextResponse.json({ error: "Invalid message format" }, { status: 400 });
  }
  const msgTs = parseInt(tsMatch[1], 10);
  const nowTs = Math.floor(Date.now() / 1000);
  if (Math.abs(nowTs - msgTs) > TIMESTAMP_WINDOW_S) {
    return NextResponse.json({ error: "Message timestamp expired" }, { status: 400 });
  }

  let valid: boolean;
  try {
    valid = await verifyMessage({
      address: address as `0x${string}`,
      message,
      signature: signature as `0x${string}`,
    });
  } catch {
    return NextResponse.json({ error: "Signature verification failed" }, { status: 400 });
  }

  if (!valid) {
    return NextResponse.json({ error: "Invalid signature" }, { status: 403 });
  }

  const jwt = await signAdminJWT(address);

  const isProduction = process.env.NODE_ENV === "production";
  const cookieParts = [
    `${ADMIN_COOKIE_NAME}=${jwt}`,
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
