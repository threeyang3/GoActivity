from dataclasses import dataclass

from app.models import Article, Event


EVENT_NOUNS = ("活动", "讲座", "论坛", "比赛", "大赛", "沙龙", "演出", "晚会", "实践", "招募", "征集", "报名")
RECAP_HINTS = ("回顾", "总结", "纪实", "纪要", "顺利举行", "圆满结束", "圆满落幕", "成功举办")
STRONG_SIGNALS = (
    ("活动时间", 3, "time_label"),
    ("演出时间", 3, "time_label"),
    ("讲座时间", 3, "time_label"),
    ("比赛时间", 3, "time_label"),
    ("截止时间", 2, "deadline"),
    ("活动地点", 3, "location_label"),
    ("地点", 2, "location_label"),
    ("报名方式", 3, "registration_label"),
    ("扫描下方二维码", 2, "registration_qr"),
    ("嘉宾", 2, "speaker"),
    ("主讲", 2, "speaker"),
    ("主持人招募", 3, "recruitment"),
    ("节目征集", 3, "recruitment"),
    ("征集", 2, "recruitment"),
    ("招募", 2, "recruitment"),
    ("报名", 2, "registration"),
    ("举办", 2, "hosted"),
    ("举行", 2, "hosted"),
)
WEAK_SIGNALS = (
    ("即日起", 1, "starts_now"),
    ("欢迎参加", 1, "invitation"),
    ("点击阅读原文", 1, "cta"),
    ("进入平台", 1, "platform"),
    ("二维码", 1, "qr"),
)
PROMO_HINTS = (
    "青春",
    "担当",
    "时代新声",
    "知行并进",
    "风采展示",
    "宣传片",
    "专题报道",
    "倡议书",
    "学习精神",
    "事迹介绍",
    "人物专访",
)
EXECUTION_HINTS = ("开展", "走进", "专场", "进社区", "宣讲", "放映", "对谈", "观演", "开售", "活动一览")


@dataclass(frozen=True)
class AccountRule:
    keep_keywords: tuple[str, ...] = ()
    filter_keywords: tuple[str, ...] = ()
    title_filter_keywords: tuple[str, ...] = ()
    recap_keywords: tuple[str, ...] = ()
    execution_keywords: tuple[str, ...] = ()


ACCOUNT_RULES = {
    "北大团委": AccountRule(
        keep_keywords=("招募", "征集", "报名", "通知", "启动", "大讲堂", "大赛", "毕业典礼", "毕业生晚会"),
        filter_keywords=("青春年少好读书", "践初心", "风骨", "荣获"),
        title_filter_keywords=("学生会组织标兵", "共青团标兵", "十佳团支书", "团队风采展示", "青春年少好读书"),
        recap_keywords=("回顾", "顺利举行", "圆满收官", "专题活动"),
        execution_keywords=("走进", "进社区", "宣讲", "志愿服务", "专题活动"),
    ),
    "北京大学人文学部": AccountRule(
        keep_keywords=("预告", "人文讲座", "博雅人文讲堂"),
        recap_keywords=("纪要", "圆满收官"),
    ),
    "北京大学百周年纪念讲堂": AccountRule(
        keep_keywords=("开售", "开售预告", "活动一览", "音乐会", "艺术影院", "影像放映", "沙龙", "对谈", "李莹厅"),
        recap_keywords=("精彩瞬间",),
        execution_keywords=("观众厅", "票价", "校内票", "校外票"),
    ),
    "北京大学人文社会科学研究院": AccountRule(
        keep_keywords=("预告", "文研讲座", "文研论坛", "未名学者讲座", "静园雅集", "中国讲坛"),
        filter_keywords=("方法", "典范", "书事", "延伸阅读", "公示", "招聘启事"),
        recap_keywords=("纪要",),
    ),
}


@dataclass
class ContentClassification:
    is_event_related: bool
    reason: str
    score: int
    activity_kind: str
    activity_kind_reason: str


VOLUNTEER_RECRUITMENT_HINTS = (
    "志愿者招募",
    "志愿者报名",
    "志愿者",
    "招募志愿者",
    "志愿服务招募",
)
LECTURE_HINTS = (
    "讲座",
    "论坛",
    "讲堂",
    "讲坛",
    "雅集",
    "沙龙",
    "对谈",
)
PERFORMANCE_HINTS = (
    "音乐会",
    "演出",
    "影像放映",
    "艺术影院",
    "放映",
    "晚会",
)
COMPETITION_HINTS = (
    "比赛",
    "大赛",
    "挑战杯",
    "征稿",
    "征文",
    "诵写讲大赛",
)
RECRUITMENT_HINTS = (
    "招募",
    "报名",
    "征集",
    "招新",
)


class ContentClassifier:
    def classify(self, article: Article, event: Event) -> ContentClassification:
        title = article.title or event.title or ""
        content = "\n".join(filter(None, [article.processed_markdown, article.raw_markdown, event.ocr_text]))
        haystack = f"{title}\n{content}"
        account_rule = ACCOUNT_RULES.get((article.mp_name or "").strip())

        if account_rule:
            title_filter_hits = [keyword for keyword in account_rule.title_filter_keywords if keyword in title]
            if title_filter_hits and not any(signal in haystack for signal in ("时间：", "地点：", "报名方式", "票价：")):
                return ContentClassification(False, f"title_filter:{title_filter_hits[0]}", 0, "non_event", title_filter_hits[0])

        recap_keywords = RECAP_HINTS + (account_rule.recap_keywords if account_rule else ())
        if any(keyword in haystack for keyword in recap_keywords) and any(noun in haystack for noun in EVENT_NOUNS):
            activity_kind, kind_reason = self._activity_kind(title, haystack)
            return ContentClassification(True, "recap_with_event_context", 5, activity_kind, kind_reason)

        score = 0
        reasons: list[str] = []
        for keyword, points, reason in STRONG_SIGNALS:
            if keyword in haystack:
                score += points
                reasons.append(reason)
        for keyword, points, reason in WEAK_SIGNALS:
            if keyword in haystack:
                score += points
                reasons.append(reason)

        if event.start_time:
            score += 3
            reasons.append("parsed_start_time")
        if event.location:
            score += 2
            reasons.append("parsed_location")
        if event.registration:
            score += 2
            reasons.append("parsed_registration")
        if event.speaker:
            score += 1
            reasons.append("parsed_speaker")
        if any(noun in haystack for noun in EVENT_NOUNS):
            score += 1
            reasons.append("event_noun")
        if any(keyword in haystack for keyword in EXECUTION_HINTS):
            score += 1
            reasons.append("execution_hint")

        if account_rule:
            keep_hits = [keyword for keyword in account_rule.keep_keywords if keyword in haystack]
            filter_hits = [keyword for keyword in account_rule.filter_keywords if keyword in haystack]
            execution_hits = [keyword for keyword in account_rule.execution_keywords if keyword in haystack]
            if keep_hits:
                score += 3
                reasons.append(f"account_keep:{keep_hits[0]}")
            if execution_hits:
                score += 2
                reasons.append(f"account_execution:{execution_hits[0]}")
            if filter_hits and score < 5:
                return ContentClassification(
                    False,
                    f"account_filter:{filter_hits[0]}",
                    score,
                    "non_event",
                    filter_hits[0],
                )

        promo_hits = [keyword for keyword in PROMO_HINTS if keyword in haystack]
        if promo_hits and score < 4:
            return ContentClassification(False, f"promo_without_event_evidence:{','.join(promo_hits[:3])}", score, "non_event", promo_hits[0])
        activity_kind, kind_reason = self._activity_kind(title, haystack)
        if score >= 5:
            return ContentClassification(True, ",".join(reasons[:6]) or "strong_event_evidence", score, activity_kind, kind_reason)
        if score >= 3 and (event.start_time or event.location or event.registration):
            return ContentClassification(True, ",".join(reasons[:6]) or "structured_event_evidence", score, activity_kind, kind_reason)
        return ContentClassification(False, ",".join(reasons[:6]) or "insufficient_event_evidence", score, "non_event", kind_reason)

    def _activity_kind(self, title: str, haystack: str) -> tuple[str, str]:
        source = f"{title}\n{haystack}"
        for keyword in VOLUNTEER_RECRUITMENT_HINTS:
            if keyword in source and any(marker in source for marker in RECRUITMENT_HINTS):
                return "volunteer_recruitment", keyword
        # PERFORMANCE_HINTS 在 LECTURE_HINTS 之前判定。
        # 原因：LECTURE_HINTS 中的 "讲堂" 会与场地名（"百周年纪念讲堂"、"大讲堂艺术影院"）误匹配；
        # PERFORMANCE_HINTS（"演出"/"放映"/"晚会"/"音乐会"/"艺术影院"/"影像放映"）是强且无歧义信号，
        # 让其优先可避免"场地讲堂 + 演出时间"被误判为 lecture。
        for keyword in PERFORMANCE_HINTS:
            if keyword in source:
                return "performance", keyword
        for keyword in LECTURE_HINTS:
            if keyword in source:
                return "lecture", keyword
        for keyword in COMPETITION_HINTS:
            if keyword in source:
                return "competition", keyword
        for keyword in RECRUITMENT_HINTS:
            if keyword in source:
                return "general_recruitment", keyword
        return "general_event", "default"
