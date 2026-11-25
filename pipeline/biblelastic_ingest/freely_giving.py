"""
Add the books of https://books.freely.giving to the registry: every English or Spanish book that's CC0 or in the public domain, and has an EPUB.

    python3 -m biblelastic_ingest.freely_giving

Surveys the site's library (politely: one request at a time), fetches each EPUB once (into build/downloads/, where it's kept),
reads the book's own copyright and Bible-quotation notices from its front matter, and writes pipeline/books-freely-giving.toml,
which sources.toml includes. Books that sources.toml already has (with the same `source` page) are left out of it.
Run it again to pick up books that have been added to the library since.
"""
import html
import json
import re
import sys
import time
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

from . import epub, references

SITE = 'https://books.freely.giving'
PIPELINE_FOLDER = Path( __file__ ).resolve().parent.parent
REPOSITORY_FOLDER = PIPELINE_FOLDER.parent
OUTPUT = PIPELINE_FOLDER / 'books-freely-giving.toml'
DOWNLOADS = REPOSITORY_FOLDER / 'build' / 'downloads'
HEADERS = {'User-Agent':'Biblelastic-ingest'}
LICENCES = { 'CC0':'CC0 1.0', 'Public Domain':'Public domain' } # As the site gives them → as the registry records them
LANGUAGES = { 'en':'eng', 'es':'spa' } # The site's language codes → ours (for the books that are included)
# Paragraphs of a book's front matter that say who may do what with it, or where its Bible quotations are from
NOTICE_RE = re.compile( r'(?i)copyright|waived|public domain|creative ?commons|\bCC0\b|scripture (quotations|taken|texts?)|used by permission|all rights reserved|translations?,? including'
                         r'|dominio público|derechos reservados|citas (bíblicas|de la escritura)|tomadas de la (versión|biblia|reina|nueva)|con permiso' ) # (and in Spanish)


class _NoRedirect( urllib.request.HTTPRedirectHandler ):
    def redirect_request( self, *arguments ): return None


def get( url:str ) -> str:
    time.sleep( 0.5 ) # Politely
    with urllib.request.urlopen( urllib.request.Request( url, headers=HEADERS ), timeout=60 ) as response: return response.read().decode( 'utf-8', 'replace' )


def target( url:str ) -> str:
    """ Where a short link points (without following it) """
    time.sleep( 0.3 )
    try: urllib.request.build_opener( _NoRedirect ).open( urllib.request.Request( url, headers=HEADERS ), timeout=60 )
    except urllib.error.HTTPError as error: return error.headers.get( 'Location', '' )
    return ''


def text_of( page:str ) -> str:
    return html.unescape( re.sub( r'\s+', ' ', re.sub( r'<[^>]+>', ' ', re.sub( r'<(script|style)[^>]*>.*?</\1>', '', page, flags=re.S ) ) ) )


def licence_of( text:str ) -> str:
    """ From a book page's text, e.g., ‘… 2024 · 212 pages · CC0 Description …’ → 'CC0' (the pages are sometimes left out) """
    line = re.search( r'\d{3,4} · (?:[\d,]+ pages · )?(.+?) Description', text )
    if not line: return ''
    return 'Public Domain' if line.group( 1 ).startswith( 'Public Domain' ) else line.group( 1 ).split()[0]


def byline_of( text:str, title:str ) -> str:
    """ From a book page's text: who it's by, after its title (which can itself have ‘by’ in it, e.g., Surprised by Hesed) """
    byline = re.search( re.escape( title ) + r' by (.+?) \d{3,4} · ', text[text.find( 'People People' ):] )
    if not byline: return ''
    # ‘Anonymous foreword by …’ → ‘Anonymous, foreword by …’, and ‘Owens , Melin’ → ‘Owens, Melin’
    return re.sub( r'\s+,', ',', re.sub( r'(?<=\w) (foreword|introduction|edited|translated) by ', r', \1 by ', byline.group( 1 ).strip() ) )


def survey() -> list:
    """ Every book in the library: [{href, slug, title, lang, authors, year, licence, epub}, …] (the last two only for English and Spanish books) """
    library = get( f'{SITE}/library/' )
    library = library[library.find( 'id="by-title"' ):library.find( 'id="by-author"' )]
    books = []
    for card in re.findall( r'<div class="book-grid-item[^"]*"(.*?)</small>', library, re.S ):
        attributes = dict( re.findall( r'data-(\w+)="([^"]*)"', card[:400] ) )
        href, title = re.search( r'<a href="(/books/[^"]+)"[^>]*>([^<]+)</a>', card ).groups()
        year = re.search( r'(\d{3,4}) ·', card )
        books.append( { 'href':href, 'slug':href.rstrip( '/' ).rsplit( '/', 1 )[1], 'title':html.unescape( title ).strip(), 'lang':attributes.get( 'lang' ),
                        'authors':[ html.unescape( author ) for author in re.findall( r'/people/[^"]+" class="text-reset">([^<]+)</a>', card ) ],
                        'year':year.group( 1 ) if year else '' } )
    for book in books:
        if book['lang'] not in LANGUAGES: continue
        page = get( SITE + book['href'] )
        text = text_of( page )
        book['licence'] = licence_of( text )
        book['byline'] = byline_of( text, book['title'] ) or ', '.join( book['authors'] )
        links = sorted( set( re.findall( r'href="(https://(?:files\.books\.freelygiv\.ing|go\.freelygiv\.ing)/[^"]+)"', page ) ) )
        found = [ link for link in links if link.endswith( '.epub' ) ]
        for link in links:
            if found: break
            if 'go.freelygiv.ing' in link and 'github' not in link and (where := target( link )).endswith( '.epub' ): found = [where]
        book['epub'] = found[0] if found else None
    return books


def identifier( slug:str ) -> str:
    """ the-dorean-principle → DoreanPrinciple, el-nombre-divino → NombreDivino (a leading ‘the’, ‘el’, ‘la’, etc., is dropped) """
    words = [ word for word in re.split( r'[^A-Za-z0-9]+', slug ) if word ]
    if words and words[0] in ('the', 'el', 'la', 'los', 'las') and len(words) > 1: words = words[1:]
    if words and words[0].isdigit(): words = words[1:] + words[:1] # An identifier mustn't start with a number: 1689 Baptist Confession → BaptistConfession…1689
    return ''.join( word[:1].upper() + word[1:] for word in words )


def notices( path:Path ) -> str:
    """ The paragraphs of a book's front matter that give its copyright and where its Bible quotations are from """
    blocks, _contents = epub.read_epub( str(path) )
    found = []
    for block in blocks[:150]:
        text = re.sub( r'\s+', ' ', block.text ).strip()
        # (A short line without a full stop is a heading or an item of contents, e.g., in a book about copyright)
        if NOTICE_RE.search( text ) and len(text) < 1500 and (('.' in text and len(text) > 40) or re.search( r'©|\bCC0\b|waived', text )) and text not in found:
            found.append( text )
    return ' '.join( found )


def toml_string( text:str ) -> str: return json.dumps( text, ensure_ascii=False ) # A JSON string is also a TOML basic string


def main() -> int:
    registry = tomllib.loads( (PIPELINE_FOLDER / 'sources.toml').read_text( encoding='utf-8' ) )
    already = { edition.get( 'source' ) for edition in registry.get( 'edition', [] ) }
    books = survey()
    wanted = [ book for book in books if book['lang'] in LANGUAGES and book.get( 'licence' ) in LICENCES and book.get( 'epub' ) and SITE + book['href'] not in already ]
    skipped = [ book for book in books if book not in wanted and SITE + book['href'] not in already ]
    entries = [ '# Books from https://books.freely.giving: every English or Spanish book there that is CC0 or in the public domain, and has an EPUB.',
                '# Written by `python3 -m biblelastic_ingest.freely_giving`: run it again (rather than editing this) to pick up new books.',
                '# The copyright of each is the book\'s own notices, as found in its front matter: check them before publishing.', '' ]
    ids = set()
    for book in wanted:
        host = re.match( r'https://([^/]+)/', book['epub'] ).group( 1 )
        folder = 'books.freely.giving' if 'freelygiv' in host else host
        path = DOWNLOADS / folder / book['epub'].rsplit( '/', 1 )[1]
        if not path.exists():
            print( f"Fetching {book['epub']} …" )
            path.parent.mkdir( parents=True, exist_ok=True )
            with urllib.request.urlopen( urllib.request.Request( book['epub'], headers=HEADERS ), timeout=120 ) as response: data = response.read()
            path.with_suffix( '.part' ).write_bytes( data ); path.with_suffix( '.part' ).rename( path )
        ident = identifier( book['slug'] )
        while ident in ids: ident += 'X'
        ids.add( ident )
        language = LANGUAGES[book['lang']]
        kind = 'commentary' if re.search( r'(?i)\b(commentary|comentario)\b', book['title'] ) else 'book'
        # A book about one book of the Bible (e.g., Meditations on Psalm 119): bare references in it are taken to be in that book
        named = references.find( book['title'], language=language )
        context = named[0][2][0].split()[0] if len(named) == 1 else None
        found = notices( path )
        copyright = f"{book['title']}, {book['year']}" + (f", by {book['byline']}. " if book['byline'] else '. ') + (found or f"{LICENCES[book['licence']]}, according to its page on books.freely.giving.")
        entries += [ '[[edition]]', f'id = "{ident}"', f'kind = "{kind}"', f"name = {toml_string( book['title'] )}", ] + ([ f"author = {toml_string( book['byline'] )}" ] if book['byline'] else []) + [
                     f'language = "{language}"', 'script = "Latn"', 'versification = "eng"', 'format = "EPUB"', f'source = "{SITE}{book["href"]}"', f'download = "{book["epub"]}"',
                     f'files = ["Biblelastic/build/downloads/{folder}/{path.name}"]' ] + ([ f'context_book = "{context}"' ] if context else []) + [
                     f'copyright = {toml_string( copyright )}', f'licence = "{LICENCES[book["licence"]]}"', 'redistributable = true', 'licence_verified = false', '' ]
        print( f'{ident:40} {kind:10} {len(found):5} characters of notices' )
    OUTPUT.write_text( '\n'.join( entries ), encoding='utf-8' )
    print( f'{len(wanted)} books written to {OUTPUT.relative_to( REPOSITORY_FOLDER )}. Not included:' )
    for book in skipped:
        reason = 'not English or Spanish' if book['lang'] not in LANGUAGES else f"licence: {book.get( 'licence' ) or 'not given'}" if book.get( 'licence' ) not in LICENCES else 'no EPUB'
        print( f"    {book['title'][:70]} ({reason})" )
    return 0


if __name__ == '__main__':
    sys.exit( main() )
