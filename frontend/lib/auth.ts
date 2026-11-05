/**
 * Token plumbing for application users (Microsoft Entra ID via MSAL).
 * The collection service principal is never used or visible in the browser.
 */
type TokenGetter = () => Promise<string | null>;

let tokenGetter: TokenGetter = async () => null;
export function setTokenGetter(fn: TokenGetter) {
  tokenGetter = fn;
}
export function getToken(): Promise<string | null> {
  return tokenGetter();
}

/** Local development only (APP_AUTH_MODE=disabled): simulate a role to exercise RBAC. */
export const DEV_ROLE_KEY = "acip.devRole";
export function getDevRole(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(DEV_ROLE_KEY);
}
