"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { api } from "../lib/api";

export default function HomePage() {
  const [language, setLanguage] = useState("en");
  const [text, setText] = useState("");
  const [voice, setVoice] = useState<File | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [recording, setRecording] = useState(false);
  const [recordingSupported, setRecordingSupported] = useState(false);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  useEffect(() => {
    if (typeof MediaRecorder === "undefined") return;
    setRecordingSupported(
      MediaRecorder.isTypeSupported("audio/ogg;codecs=opus") || MediaRecorder.isTypeSupported("audio/ogg"),
    );
    return () => streamRef.current?.getTracks().forEach((track) => track.stop());
  }, []);

  async function toggleRecording() {
    if (recording) {
      recorderRef.current?.stop();
      return;
    }
    if (!recordingSupported) {
      setError("This browser cannot record the OGG format accepted by the demo. Type your request or choose an OGG file.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = MediaRecorder.isTypeSupported("audio/ogg;codecs=opus") ? "audio/ogg;codecs=opus" : "audio/ogg";
      const recorder = new MediaRecorder(stream, { mimeType });
      chunksRef.current = [];
      streamRef.current = stream;
      recorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: "audio/ogg" });
        setVoice(new File([blob], "recorded-request.ogg", { type: "audio/ogg" }));
        setRecording(false);
        stream.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
        recorderRef.current = null;
      };
      recorder.start();
      setError("");
      setRecording(true);
    } catch {
      setError("Microphone access was not available. Type your request or choose an OGG file instead.");
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    if (!consent) {
      setError("Please agree before recording or selecting documents.");
      return;
    }
    if ((!text.trim() && !voice) || !files.length) {
      setError("Add a typed request or voice note, plus at least one image.");
      return;
    }
    setBusy(true);
    try {
      const created = await api<{ case_id: string }>("/cases", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ language, consent: true, channel: "web" }),
      });
      if (text.trim()) {
        await api(`/cases/${created.case_id}/text`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: text.trim() }),
        });
      }
      if (voice) {
        const form = new FormData();
        form.append("file", voice);
        await api(`/cases/${created.case_id}/voice`, { method: "POST", body: form });
      }
      for (const file of files) {
        const form = new FormData();
        form.append("file", file);
        await api(`/cases/${created.case_id}/documents`, { method: "POST", body: form });
      }
      await api(`/cases/${created.case_id}/start`, { method: "POST" });
      window.location.href = `/case/${created.case_id}`;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start your case.");
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto min-h-screen max-w-4xl px-6 py-12">
      <header className="mb-10">
        <p className="text-sm font-semibold uppercase tracking-[0.25em] text-teal-700">ADHIKAAR · local Phase 8 demo</p>
        <h1 className="mt-3 text-4xl font-bold tracking-tight">A clearer path to welfare support.</h1>
        <p className="mt-3 max-w-2xl text-slate-600">Use synthetic sample documents only. The deterministic rules engine decides eligibility; a reviewer handles uncertainty.</p>
      </header>
      <form onSubmit={submit} className="grid gap-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <label className="order-first flex gap-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-950">
          <input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} />
          <span>I agree to process these synthetic sample documents for this demo. Accept consent before recording or selecting uploads.</span>
        </label>
        <label className="grid gap-2">
          <span className="font-medium">Language</span>
          <select value={language} onChange={(event) => setLanguage(event.target.value)} className="rounded-lg border p-3">
            <option value="en">English</option><option value="ta">தமிழ்</option><option value="te">తెలుగు</option><option value="hi">हिन्दी</option>
          </select>
        </label>
        <label className="grid gap-2">
          <span className="font-medium">What help do you need?</span>
          <textarea value={text} onChange={(event) => setText(event.target.value)} rows={4} placeholder="Example: I am a farmer seeking PM-Kisan help" className="rounded-lg border p-3" />
        </label>
        <label className="grid gap-2">
          <span className="font-medium">Optional voice note</span>
          <div className="flex flex-wrap items-center gap-3">
            <button type="button" disabled={!consent || busy || recordingSupported === false} onClick={() => void toggleRecording()} className="rounded-lg border px-4 py-2 disabled:cursor-not-allowed disabled:opacity-50">{recording ? "Stop recording" : "Record voice"}</button>
            <span className="text-sm text-slate-600">{recording ? "Recording locally…" : voice ? `Ready: ${voice.name}` : "No voice note selected"}</span>
          </div>
          <input disabled={!consent || recording} type="file" accept="audio/ogg,audio/wav,audio/mpeg" onChange={(event) => setVoice(event.target.files?.[0] || null)} />
          <span className="text-xs text-slate-500">Use a short OGG, WAV, or MP3 sample when text is not available. Recording uses OGG when supported.</span>
        </label>
        <label className="grid gap-2">
          <span className="font-medium">Sample document images</span>
          <input disabled={!consent} type="file" accept="image/jpeg,image/png,image/webp" multiple onChange={(event) => setFiles(Array.from(event.target.files || []))} />
        </label>
        {error && <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}
        <button disabled={busy || recording} className="rounded-lg bg-teal-700 px-5 py-3 font-semibold text-white disabled:opacity-50">{busy ? "Starting…" : "Start my case"}</button>
      </form>
      <nav className="mt-8 flex gap-4 text-sm text-teal-700"><a href="/reviewer">Reviewer queue</a></nav>
    </main>
  );
}
