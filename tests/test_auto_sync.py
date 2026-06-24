"""自动同步服务测试。"""

import pytest
from apscheduler.triggers.cron import CronTrigger

from app.utils.cron import parse_cron


class TestParseCron:
    def test_five_field_cron(self) -> None:
        trigger = parse_cron("0 * * * *")
        assert isinstance(trigger, CronTrigger)

    def test_two_field_cron(self) -> None:
        trigger = parse_cron("30 9")
        assert isinstance(trigger, CronTrigger)

    def test_three_field_cron(self) -> None:
        trigger = parse_cron("0 9 *")
        assert isinstance(trigger, CronTrigger)

    def test_invalid_cron_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_cron("bad")

    def test_single_field_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_cron("0")
