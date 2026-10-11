"use client";
// Lato browser: la password dell'area Comune resta in sessionStorage solo per la sessione corrente.
export const getAdminPw = () => { try { return sessionStorage.getItem("adm") ?? ""; } catch { return ""; } };
export const setAdminPw = (p: string | null) => { try { if (p) sessionStorage.setItem("adm", p); else sessionStorage.removeItem("adm"); } catch {} };

export function adminFetch(url: string, init: RequestInit = {}) {
  return fetch(url, { ...init, headers: { ...(init.headers ?? {}), "x-admin-password": getAdminPw() } });
}
