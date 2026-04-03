DJ Setlist Organizer (AudioSetlist)
===================================

Prepare your DJ gigs: play tracks from a folder, reorder on the fly, and lock in your final set order by renaming files with numeric indices.

Run locally
-----------

You need **Python 3.10+**, `PyQt6`, and `python-vlc` installed:

```bash
pip install PyQt6 python-vlc

python DJ_Setlist_Organizer.py
```

In-app help (F1)
----------------

This is the same help content you see when you press **F1** in the app, rewritten as plain Markdown.

### Features

- **Drag-and-drop reordering**: Arrange your tracks in the ideal order for your set.
- **Live playback & preview**: Listen to each track directly in the app.
- **Save order by renaming**: Rename all files with sequential indices (for example `001_song.mp3`, `002_song.mp3`).
- **Custom start index**: Start numbering from any value to fit your existing file naming scheme.
- **Search & filter**: Quickly find songs in your collection.
- **Dark theme**: Easy on the eyes during long sessions.
- **Keyboard shortcuts**: Speed up your workflow with handy shortcuts.
- **Remove tracks**: Delete tracks from your setlist (without deleting files from disk).
- **Undo/redo**: Undo or redo playlist reordering and file renaming.

### Keyboard shortcuts

#### Playback

- **Space**: Play / Pause  
- **Ctrl + Right**: Next track  
- **Ctrl + Left**: Previous track  
- **Shift + Right**: Fast forward 5 seconds  
- **Shift + Left**: Fast backward 5 seconds  
- **Ctrl + S**: Stop  
- **Ctrl + Up**: Volume up  
- **Ctrl + Down**: Volume down  

#### Navigation

- **Enter**: Play selected song  
- **Ctrl + P**: Scroll to “Now Playing”  
- **Ctrl + F**: Focus search box  
- **Esc**: Clear search box  
- **Delete**: Remove selected track from setlist  

#### Playlist

- **Ctrl + O**: Select folder  
- **F5**: Refresh song list  
- **Ctrl + Shift + R**: Rename all files (add index)  
- **F2**: Rename selected file  
- **Shift + Up / Down**: Move selected song up / down  
- **Ctrl + L**: Toggle loop  
- **Ctrl + Z**: Undo playlist reorder  
- **Ctrl + Y**: Redo playlist reorder  
- **Ctrl + Shift + Z**: Undo rename  
- **Ctrl + Shift + Y**: Redo rename  

#### Help

- **F1**: Show this help in the app dialog  

Tagline: *AudioSetlist – your music, your order, your way.*

