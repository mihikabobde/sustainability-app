import streamlit as st

st.set_page_config(page_title="GreenSteps", page_icon="🌱")

st.title("🌱 GreenSteps: Sustainability Tracker")
st.write("Track your eco-friendly actions and see your estimated CO₂ savings.")

# Default values for each action (very rough but good for a student project)
CO2_SAVINGS = {
    "Reusable Water Bottle Used": 0.08,      # lbs of CO₂ saved per use
    "Biked/Walked Instead of Car": 1.1,      # per mile avoided
    "Vegetarian Meal": 2.5,                  # per meal
    "Recycled Paper/Plastic": 0.2,           # per item
    "Turned Off Lights for 1 Hour": 0.09     # per hour
}

st.subheader("Enter Your Daily Actions")

actions = {}
for action in CO2_SAVINGS:
    actions[action] = st.number_input(f"{action} (how many times?)", min_value=0, step=1)

# Calculate CO₂ savings
if st.button("Calculate My CO₂ Savings"):
    total = 0
    for action, count in actions.items():
        total += count * CO2_SAVINGS[action]
    
    st.success(f"🎉 You saved approximately **{total:.2f} lbs** of CO₂ today!")
    st.write("This estimate is based on standard environmental research values.")

st.markdown("---")
st.write("This app was created to promote sustainability within the community.")

