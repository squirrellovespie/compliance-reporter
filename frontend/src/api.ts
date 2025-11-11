// frontend/src/api.ts
const BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

// --------- Sections admin ---------
export async function listSections(framework: string) {
  const res = await fetch(`${BASE}/sections/${framework}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<{
    framework: string;
    overarching_prompt: string;
    sections: Array<{ id: string; name: string; position: number; default_prompt: string }>;
  }>;
}

// --------- Ingest ---------
export async function uploadAssessment(firm: string, file: File) {
  const form = new FormData();
  form.append("firm", firm);
  form.append("file", file);
  const res = await fetch(`${BASE}/ingest/assessment`, { method: "POST", body: form });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function uploadEvidence(firm: string, file: File) {
  const form = new FormData();
  form.append("firm", firm);
  form.append("file", file);
  const res = await fetch(`${BASE}/ingest/evidence`, { method: "POST", body: form });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function uploadEvidenceBatch(firm: string, files: File[]) {
  const fd = new FormData();
  fd.append("firm", firm);
  for (const f of files) fd.append("files", f);
  const res = await fetch(`${BASE}/ingest/evidence-batch`, { method: "POST", body: fd });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// --------- Reports ---------
export async function runReport(opts: {
  framework: string;
  firm: string;
  scope?: string;
  selected_section_ids: string[];
  prompt_overrides: Record<string, string>;
  overarching_prompt?: string;
  include_rag_debug?: boolean;
  retrieval_strategy?: "cosine" | "mmr" | "hybrid";
  provider?: "openai" | "xai"; // NEW
  model?: string;              // NEW
}) {
  const res = await fetch(`${BASE}/reports/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(opts),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getRagDebug(runId: string) {
  const res = await fetch(`${BASE}/reports/${runId}/rag_debug`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getReport(runId: string) {
  const res = await fetch(`${BASE}/reports/${runId}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function indexFramework(framework: string) {
  const res = await fetch(`${BASE}/index/framework/${framework}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) throw new Error(`Failed to index framework ${framework}`);
  return await res.json();
}

export function downloadReportPdf(runId: string) {
  const a = document.createElement("a");
  a.href = `${BASE}/reports/${runId}/pdf`;
  a.download = `${runId}.pdf`;
  document.body.appendChild(a);
  a.click();
  a.remove();
}

// --------- Streaming Report (NDJSON) ---------
export type RunStreamEvent =
  | { event: "start"; run_id: string; framework: string; firm: string }
  | { event: "section_start"; section_id: string; section_name: string }
  | { event: "section_text"; section_id: string; section_name: string; text: string }
  | { event: "end"; run_id: string; ok: boolean }
  | { event: "error"; message: string }
  | Record<string, any>;

/**
 * Stream live report generation from /reports/run_stream.
 * Returns an async iterator that yields events as they arrive.
 */
export async function* runReportStream(opts: {
  framework: string;
  firm: string;
  scope?: string;
  selected_section_ids: string[];
  prompt_overrides: Record<string, string>;
  overarching_prompt?: string;
  include_rag_debug?: boolean;
  retrieval_strategy?: "cosine" | "mmr" | "hybrid";
  provider?: "openai" | "xai";
  model?: string;
}): AsyncGenerator<RunStreamEvent> {
  const res = await fetch(`${BASE}/reports/run_stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(opts),
  });
  if (!res.ok || !res.body) {
    throw new Error(await res.text());
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, idx).trim();
      buffer = buffer.slice(idx + 1);
      if (!line) continue;
      try {
        yield JSON.parse(line) as RunStreamEvent;
      } catch {
        // ignore malformed lines
      }
    }
  }
}
