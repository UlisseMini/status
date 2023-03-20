import os
import httpx
from datetime import datetime, timedelta, timezone
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from discord_oauth import get_user_info, get_access_token, get_login_url

AIRTABLE_API_KEY=os.environ['AIRTABLE_API_KEY']
WEBHOOK_URL=os.environ['WEBHOOK_URL']
OURA_API_KEY=os.environ['OURA_API_KEY']
ALLOWED_DISCORD_IDS = os.environ['ALLOWED_DISCORD_IDS'].split(',')
TTL = 60*60 # 1 hour


@st.cache_data() # basically constant for all time
def get_toggl_workspace() -> int:
    resp = httpx.get('https://api.track.toggl.com/api/v9/me', auth=(os.environ['TOGGL_API_KEY'], 'api_token'))
    resp.raise_for_status()
    return resp.json()['default_workspace_id']

@st.cache_data(ttl=TTL)
def get_toggl_day(start_date: str, end_date: str, grouping="projects"):
    workspace_id = get_toggl_workspace()

    resp = httpx.post(
        f'https://api.track.toggl.com/reports/api/v3/workspace/{workspace_id}/summary/time_entries',
        auth=(os.environ['TOGGL_API_KEY'], 'api_token'),
        json={
            "collapse": True,
            "grouping": grouping,
            "sub_grouping": "time_entries",
            "end_date": end_date,
            "start_date": start_date,
            "audit": {
                "show_empty_groups": False,
                "show_tracked_groups": True,
                "group_filter": {}
            },
            "include_time_entry_ids": True
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
def get_toggl_clients():
    resp = httpx.get("https://api.track.toggl.com/api/v9/me/clients", auth=(os.environ['TOGGL_API_KEY'], 'api_token'))
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
    records = resp.json()["records"]
    return records[0]["fields"] if len(records) > 0 else None


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

    st.write(f"Sleep score for {oura_data['day']} (i.e. sleep from previous night)")
    # TODO: Show sleep hours, etc. stats

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
    msg = day['Journal'] if day else "No journal data found :("
    # st.markdown(f"""```md\n{msg}\n```""")
    msg = msg.replace("\\*", "*")
    st.markdown(msg)


def show_toggl_data(start_date: str, end_date: str):
    st.write("## Time tracking")

    # Multiple choice between "projects" and "clients"
    grouping = st.radio("Grouping", ("projects", "clients")) or "projects"
    toggl = get_toggl_day(start_date, end_date, grouping=grouping)
    toggl_groupings = get_toggl_projects() if grouping == "projects" else get_toggl_clients()

    # New schema processing
    data = []
    for group in toggl['groups']:
        grouping_id = group['id']
        grouping_name = None
        if grouping_id is not None:
            grouping_name = next((group['name'] for group in toggl_groupings if group['id'] == grouping_id), None)
        for sub_group in group['sub_groups']:
            data.append({
                f'{grouping}_id': grouping_id,
                f'{grouping}_name': grouping_name,
                'title': sub_group.get('title') or '<No title>',
                'duration': sub_group['seconds'] / 60 / 60
            })

    df = pd.DataFrame(data)

    # Check if df is empty
    if df.empty:
        st.write("No time tracking data found :(")
        return

    # Sum over group name
    df = df.groupby([f'{grouping}_name']).sum(numeric_only=True).reset_index()

    # Format duration as hours minutes
    df['formatted_duration'] = df['duration'].apply(lambda x: f"{int(x)}h {int((x - int(x)) * 60)}min")

    # Pie chart with plotly
    fig = px.pie(df[[f'{grouping}_name', 'duration', 'formatted_duration']], values='duration', names=f'{grouping}_name', custom_data=['formatted_duration'])
    fig.update_traces(hovertemplate='%{label}<br>Duration: %{customdata[0]}<extra></extra>')

    st.plotly_chart(fig)



def main():
    st.title("Uli status")

    if 'access_token' not in st.session_state:
        # attempt getting it from ?code= query param
        code = st.experimental_get_query_params().get('code', None)
        if code:
            code = code[0] # because query params are always lists
            st.session_state.access_token = get_access_token(code)['access_token']
            # TODO: If this fails our token expired, so we should delete it
            st.session_state.user = get_user_info(st.session_state.access_token)
            st.experimental_set_query_params()

    if not ('user' in st.session_state and st.session_state.user['id'] in ALLOWED_DISCORD_IDS):
        st.write(f"[Login with discord]({get_login_url()})")
        return

    st.write(f"A dashboard for Uli's daily status, how his life is going, etc. Welcome, {st.session_state.user['username'].title()}!")

    # Use streamlit to get the date via a date picker
    default_date = datetime.now(timezone(timedelta(hours=-4))).date()
    date = st.date_input("Date", default_date).strftime('%Y-%m-%d') # type: ignore

    prev_day_date = (datetime.strptime(date, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')

    # In order of longest period I have data for, to shortest. Most recently added at the top.
    show_toggl_data(date, date)
    show_journal(prev_day_date)
    show_oura_sleep(date, date)


if __name__ == '__main__':
    main()
