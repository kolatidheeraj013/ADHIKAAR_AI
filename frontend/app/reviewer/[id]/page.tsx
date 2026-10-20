"use client";

import { use, useEffect, useState } from "react";
import { api, displayFactValue, isIdentifierKey, maskSensitiveData, REVIEWER_TOKEN_STORAGE_KEY, reviewerHeaders } from "../../../lib/api";

type Detail = {
  case_id: string;
  status: string;
  documents: { id: string; doc_type: string | null; quality: string | null; ocr_confidence: number | null; has_file: boolean }[];
  facts: { key: string; value: unknown; source_type: string; grounded: boolean | null; confidence: number | null }[];
  decisions: { scheme_id: string; outcome: string; rule_trace: { rule_id: string; status: string; reason: string }[] }[];
  escalation: { reason: string; evidence: unknown } | null;
};

export default function ReviewerCasePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [token, setToken] = useState("");
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [editedFacts, setEditedFacts] = useState<Record<string, string>>({});

  async function load(value: string) {
    if (!value.trim()) {
      setError("Enter the reviewer password to view case evidence.");
      return;
    }
    try {
      setDetail(await api<Detail>(`/reviewer/${id}`, { headers: reviewerHeaders(value) }));
      setToken(value.trim());
      localStorage.setItem(REVIEWER_TOKEN_STORAGE_KEY, value.trim());
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load case evidence.");
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
    setDetail(null);
    setError("");
  }

  async function act(action: "approve" | "reject" | "request_docs") {
    setBusy(true);
    try {
      await api(`/reviewer/${id}/resume`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...reviewerHeaders(token) },
        body: JSON.stringify({ action, edited_facts: editedFacts, note }),
      });
      await load(token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not resume case.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto min-h-screen max-w-5xl px-6 py-12">
      <a href="/reviewer" className="text-sm text-teal-700">← Queue</a>
      <h1 className="mt-5 text-3xl font-bold">Review case</h1>
      <div className="mt-4 flex flex-wrap items-center gap-3 text-sm"><span className="text-slate-500">Reviewer token {token ? "stored for this browser" : "required"}</span><input type="password" value={token} onChange={(event) => setToken(event.target.value)} placeholder="Reviewer password" className="rounded border p-2" /><button type="button" onClick={() => void load(token)} className="rounded bg-slate-900 px-3 py-2 text-white">Load evidence</button><button type="button" onClick={clearToken} className="rounded border px-3 py-1">Clear token</button></div>
      {error && <p className="mt-4 rounded-lg bg-red-50 p-3 text-red-700">{error}</p>}
      {!detail && !error && <p className="mt-8 text-slate-500">Enter the reviewer token to view this case.</p>}
      {detail && <>
        <div className="mt-5 rounded-xl bg-slate-100 p-5"><p className="text-sm text-slate-500">Status</p><p className="text-2xl font-semibold">{detail.status.replaceAll("_", " ")}</p>{detail.escalation && <p className="mt-2 text-slate-700">{detail.escalation.reason}</p>}</div>
        <section className="mt-6"><h2 className="font-semibold">Documents</h2><div className="mt-3 grid gap-3 sm:grid-cols-3">{detail.documents.map((doc) => <div key={doc.id} className="rounded-lg border p-4"><div className="flex h-24 items-center justify-center rounded bg-slate-100 text-xs text-slate-500">{doc.has_file ? "Private sample document" : "File deleted"}</div><p className="mt-3 font-medium">{doc.doc_type || "Unclassified"}</p><p className="text-sm text-slate-500">Quality: {doc.quality || "unknown"}</p><p className="text-sm text-slate-500">OCR confidence: {doc.ocr_confidence ?? "—"}</p></div>)}</div></section>
        <section className="mt-6"><h2 className="font-semibold">Extracted facts</h2><p className="mt-1 text-sm text-slate-500">Identifiers are masked by default. Edit only the facts needed to resolve this case.</p><div className="mt-3 overflow-x-auto rounded-lg border"><table className="min-w-full text-left text-sm"><thead className="bg-slate-50"><tr><th className="p-3">Fact</th><th className="p-3">Value</th><th className="p-3">Source</th><th className="p-3">Grounded</th><th className="p-3">Edit</th></tr></thead><tbody>{detail.facts.map((fact) => <tr key={fact.key} className="border-t"><td className="p-3">{fact.key}</td><td className="p-3">{displayFactValue(fact.key, fact.value)}</td><td className="p-3">{fact.source_type}</td><td className="p-3">{fact.grounded == null ? "—" : fact.grounded ? "Yes" : "No"}</td><td className="p-3"><input aria-label={`Edit ${fact.key}`} value={editedFacts[fact.key] ?? ""} placeholder={isIdentifierKey(fact.key) ? "Enter replacement (masked in view)" : displayFactValue(fact.key, fact.value)} onChange={(event) => setEditedFacts((current) => ({ ...current, [fact.key]: event.target.value }))} className="w-48 rounded border p-2" /></td></tr>)}</tbody></table></div></section>
        <section className="mt-6"><h2 className="font-semibold">Rule trace</h2>{detail.decisions.map((decision) => <div key={decision.scheme_id} className="mt-3 rounded-lg border p-4"><p className="font-medium">{decision.scheme_id} · {decision.outcome}</p><ul className="mt-3 grid gap-2 text-sm">{decision.rule_trace.map((rule) => <li key={rule.rule_id}><span className="font-medium">{rule.rule_id}</span>: {rule.status} — {rule.reason}</li>)}</ul></div>)}</section>
        {detail.escalation && <section className="mt-6 rounded-lg border border-amber-200 bg-amber-50 p-4"><h2 className="font-semibold">Agent recovery attempted</h2><p className="mt-2">{detail.escalation.reason}</p><pre className="mt-3 overflow-x-auto whitespace-pre-wrap text-xs text-slate-700">{JSON.stringify(maskSensitiveData(detail.escalation.evidence), null, 2)}</pre></section>}
        <section className="mt-6 rounded-xl border p-5"><h2 className="font-semibold">Reviewer action</h2><textarea value={note} onChange={(event) => setNote(event.target.value)} rows={3} placeholder="Optional note" className="mt-3 w-full rounded-lg border p-3" /><div className="mt-4 flex flex-wrap gap-3"><button disabled={busy || !token} onClick={() => void act("approve")} className="rounded-lg bg-teal-700 px-4 py-2 text-white disabled:opacity-50">Approve</button><button disabled={busy || !token} onClick={() => void act("reject")} className="rounded-lg bg-red-700 px-4 py-2 text-white disabled:opacity-50">Reject</button><button disabled={busy || !token} onClick={() => void act("request_docs")} className="rounded-lg border px-4 py-2 disabled:opacity-50">Request documents</button><a href={`/audit/${id}`} className="rounded-lg border px-4 py-2 text-teal-700">View audit</a></div></section>
      </>}
    </main>
  );
}
