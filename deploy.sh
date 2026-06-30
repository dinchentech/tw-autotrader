#!/bin/bash
set -e

VM_NAME="${1:-tw-autotrader}"
ZONE="${2:-asia-east1-b}"
ENV_FILE="${3:-.env}"
BUCKET="gs://tw-autotrader-deploy"
TMP_DIR="./TMP"
TMP_FILE="${TMP_DIR}/tw-autotrader.tar.gz"

# Pyarmor 加密相關路徑
TARGET_SCRIPT="live_trader_multi.py"
PLANS_BACKUP="plans/${TARGET_SCRIPT}"
PYARMOR_DIST="./pyarmor_dist"
PYARMOR_RUNTIME_DIR="pyarmor_runtime_000000"

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

run_as_user() {
  if [ -n "$GCLOUD_USER" ]; then
    sudo -u "$GCLOUD_USER" "$@"
  else
    "$@"
  fi
}

# ════════════════════════════════════════════════════════
# Pyarmor 還原機制（任何失敗都把原始檔放回來）
# ════════════════════════════════════════════════════════
restore_original_script() {
  if [ -f "${PLANS_BACKUP}" ]; then
    cp "${PLANS_BACKUP}" "${TARGET_SCRIPT}"
    rm -rf "${PYARMOR_RUNTIME_DIR}" "${PYARMOR_DIST}"
    echo "🔓 已還原原始 ${TARGET_SCRIPT}（pyarmor 加密產物已清除）"
  fi
}
trap restore_original_script EXIT

echo "🔍 檢查 GCP 認證..."
gcloud_as_user auth print-identity-token &>/dev/null
AUTH_OK=$?
if [ $AUTH_OK -ne 0 ]; then
  echo ""
  echo "⚠️  GCP 認證已過期或未登入，需要重新認證："
  echo ""
  echo "   gcloud auth login"
  echo ""
  echo "   瀏覽器會打開 Google 登入頁，完成後再重新執行 deploy。"
  exit 1
fi
echo "   ✅ GCP 認證有效"

echo "🔍 檢查 VM 狀態..."
VM_STATUS=$(gcloud_as_user compute instances describe "${VM_NAME}" --zone="${ZONE}" --format="get(status)" 2>&1)
if [ "$VM_STATUS" != "RUNNING" ]; then
  echo ""
  echo "⚠️  VM 目前狀態：${VM_STATUS:-未知}"
  echo "   VM 在非交易時段會自動關機，請先手動啟動："
  echo ""
  echo "   gcloud compute instances start ${VM_NAME} --zone=${ZONE}"
  echo ""
  echo "   啟動後約 1-2 分鐘 VM 就緒，再重新執行 deploy。"
  exit 1
fi
echo "   ✅ VM 運行中"

# ════════════════════════════════════════════════════════
# Pyarmor 加密：原始檔→plans/ 備份→加密後覆蓋本地檔
# ════════════════════════════════════════════════════════
if [ ! -f "${TARGET_SCRIPT}" ]; then
  echo "❌ ${TARGET_SCRIPT} 不存在，無法加密"
  exit 1
fi

PYARMOR_BIN=""
if [ -x ".venv/bin/pyarmor" ]; then
  PYARMOR_BIN=".venv/bin/pyarmor"
elif command -v pyarmor >/dev/null 2>&1; then
  PYARMOR_BIN="pyarmor"
else
  echo "❌ 找不到 pyarmor 執行檔（試過 .venv/bin/pyarmor 與 PATH）"
  exit 1
fi
echo "   ✅ pyarmor: ${PYARMOR_BIN}"

echo "💾 備份原始 ${TARGET_SCRIPT} → ${PLANS_BACKUP}..."
mkdir -p plans
cp "${TARGET_SCRIPT}" "${PLANS_BACKUP}"

echo "🔐 pyarmor 加密 ${TARGET_SCRIPT}（從 plans/）..."
rm -rf "${PYARMOR_DIST}"
"${PYARMOR_BIN}" gen -O "${PYARMOR_DIST}" "${PLANS_BACKUP}"
if [ ! -f "${PYARMOR_DIST}/${TARGET_SCRIPT}" ]; then
  echo "❌ pyarmor 加密失敗，找不到 ${PYARMOR_DIST}/${TARGET_SCRIPT}"
  exit 1
fi

echo "📝 加密版本覆蓋本地 ${TARGET_SCRIPT} + 安裝 ${PYARMOR_RUNTIME_DIR}/..."
cp "${PYARMOR_DIST}/${TARGET_SCRIPT}" "${TARGET_SCRIPT}"
rm -rf "${PYARMOR_RUNTIME_DIR}"
cp -r "${PYARMOR_DIST}/${PYARMOR_RUNTIME_DIR}" "./${PYARMOR_RUNTIME_DIR}"
rm -rf "${PYARMOR_DIST}"
echo "   ✅ 加密完成（${TARGET_SCRIPT} 已是混淆版，runtime 已就位）"

echo "🏗️  本機建構 Docker image..."
sudo docker build -t tw-autotrader .

echo "📦 壓縮 image 並存到 ${TMP_FILE}（覆蓋舊版，僅保留最新）..."
mkdir -p "${TMP_DIR}"
sudo docker save tw-autotrader | gzip > "${TMP_FILE}"
sudo chmod 644 "${TMP_FILE}"

echo "☁️  上傳 image 到 ${BUCKET}/tw-autotrader.tar.gz..."
run_as_user gsutil cp "${TMP_FILE}" "${BUCKET}/tw-autotrader.tar.gz"
echo "   ✅ 本機 ${TMP_FILE} 保留作為下次回滾用"

echo "📄 同步設定檔 (.env + docker-compose.yml)..."
gcloud_as_user compute scp "${ENV_FILE}" "${VM_NAME}:~/tw-autotrader/.env" --zone="${ZONE}" --quiet
gcloud_as_user compute scp docker-compose.yml "${VM_NAME}:~/tw-autotrader/docker-compose.yml" --zone="${ZONE}" --quiet

echo "⬇️  在 VM 上從 Cloud Storage 下載 image 並重啟..."
gcloud_as_user compute ssh "${VM_NAME}" --zone="${ZONE}" --ssh-flag=-o --ssh-flag=ServerAliveInterval=60 \
  --command="gsutil cp ${BUCKET}/tw-autotrader.tar.gz - | gunzip | sudo docker load && cd ~/tw-autotrader && sudo docker compose down 2>/dev/null; sudo docker compose up -d --force-recreate"

echo "🧹 清理舊 image..."
gcloud_as_user compute ssh "${VM_NAME}" --zone="${ZONE}" --ssh-flag=-o --ssh-flag=ServerAliveInterval=60 \
  --command="sudo docker system prune -a -f 2>&1 | tail -1"

echo ""
echo "✅  部署完成！"
echo "    查看 Log：gcloud compute ssh ${VM_NAME} --zone=${ZONE} --command='sudo docker logs tw_autotrader_bot --tail 20'"
echo "    （EXIT trap 會把本機 ${TARGET_SCRIPT} 還原為原始版本）"
