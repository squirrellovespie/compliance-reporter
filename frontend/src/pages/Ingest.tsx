import React, { useState } from "react";
import { indexFramework, uploadEvidence, uploadAssessment } from "../api";

const frameworks = ["osfi_b13", "osfi_b10", "occ", "seal"];

export default function Ingest() {
  const [fw, setFw] = useState(frameworks[0]);
  const [fwMsg, setFwMsg] = useState<string>("");

  // assessment
  const [aFirm, setAFirm] = useState("Legal Partners LLC");
  const [aFile, setAFile] = useState<File | null>(null);
  const [aMsg, setAMsg] = useState("");

  // evidence
  const [eFirm, setEFirm] = useState("Legal Partners LLC");
  const [file, setFile] = useState<File | null>(null);
  const [eMsg, setEMsg] = useState<string>("");

  async function handleIndexFramework() {
    setFwMsg("Indexing...");
    try {
      const res = await indexFramework(fw);
      setFwMsg(`Indexed ${res.count} chunks for ${res.framework}`);
    } catch (e: any) {
      setFwMsg(`Error: ${e.message}`);
    }
  }

  async function handleUploadAssessment() {
    if (!aFile) {
      setAMsg("Choose a PDF first");
      return;
    }
    setAMsg("Uploading...");
    try {
      const res = await uploadAssessment(aFirm, aFile);
      setAMsg(`Indexed assessment: ${res.doc_id} (${res.count ?? "?"} pages)`);
    } catch (e: any) {
      setAMsg(`Error: ${e.message}`);
    }
  }
  
  async function handleUploadEvidence() {
    if (!file) {
      setEMsg("Choose a file first");
      return;
    }
    setEMsg("Uploading...");
    try {
      const res = await uploadEvidence(eFirm, file);
      setEMsg(`Indexed evidence: ${res.doc_id} (${res.count ?? "?"} pages)`);
    } catch (e: any) {
      setEMsg(`Error: ${e.message}`);
    }
  }
  

  return (
    <div style={{ display: "grid", gap: 28 }}>
      <section style={{ border: "1px solid #ddd", borderRadius: 12, padding: 16 }}>
        <h2>Index Framework</h2>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <select value={fw} onChange={e => setFw(e.target.value)}>
            {frameworks.map(f => <option key={f} value={f}>{f}</option>)}
          </select>
          <button onClick={handleIndexFramework}>Index</button>
          <span>{fwMsg}</span>
        </div>
      </section>

      <section style={{ border:"1px solid #ddd", borderRadius:12, padding:16 }}>
        <h2>Upload Assessment PDF (Q&A bundle)</h2>
        <div style={{ display:"grid", gap:8 }}>
          <label>Firm</label>
          <input value={aFirm} onChange={e => setAFirm(e.target.value)} />
          <input type="file" accept="application/pdf" onChange={e => setAFile(e.target.files?.[0] ?? null)} />
          <div style={{ display:"flex", gap:12, alignItems:"center" }}>
            <button onClick={handleUploadAssessment}>Upload & Index</button>
            <span>{aMsg}</span>
          </div>
        </div>
      </section>

      <section style={{ border: "1px solid #ddd", borderRadius: 12, padding: 16 }}>
        <h2>Upload Evidence File (.txt or .pdf)</h2>
        <div style={{ display: "grid", gap: 8 }}>
          <label>Firm</label>
          <input value={eFirm} onChange={e => setEFirm(e.target.value)} />
          <input type="file" accept=".txt,application/pdf" onChange={e => setFile(e.target.files?.[0] ?? null)} />
          <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
            <button onClick={handleUploadEvidence}>Upload & Index</button>
            <span>{eMsg}</span>
          </div>
        </div>
      </section>
    </div>
  );
}
