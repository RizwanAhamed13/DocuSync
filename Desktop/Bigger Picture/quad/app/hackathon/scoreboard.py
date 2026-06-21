from app.hackathon.service import get_hackathon, list_teams, get_team_scores
import datetime

def calculate_scoreboard(hackathon_id: str) -> list[dict]:
    hackathon = get_hackathon(hackathon_id)
    if not hackathon:
        raise ValueError("Hackathon not found.")
        
    teams = list_teams(hackathon_id)
    criteria = hackathon.get("judging_criteria", [])
    
    scorecards = []
    for team in teams:
        scores = get_team_scores(team["hack_team_id"])
        
        # Group scores by criterion: {criterion: [scores]}
        grouped_scores = {c: [] for c in criteria}
        for s in scores:
            c = s["criterion"]
            if c in grouped_scores:
                grouped_scores[c].append(s["score"])
                
        # Calculate average per criterion
        criteria_averages = {}
        for c in criteria:
            c_scores = grouped_scores[c]
            criteria_averages[c] = float(sum(c_scores)) / len(c_scores) if c_scores else 0.0
            
        total_score = sum(criteria_averages.values())
        
        # Parse submission time for tie-breaking
        sub_time = team.get("submitted_at")
        if sub_time:
            try:
                dt_val = datetime.datetime.strptime(sub_time, "%Y-%m-%d %H:%M:%S")
            except Exception:
                dt_val = datetime.datetime.max
        else:
            dt_val = datetime.datetime.max
            
        scorecards.append({
            "hack_team_id": team["hack_team_id"],
            "team_name": team["team_name"],
            "project_title": team.get("project_title"),
            "project_description": team.get("project_description"),
            "submitted_at": sub_time,
            "members": team["members"],
            "leader_username": team["leader_username"],
            "criteria_scores": criteria_averages,
            "total_score": total_score,
            "sub_datetime": dt_val
        })
        
    # Tie breaking:
    # 1. Total score (descending)
    # 2. Score on primary/first criterion (descending)
    # 3. Submission time (ascending)
    primary_criterion = criteria[0] if criteria else None
    
    def sort_key(card):
        p_score = card["criteria_scores"].get(primary_criterion, 0.0) if primary_criterion else 0.0
        # For sorting: total_score desc -> -total_score; p_score desc -> -p_score; sub_datetime asc -> card["sub_datetime"]
        return (-card["total_score"], -p_score, card["sub_datetime"])
        
    scorecards.sort(key=sort_key)
    
    # Assign ranks
    for rank_idx, card in enumerate(scorecards, 1):
        card["rank"] = rank_idx
        # Remove helper datetime field before returning
        card.pop("sub_datetime", None)
        
    return scorecards
