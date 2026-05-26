import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

export const api = axios.create({
  baseURL: API,
  timeout: 15000,
});

export const getStats = () => api.get("/stats").then((r) => r.data);
export const getFeed = (params = {}) =>
  api.get("/claims/feed", { params }).then((r) => r.data);
export const getLeaderboard = (limit = 10) =>
  api.get("/leaderboard", { params: { limit } }).then((r) => r.data);
export const getTokens = (limit = 50) =>
  api.get("/tokens", { params: { limit } }).then((r) => r.data);
export const getTokenDetail = (address) =>
  api.get(`/tokens/${address}`).then((r) => r.data);
export const trackToken = (payload) =>
  api.post("/tokens/track", payload).then((r) => r.data);
export const search = (q) =>
  api.get("/search", { params: { q } }).then((r) => r.data);
export const getClaimerDetail = (handle) =>
  api.get(`/handle/${handle}`).then((r) => r.data);

export const formatEth = (v) =>
  v == null ? "0" : Number(v).toFixed(Number(v) >= 1 ? 3 : 4);
export const formatUsd = (v) =>
  v == null ? "$0" : `$${Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
export const shortAddress = (a) =>
  !a ? "" : `${a.slice(0, 6)}…${a.slice(-4)}`;
export const timeAgo = (iso) => {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  const diff = Math.max(0, Date.now() - t) / 1000;
  if (diff < 60) return `${Math.floor(diff)}s`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
  return `${Math.floor(diff / 86400)}d`;
};
