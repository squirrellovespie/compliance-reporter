# Compliance Reporter

An application to generate AI-assisted compliance reports for law firms and banks using **RAG (Retrieval-Augmented Generation)**.

---

## 🔎 How RAG Works

1. **Framework Indexing**

   * Each compliance framework (e.g., OSFI B-13, SEAL, OCC) has guideline PDFs.
   * These are chunked and stored in a vector database (`fw_<framework>`).

2. **Assessment Ingestion**

   * A firm’s self-assessment PDF is uploaded.
   * Extracted text is stored under `assessment_<firm>`.

3. **Evidence Ingestion**

   * Supporting evidence files (redacted `.txt` or PDFs) are uploaded.
   * Extracted text is stored under `evidence_<firm>`.

4. **Findings Generation**

   * Each framework defines controls in a `taxonomy.yaml`.
   * For each control, the system retrieves relevant chunks from:

     * the framework guidelines,
     * the firm’s assessment,
     * the firm’s evidence.
   * The retrieved context is passed to the LLM (or a fallback rule engine) to produce a finding with an assessment, rationale, and evidence links.

5. **Narrative Sections**

   * Reports contain sections (e.g., *Executive Summary*, *Governance*, *Cybersecurity*).
   * Section prompts are admin-defined and can be overridden by the user at runtime.
   * The LLM generates narratives grounded in the retrieved findings and evidence.

6. **Report Output**

   * Results are saved as JSON and can be rendered into a styled PDF.

---

## 📡 APIs

### Indexing & Ingestion

* `POST /index/framework/{framework}` → index a framework’s guideline PDFs.
* `POST /ingest/assessment` → upload a firm’s assessment PDF.
* `POST /ingest/evidence` → upload evidence files.

### Sections

* `GET /sections/{framework}` → list sections for a framework.
* `POST /sections/upsert` → create or update sections (id, name, position, prompt).
* `DELETE /sections/{framework}/{section_id}` → delete a section.
* `POST /sections/seed/{framework}` → seed default sections for a framework.

### Reports

* `POST /reports/run` → generate a report with selected sections and prompt overrides.
* `GET /reports/{run_id}` → fetch report JSON.
* `GET /reports/{run_id}/pdf` → download report as PDF.

---

## ⚙️ Running the System

### Backend

```bash
cd backend
./run_dev.sh
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

---

Do you want me to also add **example request payloads** (like for `/reports/run` and `/sections/upsert`) so it’s crystal clear for anyone calling the APIs?
