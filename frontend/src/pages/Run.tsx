// frontend/src/pages/Run.tsx
import React, { useEffect, useRef, useState } from "react";
import {
  listSections,
  runReportStream,
  downloadReportPdf,
  getRagDebug,
} from "../api";

type Section = { id: string; name: string; position: number; default_prompt?: string };
type RagRow = { doc_id: string; page: number; score: number | null; preview: string; source?: string };

// How fast to "type" characters (ms per char)
const TYPE_SPEED_MS = 8; // try 4–12 for best feel

export default function Run() {
  const [framework, setFramework] = useState("seal");
  const [firm, setFirm] = useState("ABC");
  const [sections, setSections] = useState<Section[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const [overarching, setOverarching] = useState<string>("");

  const [retrieval, setRetrieval] = useState<"cosine" | "mmr" | "hybrid">("cosine");
  const [provider, setProvider] = useState<"openai" | "xai">("xai");
  const [model, setModel] = useState<string>("grok-4-latest");

  const [includeDebug, setIncludeDebug] = useState<boolean>(true);
  const [loading, setLoading] = useState<boolean>(false);
  const [runId, setRunId] = useState<string>("");
  const [ragDebug, setRagDebug] = useState<Record<string, RagRow[]> | null>(null);

  // Live report text (what the user currently sees)
  const [liveReport, setLiveReport] = useState<Record<string, string>>({});
  // Full text buffers (what we received from the server)
  const fullBuffers = useRef<Record<string, string>>({});
  // Active typing intervals per section
  const typingTimers = useRef<Record<string, number | null>>({});

  useEffect(() => {
    (async () => {
      const data = await listSections(framework);
      setSections(data.sections);
      setSelected(data.sections.map((s: Section) => s.id));
      setOverarching(data.overarching_prompt || "");
      setOverrides(Object.fromEntries(data.sections.map((s: Section) => [s.id, s.default_prompt || ""])));
      setRunId("");
      setRagDebug(null);
      setLiveReport({});
      fullBuffers.current = {};
      // Clear any leftover timers
      for (const k of Object.keys(typingTimers.current)) {
        if (typingTimers.current[k]) {
          clearInterval(typingTimers.current[k]!);
          typingTimers.current[k] = null;
        }
      }
    })();
    // Cleanup on unmount
    return () => {
      for (const k of Object.keys(typingTimers.current)) {
        if (typingTimers.current[k]) {
          clearInterval(typingTimers.current[k]!);
          typingTimers.current[k] = null;
        }
      }
    };
  }, [framework]);

  // Start a "typewriter" effect for a given section from current live text to full buffer
  function startTyping(sectionName: string) {
    // stop any existing timer for this section
    if (typingTimers.current[sectionName]) {
      clearInterval(typingTimers.current[sectionName]!);
      typingTimers.current[sectionName] = null;
    }

    const target = fullBuffers.current[sectionName] || "";
    let shown = liveReport[sectionName] || "";

    // Fast-exit if already fully printed
    if (shown === target) return;

    typingTimers.current[sectionName] = window.setInterval(() => {
      // On each tick, append a few characters to keep it smooth
      // You can tune chunkSize to control smoothness vs performance.
      const chunkSize = 3;
      const next = target.slice(0, shown.length + chunkSize);
      shown = next;

      setLiveReport((prev) => ({ ...prev, [sectionName]: shown }));

      if (shown.length >= target.length) {
        if (typingTimers.current[sectionName]) {
          clearInterval(typingTimers.current[sectionName]!);
          typingTimers.current[sectionName] = null;
        }
      }
    }, TYPE_SPEED_MS);
  }

  async function onRunStream() {
    setLoading(true);
    setRunId("");
    setRagDebug(null);
    setLiveReport({});
    fullBuffers.current = {};

    // Clear all timers
    for (const k of Object.keys(typingTimers.current)) {
      if (typingTimers.current[k]) {
        clearInterval(typingTimers.current[k]!);
        typingTimers.current[k] = null;
      }
    }

    try {
      const opts = {
        framework,
        firm,
        selected_section_ids: selected,
        prompt_overrides: overrides,
        overarching_prompt: overarching,
        include_rag_debug: includeDebug,
        retrieval_strategy: retrieval,
        provider,
        model,
      };

      for await (const ev of runReportStream(opts)) {
        if (ev.event === "start") {
          setRunId(ev.run_id);
        } else if (ev.event === "section_start") {
          // show a placeholder so users see progress even before text arrives
          setLiveReport((prev) => ({ ...prev, [ev.section_name]: "…" }));
        } else if (ev.event === "section_text") {
          // store full text buffer
          fullBuffers.current[ev.section_name] = ev.text || "";
          // ensure we have some starting point (e.g., "…")
          setLiveReport((prev) => ({
            ...prev,
            [ev.section_name]: prev[ev.section_name] ?? "",
          }));
          // kick off the typer
          startTyping(ev.section_name);
        } else if (ev.event === "end") {
          // ensure all remaining sections are fully typed (optional)
          // If you prefer to keep the typeout, comment this block.
          // for (const name of Object.keys(fullBuffers.current)) {
          //   setLiveReport((prev) => ({ ...prev, [name]: fullBuffers.current[name] }));
          //   if (typingTimers.current[name]) {
          //     clearInterval(typingTimers.current[name]!);
          //     typingTimers.current[name] = null;
          //   }
          // }
          if (includeDebug) {
            try {
              const dbg = await getRagDebug(ev.run_id);
              setRagDebug(dbg);
            } catch {}
          }
          setLoading(false);
        } else if (ev.event === "error") {
          alert(`Error: ${ev.message}`);
          setLoading(false);
        }
      }
    } catch (e: any) {
      alert(`Run failed: ${e.message || e}`);
      setLoading(false);
    }
  }

  return (
    <div style={{ display: "grid", gap: 16 }}>
      {/* Controls */}
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

        <label>Provider</label>
        <select
          value={provider}
          onChange={(e) => {
            const p = e.target.value as "openai" | "xai";
            setProvider(p);
            if (p === "xai") setModel("grok-4-latest");
            if (p === "openai") setModel("gpt-4o-mini");
          }}
        >
          <option value="xai">xAI (Grok)</option>
          <option value="openai">OpenAI</option>
        </select>

        <label>Model</label>
        <input
          value={model}
          onChange={(e) => setModel(e.target.value)}
          placeholder={provider === "xai" ? "grok-4-latest" : "gpt-4o-mini"}
          style={{ width: 180 }}
        />

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

      {/* Overarching prompt */}
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

      {/* Sections */}
      <div>
        <h3>Sections</h3>
        {sections.map((s) => (
          <div key={s.id} style={{ border: "1px solid #ddd", borderRadius: 8, padding: 10, marginBottom: 8 }}>
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
                onChange={(e) => setOverrides((prev) => ({ ...prev, [s.id]: e.target.value }))}
              />
            </div>
          </div>
        ))}
      </div>

      {/* Run + Download */}
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <button onClick={onRunStream} disabled={loading}>
          {loading ? "Generating (live)..." : "Run (stream)"}
        </button>
        {runId && !loading && (
          <button onClick={() => downloadReportPdf(runId)}>Download PDF</button>
        )}
        {loading && <span style={{ opacity: 0.7 }}>Streaming sections…</span>}
      </div>

      {/* Live streaming output */}
      {Object.keys(liveReport).length > 0 && (
        <div style={{ marginTop: 20 }}>
          <h3>Live Report Output</h3>
          {sections
            .filter((s) => selected.includes(s.id))
            .map((s) => (
              <div
                key={s.id}
                style={{
                  border: "1px solid #ccc",
                  borderRadius: 8,
                  padding: 10,
                  marginBottom: 12,
                  background: "#fafafa",
                }}
              >
                <h4 style={{ marginBottom: 6 }}>{s.name}</h4>
                <pre
                  style={{
                    whiteSpace: "pre-wrap",
                    fontFamily: "inherit",
                    fontSize: 13,
                    color: "#333",
                    margin: 0,
                  }}
                >
                  {liveReport[s.name] || "(waiting…)"}
                </pre>
              </div>
            ))}
        </div>
      )}

      {/* RAG Debug after completion */}
      {runId && !loading && ragDebug && (
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
                    <div style={{ fontStyle: "italic", opacity: 0.8 }}>No chunks captured.</div>
                  ) : (
                    <div style={{ overflowX: "auto" }}>
                      <table style={{ width: "100%", borderCollapse: "collapse" }}>
                        <thead>
                          <tr>
                            <th style={{ textAlign: "left", borderBottom: "1px solid #ddd", padding: "6px 4px" }}>
                              Source
                            </th>
                            <th style={{ textAlign: "left", borderBottom: "1px solid #ddd", padding: "6px 4px" }}>
                              Doc
                            </th>
                            <th style={{ textAlign: "left", borderBottom: "1px solid #ddd", padding: "6px 4px" }}>
                              Page
                            </th>
                            <th style={{ textAlign: "left", borderBottom: "1px solid #ddd", padding: "6px 4px" }}>
                              Score
                            </th>
                            <th style={{ textAlign: "left", borderBottom: "1px solid #ddd", padding: "6px 4px" }}>
                              Preview
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          {rows.map((r, i) => (
                            <tr key={i}>
                              <td style={{ verticalAlign: "top", padding: "6px 4px" }}>{r.source ?? "fw"}</td>
                              <td style={{ verticalAlign: "top", padding: "6px 4px" }}>{r.doc_id}</td>
                              <td style={{ verticalAlign: "top", padding: "6px 4px" }}>{r.page}</td>
                              <td style={{ verticalAlign: "top", padding: "6px 4px" }}>
                                {r.score == null ? "—" : r.score.toFixed(3)}
                              </td>
                              <td style={{ verticalAlign: "top", padding: "6px 4px", whiteSpace: "normal" }}>
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
  );
}
