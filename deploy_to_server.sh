#!/bin/bash
# Deploy DocuSync to the configured server.
# Usage:
#   export DOCUSYNC_SERVER=root@host
#   export SSHPASS='server-password'   # optional; omit when SSH keys are set up
#   bash deploy_to_server.sh

set -euo pipefail

SERVER="${DOCUSYNC_SERVER:?Set DOCUSYNC_SERVER, for example root@100.94.47.50}"
REMOTE_DIR="${DOCUSYNC_REMOTE_DIR:-/root/local_document_system}"
LOCAL_DIR="${DOCUSYNC_LOCAL_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
APP_PORT="${APP_PORT:-80}"

if [[ -n "${SSHPASS:-}" ]]; then
  SSH=(sshpass -e ssh -o StrictHostKeyChecking=no)
  RSYNC_RSH="sshpass -e ssh -o StrictHostKeyChecking=no"
else
  SSH=(ssh -o StrictHostKeyChecking=no)
  RSYNC_RSH="ssh -o StrictHostKeyChecking=no"
fi

echo "=== Syncing code to server ==="
rsync -avz --delete -e "$RSYNC_RSH" \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '.git' \
  --exclude 'uploads/' \
  --exclude 'chroma_db/' \
  --exclude 'document_metadata.db' \
  --exclude 'node_modules/' \
  --exclude 'frontend/node_modules/' \
  "$LOCAL_DIR/" \
  "$SERVER:$REMOTE_DIR/"

echo "=== Installing/updating Python deps on server ==="
"${SSH[@]}" "$SERVER" "
  cd $REMOTE_DIR
  pip install -q -r requirements.txt
"

echo "=== Restarting server with systemd (or direct) ==="
"${SSH[@]}" "$SERVER" "
  pkill -f uvicorn 2>/dev/null; sleep 2
  cd $REMOTE_DIR
  APP_PORT=$APP_PORT USE_OLLAMA_TAGGING=false nohup uvicorn main:app --host 0.0.0.0 --port $APP_PORT > /tmp/docusync.log 2>&1 &
  sleep 5
  tail -5 /tmp/docusync.log
  echo '=== GPU check ==='
  nvidia-smi --query-gpu=name,utilization.gpu,memory.used --format=csv,noheader
"

echo "=== Done! Server restarted on $SERVER:$APP_PORT ==="
