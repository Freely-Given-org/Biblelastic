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

A release build of the app downloads from `https://Freely-Given.org/Software/Biblelastic/modules/`, and a debug build from this computer
(`http://localhost:8377/build/modules/`, through `adb reverse tcp:8377 tcp:8377` for a phone). Either can be changed when building:
`--dart-define=MODULES=https://…/`.

## What a phone downloads

Not everything (256 MB): the app offers a starter set for each language (65 MB for English, 58 MB for Spanish), search by meaning separately,
and each work on its own (see [App.md](App.md)). It works these out from the catalogue (each module's `kind`, `work`, `edition`, and `language`, and an alignment's name),
so publishing needs nothing more for a new work to be offered in the right places.

## Downloads that break, or arrive wrong

Each module is downloaded into a partial file (`NAME.SHA16.part`, named for the version, so that two versions are never mixed). If the connection is lost,
the app tries again by itself (six times, waiting 1, 2, 4, 8, and 16 seconds), asking for the rest (`Range: bytes=N-`) where the server can send it,
and otherwise for the whole module again; after that, trying again carries on from where it stopped. Once it's all there, its SHA-256 is checked against the catalogue's,
and only then does it take the place of the old copy (which stays usable until then). A module that arrives wrong is thrown away, with a message to try again.
`app/test_web.mjs` tests both, with a server that cuts the first download short and corrupts another.

**On Freely-Given.org**, Apache serves `.blm` files as `application/octet-stream` (`/etc/apache2/conf-available/biblelastic-modules.conf`:
`AddType application/octet-stream .blm`, since `.htaccess` isn't read there), so they aren't compressed, and Apache and Cloudflare (even from its cache)
can send the rest of one. Before that (until 26 November 2026) they were served as compressed `text/plain`, which saved only about 5% and which Cloudflare
always sent whole; its copies from then expire within two hours, or can be purged.

## The web page

`Software/Biblelastic/index.html` on Freely-Given.org describes the app, the starter sets, and each work with its licence and size (from the catalogue).
It also shows `Biblelastic-logo.png` (`app/design/logo.png`), and links to the current release, so its version, date, and APK sizes change with each one.

## Publishing a release of the app

`app/release.sh` builds the release into `app/build/release/VERSION/`. To publish it (with the site's owner's OK), from `app/`:

    L=/srv/www/Freely-Given.org/Software/Biblelastic
    rsync -a --delete build/release/VERSION/web/ $L/app/
    cp build/release/VERSION/*.apk $L/downloads/
    chgrp -R WebAdmin $L/app $L/downloads

then change the version, date, and links in `index.html`, and remove the older APKs from `downloads/`.
The web app is at `https://Freely-Given.org/Software/Biblelastic/app/`, and gets its modules from `../modules/`.
Apache serves `.apk` files as `application/vnd.android.package-archive`, as they should be.
