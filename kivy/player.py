from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.listview import ListItemButton
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.popup import Popup
from kivy.uix.slider import Slider
from kivy.core.audio import SoundLoader
from kivy.clock import Clock
from kivy.properties import StringProperty, NumericProperty, ObjectProperty
from kivy.lang import Builder
from os.path import basename, dirname, join
from os import listdir

Builder.load_string('''
<AudioPlayer>
    orientation: 'vertical'
    padding: 10
    spacing: 10
    BoxLayout:
        size_hint_y: None
        height: 40
        Button:
            text: 'Select Folder'
            on_press: root.select_folder()
        Button:
            text: 'Refresh'
            on_press: root.refresh_songs()
    Label:
        id: folder_label
        text: 'No folder selected'
        size_hint_y: None
        height: 30
    BoxLayout:
        size_hint_y: None
        height: 30
        Label:
            id: time_label
            text: '00:00 / 00:00'
        Label:
            id: track_label
            text: 'Ready to play'
    ListView:
        id: song_list
        adapter:
            ListAdapter(
                data=root.songs,
                cls=ListItemButton,
                selection_mode='single',
                allow_empty_selection=True
            )
    BoxLayout:
        size_hint_y: None
        height: 40
        Button:
            text: 'Play/Pause'
            on_press: root.play_pause()
        Button:
            text: 'Stop'
            on_press: root.stop()
        Button:
            text: 'Prev'
            on_press: root.prev_track()
        Button:
            text: 'Next'
            on_press: root.next_track()
    Slider:
        id: progress_slider
        range: (0, 100)
        value: 0
        on_touch_down: root.seek(*args)
    Slider:
        id: volume_slider
        range: (0, 100)
        value: 70
        on_value: root.set_volume(args[1])
''')

class AudioPlayer(BoxLayout):
    songs = []
    current_track = None
    current_index = -1
    sound = None
    is_playing = False
    folder_label = ObjectProperty()
    time_label = ObjectProperty()
    track_label = ObjectProperty()
    progress_slider = ObjectProperty()
    volume_slider = ObjectProperty()
    song_list = ObjectProperty()

    def __init__(self, **kwargs):
        super(AudioPlayer, self).__init__(**kwargs)
        Clock.schedule_interval(self.update_progress, 1)

    def select_folder(self):
        content = BoxLayout(orientation='vertical')
        filechooser = FileChooserListView()
        content.add_widget(filechooser)
        popup = Popup(title="Select a folder", content=content, size_hint=(0.9, 0.9))
        filechooser.bind(on_submit=lambda x: self.load_songs(filechooser.path, popup))
        popup.open()

    def load_songs(self, folder, popup):
        self.songs = []
        for f in listdir(folder):
            if f.lower().endswith(('.mp3', '.wav', '.m4a')):
                self.songs.append(join(folder, f))
        self.songs.sort()
        self.song_list.adapter.data = [basename(s) for s in self.songs]
        self.folder_label.text = f"Folder: {folder}"
        popup.dismiss()

    def refresh_songs(self):
        if not self.songs:
            return
        folder = dirname(self.songs[0])
        self.load_songs(folder, None)

    def play_song(self, index):
        if 0 <= index < len(self.songs):
            self.stop()
            self.current_index = index
            self.current_track = self.songs[index]
            self.sound = SoundLoader.load(self.current_track)
            if self.sound:
                self.sound.play()
                self.is_playing = True
                self.track_label.text = basename(self.current_track)
                self.progress_slider.max = self.sound.length
                Clock.schedule_interval(self.update_progress, 1)

    def play_pause(self):
        if self.sound:
            if self.is_playing:
                self.sound.stop()
                self.is_playing = False
            else:
                self.sound.play()
                self.is_playing = True

    def stop(self):
        if self.sound:
            self.sound.stop()
            self.is_playing = False
            self.progress_slider.value = 0
            self.time_label.text = '00:00 / 00:00'

    def next_track(self):
        if self.songs and self.current_index < len(self.songs) - 1:
            self.play_song(self.current_index + 1)

    def prev_track(self):
        if self.songs and self.current_index > 0:
            self.play_song(self.current_index - 1)

    def update_progress(self, dt):
        if self.sound and self.is_playing:
            self.progress_slider.value = self.sound.get_pos()
            self.time_label.text = f"{int(self.sound.get_pos() // 60000):02d}:{int((self.sound.get_pos() % 60000) / 1000):02d} / {int(self.sound.length // 60000):02d}:{int((self.sound.length % 60000) / 1000):02d}"

    def seek(self, slider, touch):
        if self.sound and touch.button == 'left':
            self.sound.seek(slider.value)

    def set_volume(self, instance, volume):
        if self.sound:
            self.sound.volume = volume / 100

class AudioPlayerApp(App):
    def build(self):
        return AudioPlayer()

if __name__ == '__main__':
    AudioPlayerApp().run()
