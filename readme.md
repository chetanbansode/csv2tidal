# csv2tidal

`csv2tidal` is a standalone CLI for transferring Exportify CSV playlists and similar Spotify-style exports to TIDAL with two matching modes:

- `Fast`: quicker matching for large playlist transfers
- `Accurate`: stronger album and version-aware matching for safer results

## Features

- Import Exportify `.csv` files directly
- Windows file picker in interactive mode
- Match using title, artists, album, ISRC, year, and duration
- Penalize compilation, acoustic, remix, live, and other mismatched editions
- Handle duplicate TIDAL quality editions intelligently
- Transfer accepted matches to TIDAL favorites or a new TIDAL playlist
- Optional JSON report output controlled from settings
- Quiet `Ctrl+C` handling and cancel support during matching

## Install

```bash
pip install csv2tidal
```


## Usage

Launch the interactive app:

```bash
csv2tidal
```

Interactive defaults:
- pressing `Enter` at the transfer destination prompt selects `Playlist`
- the CSV filename is used as the default playlist name
- JSON report creation depends on the saved `Generate JSON report?` setting

## Notes

- Exportify CSV is the primary supported input format.
- The CSV filename is used as the fallback collection or playlist name when the file itself does not include one.
- TIDAL login uses OAuth in your browser and stores a local session for reuse.
- Existing `tidal-transfer` settings and session data are migrated automatically to the new `csv2tidal` app-data folder on first run.
