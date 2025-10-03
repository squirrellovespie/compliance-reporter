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

# 🔧 RAG Pipeline:

## Files & Responsibilities

### Chunking & Indexing

* **Guideline chunking**: `backend/src/engine/ingest_guidelines.py`

  * Tools: **PyMuPDF** (text extraction), **tiktoken** (token-based chunking)
  * Output: `backend/src/guidelines/<framework>/chunks/*.jsonl`

* **Vector store client**: `backend/src/services/vector_langchain.py`

  * Tools: **LangChain** + **Chroma** (persistent), **OpenAIEmbeddings**
  * Collections:

    * `fw_<framework>` (guidelines)
    * `assessment_<firm>`
    * `evidence_<firm>`

* **Indexer entry points**: `backend/src/engine/indexer.py`

  * Reads chunks & pushes to vector store
  * Called by API routes:

    * `POST /index/framework/{framework}` → `backend/src/api/routes/index.py`
    * `POST /ingest/assessment` & `POST /ingest/evidence` → `backend/src/api/routes/ingest.py`

### Retrieval & Synthesis

* **Assessors (per framework)**:

  * Base logic: `backend/src/assessors/base.py`

    * `build_findings(ctx)` → queries top-k from `fw_`, `assessment_`, `evidence_`
    * `render_section_text(...)` → generates narrative using LLM
  * Framework binding: `backend/src/assessors/<framework>/assessor.py`
  * Taxonomy (controls/micro-requirements):
    `backend/src/assessors/<framework>/taxonomy.yaml`

* **Sections (admin-defined)**: `backend/src/engine/sections_store.py`
  API routes in `backend/src/api/routes/sections.py`

* **Orchestration**: `backend/src/engine/orchestrator.py`

  * Loads assessor, builds findings, generates section narratives
  * Persists run JSON to `backend/src/data/runs/<run_id>.json`

### Rendering & APIs

* **PDF rendering**: `backend/src/engine/renderers/pdf_report.py` (ReportLab)
* **API**:

  * App wiring: `backend/src/api/app.py`
  * Index routes: `backend/src/api/routes/index.py`
  * Ingest routes: `backend/src/api/routes/ingest.py`
  * Sections routes: `backend/src/api/routes/sections.py`
  * Reports routes: `backend/src/api/routes/reports.py`

### Frontend (React + Vite)

* API client: `frontend/src/api.ts`
* Pages:

  * Ingest: `frontend/src/pages/Ingest.tsx`
  * Run (select sections, prompts): `frontend/src/pages/Run.tsx`
  * Report (view + download PDF): `frontend/src/pages/Report.tsx`
  * Sections admin: `frontend/src/pages/SectionsAdmin.tsx`

## Models & Providers

* **Chunking**: PyMuPDF + tiktoken
* **Vector DB**: Chroma via **LangChain** wrappers
* **Embeddings**: `OpenAIEmbeddings` (OpenAI)
* **LLM**: OpenAI Chat models (`gpt-4o-mini`) are required for generating section narratives and the final report text.

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
