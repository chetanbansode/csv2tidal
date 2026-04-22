# FAQ

## Where do I get the CSV file?

Use [Exportify](https://exportify.app/) to export your Spotify playlist as CSV.

## Does this work with Spotify playlist URLs directly?

No. Right now `csv2tidal` is built around CSV input, mainly Exportify CSV files.

## What happens if I press `Enter` at the transfer mode prompt?

The app selects `Playlist` by default and uses the CSV filename as the default playlist name.

## Do I need a TIDAL account?

Yes. You need a TIDAL account to log in and transfer songs.

## What is the difference between Fast and Accurate mode?

- `Fast` is quicker and works well for simpler playlists.
- `Accurate` uses stricter album/version-aware matching.

## Does the app always create a JSON report?

No. JSON report generation depends on the `Generate JSON report` setting.

> [!TIP]
> If you are testing a new playlist, keep JSON reports enabled until you are happy with the transfer results.
