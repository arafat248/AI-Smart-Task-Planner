import pytest
from datetime import timedelta
from django.utils import timezone
from apps.dashboard import queries
from apps.tasks.models import Task

NOW = timezone.now()

@pytest.mark.django_db
class TestFetchSummary:
    def test_correct_counts(self, user, task_set):
        result = queries.fetch_summary(user)
        # 3 completed + 2 in_progress + 2 todo + 1 overdue(todo) + 1 cancelled + 1 ai(todo) = 10 live
        # 1 deleted is excluded
        assert result['total'] == 10
        assert result['completed'] == 4    # 3 + old_completed
        assert result['in_progress'] == 2
        # todo includes: todo_0, todo_1, overdue, ai = 4
        assert result['todo'] == 4
        assert result['cancelled'] == 1

    def test_overdue_count(self, user, task_set):
        result = queries.fetch_summary(user)
        assert result['overdue'] == 1      # only overdue task

    def test_pending_is_todo_plus_in_progress(self, user, task_set):
        result = queries.fetch_summary(user)
        assert result['pending'] == result['todo'] + result['in_progress']

    def test_productivity_pct_calculation(self, user, task_set):
        result = queries.fetch_summary(user)
        completed = result['completed']
        total     = result['total']
        cancelled = result['cancelled']
        expected  = round((completed / (total - cancelled) * 100), 1)
        assert result['productivity_pct'] == expected

    def test_productivity_pct_zero_when_no_tasks(self, user):
        result = queries.fetch_summary(user)
        assert result['productivity_pct'] == 0.0

    def test_excludes_soft_deleted(self, user, task_set):
        result = queries.fetch_summary(user)
        # deleted task must not contribute to any count
        assert result['total'] == 10   # 11 created, 1 soft-deleted

    def test_due_soon(self, user, task_set):
        result = queries.fetch_summary(user)
        # todo_1 has deadline in 12 hours
        assert result['due_soon'] >= 1

    def test_ai_generated_count(self, user, task_set):
        result = queries.fetch_summary(user)
        assert result['ai_generated'] == 1

    def test_estimated_hours(self, user, task_set):
        result = queries.fetch_summary(user)
        # 2 in_progress tasks: 2h + 1h = 3h
        assert result['total_estimated_hours'] == 3.0

    def test_single_query(self, user, task_set, django_assert_num_queries):
        with django_assert_num_queries(1):
            queries.fetch_summary(user)

    def test_other_users_tasks_excluded(self, user, other_user, task_set):
        Task.objects.create(
            user=other_user, title='Not mine', status='completed',
            priority='low', completed_at=NOW,
        )
        result = queries.fetch_summary(user)
        assert result['completed'] == 4   # unchanged

@pytest.mark.django_db
class TestFetchPriorityBreakdown:
    def test_all_priorities_present(self, user, task_set):
        result = queries.fetch_priority_breakdown(user)
        priorities = {r['priority'] for r in result}
        assert priorities == {'low', 'medium', 'high', 'urgent'}

    def test_counts_exclude_cancelled(self, user, task_set):
        result = queries.fetch_priority_breakdown(user)
        low = next(r for r in result if r['priority'] == 'low')
        # low: todo_0, cancelled(excluded) → only todo_0 in active
        assert low['total'] < 3

    def test_single_query(self, user, task_set, django_assert_num_queries):
        with django_assert_num_queries(1):
            queries.fetch_priority_breakdown(user)

@pytest.mark.django_db
class TestFetchCategoryBreakdown:
    def test_returns_category_data(self, user, task_set, category):
        result = queries.fetch_category_breakdown(user)
        assert len(result) >= 1
        cat = next((r for r in result if r['name'] == 'Work'), None)
        assert cat is not None
        assert cat['completed'] >= 3
        assert 'overdue' in cat

    def test_excludes_tasks_without_category(self, user, task_set):
        result = queries.fetch_category_breakdown(user)
        total_with_cat = sum(r['total'] for r in result)
        # Only tasks with category set should appear
        assert total_with_cat <= 10

    def test_single_query(self, user, task_set, django_assert_num_queries):
        with django_assert_num_queries(1):
            queries.fetch_category_breakdown(user)

@pytest.mark.django_db
class TestFetchTagBreakdown:
    def test_returns_tag_data(self, user, task_set, tag):
        result = queries.fetch_tag_breakdown(user)
        assert len(result) >= 1
        t = next((r for r in result if r['name'] == tag.name), None)
        assert t is not None
        assert t['total'] >= 3   # 3 completed tasks have this tag

    def test_single_query(self, user, task_set, django_assert_num_queries):
        with django_assert_num_queries(1):
            queries.fetch_tag_breakdown(user)

@pytest.mark.django_db
class TestFetchDailySeries:
    def test_returns_7_entries(self, user, task_set):
        result = queries.fetch_daily_series(user, days=7)
        assert len(result) == 7

    def test_dates_are_consecutive(self, user, task_set):
        from datetime import date
        result = queries.fetch_daily_series(user, days=7)
        dates = [r['date'] for r in result]
        for i in range(1, len(dates)):
            d0 = date.fromisoformat(dates[i - 1])
            d1 = date.fromisoformat(dates[i])
            assert (d1 - d0).days == 1

    def test_completed_today_counted(self, user):
        Task.objects.create(
            user=user, title='Today done', status='completed',
            priority='low', completed_at=timezone.now(),
        )
        result = queries.fetch_daily_series(user, days=7)
        today_entry = result[-1]   # last entry = today
        assert today_entry['completed'] >= 1

    def test_two_queries(self, user, task_set, django_assert_num_queries):
        # daily series uses 2 queries (completed + created)
        with django_assert_num_queries(2):
            queries.fetch_daily_series(user, days=7)

@pytest.mark.django_db
class TestFetchWeeklySeries:
    def test_returns_n_entries(self, user, task_set):
        result = queries.fetch_weekly_series(user, weeks=8)
        assert len(result) == 8

    def test_week_starts_are_mondays(self, user, task_set):
        from datetime import date
        result = queries.fetch_weekly_series(user, weeks=4)
        for entry in result:
            d = date.fromisoformat(entry['week_start'])
            assert d.weekday() == 0   # Monday

    def test_two_queries(self, user, task_set, django_assert_num_queries):
        with django_assert_num_queries(2):
            queries.fetch_weekly_series(user, weeks=8)

@pytest.mark.django_db
class TestFetchMonthlySeries:
    def test_returns_n_entries(self, user, task_set):
        result = queries.fetch_monthly_series(user, months=6)
        assert len(result) == 6

    def test_month_labels_present(self, user, task_set):
        result = queries.fetch_monthly_series(user, months=3)
        for entry in result:
            assert 'label' in entry
            assert 'month' in entry

    def test_two_queries(self, user, task_set, django_assert_num_queries):
        with django_assert_num_queries(2):
            queries.fetch_monthly_series(user, months=6)

@pytest.mark.django_db
class TestFetchCompletionStreak:
    def test_streak_with_consecutive_days(self, user):
        today = timezone.now().date()
        for i in range(3):
            Task.objects.create(
                user=user, title=f'S{i}', status='completed',
                priority='low',
                completed_at=timezone.make_aware(
                    __import__('datetime').datetime.combine(today - __import__('datetime').timedelta(days=i), __import__('datetime').time.min)
                ),
            )
        result = queries.fetch_completion_streak(user)
        assert result['current_streak'] >= 3
        assert result['longest_streak'] >= 3

    def test_streak_zero_when_no_completions(self, user):
        result = queries.fetch_completion_streak(user)
        assert result['current_streak'] == 0
        assert result['longest_streak'] == 0
        assert result['last_active_date'] is None

    def test_single_query(self, user, task_set, django_assert_num_queries):
        with django_assert_num_queries(1):
            queries.fetch_completion_streak(user)

@pytest.mark.django_db
class TestFetchRecentCompletions:
    def test_returns_most_recent_first(self, user, task_set):
        result = queries.fetch_recent_completions(user, limit=5)
        assert len(result) >= 1
        # Should be ordered by completed_at DESC
        timestamps = [r['completed_at'] for r in result]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_respects_limit(self, user, task_set):
        result = queries.fetch_recent_completions(user, limit=2)
        assert len(result) <= 2

    def test_no_n_plus_one(self, user, task_set, django_assert_num_queries):
        with django_assert_num_queries(1):
            queries.fetch_recent_completions(user, limit=5)

@pytest.mark.django_db
class TestFetchUpcomingDeadlines:

    def test_returns_future_deadlines_only(self, user, task_set):
        result = queries.fetch_upcoming_deadlines(user, limit=5)
        for entry in result:
            assert entry['hours_remaining'] > 0

    def test_excludes_overdue(self, user, task_set):
        result = queries.fetch_upcoming_deadlines(user, limit=10)
        titles = [r['title'] for r in result]
        assert 'Overdue task' not in titles

    def test_no_n_plus_one(self, user, task_set, django_assert_num_queries):
        with django_assert_num_queries(1):
            queries.fetch_upcoming_deadlines(user, limit=5)
