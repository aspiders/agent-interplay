"""ntfy 手机推送层。

ntfy 是开源的 pub-sub 推送服务：向 `https://ntfy.sh/{topic}` POST 一条消息，
已订阅该 topic 的手机（ntfy 应用）就会收到通知。默认用公共服务器 ntfy.sh。

注意：Title/Tags 等通知属性通过 URL 查询参数传递（ntfy 支持），而不是 HTTP 头——
urllib 的 header 只支持 latin-1，中文/emoji 标题放 header 会编码失败。
"""
import urllib.parse
import urllib.request

import config


def send_ntfy(
    title: str,
    body: str,
    topic: str | None = None,
    priority: int = 3,
) -> bool:
    """把 body 推送到指定 topic，成功返回 True。

    Args:
        title: 通知标题（手机上显示的大标题，支持中文/emoji）。
        body: 通知正文（ntfy 公共服务器单条消息上限约 4096 字节，需自行控制长度）。
        topic: 订阅的 topic，默认取 config.NTFY_TOPIC。
        priority: 1=最低 … 3=默认 … 5=紧急（手机会持续响铃/置顶）。
    """
    topic = topic or config.NTFY_TOPIC
    query = urllib.parse.urlencode({
        "title": title,
        "priority": str(priority),
        "tags": "sports",
    })
    url = f"{config.NTFY_SERVER.rstrip('/')}/{urllib.parse.quote(topic)}?{query}"

    req = urllib.request.Request(
        url,
        data=body.encode("utf-8"),
        headers={"Content-Type": "text/plain; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=config.NTFY_TIMEOUT) as resp:
            if resp.status == 200:
                return True
            print(f"[ntfy] 服务器返回非 200：{resp.status}")
            return False
    except Exception as e:
        print(f"[错误] ntfy 推送失败：{e}")
        return False
