# PitchControl export plugin for the Open Fixture Library

An export plugin for the [Open Fixture Library](https://open-fixture-library.org) (OFL, MIT): it adds **PitchControl** to the "Download as…" button of every fixture page. The download is a PitchControl fixture type file (`<manufacturer> <fixture>.json`) with all the DMX modes of the fixture that PitchControl can use. This folder is laid out like an OFL plugin (`plugin.json`, `export.js`, `exportTests/`), so it can be copied into the `plugins/` folder of OFL as it is. It lives here, next to the program it exports for, until Miro submits it (see "Submitting it to OFL").

**Status:** built and tested against OFL `cfcb0c5` (schema 12.6.0), not submitted. No issue or pull request has been opened on OFL.

| File | What |
|---|---|
| `plugin.json` | name, description, links, how to use the file, where it goes (what OFL's plugin page shows) |
| `export.js` | `version` and `exportFixtures(fixtures, options)`: one file per fixture |
| `convert.js` | OFL's fixture JSON → PitchControl's channel modes (a port of `backend/src/pitchcontrol/ofl/convert.py`) |
| `type-file.js` | the whole type file: the name, the kept OFL data, the `source` block (a port of `backend/src/pitchcontrol/ofl/importer.py`) |
| `exportTests/loads-as-fixture-type.js` | the file is a valid PitchControl type: modes, channels, values, ids, the default mode |
| `exportTests/keeps-ofl-fixture.js` | the file keeps the whole OFL fixture (it can be rebuilt from it), every mode names its OFL mode, and OFL's schema is the one the conversion was written for |

## What the plugin does

For every fixture it writes the file that PitchControl's own **File → Import Fixture → Open Fixture Library** would save for that fixture, without needing the app (item 53 of PitchControl's task list made the import, item 55 this plugin):

- every OFL mode that PitchControl can express becomes a **channel mode** with its pixel count (the pixels or pixel groups of its matrix block) and its channel layout: the colour channels (R G B, with a W) become the pixel block, a strobe / shutter channel becomes PitchControl's shutter (the open value and the fastest plain strobe value), the master dimmer is held at full when the mode mixes colours itself, and every other channel (amber, UV, programs, speed, fine channels …) is a constant at its OFL default value. Switching channels are read with the controlling channel at its default. The full rules are the docstring of `convert.js`.
- a mode PitchControl can't express (a dimmer, amber or strobe per pixel, the pixels interleaved with other channels, a hue / CCT layout without a colour block) is **left out**. About 8 % of OFL's fixtures (50 of 648 at this commit) have no usable mode at all: for them **no file is made**. When every fixture of a download is like that (a single fixture, say), the download fails with the reason ("PitchControl can't express any mode of …"); in a download of many fixtures the others are exported and these are missing.
- the file **keeps the OFL data**: OFL's own keys (`shortName`, `categories`, `meta`, `links`, `physical`, `matrix`, `availableChannels`, `templateChannels`, …) under their OFL names, the OFL mode list as `ofl_modes`, the OFL mode each mode came from as `ofl_mode`, and a `source` block (`format: "ofl"`, the fixture's key, name, manufacturer, page, OFL's schema and its version, the licence, `converter` 1 and the original key order). PitchControl shows the links (manual, product page, video) and the origin on its Fixtures page, and can rebuild the OFL fixture from the file. The shape is the docstring of `backend/src/pitchcontrol/ofl/importer.py` in PitchControl.
- the conversion works on OFL's fixture JSON (`fixture.jsonObject`, like OFL's own "Open Fixture Library JSON" plugin), not on the model's classes: the mapping is a port of Python code that works on the JSON, and the kept data has to be the JSON itself. OFL's model embeds the gobo resources of a wheel slot into the JSON; `oflJsonOf` in `type-file.js` puts the resource names back, so the file keeps what is in the repository.
- two fixtures that give the same type name ("LED Bar 240/8" and "LED Bar 240-8") get `-2`, `-3` … in one download (PitchControl compares names without regard to case; the app would ask).

## How the file differs from an import

For a fixture, the file of the plugin and the file PitchControl saves after importing the same OFL JSON are the same, key by key and in the same order, **except for these, all of them**:

| Difference | Why |
|---|---|
| `app_version` (first key of every file the app saves) is not in the plugin's file | it is the version of the app that wrote the file; the plugin isn't the app. The app reads a file without it and stamps it on the next save |
| `source.commit` is not there; the description doesn't end its source with `, commit <hash>` | an online import knows the OFL commit it fetched; the plugin doesn't |
| `source.file` is not there | an import from a file knows its name |
| a number like `1.0` is written `1` | Python and JavaScript write numbers differently; the numbers are equal |
| the order of the keys of an object that has keys like `"1"`, `"2"` (3 fixtures of 598: `matrix.pixelGroups` of `infinity/iw-720-rdm`, `stairville/xbrick-full-colour`, `stairville/xbrick-quad-16x8w-rgbw`) | a JavaScript object lists such keys first, in number order, whatever OFL's file says; the values are the same. (The only place the conversion looks at the order of such keys is a strobe repeated for each pixel group; none of the fixtures does that with such keys.) |
| files written for a fixture whose type name is already used in the same download get `-2` | see above; an import asks instead |

`source.schema_version` is in the plugin's file (the plugin knows OFL's schema version, `12.6.0` today) and, for an online import, in the app's. A file the app saves after importing from a **website download** ("Download as → Open Fixture Library JSON": versioned `$schema`, plus `fixtureKey`, `manufacturerKey` and `oflURL`) has those three keys kept as well, and `source.schema` is the versioned address: that file is another input, it is not what the plugin makes (the plugin starts from the repository's JSON).

## Testing it

The comparison with the Python import is a script in PitchControl's repository, one command from its root (Python with the backend installed: `backend/.venv`, or `pip install -e backend`; Node 26, git and the internet the first time):

```bash
py tools/ofl_plugin_check.py            # the 10 item 50 fixtures and 15 more, then OFL's lint and export tests
py tools/ofl_plugin_check.py --all      # every fixture of the pinned OFL commit (about 650), about 15 seconds
```

The first run fetches OFL at the pinned commit (`OFL_COMMIT` in the script, a shallow fetch into `<temp>/pitchcontrol-ofl-check`) and runs `npm ci` there; `--ofl DIR` uses a checkout of your own (with `npm ci` done), `--ofl-source` fetches from a local clone instead of GitHub. The script copies this folder into `plugins/` of that checkout, rebuilds `plugins.json` with `node cli/build-plugin-data.js`, and takes both out again when it is done: nothing is left modified in OFL, and nothing is ever committed there. It then

1. runs the app's import (`pitchcontrol.ofl.importer.import_fixture`, saved through the `FixtureType` model, the way the app saves a type) and OFL's `node cli/export-fixture.js -p pitch-control` on the same fixtures, and compares the two files: every key, every value, the order of the keys, with the differences above only;
2. loads every exported file through the app's own `FixtureType` model (a warning of the model is a failure) and saves it back: unchanged;
3. checks that the fixtures the app imports nothing from are refused by the plugin with the reason, and that an import *with* a commit and a file name differs from one without in exactly the documented places;
4. runs OFL's own checks of the plugin: `eslint plugins/pitch-control`, `node cli/run-export-test.js -p pitch-control` and that `plugins.json` lists the plugin and its export tests.

Of the ten item 50 fixtures, seven are in OFL; the three written by hand from their manuals (`tools/fixture_sources/`) are copied into the checkout's `fixtures/` for the run (with the `$schema` key OFL's model needs) and taken out again. It prints a report and ends with `PASS` or the first 40 problems (exit code 1). OFL's own commands work in a checkout with the plugin copied in: `node cli/export-fixture.js -p pitch-control cameo/root-par-6.json` (or `-a` for all), `node cli/run-export-test.js -p pitch-control`, `npm run lint:eslint`.

PitchControl's test suite doesn't run this (it needs Node, git and the internet); run it after every change of `backend/src/pitchcontrol/ofl/` and before every release that changes the conversion.

## Keeping it aligned with the Python converter

The conversion exists twice: `backend/src/pitchcontrol/ofl/convert.py` and `importer.py` (the app) and `convert.js` and `type-file.js` (this plugin). They are line-by-line ports, with the Python names in the comments' wording, and they carry one number, the version of the mapping: `CONVERTER_VERSION` in `importer.py` and in `type-file.js`. When the mapping changes:

1. change the Python first (and its tests), then port the same change to `convert.js` / `type-file.js`;
2. bump `CONVERTER_VERSION` in both, and `version` in `export.js`;
3. run `py tools/ofl_plugin_check.py --all`: it has to say `PASS`. A difference it finds is a place where the two disagree; it names the fixture and the key;
4. a change that adds or moves keys of the file also changes the `FixtureType` model's order of fields: `DECLARED_OFL_KEYS` and the object in `buildTypeFile` (`type-file.js`) follow what `FixtureType.model_dump` writes (`config/models.py`);
5. copy the folder into OFL's repository again, if the plugin is already there (a pull request of its own, see below).

Two things the ports rely on: Python's `round` is banker's rounding (`roundHalfEven` in `convert.js`), and `dict` keeps the order of the file where a JavaScript object doesn't for keys like `"1"` (see above).

When OFL changes its fixture schema to a new major version (it has done so eleven times), the export test `keeps-ofl-fixture` fails in OFL's own checks (`SUPPORTED_SCHEMA_MAJOR`), which is the signal to look at the converter first: PitchControl's `OFL_SCHEMA_MAJOR` in `importer.py` is the same number.

## Submitting it to OFL

**This is Miro's step, not an agent's.** OFL's [AI policy](https://github.com/OpenLightingProject/open-fixture-library/blob/master/AI_POLICY.md) allows AI-written code (understand it before you submit it) but asks that **the texts of issues and pull requests are in the contributor's own words**: don't paste texts an AI wrote, and keep them short and plain; grammar and spelling don't matter. OFL's CI also runs AgentScan on new issues and pull requests, which labels suspected bots: write and open both from your own GitHub account. Nothing has been opened yet.

1. **Read** `docs/CONTRIBUTING.md`, `docs/plugins.md` and `AI_POLICY.md` in OFL once more; look through the issues labelled [`new-plugin`](https://github.com/OpenLightingProject/open-fixture-library/issues?q=is%3Aissue+label%3Anew-plugin) to be sure nobody asked for PitchControl before.
2. **Open an issue first**, from the template "New plugin" (title `Add PitchControl Plugin`). Its questions: the software's website (https://pitchcontrol.eu), where fixtures of the format can be downloaded (they can't: PitchControl's fixture types are made by the app and shipped with it; this plugin is how they would be made from OFL), the file type (JSON), whether the format is documented (README of PitchControl, "Fixture types"), whether many fixtures of good quality exist in this format (the ten shipped types, all from OFL or from manuals), and existing work to parse it (the app imports OFL fixtures; the code is MIT). Say that you wrote the plugin and will make the pull request, that it is export only, and that fixtures with no usable mode (about 8 %) get no file. Say what you think in your own words; the points above are what the template asks.
3. **Fork OFL**, branch, copy this folder to `plugins/pitch-control/` (without this `README.md`, which describes PitchControl's side; keep it if OFL's maintainers would like it).
4. In the fork: `npm ci`, then **`npm run build`**. This regenerates `plugins/plugins.json` (the plugin appears in `exportPlugins` with its two export tests) and the other generated files; OFL's CI (`tests/built-files-committed.js`) fails the pull request if the built files are not committed, so **commit what the build changed** in the fork. (In PitchControl's check, `plugins.json` is rebuilt in the temporary checkout only and never committed.)
5. Run OFL's own checks in the fork: `npm run lint:eslint`, `node cli/run-export-test.js -p pitch-control` (the test fixtures), `node cli/export-fixture.js -p pitch-control -a -o /tmp/out`, and `npm run test:built-files-committed`.
6. **Open the pull request** (Draft first is welcome: "You can also create a (draft) pull request if you're not done yet"), link the issue, write the description yourself: what the plugin does, that the same conversion is in PitchControl, how you tested it, and what is left out. OFL's CI then runs the export tests on the test fixtures and comments the result.
7. Afterwards the plugin lives in two places. A later fix in `convert.js` or `type-file.js` goes to both (PitchControl's folder here, and OFL's `plugins/pitch-control/`, as a new pull request), see "Keeping it aligned".

### What OFL's plugin page will show

The page `/about/plugins/pitch-control` of open-fixture-library.org is built from `plugin.json`: the heading **PitchControl Plugin**, "Export plugin version 1.0.0", the description (what PitchControl is, what the plugin writes, that the same conversion is in the app, that the types should be checked against the manual), a list of four links (**Website** https://pitchcontrol.eu/, **Download** https://pitchcontrol.eu/download, **Fixtures documentation** https://pitchcontrol.eu/docs/fixtures-and-rigs, **Source code** https://github.com/hlavamir/PitchControl), the section **Install fixture definitions** ("Browse to the fixture you want to download, then select PitchControl in the Download as… button", then: copy the `.json` files into the `fixtures/types` subdirectory of your PitchControl data folder and restart PitchControl), **File locations** (fixture files in subdirectories are not recognized; per OS the user library: `C:\Users\[user name]\Documents\PitchControl\fixtures\types`, `~/Documents/PitchControl/fixtures/types` on Mac OS and on Linux) and **Additional information** (the data folder can be another folder; a file there wins over a shipped type of the same name). The plugin list `/about/plugins` gets a line "PitchControl" (export), and every fixture page gets **PitchControl** in "Download as…" (a file named like `Cameo ROOT Par 6.json`).

The links `Download` and `Fixtures documentation` point at pages of the website that exist today; the website doesn't mention the plugin or the OFL import yet (the import's docs are on the branch `ofl-import-docs` of the PitchPlease repository, to be merged at the release that ships item 53). Look at the text of `plugin.json` once more before the pull request: the plugin page is the first thing people from OFL's side read about PitchControl.
