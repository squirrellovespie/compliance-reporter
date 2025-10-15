import React, { useState } from "react";
import { indexFramework, uploadAssessment, uploadEvidenceBatch } from "../api";

const frameworks = ["osfi_b13", "osfi_b10", "occ", "seal"];

type BatchFileResult = {
  file: string;
  chunks: number;
  status: "ok" | "error";
  error?: string;
};

export default function Ingest() {
  // Framework indexing
  const [fw, setFw] = useState(frameworks[0]);
  const [fwMsg, setFwMsg] = useState<string>("");

  // Assessment
  const [aFirm, setAFirm] = useState("Legal Partners LLC");
  const [aFile, setAFile] = useState<File | null>(null);
  const [aMsg, setAMsg] = useState("");

  // Evidence (multi-file)
  const [eFirm, setEFirm] = useState("Legal Partners LLC");
  const [files, setFiles] = useState<File[]>([]);
  const [eMsg, setEMsg] = useState<string>("");
  const [batchDetails, setBatchDetails] = useState<BatchFileResult[] | null>(null);

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

  async function handleUploadEvidenceBatch() {
    if (!files.length) {
      setEMsg("Choose one or more files first");
      return;
    }
    setEMsg("Uploading & indexing…");
    setBatchDetails(null);
    try {
      const res = await uploadEvidenceBatch(eFirm, files);
      // res shape: { total_docs, total_chunks, files: [{file, chunks, status, error?}, ...] }
      setEMsg(`Indexed ${res.total_chunks} chunks from ${res.total_docs} file(s).`);
      setBatchDetails(res.files || []);
    } catch (e: any) {
      setEMsg(`Error: ${e.message}`);
    }
  }

  return (
    <div style={{ display: "grid", gap: 28 }}>
      {/* Index framework */}
      <section style={{ border: "1px solid #ddd", borderRadius: 12, padding: 16 }}>
        <h2>Index Framework</h2>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <select value={fw} onChange={(e) => setFw(e.target.value)}>
            {frameworks.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </select>
          <button onClick={handleIndexFramework}>Index</button>
          <span>{fwMsg}</span>
        </div>
        <p style={{ fontSize: 12, opacity: 0.7 }}>
          Uses chunks under <code>backend/src/guidelines/&lt;framework&gt;/chunks</code>.
        </p>
      </section>

      {/* Assessment upload */}
      <section style={{ border: "1px solid #ddd", borderRadius: 12, padding: 16 }}>
        <h2>Upload Assessment PDF (Q&amp;A bundle)</h2>
        <div style={{ display: "grid", gap: 8 }}>
          <label>Firm</label>
          <input value={aFirm} onChange={(e) => setAFirm(e.target.value)} />
          <input
            type="file"
            accept="application/pdf"
            onChange={(e) => setAFile(e.target.files?.[0] ?? null)}
          />
          <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
            <button onClick={handleUploadAssessment}>Upload &amp; Index</button>
            <span>{aMsg}</span>
          </div>
        </div>
      </section>

      {/* Evidence batch upload */}
      <section style={{ border: "1px solid #ddd", borderRadius: 12, padding: 16 }}>
        <h2>Upload Evidence Files (multiple; any format)</h2>
        <div style={{ display: "grid", gap: 8 }}>
          <label>Firm</label>
          <input value={eFirm} onChange={(e) => setEFirm(e.target.value)} />
          <input
            type="file"
            multiple
            onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
            // no "accept" => allow PDFs, TXT, DOCX, XLSX/CSV, images, etc.
          />
          <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
            <button onClick={handleUploadEvidenceBatch}>Upload &amp; Index</button>
            <span>{eMsg}</span>
          </div>

          {/* Optional: show a small summary table */}
          {batchDetails && batchDetails.length > 0 && (
            <div style={{ marginTop: 8 }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                <thead>
                  <tr style={{ textAlign: "left" }}>
                    <th style={{ borderBottom: "1px solid #eee", padding: "6px 4px" }}>File</th>
                    <th style={{ borderBottom: "1px solid #eee", padding: "6px 4px" }}>Chunks</th>
                    <th style={{ borderBottom: "1px solid #eee", padding: "6px 4px" }}>Status</th>
                    <th style={{ borderBottom: "1px solid #eee", padding: "6px 4px" }}>Error</th>
                  </tr>
                </thead>
                <tbody>
                  {batchDetails.map((r, i) => (
                    <tr key={`${r.file}-${i}`}>
                      <td style={{ borderBottom: "1px solid #f4f4f4", padding: "6px 4px" }}>
                        {r.file}
                      </td>
                      <td style={{ borderBottom: "1px solid #f4f4f4", padding: "6px 4px" }}>
                        {r.chunks}
                      </td>
                      <td
                        style={{
                          borderBottom: "1px solid #f4f4f4",
                          padding: "6px 4px",
                          color: r.status === "ok" ? "green" : "crimson",
                        }}
                      >
                        {r.status}
                      </td>
                      <td style={{ borderBottom: "1px solid #f4f4f4", padding: "6px 4px" }}>
                        {r.error ?? ""}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}