# WSL 備份還原

## 備份前清理（賣給他人前務必執行）

```bash
# 1. 刪除 .env（含玉山密碼、Telegram Token、FinMind Token）
rm -f ~/tw-autotrader/.env

# 2. 刪除 opencode API Key 憑證
rm -f ~/.local/share/opencode/auth.json
rm -rf ~/.local/share/opencode/sessions/

# 3. 清 shell 歷史
history -c && history -w

# 4. （可選）刪除 SSH Key — 如果你有放金鑰在 WSL 裡
rm -rf ~/.ssh

# 5. 離開 WSL 回到 PowerShell
exit
```

> ⚠️ **`.env` 沒刪掉的話，買家拿到你的玉山帳密、Telegram Token、FinMind Token，可以直接用你的身份下單、發訊息、叫資料。**
> ⚠️ **`~/.ssh/` 沒清的話，買家拿到你的 GitHub / GCP SSH 金鑰。**

## 注意：還原後買家需自行設定

還原後買家第一次進 WSL 要做的：

## 備份

在 **PowerShell（系統管理員）** 中執行：

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
Ubuntu_New config --default-user frank

# 啟動
wsl -d Ubuntu_New
```

進去後確認：

```bash
# 檢查 opencode 憑證已清空
ls ~/.local/share/opencode/auth.json
# 預期輸出：ls: cannot access ... No such file or directory

# 設定 opencode provider（重新登入）
opencode providers login OpenRouter
```

## 注意事項

- `--import` 預設以 **root** 登入，要變回一般使用者需執行 `wsl --set-default-user`
- `wsl --import` 不支援 `--version 2` 以外的選項（預設就是 WSL 2）
- WSL 1 的發行版無法透過 `--import` 正確還原
