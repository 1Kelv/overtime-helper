# Overtime Helper (beta)

> Small internal tool to turn Dialpad WFM timesheet exports into clean overtime summaries for People / Payroll.

---

## Background / Story

Overtime Helper started as a practical side project to remove manual overtime admin for an operations team in a fintech company.

Team leads were:

- Updating schedules and overtime in **Dialpad WFM**,
- Exporting CSVs every month,
- Then manually building overtime sheets for the People / Payroll team.

The idea behind Overtime Helper was simple:

> “If the data already lives in Dialpad, we should be able to upload one CSV and get a clean overtime summary out – ready for People – without rebuilding it in spreadsheets every time.”

What began as a quick Python script evolved into a small Streamlit app that any manager can use locally: upload a CSV, select their team, and copy a ready-made message for People in seconds.

---

## Overview

Overtime Helper is a lightweight Python + Streamlit app that:

- Takes a **Dialpad timesheet CSV** as input
- Calculates **weekly hours and overtime** per colleague
- Rolls this up into a **period summary** (e.g. a month)
- Generates:
  - Downloadable **weekly** and **period** overtime CSVs
  - A ready-to-edit **Slack/email message** for the People / Payroll team

Originally built for a Fraud Operations team, but the app supports multiple teams (Fraud Ops, Customer Support, Core Ops / Payment Ops, Compliance Ops) via a simple dropdown.

The goal is to remove manual overtime spreadsheets for team leads while keeping Dialpad as the single source of truth.

---

## Features

- 📤 **Upload** – drag and drop a Dialpad WFM timesheet CSV
- 👥 **Team selection** – choose your team from a dropdown
  - Fraud Operations
  - Customer Support
  - Core Ops / Payment Ops
  - Compliance Ops
- ⏱️ **Overtime calculation**
  - Groups data by `full_name + email + week_start`
  - Uses a configurable **contracted weekly hours** value
  - Flags hours above contract as **overtime**
- 📊 **Summaries**
  - **Weekly summary** per colleague per week
  - **Period summary** per colleague across the uploaded date range
- 📨 **Suggested message for People / Payroll**
  - Auto-generated text that states:
    - the team
    - the date range
    - total overtime hours (or “no overtime”)
  - Editable in the UI
  - One-click **“Copy to clipboard”** button
- 📁 **Downloads**
  - `ot_weekly_summary.csv`
  - `ot_monthly_summary.csv` (period summary)

---

## 🧰 Tech stack

| Layer         | Technology                               | What it does                                                             |
| ------------- | ---------------------------------------- | ------------------------------------------------------------------------ |
| Language      | **Python 3.9**                           | Core logic, data processing, and Streamlit app                           |
| Web framework | **Streamlit**                            | Renders the UI, handles file upload, inputs, layout, and downloads       |
| Data layer    | **pandas**                               | Parses the Dialpad CSV, groups by user/week, and calculates overtime     |
| Styling       | **HTML / CSS (inline in Streamlit)**     | Pill-style header badge, layout tweaks, dark styling                     |
| UX helpers    | **Vanilla JS (in Streamlit components)** | Handles the “Copy to clipboard” behaviour for the People/Payroll message |

> The app currently runs **locally** in a Python virtual environment.  
> No external APIs are called – everything stays on your machine.

---

## Project structure

```text
ot-helper/
├── app.py                 # Streamlit UI
├── ot_helper.py           # Core overtime calculation logic (CLI-style)
├── requirements.txt
├── .gitignore
├── docs/
│   ├── overtime-helper-main.png
│   └── overtime-helper-summary.png
└── example_timesheet.csv  # (optional) anonymised sample Dialpad export
```

Getting started
Prerequisites

Python 3.9+

pip installed

1. Clone the repo
   git clone https://github.com/<your-username>/overtime-helper.git
   cd overtime-helper

2. Create and activate a virtual environment (recommended)
   python3 -m venv venv
   source venv/bin/activate # macOS / Linux

# venv\Scripts\activate # Windows (PowerShell or CMD)

3. Install dependencies
   pip install -r requirements.txt

4. Run the app
   streamlit run app.py
   Streamlit will open the app in your browser (usually at http://localhost:8501).

## 🚀 How to use

Once the app is running (`streamlit run app.py`), the flow is:

1. 🧩 **Select your team**

   - Use the **“Select your team”** dropdown at the top-right.
   - Options: `Fraud Operations`, `Customer Support`, `Core Ops / Payment Ops`, `Compliance Ops`.

2. ⏱️ **Set contracted weekly hours**

   - In **“Contracted weekly hours (default for <team>)”**, enter the standard weekly hours  
     for that team (for example **45**).
   - You can add per-person exceptions later in code if needed.

3. 📤 **Export the timesheet from Dialpad**

   - In Dialpad WFM, export the **standard timesheet CSV** for the period you care about  
     (e.g. the month you want to pay overtime for).

4. 📥 **Upload the CSV into Overtime Helper**

   - Drag and drop the CSV into the **“Upload Dialpad timesheet CSV”** area, or click  
     **“Browse files”** to select it.

5. 📊 **Review the results**

   - Top metrics at the top:
     - **Total shifts**
     - **Agent-weeks**
     - **Total overtime hours**
   - **Weekly summary** tab:
     - One row per person per week with `total_hours`, `contracted_hours`, `overtime_hours`.
   - **Period summary** tab:
     - Aggregated view per person across the uploaded date range.

6. 🔎 **Check overtime status**

   - If there is **no overtime**, you’ll see a green success banner like:
     > “No overtime detected for \<team\> for the selected period…”
   - If there **is overtime**, you’ll see:
     - A warning banner with the **total OT hours**, and
     - A small table listing **who** has overtime and **how much**.

7. ✉️ **Generate the People / Payroll message**

   - Scroll to **“Suggested message for People / Payroll”**.
   - The textarea contains a pre-filled message that already:
     - Mentions the **team**
     - Includes the **date range**
     - States the **total overtime hours** (or no OT)
   - You can edit this text directly.

8. 📋 **Copy and send**

   - Click **“Copy to clipboard”** to grab the final message.
   - Paste it into Slack or email and attach:
     - `ot_weekly_summary.csv`
     - `ot_monthly_summary.csv`

9. 🔐 **Data & privacy**
   - The app only processes data from the uploaded Dialpad CSV.
   - All processing happens locally on your machine.
   - No data is sent anywhere unless you manually share the exported CSVs.
