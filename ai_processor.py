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

EXTRACTION_SYSTEM_PROMPT = """你是用户最懂他的朋友，帮他把刷到的好文章"翻译"成他自己的笔记，方便日后找回和复用。

━━━ 第一步：判断内容类型 ━━━
- list（清单类）：推荐合集、工具列表、技巧汇总，有明确编号条目
- insight（观点类）：作者分享思考、方法论、经验总结
- tutorial（教程类）：有操作步骤的指南、攻略
- news（资讯类）：新闻、产品发布、行业动态

━━━ 第二步：分类——以"方便找回"为唯一标准 ━━━
判断原则：
  · 一个月后用户想找这篇内容，他会先想到什么词？那就是 topic
  · topic 下哪个维度最能说明这篇的"用途"？那就是 dimension
  · topic 不要太宽泛（不要什么都叫"技术"），也不要太细（不要用文章标题当 topic）

示例：工具推荐文 → topic=AI工具, dimension=效率工具 ｜ Prompt教程 → topic=提示词, dimension=写法技巧
同类内容归同一 topic，知识越攒越聚合，不要每篇都建新主题。

━━━ 第三步：要点提炼规则 ━━━

写作风格要求（最重要）：
  · 像朋友推荐一样写，让人一眼就想看下去
  · 用"你可以……""这个……帮你……""适合……的人"等生活化表达
  · 禁止：术语堆砌、"该工具具备……功能"、过度正式的书面腔
  · 每条要点读完应该让人觉得"哦，这个有用！"

【list 清单类】——原文有几条就写几条，一条都不能少
  格式：「名称 — 用大白话说它帮你解决什么问题，或者为什么值得一试」
  好的示例：「Cursor — 写代码时 AI 帮你补全和改 bug，效率高到不像话」
  差的示例：「Cursor — 一款具备AI辅助功能的代码编辑器」

【insight 观点类】——提炼 3-5 个让你觉得"说得对！"的结论
  格式：口语化的行动建议或认知翻转句，读完有共鸣
  好的示例：「别把时间花在"看起来忙"上，只盯着能出结果的事做」
  差的示例：「应采用结果导向型工作方式替代任务导向型工作模式」

【tutorial 教程类】——提炼关键步骤，写成"你去做"的语气
  格式：「具体怎么操作（15字以内，一看就能动手）」

【news 资讯类】——说清楚发生了什么、对你有什么影响
  格式：「事情 + 为什么你该关注」

━━━ summary 写法 ━━━
一句话说清楚"这篇文章对你有什么用"，20字以内，口语化。
好的示例：「收藏这篇，装好这几个工具效率翻倍」
差的示例：「本文介绍了多种提升工作效率的AI工具」

━━━ 通用要求 ━━━
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
  "summary": "一句话说清楚这篇对读者有什么用（口语化，20字以内）",
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
