"""集中配置：加载 .env 并暴露所有可调参数。"""
import os
from pathlib import Path

from dotenv import load_dotenv

# 用绝对路径加载 .env：定时任务运行时工作目录不固定，不能依赖 cwd
_PROJECT_DIR = Path(__file__).resolve().parent
load_dotenv(_PROJECT_DIR / ".env")

# ---- DeepSeek LLM ----
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
# 默认关闭思考模式：更快更省，且 temperature 参数才会生效
DEEPSEEK_THINKING = os.getenv("DEEPSEEK_THINKING", "false").lower() in ("1", "true", "yes")
DEEPSEEK_MAX_RETRIES = int(os.getenv("DEEPSEEK_MAX_RETRIES", "3"))
DEEPSEEK_TIMEOUT = int(os.getenv("DEEPSEEK_TIMEOUT", "60"))

# ---- 新闻抓取 ----
# 每条新闻统计的窗口（小时）
NEWS_HOURS = int(os.getenv("NEWS_HOURS", "24"))
# 最终输出的最热新闻条数
TOP_N = int(os.getenv("TOP_N", "10"))
# 喂给 Agent A 的候选新闻上限（按时间降序截取）
CANDIDATE_LIMIT = int(os.getenv("CANDIDATE_LIMIT", "30"))
# 每个 feed 抓取超时（秒）
FEED_TIMEOUT = int(os.getenv("FEED_TIMEOUT", "15"))

# ---- ntfy 手机推送 ----
# ntfy 服务器（默认公共服务器 ntfy.sh；若用的是自建/其他服务器，改成对应地址）
NTFY_SERVER = os.getenv("NTFY_SERVER", "https://ntfy.sh")
# 已存在的订阅 topic
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "zhenghz-aspider")
NTFY_TIMEOUT = int(os.getenv("NTFY_TIMEOUT", "20"))

# 免费 RSS 体育新闻源：(来源名, URL)。可自行增删。
FEEDS = [
    ("BBC Sport", "https://feeds.bbci.co.uk/sport/rss.xml"),
    ("ESPN", "https://www.espn.com/espn/rss/news"),
    ("The Guardian Sport", "https://www.theguardian.com/sport/rss"),
    ("Google News (sports 24h)", "https://news.google.com/rss/search?q=sports%20when:1d&hl=en-US&gl=US&ceid=US:en"),
]
# 可选中文源（取消注释即可启用）：
# FEEDS.append(("Google News 体育 24h", "https://news.google.com/rss/search?q=%E4%BD%93%E8%82%B2%20when:1d&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"))

# 用 .env 里的 RSS_FEEDS 覆盖默认源（格式：名字|url,名字|url，逗号分隔多个）。
# 便于服务器上不修改代码就切换/增删 RSS 源；不设置时用上面的默认 FEEDS。
# 大陆服务器上默认海外源（BBC/Guardian/Google News）多不可达，可在 .env 配中文源。
RSS_FEEDS = os.getenv("RSS_FEEDS", "")
if RSS_FEEDS:
    FEEDS = []
    for seg in RSS_FEEDS.split(","):
        seg = seg.strip()
        if "|" in seg:
            name, url = seg.split("|", 1)
            FEEDS.append((name.strip(), url.strip()))
