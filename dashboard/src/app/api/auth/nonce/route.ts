import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const NONCE_COOKIE = "ouro-nonce";
const NONCE_MAX_AGE_S = 300; // 5 minutes

export async function GET() {
  const nonce = Array.from(crypto.getRandomValues(new Uint8Array(16)))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");

  const isProduction = process.env.NODE_ENV === "production";
  const cookieParts = [
    `${NONCE_COOKIE}=${nonce}`,
    "HttpOnly",
    "SameSite=Strict",
    "Path=/",
    `Max-Age=${NONCE_MAX_AGE_S}`,
  ];
  if (isProduction) cookieParts.push("Secure");

  const res = NextResponse.json({ nonce });
  res.headers.set("Set-Cookie", cookieParts.join("; "));
  return res;
}
