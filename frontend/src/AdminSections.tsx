import React, { useEffect, useState } from "react";
import { listSections, upsertSections, deleteSection } from "./api";

export default function AdminSections() {
  const [framework, setFramework] = useState("seal");
  const [rows, setRows] = useState<Array<{id:string; name:string; position:number; prompt:string;}>>([]);
  const [msg, setMsg] = useState("");

  async function load() {
    setMsg("Loading...");
    try {
      const r = await listSections(framework);
      setRows((r.sections ?? []).sort((a:any,b:any)=>a.position-b.position));
      setMsg("");
    } catch (e:any) {
      setMsg(`Error: ${e.message}`);
    }
  }
  useEffect(() => { load(); }, [framework]);

  function addRow() {
    const nextPos = rows.length ? Math.max(...rows.map(r => r.position)) + 1 : 1;
    setRows([...rows, { id:"", name:"", position: nextPos, prompt:"" }]);
  }
  function update(i:number, patch:Partial<typeof rows[number]>) {
    const copy = rows.slice(); copy[i] = {...copy[i], ...patch}; setRows(copy);
  }
  async function save() {
    setMsg("Saving...");
    try {
      await upsertSections(framework, rows);
      setMsg("Saved.");
      load();
    } catch (e:any) {
      setMsg(`Error: ${e.message}`);
    }
  }
  async function remove(id:string) {
    if (!id) { setRows(rows.filter(r => r.id)); return; }
    await deleteSection(framework, id);
    await load();
  }

  return (
    <div style={{display:"grid", gap:16}}>
      <h2>Admin: Framework Sections</h2>
      <div>
        <label>Framework: </label>
        <select value={framework} onChange={e=>setFramework(e.target.value)}>
          {["seal","occ","osfi_b10","osfi_b13"].map(f => <option key={f} value={f}>{f}</option>)}
        </select>
        <button onClick={load} style={{marginLeft:8}}>Reload</button>
      </div>
      <div style={{fontSize:12, color:"#666"}}>{msg}</div>

      <table style={{borderCollapse:"collapse", width:"100%"}}>
        <thead>
          <tr>
            <th style={{textAlign:"left"}}>Position</th>
            <th style={{textAlign:"left"}}>ID</th>
            <th style={{textAlign:"left"}}>Name</th>
            <th style={{textAlign:"left"}}>Prompt</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              <td><input type="number" value={r.position} onChange={e=>update(i,{position:parseInt(e.target.value||"1",10)})} style={{width:70}}/></td>
              <td><input value={r.id} onChange={e=>update(i,{id:e.target.value})} style={{width:180}}/></td>
              <td><input value={r.name} onChange={e=>update(i,{name:e.target.value})} style={{width:260}}/></td>
              <td><textarea value={r.prompt} onChange={e=>update(i,{prompt:e.target.value})} rows={3} style={{width:"100%"}}/></td>
              <td><button onClick={()=>remove(r.id)}>Delete</button></td>
            </tr>
          ))}
        </tbody>
      </table>

      <div>
        <button onClick={addRow}>+ Add</button>
        <button onClick={save} style={{marginLeft:8}}>Save All</button>
      </div>
    </div>
  );
}
