# android-tv-debloat

Debloat an Android TV over the network. One Python file, no dependencies besides `adb`.
Nothing is deleted: packages are disabled for the user, every change is backed up first, and `restore` undoes it.

Built on a TCL Smart TV Pro (Android 11, 2 GB RAM) that froze constantly: TCL ad, telemetry and promo services kept
~440 MB resident and the TV had pushed 5.6 GB through swap in 40 hours.

## Use

On the TV: Settings → System → About → press *Android TV OS build* 7 times, then turn on USB / network debugging
in Developer options.

```bash
brew install --cask android-platform-tools      # or any adb
python3 debloat.py -d 192.168.1.80 scan          # accept the prompt on the TV; read-only
python3 debloat.py apply                         # dry run of the safe tier
python3 debloat.py apply --yes                   # do it (backup written to backups/)
python3 debloat.py apply --also com.tcl.gallery --yes   # safe tier plus chosen optional packages
python3 debloat.py restore                       # undo every apply on this TV
```

`scan` shows each listed package, whether it is off, on, or running and how much RAM it holds.
`apply` also sets UI animations to 0.5x (`--no-tweaks` to skip).

## Lists

`lists/android-tv.json` covers any Android TV; `lists/<brand>.json` is picked by the TV's manufacturer.
Two tiers: `safe` (ads, telemetry, promos, apps a TV cannot use) and `optional` (real features you may not use).
A package not in a list is never touched. Pull requests for other brands are welcome; please say which model you tested.

## Tests

```bash
python3 -m unittest test_debloat
```

## License

MIT
