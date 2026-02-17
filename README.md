# Uma Voice Dataset Creator

A high-performance tool for extracting voice data, text, and metadata from *Umamusume: Pretty Derby*. Only supports JP for now.

This tool also includes a stress mode (because it caught instability on my 13900k that OCCT did not catch).

## ⚠️ Critical Requirement: libpyvgmstream

**This tool requires a compiled `libpyvgmstream` binary to function.**

Credit to hugeBlack for their [pyvgmstream](https://github.com/hugeBlack/pyvgmstream) project. The binary provided in this repo is a compilation of pyvgmstream.

* **Windows:** You must place `libpyvgmstream.pyd` in the root directory of this project.
* **Linux:** You must place `libpyvgmstream.so` in the root directory.

> **Note:** A pre-compiled `.pyd` is provided, but it is not guaranteed to work on all systems. If it fails, you may need to build `vgmstream` with Python bindings manually.

## Setup

0. Set up and activate venv (optional but recommended)

1.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```

2.  Ensure `libpyvgmstream.pyd` (or `.so`) is in the same folder as `main.py`.

3.  Edit `config/keys.json` with your game paths.

## Usage

Run the script:
```bash
python main.py
```

You will be presented with an interactive menu:

1. **Stress Test:** (If enabled in config) Runs the infinite stability loop.
2. **System Text Scan:** Extracts text/voice pairs from the `system_text` table (I/O heavy).
3. **Full Story Scan:** Extracts all text/voice pairs from all story timelines (CPU & I/O heavy).
4. **Test Mode:** If selected, limits the scan to 1,000 random rows for quick verification.

## Output

### 1. Audio
Extracted into the `output/` directory, separated by category.

```text
output/
├── system/
│   ├── 1001/                   # Character ID
│   │   ├── sys_1001_home_001.wav
│   │   ├── sys_1001_title_002.wav
│   │   └── ...
│   └── ...
│
├── story/
│   ├── 501001501/              # Story ID
│   │   ├── 990001_001.wav      # {VoiceSheetId}_{CueId}.wav
│   │   ├── 990001_002.wav
│   │   └── ...
│   └── ...
│
├── global_story_deep_scan.csv  # Metadata for Story Mode
└── global_system_voices.csv    # Metadata for System Mode

```

### 2. `global_story_deep_scan.csv` (Story Mode)
Contains the full dialogue timeline, including metadata and pointers to extracted audio.

| Column | Description |
| :--- | :--- |
| **StoryId** | The unique identifier for the story chapter. |
| **BlockIndex** | The sequential index of the text block within the conversation. |
| **CharaId** | The internal ID of the speaker. |
| **SpeakerName** | The display name of the character speaking. |
| **Text** | The actual dialogue text. |
| **RubyText** | Furigana (reading aids) applied to the text. Formatted as `CharXPosition:Reading` (e.g., `4.0:たぐい`). |
| **VoiceSheetId** | The ID of the audio bank (`.acb` file) containing this voice line. |
| **CueId** | The specific track index within the audio bank. |
| **AudioFilePath** | Relative path to the extracted `.wav` file. |
| **Transcript** | Reserved for AI transcription (empty by default). |

### 3. `global_system_voices.csv` (System Mode)
Contains "System" voices such as Title Calls, Gacha animations, and Home Screen lines.

| Column | Description |
| :--- | :--- |
| **Text** | The transcript of the line. |
| **CharaId** | The internal ID of the character. |
| **AudioFilePath** | Relative path to the extracted `.wav` file. |

## Troubleshooting

* **High RAM Usage:** The tool uses `multiprocessing` and creates one process per logical core. If you have many cores (e.g., 32+), it may consume significant RAM. Reduce the worker count in `main.py` if necessary.


