#!/usr/bin/env python3
"""Expand the assistant's compact coding decisions into the Story 2 sheet format (AI-coded).

Input line:  <id>: <SCOPE> [<group> <frames> <blamed> <victim>] [d] [?] [# note]
  SCOPE   R resident_refugee_status | X crossborder_people_services | O out_of_scope | U unclear
  group   my kh lv cn il of ge st mx   (Myanmar, Cambodia, Laos/Vietnam, China, Israel, other foreign, generic, stateless/ethnic, mixed)
  frames  letters D disease, J jobs, B undeserved benefits, S security, C criminality, V victim/exploitation, N none, O other
          (O needs text:  O:numbers   or   BO:numbers)
  actors  m migrants | ts thai_state | eb employers_brokers | fs foreign_state | tp thai_public | ot other | no none
  d       dehumanizing language      ?  needs source check
These are the ASSISTANT's judgements. Output rows carry coded_by=assistant and must never be presented as human-coded.
"""
import csv, re, sys
from pathlib import Path

SCOPE = {"R": "resident_refugee_status", "X": "crossborder_people_services", "O": "out_of_scope", "U": "unclear"}
GROUP = {"my": "myanmar", "kh": "cambodia", "lv": "laos_vietnam", "cn": "china", "il": "israel", "of": "other_foreign",
         "ge": "generic", "st": "stateless_ethnic", "mx": "mixed"}
FRAME = {"D": "frame_disease_vector", "J": "frame_job_competition", "B": "frame_undeserved_benefits", "S": "frame_security_threat",
         "C": "frame_criminality", "V": "frame_victim_exploitation", "O": "frame_other", "N": "frame_none"}
ACTOR = {"m": "migrants", "ts": "thai_state", "eb": "employers_brokers", "fs": "foreign_state", "tp": "thai_public", "ot": "other", "no": "none"}
IN = ("R", "X")


def parse_line(line: str) -> tuple[str, dict]:
    body, _, note = line.partition("#")
    i, _, rest = body.partition(":")
    i, toks = i.strip(), rest.split()
    if not toks or toks[0] not in SCOPE:
        raise ValueError(f"{i}: bad scope {toks[:1]}")
    out = {"scope": SCOPE[toks[0]], "note": note.strip(), "needs_source_check": "", "dehumanizing_language": "", "target_group": "",
           "frame_other_text": "", "blamed_actor": "", "victim_actor": ""}
    out.update({f: "" for f in FRAME.values()})
    flags = [t for t in toks[1:] if t in ("d", "?")]
    args = [t for t in toks[1:] if t not in ("d", "?")]
    if "?" in flags or toks[0] == "U":
        out["needs_source_check"] = "1"
    if toks[0] in IN:
        if len(args) != 4:
            raise ValueError(f"{i}: in-scope row needs group frames blamed victim, got {args}")
        g, fr, b, v = args
        if g not in GROUP or b not in ACTOR or v not in ACTOR:
            raise ValueError(f"{i}: bad token in {args}")
        out["target_group"] = GROUP[g]
        letters, _, other = fr.partition(":")
        if not letters or any(c not in FRAME for c in letters):
            raise ValueError(f"{i}: bad frames {fr}")
        if "N" in letters and len(letters) > 1:
            raise ValueError(f"{i}: N cannot be combined")
        if ("O" in letters) != bool(other):
            raise ValueError(f"{i}: frame O needs :text, and text needs O ({fr})")
        for c in letters:
            out[FRAME[c]] = "1"
        out["frame_other_text"] = other
        out["blamed_actor"], out["victim_actor"] = ACTOR[b], ACTOR[v]
        out["dehumanizing_language"] = "1" if "d" in flags else ""
    elif args:
        raise ValueError(f"{i}: {toks[0]} takes no group/frames/actors, got {args}")
    return i, out


def load_codes(paths) -> dict:
    codes = {}
    for p in paths:
        for n, line in enumerate(Path(p).read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip() or line.lstrip().startswith("//"):
                continue
            i, c = parse_line(line)
            if i in codes:
                raise ValueError(f"{p}:{n}: id {i} coded twice")
            codes[i] = c
    return codes
