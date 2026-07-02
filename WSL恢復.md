# WSL 備份還原

## 憑證檔案注意（重要,以下是被移出的資訊使用者必須補回）

本專案使用玉山證券 `.p12` 憑證檔案（位於 `~/tw-autotrader/esun_sdk/`）。**憑證是個人資產，無法共用。**

- **備份前**：請自行將憑證檔移出備份範圍（或告知買家需自備憑證）
- **還原後**：買家必須將自己的 `.p12` 憑證放到 `~/tw-autotrader/esun_sdk/` 目錄下
- 程式會自動偵測該目錄下的 `.p12` 檔案，無需額外設定

## 備份前清理（使用者必須補回）

```bash
# 1. 將個人憑證移出（賣給他人時，買家會用自己的憑證）
#    建議移到 Windows 磁碟暫存
mv ~/tw-autotrader/esun_sdk/*.p12 /mnt/c/Users/frank/Documents/tw_autotrader_backup/
mv ~/tw-autotrader/esun_sdk/*.example /mnt/c/Users/frank/Documents/tw_autotrader_backup/
mv ~/tw-autotrader/esun_sdk/*.ini /mnt/c/Users/frank/Documents/tw_autotrader_backup/

# 2. 移 .env（含玉山密碼、Telegram Token、FinMind Token）live_trader_multi.py
mv ~/tw-autotrader/.env /mnt/c/Users/frank/Documents/tw_autotrader_backup/
mv ~/tw-autotrader/live_trader_multi.py /mnt/c/Users/frank/Documents/tw_autotrader_backup/

# 3. 移 opencode API Key 憑證（沒有 key 就打不了任何 API）
mv ~/.local/share/opencode/auth.json /mnt/c/Users/frank/Documents/tw_autotrader_backup/

# 4. 清 shell 歷史
history -c && history -w

# 5. （可選）移 SSH Key — 如果你有放金鑰在 WSL 裡 GCP SSH key安裝M過程會在產生
# 先複製
cp -a ~/.ssh /mnt/c/Users/frank/Documents/tw_autotrader_backup/
# 刪原件
rm -rf ~/.ssh

# 6. 移 .bashrc
mv ~/.bashrc /mnt/c/Users/frank/Documents/tw_autotrader_backup/


```

> ⚠️ **`.env` 有玉山帳密、Telegram Token、FinMind Token，可以直接用你的身份下單、發訊息、叫資料。**
> ⚠️ **`~/.ssh/` 一般有你的 GitHub / GCP SSH 金鑰。**
> ⚠️ **`.p12` 憑證是個人數位簽章。**

## 備份
在 **PowerShell（系統管理員）** 中執行：

```powershell
wsl --export <Distribution Name> D:\backup\wsl-backup.tar
```
不知道<Distribution Name>可以
```powershell
wsl --list --verbose
```
例如

C:\Users\frank>wsl --list --verbose
  NAME                     STATE           VERSION
* skyworkdistro-skywork    Stopped         2
  
  Ubuntu                   Exporting       2

這裡有兩個wsl的安裝, 若要備份哪一個就把<Distribution Name>換成你要備份的.

## 注意：還原後買家需自行設定

還原後買家第一次進 WSL 要做的：

## 還原

```powershell
wsl --import <自訂系統名稱> <安裝目錄> <備份檔路徑>
```

| 參數 | 說明 | 範例 |
|------|------|------|
| `自訂系統名稱` | 你高興取什麼都行，跟備份時的名稱無關 | `Ubuntu_New` |
| `安裝目錄` | WSL 檔案實際存放的資料夾 | `D:\WSL_Storage` |
| `備份檔路徑` | 剛才 `--export` 產生的 tar 檔 | `D:\wsl_backup.tar` |

### 還原範例

```powershell
wsl --import Ubuntu_New D:\WSL_Storage D:\wsl_backup.tar
```

### 還原後啟動

```powershell
# 以指定使用者登入（假設使用者是 frank）
wsl --set-default-user frank -d Ubuntu_New

# 啟動
wsl -d Ubuntu_New
```

### 買家需要自己準備的

| 項目 | 說明 |
|------|------|
| 📄 玉山 `.p12` 憑證 | 放到 `~/tw-autotrader/esun_sdk/` |
| 📄 玉山 帳號/憑證密碼 | 填入.env |
| 🔑 自己的 `.env` | 參考 `.env.example.lump(dca)` 填寫 |
| 🤖 Telegram Bot Token | 自己跟 `@BotFather` 申請 填入 .env |
| 🔐 OpenCode API Key(openrouter/nvidea) | 填入 ~/.local/share/opencode/auth.json |
| 🔐 FinMind API Key | 自己跟 finmindtrade.com 申請,填入.\bashrc,.env |

### 還原後第一次設定

```bash
# 1. 把 remote 改為 HTTPS（SSH 金鑰已清空，改用 HTTPS 免驗證 pull, 用備份wsl不用）
cd ~/tw-autotrader
git remote set-url origin https://github.com/dinchentech/tw-autotrader.git

# 2. 拉最新程式碼
git pull

# 3. 檢查 opencode 憑證已清空
ls ~/.local/share/opencode/auth.json
# 預期輸出：ls: cannot access ... No such file or directory

# 4. 重新設定 opencode provider
opencode providers login OpenRouter

# 5. 還原.bashrc, live_trader_multi.py
cp ~/.bashrc.txt  ~/.bashrc
cp ~/tw-autotrader/live_trader_multi.py.encrypted ~/tw-autotrader/live_trader_multi.py
```

進去後確認：

```bash
# 檢查 opencode 憑證已清空
ls ~/.local/share/opencode/auth.json
# 預期輸出：ls: cannot access ... No such file or directory

# 檢查憑證已放入
ls ~/tw-autotrader/esun_sdk/*.p12
# 應該看到你的 .p12 檔案

# 設定 opencode provider（重新登入）
opencode providers login OpenRouter
```
或直接產生 nano ~/.local/share/opencode/auth.json
```bash
{
  "openrouter": {
    "type": "api",
    "key": "你的key"
  },
  "nvidia": {
    "type": "api",
    "key": "你的key"
  }
}
```

接著設定自己：.bashrc 中的FinMind憑證, .env檔中的FinMind key/玉山密碼/TG key, esun_sdk中放上玉山.example,.p12檔

============================= 以上完成後就能執行本專案程式 =================================

## 注意事項

- `--import` 預設以 **root** 登入，要變回一般使用者需執行 `wsl --set-default-user`
- `wsl --import` 不支援 `--version 2` 以外的選項（預設就是 WSL 2）
- WSL 1 的發行版無法透過 `--import` 正確還原
