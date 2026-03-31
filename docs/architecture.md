# KnowledgeFlow 架构设计说明

本文记录每个关键技术决策背后的「为什么」，帮助想 fork 改造的开发者理解系统逻辑。

---

## 整体架构

```
用户（微信/OpenClaw）
    ↓ 发链接或文字
SKILL.md（触发规则）
    ↓ HTTP 调用
FastAPI 服务（Railway 云端）
    ├── /mcp        MCP Server（供支持 MCP 协议的龙虾连接）
    ├── /api/*      REST API（供不支持 MCP 的平台调用）
    └── /view       知识树 HTML 页面
    ↓
extractor.py        URL 内容抓取
ai_processor.py     AI 结构化提取
knowledge_store.py  PostgreSQL 存储
mindmap_renderer.py HTML 知识树渲染
```

---

## 决策一：为什么用 FastAPI 而不是 Streamlit

**v1 版本（已废弃）** 使用 Streamlit 作为 UI 框架。

**问题**：Streamlit 是 Web UI 框架，没有办法暴露 REST API 供外部（OpenClaw）调用。要让龙虾能调用知识库，必须有一个标准的 HTTP 接口层。

**选择 FastAPI**：
- 同时支持 MCP Server（`/mcp` 路径）和 REST API（`/api/*` 路径）
- 性能好，部署简单
- 可以在同一个进程里同时服务 API 和 HTML 页面

---

## 决策二：为什么同时暴露 MCP 和 REST 两套接口

**MCP（Model Context Protocol）**：
- OpenClaw 原生支持，连接后龙虾可以直接调用 Python 函数（`save_article`、`save_text` 等）
- 优点：类型安全，错误处理更好

**REST API（`/api/*`）**：
- 适配不支持 MCP 协议的平台（如公司自建龙虾平台、n8n、Zapier 等）
- 通过 SKILL.md 触发规则 + HTTP 调用实现

**结论**：两套都保留，用同一套业务逻辑，只是接入层不同。

---

## 决策三：为什么从 SQLite 改为 PostgreSQL

**v1、v2 版本**：用 SQLite 文件（`knowledge_base.db`）存储。

**问题**：Railway 的容器**每次部署都会重置文件系统**，SQLite 文件随容器消失，数据每次更新代码后都丢失。

尝试过用 Railway Volume（持久磁盘）：
- 配置复杂（需要在 Railway Dashboard 手动创建 Volume 并挂载）
- `railway.toml` 的 `[[volumes]]` 声明**不会自动创建磁盘**，需要在后台手动操作

**最终方案：Railway PostgreSQL 插件**：
- 一键添加，Railway 自动注入 `DATABASE_URL` 到同项目的服务
- 独立于容器，不随部署消失
- 完全免费（Railway 免费额度内）

**兼容性**：`knowledge_store.py` 检测 `DATABASE_URL` 环境变量：
- 有 → 使用 PostgreSQL
- 无 → 降级为 SQLite（本地开发用，不需要 PostgreSQL）

---

## 决策四：为什么从 markmap 改为原生 HTML `<details>`

**v1、v2 版本**：用 markmap（一个 JS 思维导图库）渲染知识树。

连续踩了三个坑：

1. **CDN 加载顺序问题**：`markmap-view` 和 `markmap-lib` 都写入 `window.markmap`，加载顺序颠倒会导致白屏，且没有报错
2. **iframe CSP 限制**：Streamlit 的 `components.html()` 在 iframe 里渲染，某些网络环境会拦截 CDN 脚本
3. **iframe srcdoc 转义**：HTML 里的模板字符串（反引号、`$`）插入 `srcdoc` 属性时需要多层转义，极其脆弱

**最终方案**：用原生 HTML `<details>/<summary>` 标签实现可折叠树：
- **零 JS 依赖**：浏览器原生支持，不需要 CDN
- **可靠性 100%**：没有 CDN 超时、没有 namespace 冲突、没有转义问题
- **移动端友好**：原生支持触摸折叠，不需要 JS 事件
- **代码简单**：`mindmap_renderer.py` 的 `kb_to_html_tree()` 只有约 60 行 Python

---

## 决策五：为什么 AI 输出格式改为 `entries` 数组

**v1、v2 版本**：AI 每次返回单条 `{topic, dimension, key_points}`。

**问题**：一篇文章常常横跨多个领域。例如"10个AI效率工具"既有具体工具推荐（`AI工具 › 编程助手`），又有选工具的方法论（`效率方法 › 工具选型`）。强制归入单个 topic 会导致要么分类混乱，要么信息丢失。

**新格式**：
```json
{
  "summary": "几个工具装上去效率翻倍",
  "entries": [
    {"topic": "AI工具", "dimension": "编程助手", "key_points": [...]},
    {"topic": "效率方法", "dimension": "工具选型", "key_points": [...]}
  ]
}
```

**好处**：
- 同一篇文章贡献给知识树的多个节点
- 知识树越积累越聚合（同 topic 的内容自动归并）
- URL 去重时一次性删除该 URL 的所有旧条目，重新插入

---

## 决策六：为什么用 psycopg2 而不是 SQLAlchemy

**考虑过 SQLAlchemy**：功能强大，ORM 模式，代码更面向对象。

**选择 psycopg2-binary**：
- KnowledgeFlow 的数据库操作很简单（几张表，几个查询），不需要 ORM
- SQLAlchemy 需要额外设计 Model 层，增加代码量
- psycopg2 直接写 SQL，透明可控，好调试

**注意事项**（psycopg2 新手必知）：
- 占位符是 `%s`，不是 SQLite 的 `?`
- 获取插入 ID 用 `RETURNING id`，不是 `cursor.lastrowid`
- 需要显式 `conn.commit()` 或 `conn.rollback()`

---

## 决策七：为什么 Prompt 的角色是"朋友"而不是"专家"

测试过两种角色设定：

**"知识管理专家"角色输出**：
> "该工具具备AI辅助代码补全功能，可显著提升开发效率，适用于专业软件开发场景"

**"最懂你的朋友"角色输出**：
> "Cursor — 写代码时 AI 实时补全，速度快到不像话"

前者像产品说明书，后者让人想看下去。知识库的本质是"日后的自己能快速找回并理解"，口语化的表达更贴近思维方式，检索体验更好。

---

## 数据库表结构

```sql
-- 每篇文章 × 每个 topic/dimension = 一行
CREATE TABLE kb_entries (
    id         SERIAL PRIMARY KEY,
    url        TEXT NOT NULL DEFAULT '',
    title      TEXT NOT NULL DEFAULT '',
    platform   TEXT NOT NULL DEFAULT '',
    summary    TEXT NOT NULL DEFAULT '',
    topic      TEXT NOT NULL,
    dimension  TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- 要点，通过 entry_id 关联（CASCADE 自动删除）
CREATE TABLE kb_points (
    id       SERIAL PRIMARY KEY,
    entry_id INTEGER NOT NULL REFERENCES kb_entries(id) ON DELETE CASCADE,
    point    TEXT NOT NULL
);
```

**URL 去重逻辑**：
```python
# 同一 URL 再次保存时：删旧插新
DELETE FROM kb_entries WHERE url = %s AND url != '';
# kb_points 通过 ON DELETE CASCADE 自动跟着删
```
