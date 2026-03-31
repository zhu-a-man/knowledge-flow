def kb_to_markdown(kb: dict) -> str:
    """将知识库转为 Markdown 层级（供 MCP 工具文字回复使用）"""
    lines = ["# 我的知识框架"]
    for topic, topic_data in kb.get("topics", {}).items():
        lines.append(f"\n## {topic}")
        for dim, dim_data in topic_data.get("dimensions", {}).items():
            lines.append(f"\n### {dim}")
            for point in dim_data.get("points", []):
                lines.append(f"\n- {point}")
    return "\n".join(lines)


# 每个层级的颜色（topic 级别循环使用）
_TOPIC_COLORS = [
    "#6c63ff", "#1D9E75", "#D85A30", "#378ADD",
    "#BA7517", "#c0392b", "#8e44ad", "#16a085",
]


def kb_to_html_tree(kb: dict) -> str:
    """
    将知识库渲染为纯 HTML 可折叠树。
    无 JS、无 CDN 依赖，原生 <details>/<summary> 实现折叠，
    完整展示：主题 → 维度 → 要点（编号列表）+ 来源链接。
    """
    topics = kb.get("topics", {})
    if not topics:
        return '<p class="empty-tip">还没有内容，先用龙虾发一篇文章试试！</p>'

    blocks = []
    for idx, (topic, topic_data) in enumerate(topics.items()):
        color = _TOPIC_COLORS[idx % len(_TOPIC_COLORS)]
        dims = topic_data.get("dimensions", {})
        total_pts = sum(len(d["points"]) for d in dims.values())
        total_src = sum(len(d["sources"]) for d in dims.values())

        dim_blocks = []
        for dim, dim_data in dims.items():
            points = dim_data.get("points", [])
            sources = dim_data.get("sources", [])

            # 要点列表
            if points:
                pts_html = "<ol class='points'>" + "".join(
                    f"<li>{_esc(p)}</li>" for p in points
                ) + "</ol>"
            else:
                pts_html = ""

            # 来源链接
            src_items = []
            for s in sources:
                url = s.get("url", "")
                title = _esc(s.get("title") or "未知标题")
                date = s.get("date", "")
                if url:
                    src_items.append(
                        f'<a href="{_esc(url)}" target="_blank" class="src-link">'
                        f'{title}</a><span class="src-date">{date}</span>'
                    )
                else:
                    src_items.append(
                        f'<span class="src-nolink">{title}</span>'
                        f'<span class="src-date">{date}</span>'
                    )

            src_html = (
                '<div class="sources"><span class="src-label">📎 来源</span>'
                + " &nbsp;·&nbsp; ".join(src_items)
                + "</div>"
            ) if src_items else ""

            dim_blocks.append(f"""
<details class="dim-block">
  <summary class="dim-summary">
    <span class="dim-name">{_esc(dim)}</span>
    <span class="dim-meta">{len(sources)} 篇来源 · {len(points)} 个要点</span>
  </summary>
  <div class="dim-body">
    {pts_html}
    {src_html}
  </div>
</details>""")

        blocks.append(f"""
<details class="topic-block" open>
  <summary class="topic-summary" style="border-left:4px solid {color}">
    <span class="topic-name">{_esc(topic)}</span>
    <span class="topic-meta">{len(dims)} 个维度 · {total_pts} 个要点 · {total_src} 篇来源</span>
  </summary>
  <div class="topic-body">
    {"".join(dim_blocks)}
  </div>
</details>""")

    return "\n".join(blocks)


def _esc(s: str) -> str:
    """最小化 HTML 转义"""
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
