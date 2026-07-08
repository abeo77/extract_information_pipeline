# Contract Keyword Extraction Pipeline

Extract important contractual concepts from PDF/TXT contracts, group related keywords, and export compact JSON output.

## What This Project Does

The pipeline is designed for contract keyword extraction and review:

```text
Load PDF/TXT
-> Normalize text
-> Segment contract structure
-> Build compact LLM1 input batches
-> LLM1 extracts and groups contract keywords
-> Merge duplicate or synonymous keyword groups
-> Export compact JSON
-> Export results for API, CLI, or a future UI
-> Optional API or notebook-based review/reporting
```

The UI result table uses this user-facing format:

| Representative Keyword | Grouped Keywords | Context Text | Exact Extracted Information |
|---|---|---|---|
| Effective Date | Effective Date, Commencement Date, Start Date | Effective Date: January 1, 2026. | January 1, 2026 |

## Project Structure

```text
extract_information_pipeline/
  app/
    extraction/          LLM1 keyword extraction, prompts, schemas
    loaders/             PDF/TXT document loading
    preprocessing/       Text normalization
    segmentation/        Contract segmentation
    services/            Runtime config, file helpers, JSON result helpers, parallel helpers
    evaluation/          Ground-truth comparison utilities used by API/tests
  api/                   FastAPI routes and request/response schemas
  frontend/              React + Vite workspace UI
  data/
    sample_docs/         Sample contracts
    ground_truth/        Ground-truth JSON files for evaluation
    input/               Uploaded files created by API
    output/              Pipeline result JSON files
  notebooks/
    extraction_output_report.ipynb
  reports/               Generated report Markdown/CSV outputs
  tests/                 Focused unit tests for core pipeline behavior
```

## Setup

Run commands from the project directory:


If you use the existing workspace virtual environment:

```powershell
..\venv\Scripts\python.exe -m pip install -r requirements.txt
```

If you create a local virtual environment inside this project instead:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Environment Variables

Create an `.env` file from the example:

```powershell
Copy-Item .env.example .env
```

Minimum OpenAI-compatible configuration:

```env
KEYWORD_LLM_API_KEY=your_llm_api_key_here
KEYWORD_LLM_BASE_URL=
KEYWORD_LLM_PROVIDER=openai-compatible
KEYWORD_LLM_MODEL=gpt-5.4-mini
```




Runtime tuning:

```env
MAX_PARALLEL_LLM_CALLS=3
INCLUDE_ADMIN_SECTIONS=false
```

Async batch processing:

```env
REDIS_URL=redis://localhost:6379/0
JOB_DB_PATH=data/jobs/jobs.db
DEFAULT_MAX_PARALLEL_FILES=2
```

## Run CLI

Run extraction:

```powershell
..\venv\Scripts\python.exe main.py --file data/sample_docs/4.pdf --output data/output/4_result.json
```

Useful debug commands:

```powershell
..\venv\Scripts\python.exe main.py --file data/sample_docs/4.pdf --debug-load
..\venv\Scripts\python.exe main.py --file data/sample_docs/4.pdf --debug-normalize
..\venv\Scripts\python.exe main.py --file data/sample_docs/4.pdf --debug-segments
..\venv\Scripts\python.exe main.py --file data/sample_docs/4.pdf --debug-llm1-input
```

Batch and parallelism options:

```powershell
..\venv\Scripts\python.exe main.py `
  --file data/sample_docs/4.pdf `
  --output data/output/4_result.json `
  --keyword-batch-size 50 `
  --max-parallel-llm-calls 3
```

## Test Core Flow Before UI

To validate the core batch flow and output without UI or Redis, run the smoke command directly:

```powershell
..\venv\Scripts\python.exe -m app.jobs.smoke `
  data/sample_docs/3.txt `
  data/sample_docs/4.pdf `
  --max-parallel-files 2 `
  --max-parallel-llm-calls 3
```

This command:

- creates a batch locally
- runs the worker logic directly
- writes result JSON files to `data/output`
- prints per-file status, keyword group count, and output path

Use this path when you want to verify the core processing and multi-file concurrency before touching the UI layer.

## Run UI + Async Worker

Start Redis:

```powershell
docker compose up redis
```

Start FastAPI:

```powershell
..\venv\Scripts\uvicorn.exe api.main:app --reload
```

Start the background worker in a second terminal:

```powershell
..\venv\Scripts\python.exe -m app.workers.worker
```

Install and start the React/Vite UI:

```powershell
Set-Location frontend
npm install
npm run dev
```

Open:

```text
http://localhost:5173
```

By default, Vite proxies UI requests to `http://localhost:8000`. To point the UI at another API server, copy `frontend/.env.example` to `frontend/.env` and set `VITE_API_BASE_URL`.

The UI supports selecting up to 10 PDF/TXT files at once. Uploading creates a persistent batch job, then the UI polls batch status every 1.5 seconds. Operators can set `Parallel files` and `LLM calls per file` directly before starting a batch.

The UI also includes a ground-truth evaluation workspace. Upload a ground truth JSON, select a result JSON, and click Compare to estimate processing time, precision, recall, F1/accuracy, and text match rate. The app stores uploaded ground truth files under `data/ground_truth`; it does not generate ground truth automatically.

## Run API

Start FastAPI:

```powershell
..\venv\Scripts\uvicorn.exe api.main:app --reload
```

Open API docs:

```text
http://localhost:8000/docs
```

Main endpoints:

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Health check |
| POST | `/upload` | Upload PDF/TXT into `data/input` |
| POST | `/upload/batch` | Upload up to 10 PDF/TXT files into `data/input` |
| POST | `/pipeline/run` | Run extraction for a file path |
| POST | `/pipeline/run-batch` | Run extraction for up to 10 file paths with bounded file-level concurrency |
| POST | `/batches/upload` | Upload up to 10 files, create a persistent async batch, and enqueue worker processing |
| GET | `/batches/{batch_id}` | Read batch summary and per-file progress/status |
| POST | `/jobs/{job_id}/retry` | Retry one failed file job |
| POST | `/evaluation/ground-truth` | Upload a ground truth JSON file |
| GET | `/evaluation/ground-truth` | List uploaded ground truth JSON files |
| GET | `/results` | List result JSON files |
| GET | `/results/{filename}` | Read one result JSON |
| POST | `/evaluation/compare` | Compare result JSON with ground truth |

The API and evaluation utility remain available for tests and programmatic comparison.

## Ground Truth Format

Ground truth can use the existing provision format:

```json
{
  "document": {
    "document_name": "contract.pdf",
    "provisions": [
      {
        "provision": "Effective Date and Contract Term",
        "specific_keywords": ["Effective Date", "Commencement Date", "Start Date"],
        "text": "Effective Date: April 1, 2026."
      }
    ]
  }
}
```

It can also use the result-table format with `keyword_groups`, `representative_keyword`, `related_keywords`, `context_text`, and `exact_text`.

## Output JSON Format

The exported JSON is compact and user-facing:

```json
{
  "document_name": "contract.pdf",
  "processing_time_seconds": 49.62,
  "total_pages": 2,
  "total_segments": 15,
  "total_keyword_groups": 11,
  "llm_calls": {
    "keyword_extraction_batches": 1,
    "keyword_groups_for_evidence": 0,
    "evidence_extraction_batches": 0
  },
  "keyword_groups": [
    {
      "representative_keyword": "Effective Date",
      "related_keywords": ["Commencement Date", "Start Date"],
      "context_text": "Effective Date: January 1, 2026.",
      "exact_text": "January 1, 2026",
      "metadata": {
        "page": 1,
        "clause_no": "2"
      }
    }
  ]
}
```

Result files are written to:

```text
data/output/
```
