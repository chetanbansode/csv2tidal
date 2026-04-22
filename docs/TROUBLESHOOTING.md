# Troubleshooting

## The app cannot find my track

Possible reasons:

- the track is not available in the TIDAL API for your region
- the release is indexed differently on TIDAL
- the CSV metadata is too limited or unusual

## The wrong version was added

Try switching to `Accurate` mode. It applies stricter album and edition checks.

## The app says it needs an Exportify CSV

`csv2tidal` currently expects CSV files in Exportify format.
Use [Exportify](https://exportify.app/) to generate the file.

## I pressed Ctrl+C

The app should now exit quietly without printing a traceback.

## I want a report file

Enable `Generate JSON report?` in the app settings.
