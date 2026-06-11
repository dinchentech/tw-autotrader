#!/bin/bash
set -e

VM_NAME="${1:-tw-autotrader}"
ZONE="${2:-asia-east1-b}"
ENV_FILE="${3:-.env}"

if [ -n "$SUDO_USER" ]; then
  GCLOUD_USER="$SUDO_USER"
else
  GCLOUD_USER=""
fi

gcloud_as_user() {
  if [ -n "$GCLOUD_USER" ]; then
    sudo -u "$GCLOUD_USER" gcloud "$@"
  else
    gcloud "$@"
  fi
}

echo "🏗️  建構 Docker image（約 1-2 分鐘）..."
sudo docker build -t tw-autotrader .

echo "📦 壓縮並傳送至 GCP VM（${VM_NAME}）..."
sudo docker save tw-autotrader | gzip -1 | gcloud_as_user compute ssh "${VM_NAME}" \
  --zone="${ZONE}" --ssh-flag="-C" \
  --command="gunzip | sudo docker load"

echo "📄 同步設定檔 (.env + docker-compose.yml)..."
gcloud_as_user compute scp "${ENV_FILE}" "${VM_NAME}:~/tw-autotrader/.env" \
  --zone="${ZONE}" --quiet
gcloud_as_user compute scp docker-compose.yml "${VM_NAME}:~/tw-autotrader/docker-compose.yml" \
  --zone="${ZONE}" --quiet

echo "🧹 清理舊 image..."
gcloud_as_user compute ssh "${VM_NAME}" --zone="${ZONE}" \
  --command="sudo docker system prune -a -f --filter until=48h 2>&1 | tail -1"

echo "🔄 重啟容器..."
gcloud_as_user compute ssh "${VM_NAME}" --zone="${ZONE}" \
  --command="cd ~/tw-autotrader && sudo docker compose up -d --force-recreate"

echo "🧹 清理舊 image（保留最新的）..."
gcloud_as_user compute ssh "${VM_NAME}" --zone="${ZONE}" \
  --command="sudo docker system prune -a -f 2>&1 | tail -1"

echo ""
echo "✅  部署完成！"
echo "    查看 Log：gcloud compute ssh ${VM_NAME} --zone=${ZONE} --command='sudo docker logs tw_autotrader_bot --tail 20'"
