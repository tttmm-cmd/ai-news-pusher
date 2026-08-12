# 🤖 AI Agent 每日新闻推送

> 多源爬取 AI Agent 领域最新内容 → DeepSeek 翻译筛选摘要 → 推送到微信  
> 每天早上一杯咖啡的时间，了解 AI Agent 圈发生了什么

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue?logo=python" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
  <img src="https://img.shields.io/badge/Deploy-GitHub_Actions-2088FF?logo=githubactions" alt="GitHub Actions">
</p>

---

## 📸 效果预览

每天早上 8:30，微信会收到一条这样的消息：

```markdown
# 🤖 AI Agent 学习速递 | 2026年08月12日

---

1. 🟢 LangGraph 发布 v0.4：新增子图并行执行
📎 来源：GitHub
📖 是什么：LangGraph 框架的重大更新
💡 学习价值：新手可以学习如何用子图模式构建复杂 Agent 工作流
🔗 [原文](https://github.com/langchain-ai/langgraph)

2. 🟡 从零构建多 Agent 协作系统：一份完整的 Python 教程
📎 来源：Hacker News
...

---
## 🛠 今日推荐动手
> 尝试用 LangGraph 的 subgraph 功能把两个独立 Agent 串联起来...
---

📡 自动生成 | 数据来源: Hacker News · Reddit · GitHub · arXiv
```

---

## 🧩 工作原理

```
┌──────────────┐
│  Hacker News │──┐
├──────────────┤  │
│    Reddit    │──┤  并发爬取 + 去重
├──────────────┤  │
│ GitHub Trend │──┼──────────────────┐
├──────────────┤  │                  ▼
│    arXiv     │──┘         ┌──────────────┐
└──────────────┘            │   DeepSeek   │
                            │  筛选·翻译·摘要 │
                            │  难度标签·推荐  │
                            └──────┬───────┘
                                   ▼
                            ┌──────────────┐
                            │   WxPusher   │
                            │  推送到微信    │
                            └──────────────┘
```

---

## 🚀 快速开始

### 准备工作（5 分钟）

你需要注册 3 个账号，获取 3 个 Key：

| # | 平台 | 做什么 | 拿到什么 |
|---|------|--------|---------|
| 1 | [WxPusher](https://wxpusher.zjiecode.com/) | 注册 → 创建应用 | **AppToken**（`AT_` 开头）|
| 2 | WxPusher 后台 → 用户管理 | 用微信扫码关注自己的应用 | **UID**（`UID_` 开头，不是 `AT_`！）|
| 3 | [DeepSeek](https://platform.deepseek.com/) | 注册 → API Keys | **API Key**（`sk-` 开头）|

> 💰 费用：DeepSeek API 按量计费，每推送一次大约几分钱，一个月不到 2 元。

### 本地运行

```bash
# 1. 克隆项目
git clone https://github.com/tttmm-cmd/ai-news-pusher.git
cd ai-news-pusher

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入上面获取的 3 个 Key

# 3. 安装依赖（只需要 requests）
pip install -r requirements.txt

# 4. 运行
python main.py
```

成功的话，你的微信几秒内就会收到推送。

### GitHub Actions 每日自动运行

已经配好了 `.github/workflows/daily.yml`，每天早上 8:30（北京时间）自动执行。

你只需要在 GitHub 仓库中配置 Secrets：

> **Settings → Secrets and variables → Actions → New repository secret**

添加 3 个 Secret：

| Name | 值 |
|------|-----|
| `DEEPSEEK_API_KEY` | 你的 DeepSeek API Key |
| `WXPUSHER_APP_TOKEN` | 你的 WxPusher AppToken |
| `WXPUSHER_UID` | 你的 WxPusher UID |

配置好后，点击 Actions 标签 → 选择 "AI Agent 每日新闻推送" → **Run workflow** 手动触发一次测试。

---

## 📁 项目结构

```
ai-news-pusher/
├── main.py              # 主程序（爬虫 + AI 处理 + 推送）
├── requirements.txt     # 依赖（仅 requests）
├── .env.example         # 环境变量模板
├── .gitignore           # 防止 .env 被提交
└── .github/
    └── workflows/
        └── daily.yml    # GitHub Actions 定时任务
```

---

## 🔧 高级玩法：改成你自己的内容

这个项目的核心是一个**可复用的管道**：

```
爬取数据源 → LLM 处理 → 微信推送
```

你只需要改 3 个地方，就能变成任何领域的日报，下面是完整的改造指南。

### 第一步：换数据源（`fetch_*` 函数）

目前项目从 Hacker News、Reddit、GitHub、arXiv 爬 AI Agent 相关内容。要改成其他领域，替换爬虫函数即可。项目使用 **ThreadPoolExecutor 并发执行**，你写的新爬虫只要返回统一格式就能无缝接入：

```python
# 每个爬虫函数返回这个格式的列表
[{
    "title": "标题",
    "url": "链接",
    "source": "来源名称",
    "score": 0,  # 可选，用于排序
}]
```

### 第二步：换 LLM Prompt（`summarize_with_deepseek` 函数）

修改 `system_prompt` 和 `user_prompt`，让 AI 按你需要的角度筛选和解读内容。

### 第三步：换 LLM 服务商（可选）

把 `DEEPSEEK_BASE_URL` 换成任何兼容 OpenAI API 的服务（通义千问、智谱 GLM、Moonshot 等），只改环境变量即可。

---

## 🌾 案例：改成「作物栽培学」每日学术推送

假设你的农学专业朋友想要这个效果：

> 每天早上推送作物栽培学领域的最新论文、研究进展、技术动态

以下是具体做法，每步都是改 `main.py` 里的对应函数。

### 需要改的爬虫

| 原函数 | 改造方案 | 难度 |
|--------|---------|------|
| `fetch_arxiv_agent_papers` | 换搜索关键词为农学相关 | 🟢 1 分钟 |
| `fetch_hacker_news` | 删除或换成农业新闻 RSS | 🟡 20 分钟 |
| `fetch_reddit` | 换成 r/Agriculture、r/farming 等 | 🟢 1 分钟 |
| `fetch_github_trending` | 换搜索词或换成 PubMed / Semantic Scholar | 🟡 30 分钟 |

### 推荐农学数据源（免费，无需 API Key）

**1. Semantic Scholar API** — 学术论文搜索引擎，覆盖各学科

```python
url = "https://api.semanticscholar.org/graph/v1/paper/search"
params = {
    "query": "crop cultivation OR crop modeling OR precision agriculture",
    "limit": 20,
    "fields": "title,url,abstract,publicationDate"
}
```

**2. PubMed Entrez API** — 生物/农学文献最全的数据库

```python
url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
params = {
    "db": "pubmed",
    "term": "crop cultivation[Title/Abstract] OR plant breeding[Title/Abstract]",
    "retmax": 20,
    "sort": "date",
    "retmode": "json"
}
# 拿到 PMID 列表后，再用 efetch 获取标题和摘要
```

**3. CrossRef API** — 覆盖所有 DOI 论文的元数据

```python
url = "https://api.crossref.org/works"
params = {
    "query": "crop cultivation precision agriculture",
    "rows": 20,
    "sort": "published",
    "filter": "type:journal-article"
}
```

> 这三个 API 都**免费、无需注册**，直接发 HTTP 请求就能用。任选 1-2 个就能覆盖农学主要期刊。

### 改 DeepSeek Prompt

把 `system_prompt` 和 `user_prompt` 里的角色从 "AI 学习助手" 改成 "作物栽培学学术助手"：

```python
system_prompt = (
    "你是一位资深的作物栽培学学术助手，专门帮助研究生和科研人员"
    "快速了解本领域的最新研究进展。你的读者具有农学本科以上背景，"
    "关注作物栽培、生理生态、精准农业、育种等领域。"
    "你的任务是：从论文和新闻中筛选出最有学术价值的内容，"
    "用专业但不晦涩的中文解释每项研究的内容和意义。"
)

# user_prompt 里的筛选标准改成：
# - 🥇 作物栽培学重要期刊的最新论文
# - 🥈 作物模型、遥感监测、精准农业技术新进展
# - 🥉 与气候变化相关的作物适应性研究
# - ❌ 跳过纯商业推广文章
# - ❌ 跳过已广泛报道的旧闻
```

### 改造后效果预览

```
# 🌾 作物栽培学术速递 | 2026年08月12日

---

1. 🔬 高温胁迫下小麦籽粒灌浆的蛋白质组学分析
📎 来源：Field Crops Research
📖 研究了什么：利用蛋白质组学技术解析高温对小麦灌浆期的影响机制
💡 研究意义：为耐热品种选育提供了新的分子标记靶点
🔗 [原文](https://doi.org/...)

2. 📊 基于无人机多光谱影像的玉米氮素营养诊断
📎 来源：Precision Agriculture
...
```

### 改造工作量

| 改什么 | 难度 | 时间 |
|--------|------|------|
| 换 arXiv 搜索词 | 🟢 简单（改一个字符串）| 1 分钟 |
| 加 Semantic Scholar / CrossRef 爬虫 | 🟡 中等（新增函数，约 30 行）| 20 分钟 |
| 改 DeepSeek Prompt | 🟢 简单（改两个字符串）| 5 分钟 |
| 换微信推送标题和格式 | 🟢 简单 | 2 分钟 |
| **总计** | — | **1 小时内完成** |

### 我朋友不会写代码怎么办？

把这份 README 里「🌾 案例」这段发给 ChatGPT 或 Claude，附上 `main.py` 的代码，说：

> "帮我把这个项目改成作物栽培学学术论文每日推送，用 Semantic Scholar 和 PubMed API 替换现有数据源，Prompt 也改成农学方向的"

AI 会直接帮你朋友生成完整的改后代码，复制粘贴就能用。

---

## ⚠️ 安全提示

- **绝对不要把 `.env` 文件提交到 Git！** `.gitignore` 已经排除了它
- 如果你曾经 commit 过含真实 Token 的 `.env`，去对应平台重置 Token
- GitHub Actions 的 Secret 不会在日志中显示，放心使用

---

## 📄 License

MIT — 随便改、随便用，Fork 后改成你自己的日报吧 🎉
