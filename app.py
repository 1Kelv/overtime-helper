# app.py
import streamlit as st
import pandas as pd
from datetime import date

# ======================================================
# Config
# ======================================================

st.set_page_config(
    page_title="Overtime Helper (beta)",
    layout="wide",
)

# Default contracted weekly hours – can be overridden in UI
CONTRACTED_WEEKLY_DEFAULT = 45.0
CONTRACTED_WEEKLY_BY_EMAIL: dict[str, float] = {}

# Team-specific standard shift lengths (incl. 1h unpaid lunch if >= shift length)
SHIFT_HOURS_BY_TEAM = {
    "Fraud Operations": 9.0,
    "Customer Support": 9.0,
    "Core Ops / Payment Ops": 12.0,  # ✅ special rule from Jerry
    "Compliance Ops": 9.0,
    "Treasury Ops": 9.0,
}

KENYA_TZ = "Africa/Nairobi"

# Kenyan gazetted public holidays for 2025
KENYA_BANK_HOLIDAYS_2025 = {
    date(2025, 1, 1),   # New Year's Day
    date(2025, 3, 31),  # Idd-ul-Fitr (approx – varies with lunar calendar)
    date(2025, 4, 18),  # Good Friday
    date(2025, 4, 21),  # Easter Monday
    date(2025, 5, 1),   # Labour Day
    date(2025, 6, 1),   # Madaraka Day
    date(2025, 6, 7),   # Idd-ul-Azha (approx – varies)
    date(2025, 10, 10), # Huduma / Mazingira Day
    date(2025, 10, 20), # Mashujaa Day
    date(2025, 12, 12), # Jamhuri Day
    date(2025, 12, 25), # Christmas Day
    date(2025, 12, 26), # Boxing Day
}

# ======================================================
# Core helpers
# ======================================================

def prepare_shifts(
    df: pd.DataFrame,
    enable_kenyan_bh: bool = True,
    shift_hours: float = 9.0,
) -> pd.DataFrame:
    """Normalise raw Dialpad CSV and flag bank holidays."""
    df = df.copy()

    # Dates and basic fields
    df["shift_date"] = pd.to_datetime(df["shift_date"])
    df["day_name"] = df["shift_date"].dt.day_name()

    if "total_scheduled" in df.columns:
        df["hours_worked"] = pd.to_numeric(
            df["total_scheduled"], errors="coerce"
        ).fillna(0.0)
    else:
        df["hours_worked"] = 0.0

    df["scheduled_hours"] = df["hours_worked"]

    # Paid hours: 1 hour unpaid lunch if they work at least a full shift
    def _paid(h: float) -> float:
        return h - 1 if h >= shift_hours else h

    df["paid_hours"] = df["scheduled_hours"].apply(_paid)

    # Names
    if "first_name" not in df.columns:
        df["first_name"] = ""
    if "last_name" not in df.columns:
        df["last_name"] = ""

    df["full_name"] = (
        df["first_name"].astype(str).str.strip()
        + " "
        + df["last_name"].astype(str).str.strip()
    ).str.strip()

    # Week start (Monday)
    df["week_start"] = df["shift_date"] - pd.to_timedelta(
        df["shift_date"].dt.weekday, unit="D"
    )

    # Shift name
    if "subtype" in df.columns:
        df["shift_name"] = df["subtype"].astype(str)
    else:
        df["shift_name"] = ""

    # Kenyan timezone flag
    if "surfer_timezone" in df.columns:
        df["is_kenya_employee"] = df["surfer_timezone"] == KENYA_TZ
    else:
        df["is_kenya_employee"] = False

    # Bank-holiday detection (Kenya only for now)
    if enable_kenyan_bh:
        def _is_bank_holiday(row) -> bool:
            if not row["is_kenya_employee"]:
                return False
            return row["shift_date"].date() in KENYA_BANK_HOLIDAYS_2025

        df["is_bank_holiday"] = df.apply(_is_bank_holiday, axis=1)
    else:
        df["is_bank_holiday"] = False

    return df


def flag_overtime_days(
    df: pd.DataFrame,
    contracted_days_per_week: int = 5,
) -> pd.DataFrame:
    """
    Mark OT days per person per week.

    Rule (v1):
    - Sort days in the week.
    - First N contracted days are standard.
    - Any extra working days in that week are counted as overtime days.
    """
    df = df.sort_values(["email", "week_start", "shift_date"])
    df["is_ot_day"] = False

    def _mark_group(group: pd.DataFrame) -> pd.DataFrame:
        unique_dates = list(group["shift_date"].dt.date.unique())
        if len(unique_dates) <= contracted_days_per_week:
            return group
        ot_dates = set(unique_dates[contracted_days_per_week:])
        group["is_ot_day"] = group["shift_date"].dt.date.isin(ot_dates)
        return group

    return df.groupby(
        ["email", "week_start"], group_keys=False
    ).apply(_mark_group)


def add_shift_duration_and_flags(df: pd.DataFrame, shift_hours: float) -> pd.DataFrame:
    """Convert hours into 'days' based on team-specific shift length."""
    df = df.copy()
    df["shift_days"] = df["scheduled_hours"] / shift_hours
    df["ot_hours"] = df["scheduled_hours"].where(df["is_ot_day"], 0.0)
    df["bh_hours"] = df["scheduled_hours"].where(df["is_bank_holiday"], 0.0)
    return df


def build_granular_table(df: pd.DataFrame, team_name: str) -> pd.DataFrame:
    """One row per OT / bank holiday shift."""
    granular = df[df["is_ot_day"] | df["is_bank_holiday"]].copy()
    if granular.empty:
        return granular

    granular["team"] = team_name
    granular["date"] = granular["shift_date"].dt.date

    def _day_type(row):
        if row["is_bank_holiday"]:
            return "Bank holiday"
        if row["is_ot_day"]:
            return "Overtime"
        return "Standard"

    granular["day_type"] = granular.apply(_day_type, axis=1)

    cols = [
        "team",
        "full_name",
        "email",
        "date",
        "day_type",
        "shift_name",
        "scheduled_hours",
        "shift_days",
    ]
    granular = granular[cols].sort_values(["team", "full_name", "date"])
    return granular


def build_summary_table(df: pd.DataFrame, team_name: str) -> pd.DataFrame:
    """Summary by person (days + hours of OT / BH)."""
    df = df.copy()
    df["team"] = team_name

    summary = (
        df.groupby(["team", "full_name", "email"], as_index=False)
        .agg(
            days_OT=("is_ot_day", "sum"),
            days_BH=("is_bank_holiday", "sum"),
            hours_OT=("ot_hours", "sum"),
            hours_BH=("bh_hours", "sum"),
        )
        .sort_values(["team", "full_name"])
    )
    return summary


def build_pivot_from_granular(granular: pd.DataFrame) -> pd.DataFrame:
    """
    Excel-style pivot derived from the granular table.

    This shows, per person:
      - OT days / hours
      - Bank holiday days / hours

    It is basically another way to see how the summary table is created.
    """
    if granular.empty:
        return granular

    pivot = granular.pivot_table(
        index=["team", "full_name", "email"],
        columns="day_type",
        values=["scheduled_hours", "shift_days"],
        aggfunc="sum",
        fill_value=0,
    )

    # Flatten MultiIndex columns
    pivot.columns = [
        f"{val}_{col}".replace(" ", "_")
        for val, col in pivot.columns.to_flat_index()
    ]
    pivot = pivot.reset_index()

    rename_map = {
        "shift_days_Overtime": "days_OT",
        "shift_days_Bank_holiday": "days_BH",
        "scheduled_hours_Overtime": "hours_OT",
        "scheduled_hours_Bank_holiday": "hours_BH",
    }
    for old, new in rename_map.items():
        if old in pivot.columns:
            pivot[new] = pivot[old]

    cols = ["team", "full_name", "email"]
    for col in ["days_OT", "days_BH", "hours_OT", "hours_BH"]:
        if col in pivot.columns:
            cols.append(col)

    return pivot[cols]


def build_teams_with_ot(summary_table: pd.DataFrame) -> pd.DataFrame:
    """
    Roll-up per team, only including teams that actually have OT or BH.

    This will be more interesting once an API worker processes multiple
    teams in one go, but the logic is ready now.
    """
    if summary_table.empty:
        return summary_table

    teams = (
        summary_table.groupby("team", as_index=False)
        .agg(
            total_ot_hours=("hours_OT", "sum"),
            total_bh_hours=("hours_BH", "sum"),
            people_with_ot=("hours_OT", lambda s: (s > 0).sum()),
            people_with_bh=("hours_BH", lambda s: (s > 0).sum()),
        )
    )

    teams = teams[
        (teams["total_ot_hours"] > 0) | (teams["total_bh_hours"] > 0)
    ]
    return teams


def summarise_weekly_hours(df: pd.DataFrame, team_name: str) -> pd.DataFrame:
    """Optional weekly view used in the debug tab."""
    if df.empty:
        return df

    tmp = df.copy()
    tmp["team"] = team_name

    weekly = (
        tmp.groupby(
            ["team", "full_name", "email", "week_start"], as_index=False
        )
        .agg(
            total_scheduled=("scheduled_hours", "sum"),
            total_ot=("ot_hours", "sum"),
            total_bh=("bh_hours", "sum"),
        )
        .sort_values(["team", "full_name", "week_start"])
    )
    return weekly


def summarise_monthly_hours(df: pd.DataFrame, team_name: str) -> pd.DataFrame:
    """Optional monthly/period view used in the debug tab."""
    if df.empty:
        return df

    tmp = df.copy()
    tmp["team"] = team_name
    tmp["month"] = tmp["shift_date"].dt.to_period("M").dt.to_timestamp()

    monthly = (
        tmp.groupby(
            ["team", "full_name", "email", "month"], as_index=False
        )
        .agg(
            total_scheduled=("scheduled_hours", "sum"),
            total_ot=("ot_hours", "sum"),
            total_bh=("bh_hours", "sum"),
        )
        .sort_values(["team", "full_name", "month"])
    )
    return monthly


# ======================================================
# UI
# ======================================================

# Floating pill badge
st.markdown(
    """
    <style>
    .pill {
        display:inline-block;
        padding:0.35rem 1.1rem;
        border-radius:999px;
        background:linear-gradient(90deg, #2ecc71, #3498db);
        color:white;
        font-weight:600;
        font-size:0.9rem;
        letter-spacing:0.03em;
        animation: float 3s ease-in-out infinite;
    }
    @keyframes float {
        0% { transform: translateY(0px); }
        50% { transform: translateY(-2px); }
        100% { transform: translateY(0px); }
    }
    </style>
    <span class="pill">Internal · Overtime</span>
    """,
    unsafe_allow_html=True,
)

st.title("Overtime Helper (beta)")
st.caption(
    "Turn Dialpad WFM timesheets into consistent overtime and bank-holiday views "
    "for the People / Payroll team."
)

# --- Controls row ---
col_team, col_mode = st.columns([3, 2])

with col_team:
    team_options = [
        "Fraud Operations",
        "Customer Support",
        "Core Ops / Payment Ops",
        "Compliance Ops",
        "Treasury Ops",
    ]
    team_name = st.selectbox("Select your team", team_options, index=0)

with col_mode:
    mode = st.radio(
        "Mode",
        ["Manual CSV (current)", "Dialpad API (future)"],
        index=0,
        help=(
            "Manual CSV is live today. Dialpad API mode is on the roadmap for an "
            "automated worker + Slackbot flow."
        ),
    )

if mode == "Dialpad API (future)":
    st.info(
        "API mode is part of the longer-term roadmap (Dialpad API worker + Slackbot). "
        "For now, please use **Manual CSV** and upload a Dialpad export."
    )

# Team-specific shift hours
shift_hours = SHIFT_HOURS_BY_TEAM.get(team_name, 9.0)
st.caption(
    f"Using a **{shift_hours:.0f}-hour** standard shift for **{team_name}** "
    f"(1 hour unpaid lunch if they work at least a full shift)."
)

# Contracted hours / days (still editable if needed)
col_a, col_b = st.columns(2)
with col_a:
    contracted_weekly_hours = st.number_input(
        "Contracted weekly hours",
        min_value=1.0,
        max_value=80.0,
        value=CONTRACTED_WEEKLY_DEFAULT,
        step=1.0,
        help="Used for context only in this version.",
    )
with col_b:
    contracted_days_per_week = st.number_input(
        "Contracted days per week",
        min_value=1,
        max_value=7,
        value=5,
        step=1,
        help="Used to decide which days in a week count as overtime days.",
    )

enable_kenyan_bh = st.checkbox(
    "Apply Kenyan bank-holiday rules (Africa/Nairobi)",
    value=True,
    help=(
        "If ticked, Kenyan shifts on gazetted holidays pay at bank-holiday rate "
        "and are flagged separately from normal overtime."
    ),
)

uploaded_file = st.file_uploader(
    "Upload a Dialpad timesheet CSV", type=["csv"]
)

st.markdown("---")

if uploaded_file is None:
    st.info("Upload a CSV exported from Dialpad WFM to see results.")
    st.stop()

# ======================================================
# Processing
# ======================================================

raw_df = pd.read_csv(uploaded_file)

df = prepare_shifts(
    raw_df,
    enable_kenyan_bh=enable_kenyan_bh,
    shift_hours=shift_hours,
)
df = flag_overtime_days(
    df,
    contracted_days_per_week=int(contracted_days_per_week),
)
df = add_shift_duration_and_flags(df, shift_hours=shift_hours)

summary_table = build_summary_table(df, team_name)
granular_table = build_granular_table(df, team_name)
pivot_table = build_pivot_from_granular(granular_table)
weekly_summary = summarise_weekly_hours(df, team_name)
monthly_summary = summarise_monthly_hours(df, team_name)
teams_with_ot = build_teams_with_ot(summary_table)

# ======================================================
# Overview
# ======================================================

st.subheader("Overview")

total_people = summary_table.shape[0]
total_ot_hours = float(summary_table["hours_OT"].sum())
total_bh_hours = float(summary_table["hours_BH"].sum())

m1, m2, m3 = st.columns(3)
m1.metric("People in file", total_people)
m2.metric("Total OT hours", f"{total_ot_hours:.2f}")
m3.metric("Bank-holiday hours", f"{total_bh_hours:.2f}")

if teams_with_ot.empty:
    st.info(
        "No overtime or bank-holiday days detected in this file for the "
        "current team."
    )
else:
    st.caption("Teams with overtime / bank-holiday in this dataset.")
    st.dataframe(
        teams_with_ot, hide_index=True, use_container_width=True
    )

# ======================================================
# Tabs – summary, granular, pivot, debug
# ======================================================

tab1, tab2, tab3, tab4 = st.tabs(
    [
        "Summary by person",
        "Granular OT / BH days",
        "Pivot (from granular)",
        "Weekly / debug",
    ]
)

with tab1:
    st.subheader("Summary by person")
    st.caption(
        "Per-person totals for overtime and bank-holiday days and hours."
    )
    st.dataframe(
        summary_table,
        hide_index=True,
        use_container_width=True,
    )

with tab2:
    st.subheader("Granular overtime / bank-holiday days")
    st.caption(
        "One row per day where someone worked overtime or on a bank holiday."
    )
    if granular_table.empty:
        st.info("No overtime or bank-holiday days in this dataset.")
    else:
        st.dataframe(
            granular_table,
            hide_index=True,
            use_container_width=True,
        )

with tab3:
    st.subheader("Pivot view (granular → summary)")
    st.caption(
        "Excel-style pivot generated directly from the granular table. "
        "This is another way to see how the summary is built."
    )
    if pivot_table.empty:
        st.info("No data to pivot – no overtime or bank-holiday days.")
    else:
        st.dataframe(
            pivot_table,
            hide_index=True,
            use_container_width=True,
        )

with tab4:
    st.subheader("Weekly / debug views")
    st.caption(
        "Optional weekly and monthly breakdowns – useful if something in the "
        "main summary looks off and you want to dig deeper."
    )

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Weekly by person**")
        if weekly_summary.empty:
            st.info("No weekly data.")
        else:
            st.dataframe(
                weekly_summary,
                hide_index=True,
                use_container_width=True,
            )
    with c2:
        st.markdown("**Monthly by person**")
        if monthly_summary.empty:
            st.info("No monthly data.")
        else:
            st.dataframe(
                monthly_summary,
                hide_index=True,
                use_container_width=True,
            )

# ======================================================
# Downloads
# ======================================================

st.markdown("---")
st.subheader("Downloads for People / Payroll")

col1, col2, col3, col4, col5 = st.columns(5)

summary_csv = summary_table.to_csv(index=False).encode("utf-8")
granular_csv = granular_table.to_csv(index=False).encode("utf-8")
weekly_csv = weekly_summary.to_csv(index=False).encode("utf-8")
monthly_csv = monthly_summary.to_csv(index=False).encode("utf-8")
teams_csv = (
    teams_with_ot.to_csv(index=False).encode("utf-8")
    if not teams_with_ot.empty
    else None
)

with col1:
    st.download_button(
        "Summary by person (CSV)",
        data=summary_csv,
        file_name="ot_summary_by_person.csv",
        mime="text/csv",
    )

with col2:
    st.download_button(
        "Granular OT / BH (CSV)",
        data=granular_csv,
        file_name="ot_granular_days.csv",
        mime="text/csv",
    )

with col3:
    st.download_button(
        "Weekly by person (CSV)",
        data=weekly_csv,
        file_name="ot_weekly_summary.csv",
        mime="text/csv",
    )

with col4:
    st.download_button(
        "Monthly by person (CSV)",
        data=monthly_csv,
        file_name="ot_monthly_summary.csv",
        mime="text/csv",
    )

with col5:
    if teams_csv is not None:
        st.download_button(
            "Teams with OT / BH (CSV)",
            data=teams_csv,
            file_name="ot_teams_with_overtime.csv",
            mime="text/csv",
            help=(
                "Roll-up per team, only including teams that actually have "
                "overtime or bank-holiday hours. This will power the "
                "all-teams API worker later."
            ),
        )
    else:
        st.write("No OT / BH teams in this file.")
    