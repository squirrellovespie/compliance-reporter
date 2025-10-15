// frontend/src/pages/Run.tsx
import React, { useEffect, useState } from "react";
import { listSections, runReport, downloadReportPdf } from "../api";

export default function Run() {
  const [framework, setFramework] = useState("seal");
  const [firm, setFirm] = useState("ABC");
  const [sections, setSections] = useState<Array<{id:string; name:string; position:number; default_prompt:string}>>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [overrides, setOverrides] = useState<Record<string,string>>({});
  const [overarching, setOverarching] = useState<string>("");
  const [runId, setRunId] = useState<string>("");

  const [isRunning, setIsRunning] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string>("");

  useEffect(() => {
    (async () => {
      setStatusMsg("Loading sections…");
      const data = await listSections(framework);
      setSections(data.sections);
      setSelected(data.sections.map(s => s.id));
      setOverarching(data.overarching_prompt || "");
      setOverrides(Object.fromEntries(
        data.sections.map(s => [s.id, s.default_prompt || ""])
      ));
      setStatusMsg("");
    })();
  }, [framework]);

  async function onRun() {
    setIsRunning(true);
    setStatusMsg("Generating report… This can take a minute.");
    try {
      const res = await runReport({
        framework,
        firm,
        selected_section_ids: selected,
        prompt_overrides: overrides,
        overarching_prompt: overarching,
      });
      setRunId(res.run_id);
      setStatusMsg("Report generated. You can download the PDF now.");
    } catch (e: any) {
      setStatusMsg(`Error: ${e.message ?? e}`);
    } finally {
      setIsRunning(false);
    }
  }

  return (
    <div style={{display:"grid", gap:16}}>
      <div style={{display:"flex", gap:12, alignItems:"center"}}>
        <label>Framework</label>
        <select value={framework} onChange={e => setFramework(e.target.value)} disabled={isRunning}>
          <option value="seal">seal</option>
          <option value="osfi_b10">osfi_b10</option>
          <option value="osfi_b13">osfi_b13</option>
          <option value="occ">occ</option>
        </select>
        <label>Firm</label>
        <input value={firm} onChange={e => setFirm(e.target.value)} disabled={isRunning}/>
      </div>

      <div>
        <label style={{display:"block", fontWeight:600}}>Overarching Prompt</label>
        <textarea
          value={overarching}
          onChange={e => setOverarching(e.target.value)}
          rows={6}
          style={{width:"100%"}}
          placeholder="Global guidance for this run…"
          disabled={isRunning}
        />
      </div>

      <div>
        <h3>Sections</h3>
        {sections.map(s => (
          <div key={s.id} style={{border:"1px solid #ddd", borderRadius:8, padding:10, marginBottom:8, opacity: isRunning ? 0.6 : 1}}>
            <label>
              <input
                type="checkbox"
                checked={selected.includes(s.id)}
                onChange={e => {
                  if (isRunning) return;
                  setSelected(prev => e.target.checked ? [...prev, s.id] : prev.filter(x => x !== s.id));
                }}
                disabled={isRunning}
              />
              &nbsp;{s.name} (pos {s.position})
            </label>
            <div>
              <small>Prompt (override)</small>
              <textarea
                rows={3}
                style={{width:"100%"}}
                value={overrides[s.id] ?? ""}
                onChange={e => setOverrides(prev => ({...prev, [s.id]: e.target.value}))}
                disabled={isRunning}
              />
            </div>
          </div>
        ))}
      </div>

      <div style={{display:"flex", gap:8, alignItems:"center"}}>
        <button onClick={onRun} disabled={isRunning || selected.length === 0}>
          {isRunning ? "Generating…" : "Run"}
        </button>
        {runId && <button onClick={() => downloadReportPdf(runId)}>Download PDF</button>}
        <span style={{fontSize:12, opacity:0.8}}>
          {isRunning && <span className="spinner" style={{
            display:"inline-block", width:12, height:12, marginRight:6,
            border:"2px solid #ccc", borderTopColor:"#333", borderRadius:"50%",
            animation:"spin 1s linear infinite"
          }}/>}
          {statusMsg}
        </span>
      </div>

      <style>
        {`@keyframes spin { from {transform: rotate(0deg);} to {transform: rotate(360deg);} }`}
      </style>

      {runId && <div>Run ID: {runId}</div>}
    </div>
  );
}
