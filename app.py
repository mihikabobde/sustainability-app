# app.py
import streamlit as st
import pandas as pd
import os
from datetime import datetime, date, timedelta
import matplotlib.pyplot as plt
import hashlib
import json

# ---------------- CONFIG ----------------
EF_MILE = 0.9
EF_SHOWER = 0.05
EF_PLASTIC = 0.1
EF_TAKEOUT = 0.5
EF_LAUNDRY = 2.5

DATA_DIR = "user_data"
USERS_FILE = "users.json"

os.makedirs(DATA_DIR, exist_ok=True)

# ---------------- HELPERS ----------------
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        with open(USERS_FILE, "r") as f:
            return json.load(f) or {}
    except Exception:
        return {}

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)

def get_user_file(username):
    return os.path.join(DATA_DIR, f"{username}_data.csv")

def log_entry(username, entry):
    file = get_user_file(username)
    if not os.path.exists(file):
        pd.DataFrame(columns=entry.keys()).to_csv(file, index=False)
    df = pd.read_csv(file)
    df = pd.concat([df, pd.DataFrame([entry])], ignore_index=True)
    df.to_csv(file, index=False)

def calculate_co2(entry, baseline, entry_type):
    miles = max(baseline["miles"] - (entry.get("miles") or 0), 0) * EF_MILE
    shower = max(baseline["shower_minutes"] - (entry.get("shower_minutes") or 0), 0) * EF_SHOWER
    plastic = max(baseline["plastic_bottles"] - (entry.get("plastic_bottles") or 0), 0) * EF_PLASTIC

    if entry_type == "daily":
        return miles + shower + plastic

    takeout = max(baseline["takeout_meals"] - (entry.get("takeout_meals") or 0), 0) * EF_TAKEOUT
    laundry = max(baseline["laundry_loads"] - (entry.get("laundry_loads") or 0), 0) / 7 * EF_LAUNDRY
    return miles + shower + plastic + takeout + laundry

def get_streaks(df):
    df["date"] = pd.to_datetime(df["date"]).dt.date
    days = sorted(df["date"].unique(), reverse=True)

    daily_streak = 0
    today = date.today()
    for i, d in enumerate(days):
        if d == today - timedelta(days=i):
            daily_streak += 1
        else:
            break

    weeks = sorted({d.isocalendar()[:2] for d in days}, reverse=True)
    weekly_streak = 0
    current = today.isocalendar()[:2]
    for i, w in enumerate(weeks):
        if w == (current[0], current[1] - i):
            weekly_streak += 1
        else:
            break

    return daily_streak, weekly_streak

# ---------------- STREAMLIT SETUP ----------------
st.set_page_config(page_title="Sustainability Tracker", layout="wide")
st.title("🌱 Sustainability Tracker")

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = ""

users = load_users()

# ---------------- AUTH ----------------
if not st.session_state.logged_in:
    st.subheader("🌍 Measure Your Real Climate Impact")

    tab1, tab2 = st.tabs(["Login", "Create Account"])

    with tab1:
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.button("Login"):
            if u in users and users[u]["password"] == hash_password(p):
                st.session_state.logged_in = True
                st.session_state.username = u
                st.rerun()
            else:
                st.error("Invalid credentials")

    with tab2:
        new_u = st.text_input("New Username")
        new_p = st.text_input("New Password", type="password")

        st.markdown("**Baseline habits**")
        miles = st.number_input("Miles driven/day", 0.0, 20.0, 5.0)
        shower = st.number_input("Shower minutes/day", 0.0, 30.0, 10.0)
        plastic = st.number_input("Plastic bottles/day", 0, 10, 2)
        takeout = st.number_input("Takeout meals/week", 0, 10, 3)
        laundry = st.number_input("Laundry loads/week", 0, 10, 3)

        if st.button("Create Account"):
            if new_u and new_p and new_u not in users:
                users[new_u] = {
                    "password": hash_password(new_p),
                    "baseline": {
                        "miles": miles,
                        "shower_minutes": shower,
                        "plastic_bottles": plastic,
                        "takeout_meals": takeout,
                        "laundry_loads": laundry
                    }
                }
                save_users(users)
                st.session_state.logged_in = True
                st.session_state.username = new_u
                st.rerun()
            else:
                st.error("Invalid or duplicate username")

# ---------------- MAIN APP ----------------
else:
    username = st.session_state.username
    baseline = users[username]["baseline"]
    file = get_user_file(username)

    tabs = st.tabs(["Daily", "Weekly", "Insights", "Settings"])

    # ---------- DAILY ----------
    with tabs[0]:
        with st.form("daily"):
            miles = st.number_input("Miles today", 0.0, value=baseline["miles"])
            shower = st.number_input("Shower minutes today", 0.0, value=baseline["shower_minutes"])
            plastic = st.number_input("Plastic bottles today", 0, value=baseline["plastic_bottles"])
            if st.form_submit_button("Save"):
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
                entry["co2_saved"] = calculate_co2(entry, baseline, "daily")
                log_entry(username, entry)
                st.success("Saved!")
                st.rerun()

    # ---------- WEEKLY ----------
    with tabs[1]:
        takeout = st.number_input("Takeout meals this week", 0, value=baseline["takeout_meals"])
        laundry = st.number_input("Laundry loads this week", 0, value=baseline["laundry_loads"])
        if st.button("Save Weekly"):
            entry = {
                "timestamp": datetime.now().isoformat(),
                "date": date.today().isoformat(),
                "entry_type": "weekly",
                "miles": baseline["miles"],
                "shower_minutes": baseline["shower_minutes"],
                "plastic_bottles": baseline["plastic_bottles"],
                "takeout_meals": takeout,
                "laundry_loads": laundry,
            }
            entry["co2_saved"] = calculate_co2(entry, baseline, "weekly")
            log_entry(username, entry)
            st.success("Saved!")
            st.rerun()

    # ---------- INSIGHTS ----------
    with tabs[2]:
        if not os.path.exists(file):
            st.info("Log some data to see insights!")
        else:
            df = pd.read_csv(file)
            df["co2_saved"] = pd.to_numeric(df["co2_saved"], errors="coerce").fillna(0)

            daily_streak, weekly_streak = get_streaks(df)

            c1, c2 = st.columns(2)
            c1.metric("🔥 Daily Streak", f"{daily_streak} days")
            c2.metric("📆 Weekly Streak", f"{weekly_streak} weeks")

            st.markdown("### 📊 Your Biggest Impact Areas")

            impact = {
                "Driving": (baseline["miles"] - df["miles"].fillna(baseline["miles"])).sum() * EF_MILE,
                "Showers": (baseline["shower_minutes"] - df["shower_minutes"].fillna(baseline["shower_minutes"])).sum() * EF_SHOWER,
                "Plastic": (baseline["plastic_bottles"] - df["plastic_bottles"].fillna(baseline["plastic_bottles"])).sum() * EF_PLASTIC,
                "Takeout": (baseline["takeout_meals"] - df["takeout_meals"].fillna(baseline["takeout_meals"])).sum() * EF_TAKEOUT,
                "Laundry": (baseline["laundry_loads"] - df["laundry_loads"].fillna(baseline["laundry_loads"])).sum() / 7 * EF_LAUNDRY,
            }

            impact_df = pd.DataFrame.from_dict(impact, orient="index", columns=["CO₂ Saved"])
            fig, ax = plt.subplots()
            impact_df.plot(kind="bar", ax=ax, legend=False)
            ax.set_ylabel("lbs CO₂")
            st.pyplot(fig)

            top = max(impact, key=impact.get)
            st.markdown(f"🧠 **Insight:** Your biggest contribution so far comes from **{top.lower()} changes**.")

            total = df["co2_saved"].sum()
            st.markdown("### 🌍 What Your Impact Equals")
            st.write(f"📱 Charging **{int(total / 0.008)} smartphones**")
            st.write(f"🚗 Avoiding **{int(total / 0.9)} miles driven**")
            st.write(f"🌳 Equivalent to **{round(total / 48, 2)} trees planted for a year**")

    # ---------- SETTINGS ----------
    with tabs[3]:
        st.write(f"Logged in as **{username}**")
        if st.button("Logout"):
            st.session_state.logged_in = False
            st.session_state.username = ""
            st.rerun()
