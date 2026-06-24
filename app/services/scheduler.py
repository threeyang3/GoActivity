"""定时任务调度服务。

使用 APScheduler 实现日报/周报的定时发送。
"""

import contextlib
import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import get_settings
from app.utils.cron import parse_cron
from app.db import SessionLocal
from app.services.feishu_messenger import FeishuMessenger
from app.services.report_service import ReportService

logger = logging.getLogger(__name__)


class ReportScheduler:
    """日报/周报定时任务调度器。"""

    def __init__(self) -> None:
        self.scheduler = BackgroundScheduler()
        self.settings = get_settings()

    def start(self) -> None:
        """启动定时任务调度器。"""
        # 每天发日报
        if self.settings.feishu_report_daily_enabled:
            daily_cron = self.settings.feishu_report_daily_cron
            if daily_cron:
                try:
                    trigger = parse_cron(daily_cron)
                    self.scheduler.add_job(
                        self._send_daily_report,
                        trigger,
                        id="daily_report",
                        name="日报发送",
                        replace_existing=True,
                    )
                    logger.info("Scheduled daily report with cron: %s", daily_cron)
                except ValueError as e:
                    logger.warning("Invalid daily cron expression '%s': %s", daily_cron, e)
        else:
            logger.info("Daily report disabled")

        # 每周发周报
        if self.settings.feishu_report_weekly_enabled:
            weekly_cron = self.settings.feishu_report_weekly_cron
            if weekly_cron:
                try:
                    trigger = parse_cron(weekly_cron)
                    self.scheduler.add_job(
                        self._send_weekly_report,
                        trigger,
                        id="weekly_report",
                        name="周报发送",
                        replace_existing=True,
                    )
                    logger.info("Scheduled weekly report with cron: %s", weekly_cron)
                except ValueError as e:
                    logger.warning("Invalid weekly cron expression '%s': %s", weekly_cron, e)
        else:
            logger.info("Weekly report disabled")

        self.scheduler.start()
        logger.info("Report scheduler started")

    def shutdown(self) -> None:
        """关闭定时任务调度器。"""
        self.scheduler.shutdown()
        logger.info("Report scheduler stopped")

    def _send_report(self, report_type: str) -> None:
        """发送报告（日报或周报）。"""
        logger.info("Sending %s report...", report_type)
        try:
            with contextlib.closing(SessionLocal()) as db:
                report_service = ReportService(db)
                report = report_service.daily_report() if report_type == "daily" else report_service.weekly_report()
                messenger = FeishuMessenger()
                send_method = messenger.send_daily_report if report_type == "daily" else messenger.send_weekly_report
                result = send_method(report)
                if result.get("ok"):
                    logger.info("%s report sent successfully", report_type.capitalize())
                else:
                    logger.error("Failed to send %s report: %s", report_type, result.get("error"))
        except Exception as e:
            logger.error("Error sending %s report: %s", report_type, e)

    def _send_daily_report(self) -> None:
        """发送日报。"""
        self._send_report("daily")

    def _send_weekly_report(self) -> None:
        """发送周报。"""
        self._send_report("weekly")

