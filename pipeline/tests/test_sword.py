"""
Tests for the SWORD modules' reader (sword.py), and for books whose contents have title pages (epub.entry_items).
Run from the pipeline/ folder with: python3 -m unittest discover tests
"""
import io
import struct
import sys
import unittest
import zipfile
import zlib
from pathlib import Path

sys.path.insert( 0, str( Path( __file__ ).resolve().parent.parent ) )
from biblelastic_ingest import epub, sword

CHAPTERS = { 'GEN':[31, 25] + [20]*48, 'EXO':[22, 25, 22, 31] + [30]*36, 'REV':[20, 29], 'CH1':[54]*24, 'JDE':[25] }


def zld_module( entries:list ) -> zipfile.ZipFile:
    """ A zLD module (in a zip file, as CrossWire packages them) with these (key, text) entries, all in one block """
    data = b''.join( text.encode( 'utf-8' ) + b'\0' for _key, text in entries )
    block, offset = struct.pack( '<I', len(entries) ), 4 + 8 * len(entries)
    for _key, text in entries:
        block += struct.pack( '<II', offset, len(text.encode( 'utf-8' )) + 1 ); offset += len(text.encode( 'utf-8' )) + 1
    compressed = zlib.compress( block + data )
    keys, index = b'', b''
    for number, (key, _text) in enumerate( entries ):
        record = key.encode( 'utf-8' ) + b'\n' + struct.pack( '<II', 0, number )
        index += struct.pack( '<II', len(keys), len(record) ); keys += record
    memory = io.BytesIO()
    with zipfile.ZipFile( memory, 'w' ) as archive:
        archive.writestr( 'mods.d/test.conf', '[Test]\nDataPath=./modules/lexdict/zld/test/test\nModDrv=zLD\nEncoding=UTF-8\n' )
        for suffix, content in (('.idx', index), ('.dat', keys), ('.zdx', struct.pack( '<II', 0, len(compressed) )), ('.zdt', compressed)):
            archive.writestr( 'modules/lexdict/zld/test/test' + suffix, content )
    return zipfile.ZipFile( memory )


class ContextTests( unittest.TestCase ):
    def test_numbers_only( self ):
        context = sword.Context( CHAPTERS )
        self.assertEqual( context.passages( 'Rev.', '1:8' ), ['REV 1:8'] )
        self.assertEqual( context.passages( None, '11', ',' ), ['REV 1:11'] ) # (Not Genesis, as Easton's SWORD module has it)
        self.assertEqual( context.passages( None, '2:8', ';' ), ['REV 2:8'] )
        self.assertEqual( context.passages( 'Ex.', '4:14' ), ['EXO 4:14'] )
        self.assertEqual( context.passages( None, '27-30', ',' ), ['EXO 4:27-4:30'] )
        self.assertEqual( context.passages( '1Ch', '6:3' ), ['CH1 6:3'] )
        self.assertEqual( context.passages( None, '24', ';' ), ['CH1 24'] ) # After a semicolon: a chapter

    def test_commentary( self ):
        context = sword.Context( CHAPTERS, 'GEN', 1, 5 ) # In the TSK's note on Gen 1:5, ‘8,13’ are verses of chapter 1
        self.assertEqual( context.passages( None, '8,13' ), ['GEN 1:8', 'GEN 1:13'] )
        self.assertEqual( context.passages( 'Joh', '1:5' ), ['JHN 1:5'] )
        self.assertEqual( context.passages( 'Jude', '1:3' ), ['JDE 1:3'] )

    def test_checked( self ):
        context = sword.Context( CHAPTERS )
        self.assertEqual( context.passages( 'Ge', '51:1' ), [] ) # (No chapter 51)
        self.assertEqual( context.passages( 'Ge', '2:26' ), [] )
        self.assertEqual( sword.osis_passages( 'Bible:Judg.8.33-Judg.8.9' ), [] ) # Backwards
        self.assertEqual( sword.osis_passages( 'Bible:1Chr.6.3-1Chr.6.15' ), ['CH1 6:3-6:15'] )
        self.assertEqual( sword.osis_passages( '1Chr.24' ), ['CH1 24'] )


class DictionaryTests( unittest.TestCase ):
    def test_read( self ):
        archive = zld_module( [('AARON', '<entryFree n="Aaron"><title>Aaron</title><p>Son of Amram (<ref osisRef="Bible:Exod.6.20">Ex. 6:20</ref>, <ref osisRef="Bible:Gen.1.23">23</ref>).</p></entryFree>')] )
        self.assertEqual( sword.read_dictionary( archive, 'modules/lexdict/zld/test/test', 'utf-8' )[0][0], 'AARON' )

    def test_parse( self ):
        edition = { 'id':'Test', 'sword':{ 'document':'Topics', 'topics':True } }
        entries = [ ('LOVE', '<entryFree n="LOVE"><def>\n<lb/>→ OF MAN FOR GOD <ref osisRef="Exod.20.6">Ex 20:6</ref>; <ref osisRef="Deut.5.10">De 5:10</ref>,<ref osisRef="Deut.5.11">11</ref>'
                              '\n<lb/>→ See <ref target="Nave:ANGEL">ANGEL</ref></def></entryFree>'),
                    ('ANGEL (A SPIRIT)', '<entryFree n="ANGEL (A SPIRIT)"><def><lb/>→ Fallen <ref osisRef="Jude.1.6">Jude 6</ref></def></entryFree>') ]
        parsed, _names = sword.parse_dictionary( edition, entries, CHAPTERS | { 'DEU':[30]*34 }, 'test.zip' )
        self.assertEqual( [ (entry[2], entry[4]) for entry in parsed.entries ], [ ('Love', 'Love'), ('AngelaSpirit', 'Angel (a Spirit)') ] )
        self.assertEqual( [ anchor[3] for anchor in parsed.anchors ], ['EXO 20:6', 'DEU 5:10', 'DEU 5:11', 'JDE 1:6'] )
        self.assertEqual( [ link[3] for link in parsed.links ], ['Topics AngelaSpirit'] ) # (‘ANGEL’ isn't a topic: the first that starts with it is)
        self.assertEqual( parsed.text_differences, [] )
        self.assertEqual( [ paragraph[0] for paragraph in parsed.doc.paragraphs if paragraph[3] > paragraph[2] ], ['h1', 'li', 'li', 'h1', 'li'] )

    def test_raw_dictionary( self ):
        """ A RawLD module (Torrey's, Smith's): each entry is its key, a line break, and its text; Torrey's lines start with ‘- ’ (and ‘. ’ under another) """
        records = [ ('INCENSE', '- Brought from Sheba<br /><scripRef>Jer 6:20</scripRef><br /><br />- OFFERED<br />. In censers<br /><scripRef>Le 10:1</scripRef>\n'),
                    ('AB', 'See <term>MONTH</term>. (<scripRef passage="1ch 12:27">1\xa0Chronicles 12:27</scripRef>)\n'), ('MONTH', 'A month.\n') ]
        index, data = b'', b''
        for key, text in records:
            record = key.encode( 'latin-1' ) + b'\r\n' + text.encode( 'latin-1' )
            index += struct.pack( '<IH', len(data), len(record) ); data += record
        memory = io.BytesIO()
        with zipfile.ZipFile( memory, 'w' ) as archive:
            archive.writestr( 'test.idx', index ); archive.writestr( 'test.dat', data )
        entries = sword.read_raw_dictionary( zipfile.ZipFile( memory ), 'test', 'latin-1' )
        self.assertEqual( [ key for key, _text in entries ], ['INCENSE', 'AB', 'MONTH'] )
        chapters = CHAPTERS | { 'JER':[20]*52, 'LEV':[20]*27 }
        topics, _names = sword.parse_dictionary( { 'id':'Torrey', 'sword':{ 'document':'Topics', 'topics':True } }, entries[:1], chapters, 'Torrey.zip' )
        tokens = topics.doc.tokens
        lines = [ ''.join( before+text+after for before,text,after,_features in tokens[start:end] ).strip() for name, _kind, start, end, _text in topics.doc.paragraphs if end > start ]
        self.assertEqual( lines, ['Incense', 'Brought from Sheba Jer 6:20', 'OFFERED', 'In censers Le 10:1'] )
        self.assertEqual( topics.text_differences, [] )
        articles, _names = sword.parse_dictionary( { 'id':'Smith', 'sword':{ 'document':'Articles' } }, entries[1:], chapters, 'Smith.zip' )
        self.assertEqual( [ link[3] for link in articles.links ], ['Articles Month'] )
        self.assertEqual( [ anchor[3] for anchor in articles.anchors ], ['CH1 12:27'] ) # (From its passage attribute, ‘1ch 12:27’)

    def test_devotionals( self ):
        """ Spurgeon's Morning and Evening: each section's an entry. Daily Light: its Morning and Evening are, titled with the date, and its wrapped lines are joined. """
        spurgeon = '<div type="entry"><div type="section"><title>Morning, January 1</title><p>One.</p></div><div type="section"><title>Evening, January 1</title><p>Two.</p></div></div>'
        daily = '<i>Morning</i>:<br />\n<br />\n  The LORD is my<br />\n   shepherd.<br />\n<br />\nI shall not want.<br />\n<br />\n<i>Evening</i>:<br />\n<br />\nHe leadeth me.\n'
        parsed, _names = sword.parse_dictionary( { 'id':'SME', 'sword':{ 'document':'Readings', 'entries':'Reading' } }, [('01.01', spurgeon)], CHAPTERS, 'SME.zip' )
        self.assertEqual( [ (entry[2], entry[3], entry[4]) for entry in parsed.entries ], [ ('MorningJanuary1', 'Reading', 'Morning, January 1'), ('EveningJanuary1', 'Reading', 'Evening, January 1') ] )
        settings = { 'document':'Readings', 'dates':True, 'wrapped':True, 'parts':['Morning', 'Evening'] }
        parsed, _names = sword.parse_dictionary( { 'id':'Daily', 'sword':settings }, [('01.31', daily)], CHAPTERS, 'Daily.zip' )
        self.assertEqual( [ entry[4] for entry in parsed.entries ], ['Morning, January 31', 'Evening, January 31'] )
        tokens = parsed.doc.tokens
        texts = [ ''.join( before+text+after for before,text,after,_features in tokens[start:end] ).strip() for _name, _kind, start, end, _text in parsed.doc.paragraphs if end > start ]
        self.assertEqual( texts, ['Morning, January 31', 'The LORD is my shepherd.', 'I shall not want.', 'Evening, January 31', 'He leadeth me.'] )
        self.assertEqual( parsed.text_differences, [] )

    def test_general_book( self ):
        """ A RawGenBook module (Josephus's): an entry for each key whose keys under it have none under them, and notes after their paragraphs """
        tree = ('', '', [ ('The Life', '<p>The Life</p>', [ (f'Section {n}', f'<p>{n}. Text.</p>', []) for n in range( 1, 23 ) ]),
                          ('Antiquities', '', [ ('Book 1', '<p>BOOK I</p>', [ ('Chapter 1', '<p>CHAPTER 1.</p>', [ ('Section 1', '<p>1. In the beginning<note>A note.</note> God.</p>', []) ]) ]) ]) ])
        parsed = sword.parse_genbook( { 'id':'Josephus', 'sword':{} }, tree, CHAPTERS, 'Josephus.zip' )['Chapter'][0]
        self.assertEqual( len(parsed.entries), 23 ) # (The Life's 22 sections are more than 20, so each is an entry)
        self.assertEqual( [ entry[4] for entry in parsed.entries[:1] + parsed.entries[-1:] ], ['The Life, Section 1', 'Antiquities, Book 1, Chapter 1'] )
        tokens = parsed.doc.tokens
        start, end = parsed.entries[-1][:2]
        texts = [ (name, ''.join( before+text+after for before,text,after,_features in tokens[paraStart:paraEnd] ).strip()) for name, _kind, paraStart, paraEnd, _text in parsed.doc.paragraphs if paraEnd > paraStart and paraStart >= start ]
        self.assertEqual( texts, [ ('p', 'BOOK I'), ('p', 'CHAPTER 1.'), ('p', '1. In the beginning God.'), ('note', 'A note.') ] )
        self.assertEqual( parsed.text_differences, [] )

    def test_balanced( self ):
        """ Scofield's list that starts in one verse's note and ends in the next's """
        self.assertEqual( sword.balanced( 'Seven things:<list> <item>(1) he worships' ), 'Seven things:<list> <item>(1) he worships</item></list>' )
        self.assertEqual( sword.balanced( '<hi type="bold">Abel</hi></item> </list> Abel' ), '<hi type="bold">Abel</hi>  Abel' )


class CommentaryTests( unittest.TestCase ):
    def test_parse( self ):
        entries = [ ('GEN', 1, 1, 1, '<br /><scripRef passage="Ge 1:1">1</scripRef> God creates heaven and earth;<br /><scripRef passage="Ge 1:3">3</scripRef> the light.<br />\n<br />\n<br />'
                                  'beginning.<br /><scripRef>Joh 1:1-3; Heb 1:10</scripRef><br /><scripRef>Re 1:8</scripRef><br />God.<br /><scripRef>2:4; 13; Ex 20:11</scripRef>\n') ]
        documents = sword.parse_commentary( { 'id':'TSK', 'sword':{} }, entries, CHAPTERS | { 'JHN':[51], 'HEB':[14] }, 'TSK.zip' )
        parsed = documents['GEN'][0]
        self.assertEqual( [ (entry[2], entry[3]) for entry in parsed.entries ], [ ('1', 'Outline'), ('1:1', 'CrossReferences') ] )
        self.assertEqual( [ anchor[2:] for anchor in parsed.anchors if anchor[2] == 'about' ], [ ('about', 'GEN 1:1-1:31'), ('about', 'GEN 1:1') ] )
        self.assertEqual( [ anchor[3] for anchor in parsed.anchors if anchor[2] == 'cites' ],
                          ['GEN 1:1', 'GEN 1:3', 'JHN 1:1-1:3', 'HEB 1:10', 'REV 1:8', 'GEN 2:4', 'GEN 13', 'EXO 20:11'] ) # (‘13’ after a semicolon is a chapter)
        tokens = parsed.doc.tokens
        texts = [ ''.join( before+text+after for before,text,after,_features in tokens[start:end] ).strip() for _name, _kind, start, end, _text in parsed.doc.paragraphs if end > start ]
        self.assertEqual( texts, ['1 God creates heaven and earth; 3 the light.', 'beginning. Joh 1:1-3; Heb 1:10; Re 1:8', 'God. 2:4; 13; Ex 20:11'] )
        self.assertEqual( parsed.text_differences, [] )

    def test_linked_verses( self ):
        """ A zCom4 module (12-byte slots), with a note linked to two verses: one entry, about both """
        chapters = { BBB:[2] for BBB in sword.BOOKS } # (Every book with one chapter of two verses)
        note = b'A note on verses 1 and 2.'
        memory = io.BytesIO()
        with zipfile.ZipFile( memory, 'w' ) as archive:
            for testament, count in (('ot', 39), ('nt', 27)):
                slots = [ (0, 0, 0) ] * (2 + count * 4) # (Two headers, then each book's heading, its chapter's, and its two verses)
                if testament == 'ot': slots[4] = slots[5] = (0, 0, len(note)) # Genesis 1:1 and 1:2
                compressed = zlib.compress( note )
                archive.writestr( f'c/{testament}.bzv', b''.join( struct.pack( '<III', *slot ) for slot in slots ) )
                archive.writestr( f'c/{testament}.bzs', struct.pack( '<III', 0, len(compressed), len(note) ) )
                archive.writestr( f'c/{testament}.bzz', compressed )
        self.assertEqual( sword.read_commentary( zipfile.ZipFile( memory ), 'c/', 'utf-8', chapters, 12 ), [ ('GEN', 1, 1, 2, note.decode()) ] )

    def test_osis( self ):
        """ Matthew Henry's: the book's introduction and each chapter's outline (before its first ‘Verses’) are entries of their own;
            a chapter with one note, and no ‘Verses’, has it about the whole chapter. Jamieson, Fausset, and Brown's titles stay with the note. """
        pre = lambda n, text: f'<div type="x-milestone" subType="x-preverse" sID="pv{n}"/>{text}<div type="x-milestone" subType="x-preverse" eID="pv{n}"/>'
        entries = [ ('GEN', 0, 0, 0, '<title type="main">Genesis</title>'),
                    ('GEN', 1, 1, 2, pre( 1, '<title type="x-ms">Genesis</title> Genesis means origin. <title type="x-s2">Chapter 1</title> <table><row><cell>Creation.</cell><cell>(1-2)</cell></row></table>' )
                                     + '<hi type="bold">Verses 1-2</hi> God made all things (<reference osisRef="John.1.3">Joh 1:3</reference>).' ),
                    ('GEN', 2, 1, 1, pre( 2, '<title type="x-s2">Chapter 2</title>' ) + 'The sabbath.') ]
        documents = sword.parse_commentary( { 'id':'MHCC', 'sword':{ 'notes':'Commentary' } }, entries, { 'GEN':[2, 3], 'JHN':[51] }, 'MHCC.zip', osis=True )
        genesis = documents['GEN'][0]
        self.assertEqual( [ (entry[2], entry[3]) for entry in genesis.entries ], [ ('Intro', 'BookIntro'), ('1', 'Outline'), ('1:1-2', 'Commentary'), ('2:1-3', 'Commentary') ] )
        self.assertEqual( [ anchor[3] for anchor in genesis.anchors if anchor[2] == 'about' ], ['GEN 1-2', 'GEN 1:1-1:2', 'GEN 1:1-1:2', 'GEN 2:1-2:3'] )
        tokens = genesis.doc.tokens
        texts = [ (name, ''.join( before+text+after for before,text,after,_features in tokens[start:end] ).strip()) for name, _kind, start, end, _text in genesis.doc.paragraphs if end > start ]
        self.assertEqual( texts[:4], [ ('h2', 'Genesis'), ('p', 'Genesis means origin.'), ('h2', 'Chapter 1'), ('li', 'Creation. (1-2)') ] ) # (The book's title only once)
        self.assertEqual( genesis.text_differences, [] )
        entries = [ ('JHN', 1, 1, 1, pre( 3, '<title type="x-s3">Joh 1:1-5. The Word.</title>' ) + '1. In the beginning--before all time.') ]
        john = sword.parse_commentary( { 'id':'JFB', 'sword':{ 'notes':'Commentary' } }, entries, { 'JHN':[51] }, 'JFB.zip', osis=True )['JHN'][0]
        self.assertEqual( [ (entry[2], entry[3]) for entry in john.entries ], [ ('1:1', 'Commentary') ] ) # (A section's title stays with its note)
        self.assertEqual( [ paragraph[0] for paragraph in john.doc.paragraphs if paragraph[3] > paragraph[2] ], ['h2', 'p'] )

    def test_thml_and_clarke( self ):
        """ A ThML module's chapter slot that repeats another note is left out; Barnes's book introductions are about the book too;
            Adam Clarke's preface (at the book's first note) and each chapter's ‘Introduction’ are entries of their own """
        note = 'Verse 44. And the rest.'
        entries = [ ('ACT', 27, 44, 44, note), ('ROM', 1, 0, 0, note), ('ROM', 1, 1, 1, '  ROMANS Chapter One <br /><br /> PREFACE <br /><br /> THE Epistle ... Paul, a servant.'),
                    ('ROM', 1, 3, 3, 'Verse 3. Concerning his Son.') ]
        documents = sword.parse_commentary( { 'id':'Barnes', 'sword':{ 'notes':'Commentary' } }, entries, { 'ACT':[60]*28, 'ROM':[32, 29] }, 'Barnes.zip' )
        romans = documents['ROM'][0]
        self.assertEqual( [ (entry[2], entry[3]) for entry in romans.entries ], [ ('1:1', 'BookIntro'), ('1:3', 'Commentary') ] )
        self.assertEqual( [ anchor[3] for anchor in romans.anchors if anchor[2] == 'about' ][:2], ['ROM 1-2', 'ROM 1:1'] )
        verse = lambda n: f'<div sID="g{n}" type="x-p"/> <hi type="bold">Verse {n}</hi> <div eID="g{n}" type="x-p"/> A note on verse {n}.'
        entries = [ ('GEN', 1, 0, 0, '<chapter n="1" osisID="Gen.1" sID="Gen.1"/> '),
                    ('GEN', 1, 1, 1, '<title type="x-s">Preface to the Book of Genesis</title> Moses wrote it. The creation, <reference osisRef="Gen.1.1">Gen 1:1</reference>.' + verse( 1 ) ),
                    ('GEN', 1, 2, 2, verse( 2 )),
                    ('GEN', 2, 1, 1, '<title type="x-s">Introduction</title> The sabbath, <reference osisRef="Gen.2.1-Gen.2.3">Gen 2:1-3</reference>.' + verse( 1 )) ]
        genesis = sword.parse_commentary( { 'id':'Clarke', 'sword':{ 'notes':'Commentary' } }, entries, { 'GEN':[2, 3] }, 'Clarke.zip', osis=True )['GEN'][0]
        self.assertEqual( [ (entry[2], entry[3]) for entry in genesis.entries ], [ ('Intro', 'BookIntro'), ('1:1', 'Commentary'), ('1:2', 'Commentary'), ('2', 'Outline'), ('2:1', 'Commentary') ] )
        self.assertEqual( genesis.text_differences, [] )


class TitlePageTests( unittest.TestCase ):
    def test_entries( self ):
        class Block:
            def __init__( self, text:str ) -> None: self.text = text
        blocks = [ Block( 'Imprint text.' ), Block( 'Orthodoxy' ), Block( 'I: Introduction' ), Block( 'Some text.' ), Block( 'II: The Maniac' ), Block( 'More.' ),
                   Block( 'Part Two' ), Block( 'It begins here.' ), Block( 'III: Later' ) ]
        contents = [ (1, 'Imprint', 0), (1, 'Orthodoxy', 1), (2, 'I: Introduction', 2), (2, 'II: The Maniac', 4), (1, 'Part Two', 6), (2, 'III: Later', 8) ]
        starts, headings = epub.entry_items( contents, blocks )
        # ‘Orthodoxy’ is only a title page, so its chapters are entries (the title page goes with the first), but ‘Part Two’ has text of its own
        self.assertEqual( starts, { 0:'Imprint', 1:'I: Introduction', 4:'II: The Maniac', 6:'Part Two' } )
        self.assertEqual( headings, { 8:2 } )

    def test_subtitles_and_books( self ):
        class Block:
            def __init__( self, text:str ) -> None: self.text = text
        # A half-title with a subtitle; Book I's page has only its title (in two blocks); Book II's has an epigraph too; chapters are numbered only
        blocks = [ Block( 'Lilith' ), Block( 'A Romance' ), Block( 'Book' ), Block( 'I' ), Block( 'I' ), Block( 'Text.' ), Block( 'II' ), Block( 'Text.' ),
                   Block( 'Book II' ), Block( '“There is a fire”' ), Block( 'I' ), Block( 'Text.' ) ]
        contents = [ (1, 'Lilith', 0), (2, 'Book I', 2), (3, 'I', 4), (3, 'II', 6), (2, 'Book II', 8), (3, 'I', 10) ]
        starts, _headings = epub.entry_items( contents, blocks )
        self.assertEqual( starts, { 0:'Book I, I', 6:'Book I, II', 8:'Book II, I' } )

    def test_collection( self ):
        """ In a collection of stories (several items at the top level have items under them), a chapter labelled only with a number gets its story's title """
        class Block:
            def __init__( self, text:str ) -> None: self.text = text
        blocks = [ Block( 'A Double Story' ), Block( 'I' ), Block( 'Text.' ), Block( 'II' ), Block( 'Text.' ), Block( 'Cross Purposes' ), Block( 'I' ), Block( 'Text.' ) ]
        contents = [ (1, 'A Double Story', 0), (2, 'I', 1), (2, 'II', 3), (1, 'Cross Purposes', 5), (2, 'I', 6) ]
        starts, _headings = epub.entry_items( contents, blocks )
        self.assertEqual( starts, { 0:'A Double Story, I', 3:'A Double Story, II', 5:'Cross Purposes, I' } )


if __name__ == '__main__':
    unittest.main()
