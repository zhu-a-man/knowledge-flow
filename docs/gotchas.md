# 避坑手册

实际开发和部署过程中踩过的坑，按严重程度排序。

---

## 🔴 高危坑（不处理必出问题）

### 坑1：Railway 容器是临时的，数据每次部署都会消失

**现象**：每次推送代码更新，知识库里的内容全没了。

**原因**：Railway 部署会销毁旧容器、创建新容器，容器内的文件系统（包括 SQLite 数据库）随之消失。

**错误认知**：`railway.toml` 里写 `[[volumes]] mountPath = "/data"` 不会自动创建持久磁盘，只是声明而已，必须在 Railway Dashboard 手动创建 Volume 并挂载。

**正确解法**：在同一个 Railway 项目里添加 PostgreSQL 插件（`+ New → Database → PostgreSQL`），然后在 knowledge-flow 服务的 Variables 里添加 `DATABASE_URL`。Railway 会自动注入连接字符串，代码检测到后使用 PostgreSQL 存储，完全独立于容器。

```python
# knowledge_store.py 的自动切换逻辑
DATABASE_URL = os.getenv("DATABASE_URL", "")
USE_POSTGRES = bool(DATABASE_URL)
# 有 DATABASE_URL → PostgreSQL（Railway）
# 无 DATABASE_URL → SQLite（本地开发）
```

---

### 坑2：PostgreSQL 和 knowledge-flow 必须在同一个 Railway 项目

**现象**：明明创建了 PostgreSQL，knowledge-flow 的 Variables 里还是没有 `DATABASE_URL`。

**原因**：Railway 的 `DATABASE_URL` 自动注入只在**同一个项目**内有效。如果 Postgres 在项目 A，knowledge-flow 在项目 B，不会自动连通。

**解法**：在 knowledge-flow 所在的项目里重新创建 PostgreSQL，或者手动把 Postgres 的连接字符串复制到 knowledge-flow 的 Variables。

---

### 坑3：trafilatura 不支持自定义 headers，公众号返回 403

**现象**：调用 `trafilatura.fetch_url(url)` 提取公众号文章，返回空内容或错误。

**原因**：`trafilatura.fetch_url()` 内部使用 `urllib`，不支持传入 `User-Agent` 等 headers。微信、知乎等平台会拦截无 UA 的请求，返回 403 或登录页。

**错误写法**：
```python
text = trafilatura.extract(trafilatura.fetch_url(url))  # 返回空
```

**正确写法**：用 requests 先下载 HTML，再交给 trafilatura 解析：
```python
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
}
html = requests.get(url, headers=headers, timeout=15).text
text = trafilatura.extract(html, favor_recall=True)
```

`favor_recall=True` 可减少漏提取，但会多抓一些噪声内容，对 AI 提炼影响不大。

---

### 坑4：psycopg2 的占位符是 `%s`，不是 `?`

**现象**：把 SQLite 查询复制过来在 PostgreSQL 里运行，报 `syntax error`。

**原因**：
- SQLite（sqlite3 模块）：占位符是 `?`
- PostgreSQL（psycopg2 模块）：占位符是 `%s`

**对比**：
```python
# SQLite
conn.execute("SELECT * FROM kb_entries WHERE url = ?", (url,))

# PostgreSQL
cur.execute("SELECT * FROM kb_entries WHERE url = %s", (url,))
```

---

### 坑5：PostgreSQL 获取插入 ID 用 `RETURNING id`，不是 `lastrowid`

**现象**：psycopg2 的 `cursor.lastrowid` 永远返回 `None`。

**原因**：`lastrowid` 是 sqlite3 的 API，psycopg2 不支持。

**正确写法**：
```python
cur.execute(
    "INSERT INTO kb_entries (...) VALUES (...) RETURNING id",
    (...)
)
entry_id = cur.fetchone()[0]
```

---

## 🟡 中危坑（影响功能，需要处理）

### 坑6：AI 返回 JSON 带代码块标记

**现象**：`json.loads()` 报 `JSONDecodeError`，但 AI 明明返回了 JSON。

**原因**：即使 Prompt 说"只返回 JSON"，模型偶尔会用 markdown 代码块包裹：
````
```json
{"topic": "AI工具", ...}
```
````

**解法**：用正则预处理：
```python
def _parse_json_safely(raw: str) -> dict:
    raw = raw.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, re.IGNORECASE)
    if match:
        raw = match.group(1).strip()
    return json.loads(raw)
```

---

### 坑7：markmap 在 iframe 里不显示（已用原生 HTML 替代）

**现象**：思维导图区域空白，或偶尔显示偶尔不显示。

**原因（多重叠加）**：
1. `markmap-view` 和 `markmap-lib` 都写入 `window.markmap`，加载顺序颠倒时后者覆盖前者，`window.markmap.Markmap` 变成 `undefined`，且**无报错**
2. 在 iframe 中加载外部 CDN 脚本，某些浏览器/网络会因 CSP 策略拦截
3. `srcdoc` 属性里的反引号、`$` 字符需要多层转义，极易出错

**最终方案**：放弃 markmap，改用原生 HTML `<details>/<summary>` 标签，零 JS 依赖，100% 可靠。

```python
# mindmap_renderer.py 的 kb_to_html_tree()
# 纯 Python 生成 HTML，不依赖任何外部库
blocks.append(f"""
<details class="topic-block" open>
  <summary>...</summary>
  <div class="topic-body">...</div>
</details>""")
```

---

### 坑8：微信公众号文章提取成功率约 70%

**现象**：有些文章链接无法提取，返回"提取内容过短"错误。

**原因**：微信公众号分两类：
- **公开文章（不需要关注）**：可以提取，成功率约 70%
- **需关注才能看 / 已被删除**：返回登录页，无法提取

这是微信的平台限制，不是代码 bug。

**处理方式**：提取失败时明确引导用户复制正文：
```python
if not text or len(text) < 50:
    return {"error": "提取内容过短，请把文章正文复制后发给我，我帮你用「保存文字」的方式存入。"}
```

SKILL.md 里也要有对应的失败回复格式，引导用户降级使用 `save-text` 接口。

---

## 🟢 低危坑（知道就好）

### 坑9：DeepSeek API Key 需要先充值才能调用

**现象**：API 返回"余额不足"错误，龙虾回复"AI处理接口当前余额不足"。

**原因**：DeepSeek 注册后账户余额为 0，需要充值才能调用。

**解法**：登录 DeepSeek 后台 → 充值 → 最低充 10 元，处理一篇文章约 ¥0.002，够用很久。

---

### 坑10：Railway GitHub App 权限问题

**现象**：Railway 部署时"No repositories found"，搜不到自己的 repo。

**原因**：Railway GitHub App 没有被授权访问该仓库。

**解法**：在 Railway Deploy 页面找到"Configure GitHub App"入口，跳转到 GitHub 授权页面，给 Railway 选择需要访问的仓库。

---

### 坑11：`__file__` 锚定路径，避免不同目录启动路径问题

如果用相对路径 `./data/knowledge_base.db`，从不同目录启动服务会在不同位置创建数据库。

**正确写法**：
```python
DATA_DIR = os.getenv("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
```

这样无论从哪个目录启动，数据库都在 `knowledge_store.py` 同目录下的 `data/` 文件夹。

---

### 坑12：一篇文章可能拆成多个 entries，SKILL.md 必须处理多条目回复

**现象**：API 返回 `entries` 数组有多个元素，龙虾只展示了第一条。

**原因**：SKILL.md 的回复模板只写了单条目的格式，没有处理多条目情况。

**解法**：SKILL.md 里明确说明"entries 可以有多个，逐一展示，不要合并或省略"，并给出多条目的回复格式示例。

---

## 版本变更对照

| 版本 | 存储 | 渲染 | AI | 接口 |
|------|------|------|-----|------|
| v1（已废弃） | SQLite JSON | markmap | Claude | Streamlit UI |
| v2（已废弃） | SQLite DB | markmap iframe | DeepSeek | FastAPI REST |
| v3（当前） | PostgreSQL | 原生 HTML | DeepSeek | FastAPI REST + MCP |
