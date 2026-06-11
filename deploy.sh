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

SSH_OPTS="--ssh-flag=-o ServerAliveInterval=60"

echo "📂 同步原始碼至 GCP VM（約 1MB，非 Docker image）..."
tar czf - --exclude=.venv --exclude=.git --exclude="*.tar" --exclude=logs --exclude=__pycache__ \
  --exclude=.mypy_cache --exclude=.pytest_cache . | \
  gcloud_as_user compute ssh "${VM_NAME}" --zone="${ZONE}" ${SSH_OPTS} \
  --command="mkdir -p ~/tw-autotrader && tar xzf - -C ~/tw-autotrader"

echo "🏗️  在 VM 上建構 Docker image（約 2-3 分鐘）..."
gcloud_as_user compute ssh "${VM_NAME}" --zone="${ZONE}" ${SSH_OPTS} \
  --command="cd ~/tw-autotrader && sudo docker build -t tw-autotrader ."

echo "📄 同步設定檔 (.env + docker-compose.yml)..."
gcloud_as_user compute scp "${ENV_FILE}" "${VM_NAME}:~/tw-autotrader/.env" \
  --zone="${ZONE}" --quiet
gcloud_as_user compute scp docker-compose.yml "${VM_NAME}:~/tw-autotrader/docker-compose.yml" \
  --zone="${ZONE}" --quiet

echo "🧹 清理舊 image..."
gcloud_as_user compute ssh "${VM_NAME}" --zone="${ZONE}" ${SSH_OPTS} \
  --command="sudo docker system prune -a -f --filter until=48h 2>&1 | tail -1"

echo "🔄 重啟容器..."
gcloud_as_user compute ssh "${VM_NAME}" --zone="${ZONE}" ${SSH_OPTS} \
  --command="cd ~/tw-autotrader && sudo docker compose up -d --force-recreate"

echo "🧹 清理舊 image（保留最新的）..."
gcloud_as_user compute ssh "${VM_NAME}" --zone="${ZONE}" ${SSH_OPTS} \
  --command="sudo docker system prune -a -f 2>&1 | tail -1"

echo ""
echo "✅  部署完成！"
echo "    查看 Log：gcloud compute ssh ${VM_NAME} --zone=${ZONE} --command='sudo docker logs tw_autotrader_bot --tail 20'"
