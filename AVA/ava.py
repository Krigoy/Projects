"""
AVA — a desktop voice assistant.

Listens for spoken commands (Google Speech Recognition via SpeechRecognition),
answers out loud (pyttsx3, offline TTS) and can search the web, Wikipedia and
YouTube, tell jokes, keep a to-do list, set reminders, and open or close apps.

Run:
    python ava.py          # voice mode (microphone)
    python ava.py --text   # type commands instead of speaking (no microphone needed)
"""

import argparse
import datetime
import platform
import re
import subprocess
import sys
import threading
import webbrowser
from urllib.parse import quote_plus

import psutil
import pyttsx3
import requests
import wikipediaapi

try:  # only needed for voice mode
    import speech_recognition as sr
except ImportError:  # pragma: no cover - text mode works without it
    sr = None

JOKE_API_URL = "https://v2.jokeapi.dev/joke/Any?safe-mode"
WIKI_USER_AGENT = "AVA-Voice-Assistant/1.0 (https://github.com/Krigoy/Projects)"
EXIT_WORDS = {"stop", "exit", "quit", "goodbye", "bye"}
FEMALE_VOICE_HINTS = ("zira", "hazel", "female", "samantha", "victoria", "karen", "susan")

# Process names that should never be closed by a voice command.
PROTECTED_PROCESSES = {"explorer", "system", "systemd", "launchd", "finder", "python", "windowserver", "init"}

HELP_TEXT = [
    "search the web for <topic>",
    "search Wikipedia for <topic>",
    "search YouTube for <topic>",
    "tell a joke",
    "make a to-do list / read my to-do list",
    "set a reminder",
    "what time is it",
    "open <app> / close <app>",
    "stop",
]


class AVAAssistant:
    def __init__(self, text_mode: bool = False):
        self.text_mode = text_mode
        self.todo_list: list[str] = []
        self.wiki = wikipediaapi.Wikipedia(user_agent=WIKI_USER_AGENT, language="en")

        self.recognizer = None
        if not text_mode:
            if sr is None:
                raise RuntimeError("SpeechRecognition is not installed; use --text or pip install -r requirements.txt")
            self.recognizer = sr.Recognizer()

        self.engine = self._init_tts()
        self._tts_lock = threading.Lock()

    # ------------------------------------------------------------------ I/O
    def _init_tts(self):
        try:
            engine = pyttsx3.init()
        except Exception as e:  # no audio device / driver
            print(f"(Text-to-speech unavailable: {e}. Replies will be printed only.)")
            return None

        # Prefer a female voice if one is installed (names differ per OS).
        for voice in engine.getProperty("voices") or []:
            name = f"{getattr(voice, 'name', '')} {getattr(voice, 'id', '')}".lower()
            if any(hint in name for hint in FEMALE_VOICE_HINTS):
                engine.setProperty("voice", voice.id)
                break
        engine.setProperty("rate", 175)
        return engine

    def speak(self, text: str) -> None:
        print(f"AVA: {text}")
        if self.engine is None:
            return
        with self._tts_lock:
            self.engine.say(text)
            self.engine.runAndWait()

    def listen(self, prompt: str = "Listening...") -> str | None:
        """Return the user's command as lowercase text, or None if nothing was understood."""
        if self.text_mode:
            try:
                text = input("You: ").strip()
            except EOFError:
                return "exit"
            return text.lower() or None

        try:
            microphone = sr.Microphone()
        except (OSError, AttributeError) as e:
            raise RuntimeError(
                "No microphone available (or PyAudio isn't installed). "
                "Run with --text to type commands instead."
            ) from e

        with microphone as source:
            print(prompt)
            self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
            try:
                audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=10)
            except sr.WaitTimeoutError:
                return None

        try:
            text = self.recognizer.recognize_google(audio)
        except sr.UnknownValueError:
            return None
        except sr.RequestError as e:
            self.speak("I can't reach the speech recognition service right now.")
            print(f"Speech recognition error: {e}")
            return None

        print(f"You: {text}")
        return text.lower()

    # ------------------------------------------------------------ features
    def search_web(self, query: str) -> None:
        if not query:
            self.speak("What should I search for?")
            return
        webbrowser.open(f"https://www.google.com/search?q={quote_plus(query)}")
        self.speak(f"Here are the search results for {query}.")

    def search_wikipedia(self, query: str) -> None:
        if not query:
            self.speak("What should I look up on Wikipedia?")
            return
        try:
            page = self.wiki.page(query)
            exists = page.exists()
        except Exception as e:
            print(f"Wikipedia error: {e}")
            self.speak("Sorry, I couldn't reach Wikipedia.")
            return

        if not exists:
            self.speak(f"Sorry, I couldn't find a Wikipedia page for {query}.")
            return

        # First two sentences keep the spoken answer short.
        sentences = re.split(r"(?<=[.!?])\s+", page.summary.strip())
        self.speak("According to Wikipedia, " + " ".join(sentences[:2]))

    def search_youtube(self, query: str) -> None:
        if not query:
            self.speak("What should I search for on YouTube?")
            return
        search_url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
        try:
            html = requests.get(search_url, timeout=10).text
            match = re.search(r"watch\?v=([A-Za-z0-9_-]{11})", html)
        except requests.RequestException as e:
            print(f"YouTube error: {e}")
            match = None

        if match:
            webbrowser.open(f"https://www.youtube.com/watch?v={match.group(1)}")
            self.speak(f"Playing a video about {query}.")
        else:
            webbrowser.open(search_url)
            self.speak(f"Here are YouTube results for {query}.")

    def tell_joke(self) -> None:
        try:
            data = requests.get(JOKE_API_URL, timeout=10).json()
        except (requests.RequestException, ValueError) as e:
            print(f"Joke API error: {e}")
            self.speak("Sorry, I couldn't fetch a joke right now.")
            return

        if data.get("type") == "single":
            self.speak(data.get("joke", ""))
        elif data.get("type") == "twopart":
            self.speak(data.get("setup", ""))
            self.speak(data.get("delivery", ""))
        else:
            self.speak("I couldn't find a joke this time.")

    def tell_time(self) -> None:
        self.speak("It's " + datetime.datetime.now().strftime("%I:%M %p").lstrip("0"))

    def create_todo_list(self) -> None:
        self.speak("Sure. Tell me each task, and say 'done' when you're finished.")
        while True:
            task = self.listen("Task:")
            if task is None:
                self.speak("I didn't catch that. Say the task again, or say done.")
                continue
            # EXIT_WORDS also covers end of input in text mode, which listen() reports as "exit".
            if task in {"done", "that's it", "finished"} or task in EXIT_WORDS:
                break
            self.todo_list.append(task)
            self.speak(f"Added {task}.")
        self.read_todo_list()

    def read_todo_list(self) -> None:
        if not self.todo_list:
            self.speak("Your to-do list is empty.")
            return
        count = len(self.todo_list)
        self.speak(f"You have {count} task{'' if count == 1 else 's'}.")
        for i, task in enumerate(self.todo_list, start=1):
            self.speak(f"{i}. {task}")

    def set_reminder(self) -> None:
        self.speak("What should I remind you about?")
        reminder_text = self.listen("Reminder:")
        if not reminder_text:
            self.speak("I didn't catch that, so I haven't set a reminder.")
            return

        for _ in range(3):
            self.speak("When? Say a time like 5:30 PM, or 'in 10 minutes'.")
            when = self.listen("Time:")
            delay = parse_reminder_time(when or "")
            if delay is not None:
                break
            self.speak("Sorry, I couldn't understand that time.")
        else:
            self.speak("I couldn't get a time, so I haven't set the reminder.")
            return

        timer = threading.Timer(delay, lambda: self.speak(f"Reminder: {reminder_text}"))
        timer.daemon = True
        timer.start()
        due = datetime.datetime.now() + datetime.timedelta(seconds=delay)
        self.speak(f"Okay, I'll remind you to {reminder_text} at {due.strftime('%I:%M %p').lstrip('0')}.")

    def open_application(self, name: str) -> None:
        name = sanitize_app_name(name)
        if not name:
            self.speak("Which application should I open?")
            return

        system = platform.system()
        try:
            if system == "Windows":
                if name == "recycle bin":
                    subprocess.Popen(["explorer", "shell:RecycleBinFolder"])
                else:
                    # 'start' is a cmd built-in; the name is sanitised above.
                    subprocess.Popen(["cmd", "/c", "start", "", name])
            elif system == "Darwin":
                subprocess.run(["open", "-a", name], check=True)
            else:
                subprocess.Popen([name.replace(" ", "-")])
            self.speak(f"Opening {name}.")
        except (OSError, subprocess.CalledProcessError) as e:
            print(f"Could not open {name}: {e}")
            self.speak(f"Sorry, I couldn't open {name}.")

    def close_application(self, name: str) -> None:
        name = sanitize_app_name(name)
        if len(name) < 3:
            self.speak("Which application should I close?")
            return

        closed = 0
        for proc in psutil.process_iter(["name"]):
            proc_name = (proc.info.get("name") or "").lower()
            base = proc_name.rsplit(".", 1)[0]
            if base in PROTECTED_PROCESSES or name not in proc_name:
                continue
            try:
                proc.terminate()
                closed += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        if closed:
            self.speak(f"Closed {name}.")
        else:
            self.speak(f"I couldn't find {name} running.")

    def show_help(self) -> None:
        self.speak("Here's what I can do:")
        for line in HELP_TEXT:
            print(f"  - {line}")
        if self.engine is not None:
            self.speak(", ".join(HELP_TEXT[:-1]) + ".")

    # ------------------------------------------------------------ routing
    def process_command(self, command: str) -> bool:
        """Handle one command. Returns False when the assistant should stop."""
        command = command.lower().strip()

        words = re.findall(r"[a-z']+", command)
        # Only short phrases like "stop" or "ok bye" end the session, so
        # "search youtube for stop motion" still works.
        if len(words) <= 3 and set(words) & EXIT_WORDS:
            self.speak("Goodbye! Have a great day.")
            return False

        prefixes = [
            (("search wikipedia for", "wikipedia"), self.search_wikipedia),
            (("search youtube for", "play", "youtube"), self.search_youtube),
            (("search the web for", "search for", "google"), self.search_web),
        ]
        for keys, handler in prefixes:
            for key in keys:
                if command.startswith(key):
                    handler(command[len(key):].strip())
                    return True

        if "what can you do" in command or command == "help":
            self.show_help()
        elif "joke" in command:
            self.tell_joke()
        elif "time" in command and "remind" not in command:
            self.tell_time()
        elif "read" in command and "to-do" in command.replace("todo", "to-do"):
            self.read_todo_list()
        elif "to-do" in command.replace("todo", "to-do"):
            self.create_todo_list()
        elif "remind" in command:
            self.set_reminder()
        elif words and words[0] == "open":
            self.open_application(command[len("open"):])
        elif words and words[0] == "close":
            self.close_application(command[len("close"):])
        else:
            self.speak("Sorry, I don't know that one yet. Say 'what can you do' to hear my commands.")
        return True

    def run(self) -> None:
        self.speak("Hello! I'm AVA, your voice assistant. How can I help you today?")
        while True:
            try:
                command = self.listen()
                if command is None:
                    continue
                if not self.process_command(command):
                    break
            except KeyboardInterrupt:
                self.speak("Goodbye!")
                break


# ---------------------------------------------------------------- helpers
def sanitize_app_name(name: str) -> str:
    """Keep only characters that are safe to pass to the OS launcher."""
    return re.sub(r"[^a-z0-9 ._-]", "", name.lower()).strip()


def parse_reminder_time(text: str, now: datetime.datetime | None = None) -> float | None:
    """
    Convert '5:30 pm', '5 pm', '17:30' or 'in 10 minutes' / 'in 2 hours'
    into seconds from now. Returns None if the text isn't understood.
    """
    now = now or datetime.datetime.now()
    # Only strip the dots in "a.m." / "p.m." so decimals like "1.5 hours" survive.
    text = re.sub(r"\b([ap])\.m\.?", r"\1m", text.lower()).strip()

    rel = re.search(r"in (\d+(?:\.\d+)?) (second|minute|hour)s?", text)
    if rel:
        n, unit = float(rel.group(1)), rel.group(2)
        return n * {"second": 1, "minute": 60, "hour": 3600}[unit]

    m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", text)
    if not m:
        return None
    hour, minute, ampm = int(m.group(1)), int(m.group(2) or 0), m.group(3)
    if ampm == "pm" and hour != 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    if not (0 <= hour < 24 and 0 <= minute < 60) or (ampm is None and m.group(2) is None):
        return None  # bare numbers like "5" are too ambiguous

    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += datetime.timedelta(days=1)
    return (target - now).total_seconds()


def main() -> None:
    parser = argparse.ArgumentParser(description="AVA voice assistant")
    parser.add_argument("--text", action="store_true", help="type commands instead of speaking")
    args = parser.parse_args()

    try:
        AVAAssistant(text_mode=args.text).run()
    except RuntimeError as e:
        print(e)
        sys.exit(1)


if __name__ == "__main__":
    main()
