// src/api.js — owned by Member 1, matches api/main.py exactly.
// Every function returns a Promise resolving to already-parsed JSON.
//
// URL layout
//   R1 routes: FastAPI registers them as  GET /api/summary  etc.
//              → call with R1_BASE (origin + /api)
//   R2 routes: FastAPI registers them as  POST /simulate  etc. (no /api prefix)
//              → call with R2_BASE (bare origin)
//
// In dev (vite dev server on :5173) we point at the local backend on :8005.
// In production the Render deployment serves everything from one origin so
// both bases resolve to the same host.

const _DEV  = import.meta.env.DEV;
const _PROD_ORIGIN = "https://spendshield-tj9v.onrender.com";
const _DEV_ORIGIN  = "http://127.0.0.1:8005";

const ORIGIN  = _DEV ? _DEV_ORIGIN : _PROD_ORIGIN;
const R1_BASE = `${ORIGIN}/api`;   // R1: /api/summary, /api/forecast, …
const R2_BASE = ORIGIN;            // R2: /simulate, /twin/benchmark, …

async function getJSON(base, path) {
  const res = await fetch(`${base}${path}`);
  if (!res.ok) {
    throw new Error(`Request to ${path} failed: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

async function postJSON(base, path, body) {
  const res = await fetch(`${base}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`POST ${path} failed: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

// -- Round 1 exports (R1_BASE → /api/…) --
export const getSummary      = ()              => getJSON(R1_BASE, "/summary");
export const getTrends       = ()              => getJSON(R1_BASE, "/trends");
export const getRecurring    = ()              => getJSON(R1_BASE, "/recurring");
export const getForecast     = (days = 30)     => getJSON(R1_BASE, `/forecast?forecast_days=${days}`);
export const getTransactions = (limit = 50)    => getJSON(R1_BASE, `/transactions?limit=${limit}`);

// -- Round 2 exports (R2_BASE → /simulate, /twin/…, …) --
export const fetchSimulatePresets = ()        => getJSON(R2_BASE, "/simulate/presets");
export const runSimulation        = (payload) => postJSON(R2_BASE, "/simulate", payload);
export const fetchTwinBenchmark   = ()        => getJSON(R2_BASE, "/twin/benchmark");
export const runOptimizer         = (payload) => postJSON(R2_BASE, "/optimize", payload);
export const fetchReviewQueue     = ()        => getJSON(R2_BASE, "/categoriser/review-queue");
export const submitCategoryCorrection = (payload) => postJSON(R2_BASE, "/categoriser/correct", payload);
export const submitTransaction    = (payload) => postJSON(R2_BASE, "/transactions", payload);
export const sendAgentChat        = (payload) => postJSON(R2_BASE, "/agent/chat", payload);
export const fetchCalibration     = ()        => getJSON(R2_BASE, "/calibration");

