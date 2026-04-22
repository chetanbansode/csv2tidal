# Usage Guide

## Basic Flow

1. Export your Spotify playlist CSV using [Exportify](https://exportify.app/)
2. Launch `csv2tidal`
3. Pick the CSV file
4. Choose whether to transfer to `Favorites` or a `Playlist`
5. Let the app match and transfer the tracks to TIDAL

## Interactive Defaults

- Pressing `Enter` at the destination prompt selects `Playlist`
- The CSV filename is used as the default playlist name
- JSON report creation depends on the saved `Generate JSON report?` setting

## Settings

Available settings inside the app:

- `Generate JSON report?`
- `Output folder`
- `Transfer mode`

## Transfer Modes

### Fast

Use this when you want quicker transfers for large playlists.

### Accurate

Use this when album/version correctness matters more than speed.

## CSV Source

`csv2tidal` currently follows the Exportify CSV format.
Get your CSV from [Exportify](https://exportify.app/).
