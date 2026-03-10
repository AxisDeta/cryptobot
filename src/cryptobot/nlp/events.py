from __future__ import annotations

import json
from typing import Protocol

from cryptobot.schemas import EventSignal, SentimentPost


class LLMClient(Protocol):
    def complete_json(self, prompt: str) -> str:
        ...


def build_event_prompt(post: SentimentPost) -> str:
    title = (post.title or "")[:280]
    body = (post.body or "")[:2000]
    return (
        "You are a crypto event classifier. Return ONLY valid JSON object with keys: sentiment, asset, event, horizon.\n"
        "Rules:\n"
        "- sentiment in [bullish, bearish, neutral]\n"
        "- event in [regulation, adoption, celebrity_influence, hack, liquidity, macro, other]\n"
        "- horizon in [short, medium, long]\n"
        "- asset should be ticker-like when possible (e.g., BTC, ETH, SOL), else UNKNOWN\n"
        "Input:\n"
        f"Title: {title}\n"
        f"Body: {body}\n"
    )


def _extract_json_object(text: str) -> str:
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        return text
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    raise ValueError("No JSON object found in LLM response")


def extract_event(post: SentimentPost, llm: LLMClient) -> EventSignal:
    payload = llm.complete_json(build_event_prompt(post))
    data = json.loads(_extract_json_object(payload))
    return EventSignal(
        sentiment=str(data.get("sentiment", "neutral")),
        asset=str(data.get("asset", "UNKNOWN")),
        event=str(data.get("event", "other")),
        horizon=str(data.get("horizon", "short")),
    )