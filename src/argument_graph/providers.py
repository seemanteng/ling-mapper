"""Model callers for providers other than Anthropic, with the same contract as `AnthropicCaller`.

A caller is `caller(system, messages, schema) -> (data, content_for_history, log)`: one
structured-output request, `data` the parsed JSON (None if unusable), `content_for_history` what
goes back into an assistant turn on a retry, and `log` with at least `stop_reason` and `usage`
(`input_tokens`, `output_tokens`). Messages are `{"role", "content"}` with string content for
every provider except Anthropic. Nothing here is tuned per vendor beyond what the API requires,
so the prompt, schemas and retry loop stay identical across models.
"""
import json
import os
import re
import time
from pathlib import Path

# provider -> (environment variable holding the key, base URL or None for the default)
OPENAI_COMPATIBLE = {
    "openai": ("OPENAI_API_KEY", None),
    "huggingface": ("HF_TOKEN", "https://router.huggingface.co/v1"),
}


def load_env(path=".env"):
    """Read KEY=VALUE lines into os.environ without overriding variables that are already set."""
    file = Path(path)
    if not file.exists():
        return
    for line in file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)


TRANSIENT_STATUS = {408, 409, 429, 500, 502, 503, 504}


def is_transient(exc):
    """A provider hiccup worth retrying (busy, timeout, dropped connection), not a quota or credit error."""
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    message = str(exc).lower()
    if "quota" in message or "credit" in message or status == 402:
        return False
    if isinstance(status, int):
        return status in TRANSIENT_STATUS
    return any(w in type(exc).__name__ for w in ("Connection", "Timeout"))


def with_backoff(call, tries=6, base=5.0, sleep=time.sleep):
    """Run `call()`, retrying transient provider errors with exponential backoff (5, 10, 20, ... s)."""
    for attempt in range(tries):
        try:
            return call()
        except Exception as exc:
            if attempt == tries - 1 or not is_transient(exc):
                raise
            sleep(base * 2 ** attempt)


def parse_json(text):
    """Parse a model's JSON answer; tolerate a leading <think> block. Returns (data, error)."""
    if not text:
        return None, "empty output"
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    try:
        return json.loads(cleaned), None
    except json.JSONDecodeError as exc:
        return None, f"invalid_json: {exc}"


class OpenAICaller:
    """Chat Completions with a strict JSON-schema response format. Serves OpenAI itself and any
    OpenAI-compatible router (Hugging Face for Qwen). `effort` is sent as `reasoning_effort`; the
    Cerebras host of Qwen accepts it, and without it Qwen can think past the host's output cap."""

    def __init__(self, model, effort="high", provider="openai"):
        from openai import OpenAI
        key_env, base_url = OPENAI_COMPATIBLE[provider]
        if not os.environ.get(key_env):
            raise SystemExit(f"{key_env} is not set (put it in .env)")
        self.client = OpenAI(api_key=os.environ[key_env], base_url=base_url)
        self.model, self.effort, self.provider = model, effort, provider

    def __call__(self, system, messages, schema):
        started = time.time()
        request = dict(
            model=self.model, messages=[{"role": "system", "content": system}] + messages,
            response_format={"type": "json_schema", "json_schema": {"name": "answer", "schema": schema, "strict": True}})
        if self.effort in ("low", "medium", "high", "xhigh"):
            request["reasoning_effort"] = self.effort
        # Streamed, so a slow reasoning model does not hit a gateway timeout on one long response.
        def consume():
            parts, finish, usage, model, request_id = [], None, None, self.model, None
            stream = self.client.chat.completions.create(stream=True, stream_options={"include_usage": True}, **request)
            for chunk in stream:
                request_id, model = chunk.id or request_id, chunk.model or model
                usage = chunk.usage or usage
                for choice in chunk.choices:
                    parts.append(choice.delta.content or "")
                    finish = choice.finish_reason or finish
            return parts, finish, usage, model, request_id
        parts, finish, usage, model, request_id = with_backoff(consume)
        text = "".join(parts)
        log = {"request_id": request_id, "model": model, "stop_reason": finish,
               "usage": {"input_tokens": getattr(usage, "prompt_tokens", 0) or 0,
                         "output_tokens": getattr(usage, "completion_tokens", 0) or 0},
               "seconds": round(time.time() - started, 1), "response": {"content": text}}
        if finish != "stop":
            return None, text, log
        data, error = parse_json(text)
        if error:
            log["stop_reason"] = error
        return data, text, log


class GeminiCaller:
    """Gemini via google-genai with a JSON-schema response. `effort` maps to the thinking level."""

    LEVELS = {"low": "LOW", "medium": "MEDIUM", "high": "HIGH", "xhigh": "HIGH", "max": "HIGH"}

    def __init__(self, model, effort="high"):
        from google import genai
        if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
            raise SystemExit("GEMINI_API_KEY is not set (put it in .env)")
        self.client = genai.Client()
        self.model, self.effort = model, effort

    def __call__(self, system, messages, schema):
        from google.genai import types
        started = time.time()
        contents = [types.Content(role="model" if m["role"] == "assistant" else "user",
                                  parts=[types.Part(text=m["content"])]) for m in messages]
        config = types.GenerateContentConfig(
            system_instruction=system, response_mime_type="application/json", response_json_schema=schema,
            thinking_config=types.ThinkingConfig(thinking_level=self.LEVELS[self.effort]))
        response = with_backoff(lambda: self.client.models.generate_content(model=self.model, contents=contents, config=config))
        usage = response.usage_metadata
        candidate = response.candidates[0] if response.candidates else None
        reason = getattr(getattr(candidate, "finish_reason", None), "name", None) or "no_candidate"
        log = {"request_id": getattr(response, "response_id", None), "model": getattr(response, "model_version", self.model),
               "stop_reason": reason,
               "usage": {"input_tokens": getattr(usage, "prompt_token_count", 0) or 0,
                         # thinking tokens are billed as output
                         "output_tokens": (getattr(usage, "candidates_token_count", 0) or 0)
                         + (getattr(usage, "thoughts_token_count", 0) or 0)},
               "seconds": round(time.time() - started, 1), "response": response.model_dump(mode="json")}
        text = response.text if candidate else None
        if reason != "STOP":
            return None, text, log
        data, error = parse_json(text)
        if error:
            log["stop_reason"] = error
        return data, text, log


def make_caller(provider, model, effort):
    """Caller for `provider` (anthropic, openai, gemini, huggingface); loads .env first."""
    load_env()
    if provider == "anthropic":
        from .student_graph import AnthropicCaller
        return AnthropicCaller(model, effort)
    if provider in OPENAI_COMPATIBLE:
        return OpenAICaller(model, effort, provider)
    if provider == "gemini":
        return GeminiCaller(model, effort)
    raise SystemExit(f"Unknown provider {provider!r}")
