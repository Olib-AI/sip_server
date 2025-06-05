# Deployment Guide

This guide covers deploying the Olib AI SIP Server with complete two-way AI integration.

## Quick Start with Docker Compose

### Prerequisites
- Docker and Docker Compose installed
- AI platform accessible via WebSocket
- Available ports: 5060 (SIP), 8080 (API), 8081 (WebSocket)

### 1. Environment Configuration

Create `.env` file:
```bash
# Database
DB_HOST=postgres
DB_PORT=5432
DB_NAME=kamailio
DB_USER=kamailio
DB_PASSWORD=your_secure_password

# API Configuration
API_HOST=0.0.0.0
API_PORT=8080

# WebSocket Configuration
WEBSOCKET_HOST=0.0.0.0
WEBSOCKET_PORT=8081
AI_PLATFORM_WS_URL=ws://your-ai-platform:8001/ws/voice

# SIP Configuration
SIP_HOST=0.0.0.0
SIP_PORT=5060
SIP_DOMAIN=sip.yourdomain.com

# Security
JWT_SECRET_KEY=your_jwt_secret_key_here
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=30
API_KEY=your_api_key_here

# Audio Processing
AUDIO_SAMPLE_RATE=8000
AUDIO_FRAME_SIZE=160
RTP_PORT_RANGE_START=10000
RTP_PORT_RANGE_END=10100

# Logging
LOG_LEVEL=INFO
DEBUG=false
```

### 2. Deploy with Docker Compose

```bash
# Clone and navigate to project
git clone <repository-url>
cd sip_server

# Start services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f sip-server
```

### 3. Validate Deployment

```bash
# Test API health
curl http://localhost:8080/health

# Test configuration endpoint
curl http://localhost:8080/api/config

# Test WebSocket (requires authentication)
curl -H "Authorization: Bearer your_jwt_token" \
     http://localhost:8081/ws/test
```

## Production Kubernetes Deployment

### Prerequisites
- Kubernetes cluster with UDP load balancer support
- PostgreSQL database (managed or self-hosted)
- Docker registry access
- DNS configuration for SIP domains

## Production Environment Setup

### 1. Database Setup

#### Managed PostgreSQL (Recommended)
```yaml
# Example for AWS RDS
apiVersion: v1
kind: Secret
metadata:
  name: postgres-credentials
type: Opaque
stringData:
  DATABASE_URL: "postgresql://username:password@your-rds-endpoint:5432/kamailio"
```

#### Self-hosted PostgreSQL
```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
spec:
  serviceName: postgres
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
      - name: postgres
        image: postgres:15
        env:
        - name: POSTGRES_DB
          value: kamailio
        - name: POSTGRES_USER
          value: kamailio
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: postgres-credentials
              key: password
        volumeMounts:
        - name: postgres-storage
          mountPath: /var/lib/postgresql/data
  volumeClaimTemplates:
  - metadata:
      name: postgres-storage
    spec:
      accessModes: ["ReadWriteOnce"]
      resources:
        requests:
          storage: 100Gi
```

### 2. ConfigMap for Configuration

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: sip-server-config
data:
  kamailio.cfg: |
    # Production Kamailio configuration
    # Include your customized config here
  rtpengine.conf: |
    [rtpengine]
    interface = 0.0.0.0
    listen-ng = 127.0.0.1:2223
    port-min = 10000
    port-max = 20000
    log-level = 4
```

### 3. SIP Server Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: sip-server
  labels:
    app: sip-server
spec:
  replicas: 3
  selector:
    matchLabels:
      app: sip-server
  template:
    metadata:
      labels:
        app: sip-server
    spec:
      containers:
      - name: sip-server
        image: your-registry/olib-sip-server:latest
        ports:
        - containerPort: 5060
          protocol: UDP
          name: sip-udp
        - containerPort: 5060
          protocol: TCP
          name: sip-tcp
        - containerPort: 5061
          protocol: TCP
          name: sips
        - containerPort: 8000
          protocol: TCP
          name: api
        - containerPort: 8080
          protocol: TCP
          name: websocket
        env:
        - name: DB_HOST
          value: postgres
        - name: DB_NAME
          value: kamailio
        - name: DB_USER
          valueFrom:
            secretKeyRef:
              name: postgres-credentials
              key: username
        - name: DB_PASSWORD
          valueFrom:
            secretKeyRef:
              name: postgres-credentials
              key: password
        - name: JWT_SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: sip-server-secrets
              key: jwt-secret
        - name: API_KEY
          valueFrom:
            secretKeyRef:
              name: sip-server-secrets
              key: api-key
        - name: AI_PLATFORM_WS_URL
          value: "ws://ai-platform-service:8001/ws/voice"
        - name: SIP_DOMAIN
          value: "sip.yourdomain.com"
        - name: AUDIO_SAMPLE_RATE
          value: "8000"
        - name: LOG_LEVEL
          value: "INFO"
        resources:
          requests:
            memory: "2Gi"
            cpu: "1000m"
          limits:
            memory: "4Gi"
            cpu: "2000m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 60
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 5
        volumeMounts:
        - name: config
          mountPath: /app/config
        - name: logs
          mountPath: /var/log
      volumes:
      - name: config
        configMap:
          name: sip-server-config
      - name: logs
        emptyDir: {}
```

### 4. Service Configuration

```yaml
apiVersion: v1
kind: Service
metadata:
  name: sip-server-api
spec:
  selector:
    app: sip-server
  ports:
  - port: 8000
    targetPort: 8000
    name: api
  - port: 8080
    targetPort: 8080
    name: websocket
  type: ClusterIP

---
apiVersion: v1
kind: Service
metadata:
  name: sip-server-sip
  annotations:
    # Cloud provider specific annotations for UDP load balancing
    service.beta.kubernetes.io/aws-load-balancer-type: "nlb"
    service.beta.kubernetes.io/aws-load-balancer-scheme: "internet-facing"
spec:
  selector:
    app: sip-server
  ports:
  - port: 5060
    targetPort: 5060
    protocol: UDP
    name: sip-udp
  - port: 5060
    targetPort: 5060
    protocol: TCP
    name: sip-tcp
  - port: 5061
    targetPort: 5061
    protocol: TCP
    name: sips
  type: LoadBalancer
  sessionAffinity: ClientIP
```

### 5. Ingress for API (Optional)

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: sip-server-api-ingress
  annotations:
    kubernetes.io/ingress.class: nginx
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
spec:
  tls:
  - hosts:
    - api.sip.yourdomain.com
    secretName: sip-api-tls
  rules:
  - host: api.sip.yourdomain.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: sip-server-api
            port:
              number: 8000
```

## Network Configuration

### 1. DNS Setup

Configure DNS records for your SIP domain:

```
sip.yourdomain.com.    IN  A     <load-balancer-ip>
_sip._udp.yourdomain.com. IN SRV 10 5 5060 sip.yourdomain.com.
_sip._tcp.yourdomain.com. IN SRV 10 5 5060 sip.yourdomain.com.
_sips._tcp.yourdomain.com. IN SRV 10 5 5061 sip.yourdomain.com.
```

### 2. Firewall Rules

Ensure these ports are accessible:

- **5060/UDP**: SIP signaling
- **5060/TCP**: SIP signaling over TCP
- **5061/TCP**: SIP over TLS (SIPS)
- **10000-20000/UDP**: RTP media streams
- **8000/TCP**: API (internal only)
- **8080/TCP**: WebSocket (internal only)

### 3. NAT Configuration

For proper NAT traversal:

```yaml
# Add to Kamailio config
modparam("nathelper", "natping_interval", 30)
modparam("nathelper", "ping_nated_only", 1)
modparam("nathelper", "received_avp", "$avp(received)")
```

## Scaling Configuration

### Horizontal Pod Autoscaler

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: sip-server-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: sip-server
  minReplicas: 3
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

### Vertical Pod Autoscaler

```yaml
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: sip-server-vpa
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: sip-server
  updatePolicy:
    updateMode: "Auto"
  resourcePolicy:
    containerPolicies:
    - containerName: sip-server
      maxAllowed:
        cpu: 4
        memory: 8Gi
      minAllowed:
        cpu: 500m
        memory: 1Gi
```

## Monitoring Setup

### Prometheus ServiceMonitor

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: sip-server-metrics
spec:
  selector:
    matchLabels:
      app: sip-server
  endpoints:
  - port: api
    path: /metrics
    interval: 30s
```

### Grafana Dashboard

Import the provided Grafana dashboard from `monitoring/grafana/dashboards/sip-server.json`.

Key metrics to monitor:
- Active calls count
- Call success rate
- API response times
- Memory/CPU usage
- Database connections
- WebSocket connections

### Alerting Rules

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: sip-server-alerts
spec:
  groups:
  - name: sip-server
    rules:
    - alert: SIPServerDown
      expr: up{job="sip-server"} == 0
      for: 1m
      labels:
        severity: critical
      annotations:
        summary: "SIP Server is down"
        
    - alert: HighCallFailureRate
      expr: rate(sip_calls_failed_total[5m]) > 0.1
      for: 2m
      labels:
        severity: warning
      annotations:
        summary: "High call failure rate detected"
        
    - alert: HighMemoryUsage
      expr: container_memory_usage_bytes{pod=~"sip-server-.*"} / container_spec_memory_limit_bytes > 0.9
      for: 5m
      labels:
        severity: warning
      annotations:
        summary: "High memory usage on SIP server pod"
```

## Security Configuration

### 1. Network Policies

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: sip-server-netpol
spec:
  podSelector:
    matchLabels:
      app: sip-server
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from: []  # Allow all for SIP (UDP 5060)
    ports:
    - protocol: UDP
      port: 5060
  - from:
    - namespaceSelector:
        matchLabels:
          name: ai-platform
    ports:
    - protocol: TCP
      port: 8080
  egress:
  - to:
    - namespaceSelector:
        matchLabels:
          name: database
    ports:
    - protocol: TCP
      port: 5432
```

### 2. Pod Security Policy

```yaml
apiVersion: policy/v1beta1
kind: PodSecurityPolicy
metadata:
  name: sip-server-psp
spec:
  privileged: false
  allowPrivilegeEscalation: false
  requiredDropCapabilities:
    - ALL
  volumes:
    - 'configMap'
    - 'emptyDir'
    - 'projected'
    - 'secret'
    - 'downwardAPI'
    - 'persistentVolumeClaim'
  runAsUser:
    rule: 'MustRunAsNonRoot'
  seLinux:
    rule: 'RunAsAny'
  fsGroup:
    rule: 'RunAsAny'
```

### 3. RBAC Configuration

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: sip-server
  namespace: sip-system

---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: sip-server
rules:
- apiGroups: [""]
  resources: ["configmaps", "secrets"]
  verbs: ["get", "list"]

---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: sip-server
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: sip-server
subjects:
- kind: ServiceAccount
  name: sip-server
  namespace: sip-system
```

## Backup and Recovery

### Database Backup

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: postgres-backup
spec:
  schedule: "0 2 * * *"
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: postgres-backup
            image: postgres:15
            command:
            - /bin/bash
            - -c
            - |
              pg_dump $DATABASE_URL | gzip > /backup/backup-$(date +%Y%m%d-%H%M%S).sql.gz
              # Upload to S3 or other storage
            env:
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: postgres-credentials
                  key: DATABASE_URL
            volumeMounts:
            - name: backup-storage
              mountPath: /backup
          volumes:
          - name: backup-storage
            persistentVolumeClaim:
              claimName: backup-pvc
          restartPolicy: OnFailure
```

### Configuration Backup

```bash
# Backup Kubernetes configurations
kubectl get configmap sip-server-config -o yaml > backup/configmap.yaml
kubectl get secret sip-server-secrets -o yaml > backup/secrets.yaml
kubectl get deployment sip-server -o yaml > backup/deployment.yaml
```

## Performance Tuning

### Kamailio Configuration

For high-volume deployments:

```cfg
# Increase workers
children=16
tcp_children=8

# Increase memory
shm_mem=1024
pkg_mem=128

# Optimize database connections
modparam("db_postgres", "max_db_queries", 8)
modparam("db_postgres", "max_db_connections", 16)
```

### PostgreSQL Tuning

```sql
-- Optimize for SIP workload
ALTER SYSTEM SET max_connections = 200;
ALTER SYSTEM SET shared_buffers = '1GB';
ALTER SYSTEM SET effective_cache_size = '3GB';
ALTER SYSTEM SET work_mem = '16MB';
ALTER SYSTEM SET maintenance_work_mem = '256MB';
ALTER SYSTEM SET checkpoint_completion_target = 0.9;
ALTER SYSTEM SET wal_buffers = '16MB';
ALTER SYSTEM SET default_statistics_target = 100;
```

### Node Configuration

```yaml
# Node selector for dedicated SIP nodes
nodeSelector:
  workload: sip-server

# Tolerations for dedicated nodes
tolerations:
- key: "sip-server"
  operator: "Equal"
  value: "true"
  effect: "NoSchedule"
```

## Troubleshooting

### Common Deployment Issues

1. **Pod stuck in Pending**: Check resource requests vs. node capacity
2. **Service not accessible**: Verify security groups and network policies
3. **Database connection issues**: Check credentials and network connectivity
4. **High memory usage**: Tune Kamailio memory settings

### Debugging Commands

```bash
# Check pod status
kubectl get pods -l app=sip-server

# View logs
kubectl logs -f deployment/sip-server -c sip-server

# Execute into pod
kubectl exec -it <pod-name> -- /bin/bash

# Check SIP registration
kubectl exec -it <pod-name> -- kamctl ul show

# Monitor SIP traffic
kubectl exec -it <pod-name> -- tcpdump -i any port 5060
```

### Performance Monitoring

```bash
# Check resource usage
kubectl top pods -l app=sip-server

# Monitor metrics
curl http://<pod-ip>:8000/metrics

# Check Kamailio stats
kubectl exec -it <pod-name> -- kamctl stats
```