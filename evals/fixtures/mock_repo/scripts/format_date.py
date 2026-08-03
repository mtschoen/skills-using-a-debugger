MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def format_date(year, month, day):
    """Return a human-readable date string, e.g. 'March 5, 2026'."""
    month_name = MONTHS[month]
    date_str = f"{month_name} {day}, {year}"
    return date_str
