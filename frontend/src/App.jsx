import { useEffect, useMemo, useState } from "react";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
const MAX_FILES = 10;
const ACTIVE_BATCH_STATUSES = new Set(["queued", "processing"]);

function apiUrl(path) {
  return `${API_BASE_URL}${path}`;
}

async function request(path, options) {
  const response = await fetch(apiUrl(path), options);
  const contentType = response.headers.get("content-type") || "";
  const body = contentType.includes("application/json") ? await response.json() : await response.text();

  if (!response.ok) {
    const message = typeof body === "object" && body?.detail ? body.detail : response.statusText;
    throw new Error(Array.isArray(message) ? message.map((item) => item.msg).join(", ") : message);
  }

  return body;
}

function filenameFromPath(path) {
  return String(path || "").split(/[\\/]/).filter(Boolean).pop() || "";
}

function cleanText(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function groupedKeywords(group) {
  const seen = new Set();
  const values = [group.representative_keyword, ...(group.related_keywords || [])];

  return values
    .map(cleanText)
    .filter((value) => {
      const key = value.toLowerCase();
      if (!value || seen.has(key)) {
        return false;
      }
      seen.add(key);
      return true;
    })
    .join(", ");
}

function resultRows(result) {
  return (result?.keyword_groups || []).map((group, index) => ({
    id: `${group.representative_keyword || "keyword"}-${index}`,
    representative: cleanText(group.representative_keyword),
    grouped: groupedKeywords(group),
    context: cleanText(group.context_text),
    exact: cleanText(group.exact_text)
  }));
}

function totalSize(files) {
  return files.reduce((sum, file) => sum + file.size, 0);
}

function fileKey(file) {
  return `${file.name}-${file.size}-${file.lastModified}`;
}

function finishedFile(file) {
  return ["success", "cached"].includes(file.status) && file.output_path;
}

export default function App() {
  const [apiStatus, setApiStatus] = useState("checking");
  const [files, setFiles] = useState([]);
  const [maxParallelFiles, setMaxParallelFiles] = useState("2");
  const [maxParallelLlmCalls, setMaxParallelLlmCalls] = useState("3");
  const [batch, setBatch] = useState(null);
  const [results, setResults] = useState([]);
  const [groundTruths, setGroundTruths] = useState([]);
  const [selectedGroundTruth, setSelectedGroundTruth] = useState("");
  const [evaluation, setEvaluation] = useState(null);
  const [selectedResultFile, setSelectedResultFile] = useState("");
  const [selectedResult, setSelectedResult] = useState(null);
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const rows = useMemo(() => resultRows(selectedResult), [selectedResult]);
  const batchActive = batch && ACTIVE_BATCH_STATUSES.has(batch.status);

  useEffect(() => {
    checkHealth();
    refreshResults();
    refreshGroundTruths();
  }, []);

  useEffect(() => {
    if (!batchActive) {
      return undefined;
    }

    const timer = window.setInterval(() => {
      refreshBatch(batch.id, { quiet: true });
    }, 1500);
    return () => window.clearInterval(timer);
  }, [batchActive, batch?.id]);

  async function checkHealth() {
    try {
      await request("/health");
      setApiStatus("online");
    } catch {
      setApiStatus("offline");
    }
  }

  async function refreshResults() {
    try {
      const payload = await request("/results");
      setResults(payload.files || []);
    } catch (err) {
      setError(err.message);
    }
  }

  async function refreshGroundTruths() {
    try {
      const payload = await request("/evaluation/ground-truth");
      const files = payload.files || [];
      setGroundTruths(files);
      if (!selectedGroundTruth && files.length > 0) {
        setSelectedGroundTruth(files[0]);
      }
    } catch (err) {
      setError(err.message);
    }
  }

  async function refreshBatch(batchId, options = {}) {
    try {
      const payload = await request(`/batches/${encodeURIComponent(batchId)}`);
      setBatch(payload);
      if (!ACTIVE_BATCH_STATUSES.has(payload.status)) {
        await refreshResults();
        const firstReady = (payload.files || []).find(finishedFile);
        if (!selectedResult && firstReady) {
          await loadResult(firstReady.output_path);
        }
      }
    } catch (err) {
      if (!options.quiet) {
        setError(err.message);
      }
    }
  }

  function selectFiles(event) {
    const incoming = Array.from(event.target.files || []);
    const merged = [...files];
    const seen = new Set(files.map(fileKey));
    for (const file of incoming) {
      if (merged.length >= MAX_FILES) {
        break;
      }
      const key = fileKey(file);
      if (!seen.has(key)) {
        seen.add(key);
        merged.push(file);
      }
    }
    setFiles(merged);
    setBatch(null);
    setSelectedResult(null);
    setSelectedResultFile("");
    setError("");
    event.target.value = "";

    if (incoming.length + files.length > MAX_FILES) {
      setNotice(`File list is limited to ${MAX_FILES} files.`);
    } else {
      setNotice("");
    }
  }

  function removeFile(target) {
    setFiles(files.filter((file) => fileKey(file) !== fileKey(target)));
    setBatch(null);
  }

  function clearFiles() {
    setFiles([]);
    setBatch(null);
    setSelectedResult(null);
    setSelectedResultFile("");
  }

  async function startBatch(event) {
    event.preventDefault();
    if (files.length === 0) {
      setError("Choose one or more PDF/TXT files first.");
      return;
    }

    setBusy("upload");
    setError("");
    setNotice("");

    try {
      const form = new FormData();
      files.forEach((file) => form.append("files", file));
      form.append("max_parallel_files", maxParallelFiles);
      form.append("max_parallel_llm_calls", maxParallelLlmCalls);
      const payload = await request("/batches/upload", {
        method: "POST",
        body: form
      });
      setBatch(payload);
      setNotice(`Batch ${payload.id} queued with ${payload.total_files} file(s).`);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  }

  async function retryJob(jobId) {
    setBusy(`retry-${jobId}`);
    setError("");
    try {
      await request(`/jobs/${encodeURIComponent(jobId)}/retry`, {
        method: "POST"
      });
      if (batch?.id) {
        await refreshBatch(batch.id);
      }
      setNotice("Job queued for retry.");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  }

  async function loadResult(path) {
    const filename = filenameFromPath(path);
    if (!filename) {
      return;
    }

    setBusy("result");
    setError("");
    setSelectedResultFile(path);

    try {
      const result = await request(`/results/${encodeURIComponent(filename)}`);
      setSelectedResult(result);
      setEvaluation(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  }

  async function uploadGroundTruth(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) {
      return;
    }

    setBusy("ground-truth");
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      const payload = await request("/evaluation/ground-truth", {
        method: "POST",
        body: form
      });
      await refreshGroundTruths();
      setSelectedGroundTruth(payload.path);
      setNotice(`Ground truth uploaded: ${payload.filename}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  }

  async function compareWithGroundTruth() {
    if (!selectedResultFile) {
      setError("Choose a result before comparing.");
      return;
    }
    if (!selectedGroundTruth) {
      setError("Upload or choose a ground truth JSON first.");
      return;
    }

    setBusy("evaluation");
    setError("");
    try {
      const report = await request("/evaluation/compare", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          result_path: selectedResultFile,
          ground_truth_path: selectedGroundTruth
        })
      });
      setEvaluation(report);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  }

  return (
    <main className="app-shell">
      <section className="topbar">
        <div>
          <p className="eyebrow">Contract Keyword Pipeline</p>
          <h1>Batch Extraction Workspace</h1>
        </div>
        <span className={`status-pill ${apiStatus}`}>
          API {apiStatus === "checking" ? "checking" : apiStatus}
        </span>
      </section>

      {(notice || error) && (
        <section className={`message ${error ? "error" : "success"}`}>
          {error || notice}
        </section>
      )}

      <section className="workspace-grid async-grid">
        <form className="panel upload-panel" onSubmit={startBatch}>
          <div className="panel-heading">
            <span>01</span>
            <h2>Upload + Queue</h2>
          </div>
          <label className="drop-zone">
            <input
              accept=".pdf,.txt,application/pdf,text/plain"
              multiple
              type="file"
              onChange={selectFiles}
            />
            <strong>
              {files.length > 0 ? `${files.length} file(s) selected` : "Select up to 10 PDF/TXT files"}
            </strong>
            <small>
              {files.length > 0
                ? `${Math.round(totalSize(files) / 1024)} KB total`
                : "Creates a persistent batch job"}
            </small>
          </label>
          {files.length > 0 && (
            <div className="file-list">
              {files.map((file) => (
                <button key={fileKey(file)} onClick={() => removeFile(file)} type="button">
                  {file.name}
                </button>
              ))}
            </div>
          )}
          <div className="run-settings">
            <label>
              <span>Parallel files</span>
              <select
                value={maxParallelFiles}
                onChange={(event) => setMaxParallelFiles(event.target.value)}
              >
                <option value="1">1</option>
                <option value="2">2</option>
                <option value="3">3</option>
                <option value="5">5</option>
              </select>
            </label>
            <label>
              <span>LLM calls per file</span>
              <select
                value={maxParallelLlmCalls}
                onChange={(event) => setMaxParallelLlmCalls(event.target.value)}
              >
                <option value="1">1</option>
                <option value="2">2</option>
                <option value="3">3</option>
                <option value="4">4</option>
              </select>
            </label>
          </div>
          <div className="form-actions">
            <button disabled={busy === "upload" || batchActive} type="submit">
              {busy === "upload" ? "Creating batch..." : "Start Processing"}
            </button>
            {files.length > 0 && (
              <button className="ghost-button" onClick={clearFiles} type="button">
                Clear
              </button>
            )}
          </div>
        </form>

        <section className="panel dashboard-panel">
          <div className="panel-heading">
            <span>02</span>
            <h2>Batch Progress</h2>
            {batch && (
              <button className="ghost-button" onClick={() => refreshBatch(batch.id)} type="button">
                Refresh
              </button>
            )}
          </div>

          {!batch ? (
            <p className="empty-state">No batch queued yet.</p>
          ) : (
            <>
              <div className="batch-summary">
                <strong>{batch.id}</strong>
                <span>{batch.status}</span>
              </div>
              <div className="summary-grid">
                <span>{batch.queued_count} queued</span>
                <span>{batch.processing_count} processing</span>
                <span>{batch.succeeded_count} success</span>
                <span>{batch.cached_count} cached</span>
                <span>{batch.failed_count} failed</span>
              </div>
              <div className="job-list">
                {batch.files.map((file) => (
                  <article className={`job-row ${file.status}`} key={file.id}>
                    <div>
                      <strong>{file.filename}</strong>
                      <small>{file.stage}</small>
                    </div>
                    <progress max="100" value={file.progress} />
                    <div className="job-actions">
                      {finishedFile(file) && (
                        <button onClick={() => loadResult(file.output_path)} type="button">
                          View
                        </button>
                      )}
                      {file.status === "failed" && (
                        <button
                          className="danger-button"
                          disabled={busy === `retry-${file.id}`}
                          onClick={() => retryJob(file.id)}
                          type="button"
                        >
                          Retry
                        </button>
                      )}
                    </div>
                    {file.error && <p>{file.error}</p>}
                  </article>
                ))}
              </div>
            </>
          )}
        </section>

        <section className="panel results-panel">
          <div className="panel-heading">
            <span>03</span>
            <h2>Results</h2>
            <button className="ghost-button" onClick={refreshResults} type="button">
              Refresh
            </button>
          </div>

          {results.length === 0 ? (
            <p className="empty-state">No result files yet.</p>
          ) : (
            <div className="result-list">
              {results.map((path) => (
                <button
                  className={path === selectedResultFile ? "selected" : ""}
                  key={path}
                  onClick={() => loadResult(path)}
                  type="button"
                >
                  <strong>{filenameFromPath(path)}</strong>
                  <small>{path}</small>
                </button>
              ))}
            </div>
          )}
        </section>
      </section>

      <section className="evaluation-section">
        <div className="evaluation-controls">
          <div>
            <p className="eyebrow">Ground Truth Evaluation</p>
            <h2>Compare Result</h2>
          </div>
          <label className="upload-ground-truth">
            <input accept=".json,application/json" type="file" onChange={uploadGroundTruth} />
            {busy === "ground-truth" ? "Uploading..." : "Upload Ground Truth"}
          </label>
          <select
            value={selectedGroundTruth}
            onChange={(event) => setSelectedGroundTruth(event.target.value)}
          >
            <option value="">Select ground truth</option>
            {groundTruths.map((path) => (
              <option key={path} value={path}>
                {filenameFromPath(path)}
              </option>
            ))}
          </select>
          <button
            disabled={!selectedResultFile || !selectedGroundTruth || busy === "evaluation"}
            onClick={compareWithGroundTruth}
            type="button"
          >
            {busy === "evaluation" ? "Comparing..." : "Compare"}
          </button>
        </div>

        {evaluation ? (
          <div className="evaluation-report">
            <div>
              <span>Accuracy</span>
              <strong>{evaluation.accuracy_percent}%</strong>
            </div>
            <div>
              <span>Processing Time</span>
              <strong>{evaluation.processing_time_seconds ?? "-"}s</strong>
            </div>
            <div>
              <span>Matched</span>
              <strong>
                {evaluation.matched}/{evaluation.expected}
              </strong>
            </div>
            <div>
              <span>Precision</span>
              <strong>{Math.round((evaluation.precision || 0) * 100)}%</strong>
            </div>
            <div>
              <span>Recall</span>
              <strong>{Math.round((evaluation.recall || 0) * 100)}%</strong>
            </div>
            <div>
              <span>Text Match</span>
              <strong>{Math.round((evaluation.text_match_rate || 0) * 100)}%</strong>
            </div>
          </div>
        ) : (
          <p className="empty-state">Upload a ground truth JSON and select a result to estimate accuracy.</p>
        )}
      </section>

      <section className="output-section">
        <div className="output-heading">
          <div>
            <p className="eyebrow">Contract Keyword Extraction Output</p>
            <h2>{selectedResult?.document_name || "Select a result"}</h2>
          </div>
          {selectedResult && (
            <div className="summary-grid">
              <span>{selectedResult.total_pages || 0} pages</span>
              <span>{selectedResult.total_segments || 0} segments</span>
              <span>{selectedResult.total_keyword_groups || rows.length} groups</span>
            </div>
          )}
        </div>

        {busy === "result" ? (
          <p className="empty-state">Loading result...</p>
        ) : rows.length === 0 ? (
          <p className="empty-state">Queue a batch or choose a saved result to view the table.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Representative Keyword</th>
                  <th>Grouped Keywords</th>
                  <th>Context Text</th>
                  <th>Exact Extracted Information</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id}>
                    <td>{row.representative}</td>
                    <td>{row.grouped}</td>
                    <td>{row.context}</td>
                    <td>{row.exact}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
