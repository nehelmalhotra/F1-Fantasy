"""
F1 Fantasy Dashboard - DRS Mafia
Streamlit dashboard for tracking league performance, budgets, and efficiency.
"""

import os
import asyncio
from pathlib import Path
from urllib.parse import unquote
from collections import defaultdict
from datetime import datetime
import pytz

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import httpx
from dotenv import load_dotenv


# 2025 F1 Calendar with race times (UTC)
F1_SCHEDULE_2025 = [
    {"round": 1, "name": "Australia", "location": "Melbourne", "date": "2025-03-16", "time": "04:00", "completed": True},
    {"round": 2, "name": "China", "location": "Shanghai", "date": "2025-03-23", "time": "07:00", "completed": True},
    {"round": 3, "name": "Japan", "location": "Suzuka", "date": "2025-04-06", "time": "05:00", "completed": True},
    {"round": 4, "name": "Bahrain", "location": "Sakhir", "date": "2025-04-13", "time": "15:00", "completed": True},
    {"round": 5, "name": "Saudi Arabia", "location": "Jeddah", "date": "2025-04-20", "time": "17:00", "completed": True},
    {"round": 6, "name": "Miami", "location": "Miami", "date": "2025-05-04", "time": "20:00", "completed": True},
    {"round": 7, "name": "Emilia Romagna", "location": "Imola", "date": "2025-05-18", "time": "13:00", "completed": True},
    {"round": 8, "name": "Monaco", "location": "Monte Carlo", "date": "2025-05-25", "time": "13:00", "completed": True},
    {"round": 9, "name": "Spain", "location": "Barcelona", "date": "2025-06-01", "time": "13:00", "completed": True},
    {"round": 10, "name": "Canada", "location": "Montreal", "date": "2025-06-15", "time": "18:00", "completed": True},
    {"round": 11, "name": "Austria", "location": "Spielberg", "date": "2025-06-29", "time": "13:00", "completed": True},
    {"round": 12, "name": "Great Britain", "location": "Silverstone", "date": "2025-07-06", "time": "14:00", "completed": True},
    {"round": 13, "name": "Belgium", "location": "Spa", "date": "2025-07-27", "time": "13:00", "completed": True},
    {"round": 14, "name": "Hungary", "location": "Budapest", "date": "2025-08-03", "time": "13:00", "completed": True},
    {"round": 15, "name": "Netherlands", "location": "Zandvoort", "date": "2025-08-31", "time": "13:00", "completed": True},
    {"round": 16, "name": "Italy", "location": "Monza", "date": "2025-09-07", "time": "13:00", "completed": True},
    {"round": 17, "name": "Azerbaijan", "location": "Baku", "date": "2025-09-21", "time": "11:00", "completed": True},
    {"round": 18, "name": "Singapore", "location": "Marina Bay", "date": "2025-10-05", "time": "12:00", "completed": True},
    {"round": 19, "name": "USA", "location": "Austin", "date": "2025-10-19", "time": "19:00", "completed": True},
    {"round": 20, "name": "Mexico", "location": "Mexico City", "date": "2025-10-26", "time": "20:00", "completed": True},
    {"round": 21, "name": "Brazil", "location": "Sao Paulo", "date": "2025-11-09", "time": "17:00", "completed": True},
    {"round": 22, "name": "Las Vegas", "location": "Las Vegas", "date": "2025-11-22", "time": "06:00", "completed": True},
    {"round": 23, "name": "Qatar", "location": "Lusail", "date": "2025-11-30", "time": "16:00", "completed": False},
    {"round": 24, "name": "Abu Dhabi", "location": "Yas Marina", "date": "2025-12-07", "time": "13:00", "completed": False},
]

# Common timezones
TIMEZONES = [
    "America/Los_Angeles",
    "America/Denver",
    "America/Chicago",
    "America/New_York",
    "America/Toronto",
    "Europe/London",
    "Europe/Paris",
    "Europe/Berlin",
    "Asia/Dubai",
    "Asia/Kolkata",
    "Asia/Singapore",
    "Asia/Tokyo",
    "Australia/Sydney",
    "Pacific/Auckland",
]

# Load credentials
load_dotenv()

# Config
LEAGUE_ID = 5106507
LEAGUE_NAME = "DRS Mafia"
NUM_RACES = 22

# Page config
st.set_page_config(
    page_title="F1 Fantasy - DRS Mafia",
    page_icon="🏎️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS
st.markdown("""
<style>
    [data-testid="stMetric"] {
        background-color: #1e1e2e;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #3d3d5c;
    }
    [data-testid="stMetricLabel"] {
        color: #a0a0a0 !important;
    }
    [data-testid="stMetricValue"] {
        color: #ffffff !important;
    }
    [data-testid="stMetricDelta"] {
        color: #e10600 !important;
    }
    h1, h2, h3 {
        color: #e10600 !important;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: #1e1e2e;
        border-radius: 8px;
        padding: 10px 20px;
    }
</style>
""", unsafe_allow_html=True)


CHIP_NAMES = {
    1: 'Wildcard',
    2: 'Limitless',
    3: 'Final Fix',
    4: 'Autopilot',
    5: 'No Negative',
    6: 'Extra DRS',
}


class F1FantasyAPI:
    """F1 Fantasy API client."""
    
    def __init__(self):
        self.user_guid = os.environ.get("F1_USER_GUID")
        self.token = os.environ.get("F1_TOKEN")
        self.base_url = "https://fantasy.formula1.com"
    
    async def get_league_members(self, league_id: int) -> dict:
        """Get all league members with their GUIDs."""
        url = f"/services/user/leaderboard/{self.user_guid}/pvtleagueuserrankget/1/{league_id}/0/1/1/100/"
        
        async with httpx.AsyncClient(
            base_url=self.base_url,
            cookies={'F1_FANTASY_007': self.token}
        ) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                members = data.get('Data', {}).get('Value', {}).get('memRank', [])
                
                users = {}
                for m in members:
                    user_name = m['userName']
                    if user_name not in users:
                        users[user_name] = []
                    users[user_name].append({
                        'guid': m['guid'],
                        'team_no': m['teamNo'],
                        'team_name': unquote(m['teamName'])
                    })
                return users
        return {}
    
    async def get_all_race_data(self, league_id: int, num_races: int) -> dict:
        """Fetch all race data."""
        all_race_data = {}
        
        async with httpx.AsyncClient(
            base_url=self.base_url,
            cookies={'F1_FANTASY_007': self.token},
            timeout=30.0
        ) as client:
            for race_id in range(1, num_races + 1):
                url = f"/services/user/leaderboard/{self.user_guid}/pvtleagueuserrankget/2/{league_id}/{race_id}/1/1/100/"
                try:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get('Data', {}).get('Value'):
                            members = data['Data']['Value'].get('memRank', [])
                            all_race_data[race_id] = [
                                {
                                    'team_name': unquote(m['teamName']),
                                    'user_name': m['userName'],
                                    'points': m['ovPoints'] or 0
                                }
                                for m in members
                            ]
                except Exception:
                    pass
        
        return all_race_data
    
    async def get_all_budget_data(self, users: dict, num_races: int) -> dict:
        """Fetch budget data for all users across all races."""
        all_budget_data = {}
        
        async with httpx.AsyncClient(
            base_url=self.base_url,
            cookies={'F1_FANTASY_007': self.token},
            timeout=30.0
        ) as client:
            for user_name, teams in users.items():
                user_budget_history = {}
                
                for race_id in range(1, num_races + 1):
                    race_total_val = 0
                    race_total_bal = 0
                    race_max_bal = 0
                    has_data = False
                    
                    for team in teams:
                        url = f"{self.base_url}/services/user/opponentteam/opponentgamedayplayerteamget/1/{team['guid']}/{team['team_no']}/{race_id}/1"
                        try:
                            resp = await client.get(url)
                            if resp.status_code == 200:
                                data = resp.json()
                                if data.get('Data', {}).get('Value', {}).get('userTeam'):
                                    t = data['Data']['Value']['userTeam'][0]
                                    
                                    # Check both top-level AND nested team_info
                                    tv = t.get('teamval') or 0
                                    tb = t.get('teambal') or 0
                                    mb = t.get('maxteambal') or 0
                                    
                                    # Fallback to team_info if top-level is missing
                                    team_info = t.get('team_info', {})
                                    if tv == 0 and team_info:
                                        tv = team_info.get('teamVal') or 0
                                    if tb == 0 and team_info:
                                        tb = team_info.get('teamBal') or 0
                                    if mb == 0 and team_info:
                                        mb = team_info.get('maxTeambal') or 0
                                    
                                    if tv > 0 or mb > 0:
                                        race_total_val += tv
                                        race_total_bal += tb
                                        race_max_bal += mb
                                        has_data = True
                        except Exception:
                            pass
                    
                    if has_data:
                        user_budget_history[race_id] = {
                            'team_val': race_total_val,
                            'team_bal': race_total_bal,
                            'max_team_bal': race_max_bal,
                        }
                
                if user_budget_history:
                    all_budget_data[user_name] = user_budget_history
        
        return all_budget_data
    
    async def get_all_chip_usage(self, users: dict, num_races: int) -> dict:
        """Get chip usage for all users in the league."""
        all_chips = {}
        
        async with httpx.AsyncClient(
            base_url=self.base_url,
            cookies={'F1_FANTASY_007': self.token},
            timeout=30.0
        ) as client:
            for user_name, teams in users.items():
                user_chips = []
                
                for team_info in teams:
                    for race_id in range(1, num_races + 1):
                        url = f"/services/user/opponentteam/opponentgamedayplayerteamget/1/{team_info['guid']}/{team_info['team_no']}/{race_id}/1"
                        try:
                            resp = await client.get(url)
                            if resp.status_code == 200:
                                data = resp.json()
                                team = data.get('Data', {}).get('Value', {}).get('userTeam', [{}])[0]
                                booster = team.get('boosterid')
                                if booster:
                                    user_chips.append({
                                        'team': team_info['team_name'],
                                        'race': race_id,
                                        'chip_id': booster,
                                        'chip': CHIP_NAMES.get(booster, f'Chip {booster}')
                                    })
                        except:
                            pass
                
                if user_chips:
                    all_chips[user_name] = user_chips
        
        return all_chips


def build_user_data(all_race_data: dict) -> tuple:
    """Build user-level cumulative and per-race data."""
    user_cumulative = {}
    user_per_race = {}
    cumulative_totals = defaultdict(float)
    
    for race_id in sorted(all_race_data.keys()):
        # Sum points per user for this race
        race_points = defaultdict(float)
        for entry in all_race_data[race_id]:
            race_points[entry['user_name']] += entry['points'] or 0
        
        # Store per-race and cumulative
        for user_name, points in race_points.items():
            if user_name not in user_cumulative:
                user_cumulative[user_name] = {}
                user_per_race[user_name] = {}
            
            cumulative_totals[user_name] += points
            user_cumulative[user_name][race_id] = cumulative_totals[user_name]
            user_per_race[user_name][race_id] = points
    
    return user_cumulative, user_per_race


def calculate_metrics(user_cumulative: dict, budget_data: dict, num_teams_per_user: dict) -> dict:
    """Calculate efficiency metrics for each user."""
    metrics = {}
    
    for user_name, history in user_cumulative.items():
        if not history:
            continue
            
        final_race = max(history.keys())
        total_points = history.get(final_race, 0) or 0
        
        # Get budget info
        budget_history = budget_data.get(user_name, {})
        if budget_history:
            valid_races = [r for r in budget_history.keys() if budget_history[r]['max_team_bal'] > 0]
            if valid_races:
                final_team_val = budget_history[max(valid_races)]['max_team_bal']
                starting_budget = 100 * num_teams_per_user.get(user_name, 2)
            else:
                final_team_val = starting_budget = 0
        else:
            final_team_val = starting_budget = 0
        
        # Calculate metrics
        budget_gain = final_team_val - starting_budget if starting_budget > 0 else 0
        
        # Points per $M invested
        avg_team_val = (starting_budget + final_team_val) / 2 if final_team_val > 0 else starting_budget
        points_per_million = total_points / avg_team_val if avg_team_val > 0 else 0
        
        # ROI
        roi = (budget_gain / starting_budget * 100) if starting_budget > 0 else 0
        
        metrics[user_name] = {
            'total_points': total_points,
            'final_team_val': final_team_val,
            'starting_budget': starting_budget,
            'budget_gain': budget_gain,
            'points_per_million': points_per_million,
            'roi_percent': roi,
        }
    
    return metrics


def get_race_names():
    """Return race weekend names."""
    return {
        1: "Australia", 2: "China", 3: "Japan", 4: "Bahrain",
        5: "Saudi Arabia", 6: "Miami", 7: "Emilia Romagna", 8: "Monaco",
        9: "Spain", 10: "Canada", 11: "Austria", 12: "Great Britain",
        13: "Belgium", 14: "Hungary", 15: "Netherlands", 16: "Italy",
        17: "Azerbaijan", 18: "Singapore", 19: "USA", 20: "Mexico",
        21: "Brazil", 22: "Las Vegas", 23: "Qatar", 24: "Abu Dhabi"
    }


@st.cache_data(ttl=300)  # Cache for 5 minutes
def fetch_data():
    """Fetch all data from API."""
    api = F1FantasyAPI()
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    all_race_data = loop.run_until_complete(api.get_all_race_data(LEAGUE_ID, NUM_RACES))
    users = loop.run_until_complete(api.get_league_members(LEAGUE_ID))
    chip_data = loop.run_until_complete(api.get_all_chip_usage(users, NUM_RACES))
    budget_data = loop.run_until_complete(api.get_all_budget_data(users, NUM_RACES))
    
    loop.close()
    
    return all_race_data, chip_data, budget_data, users


def main():
    # Header
    st.title("🏎️ F1 Fantasy Dashboard")
    st.markdown(f"### {LEAGUE_NAME}")
    
    # Fetch data
    with st.spinner("Loading race data..."):
        all_race_data, chip_data, budget_data, users = fetch_data()
    
    if not all_race_data:
        st.error("Could not fetch data. Check your credentials.")
        return
    
    # Count teams per user
    num_teams_per_user = {name: len(teams) for name, teams in users.items()}
    
    # Build user-level data
    user_cumulative, user_per_race = build_user_data(all_race_data)
    
    # Calculate metrics
    metrics = calculate_metrics(user_cumulative, budget_data, num_teams_per_user)
    
    # Filter out users with 0 points
    final_race = max(all_race_data.keys())
    active_users = {
        name: data for name, data in user_cumulative.items()
        if data.get(final_race, 0) > 0
    }
    
    # Sort by final points
    sorted_users = sorted(
        active_users.items(),
        key=lambda x: x[1].get(final_race, 0),
        reverse=True
    )
    
    race_names = get_race_names()
    
    # === METRICS ROW ===
    col1, col2, col3, col4, col5 = st.columns(5)
    
    leader_name, leader_data = sorted_users[0]
    leader_points = leader_data.get(final_race, 0)
    leader_metrics = metrics.get(leader_name, {})
    
    with col1:
        st.metric("🥇 Leader", leader_name, f"{leader_points:,.0f} pts")
    
    with col2:
        st.metric("👥 Players", len(sorted_users))
    
    with col3:
        st.metric("🏁 Races", final_race)
    
    # Find your position
    your_name = "Nehel Malhotra"
    your_pos = next((i+1 for i, (name, _) in enumerate(sorted_users) if name == your_name), None)
    your_points = active_users.get(your_name, {}).get(final_race, 0)
    your_metrics = metrics.get(your_name, {})
    
    with col4:
        if your_pos:
            gap = leader_points - your_points
            st.metric("📍 Your Position", f"#{your_pos}", f"-{gap:,.0f} pts")
    
    with col5:
        if your_metrics:
            st.metric("💰 Your Team Value", f"${your_metrics.get('final_team_val', 0):,.1f}M", 
                     f"+${your_metrics.get('budget_gain', 0):,.1f}M")
    
    st.divider()
    
    # === TABS ===
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "📈 Points", "💰 Budget", "⚡ Efficiency", "🏆 Standings", 
        "📊 Race Breakdown", "🎯 Chip Usage", "📅 Schedule"
    ])
    
    # === TAB 1: CUMULATIVE POINTS CHART ===
    with tab1:
        st.subheader("Cumulative Points Over Season")
        
        chart_data = []
        for user_name, history in sorted_users:
            for race_id, points in history.items():
                chart_data.append({
                    'User': user_name,
                    'Race': race_id,
                    'Race Name': race_names.get(race_id, f"Race {race_id}"),
                    'Cumulative Points': points
                })
        
        df = pd.DataFrame(chart_data)
        
        fig = px.line(
            df,
            x='Race',
            y='Cumulative Points',
            color='User',
            markers=True,
            title='Cumulative Performance by User',
            hover_data=['Race Name']
        )
        
        fig.update_layout(
            template='plotly_dark',
            height=600,
            xaxis_title='Race Weekend',
            yaxis_title='Cumulative Points',
            legend=dict(yanchor="top", y=0.99, xanchor="left", x=1.02),
            hovermode='x unified'
        )
        
        fig.update_xaxes(
            tickmode='array',
            tickvals=list(range(1, final_race + 1)),
            ticktext=[race_names.get(i, f"R{i}") for i in range(1, final_race + 1)],
            tickangle=-45
        )
        
        st.plotly_chart(fig, use_container_width=True)
    
    # === TAB 2: BUDGET EVOLUTION ===
    with tab2:
        st.subheader("Team Value Evolution")
        
        if budget_data:
            # Sort users by final team value
            sorted_budget_users = sorted(
                budget_data.items(),
                key=lambda x: max([v['max_team_bal'] for v in x[1].values()] or [0]),
                reverse=True
            )
            
            budget_chart_data = []
            for user_name, history in sorted_budget_users:
                for race_id, data in history.items():
                    if data['max_team_bal'] > 0:
                        budget_chart_data.append({
                            'User': user_name,
                            'Race': race_id,
                            'Race Name': race_names.get(race_id, f"Race {race_id}"),
                            'Team Value ($M)': data['max_team_bal']
                        })
            
            budget_df = pd.DataFrame(budget_chart_data)
            
            if not budget_df.empty:
                fig_budget = px.line(
                    budget_df,
                    x='Race',
                    y='Team Value ($M)',
                    color='User',
                    markers=True,
                    title='Team Value Evolution (Combined for all teams per user)',
                    hover_data=['Race Name']
                )
                
                # Add starting budget reference line
                fig_budget.add_hline(
                    y=200, line_dash="dash", line_color="white",
                    annotation_text="Starting Budget ($200M for 2 teams)",
                    annotation_position="top left"
                )
                
                fig_budget.update_layout(
                    template='plotly_dark',
                    height=600,
                    xaxis_title='Race Weekend',
                    yaxis_title='Team Value ($M)',
                    legend=dict(yanchor="top", y=0.99, xanchor="left", x=1.02),
                    hovermode='x unified'
                )
                
                fig_budget.update_xaxes(
                    tickmode='array',
                    tickvals=list(range(1, final_race + 1)),
                    ticktext=[race_names.get(i, f"R{i}") for i in range(1, final_race + 1)],
                    tickangle=-45
                )
                
                st.plotly_chart(fig_budget, use_container_width=True)
                
                # Budget summary metrics
                st.subheader("Team Value Summary")
                
                budget_summary = []
                for user_name, history in sorted_budget_users:
                    valid_vals = [v['max_team_bal'] for v in history.values() if v['max_team_bal'] > 0]
                    if valid_vals:
                        final_val = valid_vals[-1]
                        starting = 200  # Assuming 2 teams
                        gain = final_val - starting
                        roi = (gain / starting) * 100
                        budget_summary.append({
                            'User': user_name,
                            'Final Value': f"${final_val:,.1f}M",
                            'Gain': f"+${gain:,.1f}M" if gain >= 0 else f"-${abs(gain):,.1f}M",
                            'ROI': f"{roi:+.1f}%"
                        })
                
                budget_summary_df = pd.DataFrame(budget_summary)
                st.dataframe(budget_summary_df, use_container_width=True, hide_index=True)
        else:
            st.info("Budget data not available")
    
    # === TAB 3: EFFICIENCY METRICS ===
    with tab3:
        st.subheader("Efficiency Analysis")
        
        if metrics:
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("#### ⚡ Points per $M Invested")
                
                efficiency_data = sorted(
                    [(n, m['points_per_million']) for n, m in metrics.items() if m['points_per_million'] > 0],
                    key=lambda x: x[1],
                    reverse=True
                )
                
                eff_df = pd.DataFrame(efficiency_data, columns=['User', 'Points/$M'])
                
                fig_eff = px.bar(
                    eff_df,
                    x='Points/$M',
                    y='User',
                    orientation='h',
                    title='Efficiency: Points per $M',
                    color='Points/$M',
                    color_continuous_scale='Viridis'
                )
                
                fig_eff.update_layout(
                    template='plotly_dark',
                    height=400,
                    yaxis={'categoryorder': 'total ascending'},
                    showlegend=False
                )
                
                st.plotly_chart(fig_eff, use_container_width=True)
            
            with col2:
                st.markdown("#### 📈 ROI % (Team Value Growth)")
                
                roi_data = sorted(
                    [(n, m['roi_percent']) for n, m in metrics.items() if m['roi_percent'] != 0],
                    key=lambda x: x[1],
                    reverse=True
                )
                
                roi_df = pd.DataFrame(roi_data, columns=['User', 'ROI %'])
                
                fig_roi = px.bar(
                    roi_df,
                    x='ROI %',
                    y='User',
                    orientation='h',
                    title='Return on Investment',
                    color='ROI %',
                    color_continuous_scale='RdYlGn'
                )
                
                fig_roi.update_layout(
                    template='plotly_dark',
                    height=400,
                    yaxis={'categoryorder': 'total ascending'},
                    showlegend=False
                )
                
                st.plotly_chart(fig_roi, use_container_width=True)
            
            # Combined metrics table
            st.subheader("Complete Metrics Table")
            
            metrics_table = []
            for i, (name, _) in enumerate(sorted_users):
                m = metrics.get(name, {})
                if m:
                    metrics_table.append({
                        'Rank': i + 1,
                        'User': name,
                        'Points': f"{m['total_points']:,.0f}",
                        'Team Value': f"${m['final_team_val']:,.1f}M",
                        'Gain': f"+${m['budget_gain']:,.1f}M" if m['budget_gain'] >= 0 else f"${m['budget_gain']:,.1f}M",
                        'Pts/$M': f"{m['points_per_million']:.1f}",
                        'ROI': f"{m['roi_percent']:+.1f}%"
                    })
            
            metrics_df = pd.DataFrame(metrics_table)
            st.dataframe(metrics_df, use_container_width=True, hide_index=True)
        else:
            st.info("Efficiency metrics not available")
    
    # === TAB 4: STANDINGS TABLE ===
    with tab4:
        st.subheader("League Standings")
        
        standings_data = []
        
        for i, (user_name, history) in enumerate(sorted_users):
            final_pts = history.get(final_race, 0)
            prev_race_pts = history.get(final_race - 1, 0) if final_race > 1 else 0
            race_pts = user_per_race.get(user_name, {}).get(final_race, 0)
            
            races_played = len([r for r in history.values() if r > 0])
            avg_pts = final_pts / races_played if races_played > 0 else 0
            
            gap = leader_points - final_pts
            
            m = metrics.get(user_name, {})
            
            standings_data.append({
                'Rank': i + 1,
                'User': user_name,
                'Total Points': f"{final_pts:,.0f}",
                'Last Race': f"{race_pts:,.0f}",
                'Avg/Race': f"{avg_pts:,.0f}",
                'Team Value': f"${m.get('final_team_val', 0):,.1f}M" if m else "N/A",
                'Gap to Leader': f"-{gap:,.0f}" if gap > 0 else "Leader"
            })
        
        standings_df = pd.DataFrame(standings_data)
        
        st.dataframe(
            standings_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                'Rank': st.column_config.NumberColumn('#', width='small'),
                'User': st.column_config.TextColumn('User', width='medium'),
                'Total Points': st.column_config.TextColumn('Total', width='small'),
                'Last Race': st.column_config.TextColumn('Last Race', width='small'),
                'Avg/Race': st.column_config.TextColumn('Avg/Race', width='small'),
                'Team Value': st.column_config.TextColumn('Value', width='small'),
                'Gap to Leader': st.column_config.TextColumn('Gap', width='small'),
            }
        )
    
    # === TAB 5: RACE BREAKDOWN ===
    with tab5:
        st.subheader("Points per Race Weekend")
        
        race_data = []
        for user_name in [u[0] for u in sorted_users]:
            per_race = user_per_race.get(user_name, {})
            for race_id, points in per_race.items():
                race_data.append({
                    'User': user_name,
                    'Race': race_id,
                    'Race Name': race_names.get(race_id, f"Race {race_id}"),
                    'Points': points
                })
        
        race_df = pd.DataFrame(race_data)
        
        pivot_df = race_df.pivot(index='User', columns='Race', values='Points')
        pivot_df = pivot_df.reindex([u[0] for u in sorted_users])
        pivot_df.columns = [race_names.get(c, f"Race {c}") for c in pivot_df.columns]
        
        fig_heat = px.imshow(
            pivot_df,
            labels=dict(x="Race Weekend", y="User", color="Points"),
            title="Points Heatmap by Race",
            color_continuous_scale='RdYlGn',
            aspect='auto'
        )
        
        fig_heat.update_layout(
            template='plotly_dark',
            height=400,
            xaxis_tickangle=-45
        )
        
        st.plotly_chart(fig_heat, use_container_width=True)
        
        # Race winners
        st.subheader("Race Winners")
        
        race_winners = []
        for race_id in sorted(all_race_data.keys()):
            race_points = defaultdict(float)
            for entry in all_race_data[race_id]:
                race_points[entry['user_name']] += entry['points'] or 0
            
            if race_points:
                winner = max(race_points.items(), key=lambda x: x[1])
                race_winners.append({
                    'Race': race_id,
                    'GP': race_names.get(race_id, f"Race {race_id}"),
                    'Winner': winner[0],
                    'Points': f"{winner[1]:,.0f}"
                })
        
        winners_df = pd.DataFrame(race_winners)
        win_counts = winners_df['Winner'].value_counts().to_dict()
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.dataframe(winners_df, use_container_width=True, hide_index=True)
        
        with col2:
            st.markdown("**Win Count:**")
            for user, wins in sorted(win_counts.items(), key=lambda x: -x[1]):
                st.write(f"🏆 {user}: {wins}")
    
    # === TAB 6: CHIP USAGE ===
    with tab6:
        st.subheader("Chip Usage - All Players")
        
        if chip_data:
            chip_timeline = []
            for user_name, chips in chip_data.items():
                for chip in chips:
                    chip_timeline.append({
                        'User': user_name,
                        'Team': chip['team'],
                        'Race': chip['race'],
                        'Race Name': race_names.get(chip['race'], f"Race {chip['race']}"),
                        'Chip': chip['chip']
                    })
            
            chip_df = pd.DataFrame(chip_timeline)
            
            if not chip_df.empty:
                fig_chips = px.scatter(
                    chip_df,
                    x='Race',
                    y='User',
                    color='Chip',
                    hover_data=['Team', 'Race Name'],
                    title='Chip Usage Timeline',
                    size_max=15
                )
                
                fig_chips.update_traces(marker=dict(size=15))
                fig_chips.update_layout(
                    template='plotly_dark',
                    height=400
                )
                
                fig_chips.update_xaxes(
                    tickmode='array',
                    tickvals=list(range(1, final_race + 1)),
                    ticktext=[race_names.get(i, f"R{i}") for i in range(1, final_race + 1)],
                    tickangle=-45
                )
                
                st.plotly_chart(fig_chips, use_container_width=True)
                
                st.subheader("Chips Used Per Player")
                chip_counts = chip_df.groupby(['User', 'Chip']).size().unstack(fill_value=0)
                chip_counts['Total'] = chip_counts.sum(axis=1)
                chip_counts = chip_counts.sort_values('Total', ascending=False)
                st.dataframe(chip_counts, use_container_width=True)
        else:
            st.info("Loading chip data...")
    
    # === TAB 7: SCHEDULE ===
    with tab7:
        st.subheader("2025 F1 Race Calendar")
        
        col1, col2 = st.columns([1, 3])
        with col1:
            selected_tz = st.selectbox(
                "Your Timezone",
                options=TIMEZONES,
                index=TIMEZONES.index("America/New_York") if "America/New_York" in TIMEZONES else 0
            )
        
        user_tz = pytz.timezone(selected_tz)
        utc = pytz.UTC
        
        schedule_data = []
        now = datetime.now(utc)
        next_race = None
        
        for race in F1_SCHEDULE_2025:
            race_dt_str = f"{race['date']} {race['time']}"
            race_dt_utc = utc.localize(datetime.strptime(race_dt_str, "%Y-%m-%d %H:%M"))
            race_dt_local = race_dt_utc.astimezone(user_tz)
            
            if race_dt_utc < now:
                status = "✅ Completed"
            elif next_race is None:
                status = "🟢 NEXT RACE"
                next_race = race
            else:
                status = "⏳ Upcoming"
            
            schedule_data.append({
                "Round": race["round"],
                "Race": race["name"],
                "Location": race["location"],
                "Date": race_dt_local.strftime("%a, %b %d"),
                "Time": race_dt_local.strftime("%I:%M %p"),
                "Status": status
            })
        
        schedule_df = pd.DataFrame(schedule_data)
        
        st.dataframe(
            schedule_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Round": st.column_config.NumberColumn("#", width="small"),
                "Race": st.column_config.TextColumn("Grand Prix", width="medium"),
                "Location": st.column_config.TextColumn("Circuit", width="medium"),
                "Date": st.column_config.TextColumn("Date", width="small"),
                "Time": st.column_config.TextColumn("Local Time", width="small"),
                "Status": st.column_config.TextColumn("Status", width="small"),
            }
        )
        
        if next_race:
            race_dt_str = f"{next_race['date']} {next_race['time']}"
            race_dt_utc = utc.localize(datetime.strptime(race_dt_str, "%Y-%m-%d %H:%M"))
            race_dt_local = race_dt_utc.astimezone(user_tz)
            time_until = race_dt_utc - now
            
            days = time_until.days
            hours = time_until.seconds // 3600
            
            st.markdown("---")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Next Race", next_race["name"])
            with col2:
                st.metric("Date/Time", race_dt_local.strftime("%b %d, %I:%M %p"))
            with col3:
                st.metric("Countdown", f"{days}d {hours}h")
    
    # Footer
    st.divider()
    st.caption("Data from F1 Fantasy API • Refresh the page for latest data")


if __name__ == "__main__":
    main()
