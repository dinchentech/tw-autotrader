# OpenCode 網頁版快速入門

## 啟動

```bash
opencode web --hostname 0.0.0.0
```

| 參數 | 說明 |
|------|------|
| `--hostname 0.0.0.0` | 允許區網內其他裝置連線（手機、平板、另一台電腦） |
| `--port 0` | 讓 opencode 自行挑選可用埠號（預設行為，可不加） |

### 背景執行（關終端機不中斷）

```bash
nohup opencode web --hostname 0.0.0.0 > opencode-web.log 2>&1 &
```

### tmux 執行（方便看 log）

```bash
tmux new-session -d -s opencode 'opencode web --hostname 0.0.0.0'
tmux attach -t opencode
```

## 如何連線

啟動後 terminal 會顯示類似：

```
🌐 OpenCode web server running at http://0.0.0.0:35671

   ➜  Local:   http://localhost:35671
```

**本機連線** → 瀏覽器打開 `http://localhost:35671`（埠號看 terminal 顯示的數字）

**手機 / 平板（同區網）** → `http://192.168.x.x:35671`
> 查主機 IP：`ip addr show | grep "inet "` 或 `hostname -I`

## 網頁版功能

- 與 TUI（終端機版）同一套 AI 助手，同一份設定與對話歷史
- 可上傳附件（圖片、PDF）給 AI 分析
- 適合躺床用手機操作、部署在雲端主機遠端使用

## 安全性

| 設定 | 誰能連線 |
|------|----------|
| `--hostname 127.0.0.1`（預設） | **僅本機** |
| `--hostname 0.0.0.0` | 同區網所有裝置 |

> 雲端主機上用 `0.0.0.0` 請設防火牆限制 IP，或走 SSH Tunnel。
