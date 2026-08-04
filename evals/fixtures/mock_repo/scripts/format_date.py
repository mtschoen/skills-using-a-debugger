def format_date(year, month, day):
    # Off-by-one: month list is indexed 0-11 but month comes in 1-12.
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return f"{months[month]} {day}, {year}"
