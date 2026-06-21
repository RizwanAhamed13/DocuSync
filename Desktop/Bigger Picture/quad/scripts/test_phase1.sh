#!/bin/bash
set -e

SERVER_URL="http://localhost:8000"
EXAMPLES_DIR="examples"

function test_app() {
  local app_name=$1
  local stack=$2
  local timeout=$3
  
  echo "========================================="
  echo "Testing app: $app_name ($stack)"
  echo "========================================="
  
  # 1. Zip the example folder
  echo "Zipping examples/$app_name-app..."
  rm -f "$app_name.zip"
  (cd "$EXAMPLES_DIR/$app_name-app" && zip -r "../../$app_name.zip" .) > /dev/null
  
  # 2. POST /deploy/upload with the zip and a unique name
  echo "Uploading zip..."
  upload_resp=$(curl -s -w "\n%{http_code}" -X POST "$SERVER_URL/deploy/upload?name=$app_name" \
    -F "file=@$app_name.zip")
  
  http_code=$(echo "$upload_resp" | tail -n1)
  body=$(echo "$upload_resp" | sed '$d')
  
  if [ "$http_code" -ne 202 ]; then
    echo "FAIL: upload returned HTTP $http_code. Response: $body"
    rm -f "$app_name.zip"
    exit 1
  fi
  
  echo "Upload accepted (HTTP 202)."
  
  # 3. Poll GET /apps/<name>
  echo "Polling deployment status..."
  start_time=$(date +%s)
  status="BUILDING"
  internal_port=""
  
  while true; do
    current_time=$(date +%s)
    elapsed=$((current_time - start_time))
    if [ "$elapsed" -gt "$timeout" ]; then
      echo "FAIL: Timeout waiting for app to build and run."
      rm -f "$app_name.zip"
      exit 1
    fi
    
    app_info=$(curl -s "$SERVER_URL/apps")
    status=$(echo "$app_info" | python3 -c "import json, sys; apps = json.loads(sys.stdin.read()); app = [a for a in apps if a['name']=='$app_name']; print(app[0]['status'] if app else 'NOT_FOUND')")
    internal_port=$(echo "$app_info" | python3 -c "import json, sys; apps = json.loads(sys.stdin.read()); app = [a for a in apps if a['name']=='$app_name']; print(app[0]['internal_port'] if app and app[0]['internal_port'] else '')")
    
    echo "  Status: $status (elapsed: ${elapsed}s)"
    
    if [ "$status" = "RUNNING" ]; then
      break
    elif [ "$status" = "FAILED" ]; then
      echo "FAIL: Deployment failed. Logs:"
      curl -s "$SERVER_URL/deploy/$app_name/logs"
      rm -f "$app_name.zip"
      exit 1
    elif [ "$status" = "NOT_FOUND" ]; then
      echo "FAIL: App record not found in DB."
      rm -f "$app_name.zip"
      exit 1
    fi
    
    sleep 3
  done
  
  # 5. curl http://localhost:<internal_port>/ assert HTTP 200
  echo "Asserting application is reachable at port $internal_port..."
  app_url="http://localhost:$internal_port/"
  app_resp=$(curl -s -w "\n%{http_code}" "$app_url")
  app_code=$(echo "$app_resp" | tail -n1)
  app_body=$(echo "$app_resp" | sed '$d')
  
  if [ "$app_code" -ne 200 ]; then
    echo "FAIL: App returned HTTP $app_code instead of 200."
    rm -f "$app_name.zip"
    exit 1
  fi
  
  # 6. Assert response body contains the stack name
  # Use python to perform case-insensitive checks safely
  if ! python3 -c "import sys; sys.exit(0 if '$stack' in sys.argv[1].lower() else 1)" "$app_body"; then
    echo "FAIL: Response body does not contain stack name '$stack'. Body: $app_body"
    rm -f "$app_name.zip"
    exit 1
  fi
  
  echo "App is healthy and returned stack name '$stack' (HTTP 200)."
  
  # 7. Wait 10s
  echo "Waiting 10s before checks..."
  sleep 10
  
  # 8. Assert container appears in docker ps
  c_name="quad-$app_name"
  if ! docker ps --format '{{.Names}}' | grep -q "^$c_name$"; then
    echo "FAIL: Container $c_name not found in docker ps."
    rm -f "$app_name.zip"
    exit 1
  fi
  echo "Container is running in Docker."
  
  # 9. DELETE /deploy/<name>
  echo "Cleaning up deployment..."
  del_code=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$SERVER_URL/deploy/$app_name")
  if [ "$del_code" -ne 200 ]; then
    echo "FAIL: DELETE returned HTTP $del_code."
    rm -f "$app_name.zip"
    exit 1
  fi
  
  # 10. Assert GET /apps/<name> returns 404 or empty from list
  app_check=$(curl -s "$SERVER_URL/apps" | python3 -c "import json, sys; apps = json.loads(sys.stdin.read()); print(any(a['name']=='$app_name' for a in apps))")
  if [ "$app_check" = "True" ]; then
    echo "FAIL: App still exists in SQLite list."
    rm -f "$app_name.zip"
    exit 1
  fi
  
  echo "PASS: $app_name test successful."
  rm -f "$app_name.zip"
}

# Run tests
test_app "static" "static" 60
test_app "node" "node" 60
test_app "python" "python" 60
test_app "java" "java" 240

echo "========================================="
echo "ALL TESTS PASSED SUCCESSFULLY!"
echo "========================================="
