"use client";

import { use, useEffect, useState } from "react";
import { api, maskSensitiveData, REVIEWER_TOKEN_STORAGE_KEY, reviewerHeaders } from "../../../lib/api";

type Event = { id: string; ts: string; actor: string; event_type: string; summary: string; evidence: unknown; confidence: number | null; rationale: string };

export default function AuditPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [events, setEvents] = useState<Event[] | null>(null);
  const [error, setError] = useState("");
  const [token, setToken] = useState("");

  async function load(value: string) {
    if (!value.trim()) {
      setError("Enter the reviewer password to view the audit.");
      return;
    }
    try {
      setEvents(await api<Event[]>(`/reviewer/${id}/audit`, { headers: reviewerHeaders(value) }));
      setToken(value.trim());
      localStorage.setItem(REVIEWER_TOKEN_STORAGE_KEY, value.trim());
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load audit.");
    }
  }

  useEffect(() => {
    const saved = localStorage.getItem(REVIEWER_TOKEN_STORAGE_KEY) || "";
    setToken(saved);
    if (saved) void load(saved);
  }, [id]);

  function clearToken() {
    localStorage.removeItem(REVIEWER_TOKEN_STORAGE_KEY);
    setToken("");
    setEvents(null);
  }

  return (
    <main className="mx-auto min-h-screen max-w-4xl px-6 py-12">
      <a href={`/reviewer/${id}`} className="text-sm text-teal-700">← Case review</a>
      <h1 className="mt-5 text-3xl font-bold">Audit timeline</h1>
      <p className="mt-2 text-slate-600">Reviewer-only, append-only event summaries. Evidence is redacted by the backend before display.</p>
      <div className="mt-5 flex gap-3"><input type="password" value={token} onChange={(event) => setToken(event.target.value)} placeholder="Reviewer password" className="min-w-0 flex-1 rounded-lg border p-3" /><button onClick={() => void load(token)} className="rounded-lg bg-slate-900 px-4 py-2 text-white">Load audit</button><button onClick={clearToken} className="rounded-lg border px-4 py-2">Clear token</button></div>
      {error && <p className="mt-4 rounded-lg bg-red-50 p-3 text-red-700">{error}</p>}
      {!events && !error && <p className="mt-8 text-slate-500">Enter a reviewer token to load the audit.</p>}
      {events?.length === 0 && <p className="mt-8 rounded-xl border p-5 text-slate-500">No audit events.</p>}
      {events && events.length > 0 && <ol className="mt-8 grid gap-3">{events.map((event) => <li key={event.id} className="rounded-xl border bg-white p-5"><p className="text-xs uppercase tracking-wide text-slate-500">{event.actor} · {event.event_type}</p><p className="mt-2">{event.summary}</p>{event.rationale && <p className="mt-2 text-sm text-slate-600"><span className="font-medium">Why:</span> {event.rationale}</p>}<p className="mt-2 text-xs text-slate-500">{new Date(event.ts).toLocaleString()} {event.confidence == null ? "" : `· confidence ${event.confidence}`}</p><details className="mt-3"><summary className="cursor-pointer text-sm text-teal-700">Evidence / outcome</summary><pre className="mt-2 overflow-x-auto whitespace-pre-wrap rounded bg-slate-50 p-3 text-xs">{JSON.stringify(maskSensitiveData(event.evidence), null, 2)}</pre></details></li>)}</ol>}
    </main>
  );
}
