"use client";

import { use, useEffect, useState } from "react";
import { API, api, CaseView } from "../../../lib/api";

export default function CasePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [view, setView] = useState<CaseView | null>(null);
  const [error, setError] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      setView(await api<CaseView>(`/cases/${id}`));
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load this case.");
    }
  }

  useEffect(() => {
    void load();
    const source = new EventSource(`${API}/cases/${id}/events`);
    source.onmessage = () => void load();
    source.addEventListener("status", () => void load());
    source.onerror = () => source.close();
    return () => source.close();
  }, [id]);

  async function answer(messageId: string, option: boolean) {
    setBusy(true);
    try {
      await api(`/cases/${id}/answers`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message_id: messageId, option }) });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not send the answer.");
    } finally {
      setBusy(false);
    }
  }

  async function upload() {
    if (!file) return;
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", file);
      await api(`/cases/${id}/documents`, { method: "POST", body: form });
      await api(`/cases/${id}/start`, { method: "POST" });
      setFile(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not upload the document.");
    } finally {
      setBusy(false);
    }
  }

  async function deleteCase() {
    if (!window.confirm("Delete uploaded files and extracted facts for this case?")) return;
    setBusy(true);
    try {
      await api(`/cases/${id}`, { method: "DELETE" });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete this case.");
    } finally {
      setBusy(false);
    }
  }

  const question = [...(view?.messages || [])].reverse().find((message) => message.kind === "question");

  return (
    <main className="mx-auto min-h-screen max-w-4xl px-6 py-12">
      <a href="/" className="text-sm text-teal-700">← New case</a>
      <h1 className="mt-5 text-3xl font-bold">Your case</h1>
      {error && <p className="mt-4 rounded-lg bg-red-50 p-3 text-red-700">{error}</p>}
      {!view && !error && <p className="mt-8 text-slate-500">Loading your case…</p>}
      {view && <>
        <div className="mt-5 rounded-xl bg-teal-50 p-5"><p className="text-sm text-teal-800">Current status</p><p className="mt-1 text-2xl font-semibold text-teal-950">{view.status.replaceAll("_", " ")}</p>{view.decision_summary && <p className="mt-2 text-sm text-teal-900">Decision: {view.decision_summary.outcome.replaceAll("_", " ")}</p>}</div>
        {question && view.status === "NEEDS_INFO" && <section className="mt-6 rounded-xl border border-amber-200 bg-amber-50 p-5"><h2 className="font-semibold">A question for you</h2><p className="mt-2">{question.text}</p><div className="mt-4 flex gap-3">{question.options.map((option) => <button key={String(option.value)} disabled={busy} onClick={() => void answer(question.id, option.value)} className="rounded-lg bg-amber-700 px-4 py-2 font-medium text-white disabled:opacity-50">{option.label}</button>)}</div></section>}
        {view.status === "NEEDS_DOCUMENTS" && <section className="mt-6 rounded-xl border p-5"><h2 className="font-semibold">Add a clearer document</h2><p className="mt-2 text-sm text-slate-600">Upload a synthetic replacement image and the case will resume.</p><input className="mt-4" type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => setFile(event.target.files?.[0] || null)} /><button disabled={!file || busy} onClick={() => void upload()} className="ml-3 rounded-lg bg-slate-900 px-4 py-2 text-white disabled:opacity-50">Upload and resume</button></section>}
        <section className="mt-8"><h2 className="font-semibold">Messages</h2>{view.messages.length === 0 ? <p className="mt-3 text-slate-500">No citizen messages yet. Processing may still be starting.</p> : <ol className="mt-3 grid gap-3">{view.messages.map((message) => <li key={message.id} className="rounded-lg border bg-white p-4"><span className="text-xs font-semibold uppercase tracking-wide text-slate-500">{message.kind}</span><p className="mt-2 whitespace-pre-wrap">{message.text}</p></li>)}</ol>}</section>
        <button disabled={busy} onClick={() => void deleteCase()} className="mt-8 rounded-lg border border-red-200 px-4 py-2 text-sm text-red-700 disabled:opacity-50">Delete my data</button>
      </>}
    </main>
  );
}
