// API base URL. In production (Vercel) set VITE_API_URL to the Railway
// backend, e.g. https://your-backend.up.railway.app. In local dev it's unset,
// so calls stay relative ("/api/...") and go through the Vite proxy to
// localhost:8000 — dev behaviour is unchanged.
const BASE = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");

export const api = (path) => `${BASE}${path}`;
