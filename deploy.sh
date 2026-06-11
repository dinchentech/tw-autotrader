#!/bin/bash
set -e

VM_NAME="${1:-tw-autotrader}"
ZONE="${2:-asia-east1-b}"
ENV_FILE="${3:-.env}"
BUCKET="gs://tw-autotrader-deploy"

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

echo "🏗️  本機建構 Docker image..."
sudo docker build -t tw-autotrader .

echo "📦 壓縮 image 並上傳到 Cloud Storage..."
TMP_FILE="/tmp/tw-autotrader.tar.gz"
sudo docker save tw-autotrader | gzip > "${TMP_FILE}"
sudo chmod 644 "${TMP_FILE}"
gcloud_as_user gsutil cp "${TMP_FILE}" "${BUCKET}/tw-autotrader.tar.gz"
rm -f "${TMP_FILE}"

echo "📄 同步設定檔 (.env + docker-compose.yml)..."
gcloud_as_user compute scp "${ENV_FILE}" "${VM_NAME}:~/tw-autotrader/.env" --zone="${ZONE}" --quiet
gcloud_as_user compute scp docker-compose.yml "${VM_NAME}:~/tw-autotrader/docker-compose.yml" --zone="${ZONE}" --quiet

echo "⬇️  在 VM 上從 Cloud Storage 下載 image 並重啟..."
gcloud_as_user compute ssh "${VM_NAME}" --zone="${ZONE}" --ssh-flag=-o --ssh-flag=ServerAliveInterval=60 \
  --command="gsutil cp ${BUCKET}/tw-autotrader.tar.gz - | gunzip | sudo docker load && cd ~/tw-autotrader && sudo docker compose up -d --force-recreate"

echo "🧹 清理舊 image..."
gcloud_as_user compute ssh "${VM_NAME}" --zone="${ZONE}" --ssh-flag=-o --ssh-flag=ServerAliveInterval=60 \
  --command="sudo docker system prune -a -f 2>&1 | tail -1"

echo ""
echo "✅  部署完成！"
echo "    查看 Log：gcloud compute ssh ${VM_NAME} --zone=${ZONE} --command='sudo docker logs tw_autotrader_bot --tail 20'"
