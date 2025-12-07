# app.py - Production-ready: Supabase auth + Postgres storage + guest migration fallback
import os
import json
import hashlib
import random
from datetime import datetime, date, timedelta
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

# Optional: load .env locally
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# Try to import supabase client (optional fallback)
USE_SUPABASE = False
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
if SUPABASE_URL and SUPABASE_ANON_KEY:
    try:
        from supabase import create_client, Client
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
        USE_SUPABASE = True
    except Exception as e:
        # supabase not installed or init failed; fallback to local
        st.warning("Supabase client not available; falling back to local storage.")
        USE_SUPABASE = False

# --- CONFIG: emission factors (lbs CO2 per unit) ---
EF_MILE = 0.9
EF_SHOWER = 0.05
EF_PLASTIC = 0.1
EF_TAKEOUT = 0.5
EF_LAUNDRY = 2.5

DATA_DIR = "user_data"
USERS_FILE = "users.json"
os.makedirs(DATA_DIR, exist_ok=True)

# ---------- Helper functions for local fallback ----------
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def load_users_local() -> dict:
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def save_users_local(users: dict):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)

def get_user_file_local(username: str) -> str:
    safe_name = username.replace("/", "_")
    return os.path.join(DATA_DIR, f"{safe_name}_data.csv")

# Friendly guest name generator
ADJECTIVES = ["green", "bright", "calm", "gentle", "blue", "solar", "fresh", "kind", "happy", "wild"]
NOUNS = ["sun", "leaf", "brook", "breeze", "sprout", "planet", "meadow", "oak", "harbor", "field"]
def gen_friendly_guest_local(existing_users: dict) -> str:
    def suffix(): return str(random.randint(100, 999))
    for _ in range(200):
        name = f"{random.choice(ADJECTIVES)}-{random.choice(NOUNS)}-{suffix()}"
        key = f"guest-{name}"
        if key not in existing_users:
            return key
    return f"guest-anon-{random.randint(1000,9999)}"

# ---------- CO2 calculation ----------
def calculate_co2_savings(entry: dict, baseline: dict, entry_type: str) -> float:
    miles_saving = max(baseline.get("miles", 0) - entry.get("miles", 0), 0) * EF_MILE
    shower_saving = max(baseline.get("shower_minutes", 0) - entry.get("shower_minutes", 0), 0) * EF_SHOWER
    plastic_saving = max(baseline.get("plastic_bottles", 0) - entry.get("plastic_bottles", 0), 0) * EF_PLASTIC

    if entry_type == "daily":
        return miles_saving + shower_saving + plastic_saving

    takeout_saving = max(baseline.get("takeout_meals", 0) - entry.get("takeout_meals", 0), 0) * EF_TAKEOUT
    laundry_saving = max(baseline.get("laundry_loads", 0) - entry.get("laundry_loads", 0), 0) / 7 * EF_LAUNDRY

    return miles_saving + shower_saving + plastic_saving + takeout_saving + laundry_saving

# ---------- Supabase helpers ----------
def supabase_get_profile_by_username(username: str):
    if not USE_SUPABASE: 
        return None
    resp = supabase.table("profiles").select("*").eq("username", username).limit(1).execute()
    if resp.error or not resp.data:
        return None
    return resp.data[0]

def supabase_create_profile(username: str, baseline: dict, is_guest: bool):
    if not USE_SUPABASE:
        return None
    data = {
        "username": username,
        "baseline": baseline,
        "is_guest": is_guest
    }
    resp = supabase.table("profiles").insert(data).execute()
    return resp.data[0] if not resp.error else None

def supabase_insert_entry(profile_id: str, entry: dict):
    if not USE_SUPABASE:
        return None
    payload = {**entry, "profile_id": profile_id}
    resp = supabase.table("entries").insert(payload).execute()
    return resp

def supabase_get_entries(profile_id: str):
    if not USE_SUPABASE:
        return []
    resp = supabase.table("entries").select("*").eq("profile_id", profile_id).order("date", {"ascending": False}).execute()
    if resp.error: return []
    return resp.data

def supabase_get_leaderboard(limit=50):
    if not USE_SUPABASE:
        return []
    # We'll fetch entries aggregated by profile_id
    q = """
    select p.username, coalesce(sum(e.co2_saved),0) as total
    from profiles p
    left join entries e on e.profile_id = p.id
    where p.is_guest = false
    group by p.username
    order by total desc
    limit %s;
    """ % limit
    resp = supabase.rpc("sql", {"q": q}).execute() if hasattr(supabase, "rpc") else None
    # If RPC not available fallback to client-side compute (inefficient)
    if resp and not resp.error and resp.data:
        return resp.data
    # Fallback simple approach
    profiles = supabase.table("profiles").select("*").eq("is_guest", False).execute().data
    results = []
    for p in profiles:
        total = sum([float(e.get("co2_saved",0) or 0) for e in supabase_get_entries(p["id"])])
        results.append((p["username"], total))
    results.sort(key=lambda x: x[1], reverse=True)
    return results

# ---------- Streamlit app ----------
st.set_page_config(page_title="Sustainability Tracker", layout="wide")
st.title("🌱 Sustainability Tracker")

# session state defaults
st.session_state.setdefault("logged_in", False)
st.session_state.setdefault("guest", False)
st.session_state.setdefault("username", "")
st.session_state.setdefault("profile_id", None)  # supabase profile id if logged in
st.session_state.setdefault("local_users", load_users_local())

# daily rerun guard
if "last_day" not in st.session_state:
    st.session_state["last_day"] = date.today()
if st.session_state["last_day"] != date.today():
    st.session_state["last_day"] = date.today()
    st.rerun()

# Onboarding
if not st.session_state["logged_in"] and not st.session_state["guest"]:
    st.markdown("## 🌍 Try the app quickly — no account required")
    st.write("---")
    c1,c2,c3 = st.columns([1,1,1])
    with c1:
        if st.button("Continue as Guest", use_container_width=True):
            if USE_SUPABASE:
                # generate friendly guest with collision check in db
                attempt = 0
                while attempt < 50:
                    candidate = f"guest-{random.choice(ADJECTIVES)}-{random.choice(NOUNS)}-{random.randint(100,999)}"
                    if not supabase_get_profile_by_username(candidate):
                        profile = supabase_create_profile(candidate, {
                            "miles":5.0,"shower_minutes":10.0,
                            "plastic_bottles":2,"takeout_meals":3,"laundry_loads":3
                        }, is_guest=True)
                        if profile:
                            st.session_state["guest"] = True
                            st.session_state["username"] = candidate
                            st.session_state["profile_id"] = profile["id"]
                            st.rerun()
                        break
                    attempt += 1
                # fallback
                if not st.session_state.get("guest"):
                    st.error("Could not create guest on server; try again.")
            else:
                users = load_users_local()
                guest = gen_friendly_guest_local(users)
                users[guest] = {"password": None, "baseline": {"miles":5.0,"shower_minutes":10.0,"plastic_bottles":2,"takeout_meals":3,"laundry_loads":3}, "is_guest": True}
                save_users_local(users)
                st.session_state["guest"] = True
                st.session_state["username"] = guest
                st.rerun()

    with c2:
        st.subheader("🔓 Log In")
        if USE_SUPABASE:
            # Supabase-auth flow (email/password)
            with st.form("login_form"):
                email = st.text_input("Email", key="login_email")
                password = st.text_input("Password", type="password", key="login_pwd")
                login_sub = st.form_submit_button("Login / Sign In")
            if login_sub:
                try:
                    user = supabase.auth.sign_in({"email": email, "password": password})
                    if user and user.user:
                        # we have a supabase auth user
                        # find or create profile row
                        profile = supabase_get_profile_by_username(email) or supabase_create_profile(email, {"miles":5.0,"shower_minutes":10.0,"plastic_bottles":2,"takeout_meals":3,"laundry_loads":3}, is_guest=False)
                        st.session_state["logged_in"] = True
                        st.session_state["username"] = profile["username"]
                        st.session_state["profile_id"] = profile["id"]
                        st.rerun()
                    else:
                        st.error("Login failed.")
                except Exception as e:
                    st.error("Login error: " + str(e))
        else:
            with st.form("login_form_local"):
                username = st.text_input("Username", key="login_local_username")
                password = st.text_input("Password", type="password", key="login_local_password")
                sub = st.form_submit_button("Login")
            if sub:
                users = load_users_local()
                if username in users and users[username].get("password") == hash_password(password):
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = username
                    st.rerun()
                else:
                    st.error("Invalid local login")

    with c3:
        st.subheader("🆕 Create Account")
        if USE_SUPABASE:
            with st.form("create_account_form"):
                email = st.text_input("Email (this becomes your sign-in)", key="create_email")
                password = st.text_input("Password", type="password", key="create_pwd")
                baseline_miles = st.number_input("Miles driven per day", min_value=0.0, value=5.0, key="create_baseline_miles")
                baseline_shower = st.number_input("Shower minutes per day", min_value=0.0, value=10.0, key="create_baseline_shower")
                baseline_plastic = st.number_input("Plastic bottles per day", min_value=0, value=2, key="create_baseline_plastic")
                baseline_takeout = st.number_input("Takeout meals per week", min_value=0, value=3, key="create_baseline_takeout")
                baseline_laundry = st.number_input("Laundry loads per week", min_value=0, value=3, key="create_baseline_laundry")
                create_sub = st.form_submit_button("Create Account & Import Guest Data (if any)")
            if create_sub:
                try:
                    auth_res = supabase.auth.sign_up({"email": email, "password": password})
                    # create profile row
                    profile = supabase_create_profile(email, {"miles":float(baseline_miles),"shower_minutes":float(baseline_shower),"plastic_bottles":int(baseline_plastic),"takeout_meals":int(baseline_takeout),"laundry_loads":int(baseline_laundry)}, is_guest=False)
                    # If there was a guest in this session, migrate local CSV -> supabase entries
                    if st.session_state.get("guest") and st.session_state.get("username"):
                        # migrate local file if exists
                        guest_name = st.session_state["username"]
                        guest_file = get_user_file_local(guest_name)
                        if os.path.exists(guest_file):
                            try:
                                df = pd.read_csv(guest_file)
                                for _, row in df.iterrows():
                                    payload = {
                                        "timestamp": row.get("timestamp"),
                                        "date": str(row.get("date")),
                                        "entry_type": row.get("entry_type"),
                                        "miles": float(row.get("miles")) if not pd.isna(row.get("miles")) else None,
                                        "shower_minutes": float(row.get("shower_minutes")) if not pd.isna(row.get("shower_minutes")) else None,
                                        "plastic_bottles": int(row.get("plastic_bottles")) if not pd.isna(row.get("plastic_bottles")) else None,
                                        "takeout_meals": int(row.get("takeout_meals")) if not pd.isna(row.get("takeout_meals")) else None,
                                        "laundry_loads": int(row.get("laundry_loads")) if not pd.isna(row.get("laundry_loads")) else None,
                                        "co2_saved": float(row.get("co2_saved")) if "co2_saved" in row and not pd.isna(row.get("co2_saved")) else 0.0
                                    }
                                    supabase_insert_entry(profile["id"], payload)
                                # remove local guest file and guest profile local entry
                                try:
                                    os.remove(guest_file)
                                except Exception:
                                    pass
                                users_local = load_users_local()
                                if guest_name in users_local:
                                    del users_local[guest_name]
                                    save_users_local(users_local)
                            except Exception as e:
                                st.warning("Guest migration partially failed: " + str(e))
                    # set session to logged in
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = profile["username"]
                    st.session_state["profile_id"] = profile["id"]
                    st.session_state["guest"] = False
                    st.rerun()
                except Exception as e:
                    st.error("Signup failed: " + str(e))
        else:
            with st.form("create_local_user"):
                new_user = st.text_input("Create a Username", key="create_local_username")
                new_pass = st.text_input("Create a Password", type="password", key="create_local_pwd")
                baseline_miles = st.number_input("Miles driven per day", min_value=0.0, value=5.0, key="create_local_baseline_miles")
                baseline_shower = st.number_input("Shower minutes per day", min_value=0.0, value=10.0, key="create_local_baseline_shower")
                baseline_plastic = st.number_input("Plastic bottles per day", min_value=0, value=2, key="create_local_baseline_plastic")
                baseline_takeout = st.number_input("Takeout meals per week", min_value=0, value=3, key="create_local_baseline_takeout")
                baseline_laundry = st.number_input("Laundry loads per week", min_value=0, value=3, key="create_local_baseline_laundry")
                create_sub = st.form_submit_button("Create Account & Import Guest Data (if any)")
            if create_sub:
                users = load_users_local()
                if new_user in users:
                    st.error("Username exists")
                else:
                    users[new_user] = {"password": hash_password(new_pass), "baseline": {"miles":float(baseline_miles),"shower_minutes":float(baseline_shower),"plastic_bottles":int(baseline_plastic),"takeout_meals":int(baseline_takeout),"laundry_loads":int(baseline_laundry)}, "is_guest": False}
                    save_users_local(users)
                    # migrate guest CSV if present
                    if st.session_state.get("guest") and st.session_state.get("username"):
                        guest_file = get_user_file_local(st.session_state["username"])
                        if os.path.exists(guest_file):
                            new_file = get_user_file_local(new_user)
                            try:
                                os.replace(guest_file, new_file)
                            except Exception:
                                pass
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = new_user
                    st.session_state["guest"] = False
                    st.rerun()

# Main app view (guest or logged-in)
else:
    # Refresh users/profile
    username = st.session_state.get("username", "")
    profile_id = st.session_state.get("profile_id", None)
    # Load baseline either from supabase profile or local users.json
    if USE_SUPABASE and profile_id:
        prof = supabase.table("profiles").select("*").eq("id", profile_id).limit(1).execute().data[0]
        baseline = prof.get("baseline", {"miles":5.0,"shower_minutes":10.0,"plastic_bottles":2,"takeout_meals":3,"laundry_loads":3})
        is_guest_profile = prof.get("is_guest", True)
    else:
        users_local = load_users_local()
        prof = users_local.get(username, None)
        baseline = prof.get("baseline") if prof else {"miles":5.0,"shower_minutes":10.0,"plastic_bottles":2,"takeout_meals":3,"laundry_loads":3}
        is_guest_profile = prof.get("is_guest", True) if prof else False

    has_daily = has_weekly = False
    # For simplicity, we'll check last entries locally or in supabase
    if USE_SUPABASE and profile_id:
        entries = supabase_get_entries(profile_id)
        df_entries = pd.DataFrame(entries) if entries else pd.DataFrame()
        if not df_entries.empty:
            df_entries["date"] = pd.to_datetime(df_entries["date"]).dt.date
            last_daily = df_entries[df_entries["entry_type"]=="daily"]["date"].max() if not df_entries[df_entries["entry_type"]=="daily"].empty else None
            has_daily = (last_daily == date.today())
            last_weekly = df_entries[df_entries["entry_type"]=="weekly"]["date"].max() if not df_entries[df_entries["entry_type"]=="weekly"].empty else None
            has_weekly = (last_weekly and last_weekly.isocalendar().week == date.today().isocalendar().week)
    else:
        # local CSV
        path = get_user_file_local(username)
        if os.path.exists(path):
            try:
                dfl = pd.read_csv(path)
                if "date" in dfl.columns:
                    dfl["date"] = pd.to_datetime(dfl["date"]).dt.date
                    last_daily = dfl[dfl["entry_type"]=="daily"]["date"].max() if not dfl[dfl["entry_type"]=="daily"].empty else None
                    has_daily = (last_daily == date.today())
                    last_weekly = dfl[dfl["entry_type"]=="weekly"]["date"].max() if not dfl[dfl["entry_type"]=="weekly"].empty else None
                    has_weekly = (last_weekly and last_weekly.isocalendar().week == date.today().isocalendar().week)
            except Exception:
                pass

    tabs = st.tabs(["Daily Tracker","Weekly Tracker","Dashboard","Leaderboard","Settings"])

    # Daily
    with tabs[0]:
        st.subheader("Daily Tracker")
        st.info("Baseline values help measure how much CO₂ you reduce — update them to match your typical habits!")
        with st.expander("View / Edit baseline values"):
            b_m = st.number_input("Miles driven per day (baseline)", min_value=0.0, value=float(baseline.get("miles",5.0)), key="b_m")
            b_s = st.number_input("Shower minutes per day (baseline)", min_value=0.0, value=float(baseline.get("shower_minutes",10.0)), key="b_s")
            b_p = st.number_input("Plastic bottles per day (baseline)", min_value=0, value=int(baseline.get("plastic_bottles",2)), key="b_p")
            b_t = st.number_input("Takeout meals per week (baseline)", min_value=0, value=int(baseline.get("takeout_meals",3)), key="b_t")
            b_l = st.number_input("Laundry loads per week (baseline)", min_value=0, value=int(baseline.get("laundry_loads",3)), key="b_l")
            if st.button("Save baseline changes"):
                new_baseline = {"miles":float(b_m),"shower_minutes":float(b_s),"plastic_bottles":int(b_p),"takeout_meals":int(b_t),"laundry_loads":int(b_l)}
                if USE_SUPABASE and profile_id:
                    supabase.table("profiles").update({"baseline": new_baseline}).eq("id", profile_id).execute()
                    st.success("Baseline saved to server.")
                else:
                    users_local = load_users_local()
                    if username in users_local:
                        users_local[username]["baseline"] = new_baseline
                        save_users_local(users_local)
                        st.success("Baseline saved locally.")
                    else:
                        st.error("Could not save baseline.")
                st.rerun()

        if has_daily:
            st.success("You already submitted today's entry! Come back tomorrow.")
        else:
            with st.form("daily_form"):
                miles = st.number_input("Miles driven today", min_value=0.0, value=float(baseline.get("miles",5.0)))
                shower = st.number_input("Shower minutes today", min_value=0.0, value=float(baseline.get("shower_minutes",10.0)))
                plastic = st.number_input("Plastic bottles used today", min_value=0, value=int(baseline.get("plastic_bottles",2)))
                submitted = st.form_submit_button("Save Daily Entry")
            if submitted:
                entry = {
                    "timestamp": datetime.now().isoformat(),
                    "date": date.today().isoformat(),
                    "entry_type": "daily",
                    "miles": float(miles),
                    "shower_minutes": float(shower),
                    "plastic_bottles": int(plastic),
                    "takeout_meals": None,
                    "laundry_loads": None,
                    "co2_saved": calculate_co2_savings({"miles":float(miles),"shower_minutes":float(shower),"plastic_bottles":int(plastic)}, baseline, "daily")
                }
                if USE_SUPABASE and profile_id:
                    supabase_insert_entry(profile_id, entry)
                else:
                    local_file = get_user_file_local(username)
                    # append to CSV
                    df_new = pd.DataFrame([entry])
                    if os.path.exists(local_file):
                        try:
                            df_old = pd.read_csv(local_file)
                            df_concat = pd.concat([df_old, df_new], ignore_index=True)
                        except Exception:
                            df_concat = df_new
                    else:
                        df_concat = df_new
                    df_concat.to_csv(local_file, index=False)
                st.success("Daily entry saved!")
                st.rerun()

    # Weekly
    with tabs[1]:
        st.subheader("Weekly Tracker")
        st.info("Submit once per week for laundry & takeout.")
        if has_weekly:
            st.success("You already submitted this week's entry!")
        else:
            weekly_takeout = st.number_input("Takeout meals this week", min_value=0, value=int(baseline.get("takeout_meals",3)))
            weekly_laundry = st.number_input("Laundry loads this week", min_value=0, value=int(baseline.get("laundry_loads",3)))
            if st.button("Save Weekly Entry"):
                entry = {
                    "timestamp": datetime.now().isoformat(),
                    "date": date.today().isoformat(),
                    "entry_type": "weekly",
                    "miles": baseline.get("miles",5.0),
                    "shower_minutes": baseline.get("shower_minutes",10.0),
                    "plastic_bottles": baseline.get("plastic_bottles",2),
                    "takeout_meals": int(weekly_takeout),
                    "laundry_loads": int(weekly_laundry),
                    "co2_saved": calculate_co2_savings({"miles":baseline.get("miles",5.0),"shower_minutes":baseline.get("shower_minutes",10.0),"plastic_bottles":baseline.get("plastic_bottles",2),"takeout_meals":int(weekly_takeout),"laundry_loads":int(weekly_laundry)}, baseline, "weekly")
                }
                if USE_SUPABASE and profile_id:
                    supabase_insert_entry(profile_id, entry)
                else:
                    local_file = get_user_file_local(username)
                    df_new = pd.DataFrame([entry])
                    if os.path.exists(local_file):
                        try:
                            df_old = pd.read_csv(local_file)
                            df_concat = pd.concat([df_old, df_new], ignore_index=True)
                        except Exception:
                            df_concat = df_new
                    else:
                        df_concat = df_new
                    df_concat.to_csv(local_file, index=False)
                st.success("Weekly entry saved!")
                st.rerun()

    # Dashboard
    with tabs[2]:
        st.subheader("Dashboard")
        # Get entries from supabase or local
        if USE_SUPABASE and profile_id:
            entries = supabase_get_entries(profile_id)
            df = pd.DataFrame(entries) if entries else pd.DataFrame()
        else:
            local_file = get_user_file_local(username)
            if os.path.exists(local_file):
                try:
                    df = pd.read_csv(local_file)
                except Exception:
                    df = pd.DataFrame()
            else:
                df = pd.DataFrame()
        if df.empty:
            st.info("No entries yet! Start by adding a daily or weekly entry.")
        else:
            if "co2_saved" not in df.columns:
                df["co2_saved"] = 0.0
            st.metric("Total CO₂ Saved (lbs)", round(float(df["co2_saved"].sum()), 2))
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
            df_week = df[df["date"] >= (datetime.today() - timedelta(days=6))]
            if not df_week.empty:
                fig, ax = plt.subplots()
                ax.plot(df_week["date"], df_week["co2_saved"], marker="o")
                ax.set_xlabel("Date")
                ax.set_ylabel("CO₂ Saved (lbs)")
                ax.set_title("CO₂ Savings (Last 7 Days)")
                st.pyplot(fig)
            st.write("### All Entries")
            st.dataframe(df.sort_values("date", ascending=False))

    # Leaderboard
    with tabs[3]:
        st.subheader("Leaderboard")
        if USE_SUPABASE:
            # server-side aggregation would be better; this is a simple client-side approach
            profiles_resp = supabase.table("profiles").select("*").eq("is_guest", False).execute()
            leaderboard = []
            if not profiles_resp.error and profiles_resp.data:
                for p in profiles_resp.data:
                    total = sum([float(e.get("co2_saved",0) or 0) for e in supabase_get_entries(p["id"])])
                    leaderboard.append((p["username"], total))
            leaderboard.sort(key=lambda x: x[1], reverse=True)
        else:
            users_local = load_users_local()
            leaderboard = []
            for uname, prof in users_local.items():
                if prof.get("is_guest", False): continue
                f = get_user_file_local(uname)
                if os.path.exists(f):
                    try:
                        df_temp = pd.read_csv(f)
                        total = float(df_temp["co2_saved"].sum()) if "co2_saved" in df_temp.columns else 0.0
                        leaderboard.append((uname, total))
                    except Exception:
                        continue
            leaderboard.sort(key=lambda x: x[1], reverse=True)

        st.write("### Top Users")
        if not leaderboard:
            st.info("No registered users with entries yet. Create an account and be first!")
        else:
            for i, (u, total) in enumerate(leaderboard, start=1):
                st.write(f"{i}. **{u}** — {round(total,2)} lbs CO₂ saved")

        # Keep upgrade CTA for guest
        if is_guest_profile:
            st.info("Create an account to appear on the leaderboard and keep progress across devices!")
            if st.button("Create Account & Save Progress"):
                st.rerun()  # will show onboarding create account form

    # Settings
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
                # Export either supabase data or local csv
                if USE_SUPABASE and profile_id:
                    entries = supabase_get_entries(profile_id)
                    df = pd.DataFrame(entries) if entries else pd.DataFrame()
                    csv = df.to_csv(index=False).encode()
                    st.download_button("Download CSV", data=csv, file_name=f"{username}_data.csv", mime="text/csv")
                else:
                    local_file = get_user_file_local(username)
                    if os.path.exists(local_file):
                        with open(local_file, "rb") as f:
                            st.download_button("Download CSV", data=f, file_name=os.path.basename(local_file), mime="text/csv")
                    else:
                        st.info("No data file to export.")

        with col_b:
            if st.button("Delete my local data"):
                # Deletes local CSV or server entries (be careful)
                if USE_SUPABASE and profile_id:
                    # delete entries for this profile
                    try:
                        supabase.table("entries").delete().eq("profile_id", profile_id).execute()
                        st.success("Server entries deleted.")
                    except Exception:
                        st.error("Failed to delete server entries.")
                else:
                    local_file = get_user_file_local(username)
                    if os.path.exists(local_file):
                        try:
                            os.remove(local_file)
                            st.success("Local file deleted.")
                        except Exception:
                            st.error("Could not delete file.")

        if st.button("Logout"):
            st.session_state["logged_in"] = False
            st.session_state["guest"] = False
            st.session_state["username"] = ""
            st.session_state["profile_id"] = None
            st.rerun()
