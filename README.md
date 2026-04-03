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

This is the same help content you see when you press **F1** in the app.

```html
<h1 style="color: #eee; text-align: center;">AudioSetlist: DJ Setlist Organizer</h1>

<p><strong>Prepare your next DJ gig with ease!</strong><br>
AudioSetlist helps you <strong>organize, listen, and order your music files</strong> for upcoming performances.
With a clean, dark-themed interface and intuitive controls, you can focus on crafting the perfect setlist.</p>

<h2 style="color: #eee;">Key Features</h2>
<ul>
    <li><strong>Drag-and-Drop Reordering:</strong> Arrange your tracks in the ideal order for your set.</li>
    <li><strong>Live Playback & Preview:</strong> Listen to each track directly in the app.</li>
    <li><strong>Save Order by Renaming:</strong> Rename all files with sequential indices (e.g., 001_song.mp3, 002_song.mp3).</li>
    <li><strong>Custom Start Index:</strong> Start numbering from any value to fit your existing file naming scheme.</li>
    <li><strong>Search & Filter:</strong> Quickly find songs in your collection.</li>
    <li><strong>Dark Theme:</strong> Easy on the eyes during long studio sessions.</li>
    <li><strong>Keyboard Shortcuts:</strong> Speed up your workflow with handy shortcuts.</li>
    <li><strong>Remove Tracks:</strong> Delete tracks from your setlist (without deleting files from disk).</li>
    <li><strong>Undo/Redo:</strong> Undo or redo playlist reordering and file renaming.</li>
</ul>

<h2 style="color: #eee;">Keyboard Shortcuts</h2>

<h3 style="color: #eee;">Playback</h3>
<table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse; width: 100%;">
    <tr><th>Shortcut</th><th>Action</th></tr>
    <tr><td><b>Space</b></td><td>Play/Pause</td></tr>
    <tr><td><b>Ctrl+→</b></td><td>Next Track</td></tr>
    <tr><td><b>Ctrl+←</b></td><td>Previous Track</td></tr>
    <tr><td><b>Shift+→</b></td><td>Fast Forward (5 sec)</td></tr>
    <tr><td><b>Shift+←</b></td><td>Fast Backward (5 sec)</td></tr>
    <tr><td><b>Ctrl+S</b></td><td>Stop</td></tr>
    <tr><td><b>Ctrl+↑</b></td><td>Volume Up</td></tr>
    <tr><td><b>Ctrl+↓</b></td><td>Volume Down</td></tr>
</table>

<h3 style="color: #eee;">Navigation</h3>
<table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse; width: 100%;">
    <tr><th>Shortcut</th><th>Action</th></tr>
    <tr><td><b>Enter</b></td><td>Play Selected Song</td></tr>
    <tr><td><b>Ctrl+P</b></td><td>Scroll to Now Playing</td></tr>
    <tr><td><b>Ctrl+F</b></td><td>Focus Search Box</td></tr>
    <tr><td><b>Esc</b></td><td>Clear Search Box</td></tr>
    <tr><td><b>Delete</b></td><td>Remove Selected Track from Setlist</td></tr>
</table>

<h3 style="color: #eee;">Playlist</h3>
<table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse; width: 100%;">
    <tr><th>Shortcut</th><th>Action</th></tr>
    <tr><td><b>Ctrl+O</b></td><td>Select Folder</td></tr>
    <tr><td><b>F5</b></td><td>Refresh Song List</td></tr>
    <tr><td><b>Ctrl+Shift+R</b></td><td>Rename All Files (Add Index)</td></tr>
    <tr><td><b>F2</b></td><td>Rename Selected File</td></tr>
    <tr><td><b>Shift+↑/↓</b></td><td>Move Selected Song Up/Down</td></tr>
    <tr><td><b>Ctrl+L</b></td><td>Toggle Loop</td></tr>
    <tr><td><b>Ctrl+Z</b></td><td>Undo Playlist Reorder</td></tr>
    <tr><td><b>Ctrl+Y</b></td><td>Redo Playlist Reorder</td></tr>
    <tr><td><b>Ctrl+Shift+Z</b></td><td>Undo Rename</td></tr>
    <tr><td><b>Ctrl+Shift+Y</b></td><td>Redo Rename</td></tr>
</table>

<h3 style="color: #eee;">Help</h3>
<table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse; width: 100%;">
    <tr><th>Shortcut</th><th>Action</th></tr>
    <tr><td><b>F1</b></td><td>Show This Help</td></tr>
</table>

<p style="text-align: center; font-size: 11px; color: #aaa;">
    AudioSetlist: Your music, your order, your way.
</p>
```

