import click
import requests
from rich.table import Table
from cli.config import get_api_url, get_token
from cli.output import console, print_success, print_error, print_info

@click.group(name="health")
def health_group():
    """Code health analysis."""
    pass

@health_group.command(name="check")
@click.argument("app_name")
@click.option("--json", "as_json", is_flag=True, help="Output raw JSON")
def health_check(app_name, as_json):
    """Run a health check on an app."""
    api_url = get_api_url()
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    
    try:
        resp = requests.post(f"{api_url}/health-check/{app_name}", headers=headers)
        if resp.status_code == 200:
            report = resp.json()
            if as_json:
                console.print_json(data=report)
                return
                
            summary = report["summary"]
            
            console.print(f"\n[bold]Health Report: {app_name}[/bold]")
            console.print("━" * 40)
            console.print(f"Score:  [bold green]{report['overall_score']}/100[/]  Grade: [bold cyan]{report['grade']}[/]")
            console.print(f"Files:  {summary['total_files']}      LOC: {summary['total_loc']}")
            console.print()
            
            console.print("[bold]Issues found:[/bold]")
            
            if summary.get("secrets_count", 0) > 0:
                console.print(f"[bold red]⚠  {summary['secrets_count']} hardcoded secrets[/bold]")
            else:
                console.print("[green]✓  No hardcoded secrets[/green]")
                
            if summary.get("functions_over_50_lines", 0) > 0:
                console.print(f"[bold yellow]⚠  {summary['functions_over_50_lines']} functions over 50 lines[/bold]")
            else:
                console.print("[green]✓  No functions over 50 lines[/green]")
                
            if summary.get("bare_excepts_count", 0) > 0:
                console.print(f"[bold red]⚠  {summary['bare_excepts_count']} bare excepts[/bold]")
            else:
                console.print("[green]✓  No bare excepts[/green]")
                
            if summary.get("empty_catches_count", 0) > 0:
                console.print(f"[bold red]⚠  {summary['empty_catches_count']} empty catch blocks[/bold]")
            else:
                console.print("[green]✓  No empty catch blocks[/green]")
            console.print()
            
            # Show top problematic files
            problematic = [f for f in report["file_reports"] if f["issues_count"] > 0]
            if problematic:
                problematic.sort(key=lambda x: x["issues_count"], reverse=True)
                table = Table(title="Top problematic files")
                table.add_column("File Path", style="cyan")
                table.add_column("Rating", style="magenta")
                table.add_column("Issues", style="red")
                
                for f in problematic[:5]: # Top 5
                    # rating dots, e.g. 4 issues out of 5 is ●●●●○
                    dots = "●" * min(5, f["issues_count"]) + "○" * max(0, 5 - f["issues_count"])
                    table.add_row(f["file_path"], dots, f"{f['issues_count']} issues")
                console.print(table)
                console.print()
        else:
            print_error(resp.json().get("detail") or "Failed to run health check.")
    except Exception as e:
        print_error(f"Failed to connect: {e}")

@health_group.command(name="history")
@click.argument("app_name")
def health_history(app_name):
    """Show health score history for an app."""
    api_url = get_api_url()
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    
    try:
        resp = requests.get(f"{api_url}/health-check/{app_name}/history", headers=headers)
        if resp.status_code == 200:
            history = resp.json()
            if not history:
                print_info("No health check history found for this app.")
                return
                
            table = Table(title=f"Health History: {app_name}")
            table.add_column("Date", style="cyan")
            table.add_column("Score", style="green")
            table.add_column("Grade", style="magenta")
            
            for item in history:
                table.add_row(item["generated_at"], str(item["overall_score"]), item["grade"])
            console.print(table)
        else:
            print_error("Failed to retrieve history.")
    except Exception as e:
        print_error(f"Failed to connect: {e}")
