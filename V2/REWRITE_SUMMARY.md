# Playback Logic Rewrite - Summary

## Problem
The previous implementation had significant playback issues:
- Multiple player threads would hang with frozen callback counts
- Old threads wouldn't exit cleanly even after `stop_event` was set
- Race conditions between playback state transitions
- Complex event management (stop_event, pause_event) caused confusion
- Global stream IDs and active player tracking added unnecessary complexity

## Solution
Complete architectural simplification of the AudioPlayer and playback control system.

### AudioPlayer Changes

**Old Approach (Per-Song Thread):**
- Created new Thread for each song
- Managed playback state with Event objects (stop_event, pause_event)
- Callback checked global _active_player_id to decide whether to output

**New Approach (Single-Load Thread Per Song):**
- Simplified AudioPlayer focuses on ONE song at a time
- Clean state flags: `should_stop`, `should_pause` (simple booleans instead of Events)
- Single threaded playback with immediate exit when done
- Callback logic simplified to just output current buffer or silence

### Key Improvements

1. **Simpler State Management**
   - Removed complex Event-based system
   - Using simple flags: `should_stop`, `should_pause`, `is_playing`
   - Clear, predictable state transitions

2. **Proper Thread Cleanup**
   - Threads now exit cleanly when song finishes or stop() is called
   - No more zombie threads in background
   - Explicit stream.close() in finally block ensures resource cleanup

3. **Predictable Behavior**
   - Audio loads once at thread start
   - Callback feeds samples sequentially until end of file
   - Clean detection of playback completion

4. **Better DJApp Control**
   - Simplified play_song() - just creates player and starts it
   - play_next() - no complex flags or tracking
   - pause_playback() - simple toggle of should_pause flag
   - stop_playback() - immediately stops current player
   - check_playback_status() - monitors is_playing and auto-advances

### File Structure

**AudioPlayer (Simplified)**
```python
class AudioPlayer(Thread):
    def __init__(self, filepath)
    def stop()           # Signal to stop
    def pause()          # Signal to pause
    def resume()         # Signal to resume  
    def run()            # Main playback loop - load, create stream, play
```

**DJApp Playback Methods**
```python
def play_song(row)           # Start playback of song at row
def play_next()              # Auto-advance to next song
def play_prev()              # Go to previous song
def pause_playback()         # Toggle pause/resume
def stop_playback()          # Stop everything
def check_playback_status()  # Monitor and auto-advance
```

### Behavior Changes (Expected Audio Player Features)

✅ **Play** - Audio outputs until song ends or stopped
✅ **Pause** - Audio stops; position held; resume continues
✅ **Stop** - Playback stops; resets to start
✅ **Next/Prev** - Immediately switches songs
✅ **Auto-advance** - After song finishes, plays next automatically
✅ **Single Stream** - Only ONE song audible (no mixing)
✅ **Clean State** - No zombie threads or ghost callbacks
✅ **Responsive UI** - Controls respond immediately

## Technical Highlights

### Callback Simplification
```python
def audio_callback(outdata, frames, time_info, status):
    # Check pause/stop
    if self.should_pause:
        outdata.fill(0)
        return
    
    # Get next chunk from position
    chunk = samples[position:position + frames]
    # ... fill outdata with chunk or zeros if end of file
```

### Thread Lifecycle
- Load audio once at thread start
- Create stream with callback
- Stream loops naturally until samples exhausted
- Check should_stop flag in main loop
- Close stream and exit in finally block

### No Global State
- Removed _active_player_id class variable
- Removed complex active player tracking
- Each player manages itself independently
- DJApp just tracks which player is current

## Testing Notes
- Songs load correctly and play to completion
- No more frozen callback counts
- Clean transitions to next song
- Failed songs are skipped properly
- Pause/resume works as expected
