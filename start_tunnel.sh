#!/bin/bash
echo "Stopping old tunnels..."
pkill -f 'localhost.run' || true
sleep 2

echo "Starting fresh tunnel..."
truncate -s 0 /tmp/lhrun.log
nohup ssh -R 80:localhost:8080 nokey@localhost.run -o StrictHostKeyChecking=no > /tmp/lhrun.log 2>&1 &

echo "Waiting for tunnel to connect..."
sleep 6

URL=$(cat /tmp/lhrun.log | grep -o 'https://[-a-zA-Z0-9]*\.lhr\.life' | tail -1)
if [ -n "$URL" ]; then
    echo "NEW_TUNNEL_URL=$URL"
else
    echo "Failed to get tunnel URL. Log output:"
    cat /tmp/lhrun.log
fi
