"""
KnowledgeFlow 分类体系（受控词表）

设计原则：
- 分面分类法：领域 × 子领域 × 内容形式，三个维度正交独立
- MECE 原则：每层类目相互独立、完全穷尽
- 受控生成：模型必须从词表中选择，无法匹配时走"其他"兜底
- 每层 ≤ 10 个选项（Miller's Law: 7±2 认知上限）

修改指南：
- 新增领域：确认与现有领域无交集后，在 DOMAINS 中追加
- 新增子领域：在对应领域的 subdomains 列表中追加
- boundary 字段用于消歧，提示模型在边界 case 时如何判断
"""

DOMAINS: dict[str, dict] = {
    "AI与大模型": {
        "subdomains": [
            "AI工具应用",
            "Prompt工程",
            "AI编程",
            "Agent与自动化",
            "模型与技术动态",
        ],
        "boundary": "核心价值由 AI / 大模型能力驱动",
    },
    "软件开发": {
        "subdomains": [
            "编程语言与框架",
            "架构与系统设计",
            "开发工具链",
            "DevOps与部署",
            "数据库与存储",
        ],
        "boundary": "非 AI 驱动的纯技术开发内容",
    },
    "产品与设计": {
        "subdomains": [
            "产品思维与方法",
            "用户体验设计",
            "设计工具与资源",
            "增长与运营",
        ],
        "boundary": "产品规划、设计、运营相关",
    },
    "商业与创业": {
        "subdomains": [
            "商业模式",
            "创业实践",
            "市场营销",
            "团队与管理",
        ],
        "boundary": "商业运作、创业过程相关",
    },
    "效率与工具": {
        "subdomains": [
            "效率工具推荐",
            "工作方法论",
            "知识管理",
            "自动化与流程",
        ],
        "boundary": "提升个人/团队效率的方法和工具（非 AI 专属）",
    },
    "职业发展": {
        "subdomains": [
            "技能提升",
            "职场认知",
            "求职与面试",
            "个人品牌与影响力",
        ],
        "boundary": "个人职业路径与成长",
    },
    "投资理财": {
        "subdomains": [
            "投资策略",
            "市场分析与趋势",
            "理财规划",
            "数字资产与加密",
        ],
        "boundary": "财务、投资、理财相关",
    },
    "生活与成长": {
        "subdomains": [
            "健康与运动",
            "心理与认知",
            "阅读与写作",
            "兴趣与生活方式",
        ],
        "boundary": "个人生活品质与精神成长",
    },
}

CONTENT_FORMS: dict[str, str] = {
    "工具清单": "推荐一组工具/资源/产品",
    "方法论":   "阐述思维方式/框架/原则",
    "教程步骤": "手把手教操作步骤/流程",
    "行业动态": "行业/产品/技术的新闻",
    "观点洞察": "深度观点/分析/反思判断",
    "案例故事": "通过具体案例/故事说明",
}


def format_taxonomy_for_prompt() -> str:
    """将分类体系格式化为 Prompt 注入文本"""
    lines = []
    for domain, info in DOMAINS.items():
        subs = " | ".join(info["subdomains"])
        lines.append(f"  {domain} → {subs}")
        lines.append(f"    边界：{info['boundary']}")

    domain_text = "\n".join(lines)
    forms = " | ".join(f"{k}（{v}）" for k, v in CONTENT_FORMS.items())

    return (
        f"【领域 → 子领域】（必须从中选择）\n"
        f"{domain_text}\n"
        f"  其他 → （当以上领域都不合适时使用，dimension 写具体方向）\n\n"
        f"【内容形式】（必须从中选择一种）\n"
        f"  {forms}"
    )


def get_valid_domains() -> set[str]:
    """返回所有合法领域名"""
    return set(DOMAINS.keys()) | {"其他"}


def get_valid_forms() -> set[str]:
    """返回所有合法内容形式"""
    return set(CONTENT_FORMS.keys())
