#!/bin/bash
set -e

# deploy_crypted.sh — 部署加密版 live_trader_multi.py 到 GCP VM
#
# 適用對象：沒有 live_trader_multi.py 原始碼，只有加密版的使用者
# 前置需求：目錄下需有：
#   1. live_trader_multi.py.encrypted  （已加密的主程式，由 pyarmor 產出）
#   2. pyarmor_runtime_000000/         （PyArmor 解密密碼函式庫）
#
# 使用方式：
#   ./deploy_crypted.sh                          # VM=tw-autotrader, zone=asia-east1-b
#   ./deploy_crypted.sh my-vm us-west1-a         # 自訂 VM 與區域
#   ./deploy_crypted.sh my-vm us-west1-a .env.prod
#   CRYPTED_FILE=live_trader_multi.py.crypted ./deploy_crypted.sh  # 自訂加密檔名

VM_NAME="${1:-tw-autotrader}"
ZONE="${2:-asia-east1-b}"
ENV_FILE="${3:-.env}"

CRYPTED_SRC="${CRYPTED_FILE:-live_trader_multi.py.encrypted}"
TARGET_SCRIPT="live_trader_multi.py"
PYARMOR_RUNTIME_DIR="pyarmor_runtime_000000"
TMP_DIR="./TMP"
TMP_FILE="${TMP_DIR}/tw-autotrader.tar.gz"

# ════════════════════════════════════════════════════════
# 前置檢查
# ════════════════════════════════════════════════════════

echo "🔍 檢查加密檔案是否存在..."
if [ ! -f "${CRYPTED_SRC}" ]; then
  echo "❌ ${CRYPTED_SRC} 不存在！"
  echo "   請確認已將加密版主程式命名為 ${CRYPTED_SRC} 並放在此目錄。"
  exit 1
fi
echo "   ✅ ${CRYPTED_SRC} 存在"

# 檢查 pyarmor runtime
if [ ! -d "${PYARMOR_RUNTIME_DIR}" ]; then
  echo "❌ ${PYARMOR_RUNTIME_DIR}/ 不存在！"
  echo "   請執行以下命令補齊："
  echo "   git checkout -- ${PYARMOR_RUNTIME_DIR}/"
  exit 1
fi
echo "   ✅ ${PYARMOR_RUNTIME_DIR}/ 存在"

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
# 準備加密版主程式
# ════════════════════════════════════════════════════════

echo "📦 準備加密版 ${TARGET_SCRIPT}..."
# 備份本地可能存在的原始檔（如有）
if [ -f "${TARGET_SCRIPT}" ] && [ "${TARGET_SCRIPT}" -nt "${CRYPTED_SRC}" ]; then
  echo "   ⚠️  本機有較新的 ${TARGET_SCRIPT}（可能為原始碼），備份為 ${TARGET_SCRIPT}.bak"
  cp "${TARGET_SCRIPT}" "${TARGET_SCRIPT}.bak"
fi

# 加密版複製為正式檔名（供 Docker build 使用）
cp "${CRYPTED_SRC}" "${TARGET_SCRIPT}"
echo "   ✅ ${CRYPTED_SRC} → ${TARGET_SCRIPT}"

# ════════════════════════════════════════════════════════
# Docker 建構與部署（加密檔 + runtime 都在 image 中）
# ════════════════════════════════════════════════════════

echo "🏗️  本機建構 Docker image（含加密主程式 + PyArmor runtime）..."
docker build -t tw-autotrader .

echo "📦 壓縮 image..."
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

# ════════════════════════════════════════════════════════
# 清理本地暫存
# ════════════════════════════════════════════════════════

echo "🧹 清理本機暫存..."
rm -f "${TARGET_SCRIPT}"  # 移除從 .crypted 複製的檔
if [ -f "${TARGET_SCRIPT}.bak" ]; then
  echo "   ⚠️  原始檔備份留在 ${TARGET_SCRIPT}.bak，請自行處理。"
fi

echo ""
echo "✅  部署完成！"
echo "    查看 Log：gcloud compute ssh ${VM_NAME} --zone=${ZONE} --command='sudo docker logs tw_autotrader_bot --tail 20'"
echo ""
echo "    💡 注意：本機 ${TARGET_SCRIPT} 已移除（僅用於 build 中間步驟）。"
echo "       加密檔 ${CRYPTED_SRC} 保留不動。"
