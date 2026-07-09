import { useEffect, useMemo, useState } from "react";

import {
  ACTIVE_BATCH_STATUSES,
  MAX_FILES,
  evaluationItemLabel,
  evaluationItems,
  evaluationStats,
  fileKey,
  filenameFromPath,
  finishedFile,
  formatPercent,
  formatSeconds,
  request,
  resultRows,
  totalSize
} from "./appUtils";

export default function App() {
  const [apiStatus, setApiStatus] = useState("checking");
  const [activePanel, setActivePanel] = useState("run");
  const [files, setFiles] = useState([]);
  const [maxParallelFiles, setMaxParallelFiles] = useState("2");
  const [maxParallelLlmCalls, setMaxParallelLlmCalls] = useState("3");
  const [batch, setBatch] = useState(null);
  const [results, setResults] = useState([]);
  const [groundTruths, setGroundTruths] = useState([]);
  const [selectedGroundTruth, setSelectedGroundTruth] = useState("");
  const [evaluation, setEvaluation] = useState(null);
  const [evaluationReports, setEvaluationReports] = useState(null);
  const [selectedReportFile, setSelectedReportFile] = useState("");
  const [selectedResultFile, setSelectedResultFile] = useState("");
  const [selectedResult, setSelectedResult] = useState(null);
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const rows = useMemo(() => resultRows(selectedResult), [selectedResult]);
  const evaluationMetrics = useMemo(() => evaluationStats(evaluation), [evaluation]);
  const evaluationReportFiles = evaluationReports?.files || [];
  const evaluationSummary = evaluationReports?.summary;
  const batchActive = batch && ACTIVE_BATCH_STATUSES.has(batch.status);
  const selectedResultName = filenameFromPath(selectedResultFile);
  const selectedReportName = selectedReportFile || "No report selected";

  useEffect(() => {
    checkHealth();
    refreshResults();
    refreshGroundTruths();
    refreshEvaluationReports();
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

  async function refreshEvaluationReports() {
    try {
      const payload = await request("/evaluation/reports");
      setEvaluationReports(payload);
    } catch (err) {
      setError(err.message);
    }
  }

  async function loadEvaluationReport(filename) {
    setBusy("evaluation-report");
    setError("");
    setSelectedReportFile(filename);
    try {
      const report = await request(`/evaluation/reports/${encodeURIComponent(filename)}`);
      setEvaluation(report);
      setActivePanel("evaluation");
      setNotice(`Loaded evaluation report: ${filename}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
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
      setActivePanel("run");
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
      setActivePanel("results");
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
      setSelectedReportFile("");
      setActivePanel("evaluation");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand-block">
          <span className="brand-mark">CK</span>
          <div>
            <strong>Contract Pipeline</strong>
            <small>Extraction console</small>
          </div>
        </div>

        <nav className="side-nav" aria-label="Workspace sections">
          <button
            className={activePanel === "run" ? "active" : ""}
            onClick={() => setActivePanel("run")}
            type="button"
          >
            <span>01</span>
            Run Sandbox
          </button>
          <button
            className={activePanel === "results" ? "active" : ""}
            onClick={() => setActivePanel("results")}
            type="button"
          >
            <span>02</span>
            Results
          </button>
          <button
            className={activePanel === "evaluation" ? "active" : ""}
            onClick={() => setActivePanel("evaluation")}
            type="button"
          >
            <span>03</span>
            Evaluation
          </button>
        </nav>

        <div className="sidebar-card">
          <span className={`status-dot ${apiStatus}`} />
          <div>
            <strong>API {apiStatus}</strong>
            <small>http://127.0.0.1:8000</small>
          </div>
        </div>
      </aside>

      <section className="main-stage">
        <header className="app-header">
          <div>
            <p className="eyebrow">Production Review Workspace</p>
            <h1>Contract Keyword Extraction</h1>
          </div>
          <div className="header-actions">
            <button className="ghost-button" onClick={refreshResults} type="button">
              Refresh Results
            </button>
            <button className="ghost-button" onClick={refreshEvaluationReports} type="button">
              Refresh Evaluation
            </button>
          </div>
        </header>

        {(notice || error) && (
          <section className={`message ${error ? "error" : "success"}`}>
            {error || notice}
          </section>
        )}

        <section className="overview-grid">
          <article className="metric-card primary">
            <span>Selected Result</span>
            <strong>{selectedResultName || "None"}</strong>
            <small>{rows.length} keyword groups loaded</small>
          </article>
          <article className="metric-card">
            <span>Evaluation Accuracy</span>
            <strong>
              {evaluationSummary
                ? formatPercent(evaluationSummary.average_overall_accuracy_percent, {
                    alreadyPercent: true
                  })
                : "-"}
            </strong>
            <small>{evaluationSummary?.files_evaluated || 0} files evaluated</small>
          </article>
          <article className="metric-card">
            <span>Batch Status</span>
            <strong>{batch?.status || "Idle"}</strong>
            <small>
              {batch
                ? `${batch.succeeded_count} success, ${batch.failed_count} failed`
                : "No active batch"}
            </small>
          </article>
          <article className="metric-card">
            <span>Saved Results</span>
            <strong>{results.length}</strong>
            <small>{evaluationReportFiles.length} evaluation reports</small>
          </article>
        </section>

        <section className="workspace-card">
          <div className="workspace-toolbar">
            <div>
              <p className="eyebrow">Workspace</p>
              <h2>
                {activePanel === "run" && "Run Sandbox"}
                {activePanel === "results" && "Result Review"}
                {activePanel === "evaluation" && "Evaluation Review"}
              </h2>
            </div>
            <div className="segmented-control">
              <button
                className={activePanel === "run" ? "active" : ""}
                onClick={() => setActivePanel("run")}
                type="button"
              >
                Run
              </button>
              <button
                className={activePanel === "results" ? "active" : ""}
                onClick={() => setActivePanel("results")}
                type="button"
              >
                Results
              </button>
              <button
                className={activePanel === "evaluation" ? "active" : ""}
                onClick={() => setActivePanel("evaluation")}
                type="button"
              >
                Evaluation
              </button>
            </div>
          </div>

          {activePanel === "run" && (
            <div className="stage-layout">
              <form className="sandbox-panel" onSubmit={startBatch}>
                <div className="section-heading">
                  <span>Sandbox</span>
                  <h3>Upload and queue a controlled extraction run</h3>
                </div>
                <label className="drop-zone">
                  <input
                    accept=".pdf,.txt,application/pdf,text/plain"
                    multiple
                    type="file"
                    onChange={selectFiles}
                  />
                  <strong>
                    {files.length > 0
                      ? `${files.length} file(s) ready`
                      : "Drop or select PDF/TXT files"}
                  </strong>
                  <small>
                    {files.length > 0
                      ? `${Math.round(totalSize(files) / 1024)} KB total`
                      : "Up to 10 files per batch"}
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

              <section className="progress-panel">
                <div className="section-heading horizontal">
                  <div>
                    <span>Progress</span>
                    <h3>{batch ? batch.id : "No active batch"}</h3>
                  </div>
                  {batch && (
                    <button
                      className="ghost-button"
                      onClick={() => refreshBatch(batch.id)}
                      type="button"
                    >
                      Refresh
                    </button>
                  )}
                </div>

                {!batch ? (
                  <div className="empty-panel">
                    <strong>Ready for a new run</strong>
                    <p>Select files in the sandbox, tune concurrency, then start processing.</p>
                  </div>
                ) : (
                  <>
                    <div className="batch-strip">
                      <span>{batch.queued_count} queued</span>
                      <span>{batch.processing_count} processing</span>
                      <span>{batch.succeeded_count} success</span>
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
                                Open Result
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
            </div>
          )}

          {activePanel === "results" && (
            <div className="review-layout">
              <section className="detail-panel result-detail-panel">
                <div className="section-heading horizontal result-heading">
                  <div>
                    <span>Result Table</span>
                    <h3>{selectedResult?.document_name || "Choose a result"}</h3>
                  </div>
                  <div className="result-actions">
                    <select
                      className="result-picker-select"
                      value={selectedResultFile}
                      onChange={(event) => loadResult(event.target.value)}
                    >
                      <option value="">Choose saved result</option>
                      {results.map((path) => (
                        <option key={path} value={path}>
                          {filenameFromPath(path)}
                        </option>
                      ))}
                    </select>
                    <button className="ghost-button" onClick={refreshResults} type="button">
                      Refresh
                    </button>
                  </div>
                </div>

                {selectedResult && (
                  <div className="summary-grid">
                    <span>{selectedResult.total_pages || 0} pages</span>
                    <span>{selectedResult.total_segments || 0} segments</span>
                    <span>{selectedResult.total_keyword_groups || rows.length} groups</span>
                  </div>
                )}

                {results.length === 0 && (
                  <p className="empty-state">No result files yet.</p>
                )}

                {results.length > 0 && !selectedResult && (
                  <div className="result-chip-list">
                    {results.slice(0, 6).map((path) => (
                      <button
                        className={path === selectedResultFile ? "selected" : ""}
                        key={path}
                        onClick={() => loadResult(path)}
                        type="button"
                      >
                        {filenameFromPath(path)}
                      </button>
                    ))}
                  </div>
                )}

                {busy === "result" ? (
                  <p className="empty-state">Loading result...</p>
                ) : rows.length === 0 ? (
                  <div className="empty-panel">
                    <strong>No result open</strong>
                    <p>Choose a saved result above to inspect extracted keywords.</p>
                  </div>
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
            </div>
          )}

          {activePanel === "evaluation" && (
            <div className="evaluation-layout">
              <section className="evaluation-summary-panel">
                <div className="section-heading horizontal">
                  <div>
                    <span>Updated Evaluation</span>
                    <h3>Generated report summary</h3>
                  </div>
                  <button className="ghost-button" onClick={refreshEvaluationReports} type="button">
                    Refresh
                  </button>
                </div>

                {evaluationSummary ? (
                  <div className="evaluation-report">
                    <div>
                      <span>Files</span>
                      <strong>{evaluationSummary.files_evaluated}</strong>
                    </div>
                    <div>
                      <span>Avg Accuracy</span>
                      <strong>
                        {formatPercent(evaluationSummary.average_overall_accuracy_percent, {
                          alreadyPercent: true
                        })}
                      </strong>
                    </div>
                    <div>
                      <span>Avg Time</span>
                      <strong>
                        {formatSeconds(evaluationSummary.average_processing_time_seconds)}
                      </strong>
                    </div>
                    <div>
                      <span>Avg Precision</span>
                      <strong>
                        {formatPercent(evaluationSummary.average_precision_percent, {
                          alreadyPercent: true
                        })}
                      </strong>
                    </div>
                  </div>
                ) : (
                  <p className="empty-state">No generated evaluation reports found.</p>
                )}

                {evaluationReportFiles.length > 0 && (
                  <div className="evaluation-table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>File</th>
                          <th>Accuracy</th>
                          <th>F1</th>
                          <th>Matched</th>
                          <th>Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {evaluationReportFiles.map((report) => (
                          <tr key={report.filename}>
                            <td>
                              <strong>{report.filename}</strong>
                              <small>{report.document_name}</small>
                            </td>
                            <td>
                              {formatPercent(report.overall_accuracy_percent, {
                                alreadyPercent: true
                              })}
                            </td>
                            <td>{formatPercent(report.f1)}</td>
                            <td>
                              {report.matched_items}/{report.expected_items}
                            </td>
                            <td>
                              <button
                                className={
                                  selectedReportFile === report.filename
                                    ? "selected small-button"
                                    : "small-button"
                                }
                                disabled={busy === "evaluation-report"}
                                onClick={() => loadEvaluationReport(report.filename)}
                                type="button"
                              >
                                Open
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>

              <aside className="evaluation-drawer">
                <div className="section-heading">
                  <span>Report Detail</span>
                  <h3>{selectedReportName}</h3>
                </div>

                <div className="evaluation-controls">
                  <label className="upload-ground-truth">
                    <input
                      accept=".json,application/json"
                      type="file"
                      onChange={uploadGroundTruth}
                    />
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
                    {busy === "evaluation" ? "Comparing..." : "Compare Selected Result"}
                  </button>
                </div>

                {evaluation ? (
                  <>
                    <div className="detail-metrics">
                      <div>
                        <span>Accuracy</span>
                        <strong>
                          {formatPercent(evaluationMetrics.accuracy, {
                            alreadyPercent: true
                          })}
                        </strong>
                      </div>
                      <div>
                        <span>Matched</span>
                        <strong>
                          {evaluationMetrics.matched}/{evaluationMetrics.expected}
                        </strong>
                      </div>
                      <div>
                        <span>F1</span>
                        <strong>{formatPercent(evaluationMetrics.f1)}</strong>
                      </div>
                    </div>

                    <div className="evaluation-detail-grid">
                      <div>
                        <h4>Matched</h4>
                        {evaluationItems(evaluation, "matched_items").length === 0 ? (
                          <p className="empty-state">No matched items.</p>
                        ) : (
                          evaluationItems(evaluation, "matched_items").map((item, index) => (
                            <article key={`${evaluationItemLabel(item)}-${index}`}>
                              <strong>{evaluationItemLabel(item)}</strong>
                              <span>{formatPercent(item.overall_score || 0)}</span>
                            </article>
                          ))
                        )}
                      </div>
                      <div>
                        <h4>Missing</h4>
                        {evaluationItems(evaluation, "missing_items", "missing").length === 0 ? (
                          <p className="empty-state">No missing items.</p>
                        ) : (
                          evaluationItems(evaluation, "missing_items", "missing").map(
                            (item, index) => (
                              <article key={`${evaluationItemLabel(item)}-${index}`}>
                                <strong>{evaluationItemLabel(item)}</strong>
                              </article>
                            )
                          )
                        )}
                      </div>
                      <div>
                        <h4>Extra</h4>
                        {evaluationItems(evaluation, "extra_items", "extra").length === 0 ? (
                          <p className="empty-state">No extra items.</p>
                        ) : (
                          evaluationItems(evaluation, "extra_items", "extra").map((item, index) => (
                            <article key={`${evaluationItemLabel(item)}-${index}`}>
                              <strong>{evaluationItemLabel(item)}</strong>
                            </article>
                          ))
                        )}
                      </div>
                    </div>
                  </>
                ) : (
                  <div className="empty-panel">
                    <strong>Open a report when you need the detail</strong>
                    <p>The summary stays clean until you click Open on a generated report.</p>
                  </div>
                )}
              </aside>
            </div>
          )}
        </section>
      </section>
    </main>
  );
}
