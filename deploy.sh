#!/bin/bash
set -e

VM_NAME="${1:-tw-autotrader}"
ZONE="${2:-asia-east1-b}"
ENV_FILE="${3:-.env}"

echo "🏗️  建構 Docker image（約 1-2 分鐘）..."
docker build -t tw-autotrader .

echo "📦 壓縮並傳送至 GCP VM（${VM_NAME}）..."
docker save tw-autotrader | gzip -1 | gcloud compute ssh "${VM_NAME}" \
  --zone="${ZONE}" --ssh-flag="-C" \
  --command="gunzip | sudo docker load"

echo "📄 同步 .env 設定..."
gcloud compute scp "${ENV_FILE}" "${VM_NAME}:~/tw-autotrader/.env" \
  --zone="${ZONE}" --quiet

echo "🔄 重啟容器..."
gcloud compute ssh "${VM_NAME}" --zone="${ZONE}" \
  --command="cd ~/tw-autotrader && sudo docker compose up -d"

echo ""
echo "✅  部署完成！"
echo "    查看 Log：gcloud compute ssh ${VM_NAME} --zone=${ZONE} --command='sudo docker logs tw_autotrader_bot --tail 20'"
