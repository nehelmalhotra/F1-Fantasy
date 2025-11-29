"""
F1 Fantasy League Dashboard - DRS Mafia
Complete dashboard with performance, budget tracking, and efficiency metrics.

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
import matplotlib.patches as mpatches


# Your private league
LEAGUE_ID = 5106507  # DRS Mafia
LEAGUE_NAME = "DRS Mafia"
NUM_RACES = 22

# F1 Team Colors
COLORS = [
    '#E10600', '#00D2BE', '#3671C6', '#FF8700', '#006F62',
    '#FF87BC', '#B6BABD', '#6692FF', '#52E252', '#64C4FF',
    '#FF6B6B', '#C9B037', '#9B59B6', '#1ABC9C', '#E74C3C',
    '#3498DB', '#F39C12', '#2ECC71', '#8E44AD', '#E67E22',
]


def sanitize_name(name: str) -> str:
    """Remove special characters that matplotlib can't handle."""
    safe_name = name.encode('ascii', 'ignore').decode('ascii')
    for char in ['$', '%', '_', '{', '}', '^', '~', '\\']:
        safe_name = safe_name.replace(char, '')
    return safe_name.strip()


class F1FantasyClient:
    """Complete F1 Fantasy API client."""
    
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
    
    async def get_all_race_data(self, league_id: int, num_races: int = 22) -> dict:
        """Fetch race-by-race points data for all teams."""
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
                except Exception as e:
                    print(f"    Error fetching race {race_id}: {e}")
        
        return all_race_data
    
    async def get_all_budget_data(self, league_id: int, num_races: int = 22) -> dict:
        """Fetch budget data for all teams across all races."""
        
        members = await self.get_league_members(league_id)
        
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


def build_user_cumulative_histories(all_race_data: dict) -> dict:
    """Build cumulative point histories grouped by USER."""
    user_histories = {}
    user_cumulative = defaultdict(float)
    
    for race_id in sorted(all_race_data.keys()):
        user_race_points = defaultdict(float)
        for entry in all_race_data[race_id]:
            user_name = entry['user_name']
            user_race_points[user_name] += entry['points'] or 0
        
        for user_name, points in user_race_points.items():
            if user_name not in user_histories:
                user_histories[user_name] = {}
            
            user_cumulative[user_name] += points
            user_histories[user_name][race_id] = user_cumulative[user_name]
    
    return user_histories


def calculate_metrics(user_histories: dict, budget_data: dict, num_teams_per_user: dict) -> dict:
    """Calculate interesting metrics for each user."""
    metrics = {}
    
    for user_name, history in user_histories.items():
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
                starting_budget = 100 * num_teams_per_user.get(user_name, 2)  # $100M per team
            else:
                final_team_val = starting_budget = 0
        else:
            final_team_val = starting_budget = 0
        
        # Calculate metrics
        budget_gain = final_team_val - starting_budget if starting_budget > 0 else 0
        
        # Points per $M invested (efficiency)
        # Using average team value as the "investment"
        avg_team_val = (starting_budget + final_team_val) / 2 if final_team_val > 0 else starting_budget
        points_per_million = total_points / avg_team_val if avg_team_val > 0 else 0
        
        # ROI: (final_value - starting) / starting * 100
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


def plot_cumulative_performance(user_histories: dict, league_name: str, num_races: int = 22):
    """Plot cumulative performance grouped by user."""
    
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(16, 10))
    
    final_race = max(list(user_histories.values())[0].keys())
    sorted_users = sorted(
        [(name, hist) for name, hist in user_histories.items() 
         if (hist.get(final_race, 0) or 0) > 0],
        key=lambda x: x[1].get(final_race, 0) or 0,
        reverse=True
    )
    
    for idx, (user_name, history) in enumerate(sorted_users):
        color = COLORS[idx % len(COLORS)]
        races = sorted(history.keys())
        points = [history[r] or 0 for r in races]
        
        safe_name = sanitize_name(user_name)[:20]
        final_pts = history.get(final_race, 0) or 0
        
        ax.plot(races, points, marker='o', linewidth=2.5, markersize=5,
               label=f'{safe_name} ({final_pts:,.0f})', color=color)
    
    ax.set_title(f'Cumulative Points - {league_name}',
                fontsize=20, fontweight='bold', pad=20, color='white')
    ax.set_xlabel('Race Weekend', fontsize=14, color='white')
    ax.set_ylabel('Cumulative Points', fontsize=14, color='white')
    ax.legend(loc='upper left', fontsize=9, ncol=1, bbox_to_anchor=(1.02, 1), framealpha=0.9)
    ax.grid(True, alpha=0.3, linestyle='--')
    ax.set_facecolor('#1a1a2e')
    fig.patch.set_facecolor('#0f0f1a')
    ax.set_xticks(range(1, num_races + 1))
    ax.tick_params(colors='white')
    
    plt.tight_layout()
    plt.subplots_adjust(right=0.72)
    
    safe_league = league_name.replace(' ', '_').replace('/', '_')
    filename = f"f1_points_{safe_league}.png"
    plt.savefig(filename, dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor())
    print(f"  Points chart saved: {filename}")
    
    plt.show()
    return sorted_users


def plot_budget_evolution(budget_data: dict, league_name: str, num_races: int = 22):
    """Plot team value evolution for all users."""
    
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(16, 10))
    
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
    
    for idx, (user_name, history) in enumerate(sorted_users):
        color = COLORS[idx % len(COLORS)]
        
        valid_races = sorted([r for r in history.keys() if history[r]['max_team_bal'] > 0])
        if not valid_races:
            continue
            
        values = [history[r]['max_team_bal'] for r in valid_races]
        safe_name = sanitize_name(user_name)[:20]
        final_val = values[-1] if values else 0
        
        ax.plot(valid_races, values, marker='o', linewidth=2.5, markersize=5,
               label=f'{safe_name} (${final_val:,.1f}M)', color=color)
    
    # Starting budget reference line (assuming 2 teams per user = $200M)
    ax.axhline(y=200, color='white', linestyle='--', alpha=0.5, linewidth=1)
    ax.text(1.5, 202, 'Starting Budget ($200M for 2 teams)', color='white', alpha=0.7, fontsize=10)
    
    ax.set_title(f'Team Value Evolution - {league_name}',
                fontsize=20, fontweight='bold', pad=20, color='white')
    ax.set_xlabel('Race Weekend', fontsize=14, color='white')
    ax.set_ylabel('Combined Team Value ($M)', fontsize=14, color='white')
    ax.legend(loc='upper left', fontsize=9, ncol=1, bbox_to_anchor=(1.02, 1), framealpha=0.9)
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
    print(f"  Budget chart saved: {filename}")
    
    plt.show()
    return sorted_users


def plot_efficiency_metrics(metrics: dict, league_name: str):
    """Plot efficiency metrics - Points per $M and ROI."""
    
    plt.style.use('dark_background')
    fig, axes = plt.subplots(1, 2, figsize=(18, 8))
    
    # Sort by points per million (efficiency)
    sorted_by_efficiency = sorted(
        [(name, m) for name, m in metrics.items() if m['points_per_million'] > 0],
        key=lambda x: x[1]['points_per_million'],
        reverse=True
    )
    
    # Plot 1: Points per $M (Efficiency)
    ax1 = axes[0]
    names = [sanitize_name(n)[:15] for n, _ in sorted_by_efficiency]
    efficiency = [m['points_per_million'] for _, m in sorted_by_efficiency]
    colors_eff = [COLORS[i % len(COLORS)] for i in range(len(names))]
    
    bars1 = ax1.barh(names, efficiency, color=colors_eff, edgecolor='white', linewidth=0.5)
    ax1.set_xlabel('Points per $M Invested', fontsize=12, color='white')
    ax1.set_title('Efficiency: Points per $M', fontsize=16, fontweight='bold', color='white')
    ax1.invert_yaxis()
    ax1.set_facecolor('#1a1a2e')
    ax1.tick_params(colors='white')
    
    # Add value labels
    for bar, val in zip(bars1, efficiency):
        ax1.text(val + 0.5, bar.get_y() + bar.get_height()/2, f'{val:.1f}',
                va='center', color='white', fontsize=10)
    
    # Plot 2: ROI % (Budget Growth)
    ax2 = axes[1]
    sorted_by_roi = sorted(
        [(name, m) for name, m in metrics.items() if m['roi_percent'] != 0],
        key=lambda x: x[1]['roi_percent'],
        reverse=True
    )
    
    names_roi = [sanitize_name(n)[:15] for n, _ in sorted_by_roi]
    roi = [m['roi_percent'] for _, m in sorted_by_roi]
    colors_roi = ['#52E252' if r >= 0 else '#E10600' for r in roi]
    
    bars2 = ax2.barh(names_roi, roi, color=colors_roi, edgecolor='white', linewidth=0.5)
    ax2.set_xlabel('ROI %', fontsize=12, color='white')
    ax2.set_title('Team Value ROI %', fontsize=16, fontweight='bold', color='white')
    ax2.axvline(x=0, color='white', linestyle='-', alpha=0.3)
    ax2.invert_yaxis()
    ax2.set_facecolor('#1a1a2e')
    ax2.tick_params(colors='white')
    
    # Add value labels
    for bar, val in zip(bars2, roi):
        xpos = val + 2 if val >= 0 else val - 8
        ax2.text(xpos, bar.get_y() + bar.get_height()/2, f'{val:+.1f}%',
                va='center', color='white', fontsize=10)
    
    fig.patch.set_facecolor('#0f0f1a')
    plt.tight_layout()
    
    safe_league = league_name.replace(' ', '_').replace('/', '_')
    filename = f"f1_efficiency_{safe_league}.png"
    plt.savefig(filename, dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor())
    print(f"  Efficiency chart saved: {filename}")
    
    plt.show()


def print_leaderboard(metrics: dict, user_histories: dict, budget_data: dict):
    """Print comprehensive leaderboard with all metrics."""
    
    print("\n" + "=" * 100)
    print("                            F1 FANTASY LEAGUE DASHBOARD - DRS MAFIA")
    print("=" * 100)
    
    # Sort by total points
    sorted_users = sorted(
        metrics.items(),
        key=lambda x: x[1]['total_points'],
        reverse=True
    )
    
    print("\n📊 OVERALL STANDINGS (by Points)")
    print("-" * 100)
    print(f"{'Rank':<5} {'User':<25} {'Points':>10} {'Team Value':>12} {'Gain':>10} {'Pts/$M':>10} {'ROI':>10}")
    print("-" * 100)
    
    for idx, (user_name, m) in enumerate(sorted_users, 1):
        medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else "  "
        gain_str = f"+${m['budget_gain']:.1f}M" if m['budget_gain'] >= 0 else f"-${abs(m['budget_gain']):.1f}M"
        roi_str = f"+{m['roi_percent']:.1f}%" if m['roi_percent'] >= 0 else f"{m['roi_percent']:.1f}%"
        
        print(f"{medal}{idx:<3} {user_name:<25} {m['total_points']:>10,.0f} "
              f"${m['final_team_val']:>10.1f}M {gain_str:>10} "
              f"{m['points_per_million']:>9.1f} {roi_str:>10}")
    
    # Efficiency Rankings
    print("\n\n🎯 EFFICIENCY RANKINGS (Points per $M invested)")
    print("-" * 60)
    sorted_efficiency = sorted(
        [(n, m) for n, m in metrics.items() if m['points_per_million'] > 0],
        key=lambda x: x[1]['points_per_million'],
        reverse=True
    )
    
    for idx, (user_name, m) in enumerate(sorted_efficiency, 1):
        emoji = "⚡" if idx <= 3 else "  "
        print(f"  {emoji} {idx}. {user_name:<25} - {m['points_per_million']:.2f} pts/$M")
    
    # Best Team Value Growth
    print("\n\n💰 BEST TEAM VALUE GROWTH (ROI)")
    print("-" * 60)
    sorted_roi = sorted(
        [(n, m) for n, m in metrics.items() if m['roi_percent'] != 0],
        key=lambda x: x[1]['roi_percent'],
        reverse=True
    )
    
    for idx, (user_name, m) in enumerate(sorted_roi, 1):
        emoji = "📈" if m['roi_percent'] > 0 else "📉"
        sign = "+" if m['roi_percent'] >= 0 else ""
        print(f"  {emoji} {idx}. {user_name:<25} - {sign}{m['roi_percent']:.1f}% "
              f"(${m['starting_budget']:.0f}M → ${m['final_team_val']:.1f}M)")
    
    print("\n" + "=" * 100)


async def main():
    """Main function to run the complete dashboard."""
    
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
    
    print("\n🏎️  F1 FANTASY DASHBOARD - DRS Mafia")
    print("=" * 50)
    
    client = F1FantasyClient(user_guid, token)
    
    # Fetch all data
    print("\n📡 Fetching data...")
    
    print("  • Race-by-race points data...")
    all_race_data = await client.get_all_race_data(LEAGUE_ID, num_races=NUM_RACES)
    print(f"    Got data for {len(all_race_data)} races")
    
    print("  • Budget/team value data...")
    members = await client.get_league_members(LEAGUE_ID)
    
    # Count teams per user
    num_teams_per_user = defaultdict(int)
    for m in members:
        num_teams_per_user[m['user_name']] += 1
    
    budget_data = await client.get_all_budget_data(LEAGUE_ID, num_races=NUM_RACES)
    print(f"    Got budget data for {len(budget_data)} users")
    
    if not all_race_data:
        print("Could not fetch race data")
        return
    
    # Build histories and calculate metrics
    user_histories = build_user_cumulative_histories(all_race_data)
    metrics = calculate_metrics(user_histories, budget_data, num_teams_per_user)
    
    # Print comprehensive leaderboard
    print_leaderboard(metrics, user_histories, budget_data)
    
    # Generate plots
    print("\n📊 Generating charts...")
    plot_cumulative_performance(user_histories, LEAGUE_NAME, NUM_RACES)
    plot_budget_evolution(budget_data, LEAGUE_NAME, NUM_RACES)
    plot_efficiency_metrics(metrics, LEAGUE_NAME)
    
    print("\n✅ Dashboard complete!")


if __name__ == "__main__":
    asyncio.run(main())
