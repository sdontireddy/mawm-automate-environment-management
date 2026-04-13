"""
Main entry point for MAWM Environment Management Automation
"""
import click
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.orchestrator import APIOrchestrator, OrchestrationError
from src.config_loader import ConfigLoader
from src.utils.validators import InputValidator, ValidationError
from src.utils.logger import get_logger

logger = get_logger()


def _show_execution_plan_and_confirm(action, sequence, dry_run, orchestrator, config_loader):
    """Display execution plan and wait for user confirmation"""
    try:
        # Load sequence steps
        sequence_config = config_loader.load_api_sequences()
        if sequence not in sequence_config.get("sequences", {}):
            click.echo(click.style(f"❌ Sequence '{sequence}' not found", fg='red'))
            sys.exit(1)
        
        steps = sequence_config["sequences"][sequence].get("steps", [])
        seq_description = sequence_config["sequences"][sequence].get("description", "No description")
        
        # Display execution plan
        click.echo("\n" + "="*80)
        click.echo(click.style("EXECUTION PLAN", fg='cyan', bold=True))
        click.echo("="*80)
        
        click.echo(f"\nSequence: {click.style(sequence, fg='yellow')}")
        click.echo(f"Description: {seq_description}")
        
        click.echo(f"\nExecution Options:")
        click.echo(f"  Action: {click.style(action, fg='blue')}")
        
        # Get source and target location names
        source_name = orchestrator.source_config.get("environment", {}).get("name", "source") if orchestrator.source_config else "source"
        target_name = orchestrator.env_config.get("environment", {}).get("name", "target")
        
        click.echo(f"  Source Environment: {click.style(f'{source_name} (from config)', fg='blue')}")
        click.echo(f"  Target Environment: {click.style(f'{target_name} (from config)', fg='blue')}")
        click.echo(f"  Run ID: {click.style(orchestrator.run_id, fg='blue')}")
        click.echo(f"  Dry Run: {click.style('YES' if dry_run else 'NO', fg='green' if dry_run else 'red')}")
        
        # Display steps
        click.echo(f"\nSteps to be executed ({len(steps)} total):")
        click.echo("-" * 80)
        
        for idx, step in enumerate(steps, 1):
            step_id = step.get("id", "unknown")
            step_name = step.get("name", "Unknown")
            required = step.get("required", True)
            skip = step.get("skip_step", False)
            method = step.get("method", "")
            endpoint = step.get("endpoint", "")
            target = step.get("target", "destination").upper()
            
            status_icon = "[SKIP]" if skip else ">"
            required_badge = click.style("[REQUIRED]", fg='red') if required else click.style("[OPTIONAL]", fg='yellow')
            
            click.echo(f"\n  [{idx}] {status_icon} {step_name}")
            click.echo(f"      ID: {step_id}")
            click.echo(f"      Method: {method} {endpoint}")
            click.echo(f"      Target: {target}")
            click.echo(f"      {required_badge}")
            
            if skip:
                click.echo(f"      {click.style('(This step will be skipped)', fg='yellow')}")
        
        click.echo("\n" + "="*80)
        
        # Wait for confirmation
        if dry_run:
            click.echo(click.style("\n[!] This is a DRY RUN - no actual changes will be made", fg='yellow', bold=True))
        
        confirmation = click.confirm(
            click.style("\nDo you want to proceed with this execution?", fg='cyan', bold=True),
            default=False
        )
        
        if not confirmation:
            click.echo(click.style("\n[X] Execution cancelled by user", fg='yellow'))
            sys.exit(0)
        
        click.echo(click.style("\n[OK] Proceeding with execution...\n", fg='green'))
        logger.info(f"User confirmed execution of sequence '{sequence}'")
        
    except Exception as e:
        import traceback
        error_msg = str(e) if str(e) else "Unknown error"
        click.echo(click.style(f"Error preparing execution plan: {error_msg}", fg='red'))
        logger.error(f"Error in execution plan: {error_msg}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        sys.exit(1)


@click.command()
@click.option(
    '--action',
    type=click.Choice(['create', 'validate', 'destroy', 'clone'], case_sensitive=False),
    required=True,
    help='Action to perform'
)
@click.option(
    '--sequence',
    type=str,
    default=None,
    help='Sequence name to execute (auto-selected based on action if not provided)'
)
@click.option(
    '--dry-run',
    is_flag=True,
    default=False,
    help='Simulate execution without making actual API calls'
)
@click.option(
    '--verbose',
    is_flag=True,
    default=False,
    help='Enable verbose logging'
)
def main(action: str, sequence: str, dry_run: bool, verbose: bool):
    """
    MAWM Environment Management Automation Tool
    
    Automate creation and management of Manhattan WMS environments through
    sequential API execution. Uses "source" and "target" environments from config.
    
    Examples:
    
        Create a new development environment:
        $ python main.py --action create --env dev
        
        Clone from golden environment to dev:
        $ python main.py --action clone --env dev
        
        Clone from specific source to QA:
        $ python main.py --action clone --env qa --source-env golden
        
        Validate existing QA environment:
        $ python main.py --action validate --env qa
        
        Dry run (no actual API calls):
        $ python main.py --action clone --env dev --dry-run
    """
    try:
        logger.info("MAWM Environment Management Automation")
        logger.info(f"Action: {action}")
        logger.info(f"Dry Run: {dry_run}")
        
        # Fixed environments: source and target
        target_env = "target"
        source_env = "source"
        
        # Validate inputs
        config_loader = ConfigLoader()
        validator = InputValidator()
        validator.validate_action(action, ['create', 'validate', 'destroy', 'clone'])
        
        # Auto-select sequence if not provided
        if not sequence:
            if action == 'clone':
                sequence = 'clone_bulk_transports'
            elif action == 'create':
                sequence = 'create_environment'
            elif action == 'validate':
                sequence = 'verify_environment'
            elif action == 'destroy':
                sequence = 'destroy_environment'
        
        logger.info(f"Sequence: {sequence}")
        
        # Create orchestrator
        orchestrator = APIOrchestrator(
            environment=target_env, 
            dry_run=dry_run,
            source_environment=source_env
        )
        
        # Show execution plan and get user confirmation
        _show_execution_plan_and_confirm(
            action=action,
            sequence=sequence,
            dry_run=dry_run,
            orchestrator=orchestrator,
            config_loader=config_loader
        )
        
        # Execute sequence based on action
        result = orchestrator.execute_sequence(sequence)
        
        # Display results
        if result["status"] == "success":
            click.echo(click.style("\n[SUCCESS] Operation completed successfully!", fg='green', bold=True))
            click.echo(f"Completed steps: {result['completed_steps']}")
            
            if dry_run:
                click.echo(click.style("\nNote: This was a dry run. No actual changes were made.", fg='yellow'))
            
            sys.exit(0)
        else:
            click.echo(click.style("\n[FAILED] Operation failed!", fg='red', bold=True))
            click.echo(f"Error: {result.get('error', 'Unknown error')}")
            click.echo(f"Failed at step: {result.get('failed_step', 'Unknown')}")
            click.echo(f"Completed steps: {len(result.get('completed_steps', []))}")
            sys.exit(1)
            
    except ValidationError as e:
        click.echo(click.style(f"\n[ERROR] Validation Error: {str(e)}", fg='red'))
        logger.error(f"Validation error: {str(e)}")
        sys.exit(1)
    except OrchestrationError as e:
        click.echo(click.style(f"\n[ERROR] Orchestration Error: {str(e)}", fg='red'))
        logger.error(f"Orchestration error: {str(e)}")
        sys.exit(1)
    except Exception as e:
        click.echo(click.style(f"\n[ERROR] Unexpected Error: {str(e)}", fg='red'))
        logger.exception("Unexpected error occurred")
        sys.exit(1)


if __name__ == '__main__':
    main()
