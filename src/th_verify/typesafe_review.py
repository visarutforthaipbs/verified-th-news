"""TypeSafe System One contract for migrant-story editorial screening.

The API output is deliberately namespaced and must never overwrite the human
review columns.  This module contains no network code so its contract and
routing behavior can be tested without an API key.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Mapping

import httpx


MODEL = "jev-latest"
API_URL = "https://api.typesafe.ai/v1/systemone"
QUESTION_SET_VERSION = "2026-09-21.v1"
RETRYABLE_HTTP_STATUSES = {408, 429, *range(500, 600)}

SCOPE_OPTIONS = {
    "resident_refugee_status": (
        "The claim is about migrants, foreign workers, refugees, stateless people, "
        "or foreign residents in Thailand, including their legal status, rights, "
        "work, citizenship, health, education, welfare, or treatment."
    ),
    "crossborder_people_services": (
        "The claim is about people crossing Thailand's borders or cross-border "
        "services that directly affect people, such as entry, evacuation, permits, "
        "health screening, or humanitarian assistance."
    ),
    "out_of_scope": (
        "The text is not materially about migrants or cross-border people in "
        "Thailand. Foreign countries, trade, territorial disputes, generic Thai "
        "workers, or the word 'foreign' alone do not qualify."
    ),
    "unclear": (
        "The claim/title alone is too ambiguous or incomplete to decide whether "
        "migrants or cross-border people in Thailand are materially involved."
    ),
}

ISSUE_OPTIONS = {
    "health_disease": "Disease transmission, vaccination, treatment, or public health.",
    "work_economic_competition": "Jobs, wages, occupations, businesses, or economic competition.",
    "citizenship_legal_status": "Citizenship, identity cards, visas, permits, registration, or legal status.",
    "border_security": "Borders, territorial security, entry controls, evacuation, or national security.",
    "public_services_education": "Education, welfare, health access, benefits, or other public services.",
    "crime_irregular_entry": "Crime, policing, detention, trafficking, or irregular entry/stay.",
    "scam_impersonation": "A scam or impersonation that merely uses a migrant-related authority or service.",
    "other_unclear": "None of the above is clearly the main issue, or the text is insufficient.",
}

FRAME_QUESTIONS = {
    "frame_disease_vector": (
        "Does `record.claim_text` explicitly frame migrants or cross-border people "
        "as carriers or spreaders of disease?"
    ),
    "frame_job_competition": (
        "Does `record.claim_text` explicitly frame migrants as taking jobs, income, "
        "business, or economic opportunities from Thai people?"
    ),
    "frame_undeserved_benefits": (
        "Does `record.claim_text` explicitly frame migrants as receiving citizenship, "
        "rights, welfare, education, health care, or state benefits they do not deserve?"
    ),
    "frame_security_threat": (
        "Does `record.claim_text` explicitly frame migrants or cross-border people "
        "as a threat to sovereignty, territory, elections, or national security?"
    ),
    "frame_criminality": (
        "Does `record.claim_text` explicitly generalize migrants or cross-border "
        "people as criminals, illegal entrants, traffickers, or dangerous people?"
    ),
    "frame_victim_exploitation": (
        "Does `record.claim_text` explicitly frame migrants as victims of abuse, "
        "exploitation, trafficking, discrimination, or denial of rights?"
    ),
}


def questions() -> dict[str, dict[str, Any]]:
    """Return the versioned, atomic question set sent in one API request."""
    result: dict[str, dict[str, Any]] = {
        "in_scope": {
            "type": "noul",
            "instructions": (
                "Is `record.claim_text` materially about migrants, foreign workers, "
                "refugees, stateless people, foreign residents in Thailand, or people "
                "crossing Thailand's borders? Judge only the supplied record text."
            ),
            "criteria": {
                "true": "Those people are a material subject of the claim.",
                "false": "They are absent, incidental, or only a semantic-neighbor false positive.",
            },
        },
        "scope_type": {
            "type": "choice",
            "instructions": (
                "Which editorial scope category best describes `record.claim_text` "
                "and `record.title`? Judge only the supplied text."
            ),
            "criteria": SCOPE_OPTIONS,
        },
        "primary_issue": {
            "type": "choice",
            "instructions": (
                "What is the main issue in `record.claim_text`? Choose other_unclear "
                "when the text is out of scope or insufficient."
            ),
            "criteria": ISSUE_OPTIONS,
        },
        "evidence_clarity": {
            "type": "choice",
            "instructions": (
                "How directly do `record.claim_text` and `record.title` support the "
                "scope and framing judgments, without opening the source URL?"
            ),
            "criteria": {
                "explicit": "The relevant subject and relation are explicit in the text.",
                "ambiguous": "The subject is present but its role or intended meaning is ambiguous.",
                "insufficient": "The text does not contain enough evidence for a responsible judgment.",
            },
        },
    }
    result.update(
        {
            question_id: {"type": "noul", "instructions": instructions}
            for question_id, instructions in FRAME_QUESTIONS.items()
        }
    )
    return result


def build_payload(record: Mapping[str, Any]) -> dict[str, Any]:
    """Build an API request without leaking existing labels into model state."""
    state = {
        "record": {
            "id": str(record.get("id", "")),
            "claim_text": str(record.get("claim_text", "")),
            "title": str(record.get("title", "")),
            "source": str(record.get("source", "")),
            "date": str(record.get("date", "")),
        },
        "editorial_context": (
            "Thai fact-check archive screening for a story about how narratives "
            "concerning migrants in Thailand change over time. A fact-check title "
            "reports a claim being checked; it does not endorse that claim."
        ),
    }
    return {"state": state, "model": MODEL, "questions": questions()}


def question_set_sha256() -> str:
    """Fingerprint the exact questions so live outputs remain auditable."""
    raw = json.dumps(questions(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def call_system_one(
    client: httpx.Client,
    api_key: str,
    payload: dict[str, Any],
    *,
    max_retries: int = 2,
    sleeper: Any = time.sleep,
) -> dict[str, Any]:
    """Call the HTTP API with bounded backoff for documented transient errors."""
    for attempt in range(max_retries + 1):
        try:
            response = client.post(
                API_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
        except (httpx.TimeoutException, httpx.NetworkError):
            if attempt >= max_retries:
                raise
            sleeper(min(0.5 * (2**attempt), 5.0))
            continue

        if response.status_code not in RETRYABLE_HTTP_STATUSES or attempt >= max_retries:
            response.raise_for_status()
            result = response.json()
            if not isinstance(result, dict):
                raise ValueError("TypeSafe response must be a JSON object")
            return result

        retry_after = response.headers.get("retry-after", "")
        try:
            delay = min(float(retry_after), 10.0) if retry_after else min(0.5 * (2**attempt), 5.0)
        except ValueError:
            delay = min(0.5 * (2**attempt), 5.0)
        sleeper(max(delay, 0.0))
    raise RuntimeError("unreachable TypeSafe retry state")


def parse_response(response: Mapping[str, Any]) -> dict[str, Any]:
    """Flatten typed answers while keeping probabilities for audit."""
    answers = response.get("answers")
    if not isinstance(answers, Mapping):
        raise ValueError("TypeSafe response is missing an answers object")

    scope = answers.get("scope_type", {})
    issue = answers.get("primary_issue", {})
    clarity = answers.get("evidence_clarity", {})
    in_scope = answers.get("in_scope", {})
    out: dict[str, Any] = {
        "typesafe_question_set_version": QUESTION_SET_VERSION,
        "typesafe_question_set_sha256": question_set_sha256(),
        "typesafe_model": str(response.get("model", "")),
        "typesafe_scope": scope.get("choice", ""),
        "typesafe_scope_confidence": scope.get("confidence", ""),
        "typesafe_scope_probabilities": scope.get("probabilities", {}),
        "typesafe_in_scope_probability": in_scope.get("noul", ""),
        "typesafe_primary_issue": issue.get("choice", ""),
        "typesafe_primary_issue_confidence": issue.get("confidence", ""),
        "typesafe_primary_issue_probabilities": issue.get("probabilities", {}),
        "typesafe_evidence_clarity": clarity.get("choice", ""),
        "typesafe_evidence_clarity_confidence": clarity.get("confidence", ""),
    }
    for question_id in FRAME_QUESTIONS:
        answer = answers.get(question_id, {})
        out[f"typesafe_{question_id}_probability"] = answer.get("noul", "")
    usage = response.get("usage", {})
    out["typesafe_input_tokens"] = usage.get("input_tokens", "") if isinstance(usage, Mapping) else ""
    out["typesafe_output_tokens"] = usage.get("output_tokens", "") if isinstance(usage, Mapping) else ""
    return out


def route_for_human_review(
    assistant_scope: str,
    parsed: Mapping[str, Any],
    *,
    choice_confidence: float = 0.70,
    noul_low: float = 0.30,
    noul_high: float = 0.70,
) -> tuple[str, list[str]]:
    """Prioritize review; never auto-accept a machine judgment."""
    reasons: list[str] = []
    scope = str(parsed.get("typesafe_scope", ""))
    try:
        scope_conf = float(parsed.get("typesafe_scope_confidence", 0))
    except (TypeError, ValueError):
        scope_conf = 0.0
    try:
        in_scope = float(parsed.get("typesafe_in_scope_probability", 0.5))
    except (TypeError, ValueError):
        in_scope = 0.5

    if scope != assistant_scope:
        reasons.append("assistant_typesafe_scope_disagreement")
    if scope_conf < choice_confidence:
        reasons.append("low_scope_choice_confidence")
    if noul_low < in_scope < noul_high:
        reasons.append("ambiguous_in_scope_probability")
    if (scope == "out_of_scope" and in_scope >= noul_high) or (
        scope not in {"", "out_of_scope", "unclear"} and in_scope <= noul_low
    ):
        reasons.append("internal_scope_signal_disagreement")
    if parsed.get("typesafe_evidence_clarity") != "explicit":
        reasons.append("text_not_explicit")

    frames_apply = scope in {"resident_refugee_status", "crossborder_people_services"}
    if frames_apply:
        for question_id in FRAME_QUESTIONS:
            key = f"typesafe_{question_id}_probability"
            try:
                value = float(parsed.get(key, 0.5))
            except (TypeError, ValueError):
                value = 0.5
            if noul_low < value < noul_high:
                reasons.append(f"ambiguous_{question_id}_probability")
    return ("high", reasons) if reasons else ("normal", [])
