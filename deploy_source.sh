#!/bin/bash
# set -e 已移除：SSH exit code 不穩定會誤殺後續步驟
# 關鍵步驟用 || exit 1 手動控管

VM_NAME="${1:-tw-autotrader}"
ZONE="${2:-asia-east1-b}"
ENV_FILE="${3:-.env}"
BUCKET="gs://tw-autotrader-deploy"
TMP_DIR="./TMP"
TMP_FILE="${TMP_DIR}/tw-autotrader.tar.gz"

# 源碼部署（C 方案）：直接打包 live_trader_multi.py 源碼，不加密
TARGET_SCRIPT="live_trader_multi.py"
PLANS_BACKUP="plans/${TARGET_SCRIPT}"

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
# C 方案：無加密，不需還原機制

echo "檢查 GCP 認證..."
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
echo "GCP 認證有效"

echo "檢查 VM 狀態..."
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
echo "VM 運行中"

# ════════════════════════════════════════════════════════
# C 方案（源碼）：備份原始檔 → plans/（本機保留源碼）
# ════════════════════════════════════════════════════════

echo "備份原始 ${TARGET_SCRIPT} → ${PLANS_BACKUP}..."
mkdir -p plans
cp "${TARGET_SCRIPT}" "${PLANS_BACKUP}"

echo "將 plans 子目錄單獨 Commit 與 Push..."
(
  cd plans
  git add "${TARGET_SCRIPT}"
  # 如果有變更才 commit
  if ! git diff --cached --quiet; then
    git commit -m "Auto-backup ${TARGET_SCRIPT} during deploy"
    git push origin main
  else
    echo "   plans 目錄無變更，跳過 commit"
  fi
)
echo "plans 目錄處理完畢"

echo "本機建構 Docker image（源碼版，直接 COPY . .）..."
echo "本機建構 Docker image..."
docker build -t tw-autotrader .

echo "備份源碼並壓縮 image 到 ${TMP_FILE}..."
mkdir -p "${TMP_DIR}"
cp "${TARGET_SCRIPT}" "${TMP_DIR}/live_trader_multi.py.source"
docker save tw-autotrader | gzip > "${TMP_FILE}"
chmod 644 "${TMP_FILE}"

echo "上傳 image 到 ${BUCKET}/tw-autotrader.tar.gz..."
run_as_user gsutil cp "${TMP_FILE}" "${BUCKET}/tw-autotrader.tar.gz"
echo "本機 ${TMP_FILE} 保留作為下次回滾用"

echo "同步設定檔 (.env + docker-compose.yml)..."
gcloud_as_user compute scp "${ENV_FILE}" "${VM_NAME}:~/tw-autotrader/.env" --zone="${ZONE}" --quiet
gcloud_as_user compute scp docker-compose.yml "${VM_NAME}:~/tw-autotrader/docker-compose.yml" --zone="${ZONE}" --quiet

echo "在 VM 上從 Cloud Storage 下載 image 並重啟..."
gcloud_as_user compute ssh "${VM_NAME}" --zone="${ZONE}" --ssh-flag=-o --ssh-flag=ServerAliveInterval=60 \
  --command="gsutil cp ${BUCKET}/tw-autotrader.tar.gz - | gunzip | sudo docker load && cd ~/tw-autotrader && sudo docker compose down 2>/dev/null; sudo docker compose up -d --force-recreate"
stty sane 2>/dev/null

echo "清理舊 image..."
gcloud_as_user compute ssh "${VM_NAME}" --zone="${ZONE}" --ssh-flag=-o --ssh-flag=ServerAliveInterval=60 \
  --command="sudo docker system prune -a -f 2>&1 | tail -1"
stty sane 2>/dev/null

echo "清理 VM 回測專用快取（實盤只需近期法人資料 + 選股快取）..."
gcloud_as_user compute ssh "${VM_NAME}" --zone="${ZONE}" --ssh-flag=-o --ssh-flag=ServerAliveInterval=60 \
  --command="cd ~/tw-autotrader && rm -f cache/inst_momentum/historical_shares.pkl && rm -rf cache/inst_momentum/2015 cache/inst_momentum/2020 cache/inst_momentum/2021 cache/inst_momentum_2022 && find cache/inst_momentum -name 'twse_inst_*.pkl' | while read f; do end=\$(basename \"\$f\" | sed 's/twse_inst_[0-9-]*_//; s/\.pkl//'); if [[ \"\$end\" < \"\$(date -d '60 days ago' +%F)\" ]]; then rm -f \"\$f\"; fi; done; du -sh cache 2>/dev/null | sed 's/^/  快取現況: /'"
stty sane 2>/dev/null

echo ""
echo " 部署完成！"
echo " 查看 Log：gcloud compute ssh ${VM_NAME} --zone=${ZONE} --command='sudo docker logs tw_autotrader_bot --tail 20'"
echo ""
echo "✅ 部署完成（C 方案源碼版）"
