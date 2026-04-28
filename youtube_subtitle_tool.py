"""
YouTube 多語系字幕下載工具
==================================================

功能：
1. 使用 customtkinter 建立現代化桌面圖形介面。
2. 左右二欄式主畫面，視窗尺寸 780x680。
3. 字幕清單使用可順暢滑動的捲動區。
4. 主畫面下方固定顯示 Made by 阿剛老師。
5. 阿剛老師文字可點擊，並以新瀏覽器視窗開啟：
   https://kentxchang.blogspot.tw
6. 加入簡單中文 CC 授權說明。
7. 使用 yt-dlp 讀取 YouTube 手動字幕與自動產生字幕。
8. 可選擇字幕語系下載。
安裝：
    pip install yt-dlp customtkinter

執行：
    python youtube_subtitle_tool.py
"""

import json
import importlib.util
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox

import yt_dlp


APP_NAME = "YouTube 多語系字幕下載工具"
AUTHOR_NAME = "阿剛老師"
AUTHOR_URL = "https://kentxchang.blogspot.tw"
CC_LICENSE_TEXT = (
    "本工具由阿剛老師製作，採用 CC BY-NC-SA 4.0 授權分享："
    "歡迎教學與非商業使用，請保留作者姓名，修改後請以相同方式分享。"
)
RECOGNITION_USAGE_TEXT = (
    "辨識工具說明：可處理沒有 CC 字幕的 YouTube 影片，也可選擇本機音訊或影片。"
    "請先確認模型、語言、裝置與切割粒度；按「開始辨識」後會產生逐字稿與 SRT，"
    "完成後可使用「另存 SRT」或「複製 SRT」下載/取用字幕。"
)
DEFAULT_DOWNLOAD_DIR = str(Path.home() / "Downloads" / "YouTube字幕下載")
APP_DIR = Path(__file__).resolve().parent
WHISPER_OUTPUT_DIR = APP_DIR / "outputs"
WHISPER_MEDIA_DIR = WHISPER_OUTPUT_DIR / "youtube_media"
ALLOWED_EXTENSIONS = {".mp3", ".mp4", ".wav", ".m4a", ".ogg", ".webm", ".mkv", ".mov", ".aac", ".flac"}

SEGMENT_RULES = {
    "fine": {"label": "細緻", "max_chars": 24, "max_duration": 4.2, "punctuation": "，。！？；,.!?;"},
    "standard": {"label": "標準", "max_chars": 36, "max_duration": 6.5, "punctuation": "。！？；.!?;"},
    "loose": {"label": "寬鬆", "max_chars": 58, "max_duration": 9.5, "punctuation": "。！？.!?"},
}

LANGUAGES = {
    "自動判斷": "",
    "中文": "zh",
    "英文": "en",
    "日文": "ja",
    "韓文": "ko",
    "西班牙文": "es",
}



def resource_path(relative_path: str) -> Path:
    """
    取得資源檔案路徑，支援 PyInstaller onefile (sys._MEIPASS)。

    Args:
        relative_path: 相對於專案根目錄的路徑，例如 "assets/app_icon.ico"。

    Returns:
        絕對路徑 Path。
    """
    base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base_dir / relative_path


class SubtitleService:
    """YouTube 字幕讀取與下載服務。"""

    def __init__(self) -> None:
        """初始化服務狀態。"""
        self.last_video_info: Optional[Dict[str, Any]] = None
        self.last_caption_tracks: List[Dict[str, Any]] = []

    @staticmethod
    def sanitize_filename(name: str) -> str:
        """
        將影片標題或語系代碼轉為安全檔名。

        Args:
            name: 原始名稱。

        Returns:
            安全檔名。
        """
        cleaned = re.sub(r'[\\/:*?"<>|]+', "_", name)
        cleaned = re.sub(r"\s+", "_", cleaned)
        cleaned = re.sub(r"_+", "_", cleaned)
        return cleaned.strip("._ ") or "youtube_subtitle"

    @staticmethod
    def build_ydl_options() -> Dict[str, Any]:
        """
        建立 yt-dlp 設定。

        Returns:
            yt-dlp options。
        """
        return {
            "skip_download": True,
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "ignoreerrors": False,
            "extract_flat": False,
        }

    def get_video_info(self, youtube_url: str) -> Dict[str, Any]:
        """
        取得 YouTube 影片資訊與字幕清單。

        Args:
            youtube_url: YouTube 影片連結。

        Returns:
            影片資訊。

        Raises:
            ValueError: 當網址錯誤或讀取失敗。
        """
        youtube_url = youtube_url.strip()

        if not youtube_url:
            raise ValueError("請輸入 YouTube 影片連結。")

        try:
            with yt_dlp.YoutubeDL(self.build_ydl_options()) as ydl:
                info = ydl.extract_info(youtube_url, download=False)
        except Exception as exc:
            raise ValueError(f"無法讀取影片資訊：{exc}") from exc

        if not info:
            raise ValueError("無法取得影片資訊。")

        self.last_video_info = info
        self.last_caption_tracks = self.extract_caption_tracks(info)
        return info

    def extract_caption_tracks(self, video_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        整理手動字幕與自動產生字幕。

        Args:
            video_info: yt-dlp 影片資訊。

        Returns:
            字幕軌道清單。
        """
        tracks: List[Dict[str, Any]] = []
        subtitles = video_info.get("subtitles") or {}
        automatic_captions = video_info.get("automatic_captions") or {}
        index = 0

        for language_code, formats in subtitles.items():
            if isinstance(formats, list):
                tracks.append(
                    {
                        "index": index,
                        "language_code": language_code,
                        "name": self.guess_language_name(language_code),
                        "kind": "manual",
                        "kind_label": "手動字幕",
                        "formats": self.extract_available_formats(formats),
                        "raw_formats": formats,
                    }
                )
                index += 1

        for language_code, formats in automatic_captions.items():
            if isinstance(formats, list):
                tracks.append(
                    {
                        "index": index,
                        "language_code": language_code,
                        "name": self.guess_language_name(language_code),
                        "kind": "auto",
                        "kind_label": "自動產生字幕",
                        "formats": self.extract_available_formats(formats),
                        "raw_formats": formats,
                    }
                )
                index += 1

        return tracks

    @staticmethod
    def extract_available_formats(formats: List[Dict[str, Any]]) -> List[str]:
        """
        取得字幕可用格式。

        Args:
            formats: yt-dlp 字幕格式列表。

        Returns:
            格式清單。
        """
        result: List[str] = []

        for item in formats:
            ext = str(item.get("ext") or "").strip()
            if ext and ext not in result:
                result.append(ext)

        order = ["srt", "vtt", "json3", "srv1", "srv2", "srv3", "ttml"]
        return sorted(result, key=lambda value: order.index(value) if value in order else len(order))

    @staticmethod
    def guess_language_name(language_code: str) -> str:
        """
        將常見語系代碼轉成中文名稱。

        Args:
            language_code: 語系代碼。

        Returns:
            中文語系名稱或原始代碼。
        """
        language_map = {
            "zh": "中文",
            "zh-Hant": "繁體中文",
            "zh-Hans": "簡體中文",
            "zh-TW": "繁體中文",
            "zh-CN": "簡體中文",
            "en": "英文",
            "ja": "日文",
            "ko": "韓文",
            "fr": "法文",
            "de": "德文",
            "es": "西班牙文",
            "it": "義大利文",
            "pt": "葡萄牙文",
            "ru": "俄文",
            "vi": "越南文",
            "th": "泰文",
            "id": "印尼文",
            "ms": "馬來文",
        }
        return language_map.get(language_code, language_code)

    def find_track_by_index(self, index: int) -> Dict[str, Any]:
        """
        依照 index 找字幕軌道。

        Args:
            index: 字幕 index。

        Returns:
            字幕軌道資料。

        Raises:
            ValueError: 找不到字幕。
        """
        for track in self.last_caption_tracks:
            if int(track["index"]) == int(index):
                return track

        raise ValueError("找不到指定字幕。")

    @staticmethod
    def choose_format_url(track: Dict[str, Any], target_format: str) -> Tuple[str, str]:
        """
        找出指定格式字幕下載網址。

        Args:
            track: 字幕軌道。
            target_format: 目標格式。

        Returns:
            實際格式與下載網址。

        Raises:
            ValueError: 找不到可下載網址。
        """
        raw_formats = track.get("raw_formats") or []

        for item in raw_formats:
            ext = str(item.get("ext") or "").strip()
            url = str(item.get("url") or "").strip()

            if ext == target_format and url:
                return ext, url

        for item in raw_formats:
            ext = str(item.get("ext") or "").strip()
            url = str(item.get("url") or "").strip()

            if url:
                return ext or target_format, url

        raise ValueError("找不到可下載的字幕網址。")

    def download_caption(
        self,
        youtube_url: str,
        track_index: int,
        target_format: str,
        output_dir: str,
    ) -> str:
        """
        下載指定字幕到本機資料夾。

        Args:
            youtube_url: YouTube 影片連結。
            track_index: 字幕 index。
            target_format: 目標格式。
            output_dir: 輸出資料夾。

        Returns:
            下載後的檔案路徑。
        """
        if not self.last_video_info or not self.last_caption_tracks:
            self.get_video_info(youtube_url)

        track = self.find_track_by_index(track_index)
        actual_format, subtitle_url = self.choose_format_url(track, target_format)

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        title = str(self.last_video_info.get("title") or "youtube_subtitle")
        safe_title = self.sanitize_filename(title)
        language_code = self.sanitize_filename(str(track.get("language_code") or "unknown"))
        kind = self.sanitize_filename(str(track.get("kind") or "caption"))
        file_path = output_path / f"{safe_title}_{language_code}_{kind}.{actual_format}"

        request_obj = urllib.request.Request(
            subtitle_url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                )
            },
        )

        try:
            with urllib.request.urlopen(request_obj, timeout=30) as response:
                file_path.write_bytes(response.read())
        except Exception as exc:
            raise ValueError(f"字幕下載失敗：{exc}") from exc

        return str(file_path)

    def download_media_for_transcription(
        self,
        youtube_url: str,
        output_dir: Path,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> Path:
        """
        下載 YouTube 音訊或影片媒體，供 Whisper 辨識使用。

        Args:
            youtube_url: YouTube 影片連結。
            output_dir: 暫存輸出資料夾。
            progress_callback: 進度訊息回呼。

        Returns:
            已下載媒體檔案路徑。
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        def notify(message: str) -> None:
            if progress_callback is not None:
                progress_callback(message)

        def progress_hook(status: Dict[str, Any]) -> None:
            if status.get("status") == "downloading":
                downloaded = float(status.get("downloaded_bytes") or 0)
                total = float(status.get("total_bytes") or status.get("total_bytes_estimate") or 0)
                if total > 0:
                    notify(f"正在下載 YouTube 音訊：{downloaded / total * 100:.1f}%")
                else:
                    notify("正在下載 YouTube 音訊……")
            elif status.get("status") == "finished":
                notify("音訊下載完成，準備進行辨識。")

        options = {
            "format": "bestaudio/best",
            "outtmpl": str(output_dir / "%(title).160B-%(id)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "restrictfilenames": True,
            "progress_hooks": [progress_hook],
        }

        notify("正在下載沒有 CC 字幕的 YouTube 影片音訊。")
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(youtube_url, download=True)
                requested = info.get("requested_downloads") or []
                for item in requested:
                    file_path = Path(str(item.get("filepath") or ""))
                    if file_path.exists():
                        return file_path

                prepared = Path(ydl.prepare_filename(info))
                if prepared.exists():
                    return prepared

                video_id = str(info.get("id") or "")
                candidates = sorted(output_dir.glob(f"*{video_id}*"), key=lambda path: path.stat().st_mtime, reverse=True)
                if candidates:
                    return candidates[0]
        except Exception as exc:
            raise ValueError(f"YouTube 音訊下載失敗：{exc}") from exc

        raise ValueError("YouTube 音訊下載完成，但找不到輸出的媒體檔。")



class WhisperTranscriptionService:
    """faster-whisper 本機字幕產生服務。"""

    def transcribe_media(
        self,
        file_path: Path,
        model_name: str,
        language: str,
        device_request: str,
        compute_request: str,
        segment_mode: str,
        output_dir: Path,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        started_at = time.perf_counter()
        output_dir.mkdir(parents=True, exist_ok=True)

        def notify(message: str) -> None:
            if progress_callback is not None:
                progress_callback(message)

        if importlib.util.find_spec("faster_whisper") is None:
            raise RuntimeError("缺少 faster-whisper，請先安裝 faster-whisper 後再使用辨識功能。")

        from faster_whisper import WhisperModel

        device = resolve_device(device_request)
        compute_type = resolve_compute_type(device, compute_request)

        notify(f"使用 {device} / {compute_type} 載入 {model_name} 模型。")
        try:
            model = WhisperModel(model_name, device=device, compute_type=compute_type)
        except Exception as exc:
            if device != "cuda" or not is_cuda_runtime_error(exc):
                raise

            notify("CUDA runtime 不完整，已自動改用 CPU / int8。")
            device = "cpu"
            compute_type = "int8"
            model = WhisperModel(model_name, device=device, compute_type=compute_type)

        vad_enabled = package_available("onnxruntime")
        if not vad_enabled:
            notify("未偵測到 onnxruntime，已關閉 VAD 靜音過濾。")

        segments_iter, info = model.transcribe(
            str(file_path),
            language=language or None,
            vad_filter=vad_enabled,
            beam_size=5,
        )

        raw_segments: List[Dict[str, Any]] = []
        for segment in segments_iter:
            text = clean_text(segment.text)
            if text:
                raw_segments.append({"start": float(segment.start), "end": float(segment.end), "text": text})
                notify(f"已處理到 {format_short_time(float(segment.end))}。")

        if not raw_segments:
            raise RuntimeError("沒有辨識到可輸出的字幕內容。")

        subtitle_segments = rebuild_segments(raw_segments, segment_mode)
        transcript = "\n".join(str(segment["text"]) for segment in subtitle_segments)
        srt = to_srt(subtitle_segments)

        output_name = f"{sanitize_stem(file_path.stem)}-{int(time.time())}.srt"
        output_path = output_dir / output_name
        output_path.write_text("\ufeff" + srt, encoding="utf-8")

        return {
            "transcript": transcript,
            "srt": srt,
            "meta": {
                "model": model_name,
                "device": device,
                "compute_type": compute_type,
                "language": getattr(info, "language", None),
                "duration": getattr(info, "duration", None),
                "elapsed": round(time.perf_counter() - started_at, 2),
                "segments": len(subtitle_segments),
                "output_path": output_path,
            },
        }


def collect_environment() -> Dict[str, Any]:
    package_names = ["customtkinter", "yt_dlp", "faster_whisper", "ctranslate2", "av", "onnxruntime"]
    packages = {name: package_available(name) for name in package_names}
    cuda_devices = 0
    ctranslate2_error = None

    if packages["ctranslate2"]:
        try:
            import ctranslate2

            cuda_devices = int(ctranslate2.get_cuda_device_count())
        except Exception as exc:
            ctranslate2_error = str(exc)

    return {
        "python": sys.version.split()[0],
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "packages": packages,
        "nvidia_smi": check_nvidia_smi(),
        "cuda_device_count": cuda_devices,
        "cuda_available": cuda_devices > 0,
        "ctranslate2_error": ctranslate2_error,
        "recommended_device": "cuda" if cuda_devices > 0 else "cpu",
    }


def check_nvidia_smi() -> Dict[str, Any]:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return {"available": False, "text": "找不到 nvidia-smi"}

    try:
        result = subprocess.run(
            [executable, "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            check=True,
            timeout=8,
        )
    except Exception as exc:
        return {"available": False, "text": str(exc)}

    return {"available": True, "text": result.stdout.strip()}


def package_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def resolve_device(requested: str) -> str:
    if requested != "auto":
        return requested
    try:
        import ctranslate2

        return "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
    except Exception:
        return "cpu"


def resolve_compute_type(device: str, requested: str) -> str:
    if device == "cpu":
        return "int8"
    return requested or "float16"


def is_cuda_runtime_error(exc: Exception) -> bool:
    text = str(exc).lower()
    markers = ["cublas64", "cudnn", "cudart", "cuda", "library", "dll", "not found", "cannot be loaded"]
    return any(marker in text for marker in markers)


def rebuild_segments(chunks: List[Dict[str, Any]], mode: str) -> List[Dict[str, Any]]:
    rule = SEGMENT_RULES.get(mode, SEGMENT_RULES["standard"])
    segments: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None

    for chunk in chunks:
        text_parts = split_text(str(chunk["text"]), rule)
        duration = max(0.2, float(chunk["end"]) - float(chunk["start"]))
        cursor = float(chunk["start"])

        for part in text_parts:
            ratio = len(part) / max(len(str(chunk["text"])), 1)
            part_duration = max(0.55, duration * ratio)
            next_segment = {
                "start": cursor,
                "end": min(cursor + part_duration, float(chunk["end"])),
                "text": part,
            }
            cursor = float(next_segment["end"])

            if current is None:
                current = dict(next_segment)
                continue

            separator = " " if needs_space(str(current["text"]), str(next_segment["text"])) else ""
            candidate_text = f"{current['text']}{separator}{next_segment['text']}"
            candidate_duration = float(next_segment["end"]) - float(current["start"])
            ends_cleanly = str(current["text"])[-1:] in rule["punctuation"]

            if (
                len(candidate_text) <= rule["max_chars"]
                and candidate_duration <= rule["max_duration"]
                and not ends_cleanly
            ):
                current["text"] = candidate_text
                current["end"] = next_segment["end"]
            else:
                segments.append(current)
                current = dict(next_segment)

    if current is not None:
        segments.append(current)

    for index, segment in enumerate(segments):
        next_start = segments[index + 1]["start"] if index + 1 < len(segments) else segment["end"]
        segment["end"] = max(float(segment["end"]), float(segment["start"]) + 0.5, float(next_start))
        segment["start"] = round(float(segment["start"]), 3)
        segment["end"] = round(float(segment["end"]), 3)

    return segments


def split_text(text: str, rule: Dict[str, Any]) -> List[str]:
    clean = clean_text(text)
    if len(clean) <= rule["max_chars"]:
        return [clean]

    parts: List[str] = []
    buffer = ""
    for char in clean:
        buffer += char
        should_split = len(buffer) >= rule["max_chars"] or (
            len(buffer) >= rule["max_chars"] * 0.65 and char in rule["punctuation"]
        )
        if should_split:
            parts.append(buffer.strip())
            buffer = ""

    if buffer.strip():
        parts.append(buffer.strip())
    return parts


def to_srt(segments: List[Dict[str, Any]]) -> str:
    blocks = []
    for index, segment in enumerate(segments, start=1):
        blocks.append(
            f"{index}\n"
            f"{format_srt_time(float(segment['start']))} --> {format_srt_time(float(segment['end']))}\n"
            f"{segment['text']}"
        )
    return "\n\n".join(blocks)


def format_srt_time(seconds: float) -> str:
    safe = max(0.0, seconds)
    hours = int(safe // 3600)
    minutes = int((safe % 3600) // 60)
    secs = int(safe % 60)
    millis = int((safe % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def format_short_time(seconds: float) -> str:
    safe = max(0.0, seconds)
    minutes = int(safe // 60)
    secs = int(safe % 60)
    return f"{minutes:02d}:{secs:02d}"


def clean_text(text: str) -> str:
    return " ".join(str(text).split()).strip()


def needs_space(left: str, right: str) -> bool:
    return bool(left and right and left[-1].isascii() and left[-1].isalnum() and right[0].isascii() and right[0].isalnum())


def sanitize_stem(value: str) -> str:
    safe = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value).strip("-")
    return safe or "subtitle"


def readable_bytes(bytes_count: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    value = float(bytes_count)
    unit = 0
    while value >= 1024 and unit < len(units) - 1:
        value /= 1024
        unit += 1
    return f"{value:.0f} {units[unit]}" if unit == 0 else f"{value:.1f} {units[unit]}"


def open_folder(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform.startswith("win"):
        subprocess.Popen(["explorer", str(path)])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def set_window_icon(root: ctk.CTk) -> None:
    png_icon = resource_path("assets/app_icon.png")
    ico_icon = resource_path("assets/app_icon.ico")

    try:
        if png_icon.exists():
            icon_image = tk.PhotoImage(file=str(png_icon))
            root.iconphoto(True, icon_image)
            root._app_icon_image = icon_image
    except Exception:
        pass

    try:
        if ico_icon.exists():
            root.iconbitmap(default=str(ico_icon))
    except Exception:
        pass


subtitle_service = SubtitleService()
whisper_service = WhisperTranscriptionService()


class RecognitionWindow(ctk.CTkToplevel):
    """YouTube 無字幕與本機媒體共用的 Whisper 辨識工具。"""

    def __init__(
        self,
        master: ctk.CTk,
        youtube_url: str = "",
        video_title: str = "",
        service: Optional[SubtitleService] = None,
    ) -> None:
        super().__init__(master)
        self.youtube_url = youtube_url
        self.video_title = video_title
        self.subtitle_service = service or subtitle_service
        self.whisper_service = whisper_service
        self.events: "queue.Queue[Tuple[str, Any]]" = queue.Queue()
        self.worker: Optional[threading.Thread] = None
        self.file_path: Optional[Path] = None
        self.last_srt = ""
        self.last_output_path: Optional[Path] = None

        self.model_var = tk.StringVar(value="medium")
        self.language_var = tk.StringVar(value="自動判斷")
        self.device_var = tk.StringVar(value="auto")
        self.compute_var = tk.StringVar(value="float16")
        self.segment_var = tk.StringVar(value="standard")
        self.status_var = tk.StringVar(value="YouTube 無 CC 字幕，按「開始辨識」會先下載音訊再產生 SRT。" if youtube_url else "請選擇媒體檔或貼回主畫面讀取 YouTube。")
        self.source_title_var = tk.StringVar(value=video_title or youtube_url or "可選擇音訊或影片檔進行辨識")
        self.file_var = tk.StringVar(value="來源：YouTube 影片" if youtube_url else "尚未選擇媒體檔")
        self.meta_var = tk.StringVar(value="")

        self.title("YouTube 字幕辨識生成工具")
        self.geometry("980x760")
        self.minsize(840, 700)
        self.configure(fg_color="#f6f3f8")
        self.transient(master)

        self.build_ui()
        self.poll_events()

    def build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        hero = ctk.CTkFrame(self, fg_color="#ffffff", corner_radius=20)
        hero.grid(row=0, column=0, padx=14, pady=(12, 8), sticky="ew")
        hero.grid_columnconfigure(1, weight=1)

        logo = ctk.CTkFrame(hero, width=44, height=44, fg_color="#287fec", corner_radius=14)
        logo.grid(row=0, column=0, rowspan=2, padx=(18, 14), pady=12, sticky="n")
        logo.grid_propagate(False)
        ctk.CTkLabel(logo, text="AI", text_color="#ffffff", font=ctk.CTkFont(size=20, weight="bold")).place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(
            hero,
            text="YouTube 字幕下載生成工具",
            text_color="#f64b88",
            font=ctk.CTkFont(family="Microsoft JhengHei UI", size=24, weight="bold"),
        ).grid(row=0, column=1, padx=(0, 18), pady=(10, 2), sticky="w")

        ctk.CTkLabel(
            hero,
            textvariable=self.status_var,
            text_color="#81768f",
            font=ctk.CTkFont(family="Microsoft JhengHei UI", size=13),
            wraplength=760,
            justify="left",
        ).grid(row=1, column=1, padx=(0, 18), pady=(0, 10), sticky="w")

        ctk.CTkLabel(
            hero,
            text=RECOGNITION_USAGE_TEXT,
            text_color="#57496a",
            fg_color="#fbf9fd",
            corner_radius=12,
            font=ctk.CTkFont(family="Microsoft JhengHei UI", size=12),
            wraplength=800,
            justify="left",
            padx=12,
            pady=8,
        ).grid(row=2, column=0, columnspan=2, padx=18, pady=(0, 10), sticky="ew")

        content = ctk.CTkFrame(self, fg_color="transparent")
        content.grid(row=1, column=0, padx=14, pady=(0, 12), sticky="nsew")
        content.grid_columnconfigure(0, weight=40)
        content.grid_columnconfigure(1, weight=60)
        content.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(content, fg_color="#ffffff", corner_radius=22)
        left.grid(row=0, column=0, padx=(0, 7), sticky="nsew")
        right = ctk.CTkFrame(content, fg_color="#ffffff", corner_radius=22)
        right.grid(row=0, column=1, padx=(7, 0), sticky="nsew")

        self.build_left(left)
        self.build_right(right)

    def build_left(self, parent: ctk.CTkFrame) -> None:
        parent.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(parent, text="媒體來源", text_color="#30283f", font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, padx=18, pady=(14, 6), sticky="w"
        )

        source_box = ctk.CTkFrame(parent, fg_color="#fbf9fd", border_width=1, border_color="#d9d0e5", corner_radius=16)
        source_box.grid(row=1, column=0, padx=18, sticky="ew")
        source_box.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(source_box, textvariable=self.source_title_var, text_color="#625875", wraplength=330, justify="left").grid(
            row=0, column=0, padx=14, pady=(12, 4), sticky="ew"
        )
        ctk.CTkLabel(source_box, textvariable=self.file_var, text_color="#81768f", wraplength=330, justify="left").grid(
            row=1, column=0, padx=14, pady=(0, 12), sticky="ew"
        )
        ctk.CTkButton(source_box, text="選擇本機檔", width=112, height=34, command=self.choose_file).grid(
            row=0, column=1, rowspan=2, padx=(8, 14), pady=12, sticky="e"
        )

        settings = ctk.CTkFrame(parent, fg_color="transparent")
        settings.grid(row=2, column=0, padx=18, pady=(10, 0), sticky="ew")
        settings.grid_columnconfigure((0, 1), weight=1)

        self.add_option(settings, "模型", self.model_var, ["tiny", "base", "small", "medium", "large-v3"], 0, 0)
        self.add_option(settings, "語言", self.language_var, list(LANGUAGES.keys()), 0, 1)
        self.add_option(settings, "裝置", self.device_var, ["auto", "cuda", "cpu"], 1, 0)
        self.add_option(settings, "精度", self.compute_var, ["float16", "int8_float16", "int8"], 1, 1)

        segment_box = ctk.CTkFrame(parent, fg_color="#fbf9fd", corner_radius=16)
        segment_box.grid(row=3, column=0, padx=18, pady=(8, 0), sticky="ew")
        segment_box.grid_columnconfigure((0, 1, 2), weight=1)
        ctk.CTkLabel(segment_box, text="字幕切割粒度", text_color="#30283f", font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=0, column=0, columnspan=3, padx=14, pady=(10, 4), sticky="w"
        )
        for column, (value, text) in enumerate([("fine", "細緻"), ("standard", "標準"), ("loose", "寬鬆")]):
            ctk.CTkRadioButton(segment_box, text=text, value=value, variable=self.segment_var).grid(
                row=1, column=column, padx=(14 if column == 0 else 6, 14 if column == 2 else 6), pady=(2, 12), sticky="w"
            )

        actions = ctk.CTkFrame(parent, fg_color="transparent")
        actions.grid(row=4, column=0, padx=18, pady=(12, 6), sticky="ew")
        actions.grid_columnconfigure((0, 1), weight=1)
        self.check_button = ctk.CTkButton(actions, text="檢查環境", height=36, fg_color="#2dc9be", hover_color="#23aaa1", command=self.check_environment)
        self.check_button.grid(row=0, column=0, padx=(0, 6), sticky="ew")
        self.transcribe_button = ctk.CTkButton(
            actions,
            text="開始辨識",
            height=36,
            fg_color="#ff9b44",
            hover_color="#e58432",
            command=self.start_transcribe,
        )
        self.transcribe_button.grid(row=0, column=1, padx=(6, 0), sticky="ew")

        save_actions = ctk.CTkFrame(parent, fg_color="transparent")
        save_actions.grid(row=5, column=0, padx=18, pady=(4, 14), sticky="ew")
        save_actions.grid_columnconfigure((0, 1), weight=1)
        self.save_button = ctk.CTkButton(save_actions, text="另存 SRT", height=34, command=self.save_as, state="disabled")
        self.save_button.grid(row=0, column=0, padx=(0, 6), sticky="ew")
        ctk.CTkButton(save_actions, text="打開輸出資料夾", height=34, command=lambda: open_folder(WHISPER_OUTPUT_DIR)).grid(
            row=0, column=1, padx=(6, 0), sticky="ew"
        )

    def build_right(self, parent: ctk.CTkFrame) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        head = ctk.CTkFrame(parent, fg_color="transparent")
        head.grid(row=0, column=0, padx=18, pady=(16, 8), sticky="ew")
        head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(head, text="辨識輸出", text_color="#30283f", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(head, textvariable=self.meta_var, text_color="#81768f").grid(row=0, column=1, sticky="e")

        self.tabs = ctk.CTkTabview(parent, fg_color="#fbf9fd", segmented_button_fg_color="#ede8f3")
        self.tabs.grid(row=1, column=0, padx=18, sticky="nsew")
        transcript_tab = self.tabs.add("逐字稿")
        srt_tab = self.tabs.add("SRT")
        transcript_tab.grid_columnconfigure(0, weight=1)
        transcript_tab.grid_rowconfigure(0, weight=1)
        srt_tab.grid_columnconfigure(0, weight=1)
        srt_tab.grid_rowconfigure(0, weight=1)

        self.transcript_text = ctk.CTkTextbox(transcript_tab, fg_color="#ffffff", text_color="#30283f", corner_radius=12, wrap="word")
        self.transcript_text.grid(row=0, column=0, padx=6, pady=6, sticky="nsew")
        self.srt_text = ctk.CTkTextbox(srt_tab, fg_color="#ffffff", text_color="#30283f", corner_radius=12, wrap="none")
        self.srt_text.grid(row=0, column=0, padx=6, pady=6, sticky="nsew")

        output_actions = ctk.CTkFrame(parent, fg_color="transparent")
        output_actions.grid(row=2, column=0, padx=18, pady=(12, 18), sticky="ew")
        output_actions.grid_columnconfigure((0, 1), weight=1)
        self.copy_button = ctk.CTkButton(output_actions, text="複製 SRT", height=36, command=self.copy_srt, state="disabled")
        self.copy_button.grid(row=0, column=0, padx=(0, 6), sticky="ew")
        ctk.CTkButton(output_actions, text="清除輸出", height=36, fg_color="#6758e8", hover_color="#5749cb", command=self.clear_outputs).grid(
            row=0, column=1, padx=(6, 0), sticky="ew"
        )

    def add_option(
        self,
        parent: ctk.CTkFrame,
        label: str,
        variable: tk.StringVar,
        values: List[str],
        row: int,
        column: int,
    ) -> None:
        box = ctk.CTkFrame(parent, fg_color="transparent")
        box.grid(row=row, column=column, padx=(0 if column == 0 else 6, 0 if column == 1 else 6), pady=(0, 9), sticky="ew")
        ctk.CTkLabel(box, text=label, text_color="#30283f", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", pady=(0, 4))
        ctk.CTkOptionMenu(box, variable=variable, values=values, height=34).pack(fill="x")

    def choose_file(self) -> None:
        path = filedialog.askopenfilename(
            title="選擇音訊或影片",
            filetypes=[
                ("媒體檔", "*.mp3 *.mp4 *.wav *.m4a *.ogg *.webm *.mkv *.mov *.aac *.flac"),
                ("所有檔案", "*.*"),
            ],
        )
        if not path:
            return

        selected = Path(path)
        if selected.suffix.lower() not in ALLOWED_EXTENSIONS:
            if not messagebox.askyesno("格式確認", "這個副檔名不在常見清單內，仍要嘗試辨識嗎？"):
                return

        self.file_path = selected
        self.source_title_var.set("本機媒體檔")
        self.file_var.set(f"{selected.name}\n{readable_bytes(selected.stat().st_size)}")
        self.status_var.set("本機檔案已就緒，可以開始辨識。")

    def check_environment(self) -> None:
        env = collect_environment()
        text = [
            f"Python：{env['python']}",
            f"執行位置：{APP_DIR}",
            f"ffmpeg：{'可用' if env['ffmpeg'] else '未在 PATH 偵測到'}",
            f"nvidia-smi：{env['nvidia_smi']['text']}",
            f"CUDA 裝置數：{env['cuda_device_count']}",
            f"建議裝置：{env['recommended_device']}",
            "",
            "套件：",
        ]
        text.extend(f"- {name}: {'OK' if ok else '缺少'}" for name, ok in env["packages"].items())
        if env["ctranslate2_error"]:
            text.extend(["", f"CTranslate2 錯誤：{env['ctranslate2_error']}"])

        self.status_var.set("環境檢查完成，詳細資訊已放到逐字稿頁。")
        self.set_text(self.transcript_text, "\n".join(text))
        self.device_var.set("auto" if env["cuda_available"] else "cpu")

    def start_transcribe(self) -> None:
        if not self.file_path and not self.youtube_url:
            messagebox.showwarning("尚未選擇來源", "請先選擇媒體檔，或從主畫面貼 YouTube 連結讀取。")
            return
        if self.worker and self.worker.is_alive():
            return

        config = {
            "youtube_url": self.youtube_url,
            "file_path": self.file_path,
            "model_name": self.model_var.get(),
            "language": LANGUAGES.get(self.language_var.get(), ""),
            "device": self.device_var.get(),
            "compute_type": self.compute_var.get(),
            "segment_mode": self.segment_var.get(),
        }

        self.clear_outputs()
        self.set_busy(True)
        self.status_var.set("正在準備辨識工作。第一次使用該模型會下載模型檔。")
        self.worker = threading.Thread(target=self.transcribe_worker, args=(config,), daemon=True)
        self.worker.start()

    def transcribe_worker(self, config: Dict[str, Any]) -> None:
        try:
            media_path = config["file_path"]
            if media_path is None:
                media_path = self.subtitle_service.download_media_for_transcription(
                    str(config["youtube_url"]),
                    WHISPER_MEDIA_DIR,
                    progress_callback=lambda message: self.events.put(("status", message)),
                )
                self.events.put(("source", str(media_path)))

            result = self.whisper_service.transcribe_media(
                file_path=Path(media_path),
                model_name=str(config["model_name"]),
                language=str(config["language"]),
                device_request=str(config["device"]),
                compute_request=str(config["compute_type"]),
                segment_mode=str(config["segment_mode"]),
                output_dir=WHISPER_OUTPUT_DIR,
                progress_callback=lambda message: self.events.put(("status", message)),
            )
            self.events.put(("done", result))
        except Exception as exc:
            self.events.put(("error", str(exc)))

    def poll_events(self) -> None:
        try:
            while True:
                event, payload = self.events.get_nowait()
                if event == "status":
                    self.status_var.set(str(payload))
                elif event == "source":
                    path = Path(str(payload))
                    self.file_path = path
                    self.file_var.set(f"{path.name}\n{readable_bytes(path.stat().st_size)}")
                elif event == "done":
                    self.render_result(payload)
                    self.set_busy(False)
                elif event == "error":
                    self.set_busy(False)
                    self.status_var.set(f"辨識失敗：{payload}")
                    messagebox.showerror("辨識失敗", str(payload))
        except queue.Empty:
            pass
        self.after(160, self.poll_events)

    def render_result(self, payload: Dict[str, Any]) -> None:
        self.last_srt = str(payload["srt"])
        self.last_output_path = Path(payload["meta"]["output_path"])
        self.set_text(self.transcript_text, str(payload["transcript"]))
        self.set_text(self.srt_text, self.last_srt)
        meta = payload["meta"]
        self.meta_var.set(f"{meta['segments']} 段 · {meta['device']} · {meta['elapsed']} 秒")
        self.save_button.configure(state="normal")
        self.copy_button.configure(state="normal")
        self.status_var.set(f"辨識完成，已輸出：{self.last_output_path}")

    def save_as(self) -> None:
        if not self.last_srt:
            return
        default_name = self.last_output_path.name if self.last_output_path else "subtitle.srt"
        path = filedialog.asksaveasfilename(
            title="另存 SRT",
            defaultextension=".srt",
            initialfile=default_name,
            filetypes=[("SRT 字幕", "*.srt"), ("所有檔案", "*.*")],
        )
        if path:
            Path(path).write_text("\ufeff" + self.last_srt, encoding="utf-8")
            self.status_var.set(f"已另存：{path}")

    def copy_srt(self) -> None:
        if not self.last_srt:
            return
        self.clipboard_clear()
        self.clipboard_append(self.last_srt)
        self.status_var.set("已複製 SRT 到剪貼簿。")

    def clear_outputs(self) -> None:
        self.last_srt = ""
        self.last_output_path = None
        self.meta_var.set("")
        self.save_button.configure(state="disabled")
        self.copy_button.configure(state="disabled")
        self.set_text(self.transcript_text, "")
        self.set_text(self.srt_text, "")

    def set_busy(self, busy: bool) -> None:
        self.transcribe_button.configure(state="disabled" if busy else "normal")
        self.check_button.configure(state="disabled" if busy else "normal")

    @staticmethod
    def set_text(widget: ctk.CTkTextbox, text: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)


class SubtitleDownloaderGUI:
    """customtkinter 現代化左右二欄式桌面介面。"""

    def __init__(self, root: ctk.CTk) -> None:
        """
        初始化 GUI。

        Args:
            root: customtkinter 主視窗。
        """
        self.root = root
        self.service = subtitle_service
        self.message_queue: "queue.Queue[Tuple[str, str]]" = queue.Queue()
        self.caption_check_vars: Dict[int, tk.BooleanVar] = {}
        self.recognition_window: Optional[RecognitionWindow] = None

        self.url_var = tk.StringVar()
        self.output_dir_var = tk.StringVar(value=DEFAULT_DOWNLOAD_DIR)
        self.format_var = tk.StringVar(value="srt")
        self.status_var = tk.StringVar(value="請貼上 YouTube 連結後按下「讀取字幕」。")
        self.video_info_var = tk.StringVar(value="尚未讀取影片。")

        self.setup_window()
        self.create_widgets()
        self.poll_message_queue()

    def setup_window(self) -> None:
        """設定主視窗外觀。"""
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        self.root.title(APP_NAME)
        self.root.geometry("860x720")
        self.root.minsize(820, 680)
        self.root.configure(fg_color="#f8fafc")

    def create_widgets(self) -> None:
        """建立主畫面元件。"""
        self.main_frame = ctk.CTkFrame(self.root, fg_color="#f8fafc", corner_radius=0)
        self.main_frame.pack(fill="both", expand=True, padx=14, pady=10)
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(2, weight=1)

        self.create_header(self.main_frame)
        self.create_usage_panel(self.main_frame)
        self.create_body(self.main_frame)
        self.create_footer(self.main_frame)

    def create_header(self, parent: ctk.CTkFrame) -> None:
        """
        建立標題區。

        Args:
            parent: 父容器。
        """
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        header.grid_columnconfigure(1, weight=1)

        logo = ctk.CTkLabel(
            header,
            text="CC",
            width=46,
            height=46,
            corner_radius=16,
            fg_color=("#fb7185", "#fb7185"),
            text_color="white",
            font=ctk.CTkFont(size=19, weight="bold"),
        )
        logo.grid(row=0, column=0, padx=(0, 12), sticky="w")

        title_box = ctk.CTkFrame(header, fg_color="transparent")
        title_box.grid(row=0, column=1, sticky="ew")

        title = ctk.CTkLabel(
            title_box,
            text=APP_NAME,
            text_color="#be123c",
            font=ctk.CTkFont(size=22, weight="bold"),
            anchor="w",
        )
        title.pack(fill="x")

        subtitle = ctk.CTkLabel(
            title_box,
            text="貼上 YouTube 後會自動分析：有 CC 字幕就進入下載介面，沒有字幕就開啟語音辨識工具生成 SRT。",
            text_color="#64748b",
            font=ctk.CTkFont(size=13),
            anchor="w",
            justify="left",
            wraplength=650,
        )
        subtitle.pack(fill="x", pady=(2, 0))

    def create_usage_panel(self, parent: ctk.CTkFrame) -> None:
        """建立固定可見的使用流程說明。"""
        usage = ctk.CTkFrame(
            parent,
            fg_color="#fff7ed",
            corner_radius=14,
            border_width=1,
            border_color="#fed7aa",
        )
        usage.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        usage.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            usage,
            text="使用說明",
            text_color="#9a3412",
            font=ctk.CTkFont(size=13, weight="bold"),
            width=76,
            anchor="w",
        ).grid(row=0, column=0, padx=(12, 8), pady=10, sticky="nw")

        ctk.CTkLabel(
            usage,
            text=(
                "主要流程從左側大型「開始分析 / 讀取字幕」按鈕開始。貼上 YouTube 連結後按下該按鈕，程式會自動分析字幕狀態。"
                "有 CC 字幕或自動字幕時，右側會出現語系清單，可勾選後直接下載；"
                "沒有字幕時，會自動開啟語音辨識工具，下載音訊、辨識並產生 SRT 後再另存。"
                "也可按「辨識工具」處理本機音訊或影片。"
            ),
            text_color="#7c2d12",
            font=ctk.CTkFont(size=12),
            justify="left",
            anchor="w",
            wraplength=720,
        ).grid(row=0, column=1, padx=(0, 12), pady=10, sticky="ew")

    def create_body(self, parent: ctk.CTkFrame) -> None:
        """
        建立左右二欄主內容。

        Args:
            parent: 父容器。
        """
        body = ctk.CTkFrame(parent, fg_color="transparent")
        body.grid(row=2, column=0, sticky="nsew")

        body.grid_columnconfigure(0, weight=0, minsize=320)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        left_panel = ctk.CTkFrame(
            body,
            fg_color="white",
            corner_radius=22,
            border_width=1,
            border_color="#e2e8f0",
        )
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        right_panel = ctk.CTkFrame(
            body,
            fg_color="white",
            corner_radius=22,
            border_width=1,
            border_color="#e2e8f0",
        )
        right_panel.grid(row=0, column=1, sticky="nsew")

        self.create_left_panel(left_panel)
        self.create_right_panel(right_panel)

    def create_left_panel(self, parent: ctk.CTkFrame) -> None:
        """
        建立左側操作區。

        Args:
            parent: 父容器。
        """
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(11, weight=1)

        ctk.CTkLabel(
            parent,
            text="YouTube 影片連結",
            text_color="#475569",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 6))

        url_entry = ctk.CTkEntry(
            parent,
            textvariable=self.url_var,
            placeholder_text="貼上 YouTube 連結",
            height=38,
            corner_radius=14,
            border_color="#fecdd3",
        )
        url_entry.grid(row=1, column=0, sticky="ew", padx=16)
        url_entry.bind("<Return>", lambda _event: self.load_captions_async())

        primary_box = ctk.CTkFrame(
            parent,
            fg_color="#fff1f2",
            corner_radius=18,
            border_width=1,
            border_color="#fecdd3",
        )
        primary_box.grid(row=2, column=0, sticky="ew", padx=16, pady=(10, 12))
        primary_box.grid_columnconfigure(0, weight=1)

        self.load_button = ctk.CTkButton(
            primary_box,
            text="開始分析 / 讀取字幕",
            command=self.load_captions_async,
            height=50,
            corner_radius=18,
            fg_color="#e11d48",
            hover_color="#be123c",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        self.load_button.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))

        ctk.CTkLabel(
            primary_box,
            text="按下後會先檢查 YouTube 是否有 CC 字幕；有字幕就下載，沒有字幕就轉語音辨識。",
            text_color="#9f1239",
            font=ctk.CTkFont(size=12),
            anchor="w",
            justify="left",
            wraplength=280,
        ).grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 12))

        ctk.CTkLabel(
            parent,
            text="字幕儲存資料夾",
            text_color="#475569",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        ).grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 6))

        output_entry = ctk.CTkEntry(
            parent,
            textvariable=self.output_dir_var,
            height=38,
            corner_radius=14,
            border_color="#bae6fd",
        )
        output_entry.grid(row=4, column=0, sticky="ew", padx=16)

        choose_button = ctk.CTkButton(
            parent,
            text="選擇資料夾",
            command=self.choose_output_dir,
            height=34,
            corner_radius=16,
            fg_color="#e0f2fe",
            hover_color="#bae6fd",
            text_color="#0369a1",
        )
        choose_button.grid(row=5, column=0, sticky="ew", padx=16, pady=(8, 10))

        ctk.CTkLabel(
            parent,
            text="字幕格式",
            text_color="#475569",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        ).grid(row=6, column=0, sticky="ew", padx=16, pady=(0, 6))

        format_menu = ctk.CTkOptionMenu(
            parent,
            variable=self.format_var,
            values=["srt", "vtt", "json3", "srv1", "srv2", "srv3", "ttml"],
            height=36,
            corner_radius=14,
            fg_color="#f97316",
            button_color="#fb7185",
            button_hover_color="#e11d48",
        )
        format_menu.grid(row=7, column=0, sticky="ew", padx=16, pady=(0, 10))

        self.download_button = ctk.CTkButton(
            parent,
            text="⬇️ 下載選取字幕",
            command=self.download_selected_async,
            height=38,
            corner_radius=18,
            fg_color="#16a34a",
            hover_color="#15803d",
        )
        self.download_button.grid(row=8, column=0, sticky="ew", padx=16, pady=3)

        utility_row = ctk.CTkFrame(parent, fg_color="transparent")
        utility_row.grid(row=9, column=0, sticky="ew", padx=16, pady=(3, 8))
        utility_row.grid_columnconfigure(0, weight=1)
        utility_row.grid_columnconfigure(1, weight=1)

        recognition_button = ctk.CTkButton(
            utility_row,
            text="🎙️ 辨識工具",
            command=self.open_recognition_tool,
            height=34,
            corner_radius=16,
            fg_color="#8b5cf6",
            hover_color="#7c3aed",
        )
        recognition_button.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        clear_button = ctk.CTkButton(
            utility_row,
            text="🧹 清除",
            command=self.clear_all,
            height=34,
            corner_radius=16,
            fg_color="#e2e8f0",
            hover_color="#cbd5e1",
            text_color="#334155",
        )
        clear_button.grid(row=0, column=1, sticky="ew", padx=(4, 0))

        status_box = ctk.CTkFrame(parent, fg_color="#f8fafc", corner_radius=16)
        status_box.grid(row=11, column=0, sticky="nsew", padx=16, pady=(4, 16))
        status_box.grid_columnconfigure(0, weight=1)
        status_box.grid_rowconfigure(0, weight=1)

        status_label = ctk.CTkLabel(
            status_box,
            textvariable=self.status_var,
            text_color="#475569",
            font=ctk.CTkFont(size=13),
            justify="left",
            anchor="nw",
            wraplength=260,
        )
        status_label.grid(row=0, column=0, sticky="nsew", padx=12, pady=(10, 4))

    def create_right_panel(self, parent: ctk.CTkFrame) -> None:
        """
        建立右側影片資訊與字幕清單。

        Args:
            parent: 父容器。
        """
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(2, weight=1)

        video_card = ctk.CTkFrame(parent, fg_color="#f0f9ff", corner_radius=18)
        video_card.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 10))
        video_card.grid_columnconfigure(0, weight=1)

        video_label = ctk.CTkLabel(
            video_card,
            textvariable=self.video_info_var,
            text_color="#075985",
            font=ctk.CTkFont(size=13, weight="bold"),
            justify="left",
            anchor="w",
            wraplength=360,
        )
        video_label.grid(row=0, column=0, sticky="ew", padx=12, pady=10)

        tool_row = ctk.CTkFrame(parent, fg_color="transparent")
        tool_row.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 8))
        tool_row.grid_columnconfigure(0, weight=1)
        tool_row.grid_columnconfigure(1, weight=1)

        select_all_button = ctk.CTkButton(
            tool_row,
            text="✅ 全選",
            command=lambda: self.set_all_checked(True),
            height=32,
            corner_radius=16,
            fg_color="#e0f2fe",
            hover_color="#bae6fd",
            text_color="#0369a1",
        )
        select_all_button.grid(row=0, column=0, sticky="ew", padx=(0, 5))

        select_none_button = ctk.CTkButton(
            tool_row,
            text="↩️ 取消全選",
            command=lambda: self.set_all_checked(False),
            height=32,
            corner_radius=16,
            fg_color="#f1f5f9",
            hover_color="#e2e8f0",
            text_color="#475569",
        )
        select_none_button.grid(row=0, column=1, sticky="ew", padx=(5, 0))

        self.caption_scroll = ctk.CTkScrollableFrame(
            parent,
            fg_color="#ffffff",
            corner_radius=18,
            scrollbar_button_color="#fb7185",
            scrollbar_button_hover_color="#e11d48",
            height=300,
        )
        self.caption_scroll.grid(row=2, column=0, sticky="nsew", padx=16, pady=(0, 10))
        self.caption_scroll.grid_columnconfigure(0, weight=1)

        self.render_empty_caption_message("尚未讀取字幕。")

    def create_footer(self, parent: ctk.CTkFrame) -> None:
        """
        建立作者與 CC 授權資訊。

        Args:
            parent: 父容器。
        """
        footer = ctk.CTkFrame(
            parent,
            fg_color="#ffffff",
            corner_radius=12,
            border_width=1,
            border_color="#e2e8f0",
        )
        footer.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        footer.grid_columnconfigure(1, weight=1)

        made_by = ctk.CTkLabel(
            footer,
            text="Made by 阿剛老師",
            text_color="#be123c",
            font=ctk.CTkFont(size=13, weight="bold", underline=True),
            cursor="hand2",
        )
        made_by.grid(row=0, column=0, sticky="w", padx=(12, 10), pady=8)
        made_by.bind("<Button-1>", lambda _event: webbrowser.open_new(AUTHOR_URL))

        license_label = ctk.CTkLabel(
            footer,
            text=CC_LICENSE_TEXT,
            text_color="#64748b",
            font=ctk.CTkFont(size=12),
            anchor="w",
            justify="left",
            wraplength=680,
        )
        license_label.grid(row=0, column=1, sticky="ew", padx=(0, 12), pady=8)

    def render_empty_caption_message(self, message: str) -> None:
        """
        顯示字幕清單空白訊息。

        Args:
            message: 顯示文字。
        """
        self.clear_caption_list()

        label = ctk.CTkLabel(
            self.caption_scroll,
            text=message,
            text_color="#64748b",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        )
        label.grid(row=0, column=0, sticky="ew", padx=10, pady=10)

    def choose_output_dir(self) -> None:
        """選擇輸出資料夾。"""
        selected_dir = filedialog.askdirectory(initialdir=self.output_dir_var.get())
        if selected_dir:
            self.output_dir_var.set(selected_dir)

    def clear_caption_list(self) -> None:
        """清空字幕清單。"""
        for widget in self.caption_scroll.winfo_children():
            widget.destroy()

        self.caption_check_vars.clear()

    def render_caption_list(self, tracks: List[Dict[str, Any]]) -> None:
        """
        渲染字幕清單。

        Args:
            tracks: 字幕資料清單。
        """
        self.clear_caption_list()

        if not tracks:
            self.render_empty_caption_message("沒有找到可下載的字幕。")
            return

        for position, track in enumerate(tracks):
            var = tk.BooleanVar(value=position == 0)
            self.caption_check_vars[int(track["index"])] = var

            item_frame = ctk.CTkFrame(
                self.caption_scroll,
                fg_color="#f0f9ff",
                corner_radius=16,
                border_width=1,
                border_color="#bae6fd",
            )
            item_frame.grid(row=position, column=0, sticky="ew", padx=4, pady=5)
            item_frame.grid_columnconfigure(1, weight=1)

            checkbox = ctk.CTkCheckBox(
                item_frame,
                text="",
                variable=var,
                width=28,
                checkbox_width=20,
                checkbox_height=20,
                corner_radius=6,
                fg_color="#fb7185",
                hover_color="#e11d48",
            )
            checkbox.grid(row=0, column=0, rowspan=2, sticky="nw", padx=(10, 6), pady=12)

            title_text = f"{track['name']}｜{track['kind_label']}"
            format_text = ", ".join(track["formats"]) or "未知"
            code_text = f"語系：{track['language_code']}｜格式：{format_text}"

            title_label = ctk.CTkLabel(
                item_frame,
                text=title_text,
                text_color="#075985",
                font=ctk.CTkFont(size=13, weight="bold"),
                anchor="w",
                justify="left",
                wraplength=330,
            )
            title_label.grid(row=0, column=1, sticky="ew", padx=(0, 10), pady=(10, 0))

            code_label = ctk.CTkLabel(
                item_frame,
                text=code_text,
                text_color="#64748b",
                font=ctk.CTkFont(size=12),
                anchor="w",
                justify="left",
                wraplength=330,
            )
            code_label.grid(row=1, column=1, sticky="ew", padx=(0, 10), pady=(2, 10))

    def set_all_checked(self, checked: bool) -> None:
        """
        全選或取消全選。

        Args:
            checked: 是否勾選。
        """
        for var in self.caption_check_vars.values():
            var.set(checked)

    def load_captions_async(self) -> None:
        """背景讀取字幕。"""
        youtube_url = self.url_var.get().strip()

        if not youtube_url:
            messagebox.showwarning(APP_NAME, "請先貼上 YouTube 影片連結。")
            return

        self.load_button.configure(state="disabled")
        self.download_button.configure(state="disabled")
        self.render_empty_caption_message("正在讀取字幕清單……")
        self.video_info_var.set("正在讀取影片資訊……")
        self.status_var.set("正在讀取字幕清單，請稍候……")

        thread = threading.Thread(target=self.load_captions_worker, args=(youtube_url,), daemon=True)
        thread.start()

    def load_captions_worker(self, youtube_url: str) -> None:
        """
        背景工作：讀取字幕。

        Args:
            youtube_url: YouTube 影片連結。
        """
        try:
            info = self.service.get_video_info(youtube_url)
            payload = {"info": info, "tracks": self.service.last_caption_tracks}
            self.message_queue.put(("load_success", json.dumps(payload, ensure_ascii=False, default=str)))
        except Exception as exc:
            self.message_queue.put(("load_error", str(exc)))

    def download_selected_async(self) -> None:
        """背景下載選取字幕。"""
        youtube_url = self.url_var.get().strip()
        output_dir = self.output_dir_var.get().strip()
        target_format = self.format_var.get().strip()

        selected_indexes = [index for index, var in self.caption_check_vars.items() if var.get()]

        if not youtube_url:
            messagebox.showwarning(APP_NAME, "請先貼上 YouTube 影片連結。")
            return

        if not selected_indexes:
            messagebox.showwarning(APP_NAME, "請至少選擇一個字幕。")
            return

        self.download_button.configure(state="disabled")
        self.status_var.set("正在下載字幕，請稍候……")

        thread = threading.Thread(
            target=self.download_selected_worker,
            args=(youtube_url, selected_indexes, target_format, output_dir),
            daemon=True,
        )
        thread.start()

    def download_selected_worker(
        self,
        youtube_url: str,
        selected_indexes: List[int],
        target_format: str,
        output_dir: str,
    ) -> None:
        """
        背景工作：下載字幕。

        Args:
            youtube_url: YouTube 影片連結。
            selected_indexes: 選取字幕 index。
            target_format: 目標格式。
            output_dir: 輸出資料夾。
        """
        try:
            downloaded_files: List[str] = []

            for index in selected_indexes:
                file_path = self.service.download_caption(
                    youtube_url=youtube_url,
                    track_index=index,
                    target_format=target_format,
                    output_dir=output_dir,
                )
                downloaded_files.append(file_path)
                time.sleep(0.2)

            self.message_queue.put(("download_success", json.dumps(downloaded_files, ensure_ascii=False)))
        except Exception as exc:
            self.message_queue.put(("download_error", str(exc)))

    def open_recognition_tool(self, youtube_url: str = "", video_title: str = "") -> None:
        """開啟 Whisper 辨識工具；無 CC 的 YouTube 會帶入網址。"""
        if self.recognition_window is not None and self.recognition_window.winfo_exists():
            self.recognition_window.focus()
            if youtube_url:
                self.recognition_window.youtube_url = youtube_url
                self.recognition_window.video_title = video_title
                self.recognition_window.file_path = None
                self.recognition_window.source_title_var.set(video_title or youtube_url)
                self.recognition_window.file_var.set("來源：YouTube 影片")
                self.recognition_window.status_var.set("YouTube 無 CC 字幕，按「開始辨識」會先下載音訊再產生 SRT。")
            return

        self.recognition_window = RecognitionWindow(
            self.root,
            youtube_url=youtube_url,
            video_title=video_title,
            service=self.service,
        )
        self.recognition_window.focus()

    def clear_all(self) -> None:
        """清除畫面。"""
        self.url_var.set("")
        self.video_info_var.set("尚未讀取影片。")
        self.render_empty_caption_message("尚未讀取字幕。")
        self.status_var.set("請貼上 YouTube 連結後按下「讀取字幕」。")

    def poll_message_queue(self) -> None:
        """輪詢背景工作訊息。"""
        try:
            while True:
                event_type, payload = self.message_queue.get_nowait()

                if event_type == "load_success":
                    self.handle_load_success(payload)
                elif event_type == "load_error":
                    self.handle_load_error(payload)
                elif event_type == "download_success":
                    self.handle_download_success(payload)
                elif event_type == "download_error":
                    self.handle_download_error(payload)
        except queue.Empty:
            pass

        self.root.after(100, self.poll_message_queue)

    def handle_load_success(self, payload: str) -> None:
        """
        處理字幕讀取成功。

        Args:
            payload: JSON 字串。
        """
        data = json.loads(payload)
        info = data["info"]
        tracks = data["tracks"]

        title = info.get("title") or "YouTube 影片"
        uploader = info.get("uploader") or info.get("channel") or "未知"
        video_id = info.get("id") or "未知"

        self.video_info_var.set(f"影片：{title}\n頻道：{uploader}｜ID：{video_id}")
        self.load_button.configure(state="normal")

        if tracks:
            self.render_caption_list(tracks)
            self.status_var.set(f"找到 {len(tracks)} 個字幕語系，已進入字幕下載介面。")
            self.download_button.configure(state="normal")
            return

        self.render_empty_caption_message("沒有找到可下載的 CC 或自動字幕，已切換到辨識生成工具。")
        self.status_var.set("這部影片沒有 CC 字幕，已開啟辨識工具，可下載音訊後產生 SRT。")
        self.download_button.configure(state="disabled")
        self.open_recognition_tool(youtube_url=self.url_var.get().strip(), video_title=str(title))

    def handle_load_error(self, message: str) -> None:
        """
        處理字幕讀取失敗。

        Args:
            message: 錯誤訊息。
        """
        self.video_info_var.set("讀取失敗。")
        self.render_empty_caption_message("讀取失敗。")
        self.status_var.set(f"讀取失敗：{message}")
        self.load_button.configure(state="normal")
        self.download_button.configure(state="normal")
        messagebox.showerror(APP_NAME, f"讀取失敗：\n{message}")

    def handle_download_success(self, payload: str) -> None:
        """
        處理下載成功。

        Args:
            payload: JSON 字串。
        """
        downloaded_files = json.loads(payload)
        file_list = "\n".join(downloaded_files)

        self.status_var.set(f"下載完成：\n{file_list}")
        self.download_button.configure(state="normal")

        messagebox.showinfo(APP_NAME, f"字幕下載完成！\n\n{file_list}")

    def handle_download_error(self, message: str) -> None:
        """
        處理下載失敗。

        Args:
            message: 錯誤訊息。
        """
        self.status_var.set(f"下載失敗：{message}")
        self.download_button.configure(state="normal")

        messagebox.showerror(APP_NAME, f"下載失敗：\n{message}")


def main() -> None:
    """程式進入點。"""
    Path(DEFAULT_DOWNLOAD_DIR).mkdir(parents=True, exist_ok=True)

    root = ctk.CTk()
    set_window_icon(root)

    SubtitleDownloaderGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
