"""Request-scoped Uruguay clock, requested periods and date hints for ranking."""
import calendar
import re
import unicodedata
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

URUGUAY = ZoneInfo('America/Montevideo')
DAYS = ('lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo')
MONTHS = ('enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre')


def plain(text):
    return ''.join(c for c in unicodedata.normalize('NFD', text.lower()) if not unicodedata.combining(c))


def clock_snapshot(now=None):
    local = (now or datetime.now(timezone.utc)).astimezone(URUGUAY)
    monday = local.date() - timedelta(days=local.weekday())
    return {'now': local.isoformat(timespec='seconds'), 'date': local.date().isoformat(),
            'time': local.strftime('%H:%M:%S'), 'weekday': DAYS[local.weekday()],
            'timezone': 'America/Montevideo', 'utc_offset': local.strftime('%z'),
            'date_label': f'{local.day} de {MONTHS[local.month - 1]} de {local.year}',
            'week_start': monday.isoformat(), 'week_end': (monday + timedelta(days=6)).isoformat(),
            'source': 'system_clock'}


def clock_answer(snapshot):
    return f"Hoy es {snapshot['weekday']} {snapshot['date_label']}. Son las {snapshot['time']}, hora de Uruguay."


def clock_context(snapshot):
    return (f"RELOJ REAL DEL SERVIDOR (no inferir desde entrenamiento ni historial): {snapshot['now']}; "
            f"{snapshot['weekday']} {snapshot['date_label']}; zona {snapshot['timezone']}. "
            f"Esta semana calendario va del {snapshot['week_start']} al {snapshot['week_end']}. "
            "Las horas se refieren a Uruguay. Una fecha pasada no es un evento próximo. "
            "La fecha de publicación/consulta de una página NO es la fecha del evento. "
            "No supongas que un festival anual se repite en otra fecha o año.")


def has_relative_time(text):
    return bool(re.search(r'\b(hoy|ahora|manana|esta semana|proxima semana|semana que viene|fin de semana|este mes|esta noche)\b', plain(text)))


def is_event_query(text):
    q = plain(text)
    return bool(re.search(r'\b(eventos?|agenda|cartelera|espectaculos?|conciertos?|festivales?|actividades culturales)\b', q))


def event_window(query, snapshot):
    """Upcoming dates only unless an explicit date/month is requested."""
    today = date.fromisoformat(snapshot['date'])
    monday = today - timedelta(days=today.weekday())
    q = plain(query)
    if 'proxima semana' in q or 'semana que viene' in q:
        start = monday + timedelta(days=7)
        end = start + timedelta(days=6)
    elif 'proximo fin de semana' in q:
        start, end = monday + timedelta(days=12), monday + timedelta(days=13)
    elif 'fin de semana' in q:
        start, end = max(today, monday + timedelta(days=5)), monday + timedelta(days=6)
    elif 'esta semana' in q:
        start, end = today, monday + timedelta(days=6)
    elif 'manana' in q:
        start = end = today + timedelta(days=1)
    elif re.search(r'\b(hoy|esta noche|ahora)\b', q):
        start = end = today
    elif 'este mes' in q:
        start, end = today, date(today.year, today.month, calendar.monthrange(today.year, today.month)[1])
    else:
        dates = explicit_dates(q)
        month = next((i + 1 for i, name in enumerate(MONTHS) if re.search(r'\b' + name + r'\b', q)), None)
        if dates:
            start, end = min(dates), max(dates)
        elif month:
            year_match = re.search(r'\b(20\d{2})\b', q)
            year = int(year_match[1]) if year_match else today.year + int('proximo' in q and month < today.month)
            start, end = date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
        else:
            start, end = today, today + timedelta(days=30)
    return {'start': start.isoformat(), 'end': end.isoformat()}


def explicit_dates(text):
    """Only dates with an explicit year; never infer it from a footer/copyright."""
    q = plain(text)
    values = []
    for y, m, d in re.findall(r'\b(20\d{2})-(\d{1,2})-(\d{1,2})\b', q):
        values.append((y, m, d))
    for d, m, y in re.findall(r'\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2})\b', q):
        values.append((y, m, d))
    month_pattern = '|'.join(MONTHS) + '|setiembre'
    for match in re.finditer(rf'\b(?:(\d{{1,2}})\s*(?:al|y|-)\s*)?(\d{{1,2}})\s+(?:de\s+)?({month_pattern})\s*(?:de\s+|,\s*)?(20\d{{2}})\b', q):
        first, last, month, year = match.groups()
        month_number = 9 if month == 'setiembre' else MONTHS.index(month) + 1
        values.append((year, month_number, last))
        if first:
            values.append((year, month_number, first))
    dates = []
    for y, m, d in values:
        try:
            dates.append(date(int(y), int(m), int(d)))
        except ValueError:
            pass
    return dates
