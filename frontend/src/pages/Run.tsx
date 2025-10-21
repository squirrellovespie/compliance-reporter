import React, { useEffect, useState } from "react";
import { listSections, runReport, downloadReportPdf, getRagDebug } from "../api";

type Section = { id: string; name: string; position: number; default_prompt?: string };
type RagRow = { doc_id: string; page: number; score: number | null; preview: string; source?: string };

export default function Run() {
  const [framework, setFramework] = useState("seal");
  const [firm, setFirm] = useState("ABC");
  const [sections, setSections] = useState<Section[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const [overarching, setOverarching] = useState<string>("");
  const [runId, setRunId] = useState<string>("");
  const [includeDebug, setIncludeDebug] = useState<boolean>(true);
  const [loading, setLoading] = useState<boolean>(false);
  const [ragDebug, setRagDebug] = useState<Record<string, RagRow[]> | null>(null);

  const [retrieval, setRetrieval] = useState<"cosine" | "mmr" | "hybrid">("cosine");

  useEffect(() => {
    (async () => {
      const data = await listSections(framework);
      setSections(data.sections);
      setSelected(data.sections.map((s: Section) => s.id)); // select all by default
      setOverarching(data.overarching_prompt || "");
      setOverrides(
        Object.fromEntries(data.sections.map((s: Section) => [s.id, s.default_prompt || ""]))
      );
      setRunId("");
      setRagDebug(null);
    })();
  }, [framework]);

  async function onRun() {
    setLoading(true);
    setRunId("");
    setRagDebug(null);
    try {
      const res = await runReport({
        framework,
        firm,
        selected_section_ids: selected,
        prompt_overrides: overrides,
        overarching_prompt: overarching,
        include_rag_debug: includeDebug,
        retrieval_strategy: retrieval, // <-- pass to backend
      });
      setRunId(res.run_id);

      // Prefer inline RAG debug, fall back to fetching the run
      const inline = res?.result?.rag_debug;
      if (inline) {
        setRagDebug(inline);
      } else if (includeDebug) {
        try {
          const dbg = await getRagDebug(res.run_id);
          setRagDebug(dbg);
        } catch {
          // ignore
        }
      }
    } catch (e: any) {
      alert(`Run failed: ${e.message || e}`);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <label>Framework</label>
        <select value={framework} onChange={(e) => setFramework(e.target.value)}>
          <option value="seal">seal</option>
          <option value="osfi_b10">osfi_b10</option>
          <option value="osfi_b13">osfi_b13</option>
          <option value="occ">occ</option>
        </select>

        <label>Firm</label>
        <input value={firm} onChange={(e) => setFirm(e.target.value)} />

        {/* NEW: retrieval strategy */}
        <label>Retrieval</label>
        <select value={retrieval} onChange={(e) => setRetrieval(e.target.value as any)}>
          <option value="cosine">Cosine (nearest neighbors)</option>
          <option value="mmr">MMR (diversified)</option>
          <option value="hybrid">Hybrid (vector+keyword)</option>
        </select>

        <label style={{ marginLeft: 16 }}>
          <input
            type="checkbox"
            checked={includeDebug}
            onChange={(e) => setIncludeDebug(e.target.checked)}
          />
          &nbsp;Include RAG debug
        </label>
      </div>

      <div>
        <label style={{ display: "block", fontWeight: 600 }}>Overarching Prompt</label>
        <textarea
          value={overarching}
          onChange={(e) => setOverarching(e.target.value)}
          rows={6}
          style={{ width: "100%" }}
          placeholder="Global guidance that applies to all sections…"
        />
      </div>

      <div>
        <h3>Sections</h3>
        {sections.map((s) => (
          <div
            key={s.id}
            style={{ border: "1px solid #ddd", borderRadius: 8, padding: 10, marginBottom: 8 }}
          >
            <label>
              <input
                type="checkbox"
                checked={selected.includes(s.id)}
                onChange={(e) => {
                  setSelected((prev) =>
                    e.target.checked ? [...prev, s.id] : prev.filter((x) => x !== s.id)
                  );
                }}
              />
              &nbsp;{s.name} (pos {s.position})
            </label>
            <div>
              <small>Prompt (override)</small>
              <textarea
                rows={3}
                style={{ width: "100%" }}
                value={overrides[s.id] ?? ""}
                onChange={(e) =>
                  setOverrides((prev) => ({ ...prev, [s.id]: e.target.value }))
                }
              />
            </div>
          </div>
        ))}
      </div>

      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <button onClick={onRun} disabled={loading}>
          {loading ? "Generating…" : "Run"}
        </button>
        {runId && <button onClick={() => downloadReportPdf(runId)}>Download PDF</button>}
        {loading && <span style={{ opacity: 0.7 }}>This may take a minute…</span>}
      </div>

      {runId && !loading && (
        <div>
          <div style={{ fontSize: 13, opacity: 0.8, marginTop: 4 }}>Run ID: {runId}</div>
          {ragDebug && (
            <div style={{ marginTop: 16 }}>
              <h3>RAG Debug (per section)</h3>
              {sections
                .filter((s) => selected.includes(s.id))
                .map((s) => {
                  const rows = ragDebug[s.id] || [];
                  return (
                    <div
                      key={s.id}
                      style={{
                        border: "1px solid #eee",
                        borderRadius: 8,
                        padding: 10,
                        marginTop: 10,
                      }}
                    >
                      <div style={{ fontWeight: 600, marginBottom: 6 }}>{s.name}</div>
                      {rows.length === 0 ? (
                        <div style={{ fontStyle: "italic", opacity: 0.8 }}>
                          No chunks captured.
                        </div>
                      ) : (
                        <div style={{ overflowX: "auto" }}>
                          <table style={{ width: "100%", borderCollapse: "collapse" }}>
                            <thead>
                              <tr>
                                <th
                                  style={{
                                    textAlign: "left",
                                    borderBottom: "1px solid #ddd",
                                    padding: "6px 4px",
                                  }}
                                >
                                  Source
                                </th>
                                <th
                                  style={{
                                    textAlign: "left",
                                    borderBottom: "1px solid #ddd",
                                    padding: "6px 4px",
                                  }}
                                >
                                  Doc
                                </th>
                                <th
                                  style={{
                                    textAlign: "left",
                                    borderBottom: "1px solid #ddd",
                                    padding: "6px 4px",
                                  }}
                                >
                                  Page
                                </th>
                                <th
                                  style={{
                                    textAlign: "left",
                                    borderBottom: "1px solid #ddd",
                                    padding: "6px 4px",
                                  }}
                                >
                                  Score
                                </th>
                                <th
                                  style={{
                                    textAlign: "left",
                                    borderBottom: "1px solid #ddd",
                                    padding: "6px 4px",
                                  }}
                                >
                                  Preview
                                </th>
                              </tr>
                            </thead>
                            <tbody>
                              {rows.map((r, i) => (
                                <tr key={i}>
                                  <td style={{ verticalAlign: "top", padding: "6px 4px" }}>
                                    {r.source ?? "fw"}
                                  </td>
                                  <td style={{ verticalAlign: "top", padding: "6px 4px" }}>
                                    {r.doc_id}
                                  </td>
                                  <td style={{ verticalAlign: "top", padding: "6px 4px" }}>
                                    {r.page}
                                  </td>
                                  <td style={{ verticalAlign: "top", padding: "6px 4px" }}>
                                    {r.score == null ? "—" : r.score.toFixed(3)}
                                  </td>
                                  <td
                                    style={{
                                      verticalAlign: "top",
                                      padding: "6px 4px",
                                      whiteSpace: "normal",
                                    }}
                                  >
                                    {r.preview}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </div>
                  );
                })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
