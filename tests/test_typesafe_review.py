import httpx

from th_verify.typesafe_review import (
    build_payload,
    call_system_one,
    parse_response,
    question_set_sha256,
    questions,
    route_for_human_review,
)


def test_payload_excludes_existing_labels_and_batches_atomic_questions():
    record = {
        "id": "42",
        "claim_text": "แรงงานข้ามชาติได้รับบัตรประชาชนไทย",
        "title": "ตรวจสอบข้ออ้างเรื่องบัตรประชาชน",
        "source": "example",
        "date": "2025-01-01",
        "assistant_scope": "resident_refugee_status",
        "human_scope": "",
    }
    payload = build_payload(record)
    assert payload["model"] == "jev-latest"
    assert payload["state"]["record"]["id"] == "42"
    assert "assistant_scope" not in payload["state"]["record"]
    assert "human_scope" not in payload["state"]["record"]
    assert len(questions()) == 10
    assert questions()["scope_type"]["type"] == "choice"
    assert set(questions()["in_scope"]["criteria"]) == {"true", "false"}
    assert questions()["frame_security_threat"]["type"] == "noul"
    assert len(question_set_sha256()) == 64


def test_parse_and_review_routing_preserve_typed_signals():
    response = {
        "model": "jev-1.13.0",
        "answers": {
            "in_scope": {"type": "noul", "noul": 0.92},
            "scope_type": {
                "type": "choice",
                "choice": "resident_refugee_status",
                "confidence": 0.88,
                "probabilities": {"resident_refugee_status": 0.9, "out_of_scope": 0.1},
            },
            "primary_issue": {
                "type": "choice",
                "choice": "citizenship_legal_status",
                "confidence": 0.8,
                "probabilities": {"citizenship_legal_status": 0.86, "other_unclear": 0.14},
            },
            "evidence_clarity": {
                "type": "choice",
                "choice": "explicit",
                "confidence": 0.9,
                "probabilities": {"explicit": 0.95, "ambiguous": 0.05},
            },
            "frame_disease_vector": {"type": "noul", "noul": 0.03},
            "frame_job_competition": {"type": "noul", "noul": 0.04},
            "frame_undeserved_benefits": {"type": "noul", "noul": 0.84},
            "frame_security_threat": {"type": "noul", "noul": 0.05},
            "frame_criminality": {"type": "noul", "noul": 0.08},
            "frame_victim_exploitation": {"type": "noul", "noul": 0.06},
        },
        "usage": {"input_tokens": 400, "output_tokens": 70},
    }
    parsed = parse_response(response)
    assert parsed["typesafe_scope"] == "resident_refugee_status"
    assert parsed["typesafe_frame_undeserved_benefits_probability"] == 0.84
    assert parsed["typesafe_input_tokens"] == 400
    assert route_for_human_review("resident_refugee_status", parsed) == ("normal", [])

    priority, reasons = route_for_human_review("out_of_scope", parsed)
    assert priority == "high"
    assert "assistant_typesafe_scope_disagreement" in reasons

    parsed["typesafe_frame_security_threat_probability"] = 0.51
    priority, reasons = route_for_human_review("resident_refugee_status", parsed)
    assert priority == "high"
    assert "ambiguous_frame_security_threat_probability" in reasons


def test_response_without_answers_is_rejected():
    try:
        parse_response({"model": "jev"})
    except ValueError as error:
        assert "answers" in str(error)
    else:
        raise AssertionError("missing answers must fail")


def test_http_client_retries_transient_status_and_respects_retry_after():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"retry-after": "0"}, request=request)
        return httpx.Response(200, json={"model": "jev-1.13.0", "answers": {}, "usage": {}}, request=request)

    delays = []
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = call_system_one(
            client,
            "test-key",
            {"state": "x", "model": "jev-latest", "questions": {}},
            sleeper=delays.append,
        )
    assert result["model"] == "jev-1.13.0"
    assert calls == 2
    assert delays == [0.0]
