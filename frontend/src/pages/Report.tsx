import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { getReport } from "../api";

export default function Report() {
  const { runId } = useParams<{ runId: string }>();
  const [data, setData] = useState<any>(null);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    (async () => {
      try {
        setMsg("Loading...");
        const res = await getReport(runId!);           // shape: { run_id, result } OR { ... }
        const result = (res as any).result ?? res;     // normalize
        setData(result);
        setMsg("");
      } catch (e: any) {
        setMsg(`Error: ${e.message}`);
      }
    })();
  }, [runId]);

  if (msg) return <div>{msg}</div>;
  if (!data) return null;

  const findings = data.findings ?? [];
  const sections: Record<string, string> = data.sections ?? {};
  const selected: string[] = data.selected_sections ?? [];

  const BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

  return (
    <div style={{ display: "grid", gap: 24, maxWidth: 960 }}>
        <h2>Report: {runId}</h2>
        <div>
            <b>Framework:</b> {data.framework} &nbsp;&nbsp;
            <b>Firm:</b> {data.firm}
        </div>
        <div>
            <a
                href={`${BASE}/reports/${encodeURIComponent(runId!)}/pdf`}
                target="_blank"
                rel="noreferrer"
                style={{ display: "inline-block", padding: "6px 12px", border: "1px solid #ddd", borderRadius: 8, textDecoration: "none" }}
            >
                Download PDF
            </a>
        </div>

      <div style={{ border: "1px solid #eee", padding: 12, borderRadius: 8 }}>
        <b>Selected Sections</b>
        {selected.length === 0 ? (
          <div style={{ opacity: 0.7 }}>No sections selected when running the report.</div>
        ) : (
          <ul>
            {selected.map(s => <li key={s}>{s}</li>)}
          </ul>
        )}
      </div>

      <div style={{ border: "1px solid #eee", padding: 12, borderRadius: 8 }}>
        <b>Findings ({findings.length})</b>
        {findings.length === 0 ? (
          <div style={{ opacity: 0.7 }}>
            No findings. Make sure framework is indexed and assessment/evidence uploaded.
          </div>
        ) : (
          <ul>
            {findings.map((f: any) => (
              <li key={f.id} style={{ marginBottom: 12 }}>
                <div><b>{f.id}</b></div>
                <div><b>Assessment:</b> {f.assessment} · conf {Math.round((f.confidence ?? 0) * 100)}%</div>
                <div><b>Claim:</b> {f.claim}</div>
                <div><b>Rationale:</b> {f.rationale}</div>
                {Array.isArray(f.framework_refs) && f.framework_refs.length > 0 && (
                  <details>
                    <summary>Framework refs</summary>
                    <ul>
                      {f.framework_refs.map((r: any, i: number) =>
                        <li key={i}>[{r.framework}] control {r.control_id}</li>
                      )}
                    </ul>
                  </details>
                )}
                {Array.isArray(f.evidence_links) && f.evidence_links.length > 0 && (
                  <details>
                    <summary>Evidence links</summary>
                    <ul>
                      {f.evidence_links.map((e: any, i: number) =>
                        <li key={i}>
                          {e.doc_id}{e.page ? ` · p${e.page}` : ""} · “{(f.claim || "").slice(0, 80)}”
                        </li>
                      )}
                    </ul>
                  </details>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div style={{ border: "1px solid #eee", padding: 12, borderRadius: 8 }}>
        <b>Narrative Sections</b>
        {selected.map((s: string) => (
          <section key={s} style={{ marginTop: 16 }}>
            <h3>{s}</h3>
            <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.6 }}>
              {sections[s] || "No content generated for this section."}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
