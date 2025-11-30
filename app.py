# app.py
import streamlit as st
import pandas as pd
import os
import re
from datetime import datetime, date, timedelta
import matplotlib.pyplot as plt
import hashlib
import json

# -----------------------
# Config / constants
# -----------------------
USERS_FILE = "users.json"
DATA_DIR = "user_data"
LAST_RESET_FILE = "last_reset.txt"

# Emission factors (lbs CO2 per unit)
EF_MILE = 0.9
EF_SHOWER = 0.05
EF_PLASTIC = 0.1
EF_TAKEOUT = 0.5
EF_LAUNDRY = 2.5  # per load (weekly converted to daily when used)

# -----------------------
# Ensure directories & files exist
# -----------------------
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

if not os.path.exists(USERS_FILE):
    # create empty users file
    with open(USERS_FILE, "w") as f:
        json.dump({}, f)

# -----------------------
# Helpers
# -----------------------
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def load_users() -> dict:
    try:
        with open(USERS_FILE, "r") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
            return {}
    except Exception:
        # corrupted file or read error — recover by returning empty dict
        return {}

def save_users(users: dict) -> None:
    # write atomically
    tmp = USERS_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(users, f, indent=2)
    os.replace(tmp, USERS_FILE)

def safe_username(name: str) -> str:
    # allow letters, numbers, underscores; replace others with underscore
    return re.sub(r"[^0-9A-Za-z_]", "_", name.strip())

def get_user_file(username: str) -> str:
    username = safe_username(username)
    return os.path.join(DATA_DIR, f"{username}_data.csv")

def ensure_user_file_exists(username: str):
    fp = get_user_file(username)
    if not os.path.exists(fp):
        df_init = pd.DataFrame(columns=[
            "timestamp", "date",
            "miles", "shower_minutes", "plastic_bottles",
            "takeout_meals", "laundry_loads",
            "co2_saved"
        ])
        df_init.to_csv(fp, index=False)

def log_entry(username: str, entry: dict):
    fp = get_user_file(username)
    ensure_user_file_exists(username)
    try:
        df = pd.read_csv(fp)
    except Exception:
        # if read fails, recreate empty
        df = pd.DataFrame(columns=[
            "timestamp", "date",
            "miles", "shower_minutes", "plastic_bottles",
            "takeout_meals", "laundry_loads",
            "co2_saved"
        ])
    df = pd.concat([df, pd.DataFrame([entry])], ignore_index=True)
    df.to_csv(fp, index=False)

def calculate_co2_savings(entry: dict, baseline: dict) -> float:
    # Use .get with defaults to avoid KeyError
    miles_saving = max(float(baseline.get("miles", 0)) - float(entry.get("miles", 0)), 0) * EF_MILE
    shower_saving = max(float(baseline.get("shower_minutes", 0)) - float(entry.get("shower_minutes", 0)), 0) * EF_SHOWER
    plastic_saving = max(float(baseline.get("plastic_bottles", 0)) - float(entry.get("plastic_bottles", 0)), 0) * EF_PLASTIC
    takeout_saving = max(float(baseline.get("takeout_meals", 0)) - float(entry.get("takeout_meals", 0)), 0) * EF_TAKEOUT

    # laundry baseline is per week. entry may include 'laundry_loads' for weekly entry.
    baseline_laundry = float(baseline.get("laundry_loads", 0))
    entry_laundry = float(entry.get("laundry_loads", baseline_laundry))
    laundry_saving = max(baseline_laundry - entry_laundry, 0) / 7.0 * EF_LAUNDRY

    return miles_saving + shower_saving + plastic_saving + takeout_saving + laundry_saving

# -----------------------
# Daily reset helper
# -----------------------
def reset_daily_view():
    if "daily_reset" not in st.session_state:
        st.session_state["daily_reset"] = False

    today = date.today()
    if not os.path.exists(LAST_RESET_FILE):
        with open(LAST_RESET_FILE, "w") as f:
            f.write(str(today))
        st.session_state["daily_reset"] = True
        return

    try:
        with open(LAST_RESET_FILE, "r") as f:
            last = date.fromisoformat(f.read().strip())
    except Exception:
        # If file corrupt, reset it
        with open(LAST_RESET_FILE, "w") as f:
            f.write(str(today))
        st.session_state["daily_reset"] = True
        return

    if last < today:
        with open(LAST_RESET_FILE, "w") as f:
            f.write(str(today))
        st.session_state["daily_reset"] = True
    else:
        st.session_state["daily_reset"] = False

# -----------------------
# Streamlit UI + flow
# -----------------------
st.set_page_config(page_title="Sustainability Tracker", layout="wide")
st.title("🌱 Personalized Sustainability Tracker")

# initialize session state keys
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "username" not in st.session_state:
    st.session_state["username"] = ""

# load users fresh
users = load_users()

# -----------------------
# Login / Signup UI
# -----------------------
if not st.session_state["logged_in"]:
    users = load_users()  # reload (helps with delay after save on Cloud)

    tab1, tab2 = st.tabs(["Login", "Sign Up"])

    # ---- Login ----
    with tab1:
        st.subheader("Login")
        login_user = st.text_input("Username", key="login_user")
        login_pass = st.text_input("Password", type="password", key="login_pass")

        if st.button("Login"):
            u = safe_username(login_user)
            if u and u in users and users[u].get("password") == hash_password(login_pass):
                st.session_state["logged_in"] = True
                st.session_state["username"] = u
                st.success(f"Logged in as {u}")
                # ensure file exists before moving on
                ensure_user_file_exists(u)
                st.rerun()
            else:
                st.error("Invalid username or password")

    # ---- Signup ----
    with tab2:
        st.subheader("Sign Up")
        new_user_raw = st.text_input("Choose a username", key="signup_user")
        new_pass = st.text_input("Choose a password", type="password", key="signup_pass")

        st.write("### Set baseline (your typical behavior)")
        baseline_miles = st.number_input("Miles driven per day (baseline)", min_value=0.0, value=5.0, step=0.1)
        baseline_shower = st.number_input("Shower minutes per day (baseline)", min_value=0.0, value=10.0, step=1.0)
        baseline_plastic = st.number_input("Plastic bottles per day (baseline)", min_value=0, value=2, step=1)
        baseline_takeout = st.number_input("Takeout meals per day (baseline)", min_value=0, value=1, step=1)
        baseline_laundry = st.number_input("Laundry loads per week (baseline)", min_value=0, value=3, step=1)

        if st.button("Create Account"):
            username_safe = safe_username(new_user_raw)
            if not username_safe:
                st.error("Please enter a valid username")
            elif username_safe in users:
                st.error("Username already exists. Pick another.")
            elif not new_pass:
                st.error("Please enter a password")
            else:
                users[username_safe] = {
                    "password": hash_password(new_pass),
                    "baseline": {
                        "miles": float(baseline_miles),
                        "shower_minutes": float(baseline_shower),
                        "plastic_bottles": int(baseline_plastic),
                        "takeout_meals": int(baseline_takeout),
                        "laundry_loads": int(baseline_laundry)
                    }
                }
                save_users(users)
                # create empty user file so reads later won't fail
                ensure_user_file_exists(username_safe)
                st.session_state["logged_in"] = True
                st.session_state["username"] = username_safe
                st.success("Account created — logging you in now.")
                st.rerun()

# -----------------------
# Main app (post-login)
# -----------------------
else:
    # reload users and ensure username is valid (handles cloud races)
    users = load_users()
    username = st.session_state.get("username", "")
    if username not in users:
        # user record missing (possible race or manual file edit) -> log out safely
        st.warning("User data not available. Please log in again or recreate account.")
        st.session_state["logged_in"] = False
        st.session_state["username"] = ""
        st.rerun()

    baseline = users[username].get("baseline", {})
    # provide defaults if baseline missing
    baseline_defaults = {"miles": 0, "shower_minutes": 0, "plastic_bottles": 0, "takeout_meals": 0, "laundry_loads": 0}
    # merge
    for k, v in baseline_defaults.items():
        baseline.setdefault(k, v)

    reset_daily_view()

    tabs = st.tabs(["Daily Tracker", "Weekly Tracker", "Dashboard", "Leaderboard & Badges", "Settings"])

    # ---- Daily Tracker ----
    with tabs[0]:
        st.subheader("Daily Sustainability Input")
        with st.form("daily_form"):
            miles = st.number_input("Miles driven today", min_value=0.0, value=float(baseline["miles"]))
            shower = st.number_input("Minutes showered today", min_value=0.0, value=float(baseline["shower_minutes"]))
            plastic = st.number_input("Plastic bottles used today", min_value=0, value=int(baseline["plastic_bottles"]))
            takeout = st.number_input("Takeout meals eaten today", min_value=0, value=int(baseline["takeout_meals"]))
            submitted = st.form_submit_button("Save Entry")

        if submitted:
            entry = {
                "timestamp": datetime.now().isoformat(),
                "date": date.today().isoformat(),
                "miles": float(miles),
                "shower_minutes": float(shower),
                "plastic_bottles": int(plastic),
                "takeout_meals": int(takeout),
            }
            co2 = calculate_co2_savings(entry, baseline)
            entry["co2_saved"] = float(co2)
            log_entry(username, entry)
            st.success(f"Saved! Estimated CO₂ impact today: {co2:.2f} lbs")

    # ---- Weekly Tracker ----
    with tabs[1]:
        st.subheader("Weekly Tracker (Laundry)")
        weekly_loads = st.number_input("Laundry loads this week", min_value=0, value=int(baseline["laundry_loads"]))
        if st.button("Save Weekly Laundry"):
            entry = {
                "timestamp": datetime.now().isoformat(),
                "date": date.today().isoformat(),
                "miles": float(baseline["miles"]),
                "shower_minutes": float(baseline["shower_minutes"]),
                "plastic_bottles": int(baseline["plastic_bottles"]),
                "takeout_meals": int(baseline["takeout_meals"]),
                "laundry_loads": int(weekly_loads)
            }
            co2 = calculate_co2_savings(entry, baseline)
            entry["co2_saved"] = float(co2)
            log_entry(username, entry)
            st.success("Weekly laundry saved and included in CO₂ totals.")

    # ---- Dashboard ----
    with tabs[2]:
        st.subheader("Dashboard")
        user_file = get_user_file(username)
        if os.path.exists(user_file):
            try:
                df = pd.read_csv(user_file)
                if "date" in df.columns:
                    df["date"] = pd.to_datetime(df["date"]).dt.date
                else:
                    df["date"] = pd.to_datetime(df["timestamp"]).dt.date
            except Exception:
                st.error("Unable to read your data file. It may be corrupted.")
                df = pd.DataFrame(columns=["date", "co2_saved"])
        else:
            df = pd.DataFrame(columns=["date", "co2_saved"])

        total_saved = df["co2_saved"].sum() if "co2_saved" in df.columns and not df.empty else 0.0
        st.write(f"### Total CO₂ saved (lifetime): {total_saved:.2f} lbs")

        # last 7 days plotting
        if not df.empty and "date" in df.columns:
            week_ago = date.today() - timedelta(days=6)
            df_week = df.loc[df["date"] >= week_ago].groupby("date")["co2_saved"].sum().reset_index()
            if not df_week.empty:
                fig, ax = plt.subplots()
                ax.plot(df_week["date"], df_week["co2_saved"], marker="o")
                ax.set_xlabel("Date")
                ax.set_ylabel("CO₂ saved (lbs)")
                ax.set_title("Last 7 days")
                fig.autofmt_xdate()
                st.pyplot(fig)
            else:
                st.info("No entries in the last 7 days.")
        else:
            st.info("No logged entries yet. Add a daily or weekly entry to see charts.")

        if not df.empty:
            st.write("### All entries")
            st.dataframe(df.sort_values("date", ascending=False))
        else:
            st.write("No entries yet. Your data will appear here.")

    # ---- Leaderboard & Badges ----
    with tabs[3]:
        st.subheader("Leaderboard")
        leaderboard = []
        users = load_users()
        for u in users:
            fp = get_user_file(u)
            if os.path.exists(fp):
                try:
                    df_u = pd.read_csv(fp)
                    total = df_u["co2_saved"].sum() if "co2_saved" in df_u.columns else 0.0
                except Exception:
                    total = 0.0
                leaderboard.append((u, float(total)))
        leaderboard = sorted(leaderboard, key=lambda x: x[1], reverse=True)
        if leaderboard:
            for i, (u, tot) in enumerate(leaderboard[:10], 1):
                st.write(f"{i}. **{u}** — {tot:.2f} lbs CO₂ saved")
        else:
            st.info("No users have logged data yet.")

        st.write("### Your Badges")
        # badges: requires reading user file
        fp = get_user_file(username)
        if os.path.exists(fp):
            try:
                df_user = pd.read_csv(fp)
                total_saved = float(df_user["co2_saved"].sum()) if "co2_saved" in df_user.columns else 0.0
                entry_count = len(df_user)
            except Exception:
                total_saved = 0.0
                entry_count = 0
        else:
            total_saved = 0.0
            entry_count = 0

        if entry_count >= 7:
            st.write("🏆 **Consistency Hero** — Logged 7+ entries")
        if total_saved >= 100:
            st.write("🌟 **Carbon Crusher** — 100+ lbs saved")
        if entry_count >= 30:
            st.write("💎 **Eco Elite** — 30+ entries")

    # ---- Settings ----
    with tabs[4]:
        st.subheader("Settings")
        if st.button("Logout"):
            st.session_state["logged_in"] = False
            st.session_state["username"] = ""
            st.rerun()
