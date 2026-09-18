"""Case-level evidence harness (E04).

Canonical, versioned per-replicate evidence so any evaluated case can be
reconstructed: exact prompt, exact grounding context, raw model output, candidate
SQL, model configuration, validation and execution evidence, and deterministic
content hashes. This package lives in the evaluation layer (``benchmark``); it is
never imported by production runtime code.
"""

from t2s.benchmark.case_evidence.assembler import build_case_run_record
from t2s.benchmark.case_evidence.contract import (
    E05_CONSUMED_PROTOCOL_VERSION,
    SCHEMA_VERSION,
    CaseRunRecord,
    ChatCallRecord,
    ChatMessageRecord,
    EvidenceCompleteness,
    GenerationOutcome,
    GroundingCaptureRecord,
    classify_evidence_completeness,
)
from t2s.benchmark.case_evidence.emit import (
    EvidenceEmitter,
    file_sha256,
    git_source_provenance,
    grounding_config_hash,
)
from t2s.benchmark.case_evidence.hashing import (
    canonical_json,
    sha256_json,
    sha256_text,
)
from t2s.benchmark.case_evidence.recorder import (
    CaseChatEvidence,
    CaseEvidenceRecorder,
    RecordingChatClient,
    active_case_key,
    recording_schema_serializer,
    reset_active_case,
    set_active_case,
)
from t2s.benchmark.case_evidence.replay import (
    HashCheck,
    all_hashes_valid,
    load_case_record,
    load_experiment_records,
    verify_record_hashes,
)
from t2s.benchmark.case_evidence.writer import (
    append_case_record_jsonl,
    hash_index,
    write_case_record,
    write_experiment_manifest,
)

__all__ = [
    "E05_CONSUMED_PROTOCOL_VERSION",
    "SCHEMA_VERSION",
    "CaseChatEvidence",
    "CaseEvidenceRecorder",
    "CaseRunRecord",
    "ChatCallRecord",
    "ChatMessageRecord",
    "EvidenceCompleteness",
    "EvidenceEmitter",
    "GenerationOutcome",
    "GroundingCaptureRecord",
    "HashCheck",
    "RecordingChatClient",
    "active_case_key",
    "all_hashes_valid",
    "append_case_record_jsonl",
    "build_case_run_record",
    "canonical_json",
    "classify_evidence_completeness",
    "file_sha256",
    "git_source_provenance",
    "grounding_config_hash",
    "hash_index",
    "load_case_record",
    "load_experiment_records",
    "recording_schema_serializer",
    "reset_active_case",
    "set_active_case",
    "sha256_json",
    "sha256_text",
    "verify_record_hashes",
    "write_case_record",
    "write_experiment_manifest",
]
