import json
import os
import re
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# ── 切换模型供应商，改这里即可 ─────────────────────────────────────
# DeepSeek（推荐，性价比高）：
PROVIDER = "deepseek"
API_KEY_ENV = "DEEPSEEK_API_KEY"
BASE_URL = "https://api.deepseek.com"
TEXT_MODEL = "deepseek-chat"       # DeepSeek-V3，用于文字提取
VISION_MODEL = "deepseek-chat"     # DeepSeek-V3 支持图片输入

# 通义千问（有免费额度）：取消下面注释并注释上方5行
# PROVIDER = "qwen"
# API_KEY_ENV = "DASHSCOPE_API_KEY"
# BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
# TEXT_MODEL = "qwen-plus"
# VISION_MODEL = "qwen-vl-plus"

# Claude（原始配置，需能访问 api.anthropic.com）：
# PROVIDER = "claude"
# API_KEY_ENV = "ANTHROPIC_API_KEY"
# BASE_URL = "https://api.anthropic.com/v1"
# TEXT_MODEL = "claude-sonnet-4-5"
# VISION_MODEL = "claude-sonnet-4-5"
# ──────────────────────────────────────────────────────────────────

client = OpenAI(api_key=os.getenv(API_KEY_ENV), base_url=BASE_URL)

EXTRACTION_SYSTEM_PROMPT = """你是一名专业的知识管理专家，擅长将碎片化内容提炼为结构化知识，帮用户建立可复用的个人知识框架。

━━━ 第一步：判断内容类型 ━━━
- list（清单类）：推荐合集、工具列表、技巧汇总，有明确编号条目
- insight（观点类）：作者分享思考、方法论、经验总结
- tutorial（教程类）：有操作步骤的指南、攻略
- news（资讯类）：新闻、产品发布、行业动态

━━━ 第二步：三层分类（由粗到细）━━━
一级主题（最宽泛，选一个）：
  AI技术 / 产品设计 / 内容创作 / 个人成长 / 商业运营 / 技术开发 / 投资理财 / 健康生活

二级维度（中等粒度，举例）：
  AI技术 → 工具推荐 / 提示词技巧 / 行业应用 / 前沿资讯
  产品设计 → 用户研究 / 增长策略 / 交互设计
  内容创作 → 写作技巧 / 选题方法 / 传播策略

━━━ 第三步：要点提取规则 ━━━
【list 清单类】——最重要规则：原文有几条就提取几条，绝对不能遗漏
  格式：「序号. 名称 — 一句话说明它能解决什么问题或有什么价值」
  示例：「1. Cursor — AI编程工具，写代码速度提升10倍」

【insight 观点类】——提取3-5个可直接复用的结论
  格式：动词开头的行动建议或认知升级句
  示例：「用"结果导向"替代"任务导向"来设计产品功能」

【tutorial 教程类】——提取关键步骤或核心原则
  格式：「步骤/原则（15字以内，可操作）」

【news 资讯类】——提取最值得关注的事实和影响
  格式：「事件要点 + 为什么重要」

━━━ 通用要求 ━━━
- 语言通俗易懂，避免术语堆砌
- 每个要点独立成立，无需上下文即可理解
- 只返回 JSON，不要任何其他文字"""

EXTRACTION_USER_PROMPT = """内容如下，请按规则提取：

标题：{title}
链接：{url}

正文：
{content}

返回 JSON：
{{
  "content_type": "list 或 insight 或 tutorial 或 news",
  "topic": "一级主题",
  "dimension": "二级维度",
  "key_points": ["要点1", "要点2", ...],
  "summary": "一句话概括核心价值（20字以内）",
  "source_url": "{url}"
}}"""


def _parse_json_safely(raw: str) -> dict:
    raw = raw.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, re.IGNORECASE)
    if match:
        raw = match.group(1).strip()
    return json.loads(raw)


def _chat(model: str, messages: list, max_tokens: int = 1000) -> str:
    """统一的 OpenAI 兼容调用入口"""
    response = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=messages,
    )
    return response.choices[0].message.content


def extract_from_text(text: str, title: str = "", url: str = "") -> dict:
    """从文字内容中提取结构化知识（公众号文章正文 / 粘贴文字）"""
    try:
        raw = _chat(
            model=TEXT_MODEL,
            max_tokens=2000,
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": EXTRACTION_USER_PROMPT.format(
                    title=title or "（无标题）",
                    url=url or "（无链接）",
                    content=text[:8000],
                )},
            ],
        )
        return _parse_json_safely(raw)
    except json.JSONDecodeError as e:
        return {"error": f"AI 返回格式异常，请重试。详情：{str(e)}"}
    except Exception as e:
        return {"error": f"AI 处理失败：{str(e)}"}


def extract_from_image(image_base64: str) -> dict:
    """从图片（小红书截图）中提取结构化知识（Vision 模型）"""
    try:
        raw = _chat(
            model=VISION_MODEL,
            max_tokens=1500,
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
                        },
                        {
                            "type": "text",
                            "text": (
                                "这是一张截图。请先完整阅读图片中的所有文字，"
                                "然后按照要求提取结构化知识。\n\n"
                                + EXTRACTION_USER_PROMPT.format(
                                    title="（图片内容）",
                                    url="（截图，无链接）",
                                    content="（见上方图片，请完整提取所有条目）",
                                )
                            ),
                        },
                    ],
                },
            ],
        )
        return _parse_json_safely(raw)
    except json.JSONDecodeError as e:
        return {"error": f"AI 返回格式异常，请重试。详情：{str(e)}"}
    except Exception as e:
        return {"error": f"AI 处理失败：{str(e)}"}
