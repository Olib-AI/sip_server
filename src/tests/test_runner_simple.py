#!/usr/bin/env python3
"""
Simplified test runner to validate core functionality
"""
import subprocess
import sys
from pathlib import Path

def run_basic_tests():
    """Run core tests that should pass."""
    test_commands = [
        # Basic data structure tests
        ["python", "-m", "pytest", "src/tests/unit/test_call_manager.py::TestCallSession", "-v"],
        ["python", "-m", "pytest", "src/tests/unit/test_call_manager.py::TestCallQueue", "-v"],
        ["python", "-m", "pytest", "src/tests/unit/test_call_manager.py::TestCallRouter::test_blacklist_functionality", "-v"],
        ["python", "-m", "pytest", "src/tests/unit/test_call_manager.py::TestCallRouter::test_whitelist_functionality", "-v"],
        ["python", "-m", "pytest", "src/tests/unit/test_call_manager.py::TestCallRouter::test_routing_rules", "-v"],
        
        # Basic DTMF tests
        ["python", "-m", "pytest", "src/tests/unit/test_dtmf_processing.py::TestDTMFDetector::test_dtmf_detector_initialization", "-v"],
        ["python", "-m", "pytest", "src/tests/unit/test_dtmf_processing.py::TestDTMFDetector::test_dtmf_digit_values", "-v"],
    ]
    
    passed = 0
    failed = 0
    
    for cmd in test_commands:
        print(f"\nRunning: {' '.join(cmd)}")
        result = subprocess.run(cmd, cwd=Path(__file__).parent.parent.parent)
        if result.returncode == 0:
            passed += 1
            print("✅ PASSED")
        else:
            failed += 1
            print("❌ FAILED")
    
    print(f"\n{'='*50}")
    print(f"BASIC TEST RESULTS: {passed} passed, {failed} failed")
    print(f"{'='*50}")
    
    return failed == 0

if __name__ == "__main__":
    success = run_basic_tests()
    sys.exit(0 if success else 1)