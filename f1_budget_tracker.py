"""
F1 Fantasy Budget Tracker
Tracks team value / budget evolution across races for all league members.

.env file format:
    F1_USER_GUID=your-guid-here
    F1_TOKEN=your-token-here
"""

import os
import asyncio
from pathlib import Path
from urllib.parse import unquote
from collections import defaultdict

from dotenv import load_dotenv
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    load_dotenv(env_path)
    print("Loaded credentials from .env")

import httpx
import matplotlib.pyplot as plt


# Your private league
LEAGUE_ID = 5106507  # DRS Mafia
LEAGUE_NAME = "DRS Mafia"
NUM_RACES = 22


def sanitize_name(name: str) -> str:
    """Remove special characters that matplotlib can't handle."""
    safe_name = name.encode('ascii', 'ignore').decode('ascii')
    for char in ['$', '%', '_', '{', '}', '^', '~', '\\']:
        safe_name = safe_name.replace(char, '')
    return safe_name.strip()


class F1BudgetTracker:
    """Track F1 Fantasy team budgets over time."""
    
    def __init__(self, user_guid: str, token: str):
        self.user_guid = user_guid
        self.token = token
        self.base_url = "https://fantasy.formula1.com"
    
    async def get_league_members(self, league_id: int) -> list:
        """Get all league members with their GUIDs."""
        url = f"{self.base_url}/services/user/leaderboard/{self.user_guid}/pvtleagueuserrankget/1/{league_id}/0/1/1/100/"
        
        async with httpx.AsyncClient(cookies={'F1_FANTASY_007': self.token}) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('Data', {}).get('Value'):
                    members = data['Data']['Value'].get('memRank', [])
                    return [
                        {
                            'team_name': unquote(m['teamName']),
                            'user_name': m['userName'],
                            'guid': m['guid'],
                            'team_no': m['teamNo'],
                            'total_points': m['ovPoints'] or 0,
                        }
                        for m in members
                    ]
        return []
    
    async def get_team_budget_at_race(self, guid: str, team_no: int, race_id: int) -> dict:
        """Get team budget data for a specific race."""
        url = f"{self.base_url}/services/user/opponentteam/opponentgamedayplayerteamget/1/{guid}/{team_no}/{race_id}/1"
        
        async with httpx.AsyncClient(cookies={'F1_FANTASY_007': self.token}) as client:
            try:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get('Data', {}).get('Value', {}).get('userTeam'):
                        team = data['Data']['Value']['userTeam'][0]
                        return {
                            'team_val': team.get('teamval', 0) or 0,
                            'team_bal': team.get('teambal', 0) or 0,
                            'max_team_bal': team.get('maxteambal', 0) or 0,
                            'points': team.get('ovpoints', 0) or 0,
                        }
            except Exception as e:
                pass
        return None
    
    async def get_all_budget_data(self, league_id: int, num_races: int = 22) -> dict:
        """Fetch budget data for all teams across all races."""
        
        # Get league members
        print("Fetching league members...")
        members = await self.get_league_members(league_id)
        print(f"Found {len(members)} teams")
        
        # Group by user (some users have multiple teams)
        user_teams = defaultdict(list)
        for m in members:
            user_teams[m['user_name']].append(m)
        
        all_budget_data = {}
        
        async with httpx.AsyncClient(
            cookies={'F1_FANTASY_007': self.token},
            timeout=30.0
        ) as client:
            
            for user_name, teams in user_teams.items():
                print(f"  Fetching budget data for {user_name} ({len(teams)} team(s))...")
                
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
                                    
                                    if tv > 0 or mb > 0:  # Has valid data
                                        race_total_val += tv
                                        race_total_bal += tb
                                        race_max_bal += mb
                                        has_data = True
                        except Exception as e:
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


def plot_budget_evolution(budget_data: dict, league_name: str, num_races: int = 22):
    """Plot team value evolution for all users."""
    
    colors = [
        '#E10600', '#00D2BE', '#3671C6', '#FF8700', '#006F62',
        '#FF87BC', '#B6BABD', '#6692FF', '#52E252', '#64C4FF',
        '#FF6B6B', '#C9B037', '#9B59B6', '#1ABC9C', '#E74C3C',
        '#3498DB', '#F39C12', '#2ECC71', '#8E44AD', '#E67E22',
    ]
    
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(16, 10))
    
    # Sort users by final max_team_bal
    def get_final_value(user_history):
        valid_races = [r for r in user_history.keys() if user_history[r]['max_team_bal'] > 0]
        if valid_races:
            return user_history[max(valid_races)]['max_team_bal']
        return 0
    
    sorted_users = sorted(
        budget_data.items(),
        key=lambda x: get_final_value(x[1]),
        reverse=True
    )
    
    print(f"\nTeam Value Rankings:")
    for idx, (user_name, history) in enumerate(sorted_users):
        color = colors[idx % len(colors)]
        
        # Get races with valid data
        valid_races = sorted([r for r in history.keys() if history[r]['max_team_bal'] > 0])
        if not valid_races:
            continue
            
        values = [history[r]['max_team_bal'] for r in valid_races]
        
        safe_name = sanitize_name(user_name)[:20]
        final_val = values[-1] if values else 0
        
        # Calculate gain from starting $100M
        gain = final_val - 100
        gain_str = f"+{gain:.1f}" if gain >= 0 else f"{gain:.1f}"
        
        print(f"  {idx+1:2}. {user_name:<25} - ${final_val:,.1f}M ({gain_str}M)")
        
        ax.plot(valid_races, values, marker='o', linewidth=2.5, markersize=5,
               label=f'{safe_name} (${final_val:,.1f}M)', color=color)
    
    # Add starting budget reference line
    ax.axhline(y=100, color='white', linestyle='--', alpha=0.5, label='Starting Budget ($100M)')
    
    ax.set_title(f'Team Value Evolution - {league_name}',
                fontsize=20, fontweight='bold', pad=20, color='white')
    ax.set_xlabel('Race Weekend', fontsize=14, color='white')
    ax.set_ylabel('Team Value (Millions $)', fontsize=14, color='white')
    ax.legend(loc='upper left', fontsize=9, ncol=1, bbox_to_anchor=(1.02, 1),
             framealpha=0.9)
    ax.grid(True, alpha=0.3, linestyle='--')
    ax.set_facecolor('#1a1a2e')
    fig.patch.set_facecolor('#0f0f1a')
    ax.set_xticks(range(1, num_races + 1))
    ax.tick_params(colors='white')
    
    plt.tight_layout()
    plt.subplots_adjust(right=0.72)
    
    safe_league = league_name.replace(' ', '_').replace('/', '_')
    filename = f"f1_budget_{safe_league}.png"
    plt.savefig(filename, dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor())
    print(f"\nChart saved as: {filename}")
    
    plt.show()


async def main():
    """Main function to fetch and visualize budget data."""
    
    user_guid = os.environ.get("F1_USER_GUID") or os.environ.get("USER_GUID")
    token = os.environ.get("F1_TOKEN") or os.environ.get("TOKEN")
    
    if not user_guid or not token:
        print("=" * 60)
        print("F1 FANTASY CREDENTIALS NEEDED")
        print("=" * 60)
        print("\nCreate a .env file with:")
        print("  F1_USER_GUID=your-user-id")
        print("  F1_TOKEN=your-F1_FANTASY_007-cookie-value")
        print("=" * 60)
        return
    
    print("F1 Fantasy Budget Tracker - DRS Mafia")
    print("=" * 50)
    
    tracker = F1BudgetTracker(user_guid, token)
    
    # Fetch budget data for all teams
    print(f"\nFetching budget data for {NUM_RACES} races...")
    budget_data = await tracker.get_all_budget_data(LEAGUE_ID, num_races=NUM_RACES)
    
    if not budget_data:
        print("Could not fetch budget data")
        return
    
    print(f"\nGot budget data for {len(budget_data)} users")
    
    # Plot budget evolution
    plot_budget_evolution(budget_data, LEAGUE_NAME, NUM_RACES)


if __name__ == "__main__":
    asyncio.run(main())

