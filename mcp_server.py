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

_VIEW_URL = "https://knowledge-flow-production-f40d.up.railway.app/view"


def _format_save_result(r: dict, url: str) -> str:
    """格式化保存结果，支持多条目。"""
    lines = [r["message"]]
    summary = r.get("summary", "")
    if summary:
        lines.append(f"\n💡 {summary}")

    for entry in r.get("entries", []):
        topic = entry.get("topic", "")
        dim = entry.get("dimension", "")
        points = entry.get("key_points", [])
        lines.append(f"\n📌 {topic} › {dim}")
        for p in points:
            lines.append(f"  · {p}")

    if url:
        lines.append(f"\n🔗 来源：{url}")
    lines.append(f"\n📊 查看完整知识库：{_VIEW_URL}")
    return "\n".join(lines)


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
    return _format_save_result(r, url)


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
    return _format_save_result(r, "")


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
app = FastAPI(title="KnowledgeFlow MCP Server", version="2.1.0")

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
<title>KnowledgeFlow · 我的知识库</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
    background: #f7f8f5;
    color: #2c2f2a;
    min-height: 100vh;
    font-size: 15px;
    line-height: 1.6;
  }}

  /* ── 顶栏 ──────────────────────────── */
  header {{
    background: #fff;
    border-bottom: 2px solid #e8ede3;
    padding: 16px 18px 13px;
  }}
  header h1 {{
    font-size: 1.15rem;
    font-weight: 700;
    color: #2d5a3d;
    letter-spacing: .4px;
  }}
  header p {{
    margin-top: 3px;
    font-size: .75rem;
    color: #b0bfa8;
    letter-spacing: .1px;
  }}

  /* ── 统计卡片（一行四列）─────────────── */
  .stats {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 8px;
    padding: 12px 14px 4px;
  }}
  .stat-card {{
    background: #fff;
    border-radius: 10px;
    padding: 12px 8px 10px;
    text-align: center;
    border: 1px solid #e8ede3;
  }}
  .stat-card .num {{
    font-size: 1.6rem;
    font-weight: 700;
    line-height: 1;
  }}
  /* 交替用绿色和琥珀色 */
  .stat-card:nth-child(1) .num,
  .stat-card:nth-child(3) .num {{ color: #3a7d52; }}
  .stat-card:nth-child(2) .num,
  .stat-card:nth-child(4) .num {{ color: #c07c1a; }}
  .stat-card .lbl {{
    font-size: .66rem;
    color: #a8b8a0;
    margin-top: 5px;
    letter-spacing: .4px;
  }}

  /* ── 知识树 ──────────────────────────── */
  .tree {{ padding: 12px 14px 52px; }}

  /* ── 一级：主题 ─────────────────────── */
  .topic-block {{
    margin-bottom: 12px;
    border-radius: 12px;
    background: #fff;
    border: 1px solid #dce8d8;
    overflow: hidden;
  }}
  .topic-summary {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 13px 16px;
    cursor: pointer;
    list-style: none;
    gap: 8px;
    user-select: none;
    -webkit-tap-highlight-color: transparent;
  }}
  .topic-summary::-webkit-details-marker {{ display: none; }}
  .topic-name {{
    font-size: .97rem;
    font-weight: 700;
    color: #1e3d28;
    flex: 1;
    display: flex;
    align-items: center;
    gap: 9px;
  }}
  /* 琥珀色小圆点 */
  .topic-name::before {{
    content: "";
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #d97706;
    flex-shrink: 0;
  }}
  .topic-meta {{
    font-size: .68rem;
    color: #a8b8a0;
    white-space: nowrap;
  }}
  .topic-block[open] > .topic-summary {{
    border-bottom: 1px solid #dce8d8;
    background: #f8fbf6;
  }}

  /* ── 主题体 + 连接线 ────────────────── */
  .topic-body {{
    padding: 8px 12px 10px 12px;
    position: relative;
  }}
  .topic-body::before {{
    content: "";
    position: absolute;
    left: 26px;
    top: 8px;
    bottom: 10px;
    width: 1.5px;
    background: linear-gradient(to bottom, #b7d9c4, #dce8d8);
    border-radius: 2px;
  }}

  /* ── 二级：维度 ─────────────────────── */
  .dim-block {{
    margin: 5px 0 5px 26px;
    border-radius: 9px;
    background: #f8fbf6;
    border: 1px solid #dce8d8;
    position: relative;
  }}
  .dim-block::before {{
    content: "";
    position: absolute;
    left: -13px;
    top: 50%;
    width: 13px;
    height: 1.5px;
    background: #b7d9c4;
    transform: translateY(-50%);
  }}
  .dim-summary {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 13px;
    cursor: pointer;
    list-style: none;
    gap: 8px;
    user-select: none;
    -webkit-tap-highlight-color: transparent;
  }}
  .dim-summary::-webkit-details-marker {{ display: none; }}
  .dim-name {{
    font-size: .85rem;
    font-weight: 600;
    color: #2d5a3d;
    flex: 1;
    display: flex;
    align-items: center;
    gap: 5px;
  }}
  .dim-name::before {{
    content: "›";
    color: #52a872;
    font-size: .95rem;
    font-weight: 700;
    flex-shrink: 0;
  }}
  .dim-meta {{
    font-size: .66rem;
    color: #a8b8a0;
    white-space: nowrap;
  }}
  .dim-block[open] > .dim-summary {{
    border-bottom: 1px solid #dce8d8;
  }}
  .dim-body {{ padding: 8px 13px 11px; }}

  /* ── 三级：要点 ─────────────────────── */
  .points {{
    list-style: none;
    padding: 0;
    margin: 0 0 7px;
    counter-reset: pt-counter;
  }}
  .points li {{
    counter-increment: pt-counter;
    padding: 6px 0 6px 26px;
    position: relative;
    font-size: .83rem;
    line-height: 1.65;
    color: #3a4a3c;
    border-bottom: 1px solid #eff3ec;
  }}
  .points li:last-child {{ border-bottom: none; padding-bottom: 0; }}
  /* 琥珀色序号圆 */
  .points li::before {{
    content: counter(pt-counter);
    position: absolute;
    left: 0;
    top: 8px;
    width: 17px;
    height: 17px;
    background: #fef3c7;
    color: #c07c1a;
    font-size: .62rem;
    font-weight: 700;
    border-radius: 50%;
    text-align: center;
    line-height: 17px;
  }}

  /* ── 来源区 ──────────────────────────── */
  .sources {{
    margin-top: 7px;
    padding-top: 7px;
    border-top: 1px dashed #dce8d8;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 4px 8px;
    font-size: .71rem;
  }}
  .src-label {{ color: #b8c8b0; }}
  .src-link {{
    color: #3a7d52;
    text-decoration: none;
    border-bottom: 1px dotted #3a7d52;
  }}
  .src-link:hover {{ color: #1e3d28; }}
  .src-nolink {{ color: #6b8c72; }}
  .src-date {{ color: #c8d8c0; font-size: .66rem; }}

  .empty-tip {{
    text-align: center;
    padding: 60px 20px;
    color: #b8c8b0;
    font-size: .9rem;
    line-height: 2.4;
  }}
  .empty-tip strong {{ color: #d97706; }}
</style>
</head>
<body>

<header>
  <h1>KnowledgeFlow</h1>
  <p>让你刷到的碎片信息，自己长成知识图谱</p>
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
        "summary": r.get("summary", ""),
        "entries": r.get("entries", []),
        "is_update": r.get("is_update", False),
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
        "summary": r.get("summary", ""),
        "entries": r.get("entries", []),
        "is_update": r.get("is_update", False),
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
