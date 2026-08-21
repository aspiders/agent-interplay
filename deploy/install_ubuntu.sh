#!/usr/bin/env bash
#
# 一键部署「体育新闻双智能体」到 Ubuntu/Debian 服务器（幂等，可重复跑）。
# 只会【新增】系统包，不动服务器上已有的 openclaw（Docker）等任何现有组件。
#
# 用法（需 root 或 sudo）：
#   sudo GIT_REPO="https://github.com/<用户名>/agent-interplay.git" bash install_ubuntu.sh
#   sudo GIT_REPO="..." bash install_ubuntu.sh -t "07:30"     # 指定每天定时时间
#   sudo GIT_REPO="..." bash install_ubuntu.sh -d /opt/foo -u news   # 换目录 / 运行用户
#
set -euo pipefail

# ---------- 参数 ----------
TIME="${1:-08:00}"
DIR="/opt/sports-news"
RUN_USER="sports"
# 必填：你的 GitHub 仓库地址（服务器上 clone 用）
GIT_REPO="${GIT_REPO:-}"

usage() {
  echo "用法: sudo GIT_REPO=<仓库地址> bash $0 [-t HH:MM] [-d DIR] [-u USER]"
  echo "  -t   每天定时时间（默认 08:00）"
  echo "  -d   安装目录（默认 /opt/sports-news）"
  echo "  -u   运行用户（默认 sports）"
  exit 1
}

while getopts "t:d:u:h" opt; do
  case "$opt" in
    t) TIME="$OPTARG" ;;
    d) DIR="$OPTARG" ;;
    u) RUN_USER="$OPTARG" ;;
    h) usage ;;
    *) usage ;;
  esac
done

# 校验时间格式 HH:MM
if ! [[ "$TIME" =~ ^([01][0-9]|2[0-3]):[0-5][0-9]$ ]]; then
  echo "错误：时间格式应为 HH:MM（如 07:30），收到 '$TIME'" >&2
  exit 1
fi

if [[ -z "$GIT_REPO" ]]; then
  echo "错误：请通过环境变量 GIT_REPO 传入 GitHub 仓库地址，例如：" >&2
  echo "  sudo GIT_REPO=\"https://github.com/<用户名>/agent-interplay.git\" bash $0" >&2
  exit 1
fi

if [[ "$(id -u)" -ne 0 ]]; then
  echo "错误：请用 root 或 sudo 运行本脚本。" >&2
  exit 1
fi

# ---------- 部署 ----------
echo "==> [1/8] 安装系统依赖（纯新增，不影响已有 openclaw）"
apt-get update
apt-get install -y git python3 python3-venv python3-pip python3-dev build-essential ca-certificates curl

echo "==> [2/8] 准备运行用户 $RUN_USER"
if ! id "$RUN_USER" >/dev/null 2>&1; then
  useradd -r -m -s /bin/bash "$RUN_USER"
  echo "    已创建用户 $RUN_USER"
else
  echo "    用户 $RUN_USER 已存在"
fi

echo "==> [3/8] 拉取代码到 $DIR"
if [[ ! -d "$DIR" ]]; then
  mkdir -p "$(dirname "$DIR")"
  if ! git clone "$GIT_REPO" "$DIR"; then
    echo ""
    echo "clone 失败。若因大陆网络直连 GitHub 超时，先配置镜像规则后重跑本脚本："
    echo '  git config --global url."https://ghproxy.com/https://github.com/".insteadOf "https://github.com/"'
    echo "重跑: sudo GIT_REPO=\"$GIT_REPO\" bash $0 ${TIME:+$TIME}"
    exit 1
  fi
  chown -R "$RUN_USER":"$RUN_USER" "$DIR"
else
  echo "    目录已存在，改为 git pull"
  # 用运行用户身份 pull（仓库属主已是 $RUN_USER，root 跑会触发 dubious ownership）
  sudo -u "$RUN_USER" git -C "$DIR" pull
  chown -R "$RUN_USER":"$RUN_USER" "$DIR"
fi

echo "==> [4/8] 创建 venv 并安装 Python 依赖"
sudo -u "$RUN_USER" python3 -m venv "$DIR/.venv"
sudo -u "$RUN_USER" "$DIR/.venv/bin/pip" install --upgrade pip
sudo -u "$RUN_USER" "$DIR/.venv/bin/pip" install -r "$DIR/requirements.txt"

echo "==> [5/8] 配置 .env"
if [[ ! -f "$DIR/.env" ]]; then
  cp "$DIR/.env.example" "$DIR/.env"
  echo "    已从 .env.example 生成 $DIR/.env，请编辑填入必填项后重跑本脚本："
  echo "      sudo vim $DIR/.env"
  echo "        必填：DEEPSEEK_API_KEY=sk-...（到 platform.deepseek.com 申请）"
  echo "        确认：NTFY_TOPIC=zhenghz-sport（手机已订阅的 topic）"
  echo "        可选：RSS_FEEDS=ESPN|https://www.espn.com/espn/rss/news,网易体育|https://sports.163.com/special/00051K8P/rss_newstop.xml"
  echo "              （大陆服务器海外源多不可达，换成在服务器上实测可达的中文源）"
  echo ""
  echo "    填完保存后，重新执行本脚本即可继续（幂等，跳到下一步）。"
  exit 0
else
  echo "    $DIR/.env 已存在，保留"
fi

echo "==> [6/8] 权限收紧"
chmod 600 "$DIR/.env"
chown -R "$RUN_USER":"$RUN_USER" "$DIR"

echo "==> [7/8] 安装 systemd 定时任务（每天 $TIME）"
cp "$DIR/deploy/sports-news.service" /etc/systemd/system/sports-news.service
sed -i "s|^User=.*|User=$RUN_USER|; s|WorkingDirectory=.*|WorkingDirectory=$DIR|; s|ExecStart=.*|ExecStart=$DIR/.venv/bin/python $DIR/main.py --notify|" /etc/systemd/system/sports-news.service
cp "$DIR/deploy/sports-news.timer" /etc/systemd/system/sports-news.timer
sed -i "s|OnCalendar=.*|OnCalendar=*-*-* $TIME:00|" /etc/systemd/system/sports-news.timer

echo "==> [8/8] 启用定时器"
systemctl daemon-reload
systemctl enable --now sports-news.timer
systemctl reset-failed sports-news.service >/dev/null 2>&1 || true

echo ""
echo "✔ 部署完成。接下来："
echo "  1. 先手动跑一次（确认链路）：  sudo -u $RUN_USER $DIR/.venv/bin/python $DIR/main.py"
echo "  2. 再验证推送到手机：          sudo -u $RUN_USER $DIR/.venv/bin/python $DIR/main.py --notify"
echo "  3. 看下次定时触发：            systemctl list-timers sports-news.timer"
echo "  4. 手动触发一次：              sudo systemctl start sports-news.service"
echo "  5. 看运行日志：                journalctl -u sports-news.service -n 30 --no-pager"
