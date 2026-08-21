"""体育新闻双智能体流水线入口。

流程：AgentA 通过 function calling 调用 fetch_sports_news 工具抓取 RSS →
      选出最热 Top-N 并总结 → AgentB 逐条点评 → 渲染报告。
每个阶段独立降级：AgentA 失败改用模拟新闻；AgentB 失败显示占位点评。

加 --notify 后：结果渲染成手机精简版，通过 ntfy 推送到手机（topic 见 config/.env）。
"""
import argparse
import json
import sys
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()  # 必须在 import config 之前

import config
from agents import AgentA, AgentB, normalize_items, parse_json
from news_fetcher import generate_fallback_news
from report import render_agent_a, render_agent_b, render_phone_digest_chunks, render_report
from sender import send_ntfy


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="体育新闻双智能体流水线")
    parser.add_argument(
        "--agent",
        choices=["A", "B", "both"],
        default="both",
        help="只运行哪个智能体：A=新闻编辑（Top-N 总结），B=评论员（逐条点评），both=全流程（默认）",
    )
    parser.add_argument(
        "--notify",
        action="store_true",
        help="渲染后通过 ntfy 推送到手机（topic 在 config/.env 的 NTFY_TOPIC）",
    )
    return parser.parse_args()


def _push(title: str, bodies: list[str]) -> None:
    """推送到手机（可能拆成多条分块消息）并打印结果。"""
    ok = True
    for idx, body in enumerate(bodies, start=1):
        t = f"{title}（{idx}/{len(bodies)}）" if len(bodies) > 1 else title
        if not send_ntfy(t, body):
            ok = False
    if ok:
        print(
            f"[ntfy] 已推送到手机 ✓（{len(bodies)} 条消息）→ "
            f"{config.NTFY_SERVER}/{config.NTFY_TOPIC}"
        )
    else:
        print(f"[ntfy] 推送失败 ✗ → {config.NTFY_SERVER}/{config.NTFY_TOPIC}")


def _push_title() -> str:
    return f"🏀 体育早报 · {datetime.now().strftime('%m-%d %H:%M')}"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args()
    notify = args.notify

    if not config.DEEPSEEK_API_KEY:
        msg = "未找到 DEEPSEEK_API_KEY，请在项目根目录 .env 中配置。"
        print(f"[错误] {msg}")
        if notify:
            _push("⚠️ 体育早报：配置缺失", msg)
        return 1

    print(
        f"=== 体育新闻双智能体流水线 === "
        f"(模型: {config.DEEPSEEK_MODEL}, 最近 {config.NEWS_HOURS}h, Top {config.TOP_N}, "
        f"智能体: {'A → B' if args.agent == 'both' else args.agent}"
        f"{', 推送: ntfy' if notify else ''})"
    )

    # 阶段 1：AgentA 通过 function calling 调用 fetch_sports_news 工具抓取并选出最热 Top-N
    try:
        raw_a, candidate_count, simulated = AgentA().generate()
        top_items = normalize_items(parse_json(raw_a, "items"), top_n=config.TOP_N)
        if not top_items:
            raise RuntimeError("AgentA 未返回任何新闻")
        print(f"[AgentA] 已从 {candidate_count} 条候选中选出 {len(top_items)} 条最热新闻。")
    except Exception as e:
        print(f"[错误] AgentA 失败（{e}），改用模拟数据继续。")
        top_items = generate_fallback_news(top_n=config.TOP_N)
        simulated = True

    # 只跑 AgentA
    if args.agent == "A":
        if notify:
            _push(_push_title(), render_phone_digest_chunks(top_items, {}))
        else:
            print()
            print(render_agent_a(top_items, simulated=simulated))
        return 0

    # 阶段 2：AgentB 接收 AgentA 的 JSON，逐条点评
    items_json = json.dumps({"items": top_items}, ensure_ascii=False)
    try:
        raw_b = AgentB().evaluate(items_json)
        evals = parse_json(raw_b, "evaluations")
        evaluation_map = {e["rank"]: e for e in evals}
        print(f"[AgentB] 已完成 {len(evaluation_map)} 条点评。")
    except Exception as e:
        print(f"[警告] AgentB 点评失败（{e}），将显示占位点评。")
        evaluation_map = {}

    # 只跑 AgentB
    if args.agent == "B":
        if notify:
            _push(_push_title(), render_phone_digest_chunks(top_items, evaluation_map))
        else:
            print()
            print(render_agent_b(evaluation_map))
        return 0

    # 全流程：渲染报告 或 推送到手机
    if notify:
        _push(_push_title(), render_phone_digest_chunks(top_items, evaluation_map))
    else:
        print()
        print(render_report(top_items, evaluation_map, simulated=simulated))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
