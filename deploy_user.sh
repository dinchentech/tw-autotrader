#!/bin/bash
# deploy_user.sh — 一般使用者部署腳本（無加密）
#
# 使用方式：
#   ./deploy_user.sh                    # 部署到 GCP VM（預設 tw-autotrader）
#   ./deploy_user.sh my-vm us-west1-a   # 自訂 VM 名稱與區域
#   ./deploy_user.sh my-vm us-west1-a .env.prod
#
# 無加密、無 plans 備份，直接 build Docker 推到 VM。
# 適合擁有 private repo 的使用者。

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

# ════════════════════════════════════════════════════════
# 前置檢查
# ════════════════════════════════════════════════════════

echo "🔍 檢查 GCP 認證..."
gcloud_as_user auth print-identity-token &>/dev/null
AUTH_OK=$?
if [ $AUTH_OK -ne 0 ]; then
  echo ""
  echo "⚠️  GCP 認證已過期或未登入，需要重新認證："
  echo ""
  echo "   gcloud auth login"
  echo ""
  exit 1
fi
echo "   ✅ GCP 認證有效"

echo "🔍 檢查 VM 狀態..."
VM_STATUS=$(gcloud_as_user compute instances describe "${VM_NAME}" --zone="${ZONE}" --format="get(status)" 2>&1)
if [ "$VM_STATUS" != "RUNNING" ]; then
  echo ""
  echo "⚠️  VM 目前狀態：${VM_STATUS:-未知}"
  echo "   請先手動啟動 VM："
  echo ""
  echo "   gcloud compute instances start ${VM_NAME} --zone=${ZONE}"
  echo ""
  exit 1
fi
echo "   ✅ VM 運行中"

# ════════════════════════════════════════════════════════
# Docker 建構與部署
# ════════════════════════════════════════════════════════

echo "🏗️  本機建構 Docker image..."
docker build -t tw-autotrader .

echo "📦 壓縮 image..."
TMP_DIR="./TMP"
TMP_FILE="${TMP_DIR}/tw-autotrader.tar.gz"
mkdir -p "${TMP_DIR}"
docker save tw-autotrader | gzip > "${TMP_FILE}"
chmod 644 "${TMP_FILE}"

echo "☁️  上傳 image 到 VM ${VM_NAME}..."
gcloud_as_user compute scp "${TMP_FILE}" "${VM_NAME}:~/tw-autotrader/tw-autotrader.tar.gz" --zone="${ZONE}" --quiet

echo "📄 同步設定檔..."
gcloud_as_user compute scp "${ENV_FILE}" "${VM_NAME}:~/tw-autotrader/.env" --zone="${ZONE}" --quiet
gcloud_as_user compute scp docker-compose.yml "${VM_NAME}:~/tw-autotrader/docker-compose.yml" --zone="${ZONE}" --quiet

echo "⬇️  在 VM 上載入 image 並重啟..."
gcloud_as_user compute ssh "${VM_NAME}" --zone="${ZONE}" --ssh-flag=-o --ssh-flag=ServerAliveInterval=60 \
  --command="cd ~/tw-autotrader && cat tw-autotrader.tar.gz | gunzip | sudo docker load && sudo docker compose down 2>/dev/null; sudo docker compose up -d --force-recreate && rm tw-autotrader.tar.gz"

echo "🧹 清理舊 image..."
gcloud_as_user compute ssh "${VM_NAME}" --zone="${ZONE}" --ssh-flag=-o --ssh-flag=ServerAliveInterval=60 \
  --command="sudo docker system prune -a -f 2>&1 | tail -1"

echo ""
echo "✅  部署完成！"
echo "    查看 Log：gcloud compute ssh ${VM_NAME} --zone=${ZONE} --command='sudo docker logs tw_autotrader_bot --tail 20'"
