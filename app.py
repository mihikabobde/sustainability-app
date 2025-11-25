# app.py
import streamlit as st
import pandas as pd
import os
from datetime import datetime, date, timedelta
import matplotlib.pyplot as plt
import hashlib
import json

# --- CONFIG: emission factors (lbs CO2 per unit) ---
EF_MILE = 0.9        # lbs CO2 per mile driven
EF_SHOWER = 0.05     # lbs CO2 per minute of shower
EF_PLASTIC = 0.1     # lbs CO2 per plastic bottle
EF_TAKEOUT = 0.5     # lbs CO2 per takeout meal
EF_LAUNDRY = 2.5     # lbs CO2 per laundry load (weekly, divided daily)

DATA_DIR = "user_data"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# --- Helper functions ---
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
    # Laundry is weekly: distribute daily equivalent
    laundry_saving = max(baseline["laundry_loads"] - entry.get("laundry_loads", baseline["laundry_loads"]), 0) / 7 * EF_LAUNDRY
    return miles_saving + shower_saving + plastic_saving + takeout_saving + laundry_saving

def reset_daily_view():
    if "daily_reset" not in st.session_state:
        st.session_state["daily_reset"] = False
    if not os.path.exists("last_reset.txt"):
        with open("last_reset.txt", "w") as f:
            f.write(str(date.today()))
        st.session_state["daily_reset"] = True
        return
    with open("last_reset.txt", "r") as f:
        last = date.fromisoformat(f.read())
    if last < date.today():
        with open("last_reset.txt", "w") as f:
            f.write(str(date.today()))
        st.session_state["daily_reset"] = True
    else:
        st.session_state["daily_reset"] = False

# --- Streamlit page setup ---
st.set_page_config(page_title="Sustainability Tracker", layout="wide")
st.title("🌱 Personalized Sustainability Tracker")

# Initialize session state
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "username" not in st.session_state:
    st.session_state["username"] = ""

# --- Load users ---
users = load_users()

# --- Auto-login after signup ---
if "just_signed_up" in st.session_state:
    st.session_state["logged_in"] = True
    st.session_state["username"] = st.session_state.pop("just_signed_up")
    st.experimental_rerun()

# --- Login / Signup ---
if not st.session_state["logged_in"]:
    tab1, tab2 = st.tabs(["Login", "Sign Up"])

    with tab1:
        st.subheader("Login")
        username = st.text_input("Username", key="login_user")
        password = st.text_input("Password", type="password", key="login_pass")
        if st.button("Login"):
            if username in users and users[username]["password"] == hash_password(password):
                st.session_state["logged_in"] = True
                st.session_state["username"] = username
                st.success(f"Logged in as {username}")
                st.experimental_rerun()
            else:
                st.error("Invalid username or password")

    with tab2:
        st.subheader("Sign Up")
        new_user = st.text_input("Username", key="signup_user")
        new_pass = st.text_input("Password", type="password", key="signup_pass")
        baseline_miles = st.number_input("Baseline miles driven per day", min_value=0.0, value=5.0)
        baseline_shower = st.number_input("Baseline shower minutes per day", min_value=0.0, value=10.0)
        baseline_plastic = st.number_input("Baseline plastic bottles used per day", min_value=0, value=2)
        baseline_takeout = st.number_input("Baseline takeout meals per day", min_value=0, value=1)
        baseline_laundry = st.number_input("Baseline laundry loads per week", min_value=0, value=3)

        if st.button("Sign Up"):
            if new_user in users:
                st.error("Username already exists")
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
                st.session_state["just_signed_up"] = new_user
                st.success("Account created! Logging you in...")

# --- Main App ---
else:
    username = st.session_state["username"]
    baseline = users[username]["baseline"]

    reset_daily_view()

    tabs = st.tabs(["Daily Tracker", "Weekly Tracker", "Dashboard", "Leaderboard & Badges", "Settings"])

    # --- Daily Tracker ---
    with tabs[0]:
        st.subheader("Daily Sustainability Input")
        with st.form("daily_form"):
            miles = st.number_input("Miles driven today", min_value=0.0, value=baseline["miles"], step=0.1)
            shower = st.number_input("Minutes showered today", min_value=0.0, value=baseline["shower_minutes"], step=1.0)
            plastic = st.number_input("Plastic bottles used today", min_value=0, value=baseline["plastic_bottles"], step=1)
            takeout = st.number_input("Takeout meals eaten today", min_value=0, value=baseline["takeout_meals"], step=1)
            submitted = st.form_submit_button("Save Entry")

        if submitted:
            entry = {
                "timestamp": datetime.now().isoformat(),
                "date": date.today().isoformat(),
                "miles": miles,
                "shower_minutes": shower,
                "plastic_bottles": plastic,
                "takeout_meals": takeout
            }
            co2 = calculate_co2_savings(entry, baseline)
            entry["co2_saved"] = co2
            log_entry(username, entry)
            st.success(f"Saved! CO₂ impact for today: {co2:.2f} lbs")

    # --- Weekly Tracker ---
    with tabs[1]:
        st.subheader("Weekly Tracker")
        file_path = get_user_file(username)
        df_user = pd.read_csv(file_path) if os.path.exists(file_path) else pd.DataFrame()
        weekly_loads = st.number_input("Laundry loads this week", min_value=0, value=baseline["laundry_loads"], step=1)
        if st.button("Save Weekly Laundry"):
            entry = {
                "timestamp": datetime.now().isoformat(),
                "date": date.today().isoformat(),
                "miles": baseline["miles"],
                "shower_minutes": baseline["shower_minutes"],
                "plastic_bottles": baseline["plastic_bottles"],
                "takeout_meals": baseline["takeout_meals"],
                "laundry_loads": weekly_loads
            }
            co2 = calculate_co2_savings(entry, baseline)
            entry["co2_saved"] = co2
            log_entry(username, entry)
            st.success(f"Laundry entry saved! Weekly CO₂ impact included.")

    # --- Dashboard ---
    with tabs[2]:
        st.subheader("Dashboard")
        if os.path.exists(get_user_file(username)):
            df = pd.read_csv(get_user_file(username))
            df["date"] = pd.to_datetime(df["date"]).dt.date

            st.write("**Total CO₂ saved:**", round(df["co2_saved"].sum(), 2))
            # Weekly view
            week_mask = (df["date"] >= date.today() - timedelta(days=6)) & (df["date"] <= date.today())
            df_week = df.loc[week_mask].groupby("date")["co2_saved"].sum().reset_index()
            fig, ax = plt.subplots()
            ax.plot(df_week["date"], df_week["co2_saved"], marker='o')
            ax.set_xlabel("Date")
            ax.set_ylabel("CO₂ Impact (lbs)")
            ax.set_title("Daily CO₂ Impact — Last 7 days")
            fig.autofmt_xdate()
            st.pyplot(fig)

            st.write("**Raw entries:**")
            st.dataframe(df.sort_values("date", ascending=False))
        else:
            st.info("No data yet. Start logging your daily actions!")

    # --- Leaderboard & Badges ---
    with tabs[3]:
        st.subheader("Leaderboard & Badges")
        leaderboard = []
        for user in users:
            user_file = get_user_file(user)
            if os.path.exists(user_file):
                df_user = pd.read_csv(user_file)
                total = df_user["co2_saved"].sum()
                leaderboard.append((user, total))
        leaderboard = sorted(leaderboard, key=lambda x: x[1], reverse=True)
        st.write("### Top Users by CO₂ Saved")
        for i, (user_, total_) in enumerate(leaderboard[:10], start=1):
            st.write(f"{i}. {user_}: {round(total_, 2)} lbs CO₂ saved")

        # Badges
        df_user = pd.read_csv(get_user_file(username))
        total_saved = df_user["co2_saved"].sum()
        streak = len(df_user)
        if streak >= 7:
            st.write("🏆 Consistency Hero: 7+ consecutive entries!")
        if total_saved >= 100:
            st.write("🌟 Carbon Crusher: 100+ lbs saved!")
        if streak >= 30:
            st.write("💎 Eco Elite: 30+ entries!")

    # --- Settings / Logout ---
    with tabs[4]:
        st.subheader("Settings")
        if st.button("Logout"):
            st.session_state["logged_in"] = False
            st.session_state["username"] = ""
            st.experimental_rerun()

