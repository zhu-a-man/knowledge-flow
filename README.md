# KnowledgeFlow · 让碎片信息自己长成知识图谱

> 把你每天刷到的公众号文章、网页链接发给微信龙虾机器人，AI 自动提炼要点、分类归档，累积为一棵可视化的个人知识树。

---

## 它解决什么问题

你每天读了很多好文章，但过了三天全忘了。收藏夹堆满了，从来不打开第二次。

KnowledgeFlow 的思路是：**读的时候顺手发给龙虾，让它帮你提炼和归类**，慢慢就有了一棵按主题生长的知识树，想找的时候打开 `/view` 页面一眼看到。

---

## 效果预览

```
知识树示例：
├── AI工具
│   ├── 编程助手（3篇来源 · 8个要点）
│   │   · Cursor — 写代码时 AI 实时补全，速度快到不像话
│   │   · GitHub Copilot — 适合多语言切换的开发者
│   └── 写作工具（2篇来源 · 5个要点）
│       · Notion AI — 直接在笔记里用，不用切换工具
└── 效率方法
    └── 工具选型（1篇来源 · 3个要点）
        · 用"解决哪个具体问题"来选工具，不要用"功能多不多"
```

---

## 架构

```
微信 / OpenClaw
      ↓ 发链接或文字
  SKILL.md（触发规则 + API 调用格式）
      ↓ REST API
  FastAPI 服务（Railway 云端部署）
      ↓
  extractor.py     →  从 URL 抓取正文（trafilatura + requests）
  ai_processor.py  →  AI 提炼结构化知识（DeepSeek / 通义 / Claude）
  knowledge_store.py → 存储到 PostgreSQL（永久，不随部署丢失）
      ↓
  /view 页面  →  纯 HTML 可折叠知识树（无 CDN 依赖）
```

---

## 快速开始

### 前置条件

- [Railway](https://railway.app) 账号（免费额度够用）
- [DeepSeek](https://platform.deepseek.com) API Key（推荐，国内直连，充10元用数月）
- 微信已接入 OpenClaw（`npx -y @tencent-weixin/openclaw-weixin-cli@latest install`）或其他龙虾平台

### 一键部署

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new/template)

**或手动部署（推荐，方便自定义）：**

```bash
git clone https://github.com/your-username/knowledge-flow.git
cd knowledge-flow
# 然后按照 docs/setup-guide.md 操作
```

→ 完整部署步骤见 [docs/setup-guide.md](docs/setup-guide.md)

---

## 文件结构

```
knowledge-flow/
├── mcp_server.py        # FastAPI 主服务（MCP + REST API + 知识树页面）
├── ai_processor.py      # AI 提取模块（支持 DeepSeek / 通义 / Claude）
├── knowledge_store.py   # 数据存储（PostgreSQL 优先，本地降级 SQLite）
├── extractor.py         # URL 内容抓取（requests + trafilatura）
├── mindmap_renderer.py  # 知识树 HTML 渲染（纯 HTML，无 JS 依赖）
├── requirements.txt
├── Dockerfile
├── railway.toml
├── .env.example
├── skill.md             # ← OpenClaw 技能文件（安装到龙虾使用这个）
└── docs/
    ├── setup-guide.md   # 从零到一完整部署手册
    ├── architecture.md  # 技术架构决策说明
    ├── prompt-design.md # AI 提取 Prompt 设计原理
    └── gotchas.md       # 实际踩过的坑与解决方案
```

---

## 接入 OpenClaw（微信龙虾机器人）

部署完成后，将 `skill.md` 的内容复制到你的龙虾平台技能中心，填入你的服务地址和 API Key 即可。

详见 [docs/setup-guide.md#接入-openclaw](docs/setup-guide.md#接入-openclaw)

---

## 支持的 AI 模型

| 模型 | 推荐指数 | 国内直连 | 费用 |
|------|---------|---------|------|
| DeepSeek-V3 | ⭐⭐⭐⭐⭐ | ✅ | ~¥0.002/篇 |
| 通义千问 Plus | ⭐⭐⭐⭐ | ✅ | 有免费额度 |
| Claude Sonnet | ⭐⭐⭐⭐⭐ | ❌ 需代理 | ~¥0.01/篇 |

---

## 文档索引

| 文档 | 内容 |
|------|------|
| [setup-guide.md](docs/setup-guide.md) | Railway 部署 + PostgreSQL + OpenClaw 接入全流程 |
| [architecture.md](docs/architecture.md) | 每个架构决策的原因（为什么这样设计） |
| [prompt-design.md](docs/prompt-design.md) | AI 提取 Prompt 的设计原理与最佳实践 |
| [gotchas.md](docs/gotchas.md) | 实际踩过的坑（Railway 数据丢失、公众号提取失败等） |

---

## License

MIT
