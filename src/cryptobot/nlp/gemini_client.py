from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from cryptobot.nlp.events import LLMClient


class GeminiJSONClient(LLMClient):
    """Gemini client with SDK-first JSON mode and REST fallback."""

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash") -> None:
        self.api_key = api_key
        self.model = model

    def _sdk_complete(self, prompt: str) -> str:
        import google.generativeai as genai  # type: ignore

        genai.configure(api_key=self.api_key)
        model = genai.GenerativeModel(self.model)
        response = model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.1,
                "response_mime_type": "application/json",
            },
        )
        text = getattr(response, "text", None)
        if not text:
            raise RuntimeError("Empty response from Gemini SDK")
        return str(text)

    def _rest_complete(self, prompt: str) -> str:
        encoded_model = urllib.parse.quote(self.model, safe="")
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{encoded_model}:generateContent"
            f"?key={urllib.parse.quote(self.api_key, safe='')}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
            },
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=25) as response:
            body = json.loads(response.read().decode("utf-8"))
        return body["candidates"][0]["content"]["parts"][0]["text"]

    def complete_json(self, prompt: str) -> str:
        if not self.api_key:
            raise RuntimeError("Missing GEMINI_API_KEY")

        try:
            return self._sdk_complete(prompt)
        except Exception:
            try:
                return self._rest_complete(prompt)
            except urllib.error.URLError as exc:  # pragma: no cover
                raise RuntimeError(f"Gemini request failed: {exc}") from exc