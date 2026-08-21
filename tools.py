"""AgentA 可见的工具：通过 function calling 抓取并提交体育新闻。

- fetch_sports_news：真实执行 RSS 抓取（复用 news_fetcher 的抓取/兜底逻辑）；
  抓取结果为空时返回明确标注为"模拟数据"的兜底新闻，与旧逻辑（main.py 阶段 0）行为一致。
- submit_news_report：结构化输出工具（sink）。模型把最终 Top-N 以工具调用参数提交，
  工具调用参数天然是 JSON，避免模型直接输出文本 JSON 的不稳定。
"""
from langchain_core.tools import tool

import config
import news_fetcher as nf


def fetch_news_text(hours: int | None = None, limit: int | None = None) -> tuple[str, int, bool]:
    """抓取候选新闻并渲染成文本。返回 (候选文本, 条数, 是否模拟数据)。

    实际执行 AgentA 的工具 fetch_sports_news：真实抓取 RSS，抓不到则用模拟数据兜底。
    """
    hours = hours or config.NEWS_HOURS
    limit = limit or config.CANDIDATE_LIMIT
    items = nf.fetch_recent_sports_news(hours=hours, limit=limit)
    if not items:
        items = nf.generate_fallback_news(top_n=config.TOP_N)
        text = "⚠️ RSS 源不可用，以下为模拟数据（仅供演示）：\n\n" + nf.build_news_context(items)
        return text, len(items), True
    return nf.build_news_context(items), len(items), False


@tool
def fetch_sports_news(
    hours: int = config.NEWS_HOURS,
    limit: int = config.CANDIDATE_LIMIT,
) -> str:
    """抓取最近若干小时内的多源体育新闻，返回按发布时间降序的候选列表文本。

    候选新闻来自 BBC Sport / ESPN / The Guardian / Google News 等 RSS 源。
    若全部 RSS 源不可用，将返回明确标注为"模拟数据"的兜底新闻，此时请如实总结，
    不要声称来自真实媒体。

    Args:
        hours: 只保留最近 hours 小时内发布的新闻。
        limit: 最多返回的候选条数（按发布时间降序取前 limit 条）。
    """
    text, _, _ = fetch_news_text(hours, limit)
    return text


@tool
def submit_news_report(items: list[dict]) -> str:
    """提交选出的最热体育新闻总结列表。

    当 fetch_sports_news 返回候选新闻后，必须调用本工具，把最终选出的 Top-N 条新闻
    以 items 参数（结构化列表）提交。这是你的最终输出，提交后不要再输出任何其他内容。

    每个 item 必须是包含以下字段的 JSON 对象：
    {"rank": 整数排名从1开始, "original_title": 原始标题, "source": 来源名, "url": 原文链接, "published": 发布时间, "hot_reason": 为什么值得关注, "summary": 中文总结, "keywords": [2~3个中文关键词]}
    """
    return "已收到提交。"
