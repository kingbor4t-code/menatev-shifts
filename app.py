import os
import re
import streamlit as st
import sqlite3
import pandas as pd
import random
from ortools.sat.python import cp_model

st.set_page_config(page_title="מערכת שיבוץ", page_icon="🪖", layout="wide", initial_sidebar_state="collapsed")


def inject_responsive_css():
    st.markdown(
        """
        <style>
            :root {
                color-scheme: dark;
            }
            .block-container {
                padding-top: 1rem !important;
                padding-bottom: 3rem !important;
            }
            [data-testid="stSidebar"] {
                background: #111827;
            }
            [data-testid="stSidebarContent"] {
                padding-top: 0.75rem;
            }
            .stButton > button,
            .stDownloadButton > button,
            .stFormSubmitButton > button {
                min-height: 44px;
                border-radius: 10px;
            }
            .stButton > button,
            .stFormSubmitButton > button {
                width: 100%;
            }
            .shift-table {
                width: 100%;
                border-collapse: collapse;
                direction: rtl;
                unicode-bidi: plaintext;
            }
            .shift-table th,
            .shift-table td {
                padding: 12px;
                text-align: center;
                font-size: 15px;
                white-space: nowrap;
            }
            .shift-table th {
                font-size: 16px;
                font-weight: 700;
            }
            .shift-table td {
                font-size: 14px;
            }
            .table-wrapper {
                overflow-x: auto;
                -webkit-overflow-scrolling: touch;
                padding: 0;
            }
            @media (max-width: 768px) {
                .block-container {
                    padding-left: 0.5rem !important;
                    padding-right: 0.5rem !important;
                }
                .stRadio > div {
                    flex-direction: column;
                    align-items: flex-start;
                }
                .stButton > button,
                .stFormSubmitButton > button {
                    width: 100%;
                    font-size: 1rem;
                }
                .table-wrapper {
                    padding: 0;
                    overflow-x: auto;
                    -webkit-overflow-scrolling: touch;
                    width: 100vw;
                    margin-left: calc(-50vw + 50%);
                }
                .shift-table {
                    width: auto;
                    min-width: 100%;
                }
                .shift-table th,
                .shift-table td {
                    padding: 14px 10px;
                    font-size: 16px;
                    white-space: normal;
                    word-break: break-word;
                }
                .shift-table th {
                    font-size: 17px;
                    font-weight: 700;
                    padding: 16px 10px;
                }
                .shift-table th:first-child,
                .shift-table td:first-child {
                    min-width: 130px;
                }
                .shift-table td {
                    min-width: 90px;
                }
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


inject_responsive_css()

# יצירת חיבור למסד הנתונים
base_dir = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(base_dir, 'my_shifts.db')
conn = sqlite3.connect(db_path)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS soldiers 
             (id INTEGER PRIMARY KEY AUTOINCREMENT, 
              name TEXT, 
              can_close_weekend BOOLEAN,
              closed_previous_weekend BOOLEAN DEFAULT 0)''')

# טבלה לאפטרים מרובים
c.execute('''CREATE TABLE IF NOT EXISTS soldier_afters 
             (id INTEGER PRIMARY KEY AUTOINCREMENT,
              soldier_id INTEGER,
              after_day INTEGER,
              FOREIGN KEY(soldier_id) REFERENCES soldiers(id))''')

# טבלה לחופשות מרובות
c.execute('''CREATE TABLE IF NOT EXISTS soldier_vacations 
             (id INTEGER PRIMARY KEY AUTOINCREMENT,
              soldier_id INTEGER,
              vacation_start INTEGER,
              vacation_end INTEGER,
              FOREIGN KEY(soldier_id) REFERENCES soldiers(id))''')

# טבלה לגימלים (לא ניתן לעשות משמרת ביום זה, וביום שלאחר מכן אין בוקר)
c.execute('''CREATE TABLE IF NOT EXISTS soldier_gimels 
             (id INTEGER PRIMARY KEY AUTOINCREMENT,
              soldier_id INTEGER,
              gimal_start INTEGER,
              gimal_end INTEGER,
              FOREIGN KEY(soldier_id) REFERENCES soldiers(id))''')

# טבלה לנעילות משמרת ספציפית
c.execute('''CREATE TABLE IF NOT EXISTS soldier_locked_shifts 
             (id INTEGER PRIMARY KEY AUTOINCREMENT,
              soldier_id INTEGER,
              shift_day INTEGER,
              shift_type INTEGER,
              FOREIGN KEY(soldier_id) REFERENCES soldiers(id))''')

# טבלה לאיסור משמרת ספציפי
c.execute('''CREATE TABLE IF NOT EXISTS soldier_forbidden_shifts 
             (id INTEGER PRIMARY KEY AUTOINCREMENT,
              soldier_id INTEGER,
              shift_day INTEGER,
              shift_type INTEGER,
              FOREIGN KEY(soldier_id) REFERENCES soldiers(id))''')

# טבלה לתורנויות שבועיות
c.execute('''CREATE TABLE IF NOT EXISTS weekly_duties 
             (id INTEGER PRIMARY KEY AUTOINCREMENT,
              duty_day INTEGER,
              duty_type TEXT,
              person_name TEXT)''')

# טבלה לאירועים חופשיים לפי יום
c.execute('''CREATE TABLE IF NOT EXISTS weekly_events 
             (id INTEGER PRIMARY KEY AUTOINCREMENT,
              event_day INTEGER,
              event_text TEXT)''')

# טבלה להפניות חופשיות לפי יום
c.execute('''CREATE TABLE IF NOT EXISTS weekly_references 
             (id INTEGER PRIMARY KEY AUTOINCREMENT,
              reference_day INTEGER,
              reference_text TEXT)''')

# טבלה לאחזקות שבועיות
c.execute('''CREATE TABLE IF NOT EXISTS weekly_maintenance 
             (id INTEGER PRIMARY KEY AUTOINCREMENT,
              maintenance_day INTEGER,
              person_name TEXT)''')

# טבלה לר"צ כונן בחצי שבת
c.execute('''CREATE TABLE IF NOT EXISTS weekly_rc_kinun 
             (id INTEGER PRIMARY KEY AUTOINCREMENT,
              person_name TEXT)''')

c.execute("PRAGMA table_info(soldiers)")
existing_columns = {row[1] for row in c.fetchall()}
if 'closed_previous_weekend' not in existing_columns:
    c.execute('ALTER TABLE soldiers ADD COLUMN closed_previous_weekend BOOLEAN DEFAULT 0')

conn.commit()

st.title("מערכת שיבוץ - ניהול אילוצים")

# Helper: safe rerun to support Streamlit versions without experimental_rerun
def safe_rerun():
    rerun_fn = getattr(st, 'experimental_rerun', None)
    if callable(rerun_fn):
        try:
            rerun_fn()
            return
        except Exception:
            pass
    # Fallback: stop execution and show hint to user
    st.warning("רענן את הדף כדי לראות את העדכונים.")
    st.stop()

day_names = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"]
shift_names = ["בוקר 06:30-12:30", "צהריים 12:30-18:30", "ערב 18:30-00:30", "לילה 00:30-06:30"]
duty_types = ["רס''ר", "מטבח", "רס''פ", "גדודית"]


def normalize_name(value):
    return (value or "").strip().casefold()

page = st.sidebar.radio(
    "עמודים",
    ["שיבוץ", "ניהול חיילים", "כל האילוצים", "ניהול ר\"צ/תורנויות/אחזקות"]
)

if page == "שיבוץ":
    st.subheader("שיבוץ שבועי")
    if st.button("צור שיבוץ אוטומטי לשבוע הקרוב"):
        run_schedule = True
    else:
        run_schedule = False

    if run_schedule:
        soldiers = c.execute('SELECT id, name, can_close_weekend, COALESCE(closed_previous_weekend, 0) FROM soldiers').fetchall()
        closers_count = sum(1 for s in soldiers if s[2] == 1)
        random.shuffle(soldiers)
        previous_closers = [s_idx for s_idx in range(len(soldiers)) if soldiers[s_idx][3] == 1]

        if len(soldiers) < 4:
            st.error("חסרים חיילים! צריך לפחות 4 חיילים כדי ליצור סבב הגיוני.")
        elif closers_count < 3:
            st.error(f"יש רק {closers_count} סוגרי שבת. צריך לפחות 3 סוגרים כדי לאייש את כל המשמרות בצורה תקינה!")
        else:
            model = cp_model.CpModel()
            num_days = 7
            num_shifts = 4
            num_soldiers = len(soldiers)

            soldier_index_by_id = {soldier[0]: idx for idx, soldier in enumerate(soldiers)}
            soldier_lock_map = {}
            for s_idx in range(len(soldiers)):
                soldier_id = soldiers[s_idx][0]
                locked_rows = c.execute('SELECT shift_day, shift_type FROM soldier_locked_shifts WHERE soldier_id = ?', (soldier_id,)).fetchall()
                soldier_lock_map[soldier_id] = [(row[0], row[1]) for row in locked_rows]

            soldier_name_to_id = {normalize_name(soldier[1]): soldier[0] for soldier in soldiers}
            soldier_id_to_name = {soldier[0]: soldier[1] for soldier in soldiers}

            def parse_person_names(raw_name):
                tokens = [t for t in re.split(r'[\s,;]+', raw_name.strip()) if t]
                names = []
                for token in tokens:
                    normalized = normalize_name(token)
                    if normalized in soldier_name_to_id:
                        names.append((token, normalized))
                        continue
                    if token.startswith('ו'):
                        stripped = token[1:]
                        normalized_stripped = normalize_name(stripped)
                        if normalized_stripped in soldier_name_to_id:
                            names.append((stripped, normalized_stripped))
                            continue
                    if normalized in soldier_name_to_id:
                        names.append((token, normalized))
                return names

            duty_assignments = {}
            duties = c.execute('SELECT duty_day, duty_type, person_name FROM weekly_duties').fetchall()
            for duty_day, duty_type, person_name in duties:
                matching_soldier_id = soldier_name_to_id.get(normalize_name(person_name))
                if matching_soldier_id is not None:
                    duty_assignments.setdefault(matching_soldier_id, []).append((duty_day, duty_type))

            maintenance_assignments = {}
            maintenances = c.execute('SELECT maintenance_day, person_name FROM weekly_maintenance').fetchall()
            for maintenance_day, person_name in maintenances:
                for _, normalized in parse_person_names(person_name):
                    soldier_id = soldier_name_to_id.get(normalized)
                    if soldier_id is not None:
                        maintenance_assignments.setdefault(soldier_id, []).append(maintenance_day)

            required_assignments = []
            for soldier_id, locks in soldier_lock_map.items():
                s_idx = soldier_index_by_id.get(soldier_id)
                if s_idx is None:
                    continue
                for lock_day, lock_shift in locks:
                    if 0 <= lock_day < num_days and 0 <= lock_shift < num_shifts:
                        required_assignments.append((s_idx, lock_day, lock_shift))

            forbidden_assignments = []
            forbidden_rows = c.execute('SELECT soldier_id, shift_day, shift_type FROM soldier_forbidden_shifts').fetchall()
            for soldier_id, forbid_day, forbid_shift in forbidden_rows:
                s_idx = soldier_index_by_id.get(soldier_id)
                if s_idx is None:
                    continue
                if 0 <= forbid_day < num_days and 0 <= forbid_shift < num_shifts:
                    forbidden_assignments.append((s_idx, forbid_day, forbid_shift))

            shifts = {}
            for s in range(num_soldiers):
                for d in range(num_days):
                    for sh in range(num_shifts):
                        shifts[(s, d, sh)] = model.NewBoolVar(f'shift_{s}_{d}_{sh}')

            for d in range(num_days):
                for sh in range(num_shifts):
                    model.Add(sum(shifts[(s, d, sh)] for s in range(num_soldiers)) == 1)

            for s_idx, lock_day, lock_shift in required_assignments:
                model.Add(shifts[(s_idx, lock_day, lock_shift)] == 1)

            required_shift_keys_by_soldier = {}
            for s_idx, lock_day, lock_shift in required_assignments:
                required_shift_keys_by_soldier.setdefault(s_idx, set()).add((lock_day, lock_shift))

            for s_idx, forbid_day, forbid_shift in forbidden_assignments:
                model.Add(shifts[(s_idx, forbid_day, forbid_shift)] == 0)

            all_violations = []
            for s in range(num_soldiers):
                all_shifts_flat = [shifts[(s, d, sh)] for d in range(num_days) for sh in range(num_shifts)]
                regular_shift_vars = [shifts[(s, d, sh)] for d in range(0, 4) for sh in range(num_shifts)]
                soldier_shift_count = model.NewIntVar(0, len(all_shifts_flat), f'soldier_shift_count_{s}')
                regular_shift_count = model.NewIntVar(0, len(regular_shift_vars), f'regular_shift_count_{s}')
                model.Add(soldier_shift_count == sum(all_shifts_flat))
                model.Add(regular_shift_count == sum(regular_shift_vars))
                has_shift = model.NewBoolVar(f'has_shift_{s}')
                model.Add(regular_shift_count >= 1).OnlyEnforceIf(has_shift)
                model.Add(regular_shift_count == 0).OnlyEnforceIf(has_shift.Not())
                all_violations.append(has_shift.Not() * 1000)
                for i in range(len(all_shifts_flat) - 1):
                    v_consecutive = model.NewBoolVar(f'v_cons_{s}_{i}')
                    model.Add(all_shifts_flat[i] + all_shifts_flat[i+1] <= 1 + v_consecutive)
                    all_violations.append(v_consecutive * 10000)
                    if i + 2 < len(all_shifts_flat):
                        v_gap1 = model.NewBoolVar(f'v_gap1_{s}_{i}')
                        model.Add(all_shifts_flat[i] + all_shifts_flat[i+2] <= 1 + v_gap1)
                        all_violations.append(v_gap1 * 100)
                # העדפת אי חזרה על אותו סוג משמרת בתוך 24 שעות (רך - לא חובה)
                for d in range(num_days - 1):
                    for sh in range(num_shifts):
                        v_same_shift_repeat = model.NewBoolVar(f'v_same_shift_repeat_{s}_{d}_{sh}')
                        model.Add(shifts[(s, d, sh)] + shifts[(s, d+1, sh)] <= 1 + v_same_shift_repeat)
                        all_violations.append(v_same_shift_repeat * 800)

            for s in range(num_soldiers):
                for d in range(num_days):
                    daily_shifts = sum(shifts[(s, d, sh)] for sh in range(num_shifts))
                    v_overload = model.NewIntVar(0, 4, f'v_overload_{s}_{d}')
                    model.Add(daily_shifts - 2 <= v_overload)
                    all_violations.append(v_overload * 50)

            if previous_closers:
                previous_closer_shift_vars = [shifts[(s_idx, 0, sh)] for s_idx in previous_closers for sh in range(2)]
                previous_closer_count = model.NewIntVar(0, len(previous_closer_shift_vars), 'previous_closer_count')
                model.Add(previous_closer_count == sum(previous_closer_shift_vars))
                previous_closer_missing = model.NewBoolVar('previous_closer_missing')
                model.Add(previous_closer_count >= 1).OnlyEnforceIf(previous_closer_missing.Not())
                model.Add(previous_closer_count == 0).OnlyEnforceIf(previous_closer_missing)
                all_violations.append(previous_closer_missing * 2000)

            for s_idx in range(num_soldiers):
                soldier_id = soldiers[s_idx][0]
                is_closer = soldiers[s_idx][2] == 1
                weekend_days = range(4, 7)
                weekday_days = range(0, 4)
                weekday_shift_vars = [shifts[(s_idx, d, sh)] for d in weekday_days for sh in range(num_shifts)]

                required_shift_keys = required_shift_keys_by_soldier.get(s_idx, set())

                if not is_closer:
                    for d in weekend_days:
                        for sh in range(num_shifts):
                            if (d, sh) in required_shift_keys:
                                continue
                            v_weekend = model.NewBoolVar(f'v_weekend_{s_idx}_{d}_{sh}')
                            model.Add(shifts[(s_idx, d, sh)] <= v_weekend)
                            all_violations.append(v_weekend * 5000)
                    if (3, 3) not in required_shift_keys:
                        v_wed_night_non_closer = model.NewBoolVar(f'v_wed_night_non_closer_{s_idx}')
                        model.Add(shifts[(s_idx, 3, 3)] <= v_wed_night_non_closer)
                        all_violations.append(v_wed_night_non_closer * 5000)

                    has_weekday_shift = model.NewBoolVar(f'has_weekday_shift_{s_idx}')
                    model.Add(sum(weekday_shift_vars) >= 1).OnlyEnforceIf(has_weekday_shift)
                    model.Add(sum(weekday_shift_vars) == 0).OnlyEnforceIf(has_weekday_shift.Not())
                    all_violations.append(has_weekday_shift.Not() * 300)
                else:
                    for shift_var in weekday_shift_vars:
                        all_violations.append(shift_var * 250)

                for duty_day, _ in duty_assignments.get(soldier_id, []):
                    model.Add(sum(shifts[(s_idx, duty_day, sh)] for sh in range(num_shifts)) == 0)
                    if duty_day - 1 >= 0:
                        model.Add(shifts[(s_idx, duty_day - 1, 3)] == 0)

                for maintenance_day in maintenance_assignments.get(soldier_id, []):
                    model.Add(sum(shifts[(s_idx, maintenance_day, sh)] for sh in range(num_shifts)) == 0)
                    if maintenance_day - 1 >= 0:
                        model.Add(shifts[(s_idx, maintenance_day - 1, 3)] == 0)

                afters = c.execute('SELECT after_day FROM soldier_afters WHERE soldier_id = ?', (soldier_id,)).fetchall()
                for after_row in afters:
                    after_day = after_row[0]
                    model.Add(sum(shifts[(s_idx, after_day, sh)] for sh in range(num_shifts)) == 0)
                    if after_day - 1 >= 0:
                        model.Add(shifts[(s_idx, after_day - 1, 3)] == 0)
                    if after_day + 1 < num_days:
                        model.Add(shifts[(s_idx, after_day + 1, 0)] == 0)

                vacations = c.execute('SELECT vacation_start, vacation_end FROM soldier_vacations WHERE soldier_id = ?', (soldier_id,)).fetchall()
                for vac_row in vacations:
                    vacation_start, vacation_end = vac_row
                    if vacation_end < vacation_start:
                        vacation_end = vacation_start
                    for d in range(vacation_start, vacation_end + 1):
                        model.Add(sum(shifts[(s_idx, d, sh)] for sh in range(num_shifts)) == 0)
                    if vacation_end + 1 < num_days:
                        model.Add(shifts[(s_idx, vacation_end + 1, 0)] == 0)

                gimels = c.execute('SELECT gimal_start, gimal_end FROM soldier_gimels WHERE soldier_id = ?', (soldier_id,)).fetchall()
                for gimal_row in gimels:
                    gimal_start, gimal_end = gimal_row
                    if gimal_end < gimal_start:
                        gimal_end = gimal_start
                    for d in range(gimal_start, gimal_end + 1):
                        model.Add(sum(shifts[(s_idx, d, sh)] for sh in range(num_shifts)) == 0)
                    if gimal_end + 1 < num_days:
                        model.Add(shifts[(s_idx, gimal_end + 1, 0)] == 0)

            model.Minimize(sum(all_violations))
            solver = cp_model.CpSolver()
            solver.parameters.random_seed = random.randint(1, 10000)
            status = solver.Solve(model)

            if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
                if status == cp_model.FEASIBLE:
                    st.warning("השיבוץ נוצר, אבל בגלל אילוצי כוח אדם המערכת נאלצה לצמצם שעות מנוחה לחלק מהחיילים.")
                else:
                    st.success("השיבוץ נוצר בהצלחה!")

                days_hebrew = ["יום שבת", "יום שישי", "יום חמישי", "יום רביעי", "יום שלישי", "יום שני", "יום ראשון"]
                shift_names = ["בוקר 06:30-12:30", "צהריים 12:30-18:30", "ערב 18:30-00:30", "לילה 00:30-06:30"]
                data = []
                for sh in range(num_shifts):
                    row = []
                    for d in reversed(range(num_days)):
                        for s_idx in range(num_soldiers):
                            if solver.Value(shifts[(s_idx, d, sh)]) == 1:
                                row.append(soldiers[s_idx][1])
                    row.append(shift_names[sh])
                    data.append(row)

                rc_entries = c.execute('SELECT person_name FROM weekly_rc_kinun ORDER BY id DESC').fetchall()
                rc_name = rc_entries[0][0] if rc_entries else None
                rc_map = {6: rc_name} if rc_name else {}

                maintenance_entries = c.execute('SELECT maintenance_day, person_name FROM weekly_maintenance').fetchall()
                maintenance_map = {}
                for maintenance_day, person_name in maintenance_entries:
                    maintenance_map[maintenance_day] = person_name

                duties = c.execute('SELECT duty_day, person_name, duty_type FROM weekly_duties').fetchall()
                duty_map = {}
                for duty_day, person_name, duty_type in duties:
                    duty_map[duty_day] = f"{person_name} - {duty_type}"

                after_map = {}
                after_entries = c.execute('SELECT soldier_id, after_day FROM soldier_afters').fetchall()
                for soldier_id, after_day in after_entries:
                    after_map.setdefault(after_day, []).append(soldier_id_to_name.get(soldier_id, ""))
                after_map = {day: ", ".join(names) for day, names in after_map.items()}

                vacation_map = {}
                vacations = c.execute('SELECT soldier_id, vacation_start, vacation_end FROM soldier_vacations').fetchall()
                for soldier_id, vacation_start, vacation_end in vacations:
                    if vacation_end < vacation_start:
                        vacation_end = vacation_start
                    for d in range(vacation_start, vacation_end + 1):
                        vacation_map.setdefault(d, []).append(soldier_id_to_name.get(soldier_id, ""))
                vacation_map = {day: ", ".join(names) for day, names in vacation_map.items()}

                gimal_map = {}
                gimels = c.execute('SELECT soldier_id, gimal_start, gimal_end FROM soldier_gimels').fetchall()
                for soldier_id, gimal_start, gimal_end in gimels:
                    if gimal_end < gimal_start:
                        gimal_end = gimal_start
                    for d in range(gimal_start, gimal_end + 1):
                        gimal_map.setdefault(d, []).append(soldier_id_to_name.get(soldier_id, ""))
                gimal_map = {day: ", ".join(names) for day, names in gimal_map.items()}

                if rc_name:
                    rc_row = []
                    for d in reversed(range(num_days)):
                        rc_row.append(rc_map.get(d, ""))
                    rc_row.append("ר\"צ כונן")
                    data.append(rc_row)

                if maintenance_map:
                    maintenance_row = []
                    for d in reversed(range(num_days)):
                        maintenance_row.append(maintenance_map.get(d, ""))
                    maintenance_row.append("אחזקות - חצור")
                    data.append(maintenance_row)

                if duty_map:
                    duty_row = []
                    for d in reversed(range(num_days)):
                        duty_row.append(duty_map.get(d, ""))
                    duty_row.append("תורנות")
                    data.append(duty_row)

                event_map = {}
                event_entries = c.execute('SELECT event_day, event_text FROM weekly_events').fetchall()
                for event_day, event_text in event_entries:
                    if event_text is not None and event_text.strip():
                        event_map.setdefault(event_day, []).append(event_text.strip())
                event_map = {day: ", ".join(texts) for day, texts in event_map.items()}

                if event_map:
                    event_row = []
                    for d in reversed(range(num_days)):
                        event_row.append(event_map.get(d, ""))
                    event_row.append("אירוע")
                    data.append(event_row)

                reference_map = {}
                reference_entries = c.execute('SELECT reference_day, reference_text FROM weekly_references').fetchall()
                for reference_day, reference_text in reference_entries:
                    if reference_text is not None and reference_text.strip():
                        reference_map.setdefault(reference_day, []).append(reference_text.strip())
                reference_map = {day: ", ".join(texts) for day, texts in reference_map.items()}

                if after_map:
                    after_row = []
                    for d in reversed(range(num_days)):
                        after_row.append(after_map.get(d, ""))
                    after_row.append("אפטר")
                    data.append(after_row)

                if vacation_map:
                    vacation_row = []
                    for d in reversed(range(num_days)):
                        vacation_row.append(vacation_map.get(d, ""))
                    vacation_row.append("חופש")
                    data.append(vacation_row)

                if reference_map:
                    reference_row = []
                    for d in reversed(range(num_days)):
                        reference_row.append(reference_map.get(d, ""))
                    reference_row.append("הפניה")
                    data.append(reference_row)

                if gimal_map:
                    gimal_row = []
                    for d in reversed(range(num_days)):
                        gimal_row.append(gimal_map.get(d, ""))
                    gimal_row.append("גימלים")
                    data.append(gimal_row)

                df = pd.DataFrame(data, columns=days_hebrew + ["משמרת"])
                def html_escape(text):
                    return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

                table_rows = []
                table_rows.append('<tr>')
                for column in reversed(df.columns.tolist()):
                    table_rows.append(f'<th>{html_escape(column)}</th>')
                table_rows.append('</tr>')

                for row_index, row in df.iterrows():
                    if row_index == 3:
                        table_rows.append('<tr style="border-bottom:4px solid #444;">')
                    else:
                        table_rows.append('<tr>')
                    for value in reversed(list(row)):
                        table_rows.append(f'<td>{html_escape(value)}</td>')
                    table_rows.append('</tr>')

                table_html = f'''
                    <style>
                        .table-wrapper {{display: flex; justify-content: center; width: 100%; max-width: 100%; margin: 0 auto; padding: 0; overflow-x: auto; -webkit-overflow-scrolling: touch;}}
                        .shift-table {{border-collapse: collapse; width: auto; margin: 0 auto; table-layout: auto; direction: rtl; unicode-bidi: plaintext;}}
                        .shift-table th, .shift-table td {{border: 1px solid #555; padding: 14px 10px; text-align: center; font-size: 16px; line-height: 1.4;}}
                        .shift-table th {{background: #1f2937; color: #fff; font-weight: 700; font-size: 17px;}}
                        .shift-table tr:nth-child(even) {{background: rgba(255,255,255,0.02);}}
                        .shift-table td {{min-width: 100px;}}
                        .shift-table th:first-child, .shift-table td:first-child {{min-width: 140px;}}
                    </style>
                    <div class="table-wrapper">
                        <table class="shift-table">
                            {''.join(table_rows)}
                        </table>
                    </div>
                '''
                st.markdown(table_html, unsafe_allow_html=True)
            else:
                st.error("לא נמצא פתרון - נסה להוסיף חיילים למערכת.")
    else:
        st.info("לחץ על 'צור שיבוץ אוטומטי לשבוע הקרוב' כדי לראות את הטבלה.")

elif page == "ניהול חיילים":
    st.subheader("ניהול חיילים")
    with st.form(key='add_soldier_form', clear_on_submit=True):
        new_name = st.text_input("שם חייל:")
        can_close = st.checkbox("יכול לסגור שבת במקור?")
        prev_closed = st.checkbox("סגר שבת קודמת?")
        submit_button = st.form_submit_button(label='הוסף חייל')

    if submit_button and new_name:
        c.execute('INSERT INTO soldiers (name, can_close_weekend, closed_previous_weekend) VALUES (?, ?, ?)', (new_name, can_close, prev_closed))
        conn.commit()
        safe_rerun()

    soldiers = c.execute('SELECT id, name, can_close_weekend, COALESCE(closed_previous_weekend, 0) FROM soldiers ORDER BY name').fetchall()
    soldier_names = [name for _, name, _, _ in soldiers]
    selected_name = st.selectbox("בחר חייל לעדכון:", ["בחר חייל..."] + soldier_names)

    if selected_name != "בחר חייל...":
        selected_id = next((soldier_id for soldier_id, name, _, _ in soldiers if name == selected_name), None)
        if selected_id is not None:
            selected = c.execute('SELECT id, name, can_close_weekend, COALESCE(closed_previous_weekend, 0) FROM soldiers WHERE id = ?', (selected_id,)).fetchone()
            if selected:
                soldier_id, name, can_close, prev_closed = selected
                st.write(f"### {name}")
                col1, col2 = st.columns([2, 1.2])
                with col1:
                    is_checked = st.checkbox("סוגר שבת", value=bool(can_close), key=f"check_sel_{soldier_id}")
                with col2:
                    prev_checked = st.checkbox("סגר שבת קודמת", value=bool(prev_closed), key=f"prev_check_sel_{soldier_id}")
                if is_checked != bool(can_close):
                    c.execute('UPDATE soldiers SET can_close_weekend = ? WHERE id = ?', (int(is_checked), soldier_id))
                    conn.commit()
                    safe_rerun()
                if prev_checked != bool(prev_closed):
                    c.execute('UPDATE soldiers SET closed_previous_weekend = ? WHERE id = ?', (int(prev_checked), soldier_id))
                    conn.commit()
                    safe_rerun()

                if st.button("מחק חייל זה", key=f"del_soldier_{soldier_id}"):
                    c.execute('DELETE FROM soldiers WHERE id = ?', (soldier_id,))
                    c.execute('DELETE FROM soldier_afters WHERE soldier_id = ?', (soldier_id,))
                    c.execute('DELETE FROM soldier_vacations WHERE soldier_id = ?', (soldier_id,))
                    c.execute('DELETE FROM soldier_gimels WHERE soldier_id = ?', (soldier_id,))
                    c.execute('DELETE FROM soldier_locked_shifts WHERE soldier_id = ?', (soldier_id,))
                    c.execute('DELETE FROM soldier_forbidden_shifts WHERE soldier_id = ?', (soldier_id,))
                    conn.commit()
                    safe_rerun()

                st.write("#### אפטרים")
                afters = c.execute('SELECT id, after_day FROM soldier_afters WHERE soldier_id = ?', (soldier_id,)).fetchall()
                for after_id, after_day in afters:
                    after_label = day_names[after_day]
                    col_a1, col_a2 = st.columns([3, 0.5])
                    col_a1.write(f"• {after_label}")
                    if col_a2.button("❌", key=f"del_sel_after_{after_id}"):
                        c.execute('DELETE FROM soldier_afters WHERE id = ?', (after_id,))
                        conn.commit()
                        safe_rerun()
                with st.form(key=f'form_after_sel_{soldier_id}', clear_on_submit=True):
                    after_day_add = st.selectbox("הוסף אפטר ביום", ["בחר יום..."] + day_names, index=0, key=f"add_after_sel_{soldier_id}")
                    if st.form_submit_button("הוסף אפטר"):
                        if after_day_add != "בחר יום...":
                            after_day_idx = day_names.index(after_day_add)
                            c.execute('INSERT INTO soldier_afters (soldier_id, after_day) VALUES (?, ?)', (soldier_id, after_day_idx))
                            conn.commit()
                            safe_rerun()

                st.write("#### חופשות")
                vacations = c.execute('SELECT id, vacation_start, vacation_end FROM soldier_vacations WHERE soldier_id = ?', (soldier_id,)).fetchall()
                for vac_id, vac_start, vac_end in vacations:
                    start_label = day_names[vac_start]
                    end_label = day_names[vac_end]
                    col_v1, col_v2 = st.columns([3, 0.5])
                    col_v1.write(f"• {start_label} - {end_label}")
                    if col_v2.button("❌", key=f"del_sel_vac_{vac_id}"):
                        c.execute('DELETE FROM soldier_vacations WHERE id = ?', (vac_id,))
                        conn.commit()
                        safe_rerun()
                with st.form(key=f'form_vac_sel_{soldier_id}', clear_on_submit=True):
                    vac_col_start, vac_col_end = st.columns([1.5, 1.5])
                    vac_start_option = vac_col_start.selectbox("חופש מתחיל ביום", ["בחר יום..."] + day_names, index=0, key=f"vac_start_sel_{soldier_id}")
                    vac_end_option = vac_col_end.selectbox("חופש מסתיים ביום", ["בחר יום..."] + day_names, index=0, key=f"vac_end_sel_{soldier_id}")
                    if st.form_submit_button("הוסף חופש"):
                        if vac_start_option != "בחר יום..." and vac_end_option != "בחר יום...":
                            vac_start_idx = day_names.index(vac_start_option)
                            vac_end_idx = day_names.index(vac_end_option)
                            if vac_end_idx < vac_start_idx:
                                vac_end_idx = vac_start_idx
                            c.execute('INSERT INTO soldier_vacations (soldier_id, vacation_start, vacation_end) VALUES (?, ?, ?)', (soldier_id, vac_start_idx, vac_end_idx))
                            conn.commit()
                            safe_rerun()

                st.write("#### גימלים")
                gimels = c.execute('SELECT id, gimal_start, gimal_end FROM soldier_gimels WHERE soldier_id = ?', (soldier_id,)).fetchall()
                for gimal_id, gimal_start, gimal_end in gimels:
                    start_label = day_names[gimal_start]
                    end_label = day_names[gimal_end]
                    col_g1, col_g2 = st.columns([3, 0.5])
                    col_g1.write(f"• {start_label} עד {end_label}")
                    if col_g2.button("❌", key=f"del_sel_gimal_{gimal_id}"):
                        c.execute('DELETE FROM soldier_gimels WHERE id = ?', (gimal_id,))
                        conn.commit()
                        safe_rerun()
                with st.form(key=f'form_gimal_sel_{soldier_id}', clear_on_submit=True):
                    gimal_col_start, gimal_col_end = st.columns([1.5, 1.5])
                    gimal_start_option = gimal_col_start.selectbox("גימלים מתחילים ביום", ["בחר יום..."] + day_names, index=0, key=f"gimal_start_sel_{soldier_id}")
                    gimal_end_option = gimal_col_end.selectbox("גימלים מסתיימים ביום", ["בחר יום..."] + day_names, index=0, key=f"gimal_end_sel_{soldier_id}")
                    if st.form_submit_button("הוסף גימלים"):
                        if gimal_start_option != "בחר יום..." and gimal_end_option != "בחר יום...":
                            gimal_start_idx = day_names.index(gimal_start_option)
                            gimal_end_idx = day_names.index(gimal_end_option)
                            if gimal_end_idx < gimal_start_idx:
                                gimal_end_idx = gimal_start_idx
                            c.execute('INSERT INTO soldier_gimels (soldier_id, gimal_start, gimal_end) VALUES (?, ?, ?)', (soldier_id, gimal_start_idx, gimal_end_idx))
                            conn.commit()
                            safe_rerun()

                st.write("#### משמרות חייבות")
                locked_shifts = c.execute('SELECT id, shift_day, shift_type FROM soldier_locked_shifts WHERE soldier_id = ?', (soldier_id,)).fetchall()
                for lock_id, lock_day, lock_shift in locked_shifts:
                    lock_label = f"{day_names[lock_day]} - {shift_names[lock_shift]}"
                    lock_col1, lock_col2 = st.columns([3, 0.5])
                    lock_col1.write(f"• {lock_label}")
                    if lock_col2.button("❌", key=f"del_sel_lock_{lock_id}"):
                        c.execute('DELETE FROM soldier_locked_shifts WHERE id = ?', (lock_id,))
                        conn.commit()
                        safe_rerun()
                with st.form(key=f'form_lock_sel_{soldier_id}', clear_on_submit=True):
                    lock_col_day, lock_col_shift = st.columns([1.5, 1.5])
                    lock_day_option = lock_col_day.selectbox("חייב ביום", ["בחר יום..."] + day_names, index=0, key=f"lock_day_sel_{soldier_id}")
                    lock_shift_option = lock_col_shift.selectbox("משמרת", ["בחר משמרת..." ] + shift_names, index=0, key=f"lock_shift_sel_{soldier_id}")
                    if st.form_submit_button("הוסף חובה"):
                        if lock_day_option != "בחר יום..." and lock_shift_option != "בחר משמרת...":
                            lock_day_idx = day_names.index(lock_day_option)
                            lock_shift_idx = shift_names.index(lock_shift_option)
                            c.execute('INSERT INTO soldier_locked_shifts (soldier_id, shift_day, shift_type) VALUES (?, ?, ?)', (soldier_id, lock_day_idx, lock_shift_idx))
                            conn.commit()
                            safe_rerun()

                st.write("#### משמרות אסורות")
                forbidden_shifts = c.execute('SELECT id, shift_day, shift_type FROM soldier_forbidden_shifts WHERE soldier_id = ?', (soldier_id,)).fetchall()
                for forbid_id, forbid_day, forbid_shift in forbidden_shifts:
                    forbid_label = f"{day_names[forbid_day]} - {shift_names[forbid_shift]}"
                    forbid_col1, forbid_col2 = st.columns([3, 0.5])
                    forbid_col1.write(f"• {forbid_label}")
                    if forbid_col2.button("❌", key=f"del_sel_forbid_{forbid_id}"):
                        c.execute('DELETE FROM soldier_forbidden_shifts WHERE id = ?', (forbid_id,))
                        conn.commit()
                        safe_rerun()
                with st.form(key=f'form_forbid_sel_{soldier_id}', clear_on_submit=True):
                    forbid_col_day, forbid_col_shift = st.columns([1.5, 1.5])
                    forbid_day_option = forbid_col_day.selectbox("אסור ביום", ["בחר יום..."] + day_names, index=0, key=f"forbid_day_sel_{soldier_id}")
                    forbid_shift_option = forbid_col_shift.selectbox("משמרת", ["בחר משמרת..."] + shift_names, index=0, key=f"forbid_shift_sel_{soldier_id}")
                    if st.form_submit_button("הוסף אסור"):
                        if forbid_day_option != "בחר יום..." and forbid_shift_option != "בחר משמרת...":
                            forbid_day_idx = day_names.index(forbid_day_option)
                            forbid_shift_idx = shift_names.index(forbid_shift_option)
                            c.execute('INSERT INTO soldier_forbidden_shifts (soldier_id, shift_day, shift_type) VALUES (?, ?, ?)', (soldier_id, forbid_day_idx, forbid_shift_idx))
                            conn.commit()
                            safe_rerun()
            else:
                st.error("חייל לא נמצא.")

elif page == "כל האילוצים":
    st.subheader("כל האילוצים השבועיים")
    if st.button("אפס את כל האילוצים"):
        c.execute('DELETE FROM soldier_afters')
        c.execute('DELETE FROM soldier_vacations')
        c.execute('DELETE FROM soldier_gimels')
        c.execute('DELETE FROM soldier_locked_shifts')
        c.execute('DELETE FROM soldier_forbidden_shifts')
        c.execute('DELETE FROM weekly_references')
        conn.commit()
        safe_rerun()

    st.write("### אפטרים")
    after_entries = c.execute('SELECT id, soldier_id, after_day FROM soldier_afters ORDER BY after_day, id').fetchall()
    if after_entries:
        for after_id, soldier_id, after_day in after_entries:
            row_col1, row_col2 = st.columns([3, 0.5])
            soldier_name = c.execute('SELECT name FROM soldiers WHERE id = ?', (soldier_id,)).fetchone()
            row_col1.write(f"• {soldier_name[0] if soldier_name else '---'} - {day_names[after_day]}")
            if row_col2.button("❌", key=f"del_all_after_{after_id}"):
                c.execute('DELETE FROM soldier_afters WHERE id = ?', (after_id,))
                conn.commit()
                safe_rerun()
    else:
        st.write("אין אפטרים")

    st.write("### חופשות")
    vacation_entries = c.execute('SELECT id, soldier_id, vacation_start, vacation_end FROM soldier_vacations ORDER BY vacation_start, id').fetchall()
    if vacation_entries:
        for vac_id, soldier_id, vacation_start, vacation_end in vacation_entries:
            soldier_name = c.execute('SELECT name FROM soldiers WHERE id = ?', (soldier_id,)).fetchone()
            start_label = day_names[vacation_start]
            end_label = day_names[vacation_end]
            row_col1, row_col2 = st.columns([3, 0.5])
            row_col1.write(f"• {soldier_name[0] if soldier_name else '---'} - {start_label} עד {end_label}")
            if row_col2.button("❌", key=f"del_all_vac_{vac_id}"):
                c.execute('DELETE FROM soldier_vacations WHERE id = ?', (vac_id,))
                conn.commit()
                safe_rerun()
    else:
        st.write("אין חופשות")

    st.write("### גימלים")
    gimal_entries = c.execute('SELECT id, soldier_id, gimal_start, gimal_end FROM soldier_gimels ORDER BY gimal_start, id').fetchall()
    if gimal_entries:
        for gimal_id, soldier_id, gimal_start, gimal_end in gimal_entries:
            soldier_name = c.execute('SELECT name FROM soldiers WHERE id = ?', (soldier_id,)).fetchone()
            start_label = day_names[gimal_start]
            end_label = day_names[gimal_end]
            row_col1, row_col2 = st.columns([3, 0.5])
            row_col1.write(f"• {soldier_name[0] if soldier_name else '---'} - {start_label} עד {end_label}")
            if row_col2.button("❌", key=f"del_all_gimal_{gimal_id}"):
                c.execute('DELETE FROM soldier_gimels WHERE id = ?', (gimal_id,))
                conn.commit()
                safe_rerun()
    else:
        st.write("אין גימלים")

    st.write("### משמרות חייבות")
    locked_entries = c.execute('SELECT id, soldier_id, shift_day, shift_type FROM soldier_locked_shifts ORDER BY shift_day, shift_type, id').fetchall()
    if locked_entries:
        for lock_id, soldier_id, shift_day, shift_type in locked_entries:
            soldier_name = c.execute('SELECT name FROM soldiers WHERE id = ?', (soldier_id,)).fetchone()
            row_col1, row_col2 = st.columns([3, 0.5])
            row_col1.write(f"• {soldier_name[0] if soldier_name else '---'} - {day_names[shift_day]} {shift_names[shift_type]}")
            if row_col2.button("❌", key=f"del_all_lock_{lock_id}"):
                c.execute('DELETE FROM soldier_locked_shifts WHERE id = ?', (lock_id,))
                conn.commit()
                safe_rerun()
    else:
        st.write("אין משמרות חייבות")

    st.write("### משמרות אסורות")
    forbidden_entries = c.execute('SELECT id, soldier_id, shift_day, shift_type FROM soldier_forbidden_shifts ORDER BY shift_day, shift_type, id').fetchall()
    if forbidden_entries:
        for forbid_id, soldier_id, shift_day, shift_type in forbidden_entries:
            soldier_name = c.execute('SELECT name FROM soldiers WHERE id = ?', (soldier_id,)).fetchone()
            row_col1, row_col2 = st.columns([3, 0.5])
            row_col1.write(f"• {soldier_name[0] if soldier_name else '---'} - {day_names[shift_day]} {shift_names[shift_type]}")
            if row_col2.button("❌", key=f"del_all_forbid_{forbid_id}"):
                c.execute('DELETE FROM soldier_forbidden_shifts WHERE id = ?', (forbid_id,))
                conn.commit()
                safe_rerun()
    else:
        st.write("אין משמרות אסורות")

    st.write("### הפניות")
    reference_entries = c.execute('SELECT id, reference_day, reference_text FROM weekly_references ORDER BY reference_day, id').fetchall()
    if reference_entries:
        for reference_id, reference_day, reference_text in reference_entries:
            ref_col1, ref_col2 = st.columns([3, 0.5])
            ref_col1.write(f"• {day_names[reference_day]} - {reference_text}")
            if ref_col2.button("❌", key=f"del_all_reference_{reference_id}"):
                c.execute('DELETE FROM weekly_references WHERE id = ?', (reference_id,))
                conn.commit()
                safe_rerun()
    else:
        st.write("אין הפניות כרגע")

    with st.form(key='global_reference_form', clear_on_submit=True):
        reference_day_option = st.selectbox("יום הפניה", ["בחר יום..."] + day_names, index=0, key='global_reference_day')
        reference_text = st.text_input("טקסט חופשי להפניה", key='global_reference_text')
        if st.form_submit_button("הוסף הפניה"):
            if reference_day_option != "בחר יום..." and reference_text.strip():
                reference_day_idx = day_names.index(reference_day_option)
                c.execute('INSERT INTO weekly_references (reference_day, reference_text) VALUES (?, ?)', (reference_day_idx, reference_text.strip()))
                conn.commit()
                safe_rerun()

    st.divider()
    st.subheader("ניהול אפטרים וחופשות")
    soldiers = c.execute('SELECT id, name FROM soldiers ORDER BY name').fetchall()
    soldier_id_to_name = {soldier_id: name for soldier_id, name in soldiers}
    soldier_name_to_id = {name: soldier_id for soldier_id, name in soldiers}
    after_entries = c.execute('SELECT id, soldier_id, after_day FROM soldier_afters ORDER BY after_day, id').fetchall()
    vacation_entries = c.execute('SELECT id, soldier_id, vacation_start, vacation_end FROM soldier_vacations ORDER BY vacation_start, id').fetchall()

    if after_entries or vacation_entries:
        for after_id, soldier_id, after_day in after_entries:
            row_col1, row_col2 = st.columns([3, 0.5])
            row_col1.write(f"• {soldier_id_to_name.get(soldier_id, '---')} - אפטר {day_names[after_day]}")
            if row_col2.button("❌", key=f"del_global_after_{after_id}"):
                c.execute('DELETE FROM soldier_afters WHERE id = ?', (after_id,))
                conn.commit()
                safe_rerun()
        for vac_id, soldier_id, vacation_start, vacation_end in vacation_entries:
            start_label = day_names[vacation_start] if vacation_start is not None else "?"
            end_label = day_names[vacation_end] if vacation_end is not None else "?"
            row_col1, row_col2 = st.columns([3, 0.5])
            row_col1.write(f"• {soldier_id_to_name.get(soldier_id, '---')} - חופש {start_label} עד {end_label}")
            if row_col2.button("❌", key=f"del_global_vac_{vac_id}"):
                c.execute('DELETE FROM soldier_vacations WHERE id = ?', (vac_id,))
                conn.commit()
                safe_rerun()
    else:
        st.write("אין אפטרים או חופשות כרגע")

    with st.form(key='global_after_form', clear_on_submit=True):
        global_after_soldier = st.selectbox("חייל", ["בחר חייל..."] + [name for _, name in soldiers], index=0, key='global_after_soldier')
        global_after_day = st.selectbox("יום אפטר", ["בחר יום..."] + day_names, index=0, key='global_after_day')
        if st.form_submit_button("הוסף אפטר"):
            if global_after_soldier != "בחר חייל..." and global_after_day != "בחר יום...":
                soldier_id = soldier_name_to_id.get(global_after_soldier)
                after_day_idx = day_names.index(global_after_day)
                c.execute('INSERT INTO soldier_afters (soldier_id, after_day) VALUES (?, ?)', (soldier_id, after_day_idx))
                conn.commit()
                safe_rerun()

    with st.form(key='global_gimal_form', clear_on_submit=True):
        global_gimal_soldier = st.selectbox("חייל", ["בחר חייל..."] + [name for _, name in soldiers], index=0, key='global_gimal_soldier')
        global_gimal_start = st.selectbox("גימלים מתחילים ביום", ["בחר יום..."] + day_names, index=0, key='global_gimal_start')
        global_gimal_end = st.selectbox("גימלים מסתיימים ביום", ["בחר יום..."] + day_names, index=0, key='global_gimal_end')
        if st.form_submit_button("הוסף גימלים"):
            if global_gimal_soldier != "בחר חייל..." and global_gimal_start != "בחר יום..." and global_gimal_end != "בחר יום...":
                soldier_id = soldier_name_to_id.get(global_gimal_soldier)
                gimal_start_idx = day_names.index(global_gimal_start)
                gimal_end_idx = day_names.index(global_gimal_end)
                if gimal_end_idx < gimal_start_idx:
                    gimal_end_idx = gimal_start_idx
                c.execute('INSERT INTO soldier_gimels (soldier_id, gimal_start, gimal_end) VALUES (?, ?, ?)', (soldier_id, gimal_start_idx, gimal_end_idx))
                conn.commit()
                safe_rerun()

    with st.form(key='global_vac_form', clear_on_submit=True):
        global_vac_soldier = st.selectbox("חייל", ["בחר חייל..."] + [name for _, name in soldiers], index=0, key='global_vac_soldier')
        global_vac_start = st.selectbox("חופש מתחיל ביום", ["בחר יום..."] + day_names, index=0, key='global_vac_start')
        global_vac_end = st.selectbox("חופש מסתיים ביום", ["בחר יום..."] + day_names, index=0, key='global_vac_end')
        if st.form_submit_button("הוסף חופשה"):
            if global_vac_soldier != "בחר חייל..." and global_vac_start != "בחר יום..." and global_vac_end != "בחר יום...":
                soldier_id = soldier_name_to_id.get(global_vac_soldier)
                vac_start_idx = day_names.index(global_vac_start)
                vac_end_idx = day_names.index(global_vac_end)
                if vac_end_idx < vac_start_idx:
                    vac_end_idx = vac_start_idx
                c.execute('INSERT INTO soldier_vacations (soldier_id, vacation_start, vacation_end) VALUES (?, ?, ?)', (soldier_id, vac_start_idx, vac_end_idx))
                conn.commit()
                safe_rerun()

elif page == "ניהול ר\"צ/תורנויות/אחזקות":
    st.subheader("ניהול ר\"צ כונן, תורנויות ואחזקות")
    col1, col2, col3 = st.columns([1.2, 1.2, 1.2])
    if col1.button("אפס ר\"צ כונן"):
        c.execute('DELETE FROM weekly_rc_kinun')
        conn.commit()
        safe_rerun()
    if col2.button("אפס תורנויות"):
        c.execute('DELETE FROM weekly_duties')
        conn.commit()
        safe_rerun()
    if col3.button("אפס אחזקות"):
        c.execute('DELETE FROM weekly_maintenance')
        conn.commit()
        safe_rerun()

    if st.button("אפס אירועים"):
        c.execute('DELETE FROM weekly_events')
        conn.commit()
        safe_rerun()

    st.write("### ר\"צ כונן")
    rc_entries = c.execute('SELECT id, person_name FROM weekly_rc_kinun ORDER BY id DESC').fetchall()
    if rc_entries:
        for rc_id, person_name in rc_entries:
            rc_col1, rc_col2 = st.columns([3, 0.5])
            rc_col1.write(f"• {person_name}")
            if rc_col2.button("❌", key=f"del_rc_{rc_id}"):
                c.execute('DELETE FROM weekly_rc_kinun WHERE id = ?', (rc_id,))
                conn.commit()
                safe_rerun()
    else:
        st.write("אין ר\"צ כונן רשום")

    with st.form(key='add_rc_form_global', clear_on_submit=True):
        rc_person_name = st.text_input("שם ר\"צ כונן", key='rc_person_add_global')
        if st.form_submit_button("הוסף ר\"צ כונן"):
            if rc_person_name.strip():
                c.execute('DELETE FROM weekly_rc_kinun')
                c.execute('INSERT INTO weekly_rc_kinun (person_name) VALUES (?)', (rc_person_name.strip(),))
                conn.commit()
                safe_rerun()

    st.write("### אחזקות")
    maintenance_entries = c.execute('SELECT id, maintenance_day, person_name FROM weekly_maintenance ORDER BY maintenance_day, id').fetchall()
    if maintenance_entries:
        for maintenance_id, maintenance_day, person_name in maintenance_entries:
            duty_col1, duty_col2, duty_col4 = st.columns([3, 3, 0.5])
            duty_col1.write(f"• {day_names[maintenance_day]}")
            duty_col2.write(person_name)
            if duty_col4.button("❌", key=f"del_maintenance_{maintenance_id}"):
                c.execute('DELETE FROM weekly_maintenance WHERE id = ?', (maintenance_id,))
                conn.commit()
                safe_rerun()
    else:
        st.write("אין אחזקות כרגע")

    with st.form(key='add_maintenance_form_global', clear_on_submit=True):
        maintenance_day_option = st.selectbox("יום אחזקה", ["בחר יום..."] + day_names, index=0, key='maintenance_day_add_global')
        person_name = st.text_input("שם האחראי / חיילים", key='maintenance_person_add_global')
        if st.form_submit_button("הוסף אחזקה"):
            if maintenance_day_option != "בחר יום..." and person_name.strip():
                maintenance_day_idx = day_names.index(maintenance_day_option)
                c.execute('INSERT INTO weekly_maintenance (maintenance_day, person_name) VALUES (?, ?)', (maintenance_day_idx, person_name.strip()))
                conn.commit()
                safe_rerun()

    st.write("### תורנויות")
    duties = c.execute('SELECT id, duty_day, duty_type, person_name FROM weekly_duties ORDER BY duty_day, id').fetchall()
    if duties:
        for duty_id, duty_day, duty_type, person_name in duties:
            duty_col1, duty_col2, duty_col3, duty_col4 = st.columns([2, 2, 2, 0.5])
            duty_col1.write(f"• {day_names[duty_day]}")
            duty_col2.write(duty_type)
            duty_col3.write(person_name)
            if duty_col4.button("❌", key=f"del_duty_{duty_id}"):
                c.execute('DELETE FROM weekly_duties WHERE id = ?', (duty_id,))
                conn.commit()
                safe_rerun()
    else:
        st.write("אין תורנויות כרגע")

    st.write("### אירועים")
    event_entries = c.execute('SELECT id, event_day, event_text FROM weekly_events ORDER BY event_day, id').fetchall()
    if event_entries:
        for event_id, event_day, event_text in event_entries:
            event_col1, event_col2 = st.columns([3, 0.5])
            event_col1.write(f"• {day_names[event_day]} - {event_text}")
            if event_col2.button("❌", key=f"del_event_{event_id}"):
                c.execute('DELETE FROM weekly_events WHERE id = ?', (event_id,))
                conn.commit()
                safe_rerun()
    else:
        st.write("אין אירועים כרגע")

    with st.form(key='add_event_form_global', clear_on_submit=True):
        event_day_option = st.selectbox("יום אירוע", ["בחר יום..."] + day_names, index=0, key='event_day_add_global')
        event_text = st.text_input("טקסט אירוע חופשי", key='event_text_add_global')
        if st.form_submit_button("הוסף אירוע"):
            if event_day_option != "בחר יום..." and event_text.strip():
                event_day_idx = day_names.index(event_day_option)
                c.execute('INSERT INTO weekly_events (event_day, event_text) VALUES (?, ?)', (event_day_idx, event_text.strip()))
                conn.commit()
                safe_rerun()

    with st.form(key='add_duty_form_global', clear_on_submit=True):
        duty_day_option = st.selectbox("יום תורנות", ["בחר יום..."] + day_names, index=0, key='duty_day_add_global')
        duty_type_option = st.text_input("סוג תורנות", key='duty_type_add_global')
        person_name = st.text_input("שם האחראי / חייל", key='duty_person_add_global')
        if st.form_submit_button("הוסף תורנות"):
            if duty_day_option != "בחר יום..." and duty_type_option.strip() and person_name.strip():
                duty_day_idx = day_names.index(duty_day_option)
                c.execute('INSERT INTO weekly_duties (duty_day, duty_type, person_name) VALUES (?, ?, ?)', (duty_day_idx, duty_type_option.strip(), person_name.strip()))
                conn.commit()
                safe_rerun()
