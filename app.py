import streamlit as st
import pandas as pd
import os
from datetime import datetime, date, timedelta
import matplotlib.pyplot as plt
import hashlib
import json
import random

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
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE, "r") as f:
        return json.load(f)

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)

def get_user_file(username):
    """
    Filenames:
    - For normal user: {username}_data.csv
    - For guest user: guest-<friendlyname>_data.csv (username already contains that friendly name)
    """
    return os.path.join(DATA_DIR, f"{username}_data.csv")

# ----------------- Friendly Guest Name Generator -----------------
ADJECTIVES = [
    "green", "bright", "calm", "gentle", "blue", "solar", "fresh", "kind", "happy", "wild"
]
NOUNS = [
    "sun", "leaf", "brook", "breeze", "sprout", "planet", "meadow", "oak", "harbor", "field"
]

def gen_friendly_guest(existing_users):
    suffix = lambda: str(random.randint(100, 999))
    for _ in range(50):
        name = f"{random.choice(ADJECTIVES)}-{random.choice(NOUNS)}-{suffix()}"
        key = f"guest-{name}"
        if key not in existing_users:
            return key
    # fallback
    return f"guest-anon-{random.randint(1000,9999)}"

# ---------------- FIXED DAILY/WEEKLY CHECK ----------------
def get_log_status(username):
    today = date.today()
    file_path = get_user_file(username)

    if not os.path.exists(file_path):
        return False, False

    df = pd.read_csv(file_path)
    # ensure date column exists and proper dtype
    if "date" not in df.columns:
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
        # Compare ISO week numbers
        try:
            has_weekly = (last_weekly.isocalendar().week == today.isocalendar().week)
        except Exception:
            has_weekly = False

    return has_daily, has_weekly

def log_entry(username, entry):
    file_path = get_user_file(username)

    if not os.path.exists(file_path):
        df_init = pd.DataFrame(columns=[
            "timestamp", "date", "entry_type",
            "miles", "shower_minutes", "plastic_bottles",
            "takeout_meals", "laundry_loads",
            "co2_saved"
        ])
        df_init.to_csv(file_path, index=False)

    df = pd.read_csv(file_path)
    df = pd.concat([df, pd.DataFrame([entry])], ignore_index=True)
    df.to_csv(file_path, index=False)

def calculate_co2_savings(entry, baseline, entry_type):
    miles_saving = max(baseline.get("miles", 0) - entry.get("miles", 0), 0) * EF_MILE
    shower_saving = max(baseline.get("shower_minutes", 0) - entry.get("shower_minutes", 0), 0) * EF_SHOWER
    plastic_saving = max(baseline.get("plastic_bottles", 0) - entry.get("plastic_bottles", 0), 0) * EF_PLASTIC

    if entry_type == "daily":
        return miles_saving + shower_saving + plastic_saving

    takeout_saving = max(baseline.get("takeout_meals", 0) - entry.get("takeout_meals", 0), 0) * EF_TAKEOUT
    laundry_saving = max(baseline.get("laundry_loads", 0) - entry.get("laundry_loads", 0), 0) / 7 * EF_LAUNDRY

    return miles_saving + shower_saving + plastic_saving + takeout_saving + laundry_saving

# ----------------- Streamlit Setup -----------------
st.set_page_config(page_title="Sustainability Tracker", layout="wide")
st.title("🌱 Sustainability Tracker")

if "last_day" not in st.session_state:
    st.session_state["last_day"] = date.today()

if st.session_state["last_day"] != date.today():
    st.session_state["last_day"] = date.today()
    st.experimental_rerun()

# initialize session state flags
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "guest" not in st.session_state:
    st.session_state["guest"] = False
if "username" not in st.session_state:
    st.session_state["username"] = ""
if "guest_id" not in st.session_state:
    st.session_state["guest_id"] = ""
if "baseline_temp" not in st.session_state:
    st.session_state["baseline_temp"] = None

users = load_users()

# ---------------- Welcome / Onboarding (Guest + Login + Signup) ----------------
if not st.session_state["logged_in"] and not st.session_state["guest"]:
    st.markdown("## 🌍 Measure Your Real Impact — No account required")
    st.markdown(
        "**Try the app quickly as a guest, or create an account to save progress across devices.**"
    )
    st.write("---")

    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        if st.button("Continue as Guest", use_container_width=True):
            # create friendly guest id
            guest_key = gen_friendly_guest(users)
            # create a minimal guest user entry in users.json so baseline can be stored consistently
            users[guest_key] = {
                "password": None,
                "baseline": {
                    "miles": 5.0,
                    "shower_minutes": 10.0,
                    "plastic_bottles": 2,
                    "takeout_meals": 3,
                    "laundry_loads": 3
                },
                "is_guest": True,
                "created_at": datetime.now().isoformat()
            }
            save_users(users)

            st.session_state["guest"] = True
            st.session_state["username"] = guest_key
            st.session_state["guest_id"] = guest_key
            st.session_state["baseline_temp"] = users[guest_key]["baseline"]
            st.experimental_rerun()

    with col2:
        st.subheader("🔓 Log In")
        with st.form("login_form"):
            username = st.text_input("Username", key="login_username")
            password = st.text_input("Password", type="password", key="login_password")
            login_sub = st.form_submit_button("Login", use_container_width=True)
        if login_sub:
            if username in users and users[username].get("password") == hash_password(password):
                st.session_state["logged_in"] = True
                st.session_state["guest"] = False
                st.session_state["username"] = username
                st.experimental_rerun()
            else:
                st.error("Incorrect username or password.")

    with col3:
        st.subheader("🆕 Create Account")
        with st.form("create_account_form"):
            new_user = st.text_input("Create a Username", key="create_username")
            new_pass = st.text_input("Create a Password", type="password", key="create_password")
            st.write("### Set Your Baseline Habits (you can edit later)")
            baseline_miles = st.number_input("Miles driven per day", min_value=0.0, value=5.0, key="create_baseline_miles")
            baseline_shower = st.number_input("Shower minutes per day", min_value=0.0, value=10.0, key="create_baseline_shower")
            baseline_plastic = st.number_input("Plastic bottles per day", min_value=0, value=2, key="create_baseline_plastic")
            baseline_takeout = st.number_input("Takeout meals per *week*", min_value=0, value=3, key="create_baseline_takeout")
            baseline_laundry = st.number_input("Laundry loads per week", min_value=0, value=3, key="create_baseline_laundry")
            create_sub = st.form_submit_button("Create Account & Import Guest Data (if any)", use_container_width=True)

        if create_sub:
            if new_user in users:
                st.error("Username already exists.")
            else:
                # If user was previously a guest in this session, migrate that guest data
                if st.session_state.get("guest") and st.session_state.get("guest_id"):
                    guest_key = st.session_state["guest_id"]
                    # rename file if exists
                    guest_file = get_user_file(guest_key)
                    new_file = get_user_file(new_user)
                    if os.path.exists(guest_file):
                        os.replace(guest_file, new_file)

                    # copy guest profile into new user and remove guest entry
                    users[new_user] = {
                        "password": hash_password(new_pass),
                        "baseline": {
                            "miles": baseline_miles,
                            "shower_minutes": baseline_shower,
                            "plastic_bottles": baseline_plastic,
                            "takeout_meals": baseline_takeout,
                            "laundry_loads": baseline_laundry
                        },
                        "is_guest": False,
                        "created_at": datetime.now().isoformat()
                    }
                    # Remove guest record if present
                    if guest_key in users:
                        try:
                            del users[guest_key]
                        except KeyError:
                            pass
                    save_users(users)

                    st.success("Account created and guest data migrated! Logging you in...")
                    st.session_state["logged_in"] = True
                    st.session_state["guest"] = False
                    st.session_state["username"] = new_user
                    st.session_state["guest_id"] = ""
                    st.experimental_rerun()

                else:
                    # fresh account
                    users[new_user] = {
                        "password": hash_password(new_pass),
                        "baseline": {
                            "miles": baseline_miles,
                            "shower_minutes": baseline_shower,
                            "plastic_bottles": baseline_plastic,
                            "takeout_meals": baseline_takeout,
                            "laundry_loads": baseline_laundry
                        },
                        "is_guest": False,
                        "created_at": datetime.now().isoformat()
                    }
                    save_users(users)
                    st.success("Account created! Logging you in...")
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = new_user
                    st.experimental_rerun()

# ----------------- LOGGED-IN OR GUEST VIEW --------------------
else:
    # Ensure latest users loaded
    users = load_users()
    username = st.session_state["username"]

    # If for some reason username isn't set, force a fresh state
    if not username:
        st.session_state["logged_in"] = False
        st.session_state["guest"] = False
        st.experimental_rerun()

    # Determine baseline: from users dict (works for both registered and guest since we stored baseline there)
    if username in users:
        baseline = users[username]["baseline"]
        is_guest_profile = users[username].get("is_guest", False)
    else:
        # Fallback default baseline
        baseline = {
            "miles": 5.0,
            "shower_minutes": 10.0,
            "plastic_bottles": 2,
            "takeout_meals": 3,
            "laundry_loads": 3
        }
        is_guest_profile = True

    has_daily, has_weekly = get_log_status(username)

    tabs = st.tabs([
        "Daily Tracker",
        "Weekly Tracker",
        "Dashboard",
        "Leaderboard",
        "Settings"
    ])

    # ---- DAILY TRACKER ----
    with tabs[0]:
        st.subheader("Daily Tracker")
        st.info("Submit habits **for the entire day**. One entry allowed per day.")

        if is_guest_profile:
            st.warning("You're currently using the app as a guest. Create an account to keep progress across devices!")

        # Allow guest to edit baseline for their session / profile
        with st.expander("View / Edit baseline values"):
            b_m = st.number_input("Miles driven per day (baseline)", min_value=0.0, value=float(baseline["miles"]), key="edit_baseline_miles")
            b_s = st.number_input("Shower minutes per day (baseline)", min_value=0.0, value=float(baseline["shower_minutes"]), key="edit_baseline_shower")
            b_p = st.number_input("Plastic bottles per day (baseline)", min_value=0, value=int(baseline["plastic_bottles"]), key="edit_baseline_plastic")
            b_t = st.number_input("Takeout meals per week (baseline)", min_value=0, value=int(baseline["takeout_meals"]), key="edit_baseline_takeout")
            b_l = st.number_input("Laundry loads per week (baseline)", min_value=0, value=int(baseline["laundry_loads"]), key="edit_baseline_laundry")
            if st.button("Save baseline changes"):
                # persist baseline to users.json (works for guests too)
                users = load_users()
                if username in users:
                    users[username]["baseline"] = {
                        "miles": float(b_m),
                        "shower_minutes": float(b_s),
                        "plastic_bottles": int(b_p),
                        "takeout_meals": int(b_t),
                        "laundry_loads": int(b_l)
                    }
                    save_users(users)
                    st.success("Baseline saved.")
                    st.experimental_rerun()
                else:
                    st.error("Unable to save baseline (user not found).")

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
                    "entry_type": "daily",
                    "miles": miles,
                    "shower_minutes": shower,
                    "plastic_bottles": plastic,
                    "takeout_meals": None,
                    "laundry_loads": None,
                }
                entry["co2_saved"] = calculate_co2_savings(entry, baseline, "daily")
                log_entry(username, entry)
                st.success("Daily entry saved!")
                st.experimental_rerun()

    # ---- WEEKLY TRACKER ----
    with tabs[1]:
        st.subheader("Weekly Tracker")
        st.info("Submit once per week for laundry + takeout.")

        if has_weekly:
            st.success("You already submitted this week's entry!")
        else:
            weekly_takeout = st.number_input("Takeout meals this week", min_value=0, value=baseline["takeout_meals"])
            weekly_laundry = st.number_input("Laundry loads this week", min_value=0, value=baseline["laundry_loads"])

            if st.button("Save Weekly Entry"):
                entry = {
                    "timestamp": datetime.now().isoformat(),
                    "date": date.today().isoformat(),
                    "entry_type": "weekly",
                    "miles": baseline["miles"],
                    "shower_minutes": baseline["shower_minutes"],
                    "plastic_bottles": baseline["plastic_bottles"],
                    "takeout_meals": int(weekly_takeout),
                    "laundry_loads": int(weekly_laundry),
                }
                entry["co2_saved"] = calculate_co2_savings(entry, baseline, "weekly")
                log_entry(username, entry)
                st.success("Weekly entry saved!")
                st.experimental_rerun()

    # ---- DASHBOARD ----
    with tabs[2]:
        st.subheader("Dashboard")
        file_path = get_user_file(username)

        if os.path.exists(file_path):
            df = pd.read_csv(file_path)
            if "co2_saved" not in df.columns:
                df["co2_saved"] = 0.0
            st.metric("Total CO₂ Saved (lbs)", round(df["co2_saved"].sum(), 2))

            df["date"] = pd.to_datetime(df["date"])
            df_week = df[df["date"] >= (datetime.today() - timedelta(days=6))]

            if not df_week.empty:
                fig, ax = plt.subplots()
                ax.plot(df_week["date"], df_week["co2_saved"], marker="o")
                ax.set_xlabel("Date")
                ax.set_ylabel("CO₂ Saved (lbs)")
                ax.set_title("CO₂ Savings (Last 7 Days)")
                st.pyplot(fig)
            else:
                st.info("Not enough recent data to show chart.")

            st.write("### All Entries")
            st.dataframe(df.sort_values("date", ascending=False))
        else:
            st.info("No entries yet! Start by adding a daily or weekly entry.")

    # ---- LEADERBOARD ----
    with tabs[3]:
        st.subheader("Leaderboard")
        leaderboard = []
        users = load_users()
        for user_key, profile in users.items():
            # Exclude guests from leaderboard
            if profile.get("is_guest", False):
                continue
            file = get_user_file(user_key)
            if os.path.exists(file):
                df_temp = pd.read_csv(file)
                total_saved = df_temp["co2_saved"].sum() if "co2_saved" in df_temp.columns else 0
                leaderboard.append((user_key, total_saved))

        leaderboard = sorted(leaderboard, key=lambda x: x[1], reverse=True)

        st.write("### Top Users")
        if not leaderboard:
            st.info("No registered users with entries yet. Create an account and be first!")
        else:
            for i, (u, total) in enumerate(leaderboard, start=1):
                st.write(f"{i}. **{u}** — {round(total,2)} lbs CO₂ saved")

        if is_guest_profile:
            st.info("Create an account to appear on the leaderboard and keep your progress across devices!")
            if st.button("Create Account & Save Progress"):
                # Show signup fields inline for quick upgrade (simple flow)
                with st.form("upgrade_form"):
                    up_user = st.text_input("Choose a username", key="upgrade_username")
                    up_pass = st.text_input("Choose a password", type="password", key="upgrade_password")
                    submit_upgrade = st.form_submit_button("Create Account & Migrate Data")
                if submit_upgrade:
                    users = load_users()
                    if up_user in users:
                        st.error("Username already exists. Try another.")
                    else:
                        guest_key = username
                        guest_file = get_user_file(guest_key)
                        new_file = get_user_file(up_user)
                        # move data file if exists
                        if os.path.exists(guest_file):
                            os.replace(guest_file, new_file)
                        # copy profile and transform to real account
                        users[up_user] = {
                            "password": hash_password(up_pass),
                            "baseline": users[guest_key]["baseline"],
                            "is_guest": False,
                            "created_at": datetime.now().isoformat()
                        }
                        # remove guest profile
                        if guest_key in users:
                            try:
                                del users[guest_key]
                            except KeyError:
                                pass
                        save_users(users)
                        st.success("Account created and guest data migrated! Logging you in...")
                        st.session_state["logged_in"] = True
                        st.session_state["guest"] = False
                        st.session_state["username"] = up_user
                        st.session_state["guest_id"] = ""
                        st.experimental_rerun()

    # ---- SETTINGS ----
    with tabs[4]:
        st.subheader("Settings")
        st.write(f"Signed in as: **{username}** {'(guest)' if is_guest_profile else ''}")

        if is_guest_profile:
            st.caption("Guest accounts are stored locally. Create a permanent account to access your data on other devices.")
        else:
            st.caption("Thanks for creating an account — your progress is saved!")

        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("Export my data (.csv)"):
                file_path = get_user_file(username)
                if os.path.exists(file_path):
                    with open(file_path, "rb") as f:
                        data_bytes = f.read()
                    st.download_button(label="Download CSV", data=data_bytes, file_name=os.path.basename(file_path), mime="text/csv")
                else:
                    st.info("No data file to export.")

        with col_b:
            if st.button("Delete my local data"):
                # delete file and user profile if guest; if registered, only delete file (keep account)
                file_path = get_user_file(username)
                if os.path.exists(file_path):
                    os.remove(file_path)
                if is_guest_profile:
                    users = load_users()
                    if username in users:
                        try:
                            del users[username]
                            save_users(users)
                        except Exception:
                            pass
                    st.session_state["logged_in"] = False
                    st.session_state["guest"] = False
                    st.session_state["username"] = ""
                    st.session_state["guest_id"] = ""
                    st.success("Guest data deleted.")
                    st.experimental_rerun()
                else:
                    st.success("Local entries deleted (account still exists).")

        if st.button("Logout"):
            st.session_state["logged_in"] = False
            st.session_state["guest"] = False
            st.session_state["username"] = ""
            st.session_state["guest_id"] = ""
            st.experimental_rerun()
