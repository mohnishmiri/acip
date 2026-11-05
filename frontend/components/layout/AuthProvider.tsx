"use client";
/**
 * Application user sign-in. Runtime configuration comes from /api/v1/meta/client-config so
 * the same container image works in every environment. In "entra" mode the SPA signs the
 * user in with MSAL (authorisation code + PKCE) and sends an access token for the ACIP API;
 * in "disabled" mode (local development only) no sign-in happens.
 */
import { Box, CircularProgress, Typography } from "@mui/material";
import { createContext, type ReactNode, useContext, useEffect, useState } from "react";
import { setTokenGetter } from "@/lib/auth";

interface ClientConfig {
  auth_mode: "disabled" | "entra";
  entra: { tenant_id: string; client_id: string; authority: string; api_scope: string } | null;
  demo_mode: boolean;
  version: string;
}

interface AuthState {
  mode: "disabled" | "entra" | "loading";
  config: ClientConfig | null;
  signOut: () => void;
}

const Ctx = createContext<AuthState>({ mode: "loading", config: null, signOut: () => undefined });
export const useAuth = () => useContext(Ctx);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ mode: "loading", config: null, signOut: () => undefined });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/v1/meta/client-config", { cache: "no-store" });
        if (!res.ok) throw new Error(`Configuration request failed (${res.status})`);
        const cfg = (await res.json()) as ClientConfig;
        if (cfg.auth_mode !== "entra" || !cfg.entra) {
          if (!cancelled) setState({ mode: "disabled", config: cfg, signOut: () => undefined });
          return;
        }
        const msal = await import("@azure/msal-browser");
        const pca = await msal.PublicClientApplication.createPublicClientApplication({
          auth: { clientId: cfg.entra.client_id, authority: cfg.entra.authority, redirectUri: window.location.origin, postLogoutRedirectUri: window.location.origin },
          cache: { cacheLocation: "sessionStorage" },
        });
        const redirect = await pca.handleRedirectPromise();
        const account = redirect?.account ?? pca.getActiveAccount() ?? pca.getAllAccounts()[0];
        if (!account) {
          await pca.loginRedirect({ scopes: [cfg.entra.api_scope] });
          return;
        }
        pca.setActiveAccount(account);
        const scopes = [cfg.entra.api_scope];
        setTokenGetter(async () => {
          try {
            const r = await pca.acquireTokenSilent({ scopes, account });
            return r.accessToken;
          } catch (e) {
            if (e instanceof msal.InteractionRequiredAuthError) await pca.acquireTokenRedirect({ scopes, account });
            throw e;
          }
        });
        if (!cancelled) setState({ mode: "entra", config: cfg, signOut: () => pca.logoutRedirect({ account }) });
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Sign-in failed");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (error)
    return (
      <Box sx={{ display: "grid", placeItems: "center", minHeight: "100vh", p: 4, textAlign: "center" }}>
        <Box>
          <Typography variant="h2">Unable to start ACIP</Typography>
          <Typography color="text.secondary" sx={{ mt: 1 }}>
            {error}
          </Typography>
        </Box>
      </Box>
    );
  if (state.mode === "loading")
    return (
      <Box sx={{ display: "grid", placeItems: "center", minHeight: "100vh" }}>
        <CircularProgress size={28} />
      </Box>
    );
  return <Ctx.Provider value={state}>{children}</Ctx.Provider>;
}
