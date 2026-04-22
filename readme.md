# csv2tidal

`csv2tidal` is a menu-driven desktop CLI app that transfers Exportify CSV playlists to TIDAL with smarter matching than generic playlist migration tools.

The goal of this project is simple: do not just find the same song title, find the correct release.

## Why This Exists

Most transfer tools can match the correct song but still attach the wrong album, compilation release, cover art, or edition. That is the exact problem `csv2tidal` is designed to reduce.

This project gives stronger weight to:

- track title
- artist name
- album name
- ISRC
- release context
- version differences like acoustic, remix, live, deluxe, and compilation releases

So when a track exists on multiple TIDAL releases, `csv2tidal` tries to choose the most accurate one instead of blindly accepting the first result.

## Features

- Menu-driven interface
- Import Exportify CSV files directly
- Windows file picker support
- Transfer to TIDAL favorites
- Transfer to a new TIDAL playlist
- Smart duplicate handling for multiple TIDAL release entries
- Fast and Accurate matching modes
- Optional JSON report output
- Quiet `Ctrl+C` handling
- Press `Space` to cancel matching while a transfer is running

## Requirements

Before using `csv2tidal`, you need:

- Python 3.9 or newer
- a TIDAL account
- a playlist CSV exported in Exportify format
- access to [Exportify](https://exportify.app/) to generate the CSV file

## Matching Logic

`csv2tidal` does not rely on a single field.

It compares a combination of:

- ISRC
- title
- artist
- album
- year
- duration

It also penalizes bad matches such as:

- compilations
- karaoke releases
- acoustic versions
- remix versions
- live versions
- deluxe or repackage mismatches

This helps keep metadata more accurate after transfer.

## Transfer Modes

### Fast

Use this when speed matters more and the playlist is straightforward.

- fewer checks
- quicker matching
- good for large transfers

### Accurate

Use this when album/version correctness matters more.

- stricter album-aware matching
- stronger penalties for wrong editions
- better for important playlists

## How It Works

1. Export your Spotify playlist CSV using [Exportify](https://exportify.app/)
2. Open `csv2tidal`
3. Choose the CSV file
4. Choose whether to send tracks to TIDAL favorites or a TIDAL playlist
5. Let the app match and transfer the tracks

By default in the transfer menu:

- pressing `Enter` selects `Playlist`
- the CSV filename is used as the default playlist name

## Installation

From PyPI:

```bash
pip install csv2tidal
```

Run it with:

```bash
csv2tidal
```

## Project Structure

```text
tidal-transfer/
+- app.py
+- pyproject.toml
+- README.md
+- LICENSE
+- github-readme/
   +- README.md
```

## Notes

- Exportify CSV from [exportify.app](https://exportify.app/) is the primary supported input format.
- TIDAL login uses OAuth in your browser.
- Session and settings are stored locally for reuse.
- JSON report generation can be turned on or off in settings.

## Roadmap Ideas

- better review/export tools for unresolved tracks
- richer release-type understanding
- import support for more playlist export formats
- better side-by-side result explanation for hard matches

## Author

Created by Chetan.

## License

This project is licensed under the MIT License.
