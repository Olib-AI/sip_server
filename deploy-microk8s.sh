#!/bin/bash

# MicroK8s deployment script for Olib AI SIP Server
set -e

echo "🚀 Deploying Olib AI SIP Server to MicroK8s..."

# Check if microk8s is installed and running
if ! command -v microk8s &> /dev/null; then
    echo "❌ MicroK8s is not installed. Please install it first:"
    echo "   sudo snap install microk8s --classic"
    exit 1
fi

# Check if microk8s is running
if ! microk8s status --wait-ready &> /dev/null; then
    echo "❌ MicroK8s is not running. Starting it..."
    sudo microk8s start
    microk8s status --wait-ready
fi

# Enable required addons
echo "📦 Enabling required MicroK8s addons..."
microk8s enable dns storage metallb

# Wait for metallb configuration
echo "⚙️  Configuring MetalLB..."
echo "Please configure MetalLB address pool when prompted."
echo "Example: 192.168.1.240-192.168.1.250"

# Check if namespace exists
if ! microk8s kubectl get namespace sip-system &> /dev/null; then
    echo "📝 Creating namespace..."
    microk8s kubectl apply -f k8s/microk8s/namespace.yaml
else
    echo "✅ Namespace sip-system already exists"
fi

# Deploy PostgreSQL
echo "🐘 Deploying PostgreSQL..."
microk8s kubectl apply -f k8s/microk8s/postgres.yaml

# Wait for PostgreSQL to be ready
echo "⏳ Waiting for PostgreSQL to be ready..."
microk8s kubectl wait --for=condition=ready pod -l app=postgres -n sip-system --timeout=300s

# Deploy ConfigMaps
echo "📋 Deploying ConfigMaps..."
microk8s kubectl apply -f k8s/microk8s/configmaps.yaml

# Deploy SIP Server
echo "📞 Deploying SIP Server..."
microk8s kubectl apply -f k8s/microk8s/sip-server.yaml

# Wait for deployment to be ready
echo "⏳ Waiting for SIP Server to be ready..."
microk8s kubectl wait --for=condition=available deployment/sip-server -n sip-system --timeout=300s

# Get service information
echo ""
echo "🎉 Deployment completed!"
echo ""
echo "📊 Service Status:"
microk8s kubectl get pods -n sip-system
echo ""
microk8s kubectl get services -n sip-system
echo ""

# Get external IP for SIP service
SIP_EXTERNAL_IP=$(microk8s kubectl get service sip-server-sip -n sip-system -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "pending")
API_CLUSTER_IP=$(microk8s kubectl get service sip-server-api -n sip-system -o jsonpath='{.spec.clusterIP}')

echo "🌐 Access Information:"
echo "   SIP Server (External): $SIP_EXTERNAL_IP:5060 (UDP/TCP)"
echo "   SIP Server (TLS): $SIP_EXTERNAL_IP:5061 (TCP)"
echo "   API Server (Internal): $API_CLUSTER_IP:8000"
echo "   WebSocket Bridge (Internal): $API_CLUSTER_IP:8080"
echo ""

# Port forward for API access (optional)
echo "🔌 To access the API locally, run:"
echo "   microk8s kubectl port-forward -n sip-system service/sip-server-api 8000:8000"
echo ""

# Health check
echo "🏥 Testing health endpoint..."
if microk8s kubectl exec -n sip-system deployment/sip-server -- curl -f http://localhost:8000/health 2>/dev/null; then
    echo "✅ Health check passed!"
else
    echo "⚠️  Health check failed. Check logs:"
    echo "   microk8s kubectl logs -n sip-system deployment/sip-server"
fi

echo ""
echo "📝 Useful commands:"
echo "   # View logs"
echo "   microk8s kubectl logs -f -n sip-system deployment/sip-server"
echo ""
echo "   # Access pod shell"
echo "   microk8s kubectl exec -it -n sip-system deployment/sip-server -- /bin/sh"
echo ""
echo "   # Check Kamailio status"
echo "   microk8s kubectl exec -n sip-system deployment/sip-server -- pgrep kamailio"
echo ""
echo "   # Port forward API"
echo "   microk8s kubectl port-forward -n sip-system service/sip-server-api 8000:8000"
echo ""
echo "   # Delete deployment"
echo "   microk8s kubectl delete namespace sip-system"
echo ""

echo "🔧 Next steps:"
echo "1. Configure your VOIP provider to point to: $SIP_EXTERNAL_IP:5060"
echo "2. Update AI_PLATFORM_URL in the deployment if needed"
echo "3. Configure DNS records for your SIP domain"
echo "4. Test with a SIP client (like Linphone or X-Lite)"
echo ""
echo "✨ SIP Server is ready for testing!"