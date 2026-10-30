"""Client for the Gemini generateContent API.

Resilient by design, because the app breaks for everyone when this fails:
- Temporary failures (rate limits, overload, timeouts) are retried with backoff.
- If the configured model is retired (404) or keeps failing, the next model in
  GEMINI_FALLBACK_MODELS is tried.
- Everything happens within GEMINI_TIMEOUT_SECONDS, so the client gets an answer
  (or a clear error) before its own request times out.
"""
import json
import logging
import time

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}
ATTEMPTS_PER_MODEL = 2
BACKOFF_SECONDS = 1.0
BUSY_COOLDOWN_SECONDS = 60  # a model that just failed is tried last for a while...
GONE_COOLDOWN_SECONDS = 3600  # ...and a retired one for much longer

# model -> time.monotonic() until which it goes to the back of the queue (per process)
_cooldown = {}


class GeminiError(Exception):
    pass


def _models():
    """Configured models in preference order, with recently failing ones moved last."""
    primary = settings.GEMINI_MODEL
    ordered = [primary] + [m for m in settings.GEMINI_FALLBACK_MODELS if m != primary]
    now = time.monotonic()
    return sorted(ordered, key=lambda m: _cooldown.get(m, 0) > now)  # stable sort


def _error_detail(response):
    try:
        return response.json().get("error", {}).get("message", "")[:300]
    except ValueError:
        return response.text[:300]


def _extract_text(payload):
    """Join the text parts of the first candidate, skipping model 'thoughts'."""
    try:
        candidate = payload["candidates"][0]
    except (KeyError, IndexError, TypeError):
        if payload.get("promptFeedback", {}).get("blockReason"):
            raise GeminiError("The AI couldn't answer that. Try rephrasing the subject.")
        raise GeminiError("The AI service returned an unexpected response.")
    parts = (candidate.get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if isinstance(p, dict) and not p.get("thought"))
    if not text.strip():
        if candidate.get("finishReason") in ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST"):
            raise GeminiError("The AI couldn't answer that. Try rephrasing the subject.")
        raise GeminiError("The AI service returned an empty response.")
    return text.strip()


def generate(prompt, *, schema=None, timeout=30):
    """Return the model's text (a JSON string when `schema` is given)."""
    if not settings.GEMINI_API_KEY:
        raise GeminiError("The AI service isn't configured yet. Ask your administrator.")

    body = {"contents": [{"parts": [{"text": prompt}]}]}
    if schema:
        body["generationConfig"] = {"responseMimeType": "application/json", "responseSchema": schema}

    deadline = time.monotonic() + settings.GEMINI_TIMEOUT_SECONDS
    busy = False
    for model in _models():
        for attempt in range(ATTEMPTS_PER_MODEL):
            remaining = deadline - time.monotonic()
            if remaining < 2:
                break
            try:
                response = requests.post(
                    f"{API_ROOT}/{model}:generateContent",
                    json=body,
                    headers={"x-goog-api-key": settings.GEMINI_API_KEY},
                    timeout=min(timeout, remaining),
                )
            except requests.RequestException as exc:  # includes timeouts
                logger.warning("Gemini %s request failed (attempt %s): %s", model, attempt + 1, exc)
                busy = True
                continue

            if response.status_code == 200:
                _cooldown.pop(model, None)
                try:
                    return _extract_text(response.json())
                except ValueError:
                    raise GeminiError("The AI service returned an unexpected response.")

            detail = _error_detail(response)
            if response.status_code == 404:
                # Retired or unknown model: don't retry it, move to the next one.
                logger.error(
                    "Gemini model %r is unavailable (%s). Set GEMINI_MODEL to a current model.",
                    model,
                    detail,
                )
                _cooldown[model] = time.monotonic() + GONE_COOLDOWN_SECONDS
                break
            if response.status_code in RETRYABLE_STATUSES:
                logger.warning("Gemini %s busy (%s, attempt %s): %s", model, response.status_code, attempt + 1, detail)
                busy = True
                if attempt + 1 == ATTEMPTS_PER_MODEL:
                    _cooldown[model] = time.monotonic() + BUSY_COOLDOWN_SECONDS
                else:
                    time.sleep(min(BACKOFF_SECONDS * (attempt + 1), max(0, deadline - time.monotonic() - 2)))
                continue
            if response.status_code in (401, 403):
                logger.error("Gemini rejected the API key (%s): %s", response.status_code, detail)
                raise GeminiError("The AI service isn't available right now. Ask your administrator to check the API key.")
            logger.error("Gemini %s error %s: %s", model, response.status_code, detail)
            raise GeminiError("The AI service returned an error. Please try again.")

    if busy:
        raise GeminiError("The AI service is busy right now. Please try again in a moment.")
    raise GeminiError("No AI model is available. Ask your administrator to update GEMINI_MODEL.")


def generate_json(prompt, schema, **kwargs):
    text = generate(prompt, schema=schema, **kwargs)
    try:
        return json.loads(text)
    except ValueError:
        raise GeminiError("The AI service returned malformed data.")
