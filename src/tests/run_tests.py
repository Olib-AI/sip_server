#!/usr/bin/env python3
"""
Test runner script for SIP server comprehensive test suite.
Validates all test components and provides detailed reporting.
"""
import sys
import os
import subprocess
import asyncio
import time
from pathlib import Path
from typing import Dict, List, Any
import json

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

def run_command(command: List[str], timeout: int = 300) -> Dict[str, Any]:
    """Run command and return results."""
    print(f"Running: {' '.join(command)}")
    start_time = time.time()
    
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=Path(__file__).parent.parent.parent
        )
        
        end_time = time.time()
        duration = end_time - start_time
        
        return {
            "command": ' '.join(command),
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "duration": duration,
            "success": result.returncode == 0
        }
        
    except subprocess.TimeoutExpired:
        return {
            "command": ' '.join(command),
            "returncode": -1,
            "stdout": "",
            "stderr": f"Command timed out after {timeout} seconds",
            "duration": timeout,
            "success": False
        }
    except Exception as e:
        return {
            "command": ' '.join(command),
            "returncode": -2,
            "stdout": "",
            "stderr": str(e),
            "duration": 0,
            "success": False
        }


def validate_test_structure():
    """Validate test directory structure."""
    print("\\n=== Validating Test Structure ===")
    
    test_dir = Path(__file__).parent
    required_dirs = [
        "unit",
        "integration", 
        "e2e",
        "load",
        "performance"
    ]
    
    required_files = [
        "__init__.py",
        "conftest.py",
        "run_tests.py"
    ]
    
    # Check directories
    missing_dirs = []
    for dir_name in required_dirs:
        dir_path = test_dir / dir_name
        if not dir_path.exists():
            missing_dirs.append(dir_name)
        else:
            print(f"✓ {dir_name}/ directory exists")
    
    # Check files
    missing_files = []
    for file_name in required_files:
        file_path = test_dir / file_name
        if not file_path.exists():
            missing_files.append(file_name)
        else:
            print(f"✓ {file_name} exists")
    
    # Check unit tests
    unit_dir = test_dir / "unit"
    unit_test_files = [
        "test_call_manager.py",
        "test_websocket_bridge.py", 
        "test_audio_processing.py",
        "test_dtmf_processing.py",
        "test_sms_handling.py"
    ]
    
    missing_unit_tests = []
    for test_file in unit_test_files:
        test_path = unit_dir / test_file
        if test_path.exists():
            print(f"✓ unit/{test_file} exists")
        else:
            missing_unit_tests.append(test_file)
    
    # Check integration tests
    integration_dir = test_dir / "integration"
    integration_test_files = [
        "test_api_endpoints.py",
        "test_websocket_integration.py"
    ]
    
    missing_integration_tests = []
    for test_file in integration_test_files:
        test_path = integration_dir / test_file
        if test_path.exists():
            print(f"✓ integration/{test_file} exists")
        else:
            missing_integration_tests.append(test_file)
    
    # Report results
    all_valid = (
        not missing_dirs and 
        not missing_files and 
        not missing_unit_tests and 
        not missing_integration_tests
    )
    
    if missing_dirs:
        print(f"✗ Missing directories: {missing_dirs}")
    if missing_files:
        print(f"✗ Missing files: {missing_files}")
    if missing_unit_tests:
        print(f"✗ Missing unit tests: {missing_unit_tests}")
    if missing_integration_tests:
        print(f"✗ Missing integration tests: {missing_integration_tests}")
    
    if all_valid:
        print("✓ Test structure validation passed")
    else:
        print("✗ Test structure validation failed")
    
    return all_valid


def run_test_suite(category: str = "all", verbose: bool = True) -> Dict[str, Any]:
    """Run specific test category."""
    print(f"\\n=== Running {category.upper()} Tests ===")
    
    base_cmd = ["python", "-m", "pytest"]
    
    if verbose:
        base_cmd.append("-v")
    
    # Add coverage 
    base_cmd.extend(["--cov=src", "--cov-report=term-missing"])
    
    # Category-specific commands
    if category == "unit":
        cmd = base_cmd + ["src/tests/unit/"]
    elif category == "integration":
        cmd = base_cmd + ["src/tests/integration/"]
    elif category == "e2e":
        cmd = base_cmd + ["src/tests/e2e/"]
    elif category == "load":
        cmd = base_cmd + ["src/tests/load/"]
    elif category == "performance":
        cmd = base_cmd + ["src/tests/performance/"]
    elif category == "all":
        cmd = base_cmd + ["src/tests/"]
    else:
        cmd = base_cmd + [f"src/tests/{category}"]
    
    # Skip markers - not all tests have them
    # if category != "all":
    #     cmd.extend(["-m", category])
    
    return run_command(cmd, timeout=600)  # 10 minute timeout


def run_syntax_validation():
    """Validate Python syntax in all test files."""
    print("\\n=== Validating Python Syntax ===")
    
    test_files = []
    test_dir = Path(__file__).parent
    
    # Find all Python test files
    for pattern in ["**/*.py"]:
        test_files.extend(test_dir.glob(pattern))
    
    syntax_errors = []
    
    for test_file in test_files:
        try:
            with open(test_file, 'r', encoding='utf-8') as f:
                compile(f.read(), test_file, 'exec')
            print(f"✓ {test_file.relative_to(test_dir)}")
        except SyntaxError as e:
            syntax_errors.append(f"{test_file}: {e}")
            print(f"✗ {test_file.relative_to(test_dir)}: {e}")
        except Exception as e:
            syntax_errors.append(f"{test_file}: {e}")
            print(f"✗ {test_file.relative_to(test_dir)}: {e}")
    
    if not syntax_errors:
        print("✓ All test files have valid Python syntax")
        return True
    else:
        print(f"✗ Found {len(syntax_errors)} syntax errors")
        return False


def run_import_validation():
    """Validate that all imports work correctly."""
    print("\\n=== Validating Imports ===")
    
    # Test core imports
    try:
        import pytest
        print("✓ pytest imported successfully")
    except ImportError as e:
        print(f"✗ Failed to import pytest: {e}")
        return False
    
    try:
        import pytest_asyncio
        print("✓ pytest-asyncio imported successfully")
    except ImportError as e:
        print(f"✗ Failed to import pytest-asyncio: {e}")
        return False
    
    # Test project imports
    try:
        from src.call_handling.call_manager import CallManager
        print("✓ CallManager imported successfully")
    except ImportError as e:
        print(f"✗ Failed to import CallManager: {e}")
        return False
    
    try:
        from src.websocket.bridge import WebSocketBridge
        print("✓ WebSocketBridge imported successfully")
    except ImportError as e:
        print(f"✗ Failed to import WebSocketBridge: {e}")
        return False
    
    try:
        from src.api.main import app
        print("✓ FastAPI app imported successfully")
    except ImportError as e:
        print(f"✗ Failed to import FastAPI app: {e}")
        return False
    
    print("✓ All imports validated successfully")
    return True


def generate_test_report(results: Dict[str, Any]):
    """Generate comprehensive test report."""
    print("\\n" + "="*60)
    print("COMPREHENSIVE TEST REPORT")
    print("="*60)
    
    total_duration = sum(r.get("duration", 0) for r in results.values() if isinstance(r, dict))
    successful_tests = [k for k, v in results.items() if isinstance(v, dict) and v.get("success", False)]
    failed_tests = [k for k, v in results.items() if isinstance(v, dict) and not v.get("success", False)]
    
    print(f"\\nTotal Test Duration: {total_duration:.2f} seconds")
    print(f"Successful Test Categories: {len(successful_tests)}")
    print(f"Failed Test Categories: {len(failed_tests)}")
    
    print(f"\\nTest Results by Category:")
    for category, result in results.items():
        if isinstance(result, dict):
            status = "✓ PASSED" if result["success"] else "✗ FAILED"
            duration = result.get("duration", 0)
            print(f"  {category:20} {status:10} ({duration:.2f}s)")
        else:
            status = "✓ PASSED" if result else "✗ FAILED" 
            print(f"  {category:20} {status:10}")
    
    if failed_tests:
        print(f"\\nFailed Test Details:")
        for category in failed_tests:
            result = results[category]
            if isinstance(result, dict):
                print(f"\\n{category}:")
                if result.get("stderr"):
                    print(f"Error: {result['stderr']}")
                if result.get("stdout"):
                    # Show last few lines of output
                    lines = result["stdout"].split("\\n")
                    relevant_lines = [line for line in lines[-20:] if line.strip()]
                    for line in relevant_lines:
                        print(f"  {line}")
    
    # Overall assessment
    overall_success = len(failed_tests) == 0 and results.get("structure_validation", False)
    
    print(f"\\n{'='*60}")
    if overall_success:
        print("🎉 ALL TESTS PASSED - SYSTEM IS READY FOR PRODUCTION!")
    else:
        print("⚠️  SOME TESTS FAILED - REVIEW REQUIRED BEFORE DEPLOYMENT")
    print(f"{'='*60}")
    
    return overall_success


def run_docker_validation():
    """Run validation using docker-compose as specified in LOCAL_DEBUG.md."""
    print("\\n=== Docker Compose Validation ===")
    
    # Check if docker-compose.yml exists
    compose_file = Path(__file__).parent.parent.parent / "docker-compose.yml"
    if not compose_file.exists():
        print("✗ docker-compose.yml not found")
        return False
    
    print("✓ docker-compose.yml found")
    
    # Check docker and docker-compose availability
    docker_check = run_command(["docker", "--version"])
    if not docker_check["success"]:
        print("✗ Docker not available")
        return False
    
    print("✓ Docker is available")
    
    compose_check = run_command(["docker-compose", "--version"])
    if not compose_check["success"]:
        print("✗ Docker Compose not available")
        return False
    
    print("✓ Docker Compose is available")
    
    # Note: We won't actually start the services in the test validation
    # as that would require actual infrastructure
    print("📝 Docker validation completed (services not started in test mode)")
    
    return True


def main():
    """Main test execution function."""
    print("OLIB AI SIP SERVER - COMPREHENSIVE TEST SUITE")
    print("="*60)
    
    results = {}
    
    # Step 1: Structure validation
    results["structure_validation"] = validate_test_structure()
    
    # Step 2: Syntax validation
    results["syntax_validation"] = run_syntax_validation()
    
    # Step 3: Import validation  
    results["import_validation"] = run_import_validation()
    
    # Step 4: Docker validation
    results["docker_validation"] = run_docker_validation()
    
    # Only run tests if basic validations pass
    if results["syntax_validation"] and results["import_validation"]:
        
        # Step 5: Run test categories
        test_categories = ["unit", "integration", "e2e"]
        
        for category in test_categories:
            print(f"\\n{'='*20} {category.upper()} TESTS {'='*20}")
            results[f"{category}_tests"] = run_test_suite(category, verbose=True)
        
        # Step 6: Run all tests together
        print(f"\\n{'='*20} ALL TESTS {'='*20}")
        results["all_tests"] = run_test_suite("all", verbose=False)
    
    else:
        print("\\n⚠️  Skipping test execution due to validation failures")
    
    # Step 7: Generate comprehensive report
    overall_success = generate_test_report(results)
    
    # Return appropriate exit code
    sys.exit(0 if overall_success else 1)


if __name__ == "__main__":
    main()