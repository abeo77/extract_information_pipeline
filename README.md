# Contract Keyword Extraction Pipeline

Extract important contractual concepts from PDF/TXT contracts, group related keywords, attach exact evidence text, and show the result in a Streamlit UI or compact JSON output.

## What This Project Does

The pipeline is designed for contract keyword extraction and review:

```text
Load PDF/TXT
-> Normalize text
-> Segment contract structure
-> Build compact LLM1 input batches
-> LLM1 extracts and groups contract keywords
-> LLM2 attaches exact evidence text
-> Merge duplicate or synonymous keyword groups
-> Export compact JSON
-> Show results in UI table
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
    extraction/          LLM1 keyword extraction, LLM2 evidence extraction, prompts, schemas
    loaders/             PDF/TXT document loading
    preprocessing/       Text normalization
    segmentation/        Contract segmentation
    services/            Runtime config, file helpers, JSON result helpers, parallel helpers
    evaluation/          Ground-truth comparison utilities used by API/tests
  api/                   FastAPI routes and request/response schemas
  ui/                    Streamlit upload, run, trace, segment preview, and result views
  data/
    sample_docs/         Sample contracts
    ground_truth/        Ground-truth JSON files for evaluation
    input/               Uploaded files created by UI/API
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

## Run The Streamlit UI

Start the UI:

```powershell
..\venv\Scripts\streamlit.exe run ui/streamlit_app.py
```

Open:

```text
http://localhost:8501
```

Current UI tabs:

| Tab | Purpose |
|---|---|
| Segments | Preview normalized contract segments before extraction |
| RUN | Run the pipeline, see step progress, and inspect LLM trace |
| Results | View saved result JSON files as the 4-column extraction table |

The `RUN` tab includes an `LLM Processing Trace` section. It shows each completed LLM batch with:

- stage: `LLM1` or `LLM2`
- provider/model
- elapsed time
- input and output counts
- prompt sent to the LLM
- raw LLM response
- parsed JSON payload
- output summary

Private chain-of-thought is not available from the API; the trace shows observable prompt/response data only.

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
  --evidence-batch-size 20 `
  --max-evidence-segments-per-group 3 `
  --max-parallel-llm-calls 3
```

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
| POST | `/pipeline/run` | Run extraction for a file path |
| GET | `/results` | List result JSON files |
| GET | `/results/{filename}` | Read one result JSON |
| POST | `/evaluation/compare` | Compare result JSON with ground truth |

The Streamlit UI no longer exposes an Evaluation tab, but the API and evaluation utility remain available for tests and programmatic comparison.

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
    "keyword_groups_for_evidence": 11,
    "evidence_extraction_batches": 1
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

