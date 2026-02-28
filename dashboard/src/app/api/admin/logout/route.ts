import { NextResponse } from "next/server";
import { ADMIN_COOKIE_NAME } from "@/lib/admin-auth";

export const dynamic = "force-dynamic";

export async function POST() {
  const isProduction = process.env.NODE_ENV === "production";
  const cookieParts = [
    `${ADMIN_COOKIE_NAME}=`,
    "HttpOnly",
    "SameSite=Strict",
    "Path=/",
    "Max-Age=0",
  ];
  if (isProduction) cookieParts.push("Secure");

  const res = NextResponse.json({ ok: true });
  res.headers.set("Set-Cookie", cookieParts.join("; "));
  return res;
}
