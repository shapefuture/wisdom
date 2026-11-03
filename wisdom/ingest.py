"""Rights-aware ingestion of user-provided text and subtitle files.

Offsets in SourceSpan records are Python Unicode codepoint offsets into the
immutable ``source.data['original_text']`` value. They are not byte offsets.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any

from .errors import ValidationError
from .ports import StorePort


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _input_hash(payload: dict[str, Any]) -> str:
    try:
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValidationError("source payload must contain JSON-compatible values") from exc
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _is_expired(rights: dict[str, Any]) -> bool:
    expires_at = rights.get("expires_at")
    if expires_at is None:
        return False
    if not isinstance(expires_at, str):
        raise ValidationError("rights.expires_at must be an ISO timestamp")
    try:
        expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError("rights.expires_at must be an ISO timestamp") from exc
    if expiry.tzinfo is None:
        raise ValidationError("rights.expires_at must include a timezone")
    return expiry <= datetime.now(timezone.utc)


_TIMING = re.compile(
    r"(?P<start>(?:\d{1,2}:)?\d{2}:\d{2}[,.]\d{3})\s+-->\s+"
    r"(?P<end>(?:\d{1,2}:)?\d{2}:\d{2}[,.]\d{3})(?:\s+.*)?$"
)


def _to_ms(value: str) -> int:
    value = value.replace(",", ".")
    pieces = value.split(":")
    if len(pieces) == 2:
        hours, minutes, seconds = 0, int(pieces[0]), float(pieces[1])
    else:
        hours, minutes, seconds = int(pieces[0]), int(pieces[1]), float(pieces[2])
    return int((hours * 3600 + minutes * 60 + seconds) * 1000)


def _subtitle_cues(original: str) -> list[dict[str, Any]]:
    lines = original.splitlines(keepends=True)
    starts: list[int] = []
    pos = 0
    for line in lines:
        starts.append(pos)
        pos += len(line)
    cues: list[dict[str, Any]] = []
    i = 0
    while i < len(lines):
        match = _TIMING.match(lines[i].strip())
        if not match:
            i += 1
            continue
        start_ms, end_ms = _to_ms(match.group("start")), _to_ms(match.group("end"))
        i += 1
        content_lines: list[str] = []
        while i < len(lines) and lines[i].strip():
            content_lines.append(lines[i].rstrip("\r\n"))
            i += 1
        if content_lines:
            # The range begins at the first displayed text and ends immediately
            # after the last, so the exact source slice includes internal newlines.
            first = i - len(content_lines)
            last = i - 1
            start_char = starts[first]
            end_char = starts[last] + len(lines[last].rstrip("\r\n"))
            cues.append({
                "text": original[start_char:end_char],
                "start_char": start_char,
                "end_char": end_char,
                "start_ms": start_ms,
                "end_ms": end_ms,
            })
        i += 1
    return cues


def _text_spans(original: str) -> list[dict[str, Any]]:
    # Split into sentence-like units while retaining all characters in each
    # anchor. Whitespace-only gaps remain visible in coverage as skipped text.
    spans: list[dict[str, Any]] = []
    pattern = re.compile(r"\S.*?(?:[.!?](?=\s|$)|(?=\Z))", re.DOTALL)
    for match in pattern.finditer(original):
        text = match.group(0)
        if text.strip():
            spans.append({"text": text, "start_char": match.start(), "end_char": match.end()})
    if not spans and original.strip():
        start = len(original) - len(original.lstrip())
        end = len(original.rstrip())
        spans.append({"text": original[start:end], "start_char": start, "end_char": end})
    return spans


class IngestService:
    def __init__(self, store: StorePort):
        self.store = store

    def ingest(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValidationError("source payload must be an object")
        fmt = payload.get("format", "text")
        if fmt not in {"text", "srt", "vtt"}:
            raise ValidationError("format must be text, srt, or vtt")
        original = payload.get("text")
        if original is not None and not isinstance(original, str):
            raise ValidationError("text must be a string or unavailable")
        original = original or ""
        rights = payload.get("rights")
        if not isinstance(rights, dict):
            raise ValidationError("rights metadata must be an object")
        required_rights = {"allowed": bool, "license": str, "private": bool, "allow_export": bool}
        for field, expected in required_rights.items():
            if field not in rights or not isinstance(rights[field], expected):
                raise ValidationError(f"rights.{field} has an invalid or missing value")
        if not rights["license"].strip():
            raise ValidationError("rights.license must be a non-empty string")
        if "allow_model" in rights and not isinstance(rights["allow_model"], bool):
            raise ValidationError("rights.allow_model must be a boolean")
        rights = dict(rights)
        rights.setdefault("allow_model", False)
        expired = _is_expired(rights)
        permitted = rights["allowed"] is True and not expired
        if expired:
            status, reason = "BLOCKED", "source rights have expired"
        elif not permitted:
            status, reason = "BLOCKED", str(rights.get("reason") or "source rights do not permit ingestion")
        elif not original.strip():
            status, reason = "BLOCKED", "source text is empty or unavailable; no transcript was created"
        else:
            status, reason = "CAPTURED", None
        raw_spans = (_subtitle_cues(original) if fmt in {"srt", "vtt"} else _text_spans(original)) if status == "CAPTURED" else []
        if status == "CAPTURED" and not raw_spans:
            status, reason = "PARTIAL", "no subtitle cues could be parsed" if fmt in {"srt", "vtt"} else "no text spans could be extracted"

        source_data = {
            "title": str(payload.get("title") or "Untitled source"),
            "uri": payload.get("uri"),  # metadata only; this service never fetches URLs
            "format": fmt,
            "source_family": str(payload.get("source_family") or f"content:{_sha(original)}"),
            "author": payload.get("author"),
            "rights": rights,
            "status": status,
            "status_reason": reason,
            "content_hash": _sha(original),
            "input_hash": _input_hash(payload),
            "offset_unit": "unicode_codepoints",
        }
        if permitted:
            source_data["original_text"] = original
            source_data["text"] = original
        key = payload.get("idempotency_key")
        if key is not None and (not isinstance(key, str) or not key.strip()):
            raise ValidationError("idempotency_key must be a non-empty string")
        source = self.store.put("source", source_data, immutable=True, idempotency_key=key)

        # A blocked source is only a manifest: content hash and reason remain,
        # while the restricted bytes and all spans are omitted.
        if not permitted:
            return source
        existing_edges = self.store.edges(source["id"])
        linked_spans = {e.get("target_id") for e in existing_edges if e.get("source_id") == source["id"] and e.get("relation") == "HAS_SPAN"}
        for index, span in enumerate(raw_spans):
            data = {
                "source_id": source["id"],
                **span,
                "content_hash": _sha(span["text"]),
                "speaker": None,
                "speaker_uncertain": True,
                "offset_unit": "unicode_codepoints",
            }
            saved = self.store.put("span", data, immutable=True,
                                   idempotency_key=f"ingest:{source['id']}:span:{index}")
            if saved["id"] not in linked_spans:
                self.store.link(source["id"], saved["id"], "HAS_SPAN", data={"ordinal": index})
        return source

    def spans(self, source_id: str) -> list[dict[str, Any]]:
        source = self.store.get(source_id)  # preserve NotFound semantics
        rights = source.get("data", {}).get("rights", {})
        if (source.get("data", {}).get("status") in {"BLOCKED", "EXPIRED"}
                or not isinstance(rights, dict) or rights.get("allowed") is not True or _is_expired(rights)):
            return []
        return sorted(
            (r for r in self.store.list("span") if r.get("data", {}).get("source_id") == source_id),
            key=lambda r: (r["data"].get("start_char", 0), r["id"]),
        )

    def coverage(self, source_id: str) -> dict[str, Any]:
        source = self.store.get(source_id)
        spans = self.spans(source_id)
        rights = source.get("data", {}).get("rights", {})
        if (source.get("data", {}).get("status") in {"BLOCKED", "EXPIRED"}
                or not isinstance(rights, dict) or rights.get("allowed") is not True or _is_expired(rights)):
            return {"source_id": source_id, "status": "BLOCKED", "status_reason": "source is blocked or rights have expired",
                    "span_count": 0, "covered_characters": 0, "source_characters": 0,
                    "coverage_ratio": 0.0, "skipped_characters": 0,
                    "skipped_reason": "content is unavailable under current rights"}
        original = source["data"].get("original_text", "")
        covered_chars = sum(max(0, s["data"]["end_char"] - s["data"]["start_char"]) for s in spans)
        status = source["data"].get("status", "CAPTURED")
        return {
            "source_id": source_id,
            "status": status,
            "status_reason": source["data"].get("status_reason"),
            "span_count": len(spans),
            "covered_characters": covered_chars,
            "source_characters": len(original),
            "coverage_ratio": (covered_chars / len(original)) if original else 0.0,
            "skipped_characters": max(0, len(original) - covered_chars),
            "skipped_reason": "format markup, cue metadata, or whitespace outside exact spans" if covered_chars < len(original) else None,
        }
