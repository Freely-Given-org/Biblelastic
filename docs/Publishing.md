# Publishing the modules

The modules are published as plain files on a web server (no program runs there): the app downloads a catalogue, `index.json`, then the modules it wants.

    target/release/biblelastic publish /srv/www/Freely-Given.org/Software/Biblelastic/modules

`publish` copies the modules from `build/modules` that may be passed on (only those that have changed, each through a temporary name so that nothing is ever
served half-copied), writes their catalogue, and takes away any module there that isn't in it any more. It says which modules it left out because they mayn't
be passed on, and how many have licences that haven't been checked. Freely-Given.org is served by Apache from `/srv/www/Freely-Given.org`, behind Cloudflare.

## The catalogue

`index.json` lists each module with:

| Field | What it is |
| --- | --- |
| `name`, `bytes` | The module's file (`NAME.blm`) and its size |
| `sha256` | Its SHA-256, which changes whenever it does |
| `kind`, `work`, `edition`, `layer`, `title`, `language` | What it is (from its header) |
| `licence`, `copyright`, `attribution` | What may be done with it, and what must be said about where it came from (and any changes made to it) |
| `licence_verified` | Whether someone has checked its licence against its source (not just copied it from there) |

`biblelastic compile` (and `model` and `embed`) write the same catalogue into `build/modules`, for the app to use while it's being developed.

## Rights

Each module's header has its work's rights, from the registry (`pipeline/sources.toml`) by way of the manifest: `module.licence`, `module.copyright`,
`module.attribution` (the registry's `attribution` and `changes`), `module.redistributable`, and `module.licence_verified`.
A layer with rights of its own (e.g., the UBS meanings of the words of the UHB and the SR-GNT) has those; an alignment has its translation's (whose makers made it);
a work's vectors have the work's; and a model has its own (both are MIT), from `[[model]]` in the registry. Publishing leaves out any module whose `redistributable` is false.

So far, by work (each work's other modules have its rights too):

| Licence | Works |
| --- | --- |
| CC0 1.0 | 61 books (from books.freely.giving), and the English thesaurus |
| CC BY-SA 4.0 | OET-RV, OET-LV, UHB, TOSN, TOBD, UBSH (and the UBS meanings), ASBRT, AOSN-ES, AOBD-ES |
| CC BY 4.0 | SR-GNT |
| Public domain | RV1909 |
| MIT | The two models for meaning-based search |

Every work's licence has been checked against its source (26 November 2026), except the thesaurus's and the two models' (`licence_verified` in the registry:
the models' are under `[[model]]`, which the ingest passes to `biblelastic model`).
[Licences.md](Licences.md) gathers what each source says, with the questions that are still open.
CC BY and CC BY-SA need their attribution shown: the app shows each work's copyright, licence, and attribution under its contents, and all of them together in
*Licences and sources* (in the Library).

## Updates, and caches

The app remembers the SHA-256 of each module that it installs. When the catalogue gives a different one, the module is shown as *Update available*,
and *Install and update all* fetches the changed modules with the missing ones. (A module installed before this was recorded is compared by its size instead.)

Cloudflare and browsers may cache what the server sends (Freely-Given.org's pages come with `cache-control: max-age=7200`). So the app asks for each module
by an address that includes the start of its SHA-256 (e.g., `OET-RV.text.blm?v=8c110bde59ed4d7c`), which a changed module can't share with an old copy,
and for the catalogue by an address that's different every time (`index.json?t=…`). Apache ignores the queries, so nothing needs configuring on the server.

## Where the app looks

A release build of the app downloads from `https://freely-given.org/Software/Biblelastic/modules/`, and a debug build from this computer
(`http://localhost:8377/build/modules/`, through `adb reverse tcp:8377 tcp:8377` for a phone). Either can be changed when building:
`--dart-define=MODULES=https://…/`.

## Not done yet

- **Resuming a broken download**, and checking a download's SHA-256 (the engine does check each page of a module as it reads it).
- **Smaller downloads**: everything is 256 MB. A phone could start with only the OET and its notes (about 40 MB), and take the rest when it's wanted.
- **A web page about the modules** (the existing Software/Biblelastic page is from 2022).
