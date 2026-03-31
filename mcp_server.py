import os
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from mcp.server.fastmcp import FastMCP

from extractor import extract_from_url
from knowledge_store import add_knowledge, get_all, get_stats
from mindmap_renderer import kb_to_markdown, kb_to_html_tree

# AI 模块延迟导入，避免缺少环境变量时启动即崩溃
def _get_ai():
    from ai_processor import extract_from_text, extract_from_image
    return extract_from_text, extract_from_image

def _format_save_result(r: dict, knowledge: dict, url: str) -> str:
    """统一格式化保存结果，输出通俗、结构清晰的消息。"""
    points = knowledge.get("key_points", [])
    points_text = "\n".join(f"  {p}" for p in points)
    source_line = f"\n🔗 来源：{url}" if url else ""
    view_url = "https://knowledge-flow-production-f40d.up.railway.app/view"
    return (
        f"{r['message']}\n\n"
        f"📌 {knowledge.get('topic')} › {knowledge.get('dimension')}\n"
        f"💡 {knowledge.get('summary', '')}\n\n"
        f"📝 提取要点：\n{points_text}"
        f"{source_line}\n\n"
        f"📊 查看完整知识图谱：{view_url}"
    )


# ── MCP Server 定义 ───────────────────────────────────────────────
mcp = FastMCP(
    "KnowledgeFlow 知识库",
    instructions=(
        "这是一个个人知识库工具。你可以用它保存文章链接或文字内容，"
        "AI 会自动提取主题、维度和知识要点，累积为个人知识框架。"
    ),
)


@mcp.tool()
def save_article(url: str) -> str:
    """
    从文章链接提取知识并保存到知识库。
    支持微信公众号文章及大多数静态文章页。
    用法示例：帮我收藏这篇文章 https://mp.weixin.qq.com/...
    """
    result = extract_from_url(url)
    if "error" in result:
        return f"❌ 链接提取失败：{result['error']}\n\n💡 提示：可以把文章正文复制后用 save_text 保存。"

    extract_from_text, _ = _get_ai()
    knowledge = extract_from_text(result["text"], result.get("title", ""), url)
    if "error" in knowledge:
        return f"❌ AI 处理失败：{knowledge['error']}"

    r = add_knowledge(knowledge, {
        "title": result.get("title", "未知标题"),
        "url": url,
        "platform": "公众号",
    })
    return _format_save_result(r, knowledge, url)


@mcp.tool()
def save_text(content: str, title: str = "") -> str:
    """
    保存文字内容到知识库。适用于复制粘贴的文章正文、读书笔记、任意文字。
    用法示例：帮我记录这段内容：[粘贴文字]
    """
    extract_from_text, _ = _get_ai()
    knowledge = extract_from_text(content, title)
    if "error" in knowledge:
        return f"❌ AI 处理失败：{knowledge['error']}"

    r = add_knowledge(knowledge, {
        "title": title or "手动输入",
        "url": "",
        "platform": "手动",
    })
    return _format_save_result(r, knowledge, "")


@mcp.tool()
def get_knowledge_stats() -> str:
    """查看知识库统计数据：已收录内容数、主题数、维度数、要点数。"""
    s = get_stats()
    return (
        f"📊 知识库统计\n"
        f"已处理内容：{s['total_items']} 篇\n"
        f"知识主题：{s['total_topics']} 个\n"
        f"知识维度：{s['total_dimensions']} 个\n"
        f"知识要点：{s['total_points']} 条"
    )


@mcp.tool()
def list_topics() -> str:
    """列出知识库中所有主题及其维度概览。"""
    kb = get_all()
    topics = kb.get("topics", {})
    if not topics:
        return "知识库暂无内容，发送文章链接或文字开始构建吧！"

    lines = ["📚 知识框架概览\n"]
    for topic, data in topics.items():
        dims = list(data.get("dimensions", {}).keys())
        total_pts = sum(len(d["points"]) for d in data["dimensions"].values())
        lines.append(f"▸ {topic}（{len(dims)} 个维度，{total_pts} 个要点）")
        for dim in dims:
            lines.append(f"    · {dim}")
    return "\n".join(lines)


# ── FastAPI App（挂载 MCP + 知识图谱查看页）────────────────────────
app = FastAPI(title="KnowledgeFlow MCP Server")

# 将 MCP server 挂载到 /mcp 路径（OpenClaw 连接此地址）
app.mount("/mcp", mcp.streamable_http_app())


@app.get("/health")
async def health():
    """Railway healthcheck 端点，轻量级不依赖 AI 或数据库。"""
    return JSONResponse({"status": "ok"})


@app.get("/", response_class=HTMLResponse)
async def root():
    """根路径重定向到知识图谱查看页。"""
    return HTMLResponse('<meta http-equiv="refresh" content="0;url=/view">', status_code=302)


@app.get("/view", response_class=HTMLResponse)
async def view_knowledge():
    """知识树查看页面，纯 HTML 渲染，无 JS 依赖。"""
    kb = get_all()
    s = get_stats()
    tree_html = kb_to_html_tree(kb)
    return HTMLResponse(_render_view_page(s, tree_html))


def _render_view_page(stats: dict, tree_html: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>🧠 KnowledgeFlow</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
          background: #f0f2f8; color: #2d3436; min-height: 100vh; }}

  header {{ background: linear-gradient(135deg,#6c63ff,#48dbfb);
            padding: 24px 24px 20px; color: #fff; }}
  header h1 {{ font-size: 1.5rem; font-weight: 700; letter-spacing: .5px; }}
  header p  {{ opacity: .85; margin-top: 4px; font-size: .85rem; }}

  .stats {{ display:flex; gap:12px; padding: 16px 16px 8px; flex-wrap:wrap; }}
  .stat-card {{ background:#fff; border-radius:12px; padding:14px 18px;
                box-shadow:0 2px 8px rgba(0,0,0,.06); flex:1; min-width:90px; text-align:center; }}
  .stat-card .num {{ font-size:1.7rem; font-weight:700; color:#6c63ff; line-height:1; }}
  .stat-card .lbl {{ font-size:.72rem; color:#636e72; margin-top:4px; }}

  .tree {{ padding: 12px 16px 40px; }}

  /* ── 主题块 ─────────────────────────── */
  .topic-block {{ margin-bottom: 12px; border-radius: 14px;
                  background:#fff; box-shadow:0 2px 10px rgba(0,0,0,.07); overflow:hidden; }}
  .topic-summary {{ display:flex; align-items:center; justify-content:space-between;
                    padding: 16px 20px; cursor:pointer; list-style:none; gap:8px;
                    border-radius:14px; transition: background .15s; }}
  .topic-summary::-webkit-details-marker {{ display:none; }}
  .topic-summary:hover {{ background:#f8f7ff; }}
  .topic-name {{ font-size:1.05rem; font-weight:700; flex:1; }}
  .topic-meta {{ font-size:.75rem; color:#b2bec3; white-space:nowrap; }}
  .topic-block[open] .topic-summary {{ border-radius:14px 14px 0 0; background:#f8f7ff; }}
  .topic-body {{ padding: 0 16px 12px; }}

  /* ── 维度块 ─────────────────────────── */
  .dim-block {{ margin: 8px 0; border-radius:10px;
                background:#f8f9fc; border:1px solid #eaedf3; }}
  .dim-summary {{ display:flex; align-items:center; justify-content:space-between;
                  padding: 12px 16px; cursor:pointer; list-style:none; gap:8px; }}
  .dim-summary::-webkit-details-marker {{ display:none; }}
  .dim-name {{ font-size:.92rem; font-weight:600; color:#2d3436; flex:1; }}
  .dim-meta {{ font-size:.72rem; color:#b2bec3; white-space:nowrap; }}
  .dim-block[open] .dim-summary {{ border-bottom:1px solid #eaedf3; }}
  .dim-body {{ padding: 10px 16px 14px; }}

  /* ── 要点列表 ────────────────────────── */
  .points {{ padding-left:0; list-style:none; margin:0 0 10px; }}
  .points li {{ padding: 6px 0 6px 20px; position:relative;
                font-size:.88rem; line-height:1.6; color:#2d3436;
                border-bottom:1px dashed #f0f2f8; }}
  .points li:last-child {{ border-bottom:none; }}
  .points li::before {{ content:counter(li-counter);
                         counter-increment:li-counter;
                         position:absolute; left:0; top:7px;
                         width:16px; height:16px; background:#6c63ff;
                         color:#fff; font-size:.65rem; font-weight:700;
                         border-radius:50%; display:flex; align-items:center;
                         justify-content:center; }}
  .points {{ counter-reset:li-counter; }}

  /* ── 来源区 ──────────────────────────── */
  .sources {{ margin-top:8px; padding-top:8px; border-top:1px solid #eaedf3;
              display:flex; flex-wrap:wrap; align-items:center; gap:6px;
              font-size:.75rem; }}
  .src-label {{ color:#b2bec3; white-space:nowrap; }}
  .src-link {{ color:#6c63ff; text-decoration:none; border-bottom:1px dotted #6c63ff; }}
  .src-link:hover {{ color:#48dbfb; }}
  .src-nolink {{ color:#636e72; }}
  .src-date {{ color:#dfe6e9; font-size:.68rem; }}

  .empty-tip {{ text-align:center; padding:60px 20px;
                color:#b2bec3; font-size:1rem; line-height:2; }}
</style>
</head>
<body>
<header>
  <h1>🧠 KnowledgeFlow</h1>
  <p>把你刷到的内容，变成自己的知识框架</p>
</header>

<div class="stats">
  <div class="stat-card">
    <div class="num">{stats['total_items']}</div>
    <div class="lbl">已处理</div>
  </div>
  <div class="stat-card">
    <div class="num">{stats['total_topics']}</div>
    <div class="lbl">主题</div>
  </div>
  <div class="stat-card">
    <div class="num">{stats['total_dimensions']}</div>
    <div class="lbl">维度</div>
  </div>
  <div class="stat-card">
    <div class="num">{stats['total_points']}</div>
    <div class="lbl">要点</div>
  </div>
</div>

<div class="tree">
  {tree_html}
</div>

</body>
</html>"""


# ── REST API（供不支持 MCP 的平台调用）────────────────────────────
from fastapi import Header, HTTPException
from pydantic import BaseModel

class ArticleReq(BaseModel):
    url: str

class TextReq(BaseModel):
    content: str
    title: str = ""

def _verify(authorization: str = Header(default="")):
    """简单 Bearer Token 校验，Railway 里设置 KF_API_KEY 环境变量。"""
    secret = os.getenv("KF_API_KEY", "")
    if not secret:
        return          # 未设置 key 时不校验（方便本地开发）
    token = authorization.removeprefix("Bearer ").strip()
    if token != secret:
        raise HTTPException(status_code=401, detail="Invalid API Key")

@app.post("/api/save-article")
async def api_save_article(req: ArticleReq, authorization: str = Header(default="")):
    """
    REST 接口：从文章链接提取知识并保存。
    Headers: Authorization: Bearer {KF_API_KEY}
    Body:    {"url": "https://..."}
    """
    _verify(authorization)
    result = extract_from_url(req.url)
    if "error" in result:
        return JSONResponse({"success": False, "message": result["error"]}, status_code=422)

    extract_from_text, _ = _get_ai()
    knowledge = extract_from_text(result["text"], result.get("title", ""), req.url)
    if "error" in knowledge:
        return JSONResponse({"success": False, "message": knowledge["error"]}, status_code=500)

    r = add_knowledge(knowledge, {
        "title": result.get("title", "未知标题"),
        "url": req.url,
        "platform": "公众号",
    })
    return {
        "success": True,
        "message": r["message"],
        "topic": knowledge.get("topic"),
        "dimension": knowledge.get("dimension"),
        "summary": knowledge.get("summary"),
        "key_points": knowledge.get("key_points", []),
    }


@app.post("/api/save-text")
async def api_save_text(req: TextReq, authorization: str = Header(default="")):
    """
    REST 接口：从文字内容提取知识并保存。
    Headers: Authorization: Bearer {KF_API_KEY}
    Body:    {"content": "...", "title": "..."}
    """
    _verify(authorization)
    extract_from_text, _ = _get_ai()
    knowledge = extract_from_text(req.content, req.title)
    if "error" in knowledge:
        return JSONResponse({"success": False, "message": knowledge["error"]}, status_code=500)

    r = add_knowledge(knowledge, {
        "title": req.title or "手动输入",
        "url": "",
        "platform": "手动",
    })
    return {
        "success": True,
        "message": r["message"],
        "topic": knowledge.get("topic"),
        "dimension": knowledge.get("dimension"),
        "summary": knowledge.get("summary"),
        "key_points": knowledge.get("key_points", []),
    }


@app.get("/api/stats")
async def api_stats(authorization: str = Header(default="")):
    """REST 接口：获取知识库统计数据。"""
    _verify(authorization)
    return get_stats()


@app.get("/api/topics")
async def api_topics(authorization: str = Header(default="")):
    """REST 接口：获取所有主题和维度列表。"""
    _verify(authorization)
    kb = get_all()
    result = []
    for topic, data in kb.get("topics", {}).items():
        dims = list(data.get("dimensions", {}).keys())
        points_count = sum(len(d["points"]) for d in data["dimensions"].values())
        result.append({"topic": topic, "dimensions": dims, "points_count": points_count})
    return {"topics": result}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("mcp_server:app", host="0.0.0.0", port=port, reload=False)
