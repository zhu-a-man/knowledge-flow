def kb_to_markdown(kb: dict) -> str:
    """将知识库转为 Markdown 层级（供 MCP 工具文字回复使用）"""
    lines = ["# 我的知识框架"]
    for topic, topic_data in kb.get("topics", {}).items():
        lines.append(f"\n## {topic}")
        for dim, dim_data in topic_data.get("dimensions", {}).items():
            lines.append(f"\n### {dim}")
            for point in dim_data.get("points", []):
                lines.append(f"\n- {point}")
            for src in dim_data.get("sources", []):
                form = src.get("content_form", "")
                form_tag = f" [{form}]" if form else ""
                lines.append(f"\n  > 来源：{src.get('title', '')}{form_tag}")
    return "\n".join(lines)


# 主题左边框颜色（绿色系循环）
_TOPIC_COLORS = [
    "#52b788", "#2d6a4f", "#40916c", "#74c69d",
    "#1b4332", "#95d5b2", "#27ae60", "#b7e4c7",
]


def kb_to_html_tree(kb: dict) -> str:
    """
    将知识库渲染为纯 HTML 可折叠树。
    无 JS、无 CDN 依赖，原生 <details>/<summary> 实现折叠，
    完整展示：主题 → 维度 → 要点（编号列表）+ 来源链接。
    """
    topics = kb.get("topics", {})
    if not topics:
        return '<p class="empty-tip">还没有内容<br><strong>发给龙虾一篇文章链接</strong>，知识树就会长出来 🌱</p>'

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
                form = s.get("content_form", "")
                form_html = f'<span class="form-tag form-{_form_class(form)}">{_esc(form)}</span>' if form else ""
                if url:
                    src_items.append(
                        f'{form_html}'
                        f'<a href="{_esc(url)}" target="_blank" class="src-link">'
                        f'{title}</a><span class="src-date">{date}</span>'
                    )
                else:
                    src_items.append(
                        f'{form_html}'
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


_FORM_CLASS_MAP = {
    "工具清单": "tools",
    "方法论":   "method",
    "教程步骤": "tutorial",
    "行业动态": "news",
    "观点洞察": "insight",
    "案例故事": "story",
}


def _form_class(form: str) -> str:
    """将内容形式映射为 CSS 类名"""
    return _FORM_CLASS_MAP.get(form, "default")


def _esc(s: str) -> str:
    """最小化 HTML 转义"""
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
