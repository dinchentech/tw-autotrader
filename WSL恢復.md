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


### 3.編輯Finmind的api key,跟opencode 的模型供應者api key
1. Findmind:
   用nano修改~/.bashrc中最下面一行改成你申請的api key
   export FINMIND_TOKEN="eyJ0eXAiOiJKV1QiLCJhbGc................aHN1YW4iLCJlbWFpbCI6ImhzaWVoLmloc3Vh>"

2. opencode:
   nano  ~/.local/share/opencode/auth.json
   修改你申請的openrouter跟nvidea的key=>
   {
     "openrouter": {
     "type": "api",
     "key": "sk-or-v1-........................1da0c559ba14a4f249b34197385a5"
     },
     "nvidia": {
     "type": "api",
     "key": "nvapi-DDsAgaIKnVNs......................DrD-rwnhHetomKrVD-9c"
     }
   }

# nano 編輯器簡易入門

`nano` 是 Linux 系統中最簡單的文字編輯器。它非常適合新手使用。

## 如何打開或建立檔案

在終端機（Terminal）中輸入 `nano` 加上檔案名稱。
如果檔案不存在，它會自動幫你建立一個新檔案。

* **指令：** `nano 檔案名稱.txt`

---

## 畫面三大區塊

1. **最上方：** 顯示 `nano` 版本和正在編輯的檔案名稱。
2. **中間：** 讓你輸入和修改文字的空白區。
3. **最下方：** 快捷鍵說明書。

---

## 必學快捷鍵

> 💡 **提示：** 畫面上的符號 `^` 代表鍵盤的 **Ctrl** 鍵。所有快捷鍵都要按住 `Ctrl` 鍵再按字母。

* **`Ctrl + O`**：存檔（寫入文字）。
* **`Ctrl + X`**：離開 `nano` 編輯器。
* **`Ctrl + W`**：搜尋文字（尋找關鍵字）。
* **`Ctrl + K`**：剪下整行文字。
* **`Ctrl + U`**：貼上文字。

---

## 最常用的操作流程

1. 輸入 `nano test.txt` 打開檔案。
2. 直接用鍵盤打字。
3. 按 **`Ctrl + O`**，再按 **Enter** 鍵儲存檔案。
4. 按 **`Ctrl + X`** 離開。

> ⚠️ **注意：** 如果你在離開前忘記存檔，`nano` 會在最下方詢問：
> `Save modified buffer? (Answering No will DISCARD changes.)`
> * 按 **`Y`**：儲存修改
> * 按 **`N`**：放棄修改（字會消失）
> * 按 **`Ctrl + C`**：取消離開，回到編輯畫面
   

