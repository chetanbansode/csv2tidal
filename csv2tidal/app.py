#!/usr/bin/env python3
"""
Standalone CSV to TIDAL transfer utility.
"""

import argparse
import csv
import json
import os
import re
import sys
import time
import webbrowser

if os.name == "nt":
    import msvcrt
from dataclasses import asdict, dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import List, Optional
import tkinter as tk
from tkinter import filedialog

import tidalapi
from rich import box
from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text

console = Console()

ACCENT = "bright_cyan"
DIM = "grey50"
SUCCESS = "green"
WARN = "yellow"
ERR = "red"

APP_DIR = Path(__file__).resolve().parent
LEGACY_APP_DATA_DIR = Path(os.getenv("APPDATA", str(Path.home()))) / "tidal-transfer"
APP_DATA_DIR = Path(os.getenv("APPDATA", str(Path.home()))) / "csv2tidal"
SESSION_FILE = APP_DATA_DIR / "tidal_session.json"
SETTINGS_FILE = APP_DATA_DIR / "settings.json"
APP_VERSION = "0.1.0"
DEFAULT_MATCH_THRESHOLD = 160


@dataclass
class AppSettings:
    output_dir: str = ""
    transfer_mode: str = "accurate"
    generate_report: bool = True


@dataclass
class ImportedTrack:
    index: int
    title: str
    artists: List[str]
    collection: str = ""
    album: str = ""
    isrc: str = ""
    year: str = ""
    duration_ms: Optional[int] = None
    source_url: str = ""
    source_id: str = ""


def load_json_file(path: Path, fallback):
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def save_json_file(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")


def migrate_app_data():
    if APP_DATA_DIR.exists() or not LEGACY_APP_DATA_DIR.exists():
        return
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    for name in ("tidal_session.json", "settings.json"):
        legacy_path = LEGACY_APP_DATA_DIR / name
        target_path = APP_DATA_DIR / name
        if legacy_path.exists() and not target_path.exists():
            try:
                target_path.write_text(legacy_path.read_text(encoding="utf-8"), encoding="utf-8")
            except Exception:
                pass


def load_settings():
    raw = load_json_file(SETTINGS_FILE, {})
    mode = str(raw.get("transfer_mode", "accurate")).strip().lower()
    if mode not in {"fast", "accurate"}:
        mode = "accurate"
    return AppSettings(
        output_dir=str(raw.get("output_dir", "")).strip(),
        transfer_mode=mode,
        generate_report=bool(raw.get("generate_report", True)),
    )


def save_settings(settings):
    save_json_file(SETTINGS_FILE, asdict(settings))


def ok(message):
    console.print(f"[green]OK[/] {message}")


def warn(message):
    console.print(f"[yellow]WARN[/] {message}")


def fail(message):
    console.print(f"[red]ERROR[/] {message}")


def clear_screen():
    command = "cls" if os.name == "nt" else "clear"
    os.system(command)


def get_layout_width(max_width=92, min_width=72):
    width = console.size.width - 4
    width = max(min_width, width)
    return min(max_width, width)


def print_header():
    body = Group(
        Align.center(Text("CSV2TIDAL", style=f"bold {ACCENT}")),
        Align.center(Text("CSV playlist transfer for TIDAL", style=DIM)),
        Align.center(Text(f"Version {APP_VERSION}  |  By Chetan", style=DIM)),
    )
    console.print()
    console.print(Align.center(Panel(body, border_style=ACCENT, padding=(1, 2), expand=False, width=get_layout_width())) )


def format_login_status():
    return "[green]Logged in[/]" if SESSION_FILE.exists() else "[red]Not logged in[/]"


def print_usage():
    table = Table(box=box.ROUNDED, border_style=ACCENT, header_style="bold white", padding=(0, 1))
    table.add_column("Flag", style=ACCENT)
    table.add_column("Description", style="white")
    table.add_column("Example", style=DIM)
    rows = [
        ("--import-file", "Exportify CSV or compatible file", "night.csv"),
        ("--transfer-favorites", "Add accepted matches to favorites", "--transfer-favorites"),
        ("--transfer-playlist", "Create a Tidal playlist for matches", "--transfer-playlist 'Night'"),
        ("--settings", "Open saved settings", "--settings"),
        ("--logout", "Remove saved Tidal session", "--logout"),
    ]
    for row in rows:
        table.add_row(*row)
    console.print(table)
    console.print()


def print_home_screen(settings):
    choices = Table(
        box=box.SQUARE,
        border_style=ACCENT,
        header_style=f"bold {ACCENT}",
        padding=(0, 1),
        expand=False,
        width=get_layout_width(),
    )
    choices.add_column("Choice", style=ACCENT, width=10)
    choices.add_column("Action", style="white")
    choices.add_row("1", "Transfer from Exportify CSV")
    choices.add_row("2", "Open settings")
    choices.add_row("3", "Logout from TIDAL")
    choices.add_row("4", "Show help")
    choices.add_row("Q", "Exit")

    settings_table = Table(
        box=box.SQUARE,
        border_style=ACCENT,
        header_style="bold yellow",
        padding=(0, 1),
        expand=False,
        width=get_layout_width(),
    )
    settings_table.add_column("Setting", style=ACCENT, width=24)
    settings_table.add_column("Current value", style="white")
    settings_table.add_row("Tidal account", format_login_status())
    settings_table.add_row("Generate JSON report", "On" if settings.generate_report else "Off")
    settings_table.add_row("Output folder", settings.output_dir or "Current folder")
    settings_table.add_row("Transfer mode", settings.transfer_mode.title())

    console.print(Align.center(Text("Choices", style=f"bold {ACCENT}")))
    console.print(Align.center(choices))
    console.print(Align.center(Text("Saved Settings", style="bold yellow")))
    console.print(Align.center(settings_table))
    console.print()


def clear_saved_session():
    if not SESSION_FILE.exists():
        return False
    try:
        SESSION_FILE.unlink()
        return True
    except Exception:
        return None


def configure_settings(settings):
    report_raw = console.input(f"  [cyan]Generate JSON report?[/] [Y/N, Enter = current: {'Y' if settings.generate_report else 'N'}]: ").strip().lower()
    if report_raw in {"y", "yes"}:
        settings.generate_report = True
    elif report_raw in {"n", "no"}:
        settings.generate_report = False
    elif report_raw:
        warn("Invalid report setting. Keeping current value.")
    output_dir = console.input(f"  [cyan]Output folder[/] [Enter = current: {settings.output_dir or 'Current folder'}]: ").strip()
    if output_dir:
        settings.output_dir = output_dir
    mode_raw = console.input(f"  [cyan]Transfer mode[/] [1 = Fast, 2 = Accurate, Enter = current: {settings.transfer_mode.title()}]: ").strip().lower()
    if mode_raw in {"1", "fast", "f"}:
        settings.transfer_mode = "fast"
    elif mode_raw in {"2", "accurate", "a"}:
        settings.transfer_mode = "accurate"
    elif mode_raw:
        warn("Invalid transfer mode. Keeping current value.")
    save_settings(settings)
    ok("Settings saved")
    console.print()
    return settings


def choose_import_file():
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askopenfilename(
            title="Select Exportify CSV",
            filetypes=[
                ("CSV files", "*.csv"),
                ("JSON files", "*.json"),
                ("All files", "*.*"),
            ],
        )
        root.destroy()
        return selected.strip()
    except Exception:
        return ""


def prompt_transfer_args(settings):
    console.print("  [dim]Opening file picker...[/]")
    import_file = choose_import_file()
    if import_file:
        console.print(f"  [cyan]Selected:[/] {import_file}")
    else:
        import_file = console.input("  [cyan]CSV file path[/]: ").strip().strip('"')
    if not import_file:
        warn("No import file provided.")
        console.print()
        return None
    mode = console.input("  [cyan]Mode[/] [1 = Favorites, 2 = Playlist, Enter = Playlist]: ").strip().lower()
    default_name = Path(import_file).stem
    transfer_favorites = mode in {"1", "favorites", "favorite", "f"}
    transfer_playlist = default_name if mode in {"", "2", "playlist", "p"} else ""
    if transfer_playlist:
        transfer_playlist = console.input(f"  [cyan]Playlist name[/] [Enter = {default_name}]: ").strip() or default_name
    console.print()
    return argparse.Namespace(
        import_file=import_file,
        output="",
        transfer_mode=settings.transfer_mode,
        dry_run=False,
        transfer_favorites=transfer_favorites,
        transfer_playlist=transfer_playlist,
        set_output_dir="",
        settings=False,
        logout=False,
    )


CYRILLIC_MAP = str.maketrans({
    "?": "a", "?": "b", "?": "v", "?": "g", "?": "d", "?": "e", "?": "e", "?": "zh", "?": "z",
    "?": "i", "?": "i", "?": "k", "?": "l", "?": "m", "?": "n", "?": "o", "?": "p", "?": "r",
    "?": "s", "?": "t", "?": "u", "?": "f", "?": "h", "?": "ts", "?": "ch", "?": "sh", "?": "sch",
    "?": "", "?": "y", "?": "", "?": "e", "?": "yu", "?": "ya",
})


def transliterate_text(value):
    value = str(value or "")
    return value.casefold().translate(CYRILLIC_MAP)


def normalize_match_text(value):
    value = transliterate_text(value)
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def extract_year_value(text):
    match = re.search(r"\b(19|20)\d{2}\b", str(text or ""))
    return match.group(0) if match else ""


def title_matches(left, right):
    left = normalize_match_text(left)
    right = normalize_match_text(right)
    if not left or not right:
        return False
    return left == right or left in right or right in left


def split_artist_text(value):
    normalized = normalize_match_text(value)
    if not normalized:
        return []
    parts = re.split(r"\b(?:and|,|;|feat|featuring|ft|with|x)\b", normalized)
    return [part.strip() for part in parts if part.strip()]


def first_present(mapping, keys, default=""):
    for key in keys:
        if key in mapping:
            value = mapping.get(key)
            if value is None:
                continue
            if isinstance(value, str):
                value = value.strip()
            if value != "":
                return value
    return default


def parse_duration_ms(value):
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        number = int(value)
        return number if number > 1000 else number * 1000
    text = str(value).strip()
    if not text:
        return None
    if re.fullmatch(r"\d+", text):
        number = int(text)
        return number if number > 1000 else number * 1000
    match = re.fullmatch(r"(?:(\d+):)?(\d+):(\d+)", text)
    if match:
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)
        return ((hours * 60 + minutes) * 60 + seconds) * 1000
    match = re.fullmatch(r"(\d+):(\d+)", text)
    if match:
        minutes = int(match.group(1))
        seconds = int(match.group(2))
        return (minutes * 60 + seconds) * 1000
    return None


def normalize_import_row_keys(row):
    normalized = {}
    for key, value in row.items():
        normalized[normalize_match_text(str(key))] = value
    return normalized


def coerce_artists(raw):
    if isinstance(raw, list):
        artists = []
        for item in raw:
            if isinstance(item, dict):
                name = first_present(normalize_import_row_keys(item), ["name", "artist", "artist name"], "")
                if name:
                    artists.append(str(name).strip())
            elif item:
                artists.append(str(item).strip())
        return artists
    if isinstance(raw, dict):
        name = first_present(normalize_import_row_keys(raw), ["name", "artist", "artist name"], "")
        return [str(name).strip()] if name else []
    if not raw:
        return []
    return [part.strip() for part in re.split(r"\s*(?:,|;|/|\band\b|\bfeat\.?\b|\bfeaturing\b|\bft\.?\b)\s*", str(raw)) if part.strip()]


def imported_track_from_row(index, row, fallback_collection=""):
    normalized = normalize_import_row_keys(row)
    title = str(first_present(normalized, ["track name", "song name", "title", "name", "track"], "")).strip()
    if not title:
        return None
    artists = coerce_artists(
        first_present(
            normalized,
            [
                "artist names",
                "artist name s",
                "artist name",
                "artist",
                "artists",
                "album artist names",
                "album artist name s",
                "album artist name",
                "album artist",
            ],
            "",
        )
    )
    collection = str(
        first_present(
            normalized,
            ["playlist name", "playlist", "collection", "source collection"],
            fallback_collection,
        )
    ).strip()
    album = str(first_present(normalized, ["album name", "album", "release"], "")).strip()
    isrc = str(first_present(normalized, ["isrc"], "")).strip()
    source_url = str(first_present(normalized, ["spotify url", "track url", "url"], "")).strip()
    source_id = str(first_present(normalized, ["spotify uri", "track uri", "uri", "track id", "id"], "")).strip()
    year = extract_year_value(first_present(normalized, ["release date", "album release date", "year", "release year", "date"], ""))
    duration_ms = parse_duration_ms(
        first_present(
            normalized,
            ["track duration ms", "duration ms", "duration_ms", "duration", "track duration"],
            "",
        )
    )
    return ImportedTrack(index, title, artists, collection, album, isrc, year, duration_ms, source_url, source_id)


def imported_track_from_json_item(index, item, fallback_collection=""):
    if not isinstance(item, dict):
        return None
    row = dict(item.get("track", item))
    if "artists" in item and "artists" not in row:
        row["artists"] = item["artists"]
    if "album" in item and isinstance(item["album"], dict):
        row.setdefault("album", first_present(normalize_import_row_keys(item["album"]), ["name", "title"], ""))
        row.setdefault("release_date", first_present(normalize_import_row_keys(item["album"]), ["release date", "release_date", "year"], ""))
    return imported_track_from_row(index, row, fallback_collection=fallback_collection)


def load_imported_tracks(path):
    import_path = Path(path)
    if not import_path.exists():
        sys.exit(f"Import file not found: {import_path}")
    fallback_collection = import_path.stem
    tracks = []
    if import_path.suffix.lower() == ".csv":
        with import_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for index, row in enumerate(reader, start=1):
                track = imported_track_from_row(index, row, fallback_collection=fallback_collection)
                if track:
                    tracks.append(track)
    elif import_path.suffix.lower() == ".json":
        raw = json.loads(import_path.read_text(encoding="utf-8"))
        items = raw if isinstance(raw, list) else raw.get("tracks") or raw.get("items") or raw.get("songs") or []
        for index, item in enumerate(items, start=1):
            track = imported_track_from_json_item(index, item, fallback_collection=fallback_collection)
            if track:
                tracks.append(track)
    else:
        sys.exit("Import file must be .csv or .json")
    if not tracks:
        sys.exit(f"No usable tracks found in: {import_path}")
    return tracks


def normalize_browser_url(url):
    url = (url or "").strip()
    if not url:
        return url
    if re.match(r"^[a-z][a-z0-9+.-]*://", url, re.I):
        return url
    if re.match(r"^[a-z0-9.-]+\.[a-z]{2,}([/:?#].*)?$", url, re.I):
        return f"https://{url}"
    return url


def open_in_default_browser(url):
    url = normalize_browser_url(url)
    if not url:
        return False
    try:
        return webbrowser.open(url)
    except Exception:
        return False


def save_session(session):
    save_json_file(
        SESSION_FILE,
        {
            "token_type": session.token_type,
            "access_token": session.access_token,
            "refresh_token": session.refresh_token,
            "expiry_time": str(session.expiry_time) if session.expiry_time else None,
        },
    )


def load_session():
    session = tidalapi.Session()
    if SESSION_FILE.exists():
        data = load_json_file(SESSION_FILE, {})
        try:
            loaded = session.load_oauth_session(
                token_type=data.get("token_type"),
                access_token=data.get("access_token"),
                refresh_token=data.get("refresh_token"),
                expiry_time=data.get("expiry_time"),
            )
            if loaded and session.check_login():
                ok("Tidal session resumed")
                return session
        except Exception:
            pass

    console.print(Panel("No saved session found.\nA login link will open in your browser.", title="[bold yellow]Login Required[/]"))
    login, future = session.login_oauth()
    login_url = normalize_browser_url(login.verification_uri_complete)
    if open_in_default_browser(login_url):
        ok("Opened Tidal login in your browser")
    else:
        console.print(login_url)
    with console.status("[yellow]Waiting for login...[/]", spinner="dots"):
        future.result()
    if not session.check_login():
        sys.exit("Login failed.")
    save_session(session)
    ok("Logged in and saved session")
    return session


def get_album_artist(track):
    album = getattr(track, "album", None)
    if not album:
        return ""
    album_artist = getattr(album, "artist", None)
    if album_artist and getattr(album_artist, "name", None):
        return album_artist.name
    album_artists = getattr(album, "artists", None) or []
    return ", ".join(artist.name for artist in album_artists if getattr(artist, "name", None))


def get_track_year(track):
    return extract_year_value(
        getattr(track, "tidal_release_date", None)
        or getattr(track, "stream_start_date", None)
        or getattr(getattr(track, "album", None), "release_date", None)
        or getattr(getattr(track, "album", None), "stream_start_date", None)
        or getattr(getattr(track, "album", None), "year", None)
    )


def get_track_duration_ms(track):
    duration = getattr(track, "duration", None)
    if duration in (None, ""):
        return None
    try:
        return int(float(duration) * 1000)
    except Exception:
        return None


def get_track_artists_for_match(track):
    artists = []
    for artist in getattr(track, "artists", []) or []:
        name = normalize_match_text(getattr(artist, "name", ""))
        if name:
            artists.extend(split_artist_text(name))
    album_artist = normalize_match_text(get_album_artist(track))
    if album_artist:
        artists.extend(split_artist_text(album_artist))
    return [name for name in artists if name]


def has_artist_overlap(source_artists, track):
    left = []
    for artist in source_artists:
        left.extend(split_artist_text(artist))
    right = get_track_artists_for_match(track)
    return bool(left and right and any(a == b or a in b or b in a for a in left for b in right))


def detect_edition_flags(value):
    normalized = normalize_match_text(value)
    if not normalized:
        return set()
    tags = set()
    keywords = {
        "live": "live",
        "remaster": "remaster",
        "remastered": "remaster",
        "acoustic": "acoustic",
        "karaoke": "karaoke",
        "instrumental": "instrumental",
        "version": "version",
        "reprise": "reprise",
        "radio edit": "radio_edit",
        "edit": "edit",
    }
    for key, tag in keywords.items():
        if key in normalized:
            tags.add(tag)
    return tags


def to_track_like(value):
    if isinstance(value, dict):
        converted = {}
        for key, item in value.items():
            converted[key] = to_track_like(item)
        return SimpleNamespace(**converted)
    if isinstance(value, list):
        return [to_track_like(item) for item in value]
    return value


def ensure_track_details(session, track, lookup_cache=None):
    track_id = getattr(track, "id", None)
    if not track_id:
        return track

    has_name = bool(getattr(track, "name", ""))
    album = getattr(track, "album", None)
    has_album = bool(getattr(album, "name", "")) if album else False
    has_quality = bool(getattr(track, "audio_quality", ""))
    if has_name and has_album and has_quality:
        return track

    if lookup_cache is not None:
        cached = lookup_cache.setdefault("track", {}).get(track_id)
        if cached is not None:
            return cached

    try:
        detailed = session.track(track_id)
    except Exception:
        detailed = track

    if lookup_cache is not None:
        lookup_cache.setdefault("track", {})[track_id] = detailed
    return detailed


def is_compilation_album_name(name):
    normalized = normalize_match_text(name)
    if not normalized:
        return False
    compilation_words = {
        "greatest hits",
        "best of",
        "essentials",
        "hits",
        "mix",
        "playlist",
        "karaoke",
        "tribute",
        "music hit",
        "pop",
        "songs",
        "temazos",
        "specials",
        "road trip",
        "getaway",
        "usa",
        "bangers",
        "break",
        "summer",
        "country",
        "only",
        "na",
    }
    return any(word in normalized for word in compilation_words)


def album_match_flags(source_track, tidal_track):
    source_album_norm = normalize_match_text(source_track.album)
    tidal_album_norm = normalize_match_text(getattr(getattr(tidal_track, "album", None), "name", "") or "")
    if not source_album_norm or not tidal_album_norm:
        return False, False
    album_exact = source_album_norm == tidal_album_norm
    album_close = album_exact or source_album_norm in tidal_album_norm or tidal_album_norm in source_album_norm
    return album_exact, album_close


def title_similarity_flags(source_track, tidal_track):
    source_title_norm = normalize_match_text(source_track.title)
    tidal_title_norm = normalize_match_text(getattr(tidal_track, "name", "") or "")
    if not source_title_norm or not tidal_title_norm:
        return False, False
    title_exact = source_title_norm == tidal_title_norm
    title_close = title_exact or source_title_norm in tidal_title_norm or tidal_title_norm in source_title_norm
    return title_exact, title_close


def source_looks_like_single(source_track):
    source_title_norm = normalize_match_text(source_track.title)
    source_album_norm = normalize_match_text(source_track.album)
    if not source_title_norm or not source_album_norm:
        return False
    return source_title_norm == source_album_norm or source_title_norm in source_album_norm or source_album_norm in source_title_norm


def resolve_transfer_mode(value, fallback="accurate"):
    mode = str(value or fallback).strip().lower()
    return mode if mode in {"fast", "accurate"} else fallback


def release_preference_score(source_track, tidal_track):
    score = 0
    tidal_title = getattr(tidal_track, "name", "") or ""
    tidal_album = getattr(getattr(tidal_track, "album", None), "name", "") or ""
    tidal_album_norm = normalize_match_text(tidal_album)
    source_title_norm = normalize_match_text(source_track.title)
    album_exact, album_close = album_match_flags(source_track, tidal_track)
    title_exact, title_close = title_similarity_flags(source_track, tidal_track)
    source_flags = detect_edition_flags(f"{source_track.title} {source_track.album}")
    tidal_flags = detect_edition_flags(f"{tidal_title} {tidal_album} {getattr(tidal_track, 'version', '')}")

    if album_exact:
        score += 160
    elif album_close:
        score += 90

    if source_looks_like_single(source_track):
        if title_exact and tidal_album_norm and (tidal_album_norm == source_title_norm or tidal_album_norm in source_title_norm or source_title_norm in tidal_album_norm):
            score += 120
        elif not title_exact and title_close:
            score -= 80
        elif not album_close:
            score -= 35

    if tidal_flags and not source_flags:
        score -= 90
    elif tidal_flags and source_flags != tidal_flags:
        score -= 35

    if is_compilation_album_name(tidal_album):
        score -= 120

    version_text = normalize_match_text(getattr(tidal_track, "version", "") or "")
    if version_text and not source_flags:
        score -= 50

    return score


def should_keep_isrc_pool(source_track, ranked_candidates):
    if not ranked_candidates:
        return False

    top = ranked_candidates[:4]
    if any(album_match_flags(source_track, track)[1] for _, track in top):
        return True

    non_compilations = [track for _, track in top if not is_compilation_album_name(getattr(getattr(track, "album", None), "name", "") or "")]
    if non_compilations:
        return True

    return False


def score_import_match(source_track, tidal_track, transfer_mode="accurate"):
    score = 0
    reasons = []
    tidal_title = getattr(tidal_track, "name", "")
    tidal_album = getattr(getattr(tidal_track, "album", None), "name", "") or ""
    tidal_year = get_track_year(tidal_track)
    source_year = source_track.year

    source_title_norm = normalize_match_text(source_track.title)
    tidal_title_norm = normalize_match_text(tidal_title)
    source_album_norm = normalize_match_text(source_track.album)
    tidal_album_norm = normalize_match_text(tidal_album)
    source_isrc_norm = normalize_match_text(source_track.isrc)
    tidal_isrc_norm = normalize_match_text(getattr(tidal_track, "isrc", ""))

    isrc_exact = bool(source_isrc_norm and tidal_isrc_norm and source_isrc_norm == tidal_isrc_norm)
    title_ok = title_matches(source_track.title, tidal_title)
    artist_ok = has_artist_overlap(source_track.artists, tidal_track)

    album_exact = False
    album_close = False
    if source_album_norm and tidal_album_norm:
        album_exact = source_album_norm == tidal_album_norm
        album_close = album_exact or source_album_norm in tidal_album_norm or tidal_album_norm in source_album_norm

    if isrc_exact:
        score += 260
        reasons.append("ISRC exact")

    if title_ok:
        if source_title_norm and tidal_title_norm and source_title_norm == tidal_title_norm:
            score += 110
            reasons.append("title exact")
        else:
            score += 75
            reasons.append("title close")
    else:
        score -= 160

    if artist_ok:
        score += 95
        reasons.append("artist overlap")
    else:
        score -= 110

    if source_album_norm:
        if album_exact:
            score += 220
            reasons.append("album exact")
        elif album_close:
            score += 140
            reasons.append("album close")
        else:
            score -= 80

    if isrc_exact and source_album_norm and not album_close:
        score -= 120
        reasons.append("ISRC album mismatch")

    if source_year and tidal_year:
        if source_year == tidal_year:
            score += 25
        else:
            try:
                if abs(int(source_year) - int(tidal_year)) == 1:
                    score += 5
            except Exception:
                pass

    source_duration = source_track.duration_ms
    tidal_duration = get_track_duration_ms(tidal_track)
    if source_duration and tidal_duration:
        delta = abs(source_duration - tidal_duration)
        if delta <= 2000:
            score += 25
        elif delta <= 5000:
            score += 12
        elif delta >= 20000:
            score -= 20

    source_flags = detect_edition_flags(f"{source_track.title} {source_track.album}")
    tidal_flags = detect_edition_flags(f"{tidal_title} {tidal_album} {getattr(tidal_track, 'version', '')}")
    mismatch_flags = source_flags.symmetric_difference(tidal_flags)
    if mismatch_flags:
        if not source_flags:
            score -= min(120, len(mismatch_flags) * 40)
        else:
            score -= min(60, len(mismatch_flags) * 18)

    if source_album_norm and source_album_norm != tidal_album_norm:
        normalized_album = tidal_album_norm
        if is_compilation_album_name(normalized_album):
            score -= 90
            reasons.append("compilation penalty")

    transfer_mode = resolve_transfer_mode(transfer_mode)
    if transfer_mode == "accurate":
        release_bonus = release_preference_score(source_track, tidal_track)
        score += release_bonus
        if release_bonus > 0:
            reasons.append("release preference")
        elif release_bonus < 0:
            reasons.append("release penalty")
    else:
        if album_exact:
            score += 40
        elif album_close:
            score += 20
        if is_compilation_album_name(tidal_album):
            score -= 20

    return score, reasons


def search_tidal_candidates(session, source_track, lookup_cache=None, transfer_mode="accurate"):
    transfer_mode = resolve_transfer_mode(transfer_mode)
    lookup_cache = lookup_cache or {"isrc": {}, "search": {}, "track": {}}
    candidates = {}

    if source_track.isrc:
        isrc_key = normalize_match_text(source_track.isrc)
        items = lookup_cache["isrc"].get(isrc_key)
        if items is None:
            try:
                results = session.request.request(
                    "GET",
                    "tracks",
                    params={"isrc": source_track.isrc, "countryCode": session.country_code, "limit": 10},
                ).json()
                items = results.get("items", [])
            except Exception:
                items = []
            lookup_cache["isrc"][isrc_key] = items

        raw_candidates = []
        for item in items:
            track = to_track_like(item)
            track = ensure_track_details(session, track, lookup_cache=lookup_cache)
            raw_score, _ = score_import_match(source_track, track, transfer_mode=transfer_mode)
            raw_candidates.append((raw_score, track))

        raw_candidates.sort(
            key=lambda row: (
                -row[0],
                -get_quality_rank(row[1]),
                -(getattr(row[1], "popularity", 0) or 0),
                getattr(row[1], "id", 0) or 0,
            )
        )

        if transfer_mode == "fast" or should_keep_isrc_pool(source_track, raw_candidates):
            for raw_score, track in raw_candidates[:4]:
                track_id = getattr(track, "id", None)
                if track_id and track_id not in candidates:
                    candidates[track_id] = track

    queries = []
    primary_artist = source_track.artists[0] if source_track.artists else ""
    if source_track.title and primary_artist and source_track.album:
        queries.append(f"{source_track.title} {primary_artist} {source_track.album}")
    if source_track.title and primary_artist:
        queries.append(f"{source_track.title} {primary_artist}")
        queries.append(f"{primary_artist} {source_track.title}")
    if primary_artist and source_track.album:
        queries.append(f"{primary_artist} {source_track.album}")
    if source_track.title:
        queries.append(source_track.title)

    transliterated_title = transliterate_text(source_track.title)
    transliterated_album = transliterate_text(source_track.album)
    if transliterated_title and transliterated_title != str(source_track.title).casefold():
        if primary_artist and transliterated_album:
            queries.append(f"{transliterated_title} {primary_artist} {transliterated_album}")
        if primary_artist:
            queries.append(f"{transliterated_title} {primary_artist}")
            queries.append(f"{primary_artist} {transliterated_title}")
        queries.append(transliterated_title)

    for index, query in enumerate(queries):
        search_key = normalize_match_text(query)
        tracks = lookup_cache["search"].get(search_key)
        if tracks is None:
            try:
                results = session.search(query, [tidalapi.Track], limit=6 if transfer_mode == "fast" else 12)
                tracks = results.get("tracks", [])
            except Exception:
                tracks = []
            lookup_cache["search"][search_key] = tracks

        for track in tracks:
            track_id = getattr(track, "id", None)
            if track_id and track_id not in candidates:
                candidates[track_id] = track

        if index == 0:
            if transfer_mode == "fast" and len(candidates) >= 3:
                break
            strong_found = False
            for candidate in candidates.values():
                album_exact, album_close = album_match_flags(source_track, candidate)
                if album_exact or (album_close and not is_compilation_album_name(getattr(getattr(candidate, "album", None), "name", "") or "")):
                    strong_found = True
                    break
            if strong_found:
                break

    return list(candidates.values())


def classify_match_confidence(score, gap):
    if score >= 240 and gap >= 25:
        return "high"
    if score >= 160 and gap >= 15:
        return "medium"
    return "low"


def get_quality_rank(track):
    quality = str(getattr(track, "audio_quality", "") or "").upper()
    ranks = {
        "HI_RES": 5,
        "HI_RES_LOSSLESS": 5,
        "MAX": 5,
        "LOSSLESS": 4,
        "HIGH": 3,
        "LOW": 2,
    }
    return ranks.get(quality, 1)


def equivalent_candidate_key(track):
    return (
        normalize_match_text(getattr(track, "isrc", "")),
        normalize_match_text(getattr(track, "name", "")),
        normalize_match_text(getattr(getattr(track, "artist", None), "name", "")),
        normalize_match_text(getattr(getattr(track, "album", None), "name", "")),
    )


def collapse_duplicate_candidates(scored):
    grouped = {}
    order = []
    for score, candidate, reasons in scored:
        key = equivalent_candidate_key(candidate)
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append((score, candidate, reasons))

    collapsed = []
    duplicate_keys = set()
    for key in order:
        group = grouped[key]
        if len(group) > 1:
            duplicate_keys.add(key)
        group.sort(
            key=lambda row: (
                -row[0],
                -get_quality_rank(row[1]),
                -(getattr(row[1], "popularity", 0) or 0),
                getattr(row[1], "id", 0) or 0,
            )
        )
        collapsed.append(group[0])
    return collapsed, duplicate_keys


def resolve_import_match(session, source_track, lookup_cache=None, transfer_mode="accurate"):
    candidates = search_tidal_candidates(session, source_track, lookup_cache=lookup_cache, transfer_mode=transfer_mode)
    if not candidates:
        return None
    scored = []
    for candidate in candidates:
        score, reasons = score_import_match(source_track, candidate, transfer_mode=transfer_mode)
        scored.append((score, candidate, reasons))

    scored.sort(
        key=lambda row: (
            -row[0],
            -get_quality_rank(row[1]),
            -(getattr(row[1], "popularity", 0) or 0),
            getattr(row[1], "id", 0) or 0,
        )
    )
    collapsed, duplicate_keys = collapse_duplicate_candidates(scored)
    best_score, best_track, reasons = collapsed[0]
    second_score = collapsed[1][0] if len(collapsed) > 1 else None
    gap = best_score - second_score if second_score is not None else best_score

    best_key = equivalent_candidate_key(best_track)
    if best_key in duplicate_keys:
        gap = max(gap, 25)
        if "duplicate quality edition" not in reasons:
            reasons = list(reasons) + ["duplicate quality edition"]

    alternatives = []
    for score, candidate, _ in scored[:3]:
        alternatives.append({
            "tidal_id": getattr(candidate, "id", None),
            "title": getattr(candidate, "name", ""),
            "artist": getattr(getattr(candidate, "artist", None), "name", ""),
            "album": getattr(getattr(candidate, "album", None), "name", ""),
            "score": score,
            "audio_quality": getattr(candidate, "audio_quality", ""),
        })
    return {
        "track": best_track,
        "score": best_score,
        "gap": gap,
        "confidence": classify_match_confidence(best_score, gap),
        "reasons": reasons,
        "alternatives": alternatives,
    }


def chunked(items, size):
    for index in range(0, len(items), size):
        yield items[index:index + size]


def build_output_path(args, settings):
    output_name = args.output or "csv2tidal_report.json"
    output_path = Path(output_name)
    if output_path.is_absolute():
        return output_path
    base_dir = Path.cwd()
    if settings.output_dir:
        configured_dir = Path(settings.output_dir).expanduser()
        configured_dir.mkdir(parents=True, exist_ok=True)
        base_dir = configured_dir
    return base_dir / output_path


def track_report_row(source_track, match):
    if not match:
        return {
            "source_index": source_track.index,
            "source_collection": source_track.collection,
            "source_title": source_track.title,
            "source_artists": source_track.artists,
            "source_album": source_track.album,
            "source_isrc": source_track.isrc,
            "matched": False,
            "confidence": "none",
        }
    tidal_track = match["track"]
    return {
        "source_index": source_track.index,
        "source_collection": source_track.collection,
        "source_title": source_track.title,
        "source_artists": source_track.artists,
        "source_album": source_track.album,
        "source_isrc": source_track.isrc,
        "matched": True,
        "confidence": match["confidence"],
        "score": match["score"],
        "score_gap": match["gap"],
        "reasons": match["reasons"],
        "tidal_id": getattr(tidal_track, "id", None),
        "tidal_title": getattr(tidal_track, "name", ""),
        "tidal_artist": getattr(getattr(tidal_track, "artist", None), "name", ""),
        "tidal_album": getattr(getattr(tidal_track, "album", None), "name", ""),
        "tidal_isrc": getattr(tidal_track, "isrc", ""),
        "alternatives": match["alternatives"],
    }


def print_review_candidates(results, limit=8):
    review_rows = [row for row in results if row.get("matched") and not row.get("accepted_for_transfer")]
    if not review_rows:
        return

    console.print("[bold yellow]Needs Review[/]")
    console.print()
    for row in review_rows[:limit]:
        artists = ", ".join(row.get("source_artists", [])) or "Unknown artist"
        collection = row.get("source_collection") or "-"
        reason = f"score {row.get('score', '-')} / gap {row.get('score_gap', '-')}"
        console.print(f"  [yellow]{row['source_title']}[/] [dim]-[/] {artists}")
        console.print(f"    [dim]Collection:[/] {collection}  [dim]|[/]  [dim]Album:[/] {row.get('source_album', '') or '-'}  [dim]|[/]  [dim]{reason}[/]")
    console.print()


def print_summary(summary, output_path, elapsed, results=None):
    console.print()
    minutes, seconds = divmod(int(elapsed), 60)
    time_str = f"{minutes}m {seconds}s" if minutes else f"{seconds}s"
    table = Table.grid(padding=(0, 3))
    table.add_column(justify="center")
    table.add_column(justify="center")
    table.add_column(justify="center")
    table.add_column(justify="center")
    table.add_column(justify="center")
    table.add_row(
        Text.assemble(("Total\n", DIM), (str(summary["total"]), "bold white")),
        Text.assemble(("Matched\n", DIM), (str(summary["matched"]), f"bold {SUCCESS}")),
        Text.assemble(("Accepted\n", DIM), (str(summary["accepted"]), f"bold {ACCENT}")),
        Text.assemble(("Transferred\n", DIM), (str(summary["transferred"]), f"bold {SUCCESS}")),
        Text.assemble(("Failed\n", DIM), (str(summary["failed"]), f"bold {ERR if summary['failed'] else DIM}")),
    )
    console.print(Panel(Align.center(table), border_style=ACCENT, padding=(1, 3), expand=False, title=f"[bold]{time_str}[/]"))
    if output_path:
        console.print(f"  File Saved to [bold cyan]{output_path}[/]")
    if summary.get("cancelled"):
        console.print("  [yellow]Transfer cancelled by user.[/]")
    if summary["low_confidence"]:
        if output_path:
            console.print(f"  [yellow]{summary['low_confidence']} lower-confidence match(es) were still saved in the JSON report.[/]")
        else:
            console.print(f"  [yellow]{summary['low_confidence']} lower-confidence match(es) were transferred using the current mode.[/]")
    console.print()


def cancel_requested():
    if os.name != "nt":
        return False
    try:
        while msvcrt.kbhit():
            key = msvcrt.getwch()
            if key == " ":
                return True
        return False
    except Exception:
        return False


def run_transfer(args, settings, session):
    start_time = time.time()
    imported_tracks = load_imported_tracks(args.import_file)
    output_path = build_output_path(args, settings) if settings.generate_report or args.output else None
    threshold = DEFAULT_MATCH_THRESHOLD
    transfer_mode = resolve_transfer_mode(getattr(args, "transfer_mode", ""), settings.transfer_mode)
    lookup_cache = {"isrc": {}, "search": {}, "track": {}}
    results = []
    summary = {"total": len(imported_tracks), "matched": 0, "accepted": 0, "transferred": 0, "failed": 0, "low_confidence": 0, "cancelled": False}

    with Progress(
        SpinnerColumn(style=ACCENT),
        TextColumn("[bold white]{task.description}"),
        BarColumn(bar_width=40, style="cyan", complete_style=ACCENT),
        TextColumn("[cyan]{task.completed}[/][dim]/{task.total}[/]"),
        TimeElapsedColumn(),
        TextColumn("[dim]Press Space to cancel[/]"),
        console=console,
    ) as progress:
        task = progress.add_task("Matching imported tracks", total=len(imported_tracks))
        for source_track in imported_tracks:
            if cancel_requested():
                summary["cancelled"] = True
                break
            progress.update(task, description=f"[white]{source_track.title[:36]:<36}[/]")
            match = resolve_import_match(session, source_track, lookup_cache=lookup_cache, transfer_mode=transfer_mode)
            row = track_report_row(source_track, match)
            if match:
                summary["matched"] += 1
                accepted = match["score"] >= threshold
                row["accepted_for_transfer"] = accepted
                if accepted:
                    summary["accepted"] += 1
                else:
                    summary["low_confidence"] += 1
            else:
                row["accepted_for_transfer"] = False
                summary["failed"] += 1
            results.append(row)
            progress.advance(task)

    accepted_ids = [str(row["tidal_id"]) for row in results if row.get("accepted_for_transfer") and row.get("tidal_id")]
    if accepted_ids and not summary["cancelled"]:
        user = session.user
        if args.transfer_favorites:
            favorites = tidalapi.Favorites(session, user.id)
            for batch in chunked(accepted_ids, 100):
                favorites.add_track(batch)
                summary["transferred"] += len(batch)
        if args.transfer_playlist:
            playlist = user.create_playlist(args.transfer_playlist, "Imported by csv2tidal")
            for batch in chunked(accepted_ids, 100):
                playlist.add(batch)
            summary["transferred"] = len(accepted_ids)

    if output_path:
        save_json_file(output_path, {
            "source_file": str(Path(args.import_file).resolve()),
            "threshold": threshold,
            "transfer_mode": transfer_mode,
            "dry_run": False,
            "transfer_favorites": bool(args.transfer_favorites),
            "transfer_playlist": args.transfer_playlist or "",
            "summary": summary,
            "results": results,
        })
    save_session(session)
    return output_path, summary, results, time.time() - start_time


def build_parser():
    parser = argparse.ArgumentParser(description="Transfer Spotify-style track exports to Tidal.")
    parser.add_argument("--import-file")
    parser.add_argument("--output", default="")
    parser.add_argument("--transfer-mode", default="")
    parser.add_argument("--transfer-favorites", action="store_true")
    parser.add_argument("--transfer-playlist", default="")
    parser.add_argument("--set-output-dir", default="")
    parser.add_argument("--settings", action="store_true")
    parser.add_argument("--logout", action="store_true")
    return parser


def main(argv=None):
    migrate_app_data()
    parser = build_parser()
    args = parser.parse_args(argv)
    print_header()
    settings = load_settings()

    if args.set_output_dir:
        settings.output_dir = args.set_output_dir.strip()
        save_settings(settings)
        ok(f"Saved output directory: {settings.output_dir}")

    if args.logout and not args.import_file:
        logout_result = clear_saved_session()
        if logout_result is True:
            ok("Saved Tidal session removed.")
        elif logout_result is False:
            warn("No saved Tidal session was found.")
        else:
            fail(f"Could not remove saved session: {SESSION_FILE}")
        console.print()
        return 0

    if args.settings and not args.import_file:
        clear_screen()
        print_header()
        configure_settings(settings)
        return 0

    if not args.import_file:
        session = None
        while True:
            clear_screen()
            print_header()
            print_home_screen(settings)
            try:
                choice = console.input("  [cyan]Choose an option[/]: ").strip().lower()
            except KeyboardInterrupt:
                return 0
            console.print()
            if choice in {"q", "quit", "exit", "x", "0"}:
                return 0
            if choice in {"4", "h", "help"}:
                clear_screen()
                print_header()
                print_usage()
                try:
                    console.input("  [cyan]Press Enter to return to the menu[/]")
                except KeyboardInterrupt:
                    return 0
                continue
            if choice in {"2", "s", "settings"}:
                clear_screen()
                print_header()
                settings = configure_settings(settings)
                continue
            if choice in {"3", "logout", "signout"}:
                clear_screen()
                print_header()
                logout_result = clear_saved_session()
                if logout_result is True:
                    ok("Saved Tidal session removed.")
                    session = None
                elif logout_result is False:
                    warn("No saved Tidal session was found.")
                else:
                    fail(f"Could not remove saved session: {SESSION_FILE}")
                time.sleep(1)
                continue
            if choice not in {"1", "t", "transfer"}:
                warn("Invalid option.")
                time.sleep(1)
                continue

            clear_screen()
            print_header()
            run_args = prompt_transfer_args(settings)
            if not run_args:
                continue
            if session is None:
                session = load_session()
                console.print()
            output_path, summary, results, elapsed = run_transfer(run_args, settings, session)
            clear_screen()
            print_header()
            print_summary(summary, output_path, elapsed, results=results)
            try:
                console.input("  [cyan]Press Enter to return to the menu[/]")
            except KeyboardInterrupt:
                return 0
        return 0

    try:
        session = load_session()
        output_path, summary, results, elapsed = run_transfer(args, settings, session)
        print_summary(summary, output_path, elapsed, results=results)
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(0)



