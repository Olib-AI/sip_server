#!/bin/bash

echo "🚀 Setting up local SIP testing environment..."

# Wait for services to be ready
sleep 5

# Generate admin token
ADMIN_TOKEN=$(docker compose exec sip-server python -c "from src.utils.auth import create_access_token; from datetime import timedelta; print(create_access_token(data={'sub': 'admin', 'role': 'admin'}, expires_delta=timedelta(days=1)))" 2>/dev/null | tr -d '\r')

if [ -z "$ADMIN_TOKEN" ]; then
    echo "❌ Failed to generate admin token. Make sure SIP server is running."
    echo "Try: docker compose up -d"
    exit 1
fi

echo "✓ Admin token generated"

# Create test users
echo "Creating test users..."
for i in 1 2 3; do
  echo "Creating user test$i..."
  RESPONSE=$(curl -s -X POST http://localhost:8080/api/sip-users/ \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -d "{
      \"username\": \"test$i\",
      \"password\": \"password$i\",
      \"display_name\": \"Test User $i\",
      \"realm\": \"localhost\",
      \"max_concurrent_calls\": 5
    }")
  
  if echo "$RESPONSE" | grep -q '"id"'; then
    echo "✓ User test$i created"
  else
    echo "⚠️  User test$i might already exist or creation failed"
  fi
done

# Get local IP (works on both macOS and Linux)
if command -v ip >/dev/null 2>&1; then
    # Linux
    LOCAL_IP=$(ip route get 1 2>/dev/null | awk '{print $7}' | head -1)
elif command -v ipconfig >/dev/null 2>&1; then
    # macOS
    LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null)
else
    # Fallback
    LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
fi

# Final fallback
if [ -z "$LOCAL_IP" ]; then
    LOCAL_IP="localhost"
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "📱 SIP Client Configuration:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Server: localhost or $LOCAL_IP"
echo "Port: 5060"
echo "Transport: UDP or TCP"
echo ""
echo "Test Users:"
echo "• Username: test1 | Password: password1"
echo "• Username: test2 | Password: password2"
echo "• Username: test3 | Password: password3"
echo ""
echo "🎯 To test calls:"
echo "1. Register two users in different SIP clients"
echo "2. Call using: test2@localhost or test2@$LOCAL_IP"
echo ""
echo "📊 Next steps:"
echo "1. Configure Linphone with test1 credentials"
echo "2. Monitor logs: docker compose logs -f sip-server"
echo "3. Check registration: docker compose exec sip-server kamctl ul show"
