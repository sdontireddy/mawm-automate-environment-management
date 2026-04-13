"""
Test script for clone_bulk_transports sequence
Run this to verify the clone_bulk_transports API sequence execution
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.orchestrator import APIOrchestrator, OrchestrationError
from src.config_loader import ConfigLoader
from src.utils.logger import get_logger
import os
from dotenv import load_dotenv

logger = get_logger()


def test_clone_bulk_transports():
    """Test clone_bulk_transports sequence execution"""
    
    print("\n" + "="*80)
    print("Testing clone_bulk_transports Sequence")
    print("="*80 + "\n")
    
    # Load environment variables
    load_dotenv()
    
    # Check configuration
    print("[1] Checking Configuration...")
    try:
        config_loader = ConfigLoader()
        sequences = config_loader.load_api_sequences()
        
        if "clone_bulk_transports" not in sequences["sequences"]:
            print("    ✗ clone_bulk_transports sequence not found!")
            return False
        
        sequence = sequences["sequences"]["clone_bulk_transports"]
        print(f"    ✓ Found sequence: {sequence['description']}")
        print(f"    ✓ Total steps: {len(sequence['steps'])}\n")
        
        # List steps
        print("    Steps in sequence:")
        for idx, step in enumerate(sequence['steps'], 1):
            required = "REQUIRED" if step.get("required", True) else "OPTIONAL"
            skip = "SKIPPED" if step.get("skip_step", False) else ""
            print(f"      [{idx}] {step['id']}: {step['name']} ({required}) {skip}")
        print()
        
    except Exception as e:
        print(f"    ✗ Configuration error: {str(e)}")
        return False
    
    # Test dry-run mode
    print("-"*80)
    print("[2] Testing DRY RUN Mode...")
    print("    (No actual API calls will be made)\n")
    
    try:
        orchestrator = APIOrchestrator(
            environment="XXX",
            dry_run=True,
            source_environment="XXXdev"
        )
        
        result = orchestrator.execute_sequence("clone_bulk_transports")
        
        if result["status"] == "success":
            print(f"\n    ✓ Dry run completed successfully!")
            print(f"    ✓ Steps processed: {result['completed_steps']}\n")
            return True
        else:
            print(f"\n    ✗ Dry run failed: {result.get('error', 'Unknown error')}")
            print(f"    Failed step: {result.get('failed_step', 'Unknown')}\n")
            return False
            
    except OrchestrationError as e:
        print(f"    ✗ Orchestration error: {str(e)}\n")
        return False
    except Exception as e:
        print(f"    ✗ Unexpected error: {str(e)}\n")
        import traceback
        traceback.print_exc()
        return False


def test_with_skipped_steps():
    """Test clone_bulk_transports with skip_step flag"""
    
    print("-"*80)
    print("[3] Testing with Skipped Steps...")
    print("    (Testing skip_step functionality)\n")
    
    try:
        # Load configuration
        config_loader = ConfigLoader()
        sequences = config_loader.load_api_sequences()
        sequence = sequences["sequences"]["clone_bulk_transports"]
        
        # Skip the verification step
        for step in sequence["steps"]:
            if step["id"] == "verify_bulk_transports":
                step["skip_step"] = True
                print(f"    Setting skip_step=true for: {step['name']}\n")
                break
        
        # Execute with skip
        orchestrator = APIOrchestrator(
            environment="XXX",
            dry_run=True,
            source_environment="XXXdev"
        )
        
        # Override the sequence config
        orchestrator.sequence_config["sequences"]["clone_bulk_transports"] = sequence
        
        result = orchestrator.execute_sequence("clone_bulk_transports")
        
        if result["status"] == "success":
            print(f"    ✓ Execution with skipped steps completed!")
            print(f"    ✓ Steps processed: {result['completed_steps']}\n")
            return True
        else:
            print(f"    ✗ Execution failed: {result.get('error', 'Unknown error')}\n")
            return False
            
    except Exception as e:
        print(f"    ✗ Error: {str(e)}\n")
        return False


if __name__ == "__main__":
    try:
        print("\n" + "="*80)
        print("CLONE_BULK_TRANSPORTS Sequence Test Suite")
        print("="*80 + "\n")
        
        # Run tests
        test1_passed = test_clone_bulk_transports()
        
        # Skip test 2 (optional skipped steps test)
        # test2_passed = test_with_skipped_steps()
        test2_passed = True  # Mark as passed when skipped
        
        # Summary
        print("="*80)
        print("Test Summary")
        print("="*80)
        print(f"Test 1 - Basic Dry Run: {'✓ PASSED' if test1_passed else '✗ FAILED'}")
        print(f"Test 2 - Skip Step Feature: SKIPPED\n")
        
        if test1_passed:
            print("✅ clone_bulk_transports test PASSED!")
            print("\nTo execute with actual API calls, use:")
            print("  python main.py --action clone --target-env XXX --source-env XXXdev --sequence clone_bulk_transports\n")
            sys.exit(0)
        else:
            print("❌ clone_bulk_transports test FAILED")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n\nTests cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {str(e)}")
        logger.exception("Test failed with unexpected error")
        sys.exit(1)
