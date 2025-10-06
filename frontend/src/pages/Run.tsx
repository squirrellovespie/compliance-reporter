import React from "react";
import { useEffect, useState } from "react";
import { listSections, runReport, downloadReportPdf } from "../api";

export default function Run() {
  const [framework, setFramework] = useState("seal");
  const [firm, setFirm] = useState("ABC");
  const [sections, setSections] = useState<Array<{id:string; name:string; position:number; default_prompt:string}>>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [overrides, setOverrides] = useState<Record<string,string>>({});
  const [overarching, setOverarching] = useState<string>("");
  const [runId, setRunId] = useState<string>("");

  useEffect(() => {
    (async () => {
      const data = await listSections(framework);
      setSections(data.sections);
      setSelected(data.sections.map(s => s.id)); // select all by default
      setOverarching(data.overarching_prompt || ""); // <-- default from file
      setOverrides(Object.fromEntries(
        data.sections.map(s => [s.id, s.default_prompt || ""])
      ));
    })();
  }, [framework]);

  async function onRun() {
    const res = await runReport({
      framework,
      firm,
      selected_section_ids: selected,
      prompt_overrides: overrides,
      overarching_prompt: overarching, // UI override wins
    });
    setRunId(res.run_id);
  }

  return (
    <div style={{display:"grid", gap:16}}>
      <div style={{display:"flex", gap:12, alignItems:"center"}}>
        <label>Framework</label>
        <select value={framework} onChange={e => setFramework(e.target.value)}>
          <option value="seal">seal</option>
          <option value="osfi_b10">osfi_b10</option>
          <option value="osfi_b13">osfi_b13</option>
          <option value="occ">occ</option>
        </select>
        <label>Firm</label>
        <input value={firm} onChange={e => setFirm(e.target.value)} />
      </div>

      <div>
        <label style={{display:"block", fontWeight:600}}>Overarching Prompt</label>
        <textarea
          value={overarching}
          onChange={e => setOverarching(e.target.value)}
          rows={6}
          style={{width:"100%"}}
          placeholder="Global guidance that applies to all sections…"
        />
      </div>

      <div>
        <h3>Sections</h3>
        {sections.map(s => (
          <div key={s.id} style={{border:"1px solid #ddd", borderRadius:8, padding:10, marginBottom:8}}>
            <label>
              <input
                type="checkbox"
                checked={selected.includes(s.id)}
                onChange={e => {
                  setSelected(prev => e.target.checked ? [...prev, s.id] : prev.filter(x => x !== s.id));
                }}
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
              />
            </div>
          </div>
        ))}
      </div>

      <div style={{display:"flex", gap:8}}>
        <button onClick={onRun}>Run</button>
        {runId && <button onClick={() => downloadReportPdf(runId)}>Download PDF</button>}
      </div>
      {runId && <div>Run ID: {runId}</div>}
    </div>
  );
}
