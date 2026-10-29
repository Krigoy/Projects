# AVA — Python Voice Assistant

A desktop voice assistant written in Python. AVA listens for spoken commands, answers out loud, and can search the web, Wikipedia and YouTube, tell jokes, keep a to-do list, set reminders, and open or close applications.

There is also a **text mode** (`--text`) for typing commands instead of speaking, which is handy for testing without a microphone.

## Features

| Say… | What happens |
|---|---|
| "search the web for *python decorators*" | Opens Google results in your browser |
| "search Wikipedia for *Alan Turing*" | Reads the first two sentences of the Wikipedia summary |
| "search YouTube for *lofi music*" / "play *lofi music*" | Opens the top matching video |
| "tell me a joke" | Fetches a safe-mode joke from JokeAPI |
| "what time is it" | Says the current time |
| "make a to-do list" / "read my to-do list" | Collects tasks until you say "done", then reads them back |
| "set a reminder" | Asks what and when ("5:30 PM", "17:30" or "in 10 minutes"), then speaks the reminder at that time |
| "open *notepad*" / "close *notepad*" | Launches or closes an application (Windows, macOS and Linux) |
| "what can you do" | Lists the commands |
| "stop" / "bye" | Exits |

## How it works

- **Speech to text:** [SpeechRecognition](https://pypi.org/project/SpeechRecognition/) with Google's free web recognizer (needs an internet connection) and ambient-noise calibration.
- **Text to speech:** [pyttsx3](https://pypi.org/project/pyttsx3/), which runs offline using the OS voices (SAPI5, NSSpeechSynthesizer or eSpeak). AVA picks a female voice if one is installed.
- **Commands:** a small router in `process_command` matches phrases and calls the relevant method. Short phrases like "stop" end the session; "search YouTube for stop motion" does not.
- **Reminders:** time phrases are parsed by `parse_reminder_time` and scheduled with a background `threading.Timer`.
- **Safety:** application names are sanitised before being passed to the OS launcher, and core system processes (Explorer, Finder, systemd…) can't be closed by voice.

## Getting started

### Prerequisites

- Python 3.10+
- A microphone for voice mode
- On Linux: `sudo apt install portaudio19-dev espeak` (needed by PyAudio and pyttsx3)

### Install and run

```bash
cd AVA
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-voice.txt   # voice mode only (needs PortAudio); skip for --text

python ava.py          # voice mode
python ava.py --text   # text mode, no microphone needed
```

If PyAudio fails to install on Windows, try `pip install pipwin && pipwin install pyaudio`, or use text mode.

## Limitations

- Speech recognition uses Google's online service, so voice mode needs internet access.
- Reminders and the to-do list live in memory and are lost when AVA exits.
- No wake word: AVA listens continuously while running.
- YouTube results come from the public search page, so they can break if YouTube changes its markup (AVA then falls back to opening the search results).

## Ideas for next steps

- Wake-word activation (e.g. Porcupine or openWakeWord)
- Offline speech recognition (Vosk or Whisper)
- Saving reminders and to-dos to a file
- Translation between languages
