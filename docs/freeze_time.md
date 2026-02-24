## Freezing time (debug / testing)

PowerController supports optionally freezing time for debugging or repeatable testing.

On each controller loop iteration, it checks for a file at:

`logs/freeze_time.json`

If the file exists, it reads two fields:

- `freeze_time` (string): an ISO-8601 datetime, e.g. `2026-02-21T12:34:56` (a trailing `Z` is also supported)
- `do_tick` (bool): controls whether time advances

### Example: re-freeze every loop (no ticking)

If `do_tick` is `false`, the controller will re-read the file and apply the freeze *every loop*:

```json
{
	"freeze_time": "2026-02-21T12:34:56",
	"do_tick": false
}
```

### Example: freeze once for the whole run loop (ticking)

If `do_tick` is `true`, the controller starts a *ticking* freeze that applies to the whole `PowerController.run()` loop and it only does this once:

```json
{
	"freeze_time": "2026-02-21T12:34:56",
	"do_tick": true
}
```

"2026-02-21T12:34:56" - will get local timezone added
"2026-02-21T12:34:56+11:00" - will preserve the +11:00 timezone

To stop freezing time, delete `logs/freeze_time.json` and restart the app.