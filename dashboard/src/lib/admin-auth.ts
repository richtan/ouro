import { SignJWT, jwtVerify } from "jose";

export const ADMIN_COOKIE_NAME = "ouro-admin-session";

const JWT_EXPIRY = "24h";

async function getSecret(): Promise<Uint8Array> {
  // Derive a 256-bit key via SHA-256 so short ADMIN_API_KEY values
  // still produce a full-strength HS256 signing key.
  const raw = new TextEncoder().encode(process.env.ADMIN_API_KEY);
  const hash = await crypto.subtle.digest("SHA-256", raw);
  return new Uint8Array(hash);
}

export function isAdminAuthEnabled(): boolean {
  return !!process.env.ADMIN_API_KEY;
}

export async function signAdminJWT(address: string): Promise<string> {
  return new SignJWT({ sub: address.toLowerCase(), role: "admin" })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime(JWT_EXPIRY)
    .sign(await getSecret());
}

export async function verifyAdminJWT(
  token: string,
): Promise<string | null> {
  try {
    const { payload } = await jwtVerify(token, await getSecret());
    return (payload.sub as string) ?? null;
  } catch {
    return null;
  }
}
