"""Non-sensitive LLM settings, a write-only encrypted credential, and a model probe."""
from time import perf_counter
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from spectrumagent.agent import credential_store
from spectrumagent.agent.llm import (LLMError, LLMSettings, OpenAICompatibleClient, has_api_key,
                                     read_settings, restore_settings, set_api_key, write_settings)
from spectrumagent.api.project_paths import install_project_paths

BASE_URL_HINT = ("base_url 请填写服务商的 API 基地址（例如 https://api.siliconflow.cn/v1，以 /v1 结尾），"
                 "不要带 /chat/completions、查询参数或密钥；程序会自动拼接 /chat/completions。")
VERIFY_TIMEOUT_SECONDS = 10.0


class KeyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    key: SecretStr


class VerifyResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["available", "unavailable", "disabled", "unconfigured"]
    detail: str = Field(max_length=512)
    latency_ms: int | None = Field(default=None, ge=0)


def make_router(paths):
    database = paths.database
    router = APIRouter(prefix="/api/v1/settings", tags=["settings"])
    install_project_paths(router, paths)
    # Engine startup is the only restore point: a fresh process has an empty
    # in-memory container, so decrypt the saved key once into it. A key already
    # set in this process always wins (tests and in-process callers).
    if not has_api_key():
        restored = credential_store.load(paths.credential_root)
        if restored:
            set_api_key(restored)
    # A fresh session starts with pristine LLM settings; adopt the last saved
    # model configuration so the user never has to re-enter it after a restart.
    restore_settings(database, paths.credential_root)

    def current():
        return {**read_settings(database).model_dump(), "has_key": has_api_key()}

    @router.get("/llm")
    def get_llm():
        return current()

    @router.put("/llm")
    def put_llm(request: LLMSettings):
        write_settings(database, request, permanent_root=paths.credential_root)
        return current()

    @router.post("/llm/verify", response_model=VerifyResult)
    def verify_llm():
        """One real, minimal request so the panel can state whether the model works.

        Configured-save only: an incomplete configuration, a disabled egress
        switch or the common base_url mistake never reaches the provider. A
        completed probe is recorded in the ordinary llm_call audit trail.
        """
        settings = read_settings(database)
        if not settings.egress_enabled:
            return VerifyResult(status="disabled", detail="允许 LLM 外发已关闭，未发起验证请求。")
        missing = [name for name, value in (("base_url", settings.base_url), ("model", settings.model)) if not value]
        if not has_api_key():
            missing.append("API KEY")
        if missing:
            return VerifyResult(status="unconfigured", detail="尚未配置：" + "、".join(missing) + "。")
        if settings.base_url.rstrip("/").lower().endswith("/chat/completions"):
            return VerifyResult(status="unavailable", detail=BASE_URL_HINT + "当前地址会被重复拼接路径。")
        started = perf_counter()
        try:
            OpenAICompatibleClient(database, default_timeout=VERIFY_TIMEOUT_SECONDS).chat(
                [{"role": "user", "content": "ping"}], [])
        except LLMError as exc:
            # LLMError details are fixed, server-authored Chinese text only.
            return VerifyResult(status="unavailable", detail=str(exc)[:512])
        except OSError:
            return VerifyResult(status="unavailable", detail="本机验证请求未能完成，请检查网络后重试。")
        return VerifyResult(status="available", detail="模型可以正常使用。",
                            latency_ms=int((perf_counter() - started) * 1000))

    @router.put("/llm/key")
    def put_key(request: KeyRequest):
        key = request.key.get_secret_value()
        if key:
            # Persist before publishing to memory: has_key=true must mean the
            # key also survives a restart, not just this process.
            credential_store.save(paths.credential_root, key)
            set_api_key(key)
        else:
            credential_store.clear(paths.credential_root)
            set_api_key("")
        return {"has_key": has_api_key()}

    return router
