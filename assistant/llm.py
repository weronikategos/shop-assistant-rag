"""Answer generation with Gemini: timeouts, retries and fallback models, plus token usage for monitoring."""
import time
from dataclasses import dataclass

import httpx
from google import genai
from google.genai import errors, types

from . import config

RETRY_CODES = (429, 500, 502, 503)  # worth another try on the same model
FALLBACK_CODES = (404, 429, 500, 502, 503, 504)  # move on to the next model
RETRY_DELAYS = (2, 4)  # seconds before the 2nd and 3rd attempt
REQUEST_TIMEOUT_MS = 60_000
BLOCKED_REASONS = {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "RECITATION"}


@dataclass
class Generation:
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0  # includes thinking tokens, which are billed as output
    attempts: int = 1
    blocked: bool = False


def make_client():
    """Reads the API key from GEMINI_API_KEY."""
    return genai.Client(http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS))


def _usage(response):
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return 0, 0
    output = (usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)
    return usage.prompt_token_count or 0, output


def _finish_reason(response):
    reason = response.candidates[0].finish_reason if response.candidates else None
    return getattr(reason, "name", reason)


class GeminiGenerator:
    def __init__(self, client=None, model=config.CHAT_MODEL, fallback_models=None, on_status=None):
        self.client = client or make_client()
        fallbacks = config.FALLBACK_MODELS if fallback_models is None else fallback_models
        self.models = [model] + [m for m in fallbacks if m != model]
        self.on_status = on_status or (lambda _message: None)

    def generate(self, system, prompt):
        attempts = 0
        for i, model in enumerate(self.models):
            try:
                result = self._generate_with(model, system, prompt)
                result.attempts += attempts
                return result
            except (errors.APIError, httpx.TransportError) as exc:
                attempts += getattr(exc, "attempts", 1)
                can_fall_back = not isinstance(exc, errors.APIError) or exc.code in FALLBACK_CODES
                if not can_fall_back or i == len(self.models) - 1:
                    raise
                self.on_status(f"[fallback] switching to {self.models[i + 1]}")

    def _generate_with(self, model, system, prompt):
        cfg = types.GenerateContentConfig(system_instruction=system, max_output_tokens=2048)
        for attempt, delay in enumerate((*RETRY_DELAYS, None), start=1):
            try:
                response = self.client.models.generate_content(model=model, contents=prompt, config=cfg)
                break
            except httpx.TimeoutException as exc:
                exc.attempts = attempt
                raise  # it already waited a full minute, so try the next model instead
            except errors.APIError as exc:
                if exc.code not in RETRY_CODES or delay is None:
                    exc.attempts = attempt
                    raise
                problem = f"busy ({exc.code})"
            except httpx.TransportError as exc:
                if delay is None:
                    exc.attempts = attempt
                    raise
                problem = "connection dropped"
            self.on_status(f"[retry] {model}: {problem}, retrying in {delay} s...")
            time.sleep(delay)

        input_tokens, output_tokens = _usage(response)
        if not response.candidates or _finish_reason(response) in BLOCKED_REASONS:
            return Generation("", model, input_tokens, output_tokens, attempt, blocked=True)
        return Generation((response.text or "").strip(), model, input_tokens, output_tokens, attempt)


def friendly_error(exc):
    """One readable line for an error that is still there after the retries and fallbacks."""
    if isinstance(exc, httpx.TransportError):
        return "Connection to the Gemini API was interrupted. Please try again."
    if exc.code in (502, 503, 504):
        return f"The model is busy right now ({exc.code}). Please try again in a minute."
    if exc.code == 429:
        return "The free-tier request limit is used up for now (429). Please try again later."
    if exc.code in (401, 403):
        return f"The API key was rejected ({exc.code}). Check GEMINI_API_KEY."
    return f"The Gemini API returned an error ({exc.code})."
