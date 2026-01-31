<div align="center">

# 🎬 Auto Video Generator

**Transform scripts into stunning short-form videos with AI-generated visuals, voiceover, and captions. Fully automated.**

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-22C55E?style=for-the-badge)](LICENSE)
[![FFmpeg](https://img.shields.io/badge/FFmpeg-Required-007808?style=for-the-badge&logo=ffmpeg&logoColor=white)](https://ffmpeg.org)

<br>

### 🎥 Example Output

https://github.com/saadbenchakroun/auto-video-generator/raw/main/output/video_1.mp4

<img src="output/preview.gif" width="480" />

*Above: A video generated entirely from a script using this pipeline*

</div>

---

## Who this is For
Ideal for creators, marketers, or developers who want to automate short-form video production.

## ✨ Features

| Feature | Description |
|---------|-------------|
| 📊 **Google Sheets Integration** | Fetch scripts and track processing status automatically |
| 🎙️ **AI Voiceover** | Generate natural speech using Kokoro TTS |
| 📝 **Auto Subtitles** | Create word-level SRT files with Whisper |
| 🎨 **AI Image Generation** | Create visuals with Stable Diffusion XL via Cloudflare |
| 🖼️ **Dynamic Animations** | Zoom, fade, blur, and glitch effects |
| 🎬 **Video Assembly** | Stitch clips, add audio, burn captions |
| 💻 **Modern UI** | Dark-themed CustomTkinter interface |

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.10+**
- **FFmpeg** installed and in PATH
- **Google Cloud** service account credentials
- **API Keys** for Cerebras and Cloudflare

### Installation

```bash
# Clone the repository
git clone https://github.com/saadkhalid-git/auto-video-generator.git
cd auto-video-generator

# Install dependencies
pip install -r requirements.txt
```

### Configuration

1. Copy the example config files:
   ```bash
   cp config/config.example.json config.json
   cp config/credentials.example.json credentials.json
   ```

2. Edit `config.json` with your API keys:
   ```json
   {
       "api_keys": {
           "cerebras": "your-cerebras-key",
           "cloudflare_account_id": "your-account-id",
           "cloudflare_api_token": "your-api-token"
       }
   }
   ```

3. Replace `credentials.json` with your Google Cloud service account JSON

### Run

```bash
python run.py
```

---

## 📁 Project Structure

```
auto-video-generator/
├── app/                        # Application modules
│   ├── ui.py                   # GUI application
│   ├── main.py                 # Pipeline orchestrator
│   ├── ai_manager.py           # Cerebras AI prompts
│   ├── video_assembler.py      # FFmpeg stitching
│   ├── image_generator.py      # Cloudflare SDXL
│   ├── voice_generator.py      # Kokoro TTS
│   ├── srt_generator.py        # Whisper subtitles
│   ├── short_clips_maker.py    # OpenCV animations
│   ├── caption_burner.py       # Caption overlay
│   ├── sheets_extractor.py     # Google Sheets API
│   └── config_manager.py       # Config accessor
│
├── assets/temp/                # Working directory
├── output/                     # Completed videos
├── config/                     # Example configurations
│
├── run.py                      # Entry point
├── config.json                 # Your configuration
├── credentials.json            # Google credentials
├── requirements.txt            # Dependencies
└── README.md
```

---

## 📋 Google Sheet Format

Your Google Sheet should have these columns:

| id | script | created |
|----|--------|---------|
| 1 | Your script text here... | *(leave empty)* |
| 2 | Another script... | *(leave empty)* |

The app will:
- ✅ Find rows where `created` is empty
- 🔄 Update status to `Processing` when starting
- ✅ Update status to `Done` when complete

---

## 🔧 Configuration Options

<details>
<summary><b>Video Settings</b></summary>

```json
"video_settings": {
    "width": 1280,
    "height": 720,
    "fps": 30,
    "clip_duration": 4.0
}
```
</details>

<details>
<summary><b>Caption Styling</b></summary>

```json
"captions": {
    "font_size": 52,
    "position": "bottom",
    "font_color": [255, 255, 255],
    "outline_color": [0, 0, 0]
}
```
</details>

<details>
<summary><b>AI Settings</b></summary>

```json
"ai_settings": {
    "model": "llama3.1-70b",
    "max_retries": 3
}
```
</details>

---

## 🔄 Pipeline Flow

```
┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
│  Google Sheets  │──►│   Kokoro TTS    │──►│     Whisper     │
│  Fetch Scripts  │   │  Generate Audio │   │   Create SRT    │
└─────────────────┘   └─────────────────┘   └─────────────────┘
                                                    │
┌─────────────────┐   ┌─────────────────┐           ▼
│  Google Sheets  │◄──│     FFmpeg      │◄──┌─────────────────┐
│  Update Status  │   │  Final Assembly │   │   Cerebras AI   │
└─────────────────┘   └─────────────────┘   │ Generate Prompts│
                             ▲              └─────────────────┘
                             │                      │
                      ┌─────────────────┐           ▼
                      │     OpenCV      │   ┌─────────────────┐
                      │  Animate Clips  │◄──│  Cloudflare AI  │
                      └─────────────────┘   │ Generate Images │
                                            └─────────────────┘
```

---

## 📦 Dependencies

| Package | Purpose |
|---------|---------|
| `customtkinter` | Modern UI framework |
| `gspread` + `google-auth` | Google Sheets integration |
| `kokoro` | Text-to-speech |
| `faster-whisper` | Speech recognition |
| `cerebras-cloud-sdk` | AI prompts |
| `opencv-python` | Video processing |
| `ffmpeg-python` | Video assembly |
| `Pillow` | Image processing |

---

## 🛠️ Models Required

| Model | Purpose | Link |
|-------|---------|------|
| Kokoro TTS | Voice generation | [GitHub](https://github.com/thewh1teagle/kokoro-onnx) |
| Faster-Whisper | Speech recognition | [HuggingFace](https://huggingface.co/guillaumekln/faster-whisper-base.en) |

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

<div align="center">

### 🙏 Acknowledgments

Built with amazing open-source tools:

[Kokoro TTS](https://github.com/thewh1teagle/kokoro-onnx) • 
[Faster-Whisper](https://github.com/guillaumekln/faster-whisper) • 
[Cerebras](https://cerebras.ai/) • 
[Cloudflare Workers AI](https://developers.cloudflare.com/workers-ai/)

</div>
