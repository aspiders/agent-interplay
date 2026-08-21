"""把 AgentA 的 items 与 AgentB 的点评合并渲染成中文报告。"""
import config


def _clip(text: str, max_len: int) -> str:
    """截断字符串到指定长度，超长加省略号。"""
    text = (text or "").strip()
    return text if len(text) <= max_len else text[:max_len] + "…"


# ntfy 公共服务器单条消息上限约 4096 字节，这里留 10% 余量
_NTFY_MAX_BYTES = 3800


def _byte_len(text: str) -> int:
    """UTF-8 字节数（中文字符 3 字节、emoji 4 字节）。"""
    return len(text.encode("utf-8"))


def _phone_blocks(items: list[dict], evaluation_map: dict) -> tuple[str, list[str]]:
    """构建手机精简版：返回 (头部标题行, 每条新闻的块)。

    每条块含 AgentB 的完整点评（不截断）。分块时以「条」为最小单位，
    整条新闻从不拆开，确保任何一条点评都完整。
    """
    header = f"🏀 过去 {config.NEWS_HOURS}h 最热体育 TOP {config.TOP_N}"
    blocks = []
    for it in items:
        rank = it.get("rank", 0)
        ev = evaluation_map.get(rank) or {}
        rating = ev.get("rating")
        stars = "⭐" * int(rating) if isinstance(rating, int) and 1 <= rating <= 5 else ""
        comment = (ev.get("evaluation") or "").strip()
        lines = [f"{rank}. {_clip(it.get('original_title', ''), 34)} {stars}".rstrip()]
        lines.append(f"   {_clip(it.get('summary', ''), 46)}")
        if comment:
            lines.append(f"   💬 {comment}")
        blocks.append("\n".join(lines))
    return header, blocks


def render_phone_digest(items: list[dict], evaluation_map: dict) -> str:
    """渲染适合手机推送的精简版（含 AgentB 完整点评）。

    注意：点评较多时可能超过 ntfy 单条 4KB 上限，正式推送请用
    render_phone_digest_chunks 自动分块。
    """
    header, blocks = _phone_blocks(items, evaluation_map)
    return header + "\n" + "\n".join(blocks)


def render_phone_digest_chunks(
    items: list[dict],
    evaluation_map: dict,
    max_bytes: int = _NTFY_MAX_BYTES,
) -> list[str]:
    """渲染手机精简版并自动分块（每条新闻不拆开）。

    一条放得下就返回单条；超过 max_bytes 时按新闻条数拆成多条消息，
    每条都含完整点评。拆多块时手机上会收到多条通知，标题带「第 x/n 条」。
    """
    header, blocks = _phone_blocks(items, evaluation_map)
    chunks: list[list[str]] = []
    current: list[str] = []
    current_size = _byte_len(header) + 1

    for block in blocks:
        block_size = _byte_len(block) + 1
        # 放不下就另起一条消息；单条新闻即使超长也单独成块、绝不截断
        if current and current_size + block_size > max_bytes:
            chunks.append(current)
            current = []
            current_size = _byte_len(header) + 1
        current.append(block)
        current_size += block_size

    if current:
        chunks.append(current)

    if len(chunks) <= 1:
        return [header + "\n" + "\n".join(chunks[0]) if chunks else header]

    parts = []
    for idx, chunk in enumerate(chunks, start=1):
        hdr = f"{header}（第 {idx}/{len(chunks)} 条）"
        parts.append(hdr + "\n" + "\n".join(chunk))
    return parts


def render_agent_a(items: list[dict], simulated: bool = False) -> str:
    """只渲染 AgentA（新闻编辑）的输出：Top-N 新闻总结，不包含点评。"""
    lines = []
    title = "🏀 AgentA（体育新闻编辑）输出：过去 24 小时最热体育新闻"
    if simulated:
        title += "  【⚠️ 模拟数据】"
    lines.append("=" * 70)
    lines.append(title)
    lines.append("=" * 70)

    if not items:
        lines.append("（未获取到任何新闻）")
        return "\n".join(lines)

    for it in items:
        lines.append(f"\n[{it.get('rank', 0)}] {it.get('original_title', '')}")
        lines.append(
            f"    来源：{it.get('source', '-')} | 时间：{it.get('published', '-')}"
        )
        if it.get("url"):
            lines.append(f"    链接：{it.get('url')}")
        lines.append(f"    总结：{it.get('summary', '')}")
        lines.append(f"    热度原因：{it.get('hot_reason', '')}")
        kws = it.get("keywords") or []
        lines.append(f"    关键词：{'、'.join(kws) if kws else '-'}")
    lines.append("\n" + "=" * 70)
    lines.append("以上为 AgentA 的完整输出（JSON 已交给 AgentB）。")
    lines.append("=" * 70)
    return "\n".join(lines)


def render_agent_b(evaluation_map: dict) -> str:
    """只渲染 AgentB（评论员）的输出：逐条点评与评分。"""
    lines = []
    lines.append("=" * 70)
    lines.append("🎙 AgentB（体育评论员）输出：逐条点评")
    lines.append("=" * 70)

    if not evaluation_map:
        lines.append("（无点评数据）")
        return "\n".join(lines)

    for rank in sorted(evaluation_map):
        ev = evaluation_map[rank]
        rating = ev.get("rating")
        rating_str = f"{'⭐' * int(rating)} ({rating}/5)" if isinstance(rating, int) and 1 <= rating <= 5 else "—"
        lines.append(f"\n[新闻 {rank}]")
        lines.append(f"    点评：{ev.get('evaluation', '')}")
        lines.append(f"    热度评分：{rating_str}")
    lines.append("\n" + "=" * 70)
    return "\n".join(lines)


def render_report(
    items: list[dict],
    evaluation_map: dict,
    simulated: bool = False,
) -> str:
    """渲染最终报告。

    Args:
        items: AgentA 输出的规范化新闻列表。
        evaluation_map: {rank: {"evaluation": str, "rating": int}}，可能为空。
        simulated: 是否走的是模拟数据。
    """
    lines = []
    title = "🏀 过去 24 小时最热体育新闻 TOP 10（双智能体协作）"
    if simulated:
        title += "  【⚠️ 模拟数据】"
    lines.append("=" * 70)
    lines.append(title)
    lines.append(f"模型：{config.DEEPSEEK_MODEL} | 窗口：最近 {config.NEWS_HOURS} 小时")
    lines.append("=" * 70)

    if not items:
        lines.append("（未获取到任何新闻）")
        return "\n".join(lines)

    for it in items:
        rank = it.get("rank", 0)
        lines.append(f"\n[{rank}] {it.get('original_title', '')}")
        lines.append(
            f"    来源：{it.get('source', '-')} | 时间：{it.get('published', '-')}"
        )
        if it.get("url"):
            lines.append(f"    链接：{it.get('url')}")
        lines.append(f"    总结：{it.get('summary', '')}")
        lines.append(f"    热度原因：{it.get('hot_reason', '')}")
        kws = it.get("keywords") or []
        lines.append(f"    关键词：{'、'.join(kws) if kws else '-'}")

        ev = evaluation_map.get(rank)
        if ev:
            rating = ev.get("rating")
            rating_str = f"{'⭐' * int(rating)}" if isinstance(rating, int) and 1 <= rating <= 5 else "—"
            lines.append(f"    🎙 点评（AgentB）：{ev.get('evaluation', '')}")
            lines.append(f"    热度评分：{rating_str} ({rating}/5)" if rating_str != "—" else f"    热度评分：—")
        else:
            lines.append("    🎙 点评（AgentB）：（点评生成失败，可能是 API 限流）")
            lines.append("    热度评分：—")

    lines.append("\n" + "=" * 70)
    lines.append("已由两个智能体协作完成：AgentA（新闻编辑）→ AgentB（评论员）")
    lines.append("=" * 70)
    return "\n".join(lines)
