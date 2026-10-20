export const API = (process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000").replace(/\/$/, "");
export const REVIEWER_TOKEN_STORAGE_KEY = "adhikaar-reviewer-token";

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    ...init,
    headers: { ...(init?.headers || {}) },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.detail || `Request failed (${response.status})`);
  }
  return body as T;
}

export function reviewerHeaders(token: string): HeadersInit {
  return token.trim() ? { "X-Reviewer-Token": token.trim() } : {};
}

export function isIdentifierKey(key: string): boolean {
  return /(aadhaar|account|ifsc|phone|email|identifier|document)/i.test(key);
}

export function maskIdentifier(value: unknown): string {
  const text = String(value ?? "");
  const digits = text.replace(/\D/g, "");
  if (digits.length >= 4) return `•••• ${digits.slice(-4)}`;
  return "[REDACTED]";
}

export function displayFactValue(key: string, value: unknown): string {
  return isIdentifierKey(key) ? maskIdentifier(value) : String(value ?? "—");
}

export function maskSensitiveData(value: unknown, key = ""): unknown {
  if (isIdentifierKey(key)) return maskIdentifier(value);
  if (Array.isArray(value)) return value.map((item) => maskSensitiveData(item));
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([childKey, childValue]) => [childKey, maskSensitiveData(childValue, childKey)]));
  }
  return value;
}

export type CaseMessage = {
  id: string;
  kind: string;
  text: string;
  options: { label: string; value: boolean }[];
  created_at: string;
};

export type CaseView = {
  case_id: string;
  status: string;
  language: string;
  channel: string;
  decision_summary: { scheme_id: string; outcome: string } | null;
  messages: CaseMessage[];
};
