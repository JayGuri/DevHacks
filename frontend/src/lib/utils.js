import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs) {
  return twMerge(clsx(inputs));
}

export function formatPercent(n) {
  return `${n.toFixed(1)}%`;
}

export function formatEpsilon(n) {
  return `ε = ${n.toFixed(2)}`;
}

/** Zero-pad round number: 42 → "R042" */
export function formatRound(n) {
  return `R${String(n).padStart(3, "0")}`;
}

/** Map trust score to a text color class for traffic-light severity */
export function getTrustColor(trust) {
  if (trust >= 0.7) return "text-emerald-500";
  if (trust >= 0.4) return "text-amber-500";
  return "text-rose-500";
}

/** Map trust score to a background color class for traffic-light severity */
export function getTrustBg(trust) {
  if (trust >= 0.7) return "bg-emerald-500";
  if (trust >= 0.4) return "bg-amber-500";
  return "bg-rose-500";
}

export function randomBetween(a, b) {
  return a + Math.random() * (b - a);
}

export function clampVal(v, min, max) {
  return Math.min(Math.max(v, min), max);
}

/** Extract initials from a full name: "Alex Morgan" → "AM" */
export function getInitials(name) {
  if (!name) return "";
  return name
    .split(" ")
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

const INVITE_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";

/** Generate a random 6-character uppercase alphanumeric invite code */
export function generateInviteCode() {
  return Array.from({ length: 6 }, () =>
    INVITE_CHARS[Math.floor(Math.random() * INVITE_CHARS.length)]
  ).join("");
}

/** Validate an invite code against a list of projects. Returns the matching project or null. */
export function validateInviteCode(code, projects) {
  if (!code || code.length !== 6) return null;
  const upper = code.toUpperCase();
  return projects.find((p) => p.inviteCode === upper) || null;
}

