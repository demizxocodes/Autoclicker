# Autoclicker

A small Windows autoclicker. Pick spots on your screen (A, B, C, ...), choose how
long to wait before each click, and it clicks them in order, then repeats.
Your click spots are saved, so you only set them up once.

## Download

Get **Autoclicker.exe** from the [Releases](../../releases) page and run it. Nothing
to install. Windows SmartScreen may warn about an unknown publisher the first time:
click **More info → Run anyway**.

## How to use

1. Click **+ Add point**. The screen dims. Click the spot you want clicked. That's point **A**.
2. Add more points the same way (**B**, **C**, ...). They're clicked top to bottom, then it starts over.
3. Select a point to change it:
   - **Wait (sec)**: how long to wait *before* clicking this point (e.g. wait 2 s then click A, wait 0.5 s then click B).
   - **Button**: left, right or middle.
   - **Click**: single or double.
   - Double-click a row (or **Re-pick location**) to choose a new spot.
4. Under **How long to run**, choose to run until you stop it, for a number of rounds,
   or for a set time.
5. Press **Start** or **F6** (works even when the window is in the background).
   Press **F6** again to stop.

### Profiles

Everything saves automatically. Use **New / Copy / Rename / Delete** to keep separate
setups (e.g. one per game). They're stored in `%APPDATA%\Autoclicker\profiles.json`.

## Run from source

```
pip install -r requirements.txt
python main.py
```

Run the tests with `pip install pytest && python -m pytest`.

## Building the exe

Every push to `main` builds `Autoclicker.exe` with GitHub Actions (download it from
the run's *Artifacts*). Pushing a tag like `v1.0.1` also publishes it as a Release.
To build locally on Windows:

```
pip install -r requirements.txt pyinstaller
pyinstaller --onefile --windowed --name Autoclicker --hidden-import pynput.keyboard._win32 --hidden-import pynput.mouse._win32 main.py
```
