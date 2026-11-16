"""
Search-form normalisation, and matching of original-language tokens to OET word-table rows.

The normalisation rules here are provisional -- they're enough to prove the pipeline, but need review per language.
"""
import re
import unicodedata

_HEBREW_NOT_CONSONANT_RE = re.compile( '[^א-ת]' )
_HEBREW_CANTILLATION_RE = re.compile( '[֑-ֽ֯⁠]' )


def _strip_marks( text:str ) -> str:
    return ''.join( character for character in unicodedata.normalize( 'NFD', text ) if unicodedata.category( character ) != 'Mn' )

def greek( text:str ) -> str:
    """ Lower-case, no accents or breathings, no final-sigma distinction. """
    return unicodedata.normalize( 'NFC', _strip_marks( text ).lower().replace( 'ς', 'σ' ) )

def hebrew_consonants( text:str ) -> str:
    return _HEBREW_NOT_CONSONANT_RE.sub( '', text )

def hebrew_vowelled( text:str ) -> str:
    """ Keeps vowel points but drops cantillation marks and morpheme joiners. """
    return _HEBREW_CANTILLATION_RE.sub( '', text )

def latin( text:str ) -> str:
    """ Lower-case, no diacritics, no modifier letters (so OET-LV ‘Yaʸsous’ becomes ‘yasous’). """
    return ''.join( character for character in _strip_marks( text ).casefold() if unicodedata.category( character ) != 'Lm' )

NORMALISERS = { 'Latn':latin, 'Grek':greek, 'Hebr':hebrew_vowelled }


def match_sequences( a:list, b:list, window:int=12 ) -> list:
    """
    Pair up the equal items of two nearly-identical sequences, in order.

    Greedy with a small look-ahead to resynchronise after insertions and deletions
    (which is all that's needed for two editions of the same text, and is linear time).
    A single differing item between two equal neighbours (e.g., a spelling difference) is paired by position.
    """
    pairs = []
    i = j = 0
    lenA, lenB = len(a), len(b)
    while i < lenA and j < lenB:
        if a[i] == b[j]:
            pairs.append( (i,j) ); i += 1; j += 1
            continue
        if pairs and pairs[-1] == (i-1,j-1) and i+1 < lenA and j+1 < lenB and a[i+1] == b[j+1]:
            pairs.append( (i,j) ); i += 1; j += 1 # Substitution
            continue
        found = None
        for distance in range( 1, window+1 ):
            for di in range( distance+1 ):
                dj = distance - di
                if i+di < lenA and j+dj < lenB and a[i+di] == b[j+dj] and a[i+di+1:i+di+2] == b[j+dj+1:j+dj+2]:
                    found = (di,dj); break
            if found: break
        if found: i += found[0]; j += found[1]
        else: i += 1; j += 1
    return pairs
