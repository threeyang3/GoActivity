import re
from dataclasses import dataclass
from datetime import datetime

from app.models import Article, Event
from app.services.event_policy import SHANGHAI_TZ, parse_datetime


LABEL_SCORES = (
    ("演出时间", 120),
    ("活动时间", 120),
    ("讲座时间", 120),
    ("比赛时间", 120),
    ("举办时间", 115),
    ("会议时间", 115),
    ("时间", 100),
    ("日期", 95),
    ("截止时间", 80),
    ("报名截止", 80),
    ("征集截止", 75),
    ("截止", 70),
)

DATE_PATTERN = re.compile(
    r"(?P<raw>"
    r"(?:(?P<year>20\d{2})\s*年\s*)?"
    r"(?P<month>\d{1,2})\s*[月\-.\/]\s*"
    r"(?P<day>\d{1,2})\s*(?:日|号)?"
    r"(?:\s*[（(][^)）]*[)）])?"
    r"(?:\s*(?P<hour>\d{1,2})(?::|点|：)(?P<minute>\d{2})(?:\s*分)?(?:\s*(?P<ampm>上午|下午|晚上|中午|晚))?)?"
    r"(?:\s*(?P<tail>前|后))?"
    r")"
)

RANGE_CONNECTOR_PATTERN = re.compile(r"\s*(?:至|到|\-|—|–|~|～)\s*")
YEAR_PATTERN = re.compile(r"(20\d{2})\s*年")


@dataclass
class TimeCandidate:
    start_time: str
    end_time: str
    score: int
    reason: str


class TimeExtractor:
    def extract(self, article: Article, event: Event, ocr_text: str) -> TimeCandidate | None:
        publish_at = parse_datetime(article.publish_time)
        contexts = self._build_contexts(article, event, ocr_text)
        candidates: list[TimeCandidate] = []

        for text, base_score in contexts:
            for line in self._split_lines(text):
                candidate = self._extract_from_line(line, publish_at, base_score)
                if candidate:
                    candidates.append(candidate)

        if not candidates:
            return None
        candidates.sort(key=lambda item: item.score, reverse=True)
        return candidates[0]

    def _build_contexts(self, article: Article, event: Event, ocr_text: str) -> list[tuple[str, int]]:
        return [
            (article.title or event.title or "", 110),
            (article.processed_markdown or "", 100),
            (article.raw_markdown or "", 90),
            (ocr_text or "", 95),
        ]

    def _split_lines(self, text: str) -> list[str]:
        if not text:
            return []
        return [line.strip() for line in text.splitlines() if line.strip()]

    def _extract_from_line(self, line: str, publish_at: datetime | None, base_score: int) -> TimeCandidate | None:
        matches = list(DATE_PATTERN.finditer(line))
        if not matches:
            return None

        score = base_score + self._label_score(line)
        if "阅读原文" in line or "邮箱" in line:
            score -= 40

        if len(matches) >= 2:
            connector = line[matches[0].end() : matches[1].start()]
            if RANGE_CONNECTOR_PATTERN.search(connector):
                start_value = self._to_datetime(matches[0], line, publish_at)
                end_value = self._to_datetime(matches[1], line, publish_at, default_year=start_value.year if start_value else None)
                if start_value and end_value:
                    return TimeCandidate(
                        start_time=self._format_datetime(start_value),
                        end_time=self._format_datetime(end_value),
                        score=score + 15,
                        reason=line[:80],
                    )

        first_value = self._to_datetime(matches[0], line, publish_at)
        if not first_value:
            return None
        if any(keyword in line for keyword in ("截止", "截至", "报名", "征集")):
            score += 8
        if any(keyword in line for keyword in ("活动时间", "演出时间", "讲座时间", "举办时间")):
            score += 20
        return TimeCandidate(
            start_time=self._format_datetime(first_value),
            end_time="",
            score=score,
            reason=line[:80],
        )

    def _label_score(self, line: str) -> int:
        for label, score in LABEL_SCORES:
            if label in line:
                return score
        return 0

    def _to_datetime(
        self,
        match: re.Match[str],
        line: str,
        publish_at: datetime | None,
        default_year: int | None = None,
    ) -> datetime | None:
        year = match.group("year")
        inferred_year = int(year) if year else self._infer_year(line, publish_at, default_year)
        month = int(match.group("month"))
        day = int(match.group("day"))
        hour = int(match.group("hour")) if match.group("hour") else 0
        minute = int(match.group("minute")) if match.group("minute") else 0
        ampm = match.group("ampm") or ""
        tail = match.group("tail") or ""

        # 基本范围校验
        if month < 1 or month > 12:
            return None
        if day < 1 or day > 31:
            return None
        if hour < 0 or hour > 23:
            return None
        if minute < 0 or minute > 59:
            return None

        # 年份合理性校验（不允许太远的过去或未来）
        current_year = datetime.now(SHANGHAI_TZ).year
        if inferred_year < current_year - 1 or inferred_year > current_year + 2:
            return None

        if ampm in {"下午", "晚上", "晚"} and hour < 12:
            hour += 12
        if ampm == "中午" and hour < 12:
            hour = 12
        if tail == "前" and not match.group("hour"):
            hour = 23
            minute = 59

        raw = f"{inferred_year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:00"
        return parse_datetime(raw)

    def _infer_year(self, line: str, publish_at: datetime | None, default_year: int | None) -> int:
        years = [int(item) for item in YEAR_PATTERN.findall(line)]
        if years:
            return years[0]
        if default_year:
            return default_year
        if publish_at:
            return publish_at.astimezone(SHANGHAI_TZ).year
        return datetime.now(SHANGHAI_TZ).year

    def _format_datetime(self, value: datetime) -> str:
        return value.astimezone(SHANGHAI_TZ).strftime("%Y-%m-%d %H:%M:%S")

    def _extract_location_from_content(self, content: str) -> str:
        """从文章内容中提取地点信息。

        匹配常见地点模式：地点/地址：XXX、Venue: XXX、【XXX厅/馆】、讲堂XXX 等。
        返回提取到的地点字符串，未匹配则返回空字符串。
        """
        if not content:
            return ""

        # 地点：XXX / 地址：XXX
        m = re.search(r"(?:地点|地址)\s*[：:]\s*(.+?)(?:\n|$)", content)
        if m:
            return m.group(1).strip()

        # Venue: XXX
        m = re.search(r"[Vv]enue\s*[：:]\s*(.+?)(?:\n|$)", content)
        if m:
            return m.group(1).strip()

        # 【XXX厅】/【XXX馆】/【XXX中心】等
        m = re.search(r"【([^】]*(?:厅|馆|中心|剧院|剧场|会场|报告厅)[^】]*)】", content)
        if m:
            return m.group(1).strip()

        # 讲堂XXX
        m = re.search(r"(\S{0,10}讲堂\S{0,10})", content)
        if m:
            return m.group(1).strip()

        return ""


class LocationExtractor:
    """从文章内容中提取活动地点。"""

    # 地点关键词模式（按优先级排序）
    PATTERNS = [
        # "地点：XXX" / "地址：XXX"
        re.compile(r"(?:地点|地址|Venue|Location)[：:]\s*(.+?)(?:\n|$)", re.IGNORECASE),
        # "在XXX举办/举行/开展"
        re.compile(r"在(.{2,20}?)(?:举办|举行|开展|进行|召开)"),
        # "XXX厅/馆/楼/室"
        re.compile(r"((?:[一-龥]{2,8}(?:厅|馆|楼|室|堂|院|园|中心|报告厅|会议室|剧场|影院)))"),
        # "【XXX】" 中的地点
        re.compile(r"【([^】]{2,20}(?:厅|馆|楼|室|堂))】"),
    ]

    # 常见地点名称（校园相关）
    KNOWN_LOCATIONS = [
        "百周年纪念讲堂", "李莹厅", "讲堂观众厅", "讲堂李莹厅",
        "光华管理学院", "经济学院", "法学院", "历史学系",
        "图书馆", "理科教学楼", "文科教学楼", "第二教学楼",
        "静园二院", "外文楼", "化学楼", "物理楼",
    ]

    def extract(self, article: "Article", event: "Event", ocr_text: str) -> str:
        """从文章标题、内容、OCR文本中提取地点。"""
        # 如果已有地点，不覆盖
        if event.location:
            return ""

        # 优先从标题中提取
        location = self._extract_from_title(article.title or "")
        if location:
            return location

        # 从内容中提取
        content = article.processed_markdown or article.raw_markdown or ""
        location = self._extract_from_content(content)
        if location:
            return location

        # 从OCR文本中提取
        if ocr_text:
            location = self._extract_from_content(ocr_text)
            if location:
                return location

        return ""

    def _extract_from_title(self, title: str) -> str:
        """从标题中提取地点。"""
        # 检查已知地点
        for loc in self.KNOWN_LOCATIONS:
            if loc in title:
                return loc

        # 【XXX厅】模式
        m = re.search(r"【([^】]{2,20}(?:厅|馆|楼|室|堂))】", title)
        if m:
            return m.group(1)

        return ""

    def _extract_from_content(self, content: str) -> str:
        """从正文中提取地点。"""
        if not content:
            return ""

        # 只检查前2000字符（地点通常在文章开头）
        text = content[:2000]

        for pattern in self.PATTERNS:
            m = pattern.search(text)
            if m:
                location = m.group(1).strip()
                # 清理：去除多余标点和空白
                location = re.sub(r"[\s　\-—–·｜|：:，,。.！!？?]+$", "", location)
                location = re.sub(r"^[\s　\-—–·｜|：:，,。.！!？?]+", "", location)
                # 长度校验
                if 2 <= len(location) <= 50:
                    return location

        return ""
