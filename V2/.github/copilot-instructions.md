# Maschsee Player - AI Coding Agent Instructions

## Project Overview
This is a DJ File Manager application built with PyQt6 for organizing, playing, and tagging audio files. The project is in active evolution with multiple app versions (app.py through app206_reorder.py) representing iterative development stages.

**Core Purpose:** Create a table-driven playlist manager that supports drag-to-reorder songs, metadata extraction (BPM, key), and batch filename tagging operations.

## Architecture & Data Flows

### Core Components
1. **Audio Playback** (`AudioPlayer` class in recent versions)
   - Thread-based player using `sounddevice` + `pydub`
   - Handles multi-format loading (.mp3, .wav, .m4a, .ogg, .flac)
   - Features: pause, resume, stop, position tracking
   - Critical: Resamples all audio to 44100Hz for consistency; auto-normalizes quiet files

2. **Data Model** (`SongTableModel` extending `QAbstractTableModel`)
   - Pandas DataFrame backing store with columns: index, type, songfile, ext, Filename, alterFilenameTo
   - Supports drag-and-drop row reordering (ItemIsDragEnabled flag required)
   - Displays in QTableView with horizontal stretch layout

3. **Filename Parsing Engine**
   - Pattern: `[001][salsa__][Artist Name][Song Title].mp3`
   - Extracts: index tags `[001]`, type tags `[salsa__]`, interpret, title from filename
   - Stored separately for independent manipulation before batch rename

### Data Flow Example
User drags song row → triggers model reorder → affects playback sequence (next song = row below current) → batch index button auto-updates `[001]` tags based on new row position

## Key Patterns & Conventions

### 1. Filename Tag System
- **Index Tags**: `[001]` format, left-padded with zeros to match max index count
- **Type Tags**: `[salsa__]` format (exact length enforced, right-padded with `_`)
- **Storage Strategy**: `alterFilenameTo` column holds proposed new filename; user confirms before applying
- **Example Evolution**: `vivir la.mp3` → `[001][salsa__]vivir la.mp3` → `[001][salsa__][vivir la].mp3`

### 2. Cross-Version Iteration Pattern
Files progress: `app.py` (foundational) → `app201index.py` (indexing) → `app202dragdrop.py` (D&D) → `app203style.py` (UI) → `app204_m4a.py` (m4a support) → `app205_colour.py` (theming) → `app206_reorder.py` (current stable)

**Important:** Do NOT delete old versions; they're design documentation. Always extend from the latest stable version (app206_reorder.py).

### 3. Audio Processing Workflow
```
Load file → Detect format → Resample to 44100Hz if needed → Normalize volume 
→ Reshape to mono/stereo → Stream via sounddevice with callback
```
Error handling: JSON decode failures in pydub → fallback to FFmpeg subprocess

### 4. UI Threading
- `AudioPlayer` is a daemon Thread; always check `is_playing` property before state transitions
- Playback callbacks use `sounddevice.sleep()` to prevent blocking; pause state managed via Event flags

## Developer Workflows

### Running the Application
```bash
venv\Scripts\activate
python app206_reorder.py
```

### Audio Format Support
- Primary: .mp3, .wav, .m4a
- Extended: .ogg, .flac (tested in recent versions)
- Fallback: FFmpeg required for m4a/codec issues

### Adding New Features
1. **New UI Controls:** Add to `init_ui()`, connect to model/player methods
2. **Batch Operations:** Implement in main loop; show `QProgressDialog` for user feedback
3. **Audio Analysis:** Use `librosa` (BPM/key detection framework, partially implemented)

### Testing Audio Compatibility
Run `check.py` or `check2.py` to validate codec support and library imports

## Critical Integration Points

### PyQt6 Drag-Drop System
- Model must implement `supportedDropActions()` returning `Qt.DropAction.MoveAction`
- Items need `Qt.ItemFlag.ItemIsDragEnabled | Qt.ItemFlag.ItemIsDropEnabled`
- Table must set `setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)`

### sounddevice + pydub Interaction
- pydub loads and converts format/samplerate
- sounddevice handles actual playback streaming
- No direct interaction; data flows through numpy array (float32 normalized)

### Filename Rename Execution
- `alterFilenameTo` is **preview only** until user confirms
- Actual rename uses `os.rename()` with full path validation
- Must handle: special characters, duplicate filenames, filesystem limits

## Code Examples

### Add a new audio format
In `app206_reorder.py` constant section:
```python
SUPPORTED_EXTENSIONS = ('.mp3', '.wav', '.m4a', '.ogg', '.flac', '.wma')
```
Then test with real .wma file; pydub should handle via FFmpeg.

### Query current playing song position
```python
if self.audio_player and self.audio_player.is_playing:
    position_seconds = self.audio_player.position / self.audio_player.fs
```

### Batch rename with progress feedback
Use `QProgressDialog` in loop; emit `setValue()` after each file rename. Catch `OSError` for filesystem errors.

## Avoiding Common Pitfalls

- **Do NOT** hardcode sample rates; always check source and resample
- **Do NOT** ignore Thread state; check `is_playing` before stopping/pausing
- **Do NOT** assume all audio is stereo; reshape logic handles mono/stereo
- **Do NOT** commit old app versions as "complete"; they're learning stages
- **Do NOT** use wildcard imports from sounddevice; be explicit with `sd.OutputStream`

## Performance Notes
- Large playlists (500+ songs): pandas operations are fast; bottleneck is audio analysis (BPM detection)
- Normalization happens on-load; recalculate only if necessary (expensive)
- Drag-reorder: keep model copy synchronized with UI; use `setData()` to trigger updates

## External Dependencies
- PyQt6: UI framework
- pydub: Audio codec handling
- sounddevice: Low-latency playback
- pandas: Data manipulation
- numpy: Audio array processing
- librosa: BPM/key analysis (incomplete)
- aubio: Alternative BPM detection (in app.py)
