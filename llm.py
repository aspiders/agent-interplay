"""LLM 构造与统一调用封装。

隔离 LangChain × DeepSeek(OpenAI 兼容) 的全部细节，业务代码只依赖本模块。
"""
import openai
from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI

import config


def make_llm(
    temperature: float = 0.6,
    max_tokens: int = 2000,
    json_mode: bool = True,
) -> ChatOpenAI:
    """构造一个指向 DeepSeek 的 ChatOpenAI 实例。

    DeepSeek 兼容坑（详见 README）：
    - 用 max_tokens，禁用 max_completion_tokens（否则 400）
    - 不设 seed / logit_bias / n / presence_penalty / frequency_penalty
    - 思考模式默认开启且会忽略 temperature，用 extra_body 关闭
    - api_key 必须显式传 DEEPSEEK_API_KEY（默认会读 OPENAI_API_KEY）
    - base_url 只给根地址，SDK 会自动追加 /chat/completions
    - function calling 与 JSON mode 不同时用：绑定了工具就设 json_mode=False
    """
    # langchain-openai 1.5.x：extra_body 是一级字段；response_format 不是字段，需放 model_kwargs
    # 工具调用（function calling）场景下不设 response_format，最终 JSON 靠提示词约束
    model_kwargs = {"response_format": {"type": "json_object"}} if json_mode else {}
    extra_body = {"thinking": {"type": "disabled"}} if not config.DEEPSEEK_THINKING else None

    return ChatOpenAI(
        model=config.DEEPSEEK_MODEL,
        api_key=config.DEEPSEEK_API_KEY,
        base_url=config.DEEPSEEK_BASE_URL,
        temperature=temperature,
        max_tokens=max_tokens,
        max_retries=config.DEEPSEEK_MAX_RETRIES,
        timeout=config.DEEPSEEK_TIMEOUT,
        extra_body=extra_body,
        model_kwargs=model_kwargs,
    )


def _translate_and_raise(e: Exception) -> None:
    """把 openai 等底层异常翻译成带中文说明的 RuntimeError 后抛出。"""
    if isinstance(e, openai.RateLimitError):
        raise RuntimeError(f"DeepSeek 限流(429)：{e}") from e
    if isinstance(e, openai.APITimeoutError):
        raise RuntimeError(f"DeepSeek 请求超时：{e}") from e
    if isinstance(e, openai.APIStatusError):
        raise RuntimeError(f"DeepSeek 返回 {e.status_code}：{e.body}") from e
    if isinstance(e, openai.APIConnectionError):
        raise RuntimeError(f"DeepSeek 连接失败：{e}") from e
    raise RuntimeError(f"未知错误：{e}") from e


def safe_invoke(chain, inputs: dict) -> str:
    """调用 LCEL 链并统一异常处理，失败时抛出带中文说明的 RuntimeError。"""
    try:
        resp = chain.invoke(inputs)
        return resp.content if hasattr(resp, "content") else str(resp)
    except Exception as e:
        _translate_and_raise(e)


def safe_model_invoke(llm, messages) -> AIMessage:
    """直接调用模型（工具调用场景），返回 AIMessage；失败时抛带中文说明的 RuntimeError。"""
    try:
        return llm.invoke(messages)
    except Exception as e:
        _translate_and_raise(e)
