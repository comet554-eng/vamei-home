"""大模型调用。只用标准库，支持 Anthropic 和 OpenAI 兼容接口（大赛提供的统一 API 多半是后者）。
配置全部来自环境变量或项目根目录的 .env，见 .env.example。没配置时 enabled=False，流程退回离线模板。"""
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class LLMError(Exception):
    pass


def load_env(path=ROOT / ".env"):
    """读 .env，已经在环境变量里的不覆盖。"""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


class LLM:
    def __init__(self):
        load_env()
        self.provider = os.environ.get("HA_LLM_PROVIDER", "mock").strip().lower()
        self.api_key = os.environ.get("HA_LLM_API_KEY", "").strip()
        self.model = os.environ.get("HA_LLM_MODEL", "").strip()
        self.base_url = os.environ.get("HA_LLM_BASE_URL", "").strip().rstrip("/")
        self.timeout = float(os.environ.get("HA_LLM_TIMEOUT", "60"))
        if self.provider == "anthropic":
            self.model = self.model or "claude-opus-5-5"
            self.base_url = self.base_url or "https://api.anthropic.com"
        elif self.provider == "openai":
            self.base_url = self.base_url or "https://api.openai.com/v1"
        self.enabled = self.provider in ("anthropic", "openai") and bool(self.api_key) and bool(self.model)

    def info(self):
        """给页面显示用，不含密钥。"""
        if not self.enabled:
            return {"mode": "mock", "detail": "未配置模型，使用离线模板"}
        return {"mode": "llm", "provider": self.provider, "model": self.model, "base_url": self.base_url}

    def _post(self, url, headers, body, retries=2):
        """429、5xx 和连接失败是临时错误，等一下再试；其余错误直接抛出。"""
        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json", **headers}, method="POST")
        for attempt in range(retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    return json.loads(r.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "replace")[:300]
                err, temporary = LLMError(f"HTTP {e.code}: {detail}"), e.code == 429 or e.code >= 500
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                err, temporary = LLMError(f"连接失败: {e}"), True
            except json.JSONDecodeError:
                err, temporary = LLMError("接口返回的不是 JSON"), False
            if not temporary or attempt == retries:
                raise err
            time.sleep(1.5 * (attempt + 1))

    def chat(self, system, user, max_tokens=2000):
        if not self.enabled:
            raise LLMError("未配置模型")
        if self.provider == "anthropic":
            data = self._post(f"{self.base_url}/v1/messages",
                              {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
                              {"model": self.model, "max_tokens": max_tokens, "system": system,
                               "messages": [{"role": "user", "content": user}]})
            parts = [c.get("text", "") for c in data.get("content", []) if c.get("type") == "text"]
            if not parts:
                raise LLMError("返回内容为空")
            return "".join(parts)
        data = self._post(f"{self.base_url}/chat/completions",
                          {"Authorization": f"Bearer {self.api_key}"},
                          {"model": self.model, "max_tokens": max_tokens, "temperature": 0.2,
                           "messages": [{"role": "system", "content": system},
                                        {"role": "user", "content": user}]})
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError("返回格式不对") from e

    def chat_json(self, system, user, max_tokens=2000, attempts=2):
        """要求模型返回 JSON 对象；解析失败重试一次，仍失败抛 LLMError。"""
        last = None
        for _ in range(attempts):
            text = self.chat(system, user, max_tokens)
            try:
                return extract_json(text)
            except ValueError as e:
                last = e
        raise LLMError(f"模型输出不是合法 JSON: {last}")


def extract_json(text):
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b <= a:
        raise ValueError("找不到 JSON 对象")
    try:
        obj = json.loads(text[a:b + 1])
    except json.JSONDecodeError as e:
        raise ValueError(str(e)) from e
    if not isinstance(obj, dict):
        raise ValueError("顶层不是对象")
    return obj
