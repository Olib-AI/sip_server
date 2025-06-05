# Network Policies for SIP Server

This directory contains Kubernetes Network Policies to secure the SIP server deployment.

## Overview

Network policies provide fine-grained control over network traffic between pods in Kubernetes. They act as a firewall at the pod level, controlling what traffic is allowed in (ingress) and out (egress) of pods.

## Files

- `network-policies.yaml` - Basic network policies for development/testing
- `network-policies-strict.yaml` - Strict policies for production use
- `apply-network-policies.sh` - Helper script to manage network policies

## Policy Structure

### 1. PostgreSQL Database Policy
- **Ingress**: Only allows connections from SIP server pods on port 5432
- **Egress**: DNS resolution only

### 2. SIP Server Policy
- **Ingress**: 
  - SIP traffic (UDP/TCP 5060, TCP 5061) from VOIP providers
  - RTP media (UDP 10000-20000) from VOIP providers
  - API access (TCP 8000) from within cluster
  - WebSocket (TCP 8080) from within cluster
- **Egress**:
  - DNS resolution
  - PostgreSQL database connections
  - AI platform connections
  - Outbound SIP/RTP to VOIP providers

### 3. AI Platform Policy (if deployed in cluster)
- **Ingress**: WebSocket connections from SIP server
- **Egress**: DNS and external API calls

## Usage

### Apply Basic Policies (Development)
```bash
./apply-network-policies.sh basic
```

### Apply Strict Policies (Production)
```bash
./apply-network-policies.sh strict
```

### Test Network Policies
```bash
./apply-network-policies.sh test
```

### Remove All Policies
```bash
./apply-network-policies.sh clean
```

## Important Considerations

### 1. VOIP Provider IPs
You MUST update the VOIP provider IP ranges in the network policies to match your actual providers:

- Twilio IPs: Check https://www.twilio.com/docs/sip-trunking/ip-addresses
- Vonage IPs: Check your Vonage account documentation
- Other providers: Contact their support for IP ranges

### 2. Default Deny Policy
The strict configuration includes a default-deny policy. This means:
- All traffic is blocked by default
- Only explicitly allowed connections work
- More secure but requires careful configuration

### 3. DNS Resolution
All policies allow DNS resolution to kube-dns. This is essential for:
- Service discovery
- External domain resolution

### 4. Testing Connectivity
To test if network policies are working correctly:

```bash
# Create a debug pod
kubectl run -it --rm debug --image=nicolaka/netshoot --restart=Never -n sip-system -- /bin/bash

# Inside the debug pod, test connections:
# Test DNS
nslookup postgres-service

# Test PostgreSQL
nc -zv postgres-service 5432

# Test SIP server API
curl http://sip-server-api:8000/health

# Test external connectivity
curl https://www.google.com
```

### 5. Troubleshooting

If you're having connectivity issues:

1. Check pod labels match policy selectors:
```bash
kubectl get pods -n sip-system --show-labels
```

2. Describe the network policy:
```bash
kubectl describe networkpolicy <policy-name> -n sip-system
```

3. Check logs for connection failures:
```bash
kubectl logs -n sip-system <pod-name>
```

4. Temporarily remove policies to isolate the issue:
```bash
./apply-network-policies.sh clean
```

## Security Best Practices

1. **Principle of Least Privilege**: Only allow necessary connections
2. **Regular Updates**: Keep VOIP provider IP ranges up to date
3. **Monitoring**: Monitor for blocked connections in pod logs
4. **Testing**: Test policies in development before production
5. **Documentation**: Document any custom IP ranges or exceptions

## Pod Labels Required

For network policies to work correctly, pods must have appropriate labels:

```yaml
# SIP Server pods
labels:
  app: sip-server
  component: core|api|websocket  # depending on function

# PostgreSQL pods
labels:
  app: postgres

# AI Platform pods
labels:
  app: ai-platform
```

## Migration Guide

When migrating from no policies to network policies:

1. Start with basic policies in development
2. Test all functionality thoroughly
3. Update VOIP provider IPs
4. Apply policies to staging environment
5. Monitor for any blocked connections
6. Apply to production with strict policies

## Common Issues and Solutions

### Issue: Cannot connect to PostgreSQL
**Solution**: Ensure SIP server pods have correct labels

### Issue: No incoming SIP calls
**Solution**: Update VOIP provider IP ranges in policies

### Issue: RTP media not working
**Solution**: Ensure RTP port range matches your configuration

### Issue: Webhooks failing
**Solution**: Add webhook destination IPs to egress rules

### Issue: DNS resolution failing
**Solution**: Check kube-dns labels match policy

## References

- [Kubernetes Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
- [Network Policy Recipes](https://github.com/ahmetb/kubernetes-network-policy-recipes)
- [Cilium Network Policy Editor](https://editor.cilium.io/)