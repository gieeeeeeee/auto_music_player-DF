"""乐谱识别:图片/文档 -> 规范化简谱文本。

设计为可插拔接口:
- StubRecognizer:内置样例,用于跑通全流程,不依赖真实 API(默认)
- OpenAIStyleRecognizer:兼容 OpenAI 协议的多模态接口,
  通义千问VL / GLM-4V / Kimi / OpenAI 等平台均可用,只需填 api_base/api_key/model

工程细节:
- 图片发送前自动等比压缩(长边 1600px、JPEG q85),避免大图上传/推理超时
- 使用流式响应(stream),长推理期间数据持续到达,不会触发读超时
- 网络错误转成可读的中文提示,HTTP 错误会透出服务端返回的原始信息
"""

import base64
import io
import json
import os
from abc import ABC, abstractmethod

import requests
from PIL import Image

CONNECT_TIMEOUT = 15    # 建连超时(秒)
READ_TIMEOUT = 300      # 流式块间最长等待(秒)
IMAGE_MAX_SIDE = 1600   # 图片长边上限,超出则等比压缩
JPEG_QUALITY = 85

# 大模型输出协议:让模型把任意简谱转成规范化文本
JIANPU_PROMPT = """你是一位简谱识别专家。请把输入的乐谱内容转成以下严格格式的简谱文本:

规则:
1. 音高:中音用数字 1-7;高音在数字后加英文单引号 ' (如 5');低音在数字后加英文逗号 , (如 5,);休止符用 0
2. 时值:不加符号=四分音符;数字后跟一个下划线 _ = 八分音符,两个 __ = 十六分音符;跟一个减号 - = 二分音符,两个 -- = 全音符;附点用 · 加在时值符号后(如 5_· 是附点八分音符)
3. 和弦:多个同时演奏的音用方括号括起、空格分隔,时值符号加在右括号后(如 [1' 3' 5']- 是二分和弦);和弦内的音只写音高不写时值
4. 每个音符(或和弦)之间用空格分隔
5. 小节线、调号(如 1=C)、拍号、歌词、装饰音符号、力度记号全部丢弃,只输出音符序列
6. 只输出简谱本身,不要输出任何解释文字,不要用代码块包裹

示例输入(图片或文字):[简谱]
示例输出:1 1 5 5 6 6 5- 4 4 3 3 2 2 1-
"""

SAMPLE_JIANPU = "1 1 5, 5, 6 6 5'- 4 4 3 3 2 2 1- 0 0 [1' 3' 5']- 1 2 3_ 3_ 5_· 5_"


class BaseRecognizer(ABC):
    @abstractmethod
    def recognize_image(self, image_path: str) -> str:
        """识别图片乐谱,返回规范化简谱文本。"""

    @abstractmethod
    def recognize_document(self, text: str) -> str:
        """识别/整理文档乐谱,返回规范化简谱文本。"""


class StubRecognizer(BaseRecognizer):
    """内置样例,不调用任何 API,用于端到端跑通流程。"""

    def recognize_image(self, image_path):
        return SAMPLE_JIANPU

    def recognize_document(self, text):
        return SAMPLE_JIANPU


def chat_messages(api_base: str, api_key: str, model: str, content: list, timeout: int = READ_TIMEOUT) -> str:
    """OpenAI 兼容协议的流式对话(识别与编谱建议共用)。

    网络/HTTP 错误统一转成可读的中文提示。
    """
    url = f"{api_base.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {"model": model, "messages": [{"role": "user", "content": content}], "stream": True}
    try:
        with requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=(CONNECT_TIMEOUT, timeout),
            stream=True,
        ) as resp:
            resp.raise_for_status()
            parts = []
            for line in resp.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except ValueError:
                    continue
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                parts.append(delta.get("content") or "")
            text = "".join(parts).strip()
            if not text:
                raise RuntimeError("模型未返回内容:请检查模型名称是否为支持图片输入的视觉模型")
            return text
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else "?"
        detail = ""
        try:
            detail = (e.response.text or "")[:300]
        except Exception:
            pass
        raise RuntimeError(f"接口返回错误(HTTP {status}): {detail}") from e
    except requests.exceptions.ReadTimeout as e:
        raise RuntimeError("识别请求超时:图片过大或网络较慢,请重试一次;多次超时可换用更快的模型(如 qwen-vl-plus)") from e
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"网络错误: {e}") from e


def chat_text(api_base: str, api_key: str, model: str, prompt: str, timeout: int = READ_TIMEOUT) -> str:
    """纯文本对话快捷入口(编谱建议等文本型任务使用)。"""
    return chat_messages(api_base, api_key, model, [{"type": "text", "text": prompt}], timeout)


class OpenAIStyleRecognizer(BaseRecognizer):
    """OpenAI 兼容协议的多模态识别接口(通义/GLM/Kimi/OpenAI 通用)。"""

    def __init__(self, api_base: str, api_key: str, model: str, timeout: int = READ_TIMEOUT):
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    @staticmethod
    def _compress_image(image_path: str):
        """大图等比压缩为 JPEG,返回 (jpeg_bytes, mime)。"""
        ext = os.path.splitext(image_path)[1].lower()
        raw_mime = "image/png" if ext == ".png" else "image/jpeg"
        img = Image.open(image_path)
        img.load()
        small = max(img.size) <= IMAGE_MAX_SIDE
        if small and raw_mime == "image/jpeg" and img.mode == "RGB":
            with open(image_path, "rb") as f:
                return f.read(), raw_mime
        if img.mode != "RGB":
            img = img.convert("RGB")
        if max(img.size) > IMAGE_MAX_SIDE:
            img.thumbnail((IMAGE_MAX_SIDE, IMAGE_MAX_SIDE), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=JPEG_QUALITY)
        return buf.getvalue(), "image/jpeg"

    def _chat(self, text_prompt: str, image_path: str | None = None) -> str:
        content = [{"type": "text", "text": text_prompt}]
        if image_path:
            if not os.path.exists(image_path):
                raise FileNotFoundError(f"图片不存在: {image_path}")
            data, mime = self._compress_image(image_path)
            b64 = base64.b64encode(data).decode("ascii")
            content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
        return chat_messages(self.api_base, self.api_key, self.model, content, self.timeout)

    def recognize_image(self, image_path: str) -> str:
        return self._chat(JIANPU_PROMPT, image_path=image_path)

    def recognize_document(self, text: str) -> str:
        return self._chat(f"{JIANPU_PROMPT}\n\n以下是文档提取出的乐谱内容:\n{text}")


def get_recognizer(cfg: dict) -> BaseRecognizer:
    """按配置实例化识别器。"""
    r = cfg.get("recognizer", {})
    provider = r.get("provider", "stub")
    if provider == "stub":
        return StubRecognizer()
    if provider == "openai_compatible":
        if not r.get("api_key"):
            raise ValueError("recognizer.api_key 未配置,请先在 config.yaml 填写 API Key")
        return OpenAIStyleRecognizer(
            api_base=r.get("api_base", ""),
            api_key=r.get("api_key", ""),
            model=r.get("model", ""),
            timeout=int(r.get("timeout", READ_TIMEOUT)),
        )
    raise ValueError(f"未知的 recognizer.provider: {provider}")


def get_recognizer_from_provider(provider: dict | None) -> BaseRecognizer:
    """按设置页配置的激活供应商创建识别器;无 key 时回退内置样例。"""
    if not provider or not provider.get("api_key"):
        return StubRecognizer()
    return OpenAIStyleRecognizer(
        api_base=provider.get("base_url", ""),
        api_key=provider.get("api_key", ""),
        model=provider.get("model", ""),
    )