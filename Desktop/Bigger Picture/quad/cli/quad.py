import click
from cli.commands.auth import auth_group
from cli.commands.apps import apps_group
from cli.commands.deploy import deploy_command
from cli.commands.share import share_command
from cli.commands.ai import ai_group
from cli.commands.health import health_group

@click.group()
def cli():
    """Quad CLI - Campus Deployments & AI Playground."""
    pass

cli.add_command(auth_group)
cli.add_command(apps_group)
cli.add_command(deploy_command)
cli.add_command(share_command)
cli.add_command(ai_group)
cli.add_command(health_group)

if __name__ == "__main__":
    cli()
