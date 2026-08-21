"""两个智能体的定义与数据交接。

AgentA（体育新闻编辑）：通过 function calling 调用 fetch_sports_news 工具抓取候选新闻，
再选出最热的 Top-N 条并逐条总结，输出 JSON。
AgentB（体育评论员）：接收 AgentA 的 JSON，逐条写中文点评并评分。

交互即两阶段接力：AgentB 的输入就是 AgentA 的结构化输出。
"""
import json

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate

import config
from llm import make_llm, safe_invoke, safe_model_invoke
from tools import fetch_news_text, fetch_sports_news, submit_news_report

# 工具调用循环最多轮数，防止模型反复调用工具不输出最终结果
_MAX_TOOL_TURNS = 6

AGENT_A_SYSTEM = """你是一名资深的体育新闻编辑智能体。为了获取新闻，你必须先调用工具 fetch_sports_news 获取候选新闻；一切内容以工具返回为准，不得臆造。然后从候选中筛选出最近 24 小时内最热门、最有影响力的体育新闻，最后调用工具 submit_news_report 提交你的总结结果（结构化列表）。"""

AGENT_A_TEMPLATE = """请严格按以下流程完成任务：

1. 调用工具 fetch_sports_news 获取候选新闻（用默认参数即可）；
2. 从工具返回的候选中，选出【最热门、最受关注、最有新闻价值】的 {top_n} 条体育新闻，逐条准备：
   - summary：用不超过 80 字的中文总结核心内容；
   - hot_reason：用不超过 40 字说明为什么值得关注；
   - keywords：提取 2~3 个中文关键词。
3. 调用工具 submit_news_report，把选出的 {top_n} 条以 items 参数（结构化列表）提交。这是你的最终输出，提交后不要再输出任何其他内容。

要求：
- 优先挑选重大赛事、重磅转会、球星动态、争议事件等话题性强的新闻；
- 各条之间避免重复主题；候选不足 {top_n} 条时按实际数量输出；
- 不要臆造工具返回中不存在的事实或链接；若工具返回的是模拟数据，也要如实总结，source 用返回中的来源名。"""

AGENT_B_SYSTEM = """你是一名犀利的体育新闻评论员智能体。你负责对编辑智能体选出的每一条体育新闻写出专业、有观点、有信息量的中文点评。你始终输出合法的 json。"""

AGENT_B_TEMPLATE = """这是体育编辑智能体从过去 24 小时新闻中选出的 {top_n} 条最热体育新闻（json 格式）：

{items_json}

请针对【每一条】新闻写一段中文点评（每条 80~150 字），要求：
- 有明确观点与态度，而不是复述新闻内容；
- 结合体育背景与行业知识，指出该新闻的意义、影响或争议点；
- 语气专业但不枯燥，可适度风趣；
- 每条点评必须用 rank 字段对应原新闻。

这是 json 模式。严格按照下面的 json 结构输出，不要输出任何额外说明：
{{"evaluations": [{{"rank": 1, "evaluation": "中文点评", "rating": 4}}]}}
rating 为该条新闻的热度/影响力评分，1~5 分。"""


class AgentA:
    """体育新闻编辑智能体：调用工具抓候选 → 通过 submit 工具提交 Top-N 总结（结构化 JSON）。

    读新闻走真正的 function calling：模型先调用 fetch_sports_news 抓 RSS，再调用
    submit_news_report 把最终结果作为工具调用参数提交（天然是 JSON，不靠文本 JSON）。
    """

    def __init__(self):
        # function calling 与 JSON mode 不同时用：绑定工具后 json_mode=False
        self.llm = make_llm(temperature=0.6, json_mode=False).bind_tools(
            [fetch_sports_news, submit_news_report]
        )
        self.system = SystemMessage(content=AGENT_A_SYSTEM)
        self.human = HumanMessage(content=AGENT_A_TEMPLATE.format(top_n=config.TOP_N))

    def generate(self) -> tuple[str, int, bool]:
        """运行工具调用循环。

        Returns:
            (原始 LLM 输出, 工具返回的候选新闻条数, 是否模拟数据)。
        """
        messages = [self.system, self.human]
        candidate_count, simulated = 0, False
        fetched = False

        for _ in range(_MAX_TOOL_TURNS):
            resp = safe_model_invoke(self.llm, messages)
            tool_calls = getattr(resp, "tool_calls", None)

            if not tool_calls:
                content = resp.content if hasattr(resp, "content") else str(resp)
                content = content or ""
                # 容错：模型偶尔直接输出 JSON 文本而非调用 submit_news_report
                stripped = content.strip()
                if stripped:
                    try:
                        data = json.loads(stripped)
                        if isinstance(data, dict) and isinstance(data.get("items"), list):
                            return content, candidate_count, simulated
                    except json.JSONDecodeError:
                        pass
                messages.append(
                    HumanMessage(
                        content="错误：请调用 submit_news_report 工具提交最终 Top-N 新闻列表，不要输出其他文本。"
                    )
                )
                continue

            messages.append(resp)
            for tc in tool_calls:
                name = tc["name"]
                args = tc.get("args") or {}
                if name == "fetch_sports_news":
                    text, candidate_count, simulated = fetch_news_text(**args)
                    fetched = True
                    print(
                        f"[AgentA] 调用工具 fetch_sports_news(hours={args.get('hours')}, "
                        f"limit={args.get('limit')}) → 返回 {candidate_count} 条候选"
                        f"{'（模拟数据）' if simulated else ''}。"
                    )
                elif name == "submit_news_report":
                    if not fetched:
                        messages.append(
                            ToolMessage(
                                content="错误：请先调用 fetch_sports_news 获取候选新闻，再提交总结。",
                                tool_call_id=tc["id"],
                                name=name,
                            )
                        )
                        continue
                    items = args.get("items") or []
                    return (
                        json.dumps({"items": items}, ensure_ascii=False),
                        candidate_count,
                        simulated,
                    )
                else:
                    text = f"未知工具：{name}"
                    messages.append(
                        ToolMessage(content=text, tool_call_id=tc["id"], name=name)
                    )
                    continue

                messages.append(
                    ToolMessage(content=text, tool_call_id=tc["id"], name=name)
                )

        raise RuntimeError(f"工具调用超过 {_MAX_TOOL_TURNS} 轮仍未输出最终结果")


class AgentB:
    """体育评论员智能体：AgentA 的 JSON → 逐条中文点评（JSON）。"""

    def __init__(self):
        self.llm = make_llm(temperature=0.6)
        self.prompt = ChatPromptTemplate.from_messages(
            [("system", AGENT_B_SYSTEM), ("human", AGENT_B_TEMPLATE)]
        )

    def evaluate(self, items_json: str) -> str:
        return safe_invoke(
            self.prompt | self.llm,
            {"items_json": items_json, "top_n": config.TOP_N},
        )


def parse_json(raw: str, key: str) -> list[dict]:
    """解析 LLM 输出的 JSON 字符串并取指定 key 的数组。

    尽量宽容：剥离可能的代码块围栏，解析失败抛 RuntimeError。
    """
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"LLM 输出不是合法 JSON：{e}\n输出片段：{text[:200]}") from e
    items = data.get(key) if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise RuntimeError(f"JSON 中缺少列表字段 \"{key}\"：{text[:200]}")
    return items


def normalize_items(items: list[dict], top_n: int | None = None) -> list[dict]:
    """把 AgentA 输出的 items 规范化：按 rank 升序、补必填字段、截断到 top_n。"""
    top_n = top_n or config.TOP_N
    out = []
    for idx, it in enumerate(items, start=1):
        out.append({
            "rank": it.get("rank", idx),
            "original_title": it.get("original_title", it.get("title", "")),
            "source": it.get("source", ""),
            "url": it.get("url", ""),
            "published": it.get("published", ""),
            "hot_reason": it.get("hot_reason", ""),
            "summary": it.get("summary", ""),
            "keywords": it.get("keywords", []),
        })
    out.sort(key=lambda x: x["rank"])
    return out[:top_n]
