""" Write Freely-Given.org's pages about what Biblelastic offers (its Bibles, Bible helps, books, and modules), from the modules' catalogue and the registry.

The project's own page (index.html) links to these, and is kept by hand. From the pipeline folder:
    python3 -m biblelastic_ingest.web_pages [--output ../build/site]
then (with the site's owner's OK) copy them next to it: see docs/Publishing.md.
"""
import argparse
import html
import json
import os
import sys
import tomllib
from datetime import date
from pathlib import Path

PIPELINE_FOLDER = Path( __file__ ).resolve().parent.parent
REPOSITORY_FOLDER = PIPELINE_FOLDER.parent

ORIGINAL_LANGUAGES = ('grc', 'hbo', 'arc')
LANGUAGE_NAMES = { 'eng':'English', 'spa':'Spanish (Español)', 'grc':'Greek', 'hbo':'Hebrew', 'arc':'Aramaic' }
LEADING_EDITIONS = ('OET-RV', 'OET-LV') # Always the first Bibles listed
OT_BOOKS = { 'GEN','EXO','LEV','NUM','DEU','JOS','JDG','RUT','SA1','SA2','KI1','KI2','CH1','CH2','EZR','NEH','EST','JOB','PSA','PRO','ECC','SNG',
             'ISA','JER','LAM','EZE','DAN','HOS','JOL','AMO','OBA','JNA','MIC','NAH','HAB','ZEP','HAG','ZEC','MAL' }
NT_BOOKS = { 'MAT','MRK','LUK','JHN','ACT','ROM','CO1','CO2','GAL','EPH','PHP','COL','TH1','TH2','TI1','TI2','TIT','PHM','HEB','JAM',
             'PE1','PE2','JN1','JN2','JN3','JDE','REV' }
NOT_BOOKS = { 'FRT', 'INT', 'BAK', 'OTH', 'GLO', 'TDX', 'NDX', 'CNC', 'XXA', 'XXB', 'XXC', 'XXD', 'XXE', 'XXF', 'XXG' }

# The pages: (file, title in the sidebar, page heading)
PAGES = [ ('Bibles.html', 'Bibles', 'Biblelastic: Bibles'), ('Helps.html', 'Bible helps', 'Biblelastic: Bible helps'),
          ('Books.html', 'Books', 'Biblelastic: Books'), ('Modules.html', 'Modules', 'Biblelastic: Modules') ]


def escape( text:str ) -> str: return html.escape( text, quote=True )
def megabytes( count:int ) -> str:
    """ As the app says it (a megabyte being 2^20 bytes), e.g., 65.1&nbsp;MB, or 2.5&nbsp;kB """
    return f'{count/1024:.1f}&nbsp;kB' if count < 100*1024 else f'{count/1048576:.1f}&nbsp;MB'
def language_name( code:str ) -> str: return LANGUAGE_NAMES.get( code, code )


class Catalogue:
    """ The works in the catalogue (as the app groups them): each with its modules (text, layers, and the alignments of its words) and its vectors """
    def __init__( self, catalogue:dict, registry:dict, intermediate:Path ):
        self.modules = catalogue['modules']
        self.registry = { edition['id']:edition for edition in registry.get( 'edition', [] ) }
        self.models = registry.get( 'model', [] )
        self.works, self.vectors = {}, {}
        for module in self.modules:
            edition = module.get( 'edition' ) or (module['name'].split( '--' )[0] if '--' in module['name'] else '')
            if not edition or module.get( 'kind' ) == 'model': continue
            if module.get( 'kind' ) == 'vectors': self.vectors[edition] = module
            else: self.works.setdefault( edition, [] ).append( module )
        self.intermediate = intermediate

    def text( self, edition:str ) -> dict: return next( (module for module in self.works[edition] if module.get( 'kind' ) == 'text'), self.works[edition][0] )
    def kind( self, edition:str ) -> str: return self.text( edition ).get( 'work', '' )
    def language( self, edition:str ) -> str: return self.text( edition ).get( 'language', '' )
    def title( self, edition:str ) -> str: return self.text( edition ).get( 'title' ) or edition
    def starter( self, edition:str ) -> bool: return self.text( edition ).get( 'starter' ) != 'false'
    def size( self, edition:str ) -> int: return sum( module['bytes'] for module in self.works[edition] )
    def of_kind( self, *kinds:str ) -> list: return [ edition for edition in self.works if self.kind( edition ) in kinds ]

    def books( self, edition:str ) -> set:
        """ The books of the Bible that an edition has (from the ingest's manifest, if it's here) """
        path = self.intermediate / edition / 'manifest.json'
        if not path.exists(): return set()
        return { document['BBB'] for document in json.loads( path.read_text( encoding='utf-8' ) ).get( 'documents', [] ) } - NOT_BOOKS

    def coverage( self, edition:str ) -> str:
        """ e.g., ‘Old and New Testaments, with the Apocrypha’ """
        books = self.books( edition )
        if not books: return ''
        ot, nt, others = books & OT_BOOKS, books & NT_BOOKS, books - OT_BOOKS - NT_BOOKS
        def part( found:set, every:set, name:str ) -> str: return name if len(found) == len(every) else f'{len(found)} books of the {name}'
        parts = [ part( ot, OT_BOOKS, 'Old Testament' ) ] if ot else []
        if nt: parts.append( part( nt, NT_BOOKS, 'New Testament' ) )
        said = ' and '.join( parts ).replace( 'Old Testament and New Testament', 'Old and New Testaments' )
        if others: said += ', with the Apocrypha' if self.language( edition ) == 'eng' and len(others) > 3 else f', with {len(others)} more'
        return said

    def linked( self, edition:str ) -> bool:
        """ Whether its words are linked to the Greek and Hebrew (by alignments, or because it's an original-language text) """
        return any( '--' in module['name'] for module in self.works[edition] ) or self.language( edition ) in ORIGINAL_LANGUAGES

    def starter_set( self, language:str ) -> int:
        """ The size of a language's starter set (as the app chooses it: see app/lib/catalogue.dart) """
        total = sum( self.size( edition ) for edition in self.works
                     if self.kind( edition ) != 'book' and self.starter( edition )
                        and (self.language( edition ) == language or self.kind( edition ) == 'scripture' and self.language( edition ) in ORIGINAL_LANGUAGES) )
        return total + sum( module['bytes'] for module in self.modules if module.get( 'kind' ) == 'thesaurus' and (module.get( 'language' ) or module.get( 'layer' )) == language )

    def languages( self ) -> list:
        """ The languages that there are Bibles in (not the original languages), English first """
        found = { self.language( edition ) for edition in self.of_kind( 'scripture' ) } - set( ORIGINAL_LANGUAGES )
        return sorted( found, key=lambda code: (code != 'eng', code) )

    def bible_order( self, edition:str ) -> tuple:
        """ The OET first, then the translations by language (English first) and title, then the original-language texts """
        language = self.language( edition )
        return (LEADING_EDITIONS.index( edition ) if edition in LEADING_EDITIONS else len(LEADING_EDITIONS),
                language in ORIGINAL_LANGUAGES, language != 'eng', language, shelved( self.title( edition ) ))


def shelved( title:str ) -> str:
    """ As a library shelves a title: ‘The Pilgrim’s Progress’ under P """
    lower = title.lower()
    for article in ('the ', 'a ', 'an ', 'el ', 'la ', 'los ', 'las '):
        if lower.startswith( article ): return lower[len(article):]
    return lower


def page( file:str, heading:str, body:str, today:date ) -> str:
    """ A page in the style of Freely-Given.org's others (XHTML 1.0 Strict), with the sidebar showing where it is """
    sidebar = [ ('../../', 'Home'), ('../../News.html', 'News'), ('../../Overview.html', 'Overview'), ('../../BibleOriginals/', 'Bible originals'),
                ('../../BibleTranslations/', 'Bible translations'), ]
    lines = [ f'    <br /><a href="{link}">{name}</a>' for link, name in sidebar ]
    lines += [ '    <br />&nbsp;&nbsp;<a href="../../BibleTranslations/English/OET/"><small>Open English Translation (OET)</small></a>',
               '    <br /><a href="../../Apps/">Apps</a>', '    <br /><a href="../">Software</a>',
               '    <br />&nbsp;&nbsp;<a href="../BibleDropBox/">Bible Drop Box</a>',
               '    <br />&nbsp;&nbsp;&nbsp;&nbsp;<a href="../BibleDropBox/Demos/">Demo outputs</a>',
               '    <br />&nbsp;&nbsp;&nbsp;&nbsp;<a href="../BibleDropBox/Formats/USFMBibles.html">USFM Bibles</a>',
               '    <br />&nbsp;&nbsp;&nbsp;&nbsp;<a href="../BibleDropBox/Formats/ESFMBibles.html">ESFM Bibles</a>',
               '    <br />&nbsp;&nbsp;<a href="../Biblelator/">Biblelator editor</a>',
               '    <br />&nbsp;&nbsp;<a href="../BibleDoor/">Bible Door app</a>',
               '    <br />&nbsp;&nbsp;<a href="./">Biblelastic</a>' ]
    for pageFile, name, _heading in PAGES:
        lines.append( f'    <br />&nbsp;&nbsp;&nbsp;&nbsp;{name}' if pageFile == file else f'    <br />&nbsp;&nbsp;&nbsp;&nbsp;<a href="{pageFile}">{name}</a>' )
    lines += [ f'    <br /><a href="../../{link}">{name}</a>' for link, name in (('Studies/', 'Bible studies'), ('Teaching/', 'Bible teaching'), ('Sermons/', 'Sermons'),
               ('Music/', 'Music and songs'), ('Images/', 'Images'), ('About.html', 'About'), ('Opportunities.html', 'Opportunities'), ('Links.html', 'Links'),
               ('Contact.html', 'Contact'), ('Donate.html', 'Donate')) ]
    sidebarHTML = '\n'.join( lines )
    return f'''<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">
<html lang="en" xml:lang="en" xmlns="http://www.w3.org/1999/xhtml">
<head>
<meta http-equiv="content-type" content="text/html;charset=UTF-8"/>
<meta name="description" content="{escape( heading )}, from Freely-Given.org"/>
<link rel="stylesheet" href="../../Overall.css" type="text/css"/>

    <title>Freely-Given.org {escape( heading )}</title>
</head>

<body class="HTMLBody">
<div id="TopBar"><a href="../../"><img class="Banner" height="120" src="../../Logo/FG-Banner.jpg" alt="Top logo banner graphic"/></a>
    <h1 class="PageHeading">Freely-Given.org {escape( heading )}</h1></div>
<div id="MainContent">
<div id="LeftSidebar">
    <p>
{sidebarHTML}
    </p></div>

<div id="MainSection">
    <p><a href="./"><img src="Biblelastic-logo.png" height="90" alt="Biblelastic: fantastic Bible study"/></a></p>
{body}
    <p>These pages are written from the catalogue of the modules, so they list everything that the app can download.</p>
</div>

<div id="Footer">
    <p class="GeneratedNotice">This page last updated: {today.strftime( '%d-%b-%Y' )}</p>
    <p class="CopyrightNotice">Issued under a <a href="https://creativecommons.org">Creative Commons</a>
        <a href="https://creativecommons.org/licenses/by-sa/4.0">Attribution/Share-alike Licence</a>,
            copyright © 2022-{today.year}, <a href="../../About.html">RJH</a></p>
    <p class="ValidationIcons"><a href="https://validator.w3.org/check?uri=referer"><img class="ValidationIcon" src="../../Icons/valid-xhtml10.png" alt="Valid XHTML 1.0 Strict"/></a>
        <a href="https://jigsaw.w3.org/css-validator/check/referer"><img class="ValidationIcon" src="../../Icons/valid-css.png" alt="Valid CSS!"/></a>
    </p></div>
</div>
</body></html>
'''


def title_cell( catalogue:Catalogue, edition:str ) -> str:
    """ A work's title, linked to where it came from (if the registry says) """
    source = catalogue.registry.get( edition, {} ).get( 'source', '' )
    title = escape( catalogue.title( edition ) )
    return f'<a href="{escape( source )}">{title}</a>' if source.startswith( 'http' ) else title


def licence_cell( catalogue:Catalogue, edition:str ) -> str:
    return f'<td style="white-space: nowrap">{escape( catalogue.text( edition ).get( "licence", "" ) )}</td>'


def bibles( catalogue:Catalogue ) -> str:
    editions = sorted( catalogue.of_kind( 'scripture' ), key=catalogue.bible_order )
    rows = []
    for edition in editions:
        notes = [ catalogue.coverage( edition ) ]
        if catalogue.linked( edition ) and catalogue.language( edition ) not in ORIGINAL_LANGUAGES: notes.append( 'its words linked to the Greek and Hebrew' )
        if catalogue.starter( edition ): notes.append( 'in the starter set' if catalogue.language( edition ) in ORIGINAL_LANGUAGES else f'in the {language_name( catalogue.language( edition ) ).split()[0]} starter set' )
        said = '; '.join( note for note in notes if note )
        rows.append( f'        <tr><td>{title_cell( catalogue, edition )}</td><td>{escape( language_name( catalogue.language( edition ) ) )}</td>'
                     f'{licence_cell( catalogue, edition )}<td style="white-space: nowrap">{megabytes( catalogue.size( edition ) )}</td><td>{escape( said[:1].upper() + said[1:] )}</td></tr>' )
    translations = [ edition for edition in editions if catalogue.language( edition ) not in ORIGINAL_LANGUAGES ]
    languages = sorted( { catalogue.language( edition ) for edition in translations } )
    return f'''
    <h2>Bibles</h2>
    <p>Biblelastic has {len(translations)} Bible translations (in {' and '.join( language_name( code ).split()[0] for code in languages )}),
        and the Greek and Hebrew texts that they translate.
        Each can be downloaded on its own in the app (from <em>Modules</em> in its menu),
        and a starter set for each language has its main Bibles, with the Greek and Hebrew.</p>
    <p>A Bible whose words are linked to the Greek and Hebrew shows, when a word is tapped, the Greek or Hebrew word that it translates.
        Those without section headings of their own are shown in the same sections as the
        <a href="../../BibleTranslations/English/OET/">Open English Translation</a>’s Readers’ Version.</p>
    <table>
        <tr><th>Bible</th><th>Language</th><th>Licence</th><th>Size</th><th>Notes</th></tr>
{chr(10).join( rows )}
    </table>
    <p>Each Bible’s copyright notice, licence, and attribution are shown in the app (under <em>About</em> in its menu).</p>'''


def helps( catalogue:Catalogue ) -> str:
    def table( editions:list ) -> str:
        rows = [ f'        <tr><td>{title_cell( catalogue, edition )}</td><td>{escape( language_name( catalogue.language( edition ) ) )}</td>'
                 f'{licence_cell( catalogue, edition )}<td style="white-space: nowrap">{megabytes( catalogue.size( edition ) )}</td></tr>'
                 for edition in sorted( editions, key=lambda edition: (catalogue.language( edition ) != 'eng', catalogue.language( edition ), shelved( catalogue.title( edition ) )) ) ]
        return '    <table>\n        <tr><th>Work</th><th>Language</th><th>Licence</th><th>Size</th></tr>\n' + '\n'.join( rows ) + '\n    </table>'
    # (The commentaries that are books, e.g., from books.freely.giving, are listed apart from the study notes)
    notes = [ edition for edition in catalogue.of_kind( 'commentary' ) if catalogue.registry.get( edition, {} ).get( 'format' ) != 'EPUB' ]
    commentaries = [ edition for edition in catalogue.of_kind( 'commentary' ) if edition not in notes ]
    thesauri = [ module for module in catalogue.modules if module.get( 'kind' ) == 'thesaurus' ]
    models = [ module for module in catalogue.modules if module.get( 'kind' ) == 'model' ]
    vectors = sum( module['bytes'] for module in catalogue.vectors.values() )
    sources = { model['id']:model.get( 'source', '' ) for model in catalogue.models }
    modelList = ' and '.join( f'<a href="{escape( sources.get( module["edition"], "" ) )}">{escape( module["edition"] )}</a> ({escape( language_name( module.get( "language", "" ) ).split()[0] )}, {megabytes( module["bytes"] )})'
                              for module in models )
    out = f'''
    <h2>Bible helps</h2>
    <p>Study notes and commentaries are shown beside the Bible (tap a verse number), and dictionary articles when a word or a subject is looked up.
        Those in a language’s starter set come with it; the others can be downloaded one by one.</p>
    <h3>Study notes</h3>
{table( notes )}'''
    if commentaries: out += f'''
    <h3>Commentaries</h3>
    <p>Each of these is shown with a note that its views are its author’s own.</p>
{table( commentaries )}'''
    out += f'''
    <h3>Dictionaries</h3>
{table( catalogue.of_kind( 'dictionary' ) )}
    <h3>Search tools</h3>
    <ul>
        <li><b>Thesaurus</b> ({', '.join( f'{language_name( module.get( "language" ) or module.get( "layer", "" ) ).split()[0]}, {megabytes( module["bytes"] )}' for module in thesauri )}):
            finds the passages about a subject, with the words that are like the words that are searched for.
            It’s in the starter set.</li>
        <li><b>Search by meaning</b>: finds passages, notes, and articles about a subject, even when they use other words.
            It runs on the phone or computer itself, with a small language model: {modelList}, both under the MIT licence,
            and each work’s <em>vectors</em> (what each of its passages is about), which are downloaded with it once the model is installed
            ({megabytes( vectors )} for all {len(catalogue.vectors)} works).</li>
    </ul>'''
    return out


def books( catalogue:Catalogue ) -> str:
    editions = sorted( catalogue.of_kind( 'book' ), key=lambda edition: (catalogue.language( edition ) != 'eng', catalogue.language( edition ), shelved( catalogue.title( edition ) )) )
    rows = [ f'        <tr><td>{title_cell( catalogue, edition )}</td><td>{escape( catalogue.registry.get( edition, {} ).get( "author", "" ) )}</td>'
             f'<td>{escape( language_name( catalogue.language( edition ) ) )}</td>{licence_cell( catalogue, edition )}'
             f'<td style="white-space: nowrap">{megabytes( catalogue.size( edition ) )}</td></tr>' for edition in editions ]
    counts = {}
    for edition in editions: counts[catalogue.language( edition )] = counts.get( catalogue.language( edition ), 0 ) + 1
    return f'''
    <h2>Books</h2>
    <p>Biblelastic has {len(editions)} Christian books ({', '.join( f'{count} in {language_name( code ).split()[0]}' for code, count in counts.items() )};
        {megabytes( sum( catalogue.size( edition ) for edition in editions ) )} altogether),
        all from <a href="https://books.freely.giving/">books.freely.giving</a>, and all dedicated to the public domain by their authors and publishers.
        Each can be downloaded on its own in the app (from <em>Library</em> or <em>Modules</em> in its menu),
        Each is shown with a note that its views are its author’s own.</p>
    <table>
        <tr><th>Book</th><th>Author</th><th>Language</th><th>Licence</th><th>Size</th></tr>
{chr(10).join( rows )}
    </table>'''


def modules( catalogue:Catalogue ) -> str:
    total = sum( module['bytes'] for module in catalogue.modules )
    starters = ', '.join( f'{megabytes( catalogue.starter_set( code ) )} for {language_name( code ).split()[0]}' for code in catalogue.languages() )
    return f'''
    <h2>Modules</h2>
    <p>The app downloads what it shows as <em>modules</em>, from <a href="modules/index.json">this website</a>:
        {len(catalogue.modules)} of them ({megabytes( total )} altogether), but nobody needs them all.
        Everything works without an Internet connection once its modules have been downloaded.</p>
    <ul>
        <li><b>A starter set</b> for each language ({starters}) has its main Bibles, its study notes and dictionaries,
            the <a href="Bibles.html">Greek and Hebrew</a> (for what each word translates), and its thesaurus (for searching by subject).</li>
        <li><b>Search by meaning</b> can then be added for a language: its model, and the vectors of its works.</li>
        <li>The other <a href="Bibles.html">Bibles</a>, <a href="Helps.html">Bible helps</a>, and <a href="Books.html">books</a>
            can then be added one at a time.</li>
    </ul>
    <p>An interrupted download carries on from where it stopped, and each module is checked (by its SHA-256) before it’s installed.
        When a module is updated here, the app offers the new one.</p>
    <p>Every work has an open licence or is in the public domain, and the app shows each one’s copyright, licence, and attribution under <em>About</em>.</p>'''


def main() -> int:
    parser = argparse.ArgumentParser( prog='biblelastic_ingest.web_pages', description=__doc__.split( '\n' )[0] )
    parser.add_argument( '--catalogue', type=Path, default=REPOSITORY_FOLDER / 'build' / 'modules' / 'index.json',
                         help='The catalogue of the modules as they are (or will be) published' )
    parser.add_argument( '--registry', type=Path, default=PIPELINE_FOLDER / 'sources.toml' )
    parser.add_argument( '--intermediate', type=Path, default=REPOSITORY_FOLDER / 'build' / 'intermediate' )
    parser.add_argument( '--output', type=Path, default=REPOSITORY_FOLDER / 'build' / 'site' )
    arguments = parser.parse_args()

    registry = tomllib.loads( arguments.registry.read_text( encoding='utf-8' ) )
    for included in registry.get( 'include', [] ):
        path = arguments.registry.parent / included
        if path.exists(): registry['edition'] = registry.get( 'edition', [] ) + tomllib.loads( path.read_text( encoding='utf-8' ) ).get( 'edition', [] )
    catalogue = Catalogue( json.loads( arguments.catalogue.read_text( encoding='utf-8' ) ), registry, arguments.intermediate )
    arguments.output.mkdir( parents=True, exist_ok=True )
    today = date.today()
    for (file, _name, heading), write in zip( PAGES, (bibles, helps, books, modules) ):
        (arguments.output / file).write_text( page( file, heading, write( catalogue ), today ), encoding='utf-8' )
        print( f'Wrote {arguments.output / file}' )
    return 0


if __name__ == '__main__':
    sys.exit( main() )
