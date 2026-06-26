# Community triggers

One JSON file per trigger, merged via pull request (the app's **Contribute this
trigger → Open a pull request** button pre-fills one for you). Each file is a
single trigger spec — the same shape as entries in `../baseload_triggers.py`:

```json
{
  "name": "Jane Doe",
  "is_active": false,
  "cooldown_seconds": 3600,
  "tail_patterns": "N12345"
}
```

On boot these are merged into the baseload, so a merged PR ships to everyone on
the next release. Guidelines + field list: see `/CONTRIBUTING.md`. Public
figures / notable / safety-relevant aircraft only; tail/type/squawk rules
travel best (geofences are location-specific).
