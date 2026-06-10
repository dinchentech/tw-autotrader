# 📂 WSL (.tar 備份檔) 還原指南

本文件記錄如何將先前使用 `wsl --export` 匯出的 `.tar` 檔案，完整還原（Restore）到 Windows 系統中。

---

## 🛠️ 還原前準備
1. **建立安裝目錄**：在硬碟中建立一個空的資料夾，用來存放還原後的 Linux 系統檔案（建議選擇空間足夠的硬碟）。
   * *範例路徑*：`D:\WSL_Storage`
2. **準備備份檔案**：確認你的 `.tar` 檔案路徑。
   * *範例路徑*：`D:\wsl_backup.tar`

---

## 🚀 完整還原步驟

### 步驟 1：關閉所有運行中的 WSL
打開 Windows 本地的 **PowerShell**（請勿使用 WSL 終端機），輸入以下指令強制關閉所有 WSL 執行個體：
```powershell
wsl --shutdown
```

### 步驟 2：執行匯入還原（Import）
在 **PowerShell** 中，依照以下格式輸入還原指令：
```powershell
wsl --import <自訂系統名稱> <安裝目錄路徑> <備份檔案路徑>
```

**💡 實際操作範例：**
將還原後的系統命名為 `Ubuntu_New`，解壓縮到 `D:\WSL_Storage`：
```powershell
wsl --import Ubuntu_New D:\WSL_Storage D:\wsl_backup.tar
```
> ⚠️ **注意**：按下 Enter 後畫面會定格數分鐘。這段時間系統正在解壓縮，請耐心等待直到下一行輸入提示出現。

### 步驟 3：確認系統已成功匯入
輸入以下指令，檢查清單中是否有出現剛剛建立的系統名稱：
```powershell
wsl --list --verbose
```

### 步驟 4：啟動並進入新系統
使用 `-d` 參數指定啟動剛剛還原的 WSL 系統：
```powershell
wsl -d Ubuntu_New
```

---

## 🔑 重要修正：改回預設使用者 `frank`

透過 `--import` 還原的系統，預設會以 `root` (最高權限) 帳號登入(密碼:dinchentech)。這會導致你找不到原本的專案檔案與設定。請依照以下步驟修正：

### 1. 臨時切換帳號
進入 WSL 後，可以直接輸入以下指令切換到你的原有帳號：
```bash
su - frank
```

### 2. 永久修正預設登入帳號
為了讓以後每次打開都自動用 `frank` 登入，請在 WSL 內設定設定檔：
1. 編輯設定檔：
   ```bash
   sudo nano /etc/wsl.conf
   ```
2. 在檔案中加入或修改以下內容：
   ```ini
   [user]
   default=frank
   ```
3. 按 `Ctrl + O` 儲存，按下 `Enter` 確認，再按 `Ctrl + X` 離開編輯器。
4. 回到 Windows **PowerShell** 執行 `wsl --shutdown` 重啟，設定即會生效。
