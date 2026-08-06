<p align="center">
<img width="128" height="128" alt="512" src="https://github.com/user-attachments/assets/0f339739-5a1a-4234-a6d8-0641a1582c77" />
</p>

# Grok-Discord-Share
A simple app that converts MP4 videos to WEBMs which autoplay and loop on Discord

<p align="center">
<img width="542" height="492" alt="image" src="https://github.com/user-attachments/assets/f4472657-b829-4dbd-acb8-32025dca2715" />
</p>

## Instructions

1. Install dependencies

```pip install tkinterdnd2 pillow python-dotenv pywin32 win11toast```

2. Run Start.bat
3. The app will automatically download and extract FFMPEG and create a folder called images to store the created WEBP files
4. Drag images or videos into the gui or click the select files button & use an explorer dialogue to select the desired files - After processing images will be automatically copied to your clipboard, so you can just press Ctrl + V directly into the discord chat you want to share them to.
5. (Recommended) Create or edit the file: .env to adjust the following:
```
ARTIST_NAME=Sinulated
COMMENT=Visit Sinulated.art For More!
START_QUALITY=91
FILENAME_TEMPLATE=Sinulated Preview {index:04d}
MAX_FILESIZE_MB=10
MAX_WIDTH=800
```

## Details

The intended use of this app is to make grok imagine videos more discord shareable. It attempts to convert the MP4 provided by grok as losslessly as possible while keeping the filesize under the 10MB maximum allowed by discord (without nitro). It does this by starting at a quality level of 91%, if the produced file is larger than 10MB it drops the quality until the resulting file is under 10MB. This *does* mean that some files will have to be processed up to several times, if you're finding that it appears to be doing this more than you'd like, you can decrease the start quality in the .env file. Also, i don't think the artist name and comment are being correctly applied, but i might fix that some day if i update the app
