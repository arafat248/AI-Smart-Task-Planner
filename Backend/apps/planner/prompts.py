from __future__ import annotations
from datetime import datetime
from typing import Any

PRIORITY_WEIGHT = {'urgent': 4, 'high': 3, 'medium': 2, 'low': 1}
PRIORITY_SORT   = {'urgent': 0, 'high': 1, 'medium': 2, 'low': 3}

def _format_task_row(task_dict: dict, idx: int) -> str:
    """Format a single task dict into a concise prompt row."""
    parts = [f'{idx}. [ID:{task_dict["id"]}]']
    priority = task_dict.get('priority', 'medium').upper()
    parts.append(f'[{priority}]')
    parts.append(f'"{task_dict["title"]}"')

    status = task_dict.get('status', 'todo')
    if status == 'in_progress':
        parts.append('(IN PROGRESS)')

    est = task_dict.get('estimated_minutes')
    if est:
        h, m = divmod(est, 60)
        parts.append(f'~{h}h{m}m' if h else f'~{m}min')

    deadline = task_dict.get('deadline')
    if deadline:
        parts.append(f'deadline:{deadline}')

    cat = task_dict.get('category')
    if cat:
        parts.append(f'[{cat}]')

    tags = task_dict.get('tags', [])
    if tags:
        parts.append(f'#{" #".join(tags)}')

    return ' '.join(parts)


def _capacity_block(available_hours: float, start: str, end: str) -> str:
    return (
        f'Available capacity: {available_hours} hours\n'
        f'Work window: {start} – {end}'
    )
RESPONSE_SCHEMA = '''
Return ONLY a valid JSON object matching this EXACT schema (no extra keys, no markdown):

{
  "summary": "string — 2-3 sentence motivational overview of the plan",

  "recommended_order": [
    {
      "task_id": <integer>,
      "title": "string",
      "rank": <integer — 1 = highest priority>,
      "reason": "string — why this task is ranked here (≤20 words)",
      "suggested_slot": "string — e.g. '9:00 AM – 10:30 AM'",
      "score": <integer 1-100 — composite urgency+importance score>
    }
  ],

  "time_blocks": [
    {
      "start": "string — HH:MM 24h e.g. '09:00'",
      "end":   "string — HH:MM 24h e.g. '10:30'",
      "title": "string — block label",
      "type":  "string — one of: work | break | lunch | buffer | admin",
      "task_id": <integer or null — null for non-task blocks>,
      "notes": "string — optional tip for this block"
    }
  ],

  "break_suggestions": [
    {
      "after_block": <integer — 1-indexed position in time_blocks>,
      "time": "string — HH:MM 24h",
      "duration_minutes": <integer>,
      "type": "string — one of: short | long | lunch | walk | meditation",
      "reason": "string — why this break is suggested here"
    }
  ],

  "overdue_risk": {
    "risk_level": "string — one of: none | low | medium | high | critical",
    "risk_score":  <integer 0-100>,
    "at_risk_tasks": [
      {
        "task_id": <integer>,
        "title": "string",
        "deadline": "string — ISO date",
        "risk_reason": "string — specific reason this task is at risk",
        "mitigation": "string — concrete action to reduce risk"
      }
    ],
    "overloaded_days": ["string — ISO dates where capacity is exceeded"],
    "analysis": "string — 2-3 sentence overall risk assessment"
  },

  "productivity_score": {
    "overall":      <integer 0-100>,
    "focus":        <integer 0-100 — depth of uninterrupted work time>,
    "feasibility":  <integer 0-100 — can all tasks fit in available hours>,
    "balance":      <integer 0-100 — work/break ratio health>,
    "urgency_load": <integer 0-100 — proportion of urgent/high tasks>,
    "advice": [
      "string — specific, actionable improvement (not generic)",
      "string",
      "string"
    ]
  },

  "tips": [
    "string — practical tip 1 specific to THIS task list",
    "string — tip 2",
    "string — tip 3"
  ]
}
'''
def build_daily_prompt(
    tasks: list[dict],
    plan_date: str,
    available_hours: float,
    work_start: str,
    work_end: str,
) -> str:
    today = datetime.now().strftime('%A, %B %d %Y')
    task_block = '\n'.join(
        _format_task_row(t, i + 1) for i, t in enumerate(tasks)
    ) or '(no pending tasks — suggest a planning and review session)'

    total_est = sum(t.get('estimated_minutes', 0) or 0 for t in tasks)
    total_est_h = round(total_est / 60, 1)
    capacity_pct = round((total_est / (available_hours * 60)) * 100) if available_hours else 0

    overdue_tasks = [t for t in tasks if t.get('is_overdue')]
    overdue_block = ''
    if overdue_tasks:
        overdue_block = '\nOVERDUE TASKS (must be addressed first or flagged):\n' + '\n'.join(
            f'  ⚠ [ID:{t["id"]}] "{t["title"]}" — was due {t["deadline"]}'
            for t in overdue_tasks
        )

    urgent_tasks = [t for t in tasks if t.get('priority') in ('urgent', 'high')]
    priority_pressure = 'HIGH' if len(urgent_tasks) > 3 else ('MEDIUM' if urgent_tasks else 'LOW')

    return f"""You are an expert AI productivity coach and cognitive scientist with deep knowledge of time-boxing, deep work, and task prioritisation frameworks (Eisenhower Matrix, GTD, PARA).

Today's date: {today}
Planning for: {plan_date}

{_capacity_block(available_hours, work_start, work_end)}
Total estimated work: {total_est_h}h across {len(tasks)} tasks
Capacity utilisation: {capacity_pct}% of available hours
Priority pressure: {priority_pressure}
{overdue_block}

TASK LIST:
{task_block}

YOUR JOB:
1. Analyse the task list holistically — consider deadlines, priorities, energy levels across the day, and cognitive load.
2. Build a REALISTIC daily schedule that fits within {work_start}–{work_end}.
3. Apply time-boxing: assign specific start/end times to each task block.
4. Insert strategic breaks (Pomodoro-style or Ultradian rhythm — every 90 min of deep work).
5. Identify overdue risk for any task whose deadline is within 48 hours or where estimated time exceeds remaining available time.
6. Score the plan's overall productivity quality (0-100) with sub-scores.
7. Provide SPECIFIC, ACTIONABLE tips — not generic productivity clichés.

RULES:
- Schedule urgent tasks before 11 AM while cognitive energy is highest.
- Never schedule >90 minutes of focused work without a break.
- Lunch break must be 30-60 minutes.
- Buffer 15 min between heavy cognitive tasks.
- If total estimated time > available hours: flag which tasks to defer, do not overload the schedule.
- For in_progress tasks: show as continuing, not starting fresh.
- Rank tasks: urgent (overdue) > urgent (deadline <24h) > high (deadline <48h) > high > medium > low.
{RESPONSE_SCHEMA}"""

def build_weekly_prompt(
    tasks: list[dict],
    plan_date: str,
    available_hours: float,
    work_start: str,
    work_end: str,
) -> str:
    today = datetime.now().strftime('%A, %B %d %Y')
    task_block = '\n'.join(
        _format_task_row(t, i + 1) for i, t in enumerate(tasks)
    ) or '(no pending tasks)'

    total_est = sum(t.get('estimated_minutes', 0) or 0 for t in tasks)
    total_est_h = round(total_est / 60, 1)
    weekly_capacity = available_hours * 5

    return f"""You are an expert AI productivity coach specialising in weekly planning, OKRs, and deep work strategies.

Today's date: {today}
Week starting: {plan_date}

{_capacity_block(available_hours, work_start, work_end)} per day ({weekly_capacity}h total for the week)
Total estimated work: {total_est_h}h across {len(tasks)} tasks

TASK LIST:
{task_block}

YOUR JOB:
1. Distribute tasks across Monday–Friday with a theme-based approach (batch similar tasks on the same day).
2. Front-load the week: place urgent/high-priority tasks Mon–Wed.
3. Reserve Thursday for deep work / project focus.
4. Friday: review, low-priority tasks, planning for next week.
5. Build in daily buffer time (30-60 min) for unexpected work.
6. Analyse which tasks are at risk of not being completed this week.
7. Score the week's plan for feasibility, balance, focus quality.

For time_blocks, use day names (e.g. "Monday Morning", "Tuesday Afternoon") instead of clock times.
For break_suggestions, suggest end-of-day wind-down and mid-day walks.
{RESPONSE_SCHEMA}"""
