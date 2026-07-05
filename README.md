# Contract Keyword Pipeline

Extract key contractual concepts from PDF/TXT contracts, attach supporting evidence, and export a compact JSON result.

## Pipeline

```text
Load PDF/TXT
-> Normalize text
-> Segment contract structure
-> Build compact LLM1 batches
-> LLM1 extract keyword groups
-> LLM2 attach evidence
-> Merge duplicate keyword groups
-> Export compact JSON
-> Optional ground-truth comparison
```

## Run CLI

Create `.env` from the example and add your LLM settings:

```powershell
Copy-Item .env.example .env
```

Required common settings:

```env
KEYWORD_LLM_API_KEY=...
KEYWORD_LLM_BASE_URL=...
KEYWORD_LLM_PROVIDER=openai-compatible
KEYWORD_LLM_MODEL=gpt-5.4-mini
```

Run extraction:

```powershell
.\venv\Scripts\python.exe main.py --file data/sample_docs/4.pdf --output data/output/4_result.json
```

Debug segmentation only:

```powershell
.\venv\Scripts\python.exe main.py --file data/sample_docs/4.pdf --debug-segments
```

## Run API

```powershell
.\venv\Scripts\uvicorn.exe api.main:app --reload
```

## Run UI

```powershell
.\venv\Scripts\streamlit.exe run ui/streamlit_app.py
```

## Main Files

- `main.py`: CLI entrypoint.
- `app/pipeline.py`: orchestrates the full extraction flow.
- `app/loaders/document_loader.py`: loads PDF/TXT files and preserves page metadata.
- `app/preprocessing/normalizer.py`: cleans whitespace, invisible characters, and formatting noise.
- `app/segmentation/contract_segmenter.py`: splits normalized contract text into meaningful segments.
- `app/extraction/llm1_input.py`: creates compact segment batches for LLM1.
- `app/extraction/prompts.py`: stores LLM1 and LLM2 prompt templates.
- `app/extraction/keyword_extractor.py`: runs LLM1 and normalizes keyword groups.
- `app/extraction/evidence_extractor.py`: runs LLM2 and attaches evidence text.
- `app/extraction/group_merger.py`: merges duplicate or clearly synonymous keyword groups.
- `app/services/result_service.py`: saves, loads, and compacts result JSON.
- `app/evaluation/evaluate_ground_truth.py`: compares result keywords against ground truth.
- `api/`: FastAPI routes and request/response schemas.
- `ui/`: Streamlit interface for upload, run, results, and evaluation.
- `tests/`: focused tests for pipeline components.

## Output Format

The exported JSON is compact and user-facing:

```json
{
  "keyword_groups": [
    {
      "representative_keyword": "Effective Date",
      "related_keywords": ["Commencement Date", "Start Date"],
      "context_text": "Effective Date: January 1, 2026.",
      "exact_text": "Effective Date: January 1, 2026.",
      "metadata": {
        "page": 1,
        "clause_no": "2"
      }
    }
  ]
}
```

## Tests

```powershell
.\venv\Scripts\python.exe -m pytest
```
