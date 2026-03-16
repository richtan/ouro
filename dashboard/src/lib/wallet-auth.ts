import { SignJWT, jwtVerify } from "jose";
import { cookies } from "next/headers";

export const WALLET_COOKIE_NAME = "ouro-session";

const JWT_EXPIRY = "24h";

async function getSecret(): Promise<Uint8Array> {
  // Derive from ADMIN_API_KEY + "wallet-session" to prevent cross-token confusion with admin JWTs
  const raw = new TextEncoder().encode(
    (process.env.ADMIN_API_KEY ?? "") + "wallet-session",
  );
  const hash = await crypto.subtle.digest("SHA-256", raw);
  return new Uint8Array(hash);
}

export async function signWalletJWT(address: string): Promise<string> {
  return new SignJWT({ sub: address.toLowerCase(), role: "user" })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime(JWT_EXPIRY)
    .sign(await getSecret());
}

export async function verifyWalletJWT(
  token: string,
): Promise<string | null> {
  try {
    const { payload } = await jwtVerify(token, await getSecret());
    if (payload.role !== "user") return null;
    return (payload.sub as string) ?? null;
  } catch {
    return null;
  }
}

/**
 * Read ouro-session cookie, verify JWT, return wallet address or null.
 */
export async function getWalletFromRequest(): Promise<string | null> {
  const cookieStore = await cookies();
  const token = cookieStore.get(WALLET_COOKIE_NAME)?.value;
  if (!token) return null;
  return verifyWalletJWT(token);
}
