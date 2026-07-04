const ACCESS_KEY = "movie_platform_access_token";
const REFRESH_KEY = "movie_platform_refresh_token";

export interface TokenPair {
  access_token: string;
  refresh_token: string;
}

export function saveTokens(tokens: TokenPair): void {
  localStorage.setItem(ACCESS_KEY, tokens.access_token);
  localStorage.setItem(REFRESH_KEY, tokens.refresh_token);
}

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(ACCESS_KEY);
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(REFRESH_KEY);
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

export interface AccessTokenPayload {
  sub: string;
  role: "owner" | "admin" | "moderator";
  exp: number;
}

/**
 * Decodes the access token's payload for UI-only purposes (showing the
 * role, hiding nav items). Not a verification — the API independently
 * enforces every permission server-side regardless of what the client
 * decodes here, so a tampered/forged value can't grant real access.
 */
export function decodeAccessToken(token: string): AccessTokenPayload | null {
  try {
    const payload = token.split(".")[1];
    return JSON.parse(atob(payload.replace(/-/g, "+").replace(/_/g, "/")));
  } catch {
    return null;
  }
}
