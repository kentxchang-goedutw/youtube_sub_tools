# YouTube 字幕下載生成工具使用說明

## 一、軟體功能

本工具是一個桌面版 YouTube 字幕處理工具，主要功能如下：

1. 貼上 YouTube 影片連結後，自動分析影片是否有 CC 字幕或 YouTube 自動字幕。
2. 如果影片有字幕，會顯示可下載的字幕語系，使用者可選擇語系與格式後直接下載字幕檔。
3. 如果影片沒有字幕，程式會自動開啟語音辨識工具，下載影片音訊後使用 Whisper 進行辨識，並產生 SRT 字幕。
4. 支援本機音訊或影片檔辨識，可將自己的 MP3、MP4、WAV、M4A 等檔案轉成字幕。
5. 可選擇 Whisper 模型、辨識語言、運算裝置、精度與字幕切割粒度。
6. 產生的字幕可另存為 SRT 檔，也可直接複製 SRT 內容。

## 二、安裝 Python

如果電腦尚未安裝 Python，請先安裝 Python 3。

### Windows

1. 前往 Python 官方網站下載：<https://www.python.org/downloads/>
2. 下載最新版 Python 3。
3. 安裝時請務必勾選 `Add python.exe to PATH`。
4. 安裝完成後，開啟「命令提示字元」或「PowerShell」，輸入：

```bash
python --version
```

如果看到 Python 版本號，代表安裝成功。

### macOS

macOS 可使用官方安裝檔，或使用 Homebrew 安裝。

官方下載：<https://www.python.org/downloads/>

安裝完成後，開啟「終端機」輸入：

```bash
python3 --version
```

如果看到 Python 版本號，代表安裝成功。

## 三、安裝需要的套件

請先打開終端機或命令提示字元，切換到本工具所在的資料夾。

例如：

```bash
cd "工具資料夾路徑"
```

接著安裝所有需要的套件：

### Windows

```bash
python -m pip install -r requirements.txt
```

### macOS

```bash
python3 -m pip install -r requirements.txt
```

如果安裝過程很久是正常的，因為語音辨識需要下載較大的相關套件。

## 四、啟動工具

套件安裝完成後，可以直接執行 Python 工具。

### Windows

```bash
python youtube_subtitle_tool.py
```

### macOS

```bash
python3 youtube_subtitle_tool.py
```

執行後會開啟桌面視窗。

## 五、基本使用流程

1. 在左側輸入框貼上 YouTube 影片連結。
2. 按下大型按鈕「開始分析 / 讀取字幕」。
3. 程式會自動判斷影片是否有字幕。
4. 如果有字幕，右側會出現字幕語系清單。
5. 勾選想下載的字幕語系。
6. 選擇字幕格式，通常建議使用 `srt`。
7. 按下「下載選取字幕」。
8. 如果影片沒有字幕，程式會開啟語音辨識工具。
9. 在辨識工具中確認模型、語言與設定後，按下「開始辨識」。
10. 辨識完成後，可按「另存 SRT」下載字幕檔。

## 六、輸出位置

直接下載的 YouTube 字幕預設會儲存在：

```text
下載資料夾/YouTube字幕下載
```

語音辨識產生的字幕會儲存在工具資料夾中的：

```text
outputs
```

也可以在工具內使用「另存 SRT」選擇自己想要的位置。

## 七、常見問題

### 1. 按下後顯示沒有字幕怎麼辦？

代表該影片沒有可直接下載的 CC 字幕或 YouTube 自動字幕。請使用自動開啟的語音辨識工具產生字幕。

### 2. 第一次辨識很慢正常嗎？

正常。第一次使用 Whisper 模型時，可能需要下載模型檔，時間會比較久。

### 3. 要選哪一個 Whisper 模型？

一般建議：

- `small`：速度較快，適合一般使用。
- `medium`：準確度較好，但速度較慢。
- `large-v3`：準確度更高，但需要較多電腦資源。

### 4. 沒有 GPU 可以使用嗎？

可以。裝置選擇 `auto` 或 `cpu` 即可，只是辨識速度會比較慢。

### 5. 建議字幕格式選哪一個？

一般用途建議選 `srt`，這是最常見、最容易匯入影片剪輯軟體或播放器的字幕格式。
