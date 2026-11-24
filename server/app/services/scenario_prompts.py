"""情景对话提示词模板 — 为不同英语学习场景定制高质量 system prompt"""

# 预设场景配置
# 每个场景包含：id、name(中文标签)、icon(emoji)、scene_desc(场景描述)、user_role(用户身份)
SCENARIO_PRESETS = [
    {
        "id": "coffee",
        "name": "咖啡店点餐",
        "icon": "☕",
        "scene_desc": "你在一家温馨的咖啡店里担任服务员。顾客来点餐、询问饮品信息。菜单上有：拿铁、美式、卡布奇诺、摩卡、抹茶拿铁等饮品，以及各种蛋糕甜点。",
        "user_role": "一位来咖啡店的顾客，想点饮品和甜点",
    },
    {
        "id": "restaurant",
        "name": "餐厅用餐",
        "icon": "🍽️",
        "scene_desc": "你是一家西餐厅的服务员。顾客来就餐，需要推荐菜品、接受点单和反馈。菜单包括前菜、主菜（牛排、意面、海鲜等）、甜品和饮品。",
        "user_role": "一位在餐厅用餐的客人",
    },
    {
        "id": "shopping",
        "name": "购物逛街",
        "icon": "🛍️",
        "scene_desc": "你是一家时尚服装店的店员。顾客来看衣服、询问尺寸颜色、试穿和结账。店内有T恤、连衣裙、牛仔裤、外套、鞋子等。",
        "user_role": "一位来逛街购物的顾客",
    },
    {
        "id": "travel",
        "name": "旅行问路",
        "icon": "🗺️",
        "scene_desc": "你是一个友善的当地人。一位游客在问路和咨询当地旅游信息。附近有著名的景点、博物馆、公园、餐厅和地铁站。",
        "user_role": "一位到这座城市旅游的游客，需要问路和获取旅行建议",
    },
    {
        "id": "hotel",
        "name": "酒店入住",
        "icon": "🏨",
        "scene_desc": "你是酒店前台接待员。顾客来办理入住/退房、咨询房间设施和酒店服务。酒店有标准间、商务套房和豪华套房，提供早餐、健身房和游泳池。",
        "user_role": "一位来办理酒店入住的旅客",
    },
    {
        "id": "airport",
        "name": "机场出行",
        "icon": "✈️",
        "scene_desc": "你是机场地勤工作人员。乘客来办理登机手续、询问登机口信息、行李规定和航班状态。",
        "user_role": "一位在机场准备乘机的旅客",
    },
    {
        "id": "interview",
        "name": "面试求职",
        "icon": "💼",
        "scene_desc": "你是一家跨国公司的招聘经理。正在面试应聘者，考察英语沟通能力、专业背景和综合素质。",
        "user_role": "一位来参加英语面试的求职者",
    },
    {
        "id": "hospital",
        "name": "看医生",
        "icon": "🏥",
        "scene_desc": "你是一位友善的医生。病人来看病，描述症状，你给出诊断和建议。你在综合医院的内科门诊工作。",
        "user_role": "一位身体不适、来看医生的病人",
    },
    {
        "id": "library",
        "name": "图书馆",
        "icon": "📚",
        "scene_desc": "你是大学图书馆的管理员。一位学生来找书、咨询借阅规则和使用学习空间。",
        "user_role": "一位来图书馆学习的大学生",
    },
    {
        "id": "friends",
        "name": "结识朋友",
        "icon": "👋",
        "scene_desc": "你是一个友善热情的英语母语者。在一次国际交流活动中，你遇到一位新朋友，正在愉快地聊天，了解彼此的兴趣爱好和生活。",
        "user_role": "一位参加国际交流活动的英语学习者",
    },
]


def build_scenario_system_prompt(scene_desc: str, user_role: str, level: str = "intermediate") -> str:
    """根据场景描述和用户身份，构建情景对话的 system prompt

    Args:
        scene_desc: 场景描述
        user_role: 用户扮演的角色
        level: 英语水平 (beginner / intermediate / advanced)

    Returns:
        完整的 system prompt
    """
    level_guides = {
        "beginner": (
            "语言难度控制：\n"
            "  - 使用基础词汇和简单句型，语速自然但语句简短\n"
            "  - 同一意思可适当换种方式重述，帮助理解\n"
            "  - 在对话中自然融入关键表达，不刻意教学"
        ),
        "intermediate": (
            "语言难度控制：\n"
            "  - 使用日常对话的自然语速和词汇量\n"
            "  - 适当使用一些习语和地道表达\n"
            "  - 如果用户表达有误，在对话结束后温和地给出正确说法"
        ),
        "advanced": (
            "语言难度控制：\n"
            "  - 使用自然、地道的口语表达，包括习语和俚语\n"
            "  - 话题可以讨论观点、情感、抽象概念\n"
            "  - 与真实母语者对话一致的风格和节奏"
        ),
    }
    level_guide = level_guides.get(level, level_guides["intermediate"])

    prompt = (
        f"你是一个英语对话练习AI助手。请严格按照以下设定进行角色扮演：\n\n"
        f"【场景设定】\n{scene_desc}\n\n"
        f"【用户身份】\n{user_role}\n\n"
        f"【行为规则】\n"
        f"1. 全程用**英语**回复，保持自然口语风格\n"
        f"2. 严格按照设定的场景和角色身份进行对话，开场时主动问候并开启话题\n"
        f"3. 引导用户多说完整句子，不要只回答 yes/no，可以通过追问促使用户表达\n"
        f"4. 【重要】你是英语母语者角色，听不懂中文。如果用户使用中文，扮演困惑不解——回应 'Sorry, I don't understand Chinese. Could you say that in English please?' 或类似的表达，直到用户改用英语沟通\n"
        f"5. 用户语法或用词不准确时，在下一轮回复中以自然重复正确说法的方式示范（不要打断对话来纠错）\n"
        f"6. 保持对话自然流畅，每次回复不宜过长（2-4句话为宜），不要一次输出太多内容\n"
        f"7. 适当重复和强化场景相关的核心词汇和表达\n\n"
        f"{level_guide}\n\n"
        f"请现在开始，以场景中的角色身份向用户打招呼，开启对话。"
    )
    return prompt


def build_scenario_intro(scenario: dict) -> str:
    """构建场景介绍文本，用于对话开始前的展示"""
    return (
        f"📖 场景：{scenario['icon']} {scenario['name']}\n"
        f"🎭 你的角色：{scenario['user_role']}\n"
        f"🤖 AI 角色：{scenario['scene_desc'][:40]}…\n\n"
        f"你可以用英语自由对话，AI 会根据对话质量给出建议。"
    )
