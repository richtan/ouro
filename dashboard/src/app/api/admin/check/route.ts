import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import {
  ADMIN_COOKIE_NAME,
  isAdminAuthEnabled,
  verifyAdminJWT,
} from "@/lib/admin-auth";

export const dynamic = "force-dynamic";

export async function GET() {
  if (!isAdminAuthEnabled()) {
    return NextResponse.json({ ok: true });
  }

  const cookieStore = await cookies();
  const token = cookieStore.get(ADMIN_COOKIE_NAME)?.value;
  if (!token) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  const address = await verifyAdminJWT(token);
  if (!address) {
    return NextResponse.json({ error: "Invalid or expired session" }, { status: 401 });
  }

  return NextResponse.json({ ok: true, address });
}
