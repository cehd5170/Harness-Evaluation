from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _as_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def normalize_usage(usage: dict[str, Any]) -> dict[str, int]:
    prompt_details = usage.get("prompt_tokens_details") or {}
    input_details = usage.get("input_token_details") or {}
    cache_read_tokens = _as_int(
        usage.get("cache_read_input_tokens")
        or usage.get("cache_read_tokens")
        or usage.get("cacheRead")
        or usage.get("cached_input_tokens")
        or prompt_details.get("cached_tokens")
        or input_details.get("cache_read")
        or input_details.get("cached_tokens")
    )
    cache_write_tokens = _as_int(
        usage.get("cache_creation_input_tokens")
        or usage.get("cache_write_tokens")
        or usage.get("cacheWrite")
        or input_details.get("cache_creation")
        or input_details.get("cache_write")
    )
    raw_input_tokens = _as_int(
        usage.get("prompt_tokens")
        or usage.get("input_tokens")
        or usage.get("input")
    )
    output_tokens = _as_int(
        usage.get("completion_tokens")
        or usage.get("output_tokens")
        or usage.get("output")
    )
    total_tokens = _as_int(
        usage.get("total_tokens")
        or usage.get("totalTokens")
        or (raw_input_tokens + output_tokens)
    )
    input_tokens = raw_input_tokens - cache_read_tokens
    if input_tokens < 0:
        input_tokens = raw_input_tokens
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read_tokens": cache_read_tokens,
        "cache_write_tokens": cache_write_tokens,
        "total_tokens": total_tokens,
        "reasoning_output_tokens": _as_int(usage.get("reasoning_output_tokens")),
    }


@dataclass
class UsageTotals:
    source: str = ""
    usage_message_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    total_tokens: int = 0
    reasoning_output_tokens: int = 0
    cost_input: float = 0.0
    cost_output: float = 0.0
    cost_cache_read: float = 0.0
    cost_cache_write: float = 0.0
    cost_total: float = 0.0
    models: set[str] = field(default_factory=set)
    providers: set[str] = field(default_factory=set)

    def add(self, usage: dict[str, Any], *, source: str, model: str = "", provider: str = "") -> None:
        normalized = normalize_usage(usage)
        if normalized["total_tokens"] <= 0:
            return
        self.source = self.source or source
        self.usage_message_count += 1
        self.input_tokens += normalized["input_tokens"]
        self.output_tokens += normalized["output_tokens"]
        self.cache_read_tokens += normalized["cache_read_tokens"]
        self.cache_write_tokens += normalized["cache_write_tokens"]
        self.total_tokens += normalized["total_tokens"]
        self.reasoning_output_tokens += normalized["reasoning_output_tokens"]
        cost = usage.get("cost")
        if isinstance(cost, dict):
            self.cost_input += _as_float(cost.get("input"))
            self.cost_output += _as_float(cost.get("output"))
            self.cost_cache_read += _as_float(cost.get("cacheRead") or cost.get("cache_read"))
            self.cost_cache_write += _as_float(cost.get("cacheWrite") or cost.get("cache_write"))
            self.cost_total += _as_float(cost.get("total"))
        else:
            self.cost_total += _as_float(usage.get("total_cost_usd") or usage.get("cost_usd"))
        if model:
            self.models.add(model)
        if provider:
            self.providers.add(provider)

    def summary(self, *, source: str | None = None) -> dict[str, Any]:
        return {
            "available": self.usage_message_count > 0,
            "source": source or self.source,
            "usage_message_count": self.usage_message_count,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "total_tokens": self.total_tokens,
            "reasoning_output_tokens": self.reasoning_output_tokens,
            "cost_input": round(self.cost_input, 8),
            "cost_output": round(self.cost_output, 8),
            "cost_cache_read": round(self.cost_cache_read, 8),
            "cost_cache_write": round(self.cost_cache_write, 8),
            "cost_total": round(self.cost_total, 8),
            "models": sorted(self.models),
            "providers": sorted(self.providers),
        }


def _json_objects_from_text(text: str) -> Iterable[dict[str, Any]]:
    stripped = text.strip()
    if not stripped:
        return
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            yield parsed
        elif isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, dict):
                    yield item
        return
    except json.JSONDecodeError:
        pass
    for line in stripped.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            yield parsed


def _usage_candidates(obj: dict[str, Any]) -> Iterable[tuple[dict[str, Any], str, str]]:
    payload = obj.get("payload")
    if isinstance(payload, dict):
        info = payload.get("info")
        if payload.get("type") == "token_count" and isinstance(info, dict):
            total = info.get("total_token_usage")
            if isinstance(total, dict):
                yield total, "", "codex"
            elif isinstance(info.get("last_token_usage"), dict):
                yield info["last_token_usage"], "", "codex"

    usage = obj.get("usage")
    if isinstance(usage, dict):
        yield usage, str(obj.get("model") or ""), str(obj.get("provider") or "")

    message = obj.get("message")
    if isinstance(message, dict) and isinstance(message.get("usage"), dict):
        yield message["usage"], str(message.get("model") or obj.get("model") or ""), str(message.get("provider") or obj.get("provider") or "")

    result = obj.get("result")
    if isinstance(result, dict) and isinstance(result.get("usage"), dict):
        yield result["usage"], str(result.get("model") or obj.get("model") or ""), str(result.get("provider") or obj.get("provider") or "")

    if any(key in obj for key in ("input_tokens", "output_tokens", "total_tokens", "total_cost_usd", "cost_usd")):
        yield obj, str(obj.get("model") or ""), str(obj.get("provider") or "")


def summarize_usage_text(text: str, *, source: str) -> dict[str, Any] | None:
    totals = UsageTotals(source=source)
    for obj in _json_objects_from_text(text):
        for usage, model, provider in _usage_candidates(obj):
            totals.add(usage, source=source, model=model, provider=provider)
    if totals.usage_message_count == 0:
        return None
    return totals.summary()


def summarize_usage_file(path: Path) -> dict[str, Any] | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    summary = summarize_usage_text(text, source=f"file:{path}")
    if summary is not None:
        summary["usage_file"] = str(path)
    return summary


def apply_pricing(summary: dict[str, Any], pricing: dict[str, Any] | None) -> dict[str, Any]:
    if not pricing or summary.get("cost_total"):
        return summary
    per_million = pricing.get("per_million_tokens") if isinstance(pricing.get("per_million_tokens"), dict) else pricing
    input_price = _as_float(per_million.get("input"))
    output_price = _as_float(per_million.get("output"))
    cache_read_price = _as_float(per_million.get("cache_read"))
    cache_write_price = _as_float(per_million.get("cache_write"))
    cost_input = summary.get("input_tokens", 0) * input_price / 1_000_000
    cost_output = summary.get("output_tokens", 0) * output_price / 1_000_000
    cost_cache_read = summary.get("cache_read_tokens", 0) * cache_read_price / 1_000_000
    cost_cache_write = summary.get("cache_write_tokens", 0) * cache_write_price / 1_000_000
    summary["cost_input"] = round(cost_input, 8)
    summary["cost_output"] = round(cost_output, 8)
    summary["cost_cache_read"] = round(cost_cache_read, 8)
    summary["cost_cache_write"] = round(cost_cache_write, 8)
    summary["cost_total"] = round(cost_input + cost_output + cost_cache_read + cost_cache_write, 8)
    summary["cost_source"] = "pricing.per_million_tokens"
    return summary
