import pandas as pd
from pathlib import Path

# ====== CONFIG – tweak these for your setup ======

# Your exported Dialpad timesheet file
INPUT_FILE = "TestTimeSheet.csv"

# Output files this script will create
OUTPUT_WEEKLY = "ot_weekly_summary.csv"
OUTPUT_MONTHLY = "ot_monthly_summary.csv"

# Default contracted hours per week (placeholder!)
# Ask People/HR what the correct number is for Fraud Ops.
CONTRACTED_WEEKLY_DEFAULT = 45  # e.g. 45 hours per week

# If some people have different contracts, set them here by email.
# Example:
# CONTRACTED_WEEKLY_BY_EMAIL = {
#     "kelvin.olasupo@nala.money": 40,
# }
CONTRACTED_WEEKLY_BY_EMAIL = {}

# =================================================


def load_shifts(path: str) -> pd.DataFrame:
    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(f"Could not find {csv_path.resolve()}")

    df = pd.read_csv(csv_path)

    # Parse date
    df["shift_date"] = pd.to_datetime(df["shift_date"])

    # Use total_scheduled as hours worked in that shift
    df["hours_worked"] = pd.to_numeric(df["total_scheduled"], errors="coerce").fillna(0)

    # Full name for nicer summaries
    df["full_name"] = df["first_name"].astype(str) + " " + df["last_name"].astype(str)

    # Week start (Monday) for grouping
    df["week_start"] = df["shift_date"] - pd.to_timedelta(
        df["shift_date"].dt.weekday, unit="D"
    )

    return df


def get_contracted_hours(email: str) -> float:
    """Look up contracted hours for this person, fall back to default."""
    return CONTRACTED_WEEKLY_BY_EMAIL.get(email, CONTRACTED_WEEKLY_DEFAULT)


def summarise_weekly(df: pd.DataFrame) -> pd.DataFrame:
    """
    Group by person + week and calculate:
    - total hours
    - contracted hours
    - overtime hours
    """
    weekly = (
        df.groupby(["full_name", "email", "week_start"], as_index=False)["hours_worked"]
        .sum()
        .rename(columns={"hours_worked": "total_hours"})
    )

    weekly["contracted_hours"] = weekly["email"].apply(get_contracted_hours)

    # Overtime = anything above contracted hours (never negative)
    weekly["overtime_hours"] = (
        weekly["total_hours"] - weekly["contracted_hours"]
    ).clip(lower=0)

    # Simple flag for filters
    weekly["has_overtime"] = weekly["overtime_hours"] > 0

    return weekly


def summarise_monthly(weekly: pd.DataFrame) -> pd.DataFrame:
    """
    Roll weekly data up to a monthly/period view per person.
    """
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
    """Return a friendly label for the period in the CSV."""
    start = df["shift_date"].min().date()
    end = df["shift_date"].max().date()
    if start == end:
        return f"on {start}"
    return f"from {start} to {end}"


def main():
    print("Loading shifts...")
    df = load_shifts(INPUT_FILE)

    if df.empty:
        print("⚠️ No shift rows found in the CSV.")
        return

    period_label = describe_period(df)

    print("Building weekly OT summary...")
    weekly = summarise_weekly(df)
    weekly.to_csv(OUTPUT_WEEKLY, index=False)

    print("Building monthly OT summary...")
    monthly = summarise_monthly(weekly)
    monthly.to_csv(OUTPUT_MONTHLY, index=False)

    total_ot = monthly["total_overtime"].sum()

    print("\n✅ Done.")
    print(f"Weekly summary saved to:   {OUTPUT_WEEKLY}")
    print(f"Monthly summary saved to:  {OUTPUT_MONTHLY}\n")

    if total_ot == 0:
        print(f"ℹ️ No Fraud Ops overtime detected for the selected period {period_label}.")
    else:
        print(
            f"🔍 Total overtime for Fraud Ops {period_label}: "
            f"{total_ot:.2f} hours\n"
        )
        ot_people = monthly[monthly["total_overtime"] > 0][
            ["full_name", "email", "total_overtime"]
        ]
        print("People with overtime:")
        print(ot_people.to_string(index=False))


if __name__ == "__main__":
    main()
