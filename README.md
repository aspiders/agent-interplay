# 体育新闻双智能体交互（LangChain + DeepSeek）

用 LangChain 实现两个智能体之间的交互，LLM 使用 DeepSeek（OpenAI 兼容接口）。

## 两个智能体

| 智能体 | 角色 | 职责 |
|---|---|---|
| **AgentA** | 体育新闻编辑 | 通过 function calling 调用 `fetch_sports_news` 工具抓取 RSS 候选新闻，选出过去 24 小时内最热的 10 条，再调用 `submit_news_report` 提交逐条中文总结、热度原因、关键词（结构化 JSON） |
| **AgentB** | 体育评论员 | 接收 AgentA 的 JSON，逐条写出中文点评并给出 1~5 分热度评分 |

**交互方式**：两阶段接力。AgentB 的输入就是 AgentA 的结构化输出（JSON），`main.py` 负责把两阶段结果合并渲染成最终报告。

```
AgentA 调用工具 fetch_sports_news（function calling 抓取 24h 候选 RSS）
   ↓
AgentA 选 Top10 + 总结  ──JSON──▶  AgentB 逐条点评
   ↓
render_report 合并打印
```

## 快速开始

```powershell
cd E:\codes\ai\agent-interplay
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 配置密钥
Copy-Item .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY=sk-...

python main.py
```

> Windows 控制台中文乱码时：`chcp 65001` 或在运行前设置 `$env:PYTHONIOENCODING="utf-8"`。

## 推送到手机（ntfy）

把结果推送到手机（需要手机装 ntfy 应用并订阅 topic）：

```powershell
# 全流程跑完并把精简版报告推到手机（topic 默认 zhenghz-aspider）
python main.py --notify
```

推送属性：
- **标题**：`🏀 体育早报 · 08-15 13:08`
- **正文**：精简版（每条新闻：标题 + 一句话总结 + 评分星级），约 1.7KB，适配 ntfy 公共服务器单条 4KB 上限
- **配置**：`.env` 里 `NTFY_SERVER`（默认 `https://ntfy.sh`）、`NTFY_TOPIC`（默认 `zhenghz-aspider`）

## 定时推送（Windows 任务计划）

```powershell
# 注册每天 08:00 自动运行并推送到手机
.\scheduler.ps1

# 指定时间（如每天早上 7:30）
.\scheduler.ps1 -Time "07:30"

# 卸载定时任务
.\scheduler.ps1 -Unregister
```

> 前提：到点电脑需开机且当前用户已登录（任务以交互方式运行）。
> 任务名：`SportsNewsNtfy`。改时间只需重跑 `.\scheduler.ps1 -Time "HH:MM"`。

## 云服务器部署（Ubuntu，可选）

想 7×24 定时跑、不依赖本机开机，可部署到一台 Ubuntu/Debian 云服务器。
应用是纯定时批处理（抓 RSS → 调 DeepSeek → 推 ntfy），无 Web 服务、无数据库，部署很轻。

**前置**：把代码推到 GitHub（本地 `git init` + push），服务器上 clone；大陆服务器直连 GitHub 超时时配镜像：
```bash
git config --global url."https://ghproxy.com/https://github.com/".insteadOf "https://github.com/"
```

**服务器端步骤**（SSH 执行）：
```bash
# 1. 时区（关键）+ 系统依赖（纯新增，不影响服务器上已有的 openclaw）
sudo timedatectl set-timezone Asia/Shanghai
sudo apt update && sudo apt install -y git python3 python3-venv python3-pip curl

# 2. 一键部署（-t 自定义时间，默认 08:00）
sudo GIT_REPO="https://github.com/<用户名>/agent-interplay.git" \
  bash <(curl -fsSL https://raw.githubusercontent.com/<用户名>/agent-interplay/main/deploy/install_ubuntu.sh) -t "08:00"
```
> 不放心 `curl | bash` 的话，clone 后跑 `sudo bash deploy/install_ubuntu.sh` 效果相同。
> 脚本会自动：装依赖 → 建 `sports` 用户 → 拉代码到 `/opt/sports-news` → 建 venv 装依赖 →
> 生成 `.env` 模板（填好密钥后重跑一次脚本继续）→ 装 systemd 定时任务。

**填 `.env`**：`sudo vim /opt/sports-news/.env`，必填 `DEEPSEEK_API_KEY`，按需配 `RSS_FEEDS`。

**验证**：
```bash
sudo -u sports /opt/sports-news/.venv/bin/python /opt/sports-news/main.py          # 全链路
sudo -u sports /opt/sports-news/.venv/bin/python /opt/sports-news/main.py --notify  # 推手机
systemctl list-timers sports-news.timer   # 看下次触发时间
journalctl -u sports-news.service -n 30   # 看日志
```

**常见问题**
- 换 RSS 源：先在服务器上 `curl -I <url>` 确认可达，再改 `.env` 的 `RSS_FEEDS`（`名字|url,名字|url`），不用改代码。
- ntfy.sh 大陆不可达：主流程不受影响（只报 `[ntfy] 推送失败`）；必要时自建 ntfy 后改 `NTFY_SERVER`。
- 更新代码：`cd /opt/sports-news && sudo git pull && sudo systemctl restart sports-news.timer`。

## 配置项（`.env`）

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DEEPSEEK_API_KEY` | （必填） | DeepSeek 密钥 |
| `DEEPSEEK_MODEL` | `deepseek-v4-flash` | 可换 `deepseek-v4-pro` 提升质量 |
| `DEEPSEEK_THINKING` | `false` | `true` 开启思考模式（更慢更贵，且 temperature 失效） |
| `NEWS_HOURS` | `24` | 新闻时间窗口（小时） |
| `TOP_N` | `10` | 最热新闻条数 |
| `CANDIDATE_LIMIT` | `30` | 喂给 AgentA 的候选新闻上限 |
| `NTFY_SERVER` | `https://ntfy.sh` | ntfy 服务器（自建/其他服务器时改） |
| `NTFY_TOPIC` | `zhenghz-aspider` | ntfy 订阅 topic（手机需已订阅） |
| `RSS_FEEDS` | （空） | 覆盖 RSS 源列表，格式 `名字\|url,名字\|url`；不设则用 `config.py` 的 `FEEDS`（大陆服务器配中文源用） |

RSS 源在 `config.py` 的 `FEEDS` 里配置，可自由增删（BBC Sport / ESPN / Guardian / Google News 等免费源）；
也可用 `.env` 的 `RSS_FEEDS` 整体覆盖，避免在服务器上改代码。

## 兜底机制

1. RSS 全部抓取失败 → `fetch_sports_news` 工具改用 DeepSeek 生成**模拟新闻**（报告中标注「模拟数据」）；
2. 连 DeepSeek 也失败 → 用内置静态模拟新闻，保证 demo 不崩；
3. 整条 AgentA（含工具调用）失败 → 直接回退到模拟数据继续跑 AgentB。

## DeepSeek × LangChain 兼容要点

DeepSeek 走 OpenAI 兼容接口，用 `langchain-openai` 的 `ChatOpenAI`，但有这些坑（已在 `llm.py` 处理）：

1. **用 `max_tokens`，禁用 `max_completion_tokens`** —— 后者会返回 400；
2. 不要传 `seed` / `logit_bias` / `n`（DeepSeek 不支持）；
3. `presence_penalty` / `frequency_penalty` 已废弃，不设；
4. **思考模式默认开启**，且开启时 `temperature` 被静默忽略 —— 用 `model_kwargs={"extra_body": {"thinking": {"type": "disabled"}}}` 关闭；
5. **`api_key` 必须显式传** `DEEPSEEK_API_KEY`，否则 `ChatOpenAI` 默认读 `OPENAI_API_KEY` 拿不到 key；
6. `base_url` 用 `https://api.deepseek.com`（SDK 自动追加 `/chat/completions`）；
7. `response_format={"type": "json_object"}` 可用，但 prompt 中必须出现单词 "json"（本项目的模板已包含）；
8. **function calling 与 JSON mode 不同时用**：AgentA 用 `bind_tools([fetch_sports_news, submit_news_report])` 走工具调用（此时 `make_llm(json_mode=False)` 不设 `response_format`）；最终 Top-N 由模型通过 `submit_news_report` 工具以结构化参数提交，工具调用参数天然是 JSON。AgentB 仍用 `response_format={"type":"json_object"}` 的 JSON mode。

## 文件结构

```
agent-interplay/
├── main.py            # 编排流水线入口（--notify 推送到手机）
├── config.py          # 集中配置（.env + feed 列表 + 参数）
├── llm.py             # ChatOpenAI 构造（json_mode 开关）+ 统一异常处理
├── news_fetcher.py    # RSS 抓取、24h 过滤、去重、兜底
├── tools.py           # AgentA 的 fetch_sports_news 工具（function calling）
├── agents.py          # AgentA（工具调用）/ AgentB（JSON mode）定义与交接
├── report.py          # 报告渲染（含手机精简版 render_phone_digest）
├── sender.py          # ntfy 手机推送
├── scheduler.ps1      # 注册 Windows 定时任务
├── deploy/            # 云服务器部署（Ubuntu）：install_ubuntu.sh + systemd units + cron.example
├── requirements.txt
├── .env.example
└── .gitignore
```
