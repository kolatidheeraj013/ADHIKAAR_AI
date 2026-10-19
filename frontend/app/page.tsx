export default function HomePage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col justify-center gap-6 px-6 py-16">
      <p className="text-sm font-semibold uppercase tracking-[0.2em] text-slate-500">ADHIKAAR</p>
      <h1 className="text-4xl font-bold tracking-tight text-slate-950">
        Welfare entitlement, without the paperwork maze.
      </h1>
      <p className="max-w-2xl text-lg leading-8 text-slate-600">
        Phase 0 is alive. The citizen intake, reviewer dashboard, and case flow arrive in
        later phases. For now, the service boundaries are explicit and boring—which is how
        production systems survive demos.
      </p>
      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <p className="font-medium text-slate-900">Demo safety</p>
        <p className="mt-2 text-sm text-slate-600">
          Use synthetic documents only. Never upload real identity documents.
        </p>
      </div>
    </main>
  );
}
