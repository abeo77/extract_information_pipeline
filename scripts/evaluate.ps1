param(
    [string]$ResultDir = "data/output",
    [string]$GroundTruthDir = "data/ground_truth",
    [string]$OutputDir = "data/evaluation"
)

$ErrorActionPreference = "Stop"

python -m app.evaluation.run_evaluation_suite `
    --result-dir $ResultDir `
    --ground-truth-dir $GroundTruthDir `
    --output-dir $OutputDir
