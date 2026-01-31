# Auto Video Creator - Complete Functionality Documentation

This document provides a comprehensive explanation of every component in the Auto Video Creator application.

---

## Table of Contents

1. [Overview](#overview)
2. [Application Architecture](#application-architecture)
3. [Entry Point: ui.py](#entry-point-uipy)
4. [Core Pipeline: main.py](#core-pipeline-mainpy)
5. [Configuration System](#configuration-system)
6. [Module Breakdown](#module-breakdown)
   - [SheetsExtractor](#sheetsextractor)
   - [VoiceGenerator](#voicegenerator)
   - [SRTGenerator](#srtgenerator)
   - [AIManager](#aimanager)
   - [ImageGenerator](#imagegenerator)
   - [DynamicVideoGenerator](#dynamicvideogenerator)
   - [VideoAssembler](#videoassembler)
   - [CaptionBurner](#captionburner)
7. [Data Flow](#data-flow)
8. [Error Handling](#error-handling)
9. [External Dependencies](#external-dependencies)

---

## Overview

Auto Video Creator is an automated video generation pipeline that:
1. Fetches scripts from a Google Sheet
2. Generates voiceover audio using Kokoro TTS
3. Creates SRT subtitles using Whisper
4. Generates image prompts using Cerebras AI
5. Creates images using Cloudflare's Stable Diffusion API
6. Animates images with effects (zoom, fade, glitch)
7. Stitches clips, adds audio, and burns captions
8. Updates the Google Sheet with completion status

---

## Application Architecture

```
┌─────────────────┐
│     ui.py       │ ← User interface (CustomTkinter)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    main.py      │ ← VideoPipeline orchestrator
│  (VideoPipeline)│
└────────┬────────┘
         │
    ┌────┴────────────────────────────────────┐
    │                                         │
    ▼                                         ▼
┌─────────────────┐                  ┌─────────────────┐
│ sheets_extractor│                  │  config_manager │
│   (Google API)  │                  │  (config.json)  │
└─────────────────┘                  └─────────────────┘
    │
    │  For each script:
    │
    ├──► voice_generator.py (Kokoro TTS → .wav)
    │
    ├──► srt_generator.py (Whisper → .srt)
    │
    ├──► ai_manager.py (Cerebras → prompts)
    │
    ├──► image_generator.py (Cloudflare SDXL → .png)
    │
    ├──► short_clips_maker.py (OpenCV → animated .mp4 clips)
    │
    ├──► video_assembler.py (FFmpeg → stitched + audio .mp4)
    │
    └──► caption_burner.py (FFmpeg + Pillow → final .mp4)
```

---

## Entry Point: ui.py

### Purpose
Provides a graphical user interface built with CustomTkinter.

### Components

| Component | Description |
|-----------|-------------|
| `App` class | Main application window |
| `TextHandler` | Logging handler that redirects logs to the console textbox |
| `SettingsWindow` | Popup window to edit AI model and video resolution |

### Key Features
- **Start Button**: Triggers the pipeline in a background thread
- **Max Videos Input**: Allows user to specify how many scripts to process
- **Console Output**: Displays real-time logs from the pipeline
- **Settings**: Edit AI model, video width/height (saved to config.json)

### Thread Safety
The pipeline runs in a separate thread (`_run_pipeline_thread`) to keep the UI responsive. Status updates use `self.after()` to safely update the UI from the worker thread.

---

## Core Pipeline: main.py

### Purpose
Orchestrates the 7-phase video generation process.

### Class: `VideoPipeline`

#### Initialization
- Creates temp and output directories
- Connects to Google Sheets
- Initializes AIManager

#### `run(max_videos: int)` Method

Executes the pipeline in 7 phases:

| Phase | Method | Description |
|-------|--------|-------------|
| 1 | `_fetch_pending_scripts()` | Get scripts from Google Sheets |
| 2 | `_generate_audio_bulk()` | Generate voiceover for all scripts |
| 3 | `_generate_srt_bulk()` | Create subtitles for all audio files |
| 4 | `_generate_prompts_bulk()` | Generate image prompts via Cerebras |
| 5 | `_generate_images_bulk()` | Create images via Cloudflare |
| 6 | `_assemble_videos_bulk()` | Create clips, stitch, add audio, burn captions |
| 7 | `_update_sheets()` | Update Google Sheet status |

#### Data Structure
Each script item is tracked as a dictionary:
```python
{
    "row_number": 5,
    "id": "abc123",
    "script_text": "Your script here...",
    "status": "Pending",  # → Processing → Done/Failed
    "files": {"audio": "...", "srt": "..."},
    "prompts": ["prompt1", "prompt2"],
    "image_paths": ["img1.png", "img2.png"],
    "audio_duration": 15.5,
    "num_images": 4
}
```

---

## Configuration System

### Files

| File | Purpose |
|------|---------|
| `config.json` | Stores all configurable settings |
| `config_manager.py` | Singleton class to access settings |

### config.json Structure

```json
{
    "api_keys": {
        "cerebras": "...",
        "cloudflare_account_id": "...",
        "cloudflare_api_token": "..."
    },
    "google_sheets": {
        "credentials_file": "credentials.json",
        "sheet_id": "...",
        "worksheet_name": "newScripts",
        "columns": {"id": "id", "script": "script", "status": "created"},
        "search_keyword": "",
        "status_values": {...}
    },
    "paths": {...},
    "video_settings": {...},
    "ai_settings": {...},
    "captions": {...}
}
```

### ConfigManager Properties

| Property | Returns |
|----------|---------|
| `api_keys` | API credentials |
| `sheets_config` | Google Sheets settings |
| `sheet_columns` | Column name mappings |
| `sheet_settings` | Search keyword, status values |
| `paths` | File paths (models, fonts, dirs) |
| `video_settings` | Width, height, fps, clip_duration |
| `ai_settings` | Model, prompts, retries |
| `caption_settings` | Font, colors, position |

---

## Module Breakdown

### SheetsExtractor

**File**: `sheets_extractor.py`

**Purpose**: Interface with Google Sheets API

**Key Methods**:

| Method | Description |
|--------|-------------|
| `_connect()` | Authenticate and connect to worksheet |
| `find_row_and_get_data()` | Find first row matching keyword |
| `find_multiple_rows_and_get_data()` | Find multiple rows (uses `get_all_values()` to handle empty cells) |
| `update_cell()` | Update a single cell |
| `update_multiple_cells()` | Batch update cells |
| `update_row()` | Update multiple columns in one row |

**Special Handling**: Uses `get_all_values()` instead of `col_values()` to correctly find rows with empty status cells.

---

### VoiceGenerator

**File**: `voice_generator.py`

**Purpose**: Text-to-speech using Kokoro TTS

**Key Methods**:

| Method | Description |
|--------|-------------|
| `load_model()` | Load Kokoro pipeline |
| `unload_model()` | Free memory |
| `generate()` | Single text → WAV file |
| `generate_batch()` | Multiple texts → multiple WAV files |

**Returns**: `GenerationResult` dataclass with `success`, `output_path`, `duration`, `error`

---

### SRTGenerator

**File**: `srt_generator.py`

**Purpose**: Generate SRT subtitles from audio using Whisper

**Key Features**:
- Multiple grouping strategies: Fixed word count, time-based, character count, smart phrase
- Configurable via `SRTConfig` dataclass
- Parallel transcription with `ThreadPoolExecutor`

**Key Methods**:

| Method | Description |
|--------|-------------|
| `load_model()` | Load Whisper model |
| `transcribe_audio()` | Get word-level timestamps |
| `group_words()` | Group words into subtitle entries |
| `generate_srt()` | Single audio → SRT |
| `generate_multiple_srts()` | Batch processing |

---

### AIManager

**File**: `ai_manager.py`

**Purpose**: Generate image prompts using Cerebras AI API

**Key Methods**:

| Method | Description |
|--------|-------------|
| `generate_prompts()` | Script segment → SDXL prompt |
| `_get_fallback_prompt()` | Random fallback if API fails |

**Features**:
- Uses JSON schema for structured output
- Retry logic (configurable max_retries)
- Fallback prompts from config

---

### ImageGenerator

**File**: `image_generator.py`

**Purpose**: Generate images using Cloudflare's Stable Diffusion XL API

**Key Methods**:

| Method | Description |
|--------|-------------|
| `generate_image()` | Single prompt → PNG |
| `generate_multiple()` | Batch generation with retries |
| `_create_fallback_image()` | Creates black image on failure |

**Features**:
- Rate limiting (requests/minute)
- Retry logic (max 3 attempts)
- Parallel generation with `ThreadPoolExecutor`
- Fallback to black images

---

### DynamicVideoGenerator

**File**: `short_clips_maker.py`

**Purpose**: Create animated video clips from static images using OpenCV

**Available Effects**:

| Effect | Modes | Description |
|--------|-------|-------------|
| `zoom` | in, out | Ken Burns-style zoom |
| `fade` | in, out | Fade from/to black |
| `blur` | focus_in, focus_out | Blur transition |
| `glitch` | - | RGB split + scanline effect |

**Easing Functions**: linear, ease_in, ease_out, cubic_in, cubic_out

**Key Method**:
```python
create_video(image_path, output_path, effects_list, width, height, fps, duration)
```

---

### VideoAssembler

**File**: `video_assembler.py`

**Purpose**: Stitch videos and add audio using FFmpeg

**Key Methods**:

| Method | Description |
|--------|-------------|
| `stitch_videos()` | Concatenate multiple clips |
| `add_voice()` | Add audio track |
| `merge_audio_tracks()` | Mix multiple audio tracks |

**Features**:
- Re-encodes to libx264 for compatibility
- Duration modes: match video or match audio length
- Volume control, fade in/out

---

### CaptionBurner

**File**: `caption_burner.py`

**Purpose**: Burn SRT subtitles onto video with custom styling

**Styling Options** (via `CaptionStyle`):
- Font (path, size, color)
- Outline (color, width)
- Background (color, padding)
- Position (top, middle, bottom)
- Shadow (offset, color)
- Text wrapping (max_width)

**Process**:
1. Parse SRT file
2. Generate PNG image for each subtitle
3. Build FFmpeg filter_complex
4. Overlay images at correct timestamps

---

## Data Flow

```
Google Sheet (script text)
       │
       ▼
Voice Generator (Kokoro TTS)
       │
       ├──► temp_assets/voice_{id}.wav
       │
       ▼
SRT Generator (Whisper)
       │
       ├──► temp_assets/subs_{id}.srt
       │
       ▼
AI Manager (Cerebras)
       │
       ├──► [prompts list]
       │
       ▼
Image Generator (Cloudflare SDXL)
       │
       ├──► temp_assets/img_{id}_{n}.png
       │
       ▼
Short Clips Maker (OpenCV)
       │
       ├──► temp_assets/clip_{id}_{n}.mp4
       │
       ▼
Video Assembler (FFmpeg)
       │
       ├──► temp_assets/stitched_{id}.mp4
       ├──► temp_assets/pre_caption_{id}.mp4
       │
       ▼
Caption Burner (FFmpeg + Pillow)
       │
       └──► final_output/video_{id}.mp4
```

---

## Error Handling

### Status Values

| Status | Meaning |
|--------|---------|
| Processing | Script is being processed |
| Done | Successfully completed |
| Failed Audio | Voice generation failed |
| Failed SRT | Subtitle generation failed |
| Failed Images | Image generation failed |
| Failed Assembly | Video assembly failed |

### Fallback Mechanisms

1. **AI Prompts**: Falls back to generic prompts from config
2. **Images**: Creates black images if API fails
3. **Retries**: Image generation retries 3 times
4. **Logging**: All errors logged to `pipeline.log`

---

## External Dependencies

### Python Packages

| Package | Purpose |
|---------|---------|
| customtkinter | Modern UI |
| gspread | Google Sheets API |
| google-auth | Google authentication |
| torch | PyTorch (for Kokoro) |
| soundfile | Audio file I/O |
| kokoro | Text-to-speech |
| faster-whisper | Speech-to-text |
| cerebras-cloud-sdk | AI prompt generation |
| requests | HTTP requests |
| Pillow | Image processing |
| opencv-python | Video processing |
| ffmpeg-python | Video encoding |
| mutagen | Audio metadata |

### External Software

| Software | Purpose |
|----------|---------|
| FFmpeg | Video encoding/decoding |

### API Services

| Service | Purpose |
|---------|---------|
| Google Sheets API | Script storage |
| Cerebras API | AI prompt generation |
| Cloudflare Workers AI | Image generation |

---

## File Structure

```
auto/
├── ui.py                    # GUI entry point
├── main.py                  # Pipeline orchestrator
├── config.json              # Configuration
├── config_manager.py        # Config accessor
├── credentials.json         # Google API credentials
├── sheets_extractor.py      # Google Sheets interface
├── voice_generator.py       # Kokoro TTS
├── srt_generator.py         # Whisper subtitles
├── ai_manager.py            # Cerebras prompts
├── image_generator.py       # Cloudflare images
├── short_clips_maker.py     # OpenCV animations
├── video_assembler.py       # FFmpeg stitching
├── caption_burner.py        # Caption overlay
├── requirements.txt         # Dependencies
├── temp_assets/             # Temporary files
└── final_output/            # Completed videos
```
