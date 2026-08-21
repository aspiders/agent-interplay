"""RSS 体育新闻抓取层：纯数据，不直接依赖 LangChain。

职责：抓取多源 RSS → 过滤最近 N 小时 → 去重 → 按时间降序取候选 → 生成候选文本。
抓取失败时提供两层兜底：LLM 生成模拟新闻 / 内置静态模拟新闻。
"""
import calendar
import html
import json
import re
import time
import urllib.request
from datetime import datetime, timezone

import feedparser
from langchain_core.messages import HumanMessage

import config
from llm import make_llm, safe_model_invoke

_UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36 App/1.0"
    )
}

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _fetch_feed(url: str):
    """带 UA 拉取 feed 字节，再交给 feedparser 解析。

    不能直接 feedparser.parse(url)：部分源对默认 Python UA 返回 403。
    """
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=config.FEED_TIMEOUT) as resp:
        return feedparser.parse(resp.read())


def _clean_snippet(raw: str, max_len: int = 200) -> str:
    """剥掉 HTML 标签、反转义实体、压空白并截断。"""
    if not raw:
        return ""
    text = _TAG_RE.sub(" ", raw)
    text = html.unescape(text)
    text = _WS_RE.sub(" ", text).strip()
    return text[:max_len]


def _normalize_title(title: str) -> str:
    """标题归一化，用于跨源去重。"""
    return re.sub(r"\s+", "", title or "").lower()


def _item_from_entry(entry, source_name: str) -> dict | None:
    """把 feedparser entry 规范化为字典；缺发布时间则丢弃。"""
    if not getattr(entry, "published_parsed", None):
        return None
    published_ts = calendar.timegm(entry.published_parsed)  # published_parsed 是 UTC
    published = datetime.fromtimestamp(published_ts, tz=timezone.utc).isoformat(timespec="minutes")
    return {
        "title": getattr(entry, "title", "").strip(),
        "link": getattr(entry, "link", "").strip(),
        "source": source_name,
        "published": published,
        "published_ts": published_ts,
        "snippet": _clean_snippet(getattr(entry, "summary", "")),
    }


def fetch_recent_sports_news(hours: int | None = None, limit: int | None = None) -> list[dict]:
    """抓取所有 feed，返回最近 `hours` 小时内、去重、按时间降序的前 `limit` 条。"""
    hours = hours or config.NEWS_HOURS
    limit = limit or config.CANDIDATE_LIMIT
    now_ts = int(time.time())
    cutoff_ts = now_ts - hours * 3600

    seen_titles: set[str] = set()
    items: list[dict] = []

    for source_name, url in config.FEEDS:
        try:
            feed = _fetch_feed(url)
        except Exception as e:
            print(f"[提示] 抓取 {source_name} 失败：{e}")
            continue

        for entry in feed.entries:
            item = _item_from_entry(entry, source_name)
            if item is None:
                continue
            # 过滤最近 hours 小时
            if not (cutoff_ts <= item["published_ts"] <= now_ts):
                continue
            # 跨源去重
            key = _normalize_title(item["title"])
            if not key or key in seen_titles:
                continue
            seen_titles.add(key)
            items.append(item)

    # 按发布时间降序，取前 limit 条候选
    items.sort(key=lambda i: i["published_ts"], reverse=True)
    return items[:limit]


def build_news_context(items: list[dict]) -> str:
    """把候选新闻列表渲染成喂给 Agent A 的纯文本。"""
    lines = []
    for i, item in enumerate(items, start=1):
        snippet = item.get("snippet") or "（无摘要）"
        # 真实 RSS items 用 title；兜底/模拟 items 只有 original_title
        title = item.get("title") or item.get("original_title", "")
        lines.append(
            f"[{i}] [{item['source']}] ({item['published']}) {title}\n"
            f"    摘要：{snippet}"
        )
    return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# 兜底数据
# ---------------------------------------------------------------------------

_FALLBACK_PROMPT = """你是新闻数据生成器。当前无法访问真实 RSS，请生成 {n} 条【明确标注为模拟】的近期体育新闻。

要求：
- 每条主题、事件、时间都要现实可信，且发布时间落在最近 24 小时内（用真实日期时间，如 2026-08-14T20:15:00+00:00 这种格式）；
- 覆盖不同运动项目（足球、篮球、网球、F1、田径等），避免重复主题；
- 不要声称来自真实媒体（source 用"模拟数据"），url 用 https://example.com/{{id}}；
- 这是 json 模式，严格按照下面的 json 结构输出，不要输出任何额外说明：
{{"items": [{{"rank": 1, "original_title": "标题", "source": "模拟数据", "url": "https://example.com/1", "published": "2026-08-14T20:15:00+00:00", "hot_reason": "为什么值得关注", "summary": "中文总结", "keywords": ["关键词1", "关键词2"]}}]}}"""

_STATIC_FALLBACK: list[dict] = [
    {
        "rank": 1, "original_title": "模拟：国际冠军足球赛决赛于晚间结束（模拟数据）",
        "source": "模拟数据", "url": "https://example.com/1",
        "published": "2026-08-14T20:15:00+00:00",
        "hot_reason": "重量级对决，看点十足",
        "summary": "一场顶级俱乐部对决的决赛在晚间落幕，比赛过程跌宕起伏，最终以微弱分差决出胜负。",
        "keywords": ["足球", "决赛"],
    },
    {
        "rank": 2, "original_title": "模拟：NBA 球星完成重磅交易加盟新东家（模拟数据）",
        "source": "模拟数据", "url": "https://example.com/2",
        "published": "2026-08-14T18:40:00+00:00",
        "hot_reason": "涉及明星球员，牵动联盟格局",
        "summary": "一则涉及全明星球员的重磅交易正式达成，该球员将身披新球队战袍出战新赛季。",
        "keywords": ["NBA", "交易"],
    },
    {
        "rank": 3, "original_title": "模拟：网球大满贯女单冠军新鲜出炉（模拟数据）",
        "source": "模拟数据", "url": "https://example.com/3",
        "published": "2026-08-14T15:10:00+00:00",
        "hot_reason": "大满贯新王加冕",
        "summary": "网球大满贯女单决赛结束，一位选手直落两盘夺冠，成为该项目新科大满贯得主。",
        "keywords": ["网球", "大满贯"],
    },
    {
        "rank": 4, "original_title": "模拟：F1 大奖赛排位赛惊现重大意外（模拟数据）",
        "source": "模拟数据", "url": "https://example.com/4",
        "published": "2026-08-14T13:05:00+00:00",
        "hot_reason": "赛程焦点，牵动总冠军悬念",
        "summary": "F1 大奖赛排位赛期间发生重大意外，赛道一度出示红旗，多位车手成绩受到影响。",
        "keywords": ["F1", "排位赛"],
    },
    {
        "rank": 5, "original_title": "模拟：田径世锦赛百米飞人战中国选手创佳绩（模拟数据）",
        "source": "模拟数据", "url": "https://example.com/5",
        "published": "2026-08-14T10:30:00+00:00",
        "hot_reason": "中国队突破，引发热议",
        "summary": "田径世锦赛男子百米大战中，中国选手跑出个人最佳成绩并历史性闯入决赛。",
        "keywords": ["田径", "百米", "中国选手"],
    },
    {
        "rank": 6, "original_title": "模拟：英超转会窗关闭前的压哨引援（模拟数据）",
        "source": "模拟数据", "url": "https://example.com/6",
        "published": "2026-08-14T08:50:00+00:00",
        "hot_reason": "压哨签约，交易窗口看点",
        "summary": "英超夏季转会窗在截止前一刻完成压哨引援，多家豪门同时官宣新援加盟。",
        "keywords": ["英超", "转会"],
    },
    {
        "rank": 7, "original_title": "模拟：篮球世界杯小组赛爆出冷门（模拟数据）",
        "source": "模拟数据", "url": "https://example.com/7",
        "published": "2026-08-13T22:20:00+00:00",
        "hot_reason": "以弱胜强，话题性极强",
        "summary": "篮球世界杯小组赛中，赛前不被看好的队伍击败夺冠热门，爆出赛事最大冷门。",
        "keywords": ["篮球", "世界杯"],
    },
    {
        "rank": 8, "original_title": "模拟：短跑名将宣布赛季结束提前备战下届大赛（模拟数据）",
        "source": "模拟数据", "url": "https://example.com/8",
        "published": "2026-08-13T19:00:00+00:00",
        "hot_reason": "名将动态，备受关注",
        "summary": "短跑名将宣布提前结束本赛季，将全力备战下一届世界大赛，引发外界对其状态的讨论。",
        "keywords": ["短跑", "名将"],
    },
]


def generate_fallback_news(top_n: int | None = None) -> list[dict]:
    """兜底生成最近新闻（模拟数据）：优先让 LLM 生成，失败则退回静态数据。"""
    top_n = top_n or config.TOP_N

    # 第一层：LLM 生成
    if config.DEEPSEEK_API_KEY:
        try:
            llm = make_llm(temperature=0.8, max_tokens=2000)
            prompt = _FALLBACK_PROMPT.format(n=top_n)
            # 直接用 HumanMessage 传已格式化的文本，避免 ChatPromptTemplate 二次模板化
            # （单花括号 JSON 会被误当模板占位符，触发嵌套字段报错）
            raw = safe_model_invoke(llm, [HumanMessage(content=prompt)]).content
            data = json.loads(raw)
            items = data.get("items", [])
            if items:
                return normalize_fallback_items(items, top_n)
        except Exception as e:
            print(f"[警告] LLM 生成模拟新闻失败（{e}），改用内置静态数据。")

    # 第二层：内置静态数据
    return normalize_fallback_items(_STATIC_FALLBACK, top_n)


def normalize_fallback_items(items: list[dict], top_n: int) -> list[dict]:
    """把兜底 items 补全字段、按 rank 升序、截断到 top_n。"""
    out = []
    for idx, it in enumerate(items, start=1):
        out.append({
            "rank": it.get("rank", idx),
            "original_title": it.get("original_title", it.get("title", "")),
            "source": it.get("source", "模拟数据"),
            "url": it.get("url", ""),
            "published": it.get("published", ""),
            "hot_reason": it.get("hot_reason", ""),
            "summary": it.get("summary", ""),
            "keywords": it.get("keywords", []),
        })
    out.sort(key=lambda x: x["rank"])
    return out[:top_n]
