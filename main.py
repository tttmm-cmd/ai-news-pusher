#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Agent 每日新闻推送
多源爬取 → DeepSeek 翻译+摘要 → 邮件推送（SMTP）
自带 URL 去重历史，避免重复推送

用法:
    python main.py          # 手动运行一次
    # 或通过 GitHub Actions 每日自动运行
"""

import os
import re
import json
import time
import hashlib
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests


def _load_dotenv(path: str = None):
    """极简 .env 加载（不引入 python-dotenv）：读取 KEY=VALUE，写入环境变量（不覆盖已存在的值）"""
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val
    except Exception as e:
        print(f"[WARN] 加载 .env 失败: {e}")


# 先加载 .env，再读取下面的配置
_load_dotenv()

# ============================================================
# 配置 — 全部从环境变量读取，不要硬编码密钥
# ============================================================

DEEPSEEK_API_KEY = os.environ["DEEPSEEK_API_KEY"]
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "") or "https://api.deepseek.com/v1"
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "") or "deepseek-chat"

# SMTP 邮件配置（默认适配 QQ 邮箱）
SMTP_HOST = os.environ.get("SMTP_HOST", "") or "smtp.qq.com"
SMTP_PORT = int(os.environ.get("SMTP_PORT", "") or "465")  # 465=SSL，587=STARTTLS
SMTP_USER = os.environ.get("SMTP_USER", "").strip()           # 发件邮箱，如 xxx@qq.com
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "").strip()   # QQ 邮箱「授权码」，不是登录密码
MAIL_TO = os.environ.get("MAIL_TO", "").strip() or SMTP_USER  # 收件人，默认发给自己
MAIL_FROM_NAME = os.environ.get("MAIL_FROM_NAME", "AI Agent 日报")
MAIL_SUBJECT_PREFIX = os.environ.get("MAIL_SUBJECT_PREFIX", "🤖 AI Agent 学习速递")

# 去重历史：记录已推送过的 URL，避免每天推重复内容
HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "history.json")
HISTORY_MAX = 500  # 最多保留最近 500 条

# 北京时间
CST = timezone(timedelta(hours=8))

# ============================================================
# 去重历史
# ============================================================

def load_history() -> set:
    """读取已推送过的 URL 历史"""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return set(data) if isinstance(data, list) else set()
        except Exception as e:
            print(f"[WARN] 读取历史记录失败: {e}")
    return set()


def save_history(urls: set) -> None:
    """追加写入本次推送的 URL，只保留最近 HISTORY_MAX 条"""
    existing = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = []
    merged = list(dict.fromkeys(list(existing) + sorted(urls)))  # 去重且保序
    merged = merged[-HISTORY_MAX:]
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False)
    except Exception as e:
        print(f"[WARN] 保存历史记录失败: {e}")


def extract_urls(text: str) -> set:
    """从生成的 Markdown 里提取链接，用于记录本次实际推送的内容"""
    return set(re.findall(r"\]\((https?://[^)\s]+)\)", text))


# ============================================================
# 新闻源爬取
# ============================================================

HEADERS = {
    "User-Agent": "AI-Agent-News-Bot/1.0 (daily AI news aggregator)"
}


def fetch_hacker_news(limit: int = 30) -> list[dict]:
    """Hacker News: 热门 + 关键词搜索，双通道获取"""
    stories = []

    # 通道1：热门新闻
    try:
        resp = requests.get(
            "https://hacker-news.firebaseio.com/v0/topstories.json", timeout=15
        )
        resp.raise_for_status()
        ids = resp.json()[:limit]

        for item_id in ids:
            try:
                item = requests.get(
                    f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json",
                    timeout=10,
                ).json()
                if item and item.get("title"):
                    stories.append({
                        "title": item["title"],
                        "url": item.get("url") or f"https://news.ycombinator.com/item?id={item_id}",
                        "source": "Hacker News",
                        "score": item.get("score", 0),
                    })
            except Exception:
                continue
            time.sleep(0.05)
    except Exception as e:
        print(f"[WARN] Hacker News 热门获取失败: {e}")

    # 通道2：Algolia 关键词搜索（补获 Agent 相关帖子，只看最近 2 天）
    try:
        recent_epoch = int(time.time()) - 2 * 86400  # 最近 48 小时
        for keyword in ["agent framework", "langgraph", "crewai", "agent tutorial"]:
            resp = requests.get(
                "https://hn.algolia.com/api/v1/search",
                params={
                    "query": keyword,
                    "tags": "story",
                    "hitsPerPage": 5,
                    "numericFilters": f"created_at_i>{recent_epoch}",
                },
                timeout=15,
            )
            resp.raise_for_status()
            for hit in resp.json().get("hits", []):
                title = hit.get("title", "")
                url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
                if title:
                    stories.append({
                        "title": title,
                        "url": url,
                        "source": "Hacker News",
                        "score": hit.get("points", 0),
                    })
            time.sleep(0.3)
    except Exception as e:
        print(f"[WARN] Hacker News 关键词搜索失败: {e}")

    return stories


def fetch_reddit(subreddits: list[str] = None) -> list[dict]:
    """Reddit 多个 subreddit 热门 — 使用 RSS feed 绕过 API 限制"""
    if subreddits is None:
        subreddits = ["MachineLearning", "LocalLLaMA", "artificial", "singularity"]

    stories = []
    for sub in subreddits:
        try:
            # 使用 .rss 方式，比 JSON API 更不容易被拦截
            url = f"https://www.reddit.com/r/{sub}/.rss?limit=15"
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()

            import xml.etree.ElementTree as ET
            root = ET.fromstring(resp.text)
            for entry in root.findall(".//entry"):
                title_el = entry.find("title")
                link_el = entry.find("link")
                if title_el is not None and title_el.text:
                    stories.append({
                        "title": title_el.text.strip(),
                        "url": link_el.get("href") if link_el is not None else "",
                        "source": f"r/{sub}",
                        "score": 0,
                    })
            time.sleep(1)  # 避免 429 频率限制
        except Exception as e:
            print(f"[WARN] Reddit r/{sub} 获取失败: {e}")

    return stories


def fetch_github_trending(languages: list[str] = None) -> list[dict]:
    """GitHub 搜索 AI Agent 相关仓库 — 免费 Search API（限速 10req/min）"""
    queries = [
        # 热门 Agent 框架（按名称搜）
        "langgraph",
        "crewai",
        "autogen agent",
        "metagpt",
        "auto-gpt",
        # 教程和入门资源
        "agent tutorial beginner",
        "build ai agent from scratch",
        "llm agent architecture",
        # 工具/平台
        "agentops",
        "agent memory tool",
    ]
    repos_all = []
    seen = set()

    for q in queries:
        try:
            params = {
                "q": q,
                "sort": "stars",
                "order": "desc",
                "per_page": 8,
            }
            resp = requests.get(
                "https://api.github.com/search/repositories",
                params=params,
                headers={**HEADERS, "Accept": "application/vnd.github.v3+json"},
                timeout=15,
            )
            resp.raise_for_status()
            items = resp.json().get("items", [])
            for r in items:
                full_name = r["full_name"]
                if full_name in seen:
                    continue
                seen.add(full_name)
                repos_all.append({
                    "title": f"{full_name}: {r.get('description') or '(无描述)'}",
                    "url": r["html_url"],
                    "source": "GitHub",
                    "score": r.get("stargazers_count", 0),
                })
            time.sleep(2)  # GitHub API 限速：每分钟 10 次无认证请求
        except Exception as e:
            print(f"[WARN] GitHub 搜索 '{q}' 失败: {e}")

    return repos_all


def fetch_arxiv_agent_papers(max_results: int = 15) -> list[dict]:
    """arXiv 最新 AI Agent 论文"""
    papers = []
    try:
        query = (
            "all:(agent framework) OR all:(LLM agent) OR all:(multi-agent collaboration) "
            "OR all:(tool use agent) OR all:(function calling agent) OR all:(agentic workflow) "
            "OR all:(retrieval augmented agent)"
        )
        params = {
            "search_query": query,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": max_results,
        }
        resp = requests.get(
            "http://export.arxiv.org/api/query", params=params, timeout=20
        )
        resp.raise_for_status()

        # 简单解析 XML（避免引入额外依赖）
        import xml.etree.ElementTree as ET
        root = ET.fromstring(resp.text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        for entry in root.findall("atom:entry", ns):
            title_el = entry.find("atom:title", ns)
            summary_el = entry.find("atom:summary", ns)
            link_el = entry.find("atom:id", ns)

            title = title_el.text.strip().replace("\n", " ") if title_el is not None else ""
            summary = summary_el.text.strip().replace("\n", " ")[:200] if summary_el is not None else ""
            url = link_el.text.strip() if link_el is not None else ""

            if title:
                papers.append({
                    "title": title,
                    "url": url,
                    "source": "arXiv",
                    "score": 0,
                    "summary_en": summary,
                })
    except Exception as e:
        print(f"[WARN] arXiv 获取失败: {e}")

    return papers


def fetch_all_news() -> list[dict]:
    """并发爬取所有新闻源，返回去重后的新闻列表"""
    all_stories = []

    print("[INFO] 开始爬取新闻源...")
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(fetch_hacker_news, 30): "HackerNews",
            executor.submit(fetch_reddit): "Reddit",
            executor.submit(fetch_github_trending): "GitHub",
            executor.submit(fetch_arxiv_agent_papers, 15): "arXiv",
        }

        for future in as_completed(futures):
            source = futures[future]
            try:
                results = future.result()
                print(f"[INFO] {source}: 获取 {len(results)} 条")
                all_stories.extend(results)
            except Exception as e:
                print(f"[ERROR] {source} 异常: {e}")

    # 按标题去重
    seen_titles = set()
    unique = []
    for s in all_stories:
        key = s["title"].lower()[:100]
        if key not in seen_titles:
            seen_titles.add(key)
            unique.append(s)

    print(f"[INFO] 去重后共 {len(unique)} 条新闻")
    return unique


# ============================================================
# DeepSeek 翻译 + 摘要
# ============================================================

def summarize_with_deepseek(stories: list[dict]) -> str:
    """将新闻列表发给 DeepSeek，让它筛选、翻译、摘要"""

    # 构建新闻列表文本
    news_text = ""
    for i, s in enumerate(stories, 1):
        news_text += f"{i}. [{s['source']}] {s['title']}\n   URL: {s['url']}\n\n"

    today_str = datetime.now(CST).strftime("%Y年%m月%d日")

    system_prompt = (
        "你是一个贴心的 AI 学习助手，专门帮助正在学习 AI Agent 开发的新手（学了约半个月）。"
        "你的读者了解 Python 基础，但对 Agent 框架（LangGraph、CrewAI、AutoGen 等）还不太熟。"
        "你的任务是：从新闻中挑出对新手最有学习价值的内容，"
        "用通俗易懂的中文解释每条新闻「说的是什么」「为什么值得关注」「能学到什么」。"
    )

    user_prompt = f"""下面是今天从 Hacker News、Reddit、GitHub、arXiv 等渠道收集的技术内容。

请完成以下任务：

1. **筛选**：优先选择以下类型的内容（按优先级排列）：
   - 🥇 热门 Agent 框架（LangGraph/CrewAI/AutoGen/MetaGPT/Dify/Coze 等）的新版本、新功能、教程
   - 🥈 「手把手教你搭建 Agent」「从零实现 Agent」类实战教程/博客
   - 🥉 对新手友好的 Agent 设计模式、架构讲解
   - 可捎带 1-2 条重大行业新闻（如 OpenAI/Anthropic 的 Agent 产品发布）
   - ❌ 跳过纯学术论文（除非有开源代码+对新手有实战价值）
   - ❌ 跳过纯产品营销文章

2. **去重**：同一事件只保留一条。

3. **翻译+讲解**：对每条内容用中文写出：
   - 标题（翻译成中文）
   - 用一句话说清楚「这是什么」
   - 用 1-2 句话说明「对正在学 Agent 开发的人有什么价值 / 能学到什么」

4. **难度标签**：每条加一个标签：
   - 🟢 新手友好（不需要先验知识）
   - 🟡 需要基础（建议了解过 Python + LLM 基本概念）
   - 🔴 进阶（适合深入理解原理）

5. **数量**：最终保留 5-8 条。

6. **末尾推荐**：从今天的内容中挑一个最适合动手的，写上「今日推荐动手」简短说明。

请严格按照以下 Markdown 格式输出：

# 🤖 AI Agent 学习速递 | {today_str}

---

**N. 🟢 中文标题**
📎 来源：GitHub
📖 是什么：一句话说清楚
💡 学习价值：1-2句话，讲清楚对新手有什么帮助
🔗 [原文](url)

...

---

## 🛠 今日推荐动手
> 从今天内容中挑一个最适合新手动手的，说明要做什么、能学到什么。

---

*📡 自动生成 | 数据来源: Hacker News · Reddit · GitHub · arXiv*

---
以下是待筛选的内容列表：

{news_text}"""

    print(f"[INFO] 发送 {len(stories)} 条新闻给 DeepSeek 处理...")

    try:
        resp = requests.post(
            f"{DEEPSEEK_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": DEEPSEEK_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.3,
                "max_tokens": 4096,
            },
            timeout=120,
        )
        resp.raise_for_status()
        result = resp.json()
        summary = result["choices"][0]["message"]["content"]
        print(f"[INFO] DeepSeek 处理完成，返回 {len(summary)} 字符")
        return summary

    except Exception as e:
        print(f"[ERROR] DeepSeek API 调用失败: {e}")
        raise


# ============================================================
# 邮件推送（SMTP）
# ============================================================

def markdown_to_html(md: str) -> str:
    """把摘要 Markdown 转成简易 HTML（不引入额外依赖）"""
    import html as _html

    out = []
    for raw in md.split("\n"):
        line = raw.rstrip()
        if line.strip() == "---":
            out.append("<hr>")
        elif line.startswith("# "):
            out.append(f"<h2>{_html.escape(line[2:])}</h2>")
        elif line.startswith("## "):
            out.append(f"<h3>{_html.escape(line[3:])}</h3>")
        elif line.startswith("> "):
            out.append(f"<blockquote>{_html.escape(line[2:])}</blockquote>")
        elif line.strip() == "":
            continue
        else:
            out.append(f"<p>{_html.escape(line)}</p>")
    body = "\n".join(out)

    # 行内格式：加粗 / 链接 / 斜体
    body = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", body)
    body = re.sub(r"\[(.+?)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', body)
    body = re.sub(r"\*(.+?)\*", r"<em>\1</em>", body)
    return body


def send_email(content: str, subject_date: str) -> bool:
    """通过 SMTP 发送 HTML 邮件"""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from email.header import Header
    from email.utils import formataddr

    if not SMTP_USER or not SMTP_PASSWORD:
        print("[ERROR] 未配置 SMTP_USER / SMTP_PASSWORD，无法发信")
        return False

    subject = f"{MAIL_SUBJECT_PREFIX} | {subject_date}"
    html_body = markdown_to_html(content)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = formataddr((str(Header(MAIL_FROM_NAME, "utf-8")), SMTP_USER))
    msg["To"] = MAIL_TO
    msg.attach(MIMEText(content, "plain", "utf-8"))  # 纯文本兜底
    msg.attach(MIMEText(html_body, "html", "utf-8"))  # HTML 正文

    try:
        if SMTP_PORT == 465:
            server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=20)
        else:
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20)
            server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_USER, [MAIL_TO], msg.as_string())
        server.quit()
        print(f"[OK] 邮件已发送到 {MAIL_TO}")
        return True
    except Exception as e:
        print(f"[ERROR] 邮件发送失败: {e}")
        return False


# ============================================================
# 主流程
# ============================================================

def main():
    print("=" * 60)
    print(f"AI Agent 每日新闻推送 — {datetime.now(CST).strftime('%Y-%m-%d %H:%M')} CST")
    print("=" * 60)

    # 1. 爬取新闻
    stories = fetch_all_news()
    if not stories:
        print("[ERROR] 未获取到任何新闻，终止")
        return

    # 2. 过滤掉历史已推送过的内容
    history = load_history()
    fresh = [s for s in stories if s["url"] not in history]
    print(f"[INFO] 过滤已推送历史后剩余 {len(fresh)} 条（历史 {len(history)} 条）")
    if not fresh:
        print("[WARN] 今日内容全部推送过，改用全部内容继续（避免空推）")
        fresh = stories

    # 3. DeepSeek 筛选 + 翻译 + 摘要
    try:
        summary = summarize_with_deepseek(fresh)
    except Exception:
        print("[FATAL] DeepSeek 处理失败，无法继续")
        return

    # 打印预览（终端可能不支持 emoji，跳过显示错误）
    print("\n" + "-" * 40)
    try:
        print(summary)
    except UnicodeEncodeError:
        print("[INFO] 摘要已生成（含 emoji/中文，终端无法显示，但推送不受影响）")
        print(f"[INFO] 摘要长度: {len(summary)} 字符")
    print("-" * 40 + "\n")

    # 4. 发送邮件（成功后才记录历史，避免发送失败却把内容标记为已发）
    today_str = datetime.now(CST).strftime("%Y年%m月%d日")
    success = send_email(summary, today_str)
    if success:
        sent_urls = extract_urls(summary) or {s["url"] for s in fresh}
        save_history(sent_urls)
        print(f"[INFO] 已记录 {len(sent_urls)} 条链接到去重历史")
        print("[DONE] 日报已通过邮件发送！")
    else:
        print("[FAIL] 邮件发送失败，请检查 SMTP 配置！")
        print("[HINT] 排查：")
        print("  1. SMTP_USER / SMTP_PASSWORD 是否正确（QQ 邮箱需用「授权码」而非登录密码）")
        print("  2. 是否已在 QQ 邮箱「设置 → 账户 → 开启 SMTP 服务」")
        print("  3. MAIL_TO 收件人地址是否正确")


if __name__ == "__main__":
    main()
