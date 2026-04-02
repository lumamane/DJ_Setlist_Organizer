


DJing App

you are a very experienced app developer with vast knowledge of dj software.

Make dj app in python  pyQt, use best modules for this useccase

Features 

- select 2 up to two folders via treeview (includes search and filtering of files and folders)

- user can select wich of both is the  active folder
- user can select wich of both is the  active song (playing it, if no other song is already beein played, or play it next , if a song is already playing)

- show folders content (standard orderd by name)
- show selected folder, number of songs, total playtime

- analyse songs (bpm,key)  

- play folder in Shown order (play/pause, stop, next)
- show infos to selected, playing song

- Autoplay songs in SHOWN order 

- change order of songs (drag and drop, or keys) influencing immediatly wich song is played next  (next in SHOWN list))

- toggle if first song is played after the last song in the active folder



- add or replace indexNumberTag to file names, format "[001]" (same length of this index for all filenames, always at the left of filename)  to ALL Filenames

- remove existing indexnumberTags in ALL filenames.

- add or replace TypeTag to filename. for example "[bachata]", [salsa],[salsa_ro], [salsa_d]  (same taglength for all files, add "_" automaticaly to the right to fill up space) ;  user can input new value or easily choose from existing values

- add or remove bracets to songname


songnames can be (exmples):

songnameA.mp3
songnameB.m4a

or

[songnameA].mp3
[songnameB].m4a


or

[001]songnameA.mp3
[001]songnameB.m4a

or

[bachata]songnameA.mp3
[salsa__]songnameB.m4a

or 
[001][bachata]songnameA.mp3
[002][salsa__]songnameB.m4a

or 
[001][bachata][songnameA].mp3
[002][salsa__][songnameB].m4a


index | type | songfile                 | ext | Filename                      | alterFilenameTo
---------------------------------------------------------------------------------------------
      |      | vivir la - marc anthony  | m4a | vivir la - marc anthony.mpa   |  
      |      | romeo santos - mi cancion | mp3 | romeo santos - mi cancion.mp3 |
      |      | prince royce - amor      | mp3 | romeo santos - mi cancion.mp3 |  



user can change position of songs in table, affecting tho order the files are played. 
(drag and drop)
next file played is always file below the actual playing song SHOWN in the table 

index | type | songfile                  | ext | Filename                       | alterFilenameTo
---------------------------------------------------------------------------------------------
      |      | vivir la - marc anthony   | m4a | vivir la - marc anthony.mpa    |
      |      | prince royce - amor       | mp3 | romeo santos - amor.mp3  |    
      |      | romeo santos - mi cancion | mp3 | romeo santos - mi cancion.mp3 |


in this case if "vivir la - marc anthony" is playing, next song will be "prince royce - amor"


user can hit button [index] to add or overwrite existing indexnumbers into the table accordingly the SHOWN order in the table. 
format: "001_" 
(all indexnumbers have the same digits as the bigest digit in the column filled up with "0" in the left)
alterFilenameTo: values are proposed

index | type | songfile                 | ext | Filename                       | alterFilenameTo
---------------------------------------------------------------------------------------------
001      |      | vivir la - marc anthony  | m4a | vivir la - marc anthony.mpa    | 001_vivir la - marc anthony.mpa
002      |      | prince royce - amor      | mp3 | romeo santos - amor.mp3        | 002_romeo santos - amor.mp3   
003      |      | romeo santos - mi cancion | mp3 | romeo santos - mi cancion.mp3 | 003_romeo santos - mi cancion.mp3


user can edit (song) "type" value or choose from values allready existing in column . (all type values have the same length filled up with spaces " " on the right side). format:
_[salsa  ]_
_[bachata]_
_[       ]_
(if ANY file has type: every file gets type ) 


index | type | songfile                 | ext | Filename                       | alterFilenameTo
---------------------------------------------------------------------------------------------
001      | salsa   | vivir la - marc anthony  | m4a | vivir la - marc anthony.mpa    | 001_[salsa  ]_vivir la - marc anthony.m4a
002      | bachata | prince royce - amor      | mp3 | romeo santos - amor.mp3        | 002_[bachata]_romeo santos - amor.mp3   
003      | bachata | romeo santos - mi cancion | mp3 | romeo santos - mi cancion.mp3 | 003_[       ]_romeo santos - mi cancion.mp3

 
if NO file has a type value

index    | type | songfile                  | ext | Filename                       | alterFilenameTo
---------------------------------------------------------------------------------------------
001      |      | vivir la - marc anthony   | m4a | vivir la - marc anthony.mpa  | 001_vivir la - marc anthony.m4a
002      |      | prince royce - amor       | mp3 | romeo santos - amor.mp3      | 002_romeo santos - amor.mp3   
003      |      | romeo santos - mi cancion | mp3 | romeo santos - mi cancion.mp3 | 003_romeo santos - mi cancion.mp3

when user hits [save filenames]:
stop playing song
 rename files with proposedNewFilenames. reload table
(order by filename ascending)  

it now should look like this:

index | type | songfile                 | ext | Filename                       | alterFilenameTo
---------------------------------------------------------------------------------------------
001      |    | vivir la - marc anthony  | m4a | 001_vivir la - marc anthony.m4a |
002      |  | prince royce - amor        | mp3 | 002_romeo santos - amor.mp3     | 
003      |  | romeo santos - mi cancion  | mp3 | romeo santos - mi cancion.mp3   | 







index | type    | interpret    | title         | key | bpm | filenameNew | filename
-------------------------------------------------------------------------------------
001   | salsa   | Marc Anthony | vivir la vida | E8  | 124 | [001][salsa__][Marc Anthony][vivir la vida].mp4" | vivir la vida - Marc Anthony.mp4
002   | bachata | romeo santos | mi cancion    | A8  | 098 | [002][bachata][romeo santos][mi cancion].mp3 | romeo santos - mi cancion.mp3


changing the filenames permanently should only happen when users hits "save filenames"
after this it could look like this:


index | type    | interpret    | title         | key | bpm | filenameNew | filename
-------------------------------------------------------------------------------------
001   | salsa   | Marc Anthony | vivir la vida | E8  | 124 | [001][salsa__][Marc Anthony][vivir la vida].mp4" | [001][salsa__][Marc Anthony][vivir la vida].mp4"
002   | bachata | romeo santos | mi cancion    | A8  | 098 | [002][bachata][romeo santos][mi cancion].mp3 | [002][bachata][romeo santos][mi cancion].mp3



- playing the songs should ALLWAYS occure in the SHOWN order (saved or not !) 
  following the active played song. unless user selects an other song as "next song"


- user can easiely toggle if values of a column are shown or not 
(not deleting the actueal values!) 

- save only the tags having values that are actualy shown.


- when reading a folder, repopulate fields using existing tags in the filenames.
  there can be various situations:

  only indexTag (numeric) exists , 
  only typeTag exists (have always same lenght), 
  both indexTag and TypeTag exist,

  addionally the former can have (allways both) songTags (interpret and title) or not.

  indexTag (numeric) allways left

