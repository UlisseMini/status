import os
import httpx
from datetime import datetime, timedelta
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

AIRTABLE_API_KEY=os.environ['AIRTABLE_API_KEY']
WEBHOOK_URL=os.environ['WEBHOOK_URL']
OURA_API_KEY=os.environ['OURA_API_KEY']
TTL = 60*60 # 1 hour

@st.cache_data(ttl=TTL)
def get_toggl_day(start_date: str, end_date: str):
    resp = httpx.get(
        'https://api.track.toggl.com/api/v9/me/time_entries',
        auth=(os.environ['TOGGL_API_KEY'], 'api_token'),
        params={
            "start_date": start_date,
            "end_date": end_date,
        }
    )
    resp.raise_for_status()

    return resp.json()


@st.cache_data(ttl=TTL)
def get_toggl_projects():
    resp = httpx.get("https://api.track.toggl.com/api/v9/me/projects", auth=(os.environ['TOGGL_API_KEY'], 'api_token'))
    resp.raise_for_status()
    return resp.json()


@st.cache_data(ttl=TTL)
def get_airtable_day(date: str):
    resp = httpx.get(f'https://api.airtable.com/v0/appq1TYckaWsk1tgt/Daily', params={
        'maxRecords': 1,
        'view': 'Grid view',
        'filterByFormula': f'DATESTR(Date) = "{date}"',
    }, headers={'Authorization': f'Bearer {AIRTABLE_API_KEY}'})
    resp.raise_for_status()
    day = resp.json()["records"][0]["fields"]
    return day


@st.cache_data(ttl=TTL)
def get_oura_sleep(start_date: str, end_date: str):
    resp = httpx.get("https://api.ouraring.com/v2/usercollection/daily_sleep", params={
        "start_date": start_date,
        "end_date": end_date,
    }, headers={"Authorization": f"Bearer {OURA_API_KEY}"})
    resp.raise_for_status()

    return resp.json()



def show_oura_sleep(start_date: str, end_date: str):
    st.write("## Sleep")
    sleep = get_oura_sleep(start_date, end_date)
    if len(sleep['data']) == 0:
        st.write("No sleep data found :(")
        return

    oura_data = sleep['data'][0]

    # Sleep Score Gauge
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=oura_data["score"],
        domain={"x": [0, 1], "y": [0, 1]},
        title={"text": f"Sleep Score for {oura_data['day']}"},
        gauge={"axis": {"range": [0, 100], "tickwidth": 2}},
        number={"suffix": "/100"}
    ))

    st.plotly_chart(fig)


def show_journal(date: str):
    # TODO: Show past journals, slider for which day to look at
    st.write("## Journal")
    day = get_airtable_day(date)
    msg = day['Journal'] if day['Date'] == date else "No journal data found :("
    st.write(msg)


def show_toggl_data(start_date: str, end_date: str):
    st.write("## Time tracking")
    toggl = get_toggl_day(start_date, end_date)
    toggl_projects = get_toggl_projects()

    df = pd.DataFrame(toggl)
    project_names = {project['id']: project['name'] for project in toggl_projects}
    df['project_name'] = df['project_id'].map(project_names)
    df['duration'] = df['duration'] / 60 / 60

    # Pie chart with plotly
    # TODO: Client data as well
    fig = px.pie(df[['project_name', 'duration']], values='duration', names='project_name')
    st.plotly_chart(fig)



def main():
    st.title("Uli status")
    st.write("A dashboard for Uli's daily status, how his life is going, etc.")

    # Use streamlit to get the date via a date picker
    TODAY = st.date_input("Date", datetime.now()).strftime('%Y-%m-%d') # type: ignore
    YESTERDAY = (datetime.strptime(TODAY, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')

    show_journal(YESTERDAY)
    show_oura_sleep(YESTERDAY, TODAY)
    show_toggl_data(YESTERDAY, TODAY)


if __name__ == '__main__':
    main()
