# app.py
"""
Sustainability Tracker — Full upgraded version with:
- per-user entries saved to data.csv
- per-user persistent weekly goals in users.csv
- demo dataset loader
- weekly goals & progress bar
- streak detection (consecutive days)
- badges/achievements
- daily challenges (bonus)
- leaderboards (weekly & all-time)
- CO2 equivalents (trees, car-miles)
- lightweight visual improvements
"""

import streamlit as st
import pandas as pd
import os
from datetime import datetime, date, timedelta
import matplotlib.pyplot as plt
from dateutil.parser import parse as parse_dt

# ---------------- CONFIG ----------------
DATA_FILE = "data.csv"
USERS_FILE = "users.csv"

# Emission factors (lbs CO2 per unit) — defensible, approximate values
EF_MILE = 0.9        # lbs CO2 per mile driven
EF_KWH = 0.85        # lbs CO2 per kWh
EF_BOTTLE = 0.1      # lbs CO2 per plastic bottle avoided
EF_BEEF_MEAL = 6.6   # lbs CO2 per beef meal avoided

# Badge thresholds (lbs) — change these names/values if you want
BADGE_THRESHOLDS = {
    "Green Starter": 50,
    "Climate Champion": 200,
    "Carbon Crusher": 500
}

# Default weekly goal (if user doesn't set one)
DEFAULT_WEEKLY_GOAL = 50

st.set_page_config(page_title="Sustainability Tracker", layout="wide")
st.title("🌱 Sustainability Tracker — upgraded")
st.markdown(
    "Track actions, set goals, earn badges, and see real impact equivalents. "
    "All entries are saved on the server in `data.csv`; user goals are stored in `users.csv`."
)

# ---------------- Helpers ----------------
def ensure_files():
    if not os.path.exists(DATA_FILE):
        df_init = pd.DataFrame(columns=[
            "timestamp", "date", "user",
            "miles_avoided", "kwh_saved",
            "bottles_avoided", "beef_meals_avoided",
            "challenge_plastic", "challenge_meatless", "challenge_bike",
            "estimated_co2_lbs"
        ])
        df_init.to_csv(DATA_FILE, index=False)
    if not os.path.exists(USERS_FILE):
        users_init = pd.DataFrame(columns=["user", "weekly_goal"])
        users_init.to_csv(USERS_FILE, index=False)

def load_data():
    ensure_files()
    df = pd.read_csv(DATA_FILE)
    if not df.empty:
        try:
            df['date'] = pd.to_datetime(df['date']).dt.date
        except Exception:
            df['date'] = df['date'].apply(lambda x: parse_dt(x).date() if pd.notna(x) else None)
    return df

def load_users():
    ensure_files()
    users = pd.read_csv(USERS_FILE)
    return users

def save_entry(entry: dict):
    df = load_data()
    new_df = pd.DataFrame([entry])
    df = pd.concat([df, new_df], ignore_index=True)
    df.to_csv(DATA_FILE, index=False)

def upsert_user_goal(user, goal):
    users = load_users()
    if user in users['user'].values:
        users.loc[users['user'] == user, 'weekly_goal'] = float(goal)
    else:
        new = pd.DataFrame([{"user": user, "weekly_goal": float(goal)}])
        users = pd.concat([users, new], ignore_index=True)
    users.to_csv(USERS_FILE, index=False)

def get_user_goal(user):
    users = load_users()
    if user in users['user'].values:
        try:
            val = users.loc[users['user'] == user, 'weekly_goal'].iloc[0]
            return float(val)
        except Exception:
            return DEFAULT_WEEKLY_GOAL
    return DEFAULT_WEEKLY_GOAL

def compute_co2(miles, kwh, bottles, beef_meals):
    co2_miles = miles * EF_MILE
    co2_kwh = kwh * EF_KWH
    co2_bottles = bottles * EF_BOTTLE
    co2_beef = beef_meals * EF_BEEF_MEAL
    total = co2_miles + co2_kwh + co2_bottles + co2_beef
    return total, (co2_miles, co2_kwh, co2_bottles, co2_beef)

def user_weekly_sum(df, user, days=7):
    today = date.today()
    start = today - timedelta(days=days-1)
    mask = (df['date'] >= start) & (df['date'] <= today) & (df['user'] == user)
    return df.loc[mask]['estimated_co2_lbs'].sum()

def user_consecutive_streak(df, user):
    user_df = df[df['user'] == user]
    if user_df.empty:
        return 0
    dates_set = set(user_df['date'].tolist())
    streak = 0
    cur = date.today()
    while cur in dates_set:
        streak += 1
        cur = cur - timedelta(days=1)
    return streak

def badges_for_user(df, user):
    total = df[df['user'] == user]['estimated_co2_lbs'].sum()
    badges = []
    for name, thresh in BADGE_THRESHOLDS.items():
        if total >= thresh:
            badges.append((name, thresh))
    return badges

def co2_equivalents(co2_lbs):
    trees = co2_lbs / 48 if co2_lbs else 0
    miles_eq = co2_lbs / EF_MILE if co2_lbs else 0
    bottles_eq = co2_lbs / EF_BOTTLE if co2_lbs else 0
    return {"trees": trees, "miles": miles_eq, "bottles": bottles_eq}

def load_demo_data():
    """Populate data.csv with a small demo dataset (appends). Useful for showing features."""
    demo_entries = []
    base = date.today() - timedelta(days=6)
    users = ["Alex", "Sam", "Taylor", "Jess"]
    for i in range(7):
        d = base + timedelta(days=i)
        for u in users:
            miles = float((i + 1) * 0.5) if u == "Alex" else float((i % 3) * 1.2)
            kwh = float((i % 2) * 1.0)
            bottles = int((i + 1) % 4)
            beef = int((i + 2) % 3 == 0)
            co2, _ = compute_co2(miles, kwh, bottles, beef)
            demo_entries.append({
                "timestamp": datetime.now().isoformat(),
                "date": d.isoformat(),
                "user": u,
                "miles_avoided": miles,
                "kwh_saved": kwh,
                "bottles_avoided": bottles,
                "beef_meals_avoided": beef,
                "challenge_plastic": False,
                "challenge_meatless": False,
                "challenge_bike": False,
                "estimated_co2_lbs": float(co2)
            })
    df = load_data()
    df_demo = pd.DataFrame(demo_entries)
    df = pd.concat([df, df_demo], ignore_index=True)
    df.to_csv(DATA_FILE, index=False)

# ----------------- UI: Layout -----------------
ensure_files()
left, middle, right = st.columns([1, 1, 1])

with left:
    st.header("📥 Log an entry")
    with st.form("entry_form", clear_on_submit=True):
        entry_date = st.date_input("Date", value=date.today())
        user_name = st.text_input("Your name or initials", value="Anonymous")
        # load user-specific weekly goal if exists
        current_goal = get_user_goal(user_name) if user_name and user_name != "Anonymous" else DEFAULT_WEEKLY_GOAL
        weekly_goal = st.number_input("Set your weekly CO₂ goal (lbs)", min_value=10, value=current_goal, step=5)

        st.markdown("**Enter actions (today)**")
        miles = st.number_input("Miles avoided (or driven less)", min_value=0.0, value=0.0, step=0.1)
        kwh = st.number_input("Electricity saved (kWh)", min_value=0.0, value=0.0, step=0.1)
        bottles = st.number_input("Plastic bottles avoided", min_value=0, value=0, step=1)
        beef_meals = st.number_input("Beef meals avoided", min_value=0, value=0, step=1)

        st.markdown("**Challenges (bonus)**")
        challenge_plastic = st.checkbox("Avoid disposable plastic today")
        challenge_meatless = st.checkbox("Eat 1 meatless meal")
        challenge_bike = st.checkbox("Walk / bike instead of car")

        submit = st.form_submit_button("Save entry")

    if submit:
        # compute base CO2 and add small bonuses for challenges (to encourage)
        total_co2, breakdown = compute_co2(miles, kwh, bottles, beef_meals)
        bonus = 0.0
        if challenge_plastic:
            bonus += 0.1
        if challenge_meatless:
            bonus += 0.5
        if challenge_bike:
            bonus += 0.2
        total_co2 += bonus

        entry = {
            "timestamp": datetime.now().isoformat(),
            "date": entry_date.isoformat(),
            "user": user_name.strip() if user_name.strip() else "Anonymous",
            "miles_avoided": float(miles),
            "kwh_saved": float(kwh),
            "bottles_avoided": int(bottles),
            "beef_meals_avoided": int(beef_meals),
            "challenge_plastic": bool(challenge_plastic),
            "challenge_meatless": bool(challenge_meatless),
            "challenge_bike": bool(challenge_bike),
            "estimated_co2_lbs": float(total_co2)
        }

        try:
            save_entry(entry)
            upsert_user_goal(entry["user"], weekly_goal)  # persist user's weekly goal
            st.success(f"Saved! ✅ Estimated {total_co2:.1f} lbs CO₂ avoided (including bonuses).")
        except Exception as e:
            st.error("Error saving entry: " + str(e))

    st.markdown("---")
    st.write("Need demo data to show features?")
    if st.button("Load demo dataset (adds sample users)"):
        try:
            load_demo_data()
            st.success("Demo data added — refresh dashboard on the right.")
        except Exception as e:
            st.error("Failed to load demo data: " + str(e))

with middle:
    st.header("📊 Quick community metrics")
    df = load_data()
    if df.empty:
        st.info("No entries yet. Add an entry on the left to begin tracking.")
    else:
        total_co2_all = df['estimated_co2_lbs'].sum()
        total_miles_all = df['miles_avoided'].sum()
        total_bottles_all = df['bottles_avoided'].sum()
        col1, col2, col3 = st.columns(3)
        col1.metric("Total CO₂ avoided (lbs)", f"{total_co2_all:.1f}")
        col2.metric("Total miles avoided", f"{total_miles_all:.1f}")
        col3.metric("Total bottles avoided", f"{int(total_bottles_all)}")

        # community last 7 days
        today = date.today()
        week_start = today - timedelta(days=6)
        period = df[df['date'] >= week_start].groupby('date', as_index=False)['estimated_co2_lbs'].sum()
        if not period.empty:
            fig, ax = plt.subplots()
            ax.plot(period['date'].astype(str), period['estimated_co2_lbs'], marker='o')
            ax.set_xlabel("Date")
            ax.set_ylabel("Estimated CO₂ (lbs)")
            ax.set_title("Community CO₂ saved — last 7 days")
            plt.xticks(rotation=45)
            st.pyplot(fig)

with right:
    st.header("👤 Personal dashboard")
    df = load_data()
    if df.empty:
        st.info("No entries yet. Add one to begin.")
    else:
        users = sorted(df['user'].unique().tolist())
        selected_user = st.selectbox("Select user to view", users, index=(0 if users else None))
        if selected_user:
            # load persisted goal
            user_goal = get_user_goal(selected_user)
            st.subheader(f"{selected_user}")
            weekly_sum = user_weekly_sum(df, selected_user, days=7)
            st.write(f"CO₂ saved in last 7 days: **{weekly_sum:.1f} lbs**")
            pct = min(weekly_sum / user_goal, 1.0) if user_goal else 0.0
            st.progress(pct)
            st.write(f"Weekly goal: **{user_goal:.1f} lbs** (stored)")

            # streak
            streak = user_consecutive_streak(df, selected_user)
            st.write(f"🔥 Current logging streak: **{streak} days**")

            # badges
            earned = badges_for_user(df, selected_user)
            st.write("🏅 Badges earned:")
            if earned:
                for name, thresh in earned:
                    st.success(f"{name} — {thresh} lbs")
            else:
                st.write("No badges yet — keep going!")

            # personal timeseries (last 30 days)
            user_df = df[df['user'] == selected_user].copy()
            user_df = user_df.groupby('date', as_index=False)['estimated_co2_lbs'].sum()
            if not user_df.empty:
                fig2, ax2 = plt.subplots()
                ax2.bar(user_df['date'].astype(str), user_df['estimated_co2_lbs'])
                ax2.set_xlabel("Date")
                ax2.set_ylabel("Estimated CO₂ (lbs)")
                ax2.set_title(f"{selected_user} — CO₂ by day (summary)")
                plt.xticks(rotation=45)
                st.pyplot(fig2)

            eq = co2_equivalents(weekly_sum)
            st.write("Equivalent for this week's savings:")
            st.write(f"- ≈ **{eq['trees']:.2f}** trees (annual sequestration equivalent)")
            st.write(f"- ≈ **{eq['miles']:.1f}** car miles avoided")
            st.write(f"- ≈ **{eq['bottles']:.0f}** plastic bottles worth (approx)")

        # Leaderboards
        st.markdown("---")
        st.subheader("🏆 Leaderboards")
        weekly_df = df[(df['date'] >= week_start) & (df['date'] <= today)].groupby('user', as_index=False)['estimated_co2_lbs'].sum()
        weekly_df = weekly_df.sort_values('estimated_co2_lbs', ascending=False).head(10)
        if not weekly_df.empty:
            st.write("Top this week (lbs CO₂ saved):")
            st.table(weekly_df.rename(columns={"estimated_co2_lbs": "weekly_co2_lbs"}).set_index('user'))

        all_time = df.groupby('user', as_index=False)['estimated_co2_lbs'].sum().sort_values('estimated_co2_lbs', ascending=False).head(10)
        if not all_time.empty:
            st.write("Top all-time (lbs CO₂ saved):")
            st.table(all_time.rename(columns={"estimated_co2_lbs": "alltime_co2_lbs"}).set_index('user'))

        st.markdown("---")
        st.subheader("📥 Raw data & export")
        st.dataframe(df.sort_values('date', ascending=False).reset_index(drop=True))
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("Download full CSV", data=csv, file_name='sustain_data.csv', mime='text/csv')

# ---------------- Footer / Credibility ----------------
st.markdown("---")
st.markdown(
    "**Notes on estimates:** Emission factors (miles, electricity, plastic, beef) are approximate. "
    "When you cite totals, include a short credibility line (e.g., 'Estimates use EPA averages and published factors for vehicle miles and electricity')."
)
