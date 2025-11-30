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
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# ----------------- Helper Functions -----------------
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def load_users():
    if not os.path.exists("users.json"):
        return {}
    with open("users.json", "r") as f:
        return json.load(f)

def save_users(users):
    with open("users.json", "w") as f:
        json.dump(users, f)

def get_user_file(username):
    return os.path.join(DATA_DIR, f"{username}_data.csv")

def get_log_status(username):
    today = date.today()
    file_path = get_user_file(username)

    if not os.path.exists(file_path):
        return False, False

    df = pd.read_csv(file_path)

    # Convert date column to actual date objects
    df["date"] = pd.to_datetime(df["date"]).dt.date

    # Daily check — any row with today's date
    has_daily = any(df["date"] == today)

    # Weekly check — any row in the last 7 days with laundry or takeout info
    last_week = today - timedelta(days=7)
    week_df = df[df["date"] >= last_week]

    has_weekly = any(~week_df["laundry_loads"].isna() | (week_df["takeout_meals"] > 0))

    return has_daily, has_weekly

def log_entry(username, entry):
    file_path = get_user_file(username)

    if not os.path.exists(file_path):
        df_init = pd.DataFrame(columns=[
            "timestamp", "date",
            "miles", "shower_minutes", "plastic_bottles",
            "takeout_meals", "laundry_loads",
            "co2_saved"
        ])
        df_init.to_csv(file_path, index=False)

    df = pd.read_csv(file_path)
    df = pd.concat([df, pd.DataFrame([entry])], ignore_index=True)
    df.to_csv(file_path, index=False)

def calculate_co2_savings(entry, baseline):
    miles_saving = max(baseline["miles"] - entry["miles"], 0) * EF_MILE
    shower_saving = max(baseline["shower_minutes"] - entry["shower_minutes"], 0) * EF_SHOWER
    plastic_saving = max(baseline["plastic_bottles"] - entry["plastic_bottles"], 0) * EF_PLASTIC
    takeout_saving = max(baseline["takeout_meals"] - entry["takeout_meals"], 0) * EF_TAKEOUT
    laundry_saving = max(
        baseline["laundry_loads"] - entry.get("laundry_loads", baseline["laundry_loads"]), 
        0
    ) / 7 * EF_LAUNDRY

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
    tab1, tab2 = st.tabs(["Login", "Sign Up"])

    # LOGIN TAB
    with tab1:
        st.subheader("Login")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")

        if st.button("Login"):
            if username in users and users[username]["password"] == hash_password(password):
                st.session_state["logged_in"] = True
                st.session_state["username"] = username
                st.rerun()
            else:
                st.error("Incorrect username or password.")

    # SIGNUP TAB
    with tab2:
        st.subheader("Sign Up")
        new_user = st.text_input("New Username")
        new_pass = st.text_input("New Password", type="password")

        st.write("### Set Your Baseline Habits")

        baseline_miles = st.number_input("Miles driven per day", min_value=0.0, value=5.0)
        baseline_shower = st.number_input("Shower minutes per day", min_value=0.0, value=10.0)
        baseline_plastic = st.number_input("Plastic bottles per day", min_value=0, value=2)
        baseline_takeout = st.number_input("Takeout meals per *week*", min_value=0, value=3)
        baseline_laundry = st.number_input("Laundry loads per week", min_value=0, value=3)

        if st.button("Create Account"):
            if new_user in users:
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
                st.success("Account created! Logging you in...")
                st.session_state["logged_in"] = True
                st.session_state["username"] = new_user
                st.rerun()

# --------------- LOGGED-IN VIEW --------------------
else:
    username = st.session_state["username"]
    baseline = users[username]["baseline"]

    has_daily, has_weekly = get_log_status(username)

    tabs = st.tabs([
        "Daily Tracker",
        "Weekly Tracker",
        "Dashboard",
        "Leaderboard",
        "Settings"
    ])

    # DAILY TRACKER
    with tabs[0]:
        st.subheader("Daily Tracker")
        st.info("Submit your habits **for the entire day**. You can only submit once per day.")

        if has_daily:
            st.success("You already submitted today's entry! Come back tomorrow.")
        else:
            with st.form("daily_form"):
                miles = st.number_input("Miles driven today", min_value=0.0, value=baseline["miles"])
                shower = st.number_input("Shower minutes today", min_value=0.0, value=baseline["shower_minutes"])
                plastic = st.number_input("Plastic bottles used today", min_value=0, value=baseline["plastic_bottles"])

                submitted = st.form_submit_button("Save Daily Entry")

            if submitted:
                entry = {
                    "timestamp": datetime.now().isoformat(),
                    "date": date.today().isoformat(),
                    "miles": miles,
                    "shower_minutes": shower,
                    "plastic_bottles": plastic,
                    "takeout_meals": baseline["takeout_meals"],  # weekly
                    "laundry_loads": baseline["laundry_loads"],
                }
                entry["co2_saved"] = calculate_co2_savings(entry, baseline)
                log_entry(username, entry)
                st.success("Daily entry saved!")
                st.rerun()

    # WEEKLY TRACKER
    with tabs[1]:
        st.subheader("Weekly Tracker")
        st.info("Submit your usage for the **entire week**. This can only be done once per week.")

        if has_weekly:
            st.success("You already submitted this week's entry!")
        else:
            weekly_takeout = st.number_input("Takeout meals this week", min_value=0, value=baseline["takeout_meals"])
            weekly_laundry = st.number_input("Laundry loads this week", min_value=0, value=baseline["laundry_loads"])

            if st.button("Save Weekly Entry"):
                entry = {
                    "timestamp": datetime.now().isoformat(),
                    "date": date.today().isoformat(),
                    "miles": baseline["miles"],
                    "shower_minutes": baseline["shower_minutes"],
                    "plastic_bottles": baseline["plastic_bottles"],
                    "takeout_meals": weekly_takeout,
                    "laundry_loads": weekly_laundry,
                }
                entry["co2_saved"] = calculate_co2_savings(entry, baseline)
                log_entry(username, entry)
                st.success("Weekly entry saved!")
                st.rerun()

    # DASHBOARD
    with tabs[2]:
        st.subheader("Dashboard")
        file_path = get_user_file(username)

        if os.path.exists(file_path):
            df = pd.read_csv(file_path)
            st.metric("Total CO₂ Saved (lbs)", round(df["co2_saved"].sum(), 2))

            df["date"] = pd.to_datetime(df["date"])
            df_week = df[df["date"] >= (datetime.today() - timedelta(days=6))]

            fig, ax = plt.subplots()
            ax.plot(df_week["date"], df_week["co2_saved"], marker="o")
            ax.set_xlabel("Date")
            ax.set_ylabel("CO₂ Saved")
            ax.set_title("CO₂ Savings (Last 7 Days)")
            st.pyplot(fig)

            st.write("### All Entries")
            st.dataframe(df.sort_values("date", ascending=False))

        else:
            st.info("No entries yet!")

    # LEADERBOARD
    with tabs[3]:
        st.subheader("Leaderboard")

        leaderboard = []
        for user in users:
            file = get_user_file(user)
            if os.path.exists(file):
                df_temp = pd.read_csv(file)
                leaderboard.append((user, df_temp["co2_saved"].sum()))

        leaderboard = sorted(leaderboard, key=lambda x: x[1], reverse=True)

        st.write("### Top Users")
        for i, (u, total) in enumerate(leaderboard, start=1):
            st.write(f"{i}. **{u}** — {round(total,2)} lbs CO₂ saved")

    # SETTINGS TAB
    with tabs[4]:
        st.subheader("Settings")
        if st.button("Logout"):
            st.session_state["logged_in"] = False
            st.session_state["username"] = ""
            st.rerun()
