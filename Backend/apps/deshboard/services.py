from __future__ import annotations
import logging
from . import queries

logger = logging.getLogger(__name__)

class DashboardService:

    def get_overview(self, user) -> dict:
        """
        All top-level counters + priority + category breakdowns in one response.
        Query count: 4 (summary, priority, category, tag).
        """
        summary    = queries.fetch_summary(user)
        priorities = queries.fetch_priority_breakdown(user)
        categories = queries.fetch_category_breakdown(user, limit=10)
        tags       = queries.fetch_tag_breakdown(user, limit=10)
        streak     = queries.fetch_completion_streak(user)
        upcoming   = queries.fetch_upcoming_deadlines(user, limit=5)
        recent     = queries.fetch_recent_completions(user, limit=5)

        logger.debug('Dashboard overview fetched for user=%s', user.id)
        return {
            'summary':    summary,
            'priorities': priorities,
            'categories': categories,
            'tags':       tags,
            'streak':     streak,
            'upcoming_deadlines': upcoming,
            'recent_completions': recent,
        }

    def get_weekly_progress(self, user, weeks: int = 8) -> dict:
        """
        Daily series (last 7 days) + weekly series (last N weeks).
        Query count: 4 (2 for daily, 2 for weekly).
        """
        weeks = min(max(weeks, 1), 52)
        return {
            'daily':  queries.fetch_daily_series(user, days=7),
            'weekly': queries.fetch_weekly_series(user, weeks=weeks),
        }

    def get_monthly_progress(self, user, months: int = 6) -> dict:
        """
        Monthly series + month-on-month summary.
        Query count: 2.
        """
        months = min(max(months, 1), 24)
        series = queries.fetch_monthly_series(user, months=months)

        # Compute month-on-month delta from the series
        mom_delta = None
        if len(series) >= 2:
            prev = series[-2]['completed']
            curr = series[-1]['completed']
            if prev > 0:
                mom_delta = round(((curr - prev) / prev) * 100, 1)
            elif curr > 0:
                mom_delta = 100.0
            else:
                mom_delta = 0.0

        return {
            'monthly': series,
            'month_on_month_delta': mom_delta,
        }

    def get_full_analytics(self, user, weeks: int = 8, months: int = 6) -> dict:
        """
        Combined endpoint for clients that want everything in one call.
        Query count: ~10 — all independent, no N+1.
        """
        return {
            **self.get_overview(user),
            'weekly_progress':  self.get_weekly_progress(user, weeks=weeks)['weekly'],
            'daily_progress':   self.get_weekly_progress(user, weeks=weeks)['daily'],
            'monthly_progress': self.get_monthly_progress(user, months=months)['monthly'],
            'month_on_month_delta': self.get_monthly_progress(user, months=months)['month_on_month_delta'],
        }
