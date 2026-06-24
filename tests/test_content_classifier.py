from app.models import Article, Event
from app.services.content_classifier import ContentClassifier


def test_classifier_accepts_real_event_notice() -> None:
    article = Article(
        article_id="article_content_1",
        title="毕业晚会通知",
        processed_markdown="演出时间：2026年6月26日\n演出地点：北京大学百周年纪念讲堂\n请扫描下方二维码填写问卷",
        raw_markdown="",
    )
    event = Event(event_id="event_content_1", article_id=article.article_id, title=article.title)

    result = ContentClassifier().classify(article, event)

    assert result.is_event_related is True
    assert result.activity_kind == "performance"


def test_classifier_rejects_promo_like_article() -> None:
    article = Article(
        article_id="article_content_2",
        title="知行并进强本领 挺膺担当建新功",
        processed_markdown="在2026年的盛夏新征程中铺就全面建设社会主义现代化国家的壮阔伟业，北大青年以青春之名书写时代答卷。",
        raw_markdown="",
    )
    event = Event(event_id="event_content_2", article_id=article.article_id, title=article.title)

    result = ContentClassifier().classify(article, event)

    assert result.is_event_related is False
    assert "promo" in result.reason or "insufficient" in result.reason


def test_classifier_keeps_tuanwei_execution_activity() -> None:
    article = Article(
        article_id="article_content_3",
        mp_name="北大团委",
        title="第七期“学雷锋·做实事·进社区”专题活动 | 北医三院急救科普志愿团队在东花市街道开展急救宣讲",
        processed_markdown="志愿服务团队走进社区开展急救宣讲。",
        raw_markdown="",
    )
    event = Event(event_id="event_content_3", article_id=article.article_id, title=article.title)

    result = ContentClassifier().classify(article, event)

    assert result.is_event_related is True
    assert "account_execution" in result.reason or result.score >= 5
    assert result.activity_kind == "general_event"


def test_classifier_rejects_wenyan_non_event_column() -> None:
    article = Article(
        article_id="article_content_4",
        mp_name="北京大学人文社会科学研究院",
        title="方法 | 葛兆光：如何重新叙述古代中国思想世界",
        processed_markdown="20世纪70年代以来的半个多世纪中，简帛文献的大量发现对古代中国思想的研究产生很大冲击。",
        raw_markdown="",
    )
    event = Event(event_id="event_content_4", article_id=article.article_id, title=article.title)

    result = ContentClassifier().classify(article, event)

    assert result.is_event_related is False
    assert result.reason.startswith("account_filter:")
    assert result.activity_kind == "non_event"


def test_classifier_keeps_jiangtang_presale_event() -> None:
    article = Article(
        article_id="article_content_5",
        mp_name="北京大学百周年纪念讲堂",
        title="开售预告｜大讲堂艺术影院《实习生》",
        processed_markdown="时间：2026年6月21日（周日）15:00 地点：讲堂观众厅 票价：40、60元",
        raw_markdown="",
    )
    event = Event(event_id="event_content_5", article_id=article.article_id, title=article.title)

    result = ContentClassifier().classify(article, event)

    assert result.is_event_related is True
    assert result.activity_kind == "performance"


def test_classifier_rejects_tuanwei_profile_title_even_with_mixed_event_words() -> None:
    article = Article(
        article_id="article_content_6",
        mp_name="北大团委",
        title="北京大学“学生会组织标兵” | 孙梦悦：笃行逐梦勤为径，怀炬向光践初心",
        processed_markdown="团队曾参与多项活动与志愿服务，持续走进社区。",
        raw_markdown="",
    )
    event = Event(event_id="event_content_6", article_id=article.article_id, title=article.title)

    result = ContentClassifier().classify(article, event)

    assert result.is_event_related is False
    assert result.reason.startswith("title_filter:")
    assert result.activity_kind == "non_event"


def test_classifier_marks_volunteer_recruitment_separately() -> None:
    article = Article(
        article_id="article_content_7",
        mp_name="北大团委",
        title="北京大学2026毕业典礼志愿者招募启动",
        processed_markdown="报名方式：扫描二维码报名，招募志愿者参与毕业典礼服务。",
        raw_markdown="",
    )
    event = Event(event_id="event_content_7", article_id=article.article_id, title=article.title)

    result = ContentClassifier().classify(article, event)

    assert result.is_event_related is True
    assert result.activity_kind == "volunteer_recruitment"


def test_classifier_marks_lecture_separately() -> None:
    article = Article(
        article_id="article_content_8",
        mp_name="北京大学人文学部",
        title="预告——【人文讲座】（第476讲）：培育丰厚感性——高科技时代美育的使命",
        processed_markdown="时间：2026年6月18日 地点：人文学苑",
        raw_markdown="",
    )
    event = Event(event_id="event_content_8", article_id=article.article_id, title=article.title)

    result = ContentClassifier().classify(article, event)

    assert result.is_event_related is True
    assert result.activity_kind == "lecture"
