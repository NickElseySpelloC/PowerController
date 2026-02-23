# Running and testing the PowerController app

By this stage you should have:

✅ Installed the [prerequisites](installation/prerequisites.md)
✅ Installed and setup your [Shelly device(s)](installation/shelly_setup.md)
✅ Installed the [PowerController application](installation/install_app.md)
✅ Configured the [PowerController application](configuration/index.md)

Eventually, we'll get the app setup for a "production" environment, but initially we recommend running the application manually to check for configuration issues. Open a new terminal window and do the following:


```bash
./launch.sh 
Resolved 87 packages in 19ms
Audited 61 packages in 8ms
[launcher] Starting app with uv run src/main.py ...


PowerController application starting.
Amber API configuration section is missing, disabling Amber pricing.
Pricing manager initialised.
Loaded system state from /Users/nick/scripts/testapp/system_state.json
Initializing power controller from saved state.
Output Network Rack initialised.
Amber API configuration section is missing, disabling Amber pricing.
[shelly] thread starting.
[controller] thread starting.
[webapp] thread starting.
Shelly worker started
Power controller starting main control loop.
Web server listening on http://127.0.0.1:8080
ShellyWorker getting location info for device Network Rack
Completed Shelly device Network Rack information retrieval.
Generating new run plan for output Network Rack
Calculating schedule General run plan for -1 hours (0 priority) with max prices 50.0 / 51.0.
Successfully generated run plan for output Network Rack. Next check at 18:33.
Output Network Rack ON - Run plan dictates that the output should be on. Started at 18:02:08 Energy Used: 0.00Wh Average Price: $0.00c/kWh Total Cost: $0.0000
Logfile trimmed.
```

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


Talk about 
- using launch script
- rebiewing log files
- Troubleshooting 
- reference all the files generated (link to another page)

 T