import { SignJWT, jwtVerify } from "jose";

export const ADMIN_COOKIE_NAME = "ouro-admin-session";

const JWT_EXPIRY = "24h";

function getSecret(): Uint8Array {
  return new TextEncoder().encode(process.env.ADMIN_API_KEY);
}

export function isAdminAuthEnabled(): boolean {
  return !!process.env.ADMIN_API_KEY;
}

export async function signAdminJWT(address: string): Promise<string> {
  return new SignJWT({ sub: address.toLowerCase() })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime(JWT_EXPIRY)
    .sign(getSecret());
}

export async function verifyAdminJWT(
  token: string,
): Promise<string | null> {
  try {
    const { payload } = await jwtVerify(token, getSecret());
    return (payload.sub as string) ?? null;
  } catch {
    return null;
  }
}
