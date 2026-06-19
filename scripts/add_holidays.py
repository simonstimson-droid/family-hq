#!/usr/bin/env python3
"""
Add UK bank holidays and family special days to data.json.
Run annually or whenever the calendar needs refreshing.

Usage: python3 add_holidays.py [year]
Default year = current year + next year
"""
import json, sys, os
from datetime import date, timedelta

DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data.json')

def get_uk_bank_holidays(year):
    """Return UK bank holidays for a given year."""
    holidays = {
        f"{year}-01-01": ("🎆 New Year's Day", ""),
        f"{year}-04-18": ("🐣 Good Friday", ""),  # 2026
        f"{year}-04-21": ("🐣 Easter Monday", ""),  # 2026
        f"{year}-05-05": ("🏦 Early May Bank Holiday", ""),
        f"{year}-05-25": ("🏦 Late May Bank Holiday", ""),
        f"{year}-08-31": ("🏦 Summer Bank Holiday", ""),
        f"{year}-12-25": ("🎄 Christmas Day", ""),
        f"{year}-12-28": ("🎁 Boxing Day", ""),
    }
    # Adjust Easter dates for other years
    if year == 2027:
        holidays[f"{year}-04-02"] = ("🐣 Good Friday", "")
        holidays[f"{year}-04-05"] = ("🐣 Easter Monday", "")
    elif year == 2025:
        holidays[f"{year}-04-18"] = ("🐣 Good Friday", "")
        holidays[f"{year}-04-21"] = ("🐣 Easter Monday", "")
    return holidays

def get_father_day(year):
    """Father's Day is the 3rd Sunday of June."""
    jun1 = date(year, 6, 1)
    # Find first Sunday in June
    days_until_sunday = (6 - jun1.weekday()) % 7
    first_sunday = jun1 + timedelta(days=days_until_sunday)
    third_sunday = first_sunday + timedelta(weeks=2)
    return third_sunday.isoformat()

def get_mother_day(year):
    """Mother's Day (Mothering Sunday) is the 4th Sunday of Lent (3 weeks before Easter)."""
    # Simplified: use known dates
    mothering = {
        2026: "2026-03-22",
        2027: "2027-03-14",
        2025: "2025-03-30",
    }
    return mothering.get(year)

def get_summer_solstice(year):
    """Summer solstice is usually June 20 or 21."""
    solstice_dates = {
        2026: "2026-06-20",
        2027: "2027-06-21",
        2025: "2025-06-21",
    }
    return solstice_dates.get(year)

def get_october_half_term(year):
    """October half term is last week of October."""
    # Last Monday of October
    oct31 = date(year, 10, 31)
    days_since_monday = oct31.weekday()
    last_monday = oct31 - timedelta(days=days_since_monday)
    return last_monday.isoformat()

def main():
    years = [int(sys.argv[1])] if len(sys.argv) > 1 else [date.today().year, date.today().year + 1]
    
    with open(DATA_PATH, 'r') as f:
        data = json.load(f)
    
    rows = data.get('📅 Calendar', {}).get('rows', [])
    
    # Build existing keys for dedup
    existing = set()
    for r in rows:
        existing.add(f"{r.get('Date')}|{r.get('Event', '').strip().lower()}")
    
    to_add = []
    
    for year in years:
        # UK Bank Holidays
        for d, (name, notes) in get_uk_bank_holidays(year).items():
            key = f"{d}|{name.strip().lower()}"
            if key not in existing:
                to_add.append({'Date': d, 'Time': 'All day', 'Event': name, 'Who': '', 'Location': '', 'Notes': notes})
                existing.add(key)
        
        # Father's Day
        fd = get_father_day(year)
        if fd:
            key = f"{fd}|father's day"
            if key not in existing:
                to_add.append({'Date': fd, 'Time': 'All day', 'Event': "☀️ Father's Day", 'Who': 'Simon', 'Location': '', 'Notes': "Dad's special day"})
                existing.add(key)
        
        # Mother's Day
        md = get_mother_day(year)
        if md:
            key = f"{md}|mother's day"
            if key not in existing:
                to_add.append({'Date': md, 'Time': 'All day', 'Event': "💐 Mother's Day", 'Who': 'Emma', 'Location': '', 'Notes': "Mum's special day"})
                existing.add(key)
        
        # Summer Solstice
        ss = get_summer_solstice(year)
        if ss:
            key = f"{ss}|summer solstice"
            if key not in existing:
                to_add.append({'Date': ss, 'Time': 'All day', 'Event': '☀️ Summer Solstice', 'Who': '', 'Location': '', 'Notes': 'Longest day of the year'})
                existing.add(key)
            
            # Solstice swim (afternoon)
            swim_key = f"{ss}|solstice swim"
            if swim_key not in existing:
                to_add.append({'Date': ss, 'Time': '17:00-18:30', 'Event': '🏊 Solstice Swim', 'Who': 'Both', 'Location': '', 'Notes': 'Family swim on the longest day'})
                existing.add(swim_key)
        
        # Halloween
        halloween = f"{year}-10-31"
        key = f"{halloween}|halloween"
        if key not in existing:
            to_add.append({'Date': halloween, 'Time': 'All day', 'Event': '🎃 Halloween', 'Who': 'Both', 'Location': '', 'Notes': 'Trick or treat!'})
            existing.add(key)
        
        # Bonfire Night
        bonfire = f"{year}-11-05"
        key = f"{bonfire}|bonfire night"
        if key not in existing:
            to_add.append({'Date': bonfire, 'Time': '18:00-21:00', 'Event': '🔥 Bonfire Night', 'Who': 'Both', 'Location': '', 'Notes': 'Fireworks & sparklers'})
            existing.add(key)
    
    if not to_add:
        print("No new holidays to add — all already present.")
        return
    
    rows.extend(to_add)
    
    # Sort
    def sort_key(e):
        d = e.get('Date', '9999-99-99')
        t = e.get('Time', '')
        if t == 'All day':
            time = '00:00'
        elif t:
            time = t.split('-')[0].strip()
        else:
            time = '00:00'
        return f"{d} {time}"
    
    rows.sort(key=sort_key)
    data['📅 Calendar'] = {
        "headers": ["Date", "Time", "Event", "Who", "Location", "Notes"],
        "rows": rows
    }
    
    with open(DATA_PATH, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Added {len(to_add)} holidays/special days to calendar")
    for e in to_add:
        print(f"  + {e['Date']} | {e['Event']}")

if __name__ == '__main__':
    main()
