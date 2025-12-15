import streamlit as st
import pandas as pd
import html
import streamlit.components.v1 as components

# ====== OPTIONAL CONFIG – tweak per team if needed ======

# Per-email contracted hours overrides (optional).
# Leaving empty for now, will fill once People confirm exact contracts.
CONTRACTED_WEEKLY_BY_EMAIL = {

}

# ========================================================


def get_contracted_hours(email: str, default_weekly: float) -> float:
    """Look up contracted hours for this person, fall back to default."""
    return CONTRACTED_WEEKLY_BY_EMAIL.get(email, default_weekly)


def prepare_shifts(df: pd.DataFrame) -> pd.DataFrame:
    """Clean and enrich the raw Dialpad CSV."""
    # Parse date
    df["shift_date"] = pd.to_datetime(df["shift_date"])

    # Hours worked from total_scheduled
    df["hours_worked"] = pd.to_numeric(
        df["total_scheduled"], errors="coerce"
    ).fillna(0)

    # Full name
    df["full_name"] = df["first_name"].astype(str) + " " + df["last_name"].astype(str)

    # Week start (Monday) for grouping
    df["week_start"] = df["shift_date"] - pd.to_timedelta(
        df["shift_date"].dt.weekday, unit="D"
    )

    return df


def summarise_weekly(df: pd.DataFrame, default_weekly: float) -> pd.DataFrame:
    """Group by person + week and calculate OT."""
    weekly = (
        df.groupby(["full_name", "email", "week_start"], as_index=False)["hours_worked"]
        .sum()
        .rename(columns={"hours_worked": "total_hours"})
    )

    weekly["contracted_hours"] = weekly["email"].apply(
        lambda e: get_contracted_hours(e, default_weekly)
    )

    weekly["overtime_hours"] = (
        weekly["total_hours"] - weekly["contracted_hours"]
    ).clip(lower=0)

    weekly["has_overtime"] = weekly["overtime_hours"] > 0

    return weekly


def summarise_monthly(weekly: pd.DataFrame) -> pd.DataFrame:
    """Roll weekly data up to a period view per person."""
    monthly = (
        weekly.groupby(["full_name", "email"], as_index=False)
        .agg(
            total_hours=("total_hours", "sum"),
            total_contracted=("contracted_hours", "sum"),
            total_overtime=("overtime_hours", "sum"),
        )
        .sort_values("full_name")
    )
    return monthly


def describe_period(df: pd.DataFrame) -> str:
    start = df["shift_date"].min().date()
    end = df["shift_date"].max().date()
    if start == end:
        return f"on {start}"
    return f"from {start} to {end}"


# ================== STREAMLIT APP =======================

st.set_page_config(page_title="Overtime Helper (beta)", layout="wide")

# Bigger styling for the badge + title
st.set_page_config(page_title="Overtime Helper (beta)", layout="wide")

st.markdown(
    """
    <style>
    .nala-pill {
        background: linear-gradient(90deg,#28b17d,#0c8bd9);
        padding: 0.55rem 1.4rem;
        border-radius: 999px;
        color: white;
        font-size: 1.0rem;
        font-weight: 600;
        display: inline-block;
        margin-bottom: 0.9rem;
        animation: float 3s ease-in-out infinite;
    }
    
    @keyframes float {
        0%, 100% {
            transform: translateY(0px);
        }
        50% {
            transform: translateY(-10px);
        }
    }
    
    .nala-title {
        font-size: 2.2rem;
        font-weight: 700;
        margin-bottom: 0.1rem;
    }
    
    .nala-tagline {
        font-size: 1.0rem;
        color: #6c757d;
        margin-bottom: 1.2rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

header_col, team_col = st.columns([3, 2])

with header_col:
    st.markdown('<div class="nala-pill">Internal · Overtime</div>', unsafe_allow_html=True)
    st.markdown('<div class="nala-title">Overtime Helper (beta)</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="nala-tagline">'
        'Turn Dialpad timesheets into a clean overtime summary for the People / Payroll team in seconds.'
        '</div>',
        unsafe_allow_html=True,
    )

with team_col:
    team_options = [
        "Fraud Operations",
        "Customer Support",
        "Core Ops / Payment Ops",
        "Compliance Ops",
    ]
    team_name = st.selectbox(
        "Select your team",
        options=team_options,
        index=0,
        help="Used in summaries and suggested messages.",
    )

uploaded_file = st.file_uploader("Upload Dialpad timesheet CSV", type=["csv"])

default_weekly = st.number_input(
    f"Contracted weekly hours (default for {team_name})",
    min_value=1.0,
    max_value=80.0,
    value=45.0,
    step=0.5,
    help="Use the standard contracted hours for this team. Can hard-code exceptions in the config above.",
)

if uploaded_file is not None:
    try:
        raw_df = pd.read_csv(uploaded_file)
    except Exception as e:
        st.error(f"Could not read CSV: {e}")
    else:
        # Quick sanity-check that expected columns exist
        required_cols = {
            "shift_date",
            "first_name",
            "last_name",
            "email",
            "total_scheduled",
        }
        missing = required_cols - set(raw_df.columns)
        if missing:
            st.error(
                f"CSV is missing required columns: {', '.join(missing)}. "
                "Please export the standard Dialpad timesheet."
            )
        else:
            df = prepare_shifts(raw_df)
            period_label = describe_period(df)

            weekly = summarise_weekly(df, default_weekly)
            monthly = summarise_monthly(weekly)

            total_ot = float(monthly["total_overtime"].sum())

            # Top-level metrics row
            col1, col2, col3 = st.columns(3)
            col1.metric("Total shifts", len(df))
            col2.metric("Agent-weeks", len(weekly))
            col3.metric("Total overtime hours", f"{total_ot:.2f}")

            st.subheader(f"Period covered: {period_label}")

            # Build suggested message text for People
            if total_ot == 0:
                st.success(
                    f"No overtime detected for {team_name} for the selected period {period_label}."
                )

                suggested_message = (
                    f"Hi People team,\n\n"
                    f"For **{team_name}**, there is **no overtime** to report for the period {period_label}, "
                    f"based on the Dialpad timesheet export.\n\n"
                    f"Many thanks,\n"
                    f"(Insert you name)\n"
                )
            else:
                st.warning(
                    f"Total overtime for {team_name} {period_label}: {total_ot:.2f} hours."
                )

                ot_people = monthly[monthly["total_overtime"] > 0][
                    ["full_name", "email", "total_overtime"]
                ]

                st.markdown(f"**People with overtime in {team_name} for this period:**")
                st.dataframe(ot_people, hide_index=True, use_container_width=True)

                suggested_message = (
                    f"Hi People team,\n\n"
                    f"Please find attached the **{team_name}** overtime summary for the period {period_label}.\n\n"
                    f"Total overtime across the team: {total_ot:.2f} hours.\n\n"
                    f"The attached CSV includes overtime hours by colleague and week, "
                    f"calculated from the Dialpad timesheet export.\n\n"
                    f"Many thanks,\n"
                    f"(Insert you name)\n"
                )

            st.markdown("---")
            st.markdown("### Suggested message for People / Payroll, can be sent via Slack or email")
            st.write("Edit the text if needed, then click **Copy to clipboard**.")

            # HTML textarea + copy button so edits are included in the copy
            escaped_msg = html.escape(suggested_message)

            components.html(
                f"""
                <div>
                    <textarea id="ot-helper-message"
                        rows="9"
                        style="
                            width: 100%;
                            border-radius: 0.5rem;
                            padding: 0.75rem;
                            font-size: 0.95rem;
                            font-family: -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
                            background-color: #1e1e20;
                            color: #f5f5f5;
                            border: 1px solid #444;
                            box-sizing: border-box;
                        ">{escaped_msg}</textarea>
                    <button
                        style="
                            margin-top: 0.5rem;
                            padding: 0.4rem 1.0rem;
                            border-radius: 999px;
                            border: none;
                            background: linear-gradient(90deg,#28b17b,#0c8bd9);
                            color: white;
                            font-weight: 600;
                            cursor: pointer;
                        "
                        onclick="
                            const text = document.getElementById('ot-helper-message').value;
                            navigator.clipboard.writeText(text).then(function() {{
                                const status = document.getElementById('ot-helper-copy-status');
                                if (status) status.innerText = 'Copied!';
                            }});
                        ">
                        Copy to clipboard
                    </button>
                    <span id="ot-helper-copy-status"
                          style="margin-left:0.6rem; font-size:0.85rem; color:#9fe6bf;">
                    </span>
                </div>
                """,
                height=260,
            )

            # Show weekly + monthly tables in tabs
            st.markdown("---")
            tab1, tab2 = st.tabs(["Weekly summary", "Period summary"])

            with tab1:
                st.dataframe(weekly, hide_index=True, use_container_width=True)

            with tab2:
                st.dataframe(monthly, hide_index=True, use_container_width=True)

            # Download buttons
            weekly_csv = weekly.to_csv(index=False).encode("utf-8")
            monthly_csv = monthly.to_csv(index=False).encode("utf-8")

            st.markdown("---")
            st.markdown("### Downloads")

            st.download_button(
                "Download weekly OT summary (CSV)",
                weekly_csv,
                file_name="ot_weekly_summary.csv",
                mime="text/csv",
            )

            st.download_button(
                "Download period OT summary (CSV)",
                monthly_csv,
                file_name="ot_monthly_summary.csv",
                mime="text/csv",
            )
else:
    st.info("Upload a Dialpad timesheet CSV to get started.")
import pandas as pd
from pathlib import Path