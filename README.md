# YouTube 字幕下載整合工具

桌面版工具：可下載 YouTube **原生 SRT 字幕**（若影片本來就提供），若沒有 SRT 就可用 Whisper 辨識產生字幕。

## 功能重點

1. YouTube 字幕下載：只列出「原生就有 SRT」的字幕語系，並下載成 `.srt`。
2. 無 SRT 時自動切換：若影片沒有原生 SRT，會自動開啟「辨識工具」。
3. Whisper 辨識工具：支援 YouTube 網址或本機媒體檔（mp3/mp4/wav/m4a…）產生逐字稿與 SRT。
4. 逐字稿下載：辨識完成後可「下載逐字稿（.txt）」與「另存 SRT」。
5. YouTube 影片/音訊下載：可下載 `mp4` 或 `mp3`，並可選畫質。
6. FFmpeg 自動準備：
   - Windows（exe）：系統沒有 FFmpeg 時，首次使用會在背景下載 FFmpeg 到使用者資料夾。
   - Python 直接執行（macOS/Linux/Windows）：若缺少 FFmpeg，會嘗試在背景安裝 `imageio-ffmpeg` 作為備援。

## Windows 直接使用（推薦）

1. 到本專案 GitHub 右側的 **Releases**。
2. 下載 `YouTubeSubtitleTool.exe`。
3. 直接雙擊執行即可（不需要安裝 Python）。

提示：第一次開啟或第一次使用某些功能可能會較久，因為需要初始化環境或下載模型/第三方工具。

## 用 Python 執行（適合要改程式的人）

1. 安裝 Python 3
2. 安裝套件：

```bash
python -m pip install -r requirements.txt
```

3. 啟動：

```bash
python youtube_subtitle_tool.py
```

也可使用雙擊腳本：
- Windows：`run_windows.bat`
- macOS：`run_mac.command`（第一次請先在終端機執行 `chmod +x run_mac.command`）

## 基本使用流程

### 下載 YouTube 原生 SRT 字幕

1. 貼上 YouTube 影片連結
2. 按「開始分析 / 讀取字幕」
3. 若影片有原生 SRT：右側會列出可下載語系，勾選後按「下載選取 SRT 字幕」
4. 若影片沒有原生 SRT：會自動開啟辨識工具

### Whisper 辨識（沒有 SRT 時）

1. 在辨識工具中，來源可選：
   - 貼上 YouTube 網址後按「使用網址」
   - 或按「選擇本機檔」
2. 設定模型/語言/裝置等，按「開始辨識」
3. 完成後：
   - 「另存 SRT」：存出 `.srt`
   - 「下載逐字稿」：存出 `.txt`

## 輸出資料夾

主介面左側的「字幕儲存資料夾」是整個工具的輸出資料夾：
- YouTube 字幕下載
- Whisper 辨識輸出（包含自動產出的 SRT 檔）
- 影片/音訊下載

辨識工具的「打開輸出資料夾」也會開啟同一個資料夾。

## 常見問題

### 1. 讀取 YouTube 失敗，顯示 Video unavailable / This video is not available

這通常代表影片本身不可讀取（例如：已刪除、私人、地區/年齡限制），或網址 ID 有誤。此情況下工具也無法下載音訊進行辨識。

### 2. 第一次辨識很慢正常嗎？

正常。第一次使用 Whisper 模型會下載模型檔，時間會比較久。
