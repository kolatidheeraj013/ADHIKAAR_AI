"use client";

import { useEffect, useState } from "react";
import { api, REVIEWER_TOKEN_STORAGE_KEY, reviewerHeaders } from "../../lib/api";

type QueueItem = { case_id: string; reason: string; status: string; created_at: string };

export default function ReviewerPage() {
  const [token, setToken] = useState("");
  const [queue, setQueue] = useState<QueueItem[] | null>(null);
  const [error, setError] = useState("");

  async function load(value = token) {
    const candidate = value.trim();
    if (!candidate) {
      setError("Enter the reviewer password before loading the queue.");
      setQueue(null);
      return;
    }
    try {
      setError("");
      setQueue(await api<QueueItem[]>("/reviewer/queue", { headers: reviewerHeaders(candidate) }));
      setToken(candidate);
      localStorage.setItem(REVIEWER_TOKEN_STORAGE_KEY, candidate);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load reviewer queue.");
      setQueue(null);
    }
  }

  useEffect(() => {
    const saved = localStorage.getItem(REVIEWER_TOKEN_STORAGE_KEY) || "";
    setToken(saved);
    if (saved) void load(saved);
  }, []);

  function clearToken() {
    localStorage.removeItem(REVIEWER_TOKEN_STORAGE_KEY);
    setToken("");
    setQueue(null);
    setError("");
  }

  return (
    <main className="mx-auto min-h-screen max-w-4xl px-6 py-12">
      <a href="/" className="text-sm text-teal-700">← Citizen intake</a>
      <h1 className="mt-5 text-3xl font-bold">Reviewer queue</h1>
      <p className="mt-2 text-slate-600">Use the local reviewer password to inspect escalated cases. The token is sent only as X-Reviewer-Token.</p>
      <div className="mt-5 flex gap-3"><input type="password" value={token} onChange={(event) => setToken(event.target.value)} placeholder="Demo reviewer password" className="min-w-0 flex-1 rounded-lg border p-3" /><button onClick={() => void load()} className="rounded-lg bg-slate-900 px-4 py-2 text-white">Load queue</button><button type="button" onClick={clearToken} className="rounded-lg border px-4 py-2">Clear token</button></div>
      {error && <p className="mt-4 rounded-lg bg-red-50 p-3 text-red-700">{error}</p>}
      {queue === null && !error && <p className="mt-8 text-slate-500">Enter the reviewer password to load open escalations.</p>}
      {queue?.length === 0 && <p className="mt-8 rounded-xl border p-5 text-slate-500">The queue is empty.</p>}
      {queue && queue.length > 0 && <ul className="mt-8 grid gap-3">{queue.map((item) => <li key={item.case_id} className="rounded-xl border bg-white p-5"><a className="font-semibold text-teal-700" href={`/reviewer/${item.case_id}`}>{item.case_id}</a><p className="mt-2 text-slate-700">{item.reason}</p><p className="mt-2 text-xs text-slate-500">{item.status} · {new Date(item.created_at).toLocaleString()}</p></li>)}</ul>}
    </main>
  );
}
