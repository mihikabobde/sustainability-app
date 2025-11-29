import streamlit as st
import pandas as pd
import os
from datetime import datetime, date

# -----------------------------
# File setup
# -----------------------------
USERS_FILE = "users.csv"
DAILY_FILE = "daily_usage.csv"
WEEKLY_FILE = "weekly_usage.csv"

if not os.path.exists(USERS_FILE):
    pd.DataFrame(columns=["username", "password", "baseline_miles", "baseline_showers", "baseline_bottles", "baseline_takeout", "baseline_laundry"]).to_csv(USERS_FILE, index=False)

if not os.path.exists(DAILY_FILE):
    pd.DataFrame(columns=["username", "date", "miles", "showers", "bottles", "takeout"]).to_csv(DAILY_FILE, index=False)

if not os.path.exists(WEEKLY_FILE):
    pd.DataFrame(columns=["username", "week_start", "laundry"]).to_csv(WEEKLY_FILE, index=False)


# -----------------------------
# Helpers
# -----------------------------
def load_users():
    return pd.read_csv(USERS_FILE)

def save_users(df):
    df.to_csv(USERS_FILE, index=False)

def load_daily():
    return pd.read_csv(DAILY_FILE)

def save_daily(df):
    df.to_csv(DAILY_FILE, index=False)

def load_weekly():
    return pd.read_csv(WEEKLY_FILE)

def save_weekly(df):
    df.to_csv(WEEKLY_FILE, index=False)


def rerun():
    """Correct rerun method for Streamlit."""
    st.session_state._rerun = True
    st.experimental_rerun()


# -----------------------------
# Authentication UI
# -----------------------------
def login_page():
    st.title("🌱 Sustainability Tracker – Login")

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Log In"):
        users = load_users()
        user_row = users[(users["username"] == username) & (users["password"] == password)]

        if user_row.empty:
            st.error("Incorrect username or password.")
        else:
            st.session_state["user"] = username
            rerun()

    st.write("---")
    st.subheader("Don't have an account?")
    if st.button("Create Account"):
        st.session_state["page"] = "signup"
        rerun()


def signup_page():
    st.title("🌿 Create Your Sustainability Account")

    username = st.text_input("Create username")
    password = st.text_input("Create password", type="password")

    st.subheader("Set your baseline (normal weekly behavior)")
    baseline_miles = st.number_input("Miles you normally drive per day:", min_value=0.0)
    baseline_showers = st.number_input("Minutes you usually shower:", min_value=0.0)
    baseline_bottles = st.number_input("Plastic bottles used per day:", min_value=0)
    baseline_takeout = st.number_input("Takeout meals per week:", min_value=0)
    baseline_laundry = st.number_input("Laundry loads per week:", min_value=0)

    if st.button("Sign Up"):
        users = load_users()

        if username in users["username"].values:
            st.error("Username already exists.")
            return

        new_user = pd.DataFrame(
            [[username, password, baseline_miles, baseline_showers, baseline_bottles, baseline_takeout, baseline_laundry]],
            columns=users.columns
        )

        users = pd.concat([users, new_user], ignore_index=True)
        save_users(users)

        st.success("Account created! Logging you in...")

        st.session_state["user"] = username
        rerun()


# -----------------------------
# Main App
# -----------------------------
def app_page():
    st.title("🌎 Sustainability Tracker Dashboard")

    username = st.session_state["user"]
    st.write(f"Welcome, **{username}**! 🌱")

    st.sidebar.title("Menu")
    choice = st.sidebar.radio("Navigate", ["Daily Input", "Weekly Input", "Leaderboard", "Badges"])

    if st.sidebar.button("Log Out"):
        st.session_state.clear()
        rerun()

    if choice == "Daily Input":
        daily_input(username)
    elif choice == "Weekly Input":
        weekly_input(username)
    elif choice == "Leaderboard":
        leaderboard()
    elif choice == "Badges":
        badges(username)


# -----------------------------
# Features
# -----------------------------
def daily_input(username):
    st.header("📅 Daily Tracking")

    miles = st.number_input("Miles driven today:", min_value=0.0)
    showers = st.number_input("Minutes showered today:", min_value=0.0)
    bottles = st.number_input("Plastic bottles used today:", min_value=0)
    takeout = st.number_input("Takeout meals today:", min_value=0)

    if st.button("Submit Daily Data"):
        df = load_daily()
        new = pd.DataFrame([[username, str(date.today()), miles, showers, bottles, takeout]], columns=df.columns)
        df = pd.concat([df, new], ignore_index=True)
        save_daily(df)
        st.success("Daily data saved!")


def weekly_input(username):
    st.header("📆 Weekly Tracking")

    laundry = st.number_input("Laundry loads this week:", min_value=0)
    week_start = date.today().strftime("%Y-%m-%d")

    if st.button("Submit Weekly Data"):
        df = load_weekly()
        new = pd.DataFrame([[username, week_start, laundry]], columns=df.columns)
        df = pd.concat([df, new], ignore_index=True)
        save_weekly(df)
        st.success("Weekly data saved!")


def leaderboard():
    st.header("🏆 Leaderboard")
    st.info("Leaderboard coming next! (We calculate based on CO₂ saved)")


def badges(username):
    st.header("🎖 Badges")
    st.info("Badges coming next!")


# -----------------------------
# App Routing
# -----------------------------
if "page" not in st.session_state:
    st.session_state["page"] = "login"

if "user" in st.session_state:
    app_page()
else:
    if st.session_state["page"] == "login":
        login_page()
    else:
        signup_page()
