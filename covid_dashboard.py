# Note to graders: I got a lot of help from Claude Code (Opus 4.6):
# First, I got a bit of help with streamlit syntax (and tools) because I wasn't familiar with it
# Next, after I finished the whole thing, I asked Claude to help make a "normalize for population size" button
# And all of that (REST Countries API, population data parsing, name mapping) was written by Claude
# Hope that's ok!

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import json
import urllib.request

# Raw CSV URLs from CSSE GitHub repo
URLS = {
    "Confirmed": "https://raw.githubusercontent.com/CSSEGISandData/COVID-19/master/csse_covid_19_data/csse_covid_19_time_series/time_series_covid19_confirmed_global.csv",
    "Deaths": "https://raw.githubusercontent.com/CSSEGISandData/COVID-19/master/csse_covid_19_data/csse_covid_19_time_series/time_series_covid19_deaths_global.csv",
    "Recovered": "https://raw.githubusercontent.com/CSSEGISandData/COVID-19/master/csse_covid_19_data/csse_covid_19_time_series/time_series_covid19_recovered_global.csv",
}

# Mapping from CSSE country names to REST Countries common names
CSSE_TO_RC = {
    "Burma": "Myanmar",
    "Cabo Verde": "Cape Verde",
    "Congo (Brazzaville)": "Republic of the Congo",
    "Congo (Kinshasa)": "DR Congo",
    "Cote d'Ivoire": "Ivory Coast",
    "Holy See": "Vatican City",
    "Korea, North": "North Korea",
    "Korea, South": "South Korea",
    "Sao Tome and Principe": "São Tomé and Príncipe",
    "Taiwan*": "Taiwan",
    "US": "United States",
    "West Bank and Gaza": "Palestine",
}

st.set_page_config(page_title="COVID-19 Dashboard", layout="wide")

st.title("COVID-19 Global Dashboard")
st.caption("Data Source: [Johns Hopkins CSSE — Center for Systems Science and Engineering](https://github.com/CSSEGISandData/COVID-19)")

@st.cache_data(ttl=3600)
def load_population():
    """Load population data from REST Countries API."""
    resp = urllib.request.urlopen("https://restcountries.com/v3.1/all?fields=name,population")
    rc_data = json.loads(resp.read())
    return {entry["name"]["common"]: entry["population"] for entry in rc_data}

@st.cache_data(ttl=3600)
def load_data():
    """Load and reshape CSSE time-series CSVs."""
    frames = {}
    for metric, url in URLS.items():
        df = pd.read_csv(url)
        df = df.drop(columns=["Province/State", "Lat", "Long"]).groupby("Country/Region").sum()
        df = df.T
        df.index = pd.to_datetime(df.index)
        df.index.name = "Date"
        frames[metric] = df
    return frames

def get_population(country, pop_data):
    """Look up population for a CSSE country name."""
    rc_name = CSSE_TO_RC.get(country, country)
    return pop_data.get(rc_name)

with st.spinner("Loading data..."):
    data = load_data()
    pop_data = load_population()

countries = sorted(data["Confirmed"].columns.tolist())

# Sidebar controls
with st.sidebar:
    st.header("Settings")

    selected_countries = st.multiselect(
        "Select countries",
        options=countries,
        default=["US", "India", "Brazil"],
    )

    metric = st.selectbox("Metric", ["Confirmed", "Deaths", "Recovered"])

    mode = st.radio("Display mode", ["Cumulative", "Daily"])

    per_capita = st.checkbox("Per 1,000 people (per capita)")

    show_log = st.checkbox("Logarithmic Y-axis")

if not selected_countries:
    st.info("Add one or more countries from the sidebar to get started.")
    st.stop()

# Check population availability when per-capita is on
if per_capita:
    missing_pop = [c for c in selected_countries if get_population(c, pop_data) is None]
    if missing_pop:
        st.warning(f"Population data unavailable for: {', '.join(missing_pop)}. "
                   "These countries will be excluded from per-capita view.")
        selected_countries = [c for c in selected_countries if c not in missing_pop]
        if not selected_countries:
            st.stop()

# Prepare data and switch modes
df = data[metric][selected_countries].copy()

if mode == "Daily":
    df = df.diff().clip(lower=0)

if per_capita:
    for country in selected_countries:
        pop = get_population(country, pop_data)
        df[country] = df[country] / (pop / 1000)

# Summaries
y_label = metric
if per_capita:
    y_label += " per 1,000 people"
st.subheader(f"{mode} {y_label}")

cols = st.columns(len(selected_countries))
cumulative = data[metric][selected_countries]
for col, country in zip(cols, selected_countries):
    total = int(cumulative[country].iloc[-1])
    last_day = int(cumulative[country].diff().iloc[-1])
    if per_capita:
        pop = get_population(country, pop_data)
        total_pc = total / (pop / 1000)
        last_pc = last_day / (pop / 1000)
        col.metric(country, f"{total_pc:,.2f}/1k", delta=f"+{last_pc:,.2f}/1k today")
    else:
        col.metric(country, f"{total:,}", delta=f"+{last_day:,} today")

# Line chart
fig = px.line(
    df,
    labels={"value": y_label, "variable": "Country"},
    title=f"{mode} {y_label} by Country",
)
fig.update_layout(
    xaxis_title="Date",
    yaxis_title=y_label,
    yaxis_type="log" if show_log else "linear",
    legend_title="Country",
    hovermode="x unified",
    height=500,
)
st.plotly_chart(fig, use_container_width=True)

# Comparison bar chart (last 30 days)
st.subheader(f"Last 30 Days — Daily New {y_label}")
recent = data[metric][selected_countries].diff().clip(lower=0).tail(30)
if per_capita:
    for country in selected_countries:
        pop = get_population(country, pop_data)
        recent[country] = recent[country] / (pop / 1000)
fig_bar = px.bar(
    recent,
    barmode="group",
    labels={"value": y_label, "variable": "Country"},
)
fig_bar.update_layout(xaxis_title="Date", yaxis_title=f"Daily {y_label}", height=400)
st.plotly_chart(fig_bar, use_container_width=True)

# Raw data table
with st.expander("Show raw data"):
    fmt = "{:,.2f}" if per_capita else "{:,.0f}"
    st.dataframe(df.tail(60).style.format(fmt))
