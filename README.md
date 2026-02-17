# Uma Voice Dataset Creator

A high-performance tool for extracting voice data, text, and metadata from *Umamusume: Pretty Derby*. 

This tool also includes a stress mode (because it caught instability on my 13900k that OCCT did not catch).

## ⚠️ Critical Requirement: libpyvgmstream

**This tool requires a compiled `libpyvgmstream` binary to function.**

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

### Output

* **Audio:** Saved as `.wav` files in the `output/` directory, organized by Character ID or Story ID.
* **Data:** 
    * `global_system_voices.csv`: Transcript and paths for system voices.
    * `global_story_deep_scan.csv`: Detailed dataset including Speaker, Text, Ruby, and Audio Paths.

## Troubleshooting

* **High RAM Usage:** The tool uses `multiprocessing` and creates one process per logical core. If you have many cores (e.g., 32+), it may consume significant RAM. Reduce the worker count in `main.py` if necessary.