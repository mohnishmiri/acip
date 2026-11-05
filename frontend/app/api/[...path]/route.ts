/**
 * Runtime proxy from the browser to the backend API.
 * BACKEND_INTERNAL_URL is read at request time, so the same image works locally (Docker
 * Compose) and in AKS. In AKS the ingress may route /api directly to the backend instead.
 * Only an allow-list of headers is forwarded; no credentials are added here.
 */
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const FORWARD_REQUEST = ["authorization", "content-type", "accept", "x-request-id", "x-acip-dev-role", "x-acip-dev-application"];
const FORWARD_RESPONSE = ["content-type", "content-disposition", "x-request-id", "cache-control"];

async function proxy(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  const backend = (process.env.BACKEND_INTERNAL_URL || "http://localhost:8000").replace(/\/$/, "");
  const search = new URL(req.url).search;
  const target = `${backend}/api/${path.map(encodeURIComponent).join("/")}${search}`;
  const headers = new Headers();
  for (const h of FORWARD_REQUEST) {
    const v = req.headers.get(h);
    if (v) headers.set(h, v);
  }
  let res: Response;
  try {
    res = await fetch(target, {
      method: req.method,
      headers,
      body: req.method === "GET" || req.method === "HEAD" ? undefined : await req.arrayBuffer(),
      cache: "no-store",
    });
  } catch {
    return NextResponse.json({ error: { code: "backend_unavailable", message: "The ACIP API is not reachable." } }, { status: 502 });
  }
  const out = new Headers();
  for (const h of FORWARD_RESPONSE) {
    const v = res.headers.get(h);
    if (v) out.set(h, v);
  }
  return new NextResponse(res.status === 204 ? null : res.body, { status: res.status, headers: out });
}

export { proxy as GET, proxy as POST, proxy as PUT, proxy as DELETE };
