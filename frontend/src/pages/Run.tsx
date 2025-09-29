import React, { useEffect, useState } from "react";
import { listSections, runReport, downloadReportPdf } from "../api";

export default function Run() {
  const [framework, setFramework] = useState("seal");
  const [firm, setFirm] = useState("Legal Partners LLC");
  const [sections, setSections] = useState<Array<{id:string; name:string; position:number; prompt:string;}>>([]);
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [overrides, setOverrides] = useState<Record<string,string>>({});
  const [runId, setRunId] = useState<string>("");
  const [msg, setMsg] = useState("");

  async function load() {
    setMsg("Loading sections...");
    try {
      const r = await listSections(framework);
      const ss = (r.sections ?? []).sort((a:any,b:any)=>a.position-b.position);
      setSections(ss);
      setSelected(Object.fromEntries(ss.map((s:any) => [s.id, true])));
      setOverrides({});
      setMsg("");
    } catch (e:any) {
      setMsg(`Error: ${e.message}`);
    }
  }
  useEffect(() => { load(); }, [framework]);

  async function go() {
    setMsg("Generating...");
    try {
      const selectedIds = sections.filter(s => selected[s.id]).map(s => s.id);
      const r = await runReport({
        framework,
        firm,
        selected_section_ids: selectedIds,
        prompt_overrides: overrides,
      });
      setRunId(r.run_id);
      setMsg(`Done: ${r.run_id}`);
    } catch (e:any) {
      setMsg(`Error: ${e.message}`);
    }
  }

  return (
    <div style={{display:"grid", gap:16}}>
      <h2>Run Report</h2>

      <div>
        <label>Framework: </label>
        <select value={framework} onChange={e=>setFramework(e.target.value)}>
          {["seal","occ","osfi_b10","osfi_b13"].map(f => <option key={f} value={f}>{f}</option>)}
        </select>
      </div>

      <div>
        <label>Firm: </label>
        <input value={firm} onChange={e=>setFirm(e.target.value)} />
      </div>

      <div style={{fontSize:12, color:"#666"}}>{msg}</div>

      <div style={{border:"1px solid #ddd", borderRadius:8, padding:12}}>
        <h3>Sections</h3>
        {sections.map((s) => (
          <div key={s.id} style={{display:"grid", gridTemplateColumns:"24px 160px 1fr", gap:8, alignItems:"start", marginBottom:8}}>
            <input type="checkbox" checked={!!selected[s.id]} onChange={e=>setSelected({...selected, [s.id]: e.target.checked})}/>
            <div><b>{s.position}.</b> {s.name} <span style={{opacity:.6, fontSize:12}}>({s.id})</span></div>
            <textarea
              placeholder={`Prompt override for ${s.name} (optional)`}
              value={overrides[s.id] ?? ""}
              onChange={e=>setOverrides({...overrides, [s.id]: e.target.value})}
              rows={3}
            />
          </div>
        ))}
      </div>

      <div>
        <button onClick={go}>Generate</button>
        {runId && (
          <button onClick={()=>downloadReportPdf(runId)} style={{marginLeft:8}}>Download PDF</button>
        )}
      </div>
    </div>
  );
}
