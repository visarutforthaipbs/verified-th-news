#!/bin/bash
# Pull finished ASR results from the GPU node into the canonical database.
#
# Run this whenever you want the review room topped up -- it is idempotent and
# safe to run mid-batch. Verdicts go in as verdict_origin='llm' (human labels
# are never overwritten) and the transcript+quote go into asr_evidence, which
# is what /review?mode=verify needs to show you the machine's reasoning.
set -e
scp -q lighthouse-gpu01:~/th-verify-asr/standard_results.jsonl /tmp/asr_new.jsonl
scp -q /tmp/asr_new.jsonl lighthouse-core:~/th-verify/data/asr_standard_results.jsonl
ssh lighthouse-core "cd ~/th-verify && \
  .venv/bin/python scripts/asr/asr_pipeline.py apply data/asr_standard_results.jsonl 2>&1 | tail -3 && \
  .venv/bin/python scripts/import_asr_evidence.py --results data/asr_standard_results.jsonl --apply 2>&1 | tail -2"
