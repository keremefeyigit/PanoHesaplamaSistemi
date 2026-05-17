#!/bin/bash
pkill -9 -f 'uvicorn main:app' || true
sleep 1
truncate -s 0 /home/PanoHesaplamaSistemi/web/backend/backend.log
cd /home/PanoHesaplamaSistemi/web/backend
PYTHONPATH=/home/PanoHesaplamaSistemi nohup /home/PanoHesaplamaSistemi/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 >> /home/PanoHesaplamaSistemi/web/backend/backend.log 2>&1 &
sleep 4

echo "Checking backend health:"
curl -sk https://127.0.0.1/api/health
echo

echo "Checking if lhr.life tunnel is running:"
if ! pgrep -f 'localhost.run' > /dev/null; then
  echo "Tunnel was down, starting it..."
  nohup ssh -R 80:localhost:8080 nokey@localhost.run -o StrictHostKeyChecking=no > /tmp/lhrun.log 2>&1 &
  sleep 4
fi

cat /tmp/lhrun.log | grep -o 'https://[-a-zA-Z0-9]*\.lhr\.life' | head -1
