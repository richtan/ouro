import { NextResponse } from "next/server";
import { getWalletFromRequest } from "@/lib/wallet-auth";

export const dynamic = "force-dynamic";

export async function GET() {
  const address = await getWalletFromRequest();
  if (!address) {
    return NextResponse.json(
      { error: "Not authenticated" },
      { status: 401 },
    );
  }

  return NextResponse.json({ ok: true, address });
}
