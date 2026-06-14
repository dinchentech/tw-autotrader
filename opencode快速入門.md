# OpenCode 快速入門


```bash
opencode web --hostname 0.0.0.0
```

wsl 本地TUI（終端機版）:

```bash
cd ~\tw-autotrader
opencode .
```

## 如果你的專案在wsl中,請勿使用web版,web版只認識windows目錄!

## 注意:如果使用網頁版請將你的工作目錄放到windwows中

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

---

## 四大代理角色對比

| 角色 | 神話原型 | 做的事 | 什麼時候用 |
|------|----------|--------|-----------|
| **Prometheus** | 普羅米修斯（盜火者） | **規劃不實作** — 產出 `.omo/plans/*.md` 執行計畫 | **任何任務開始時** — 把模糊需求變成可執行的計畫 |
| **Sisyphus** | 薛西弗斯（推石頭） | **拿到計畫後執行** — 跑完所有 TODO | **Prometheus 計畫完成後** — `/start-work` |
| **Hephaestus** | 赫菲斯托斯（工匠神） | **前端/視覺/動畫** — UI、CSS、HTML 原型 | **需要「手藝」的工作** |
| **Atlas** | 阿特拉斯（撐天者） | **扛長期大型任務** — 跨 session 持續追蹤 | **任務太龐大撐不過單一 session** |

### 出任務流程

```
你拋需求 → Prometheus 規劃 → Sisyphus 執行
                            ├ 中途需要前端？叫 Hephaestus
                            └ 任務太大跨 session？用 Atlas 追蹤
```

### 子代理類型

| 代理 | 用途 | 費用 |
|------|------|------|
| `explore` | 在目前 codebase 搜尋檔案、模式 | **最便宜**，可平行開多個 |
| `librarian` | 搜尋外部資源（GitHub、官方文件、網路） | **便宜** |
| `oracle` | 純思考 — 除錯、架構設計、複雜推理 | **最貴**，但值得 |
| `metis` | 需求模糊時釐清歧義、找出遺漏假設 | 規劃專用 |

### Atlas 跨 session 運作機制

Atlas 不是 Sisyphus 執行中自動呼叫的，而是在**規劃階段就被指定**的角色。

```
你拋需求 → Prometheus 規劃
                    ↓
         判斷任務大小，決定用誰扛:
           ├ 一般 → Sisyphus（單一 session 完成）
           └ 太大 → Atlas（跨 session 追蹤）
                              ↓
                   實際執行每個 todo 的還是
                   Sisyphus-Junior / general agent
                   （Atlas 只是標籤，不是執行者）
```

Atlas 靠 **Boulder 系統**（`.omo/boulder.json`）跨 session：

```json
{
  "work_id": "breakout-atr-filter-...",
  "agent": "atlas",
  "status": "completed",
  "session_ids": ["ses_xxx", "ses_yyy", ...],
  "task_sessions": {
    "todo:1": { "agent": "general", "status": "completed" }
  }
}
```

下次開新 session 時，Boulder 自動載入進度 — 不用每次重頭解釋。

> **你用 Sisyphus 就夠了。** Atlas 是給規劃階段就預期要搞好幾天、好幾個 session 的大型任務用的，不需要手動切換。

### 一句話總結

> **explore 找 code → librarian 找外援 → metis 釐清需求 → oracle 解難題。**
> 大部分日常改動 explore + 自己讀就夠了，不要什麼都叫 oracle。
