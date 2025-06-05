#!/bin/bash

# Script to apply network policies for SIP server
# Usage: ./apply-network-policies.sh [basic|strict|clean]

set -e

NAMESPACE="sip-system"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    print_error "kubectl could not be found. Please install kubectl first."
    exit 1
fi

# Check if namespace exists
if ! kubectl get namespace $NAMESPACE &> /dev/null; then
    print_error "Namespace $NAMESPACE does not exist. Please create it first."
    exit 1
fi

# Function to apply basic network policies
apply_basic() {
    print_info "Applying basic network policies..."
    
    if [ -f "$SCRIPT_DIR/network-policies.yaml" ]; then
        kubectl apply -f "$SCRIPT_DIR/network-policies.yaml"
        print_info "Basic network policies applied successfully"
    else
        print_error "network-policies.yaml not found"
        exit 1
    fi
}

# Function to apply strict network policies
apply_strict() {
    print_warn "Applying strict network policies..."
    print_warn "This will restrict all traffic except explicitly allowed connections"
    
    read -p "Are you sure you want to apply strict policies? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_info "Cancelled"
        exit 0
    fi
    
    if [ -f "$SCRIPT_DIR/network-policies-strict.yaml" ]; then
        kubectl apply -f "$SCRIPT_DIR/network-policies-strict.yaml"
        print_info "Strict network policies applied successfully"
        print_warn "Make sure to update VOIP provider IP ranges in the policies!"
    else
        print_error "network-policies-strict.yaml not found"
        exit 1
    fi
}

# Function to clean/remove network policies
clean_policies() {
    print_warn "Removing all network policies from namespace $NAMESPACE..."
    
    read -p "Are you sure you want to remove all network policies? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_info "Cancelled"
        exit 0
    fi
    
    kubectl delete networkpolicies --all -n $NAMESPACE
    print_info "All network policies removed"
}

# Function to test network policies
test_policies() {
    print_info "Testing network policy configuration..."
    
    # Check if network policies exist
    POLICY_COUNT=$(kubectl get networkpolicies -n $NAMESPACE --no-headers | wc -l)
    print_info "Found $POLICY_COUNT network policies in namespace $NAMESPACE"
    
    if [ $POLICY_COUNT -eq 0 ]; then
        print_warn "No network policies found. Network is unrestricted."
        return
    fi
    
    # List all policies
    print_info "Active network policies:"
    kubectl get networkpolicies -n $NAMESPACE
    
    # Check pod labels
    print_info "\nPod labels in namespace (for policy selectors):"
    kubectl get pods -n $NAMESPACE --show-labels
    
    # Test connectivity from a debug pod
    print_info "\nTo test connectivity, you can run:"
    echo "kubectl run -it --rm debug --image=nicolaka/netshoot --restart=Never -n $NAMESPACE -- /bin/bash"
    echo "Then use tools like curl, nc, nslookup to test connections"
}

# Function to show policy details
show_policy_details() {
    local policy_name=$1
    if [ -z "$policy_name" ]; then
        print_error "Please specify a policy name"
        echo "Usage: $0 show <policy-name>"
        exit 1
    fi
    
    print_info "Details for network policy: $policy_name"
    kubectl describe networkpolicy $policy_name -n $NAMESPACE
}

# Function to update VOIP provider IPs
update_voip_ips() {
    print_info "Current VOIP provider IP configuration:"
    print_warn "You need to manually edit the network policy files to update IP ranges"
    echo
    echo "Common VOIP provider IP ranges:"
    echo "Twilio:"
    echo "  - 54.172.60.0/23"
    echo "  - 34.203.250.0/23"
    echo "  - 52.215.127.0/24"
    echo "  - 3.122.181.0/24"
    echo
    echo "Vonage:"
    echo "  - 174.37.245.0/24"
    echo "  - 174.36.196.0/24"
    echo
    echo "To find your provider's IPs, check their documentation or contact support"
}

# Main script logic
case "$1" in
    basic)
        apply_basic
        ;;
    strict)
        apply_strict
        ;;
    clean)
        clean_policies
        ;;
    test)
        test_policies
        ;;
    show)
        show_policy_details "$2"
        ;;
    update-ips)
        update_voip_ips
        ;;
    *)
        echo "Usage: $0 {basic|strict|clean|test|show <policy-name>|update-ips}"
        echo
        echo "Commands:"
        echo "  basic      - Apply basic network policies (recommended for start)"
        echo "  strict     - Apply strict network policies (for production)"
        echo "  clean      - Remove all network policies"
        echo "  test       - Test current network policy configuration"
        echo "  show       - Show details of a specific policy"
        echo "  update-ips - Show instructions for updating VOIP provider IPs"
        echo
        echo "Examples:"
        echo "  $0 basic                    # Apply basic policies"
        echo "  $0 test                     # Test current configuration"
        echo "  $0 show postgres-network-policy  # Show specific policy details"
        exit 1
        ;;
esac