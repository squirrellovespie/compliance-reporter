import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Routes, Route, Link, NavLink } from "react-router-dom";
import Ingest from "./pages/Ingest";
import Run from "./pages/Run";
import Report from "./pages/Report";

function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ fontFamily: "system-ui, sans-serif", maxWidth: 1100, margin: "0 auto", padding: 24 }}>
      <header style={{ display: "flex", gap: 16, alignItems: "baseline", marginBottom: 16 }}>
        <h1 style={{ margin: 0 }}><Link to="/">Compliance Reporter</Link></h1>
        <nav style={{ display: "flex", gap: 12 }}>
          <NavLink to="/ingest">Ingest</NavLink>
          <NavLink to="/run">Run</NavLink>
        </nav>
      </header>
      <main>{children}</main>
      <footer style={{ marginTop: 32, fontSize: 12, opacity: 0.7 }}>local dev UI</footer>
    </div>
  );
}

function Home() {
  return (
    <div>
      <p>Use <b>Ingest</b> to index frameworks & upload evidence / questionnaire. Then <b>Run</b> a report and view findings.</p>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <BrowserRouter>
    <Layout>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/ingest" element={<Ingest />} />
        <Route path="/run" element={<Run />} />
        <Route path="/report/:runId" element={<Report />} />
      </Routes>
    </Layout>
  </BrowserRouter>
);
