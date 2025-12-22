# app.py
import streamlit as st
import pandas as pd
import os
from datetime import datetime, date, timedelta
import matplotlib.pyplot as plt
import hashlib
import json

# --- CONFIG: emission factors (lbs CO2 per unit) ---
EF_MILE = 0.9
EF_SHOWER = 0.05
EF_PLASTIC = 0.1
EF_TAKEOUT = 0.5
EF_LAUNDRY = 2.5

DATA_DIR = "user_data"
USERS_FILE = "users.json"

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# ----------------- Helper Functions -----------------
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def load_users() -> dict:
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        with open(USERS_FILE, "r") as f:
            return json.load(f) or {}
    except (json.JSONDecodeError, IOError):
        return {}

def save_users(users: dict):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)

def get_user_file(username: str) -> str:
    return os.path.join(DATA_DIR, f"{username}_data.csv")

def get_log_status(username: str):
    today = date.today()
    file_path = get_user_file(username)

    if not os.path.exists(file_path):
        return False, False

    try:
        df = pd.read_csv(file_path)
    except Exception:
        return False, False

    if "date" not in df.columns or "entry_type" not in df.columns:
        return False, False

    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date

    daily_entries = df[df["entry_type"] == "daily"]
    last_daily = daily_entries["date"].max() if not daily_entries.empty else None
    has_daily = (last_daily == today)

    weekly_entries = df[df["entry_type"] == "weekly"]
    last_weekly = weekly_entries["date"].max() if not weekly_entries.empty else None

    if last_weekly is None:
        has_weekly = False
    else:
        has_weekly = (last_weekly.isocalendar().week == today.isocalendar().week and last_weekly.year == today.year)

    return has_daily, has_weekly

def log_entry(username: str, entry: dict):
    file_path = get_user_file(username)

    if not os.path.exists(file_path):
        df_init = pd.DataFrame(columns=[
            "timestamp", "date", "entry_type",
            "miles", "shower_minutes", "plastic_bottles",
            "takeout_meals", "laundry_loads",
            "co2_saved"
        ])
        df_init.to_csv(file_path, index=False)

    try:
        df = pd.read_csv(file_path)
    except Exception:
        df = pd.DataFrame(columns=[
            "timestamp", "date", "entry_type",
            "miles", "shower_minutes", "plastic_bottles",
            "takeout_meals", "laundry_loads",
            "co2_saved"
        ])

    df = pd.concat([df, pd.DataFrame([entry])], ignore_index=True)
    df.to_csv(file_path, index=False)

def calculate_co2_savings(entry: dict, baseline: dict, entry_type: str):
    miles_e = entry.get("miles") or 0
    shower_e = entry.get("shower_minutes") or 0
    plastic_e = entry.get("plastic_bottles") or 0

    miles_b = baseline.get("miles") or 0
    shower_b = baseline.get("shower_minutes") or 0
    plastic_b = baseline.get("plastic_bottles") or 0

    miles_saving = max(miles_b - miles_e, 0) * EF_MILE
    shower_saving = max(shower_b - shower_e, 0) * EF_SHOWER
    plastic_saving = max(plastic_b - plastic_e, 0) * EF_PLASTIC

    if entry_type == "daily":
        return miles_saving + shower_saving + plastic_saving

    takeout_e = entry.get("takeout_meals") or 0
    laundry_e = entry.get("laundry_loads") or 0
    takeout_b = baseline.get("takeout_meals") or 0
    laundry_b = baseline.get("laundry_loads") or 0

    takeout_saving = max(takeout_b - takeout_e, 0) * EF_TAKEOUT
    laundry_saving = max(laundry_b - laundry_e, 0) / 7 * EF_LAUNDRY

    return miles_saving + shower_saving + plastic_saving + takeout_saving + laundry_saving

# ----------------- Streamlit Setup -----------------
st.set_page_config(page_title="Sustainability Tracker", layout="wide")
st.title("🌱 Sustainability Tracker")

if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "username" not in st.session_state:
    st.session_state["username"] = ""

users = load_users()

# --------------- LOGIN / SIGNUP --------------------
if not st.session_state["logged_in"]:
    st.markdown("## 🌍 Measure Your Real Impact")
    st.markdown(
        "**Find your real carbon footprint today ** "
        "and discover the easiest habits that save CO₂ **and** save you money, daily."
    )
    st.markdown("---")

    tab1, tab2 = st.tabs(["🔓 Login", "🆕 Create Account"])

    with tab1:
        st.subheader("Welcome Back")
        st.caption("Continue your eco-streak and keep making progress 🌱")
        username_input = st.text_input("Username")
        password_input = st.text_input("Password", type="password")

        if st.button("Login", use_container_width=True):
            users = load_users()
            if username_input and username_input in users and users[username_input].get("password") == hash_password(password_input or ""):
                st.session_state["logged_in"] = True
                st.session_state["username"] = username_input
                st.rerun()
            else:
                st.error("Incorrect username or password.")

    with tab2:
        st.subheader("Start Your Impact Journey")
        st.caption("Unlock badges 🏅, track progress 📈, and join a growing community.")
        new_user = st.text_input("Create a Username")
        new_pass = st.text_input("Create a Password", type="password")

        st.write("### Set Your Baseline Habits")
        st.caption("These help us estimate your starting footprint (you can adjust anytime).")
        baseline_miles = st.number_input("Miles driven per day", min_value=0.0, value=5.0)
        baseline_shower = st.number_input("Shower minutes per day", min_value=0.0, value=10.0)
        baseline_plastic = st.number_input("Plastic bottles per day", min_value=0, value=2)
        baseline_takeout = st.number_input("Takeout meals per *week*", min_value=0, value=3)
        baseline_laundry = st.number_input("Laundry loads per week", min_value=0, value=3)

        if st.button("Create My Free Account 🌍", use_container_width=True):
            users = load_users()
            if not new_user or not new_pass:
                st.error("Choose a username and password.")
            elif new_user in users:
                st.error("Username already exists.")
            else:
                users[new_user] = {
                    "password": hash_password(new_pass),
                    "baseline": {
                        "miles": baseline_miles,
                        "shower_minutes": baseline_shower,
                        "plastic_bottles": baseline_plastic,
                        "takeout_meals": baseline_takeout,
                        "laundry_loads": baseline_laundry
                    }
                }
                save_users(users)
                st.success("Account created! Logging you in... 🚀")
                st.session_state["logged_in"] = True
                st.session_state["username"] = new_user
                st.rerun()

# --------------- LOGGED-IN VIEW --------------------
else:
    username = st.session_state.get("username", "")
    users = load_users()

    if username not in users:
        st.warning("User not found on disk. You've been logged out.")
        st.session_state["logged_in"] = False
        st.session_state["username"] = ""
        st.rerun()

    baseline = users[username].get("baseline", {
        "miles": 5.0,
        "shower_minutes": 10.0,
        "plastic_bottles": 2,
        "takeout_meals": 3,
        "laundry_loads": 3
    })

    has_daily, has_weekly = get_log_status(username)

    tabs = st.tabs([
        "Daily Tracker",
        "Weekly Tracker",
        "Dashboard",
        "Insights",
        "Settings"
    ])

    with tabs[0]:
        st.subheader("Daily Tracker")
        st.info("Submit habits **for the entire day**. One entry allowed per day.")
        with st.form("daily_form"):
            miles = st.number_input("Miles driven today", min_value=0.0, value=baseline["miles"])
            shower = st.number_input("Shower minutes today", min_value=0.0, value=baseline["shower_minutes"])
            plastic = st.number_input("Plastic bottles used today", min_value=0, value=baseline["plastic_bottles"])
            submitted = st.form_submit_button("Save Daily Entry")
            if submitted:
                entry = {
                    "timestamp": datetime.now().isoformat(),
                    "date": date.today().isoformat(),
                    "entry_type": "daily",
                    "miles": miles,
                    "shower_minutes": shower,
                    "plastic_bottles": plastic,
                    "takeout_meals": None,
                    "laundry_loads": None,
                }
                entry["co2_saved"] = calculate_co2_savings(entry, baseline, "daily")
                log_entry(username, entry)
                st.experimental_rerun()

    with tabs[1]:
        st.subheader("Weekly Tracker")
        st.info("Submit once per week for laundry + takeout.")
        with st.form("weekly_form"):
            weekly_takeout = st.number_input("Takeout meals this week", min_value=0, value=baseline.get("takeout_meals", 0))
            weekly_laundry = st.number_input("Laundry loads this week", min_value=0, value=baseline.get("laundry_loads", 0))
            submitted = st.form_submit_button("Save Weekly Entry")
            if submitted:
                entry = {
                    "timestamp": datetime.now().isoformat(),
                    "date": date.today().isoformat(),
                    "entry_type": "weekly",
                    "miles": baseline.get("miles", 0),
                    "shower_minutes": baseline.get("shower_minutes", 0),
                    "plastic_bottles": baseline.get("plastic_bottles", 0),
                    "takeout_meals": weekly_takeout,
                    "laundry_loads": weekly_laundry,
                }
                entry["co2_saved"] = calculate_co2_savings(entry, baseline, "weekly")
                log_entry(username, entry)
                st.experimental_rerun()

    with tabs[2]:
        st.subheader("Dashboard")
        file_path = get_user_file(username)
        if os.path.exists(file_path):
            df = pd.read_csv(file_path)
            if "co2_saved" not in df.columns:
                df["co2_saved"] = 0
            df["co2_saved"] = pd.to_numeric(df["co2_saved"], errors="coerce").fillna(0)
            st.metric("Total CO₂ Saved (lbs)", round(df["co2_saved"].sum(), 2))
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
            df_week = df[df["date"] >= (datetime.today() - timedelta(days=6))]
            fig, ax = plt.subplots()
            if not df_week.empty:
                ax.plot(df_week["date"], df_week["co2_saved"], marker="o")
            else:
                ax.plot([], [])
            ax.set_xlabel("Date")
            ax.set_ylabel("CO₂ Saved (lbs)")
            ax.set_title("CO₂ Savings (Last 7 Days)")
            st.pyplot(fig)
            st.write("### All Entries")
            st.dataframe(df.sort_values("date", ascending=False))
        else:
            st.info("No entries yet!")

    with tabs[3]:
        st.subheader("Insights")
        file_path = get_user_file(username)
        if os.path.exists(file_path):
            df = pd.read_csv(file_path)
            if "co2_saved" not in df.columns:
                df["co2_saved"] = 0
            total_days = len(df[df["entry_type"]=="daily"])
            total_weekly = len(df[df["entry_type"]=="weekly"])
            total_co2 = round(df["co2_saved"].sum(), 2)
            st.write(f"**Total CO₂ Saved:** {total_co2} lbs")
            st.write(f"**Daily Entries:** {total_days}")
            st.write(f"**Weekly Entries:** {total_weekly}")
            if total_days > 0:
                avg_daily = round(df[df["entry_type"]=="daily"]["co2_saved"].mean(),2)
                st.write(f"**Average Daily CO₂ Saved:** {avg_daily} lbs")
        else:
            st.info("No data to show insights yet.")

    with tabs[4]:
        st.subheader("Settings")
        st.write(f"Logged in as **{username}**")
        if st.button("Logout"):
            st.session_state["logged_in"] = False
            st.session_state["username"] = ""
            st.rerun()
