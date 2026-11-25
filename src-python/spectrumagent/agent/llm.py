"""G1 gateway: OpenAI-compatible HTTP, egress backstop, content-free audit.

Callers must rebuild context from the TASK-07 §2.3 whitelist (ids, class codes,
metric numbers and tool names). This deny scan is a fallback, not the primary
boundary. Tool/context construction belongs to 12.2, outside this module.
"""
from abc import ABC, abstractmethod
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
import re
from time import perf_counter_ns
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator

from backend.database import connect_database
from .open_access import OPEN_ACCESS
from spectrumagent.data import DataError
from .migrations import SETTING_KEYS
from .execution import RequestCancelled


@dataclass(repr=False)
class _Credentials:
    key: str = field(default="", repr=False)


# Process memory only. Never serialize this container or include it in logs.
# The encrypted-at-rest copy lives in credential_store and is restored once at
# engine startup by api/settings.py; this container stays the sole runtime holder.
_credentials = _Credentials()


def set_api_key(key: str) -> None:
    _credentials.key = key


def has_api_key() -> bool:
    return bool(_credentials.key)


class LLMSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    base_url: StrictStr = ""
    model: StrictStr = ""
    router_model: StrictStr = ""
    temperature: StrictStr = ""
    max_tokens: StrictStr = ""
    timeout_ms: StrictStr = ""
    egress_enabled: bool = True

    @field_validator("egress_enabled", mode="before")
    @classmethod
    def egress_switch(cls, value):
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value in {"1", "0"}:
            return value == "1"
        raise ValueError("egress_enabled must be a boolean or the string 1/0")

    @field_validator("base_url")
    @classmethod
    def valid_url(cls, value):
        if value:
            url = httpx.URL(value)
            if (url.scheme not in {"http", "https"} or not url.host
                    or url.userinfo or url.query or url.fragment):
                raise ValueError("base_url must be an HTTP(S) base without credentials/query/fragment")
        return value

    @field_validator("temperature", "max_tokens", "timeout_ms", mode="before")
    @classmethod
    def numeric_setting(cls, value, info):
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            raise ValueError("numeric setting or empty string required")
        if value == "":
            return value
        text = str(value)
        if info.field_name == "temperature":
            if not math.isfinite(float(text)):
                raise ValueError("finite temperature required")
        elif int(text) <= 0:
            raise ValueError("positive integer required")
        return text


def read_settings(database: Path) -> LLMSettings:
    with connect_database(database) as db:
        values = dict(db.execute("SELECT key,value FROM llm_settings"))
    return LLMSettings(**{key: values[key] for key in SETTING_KEYS})


def _write_database(database: Path, settings: LLMSettings) -> None:
    with connect_database(database) as db:
        db.executemany("UPDATE llm_settings SET value=? WHERE key=?",
                       [(("1" if value else "0") if key == "egress_enabled" else value, key)
                        for key, value in settings.model_dump().items()])


def write_settings(database: Path, settings: LLMSettings, *, permanent_root: Path | None = None) -> None:
    """Publish settings to the session DB and snapshot them to the permanent root.

    Persisting first keeps the same guarantee as the API key: a successful save
    means the configuration really survives a restart. Every writer (settings
    panel, the settings.llm_set tool, tests) goes through this single function.
    """
    from . import settings_store
    root = permanent_root or settings_store.root_from_database(database)
    settings_store.save(root, settings.model_dump())
    _write_database(database, settings)


def restore_settings(database: Path, permanent_root: Path | None = None) -> bool:
    """Restore the saved model configuration into a fresh session's empty DB.

    Values explicitly configured in this session always win; a restart starts
    from the pristine defaults and therefore adopts the snapshot. Returns
    whether a snapshot was applied.
    """
    from . import settings_store
    from pydantic import ValidationError
    root = permanent_root or settings_store.root_from_database(database)
    values = settings_store.load(root)
    if values is None:
        return False
    try:
        saved = LLMSettings.model_validate(values)
    except ValidationError:
        return False
    if read_settings(database) != LLMSettings():
        return False
    _write_database(database, saved)
    return True


class ToolCall(BaseModel):
    id: str
    name: str
    arguments_json: str


class Usage(BaseModel):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class ChatResult(BaseModel):
    content: str | None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    usage: Usage | None = None
    finish_reason: str | None


class LLMError(DataError):
    def __init__(self, code: str, status: str, detail=None):
        super().__init__(code, detail or code)
        self.status = status


class LLMClient(ABC):
    @abstractmethod
    def chat(self, messages, tools, *, stream=False) -> ChatResult:
        """Return a complete result or a distinguishable, audited LLMError."""


def _json(value):
    # Reproducible prompt digest, independent of dictionary insertion order.
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


_DENY_TEXT = re.compile(r"[a-z]:|\\|/[^\s/]+|\.(?:img|hdr|mat)\b|\blabel_map\b", re.I)
_NESTED_ARRAY = re.compile(r"\[\s*\[")
ABSOLUTE_FRAGMENT = re.compile(r"""(?i)["“‘'](?:[a-z]:[\\/]|[\\/])[^"”’'\r\n]+["”’']|"""
                               r"""(?:(?<![a-z0-9_])[a-z]:[\\/]|\\\\|(?<![\w:/])\/)[^\r\n，,。；;、！？!?]+""")


def _hide_user_paths(messages):
    return [
        {**message, "content": ABSOLUTE_FRAGMENT.sub(" 本地输入源 ", message["content"])}
        if message.get("role") == "user" and isinstance(message.get("content"), str) else message
        for message in messages
    ]


def _redact_assistant_paths(messages):
    """Remove whole assistant text: path markers cannot delimit the full path."""
    if OPEN_ACCESS:
        return messages
    safe = []
    for message in messages:
        message = dict(message)
        if message.get('role')=='assistant' and isinstance(message.get('content'),str):
            # Closed public notations are prose, not a location. Never match
            # a component inside an absolute/relative path or a filename.
            edges=r'A-Za-z0-9_./\\:'
            message['content']=re.sub(r'(?<!['+edges+r'])(?:PE|PET|PP)(?:/(?:PE|PET|PP))+(?!['+edges+r'])',
                                      lambda match:match[0].replace('/','、'),message['content'])
            message['content']=re.sub(r'(?<!['+edges+r'])(?:分割就绪|已核验|已核对|已完成|进度)\s*\d+/\d+(?!['+edges+r'])',
                                      lambda match:match[0].replace('/','／'),message['content'])
        if (message.get("role") == "assistant" and isinstance(message.get("content"), str)
                and _DENY_TEXT.search(message["content"])):
            message["content"] = "[路径已隐藏]"
        safe.append(message)
    return safe


def _egress_blocked(value):
    # Scan original strings so JSON's escaped newlines aren't mistaken for
    # literal backslashes. Scan serialized context too, including stringified
    # coordinate arrays, whitespace variants and tool arguments/schemas.
    if OPEN_ACCESS:
        return bool(_NESTED_ARRAY.search(_json(value)))
    def forbidden(item):
        if isinstance(item, str):
            return bool(_DENY_TEXT.search(item))
        if isinstance(item, dict):
            return any(forbidden(k) or forbidden(v) for k, v in item.items())
        if isinstance(item, list):
            return any(forbidden(v) for v in item)
        return False
    return forbidden(value) or bool(_NESTED_ARRAY.search(_json(value)))


def _parse_result(body):
    if not isinstance(body, dict) or not isinstance(body.get("choices"), list) or not body["choices"]:
        raise ValueError("invalid choices")
    choice = body["choices"][0]
    if not isinstance(choice, dict) or not isinstance(choice.get("message"), dict):
        raise ValueError("invalid message")
    message = choice["message"]
    return ChatResult(
        content=message.get("content"), finish_reason=choice.get("finish_reason"),
        tool_calls=[ToolCall(id=call["id"], name=call["function"]["name"],
                             arguments_json=call["function"]["arguments"])
                    for call in (message.get("tool_calls") or [])],
        usage=Usage(**body["usage"]) if body.get("usage") is not None else None,
    )


def validate_tool_response(result):
    """Never execute tool-looking prose or a truncated tool response."""
    if result.finish_reason in {"length", "max_tokens"}:
        raise LLMError("LLM_OUTPUT_TRUNCATED", "http_error", "模型输出达到长度上限，请提高输出上限后重试")
    if (re.search(r"<[^>]*(?:DSML|tool_calls?|invoke)\b", result.content or "", re.I)
            or result.finish_reason == "tool_calls" and not result.tool_calls
            or len({call.id for call in result.tool_calls}) != len(result.tool_calls)):
        raise LLMError("LLM_TOOL_PROTOCOL", "http_error", "模型未返回有效的原生工具调用，请检查模型的工具调用兼容性")


def _workflow_wire(messages, tools):
    """Use portable function names at the provider boundary, retain domain names locally."""
    if not any(tool['function']['name'] == 'annotations.prepare'
               or tool['function']['name'].startswith('experiments.') for tool in tools or []):
        return messages, tools, {}
    mapping = {tool["function"]["name"]: "sa_" + tool["function"]["name"].replace(".", "__") for tool in tools}
    if len(set(mapping.values())) != len(mapping):
        raise LLMError("LLM_TOOL_PROTOCOL", "http_error")
    wire_tools = [{**tool, "function": {**tool["function"], "name": mapping[tool["function"]["name"]]}} for tool in tools]
    wire_messages = []
    for message in messages:
        item = dict(message)
        if "tool_calls" in item:
            item["tool_calls"] = [{**call, "function": {**call["function"],
                                  "name": mapping.get(call["function"]["name"], call["function"]["name"])}}
                                 for call in item["tool_calls"]]
        wire_messages.append(item)
    return wire_messages, wire_tools, {wire: name for name, wire in mapping.items()}


def _parse_stream(response):
    content, calls, finish, usage = [], {}, None, None
    saw_content = False
    finished = False
    for line in response.iter_lines():
        if not line.startswith("data:"):
            continue
        data = line[len("data:"):].strip()
        if data == "[DONE]":
            finished = True
            break
        body = json.loads(data)
        if body.get("usage") is not None:
            usage = Usage(**body["usage"])
        for choice in body.get("choices", []):
            if choice["index"] != 0:
                continue
            delta = choice.get("delta", {})
            if delta.get("content") is not None:
                content.append(delta["content"])
                saw_content = True
            for call in delta.get("tool_calls", []):
                accumulated = calls.setdefault(call["index"], {"id": "", "name": "", "arguments_json": ""})
                accumulated["id"] += call.get("id", "")
                accumulated["name"] += call.get("function", {}).get("name", "")
                accumulated["arguments_json"] += call.get("function", {}).get("arguments", "")
            if choice.get("finish_reason") is not None:
                finish = choice["finish_reason"]
    if not finished:
        raise ValueError("incomplete stream")
    return ChatResult(content="".join(content) if saw_content else None,
                      tool_calls=[ToolCall(**calls[i]) for i in sorted(calls)],
                      usage=usage, finish_reason=finish)


class OpenAICompatibleClient(LLMClient):
    def __init__(self, database: Path, *, transport: httpx.BaseTransport | None = None,
                 session_id: str | None = None, default_timeout: float | None = None):
        self.database = database
        self.transport = transport  # httpx.MockTransport injection: no tokens/network.
        self.session_id = session_id
        # Only used when timeout_ms is blank. The settings verification probe
        # supplies a bounded value so an unconfigured timeout cannot hang the UI.
        self.default_timeout = default_timeout

    def chat_cancellable(self, messages, tools, control):
        return self.chat(messages, tools, control=control)

    def route_chat(self, messages, control=None):
        settings = read_settings(self.database)
        if not settings.egress_enabled or not settings.base_url or not settings.model:
            return None
        return self.chat(messages, [], control=control, model=settings.router_model or settings.model,
                         temperature=0, max_tokens=128, timeout_cap=8.)

    def chat(self, messages, tools, *, stream=False, control=None, model=None,
             temperature=None, max_tokens=None, timeout_cap=None) -> ChatResult:
        started = perf_counter_ns()
        audit_id = str(uuid4())
        self.last_audit_id = audit_id
        # Preserve raw array rejection even when assistant text is redacted.
        nested = bool(_NESTED_ARRAY.search(_json({"messages": messages, "tools": tools})))
        messages = _redact_assistant_paths(_hide_user_paths(messages))
        digest = sha256(_json(messages).encode("utf-8")).hexdigest()
        settings = read_settings(self.database)
        actual_model = model or settings.model
        names = [tool["function"]["name"] for tool in (tools or [])]
        usage = None
        http_status, error_stage = None, None
        status, error = "http_error", "LLM_HTTP"
        try:
            if not settings.egress_enabled:
                raise LLMError("LLM_EGRESS_DISABLED", "blocked")
            if nested:
                raise LLMError("EGRESS_BLOCKED", "blocked")
            if _egress_blocked({"messages": messages, "tools": tools}):
                raise LLMError("EGRESS_BLOCKED", "blocked")
            if not settings.base_url or not actual_model:
                raise LLMError("LLM_NOT_CONFIGURED", "http_error")
            wire_messages, wire_tools, reverse_names = _workflow_wire(messages, tools)
            payload = {"model": actual_model, "messages": wire_messages, "stream": stream}
            if wire_tools:
                payload["tools"] = wire_tools
            if temperature is not None or settings.temperature != "":
                payload["temperature"] = temperature if temperature is not None else float(settings.temperature)
            if max_tokens is not None or settings.max_tokens != "":
                payload["max_tokens"] = max_tokens if max_tokens is not None else int(settings.max_tokens)
            if stream:
                payload["stream_options"] = {"include_usage": True}
            # Empty timeout is explicitly unconfigured, not an invented number.
            # A caller may supply a bounded default for its own probe request.
            timeout = (int(settings.timeout_ms) / 1000 if settings.timeout_ms != ""
                       else self.default_timeout)
            if timeout_cap is not None:
                timeout = min(timeout,timeout_cap) if timeout is not None else timeout_cap
            headers = {"Authorization": "Bearer " + _credentials.key} if _credentials.key else {}
            if control is not None and not stream:
                bounded_timeout = timeout if timeout is not None else 300
                async def request():
                    nonlocal http_status
                    async with httpx.AsyncClient(transport=self.transport, timeout=bounded_timeout, trust_env=False,
                                                 follow_redirects=False) as client:
                        response = await client.post(settings.base_url.rstrip('/') + '/chat/completions',
                                                     json=payload, headers=headers)
                        http_status = response.status_code
                        response.raise_for_status()
                        return _parse_result(response.json())
                async def bounded_request():
                    return await asyncio.wait_for(control.wait_for(request()), timeout=bounded_timeout)
                result = asyncio.run(bounded_request())
            else:
                with httpx.Client(transport=self.transport, timeout=timeout, trust_env=False,
                              follow_redirects=False) as client:
                    with client.stream("POST", settings.base_url.rstrip("/") + "/chat/completions",
                                   json=payload, headers=headers) as response:
                        http_status = response.status_code
                        response.raise_for_status()
                        if stream:
                            result = _parse_stream(response)
                        else:
                            response.read()
                            result = _parse_result(response.json())
            result.tool_calls = [call.model_copy(update={"name": reverse_names.get(call.name, call.name)}) for call in result.tool_calls]
            validate_tool_response(result)
            usage = result.usage
            status, error = "ok", None
            return result
        except RequestCancelled:
            status, error, error_stage = 'transport_error', 'REQUEST_INTERRUPTED', 'transport'
            raise
        except TimeoutError:
            status, error, error_stage = 'transport_error', 'LLM_TRANSPORT', 'transport'
            raise LLMError(error, status, '模型请求超时，请重试') from None
        except LLMError as exc:
            status, error = exc.status, exc.code
            error_stage = "protocol" if exc.code in {"LLM_TOOL_PROTOCOL", "LLM_OUTPUT_TRUNCATED"} else "configuration"
            raise
        except httpx.TransportError:
            status, error = "transport_error", "LLM_TRANSPORT"
            error_stage = "transport"
            raise LLMError(error, status) from None
        except httpx.HTTPStatusError:
            status, error, error_stage = "http_error", "LLM_HTTP", "http"
            explanation = ("模型服务鉴权失败，请检查密钥" if http_status in {401, 403} else
                           "模型服务限流，请稍后重试" if http_status == 429 else
                           "模型服务暂时不可用" if http_status is not None and http_status >= 500 else
                           "模型服务拒绝请求，请检查模型与工具调用配置")
            raise LLMError(error, status, f"{explanation}（HTTP {http_status}）") from None
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError, AttributeError):
            # Never persist provider bodies, exception text, messages or headers.
            status, error = "http_error", "LLM_HTTP"
            error_stage = "response"
            raise LLMError(error, status, "模型响应格式不符合工具调用接口，请检查服务兼容性") from None
        finally:
            elapsed = (perf_counter_ns() - started) // 1_000_000
            with connect_database(self.database) as db:
                db.execute("INSERT INTO llm_call "
                           "(id,session_id,model,prompt_sha256,tool_names,prompt_tokens,completion_tokens,"
                           "total_tokens,latency_ms,status,error,created_at,http_status,error_stage) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                           (audit_id, self.session_id, actual_model, digest,
                            _json(names) if names else None,
                            usage.prompt_tokens if usage else None,
                            usage.completion_tokens if usage else None,
                            usage.total_tokens if usage else None,
                            elapsed, status, error, datetime.now(timezone.utc).isoformat(), http_status, error_stage))
