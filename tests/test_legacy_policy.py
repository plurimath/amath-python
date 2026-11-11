"""Explicit legacy mode against fixed source-producer expectations."""
import json
from pathlib import Path
import unittest
import amath as stage

def ordered(value):
    if isinstance(value,dict):
        if set(value)=={'offset','length','line','column','value'}:return value
        return [[key,ordered(child)]for key,child in value.items()]
    if isinstance(value,list):return [ordered(child)for child in value]
    return value

class LegacyPolicyTests(unittest.TestCase):
    def test_fixed_ruby_raw_trees_offsets_and_hash_order(self):
        rows=json.loads((Path(__file__).parent/'legacy-cases.json').read_text())['cases']
        for row in rows:
            with self.subTest(input=row['input']):
                if row['ok']:
                    result=stage.parse_legacy_raw(row['input'],decimal=row.get('decimal','.'))
                    self.assertEqual(ordered(result.tree),ordered(row['tree']))
                else:
                    with self.assertRaises(stage.ParseError)as raised:stage.parse_legacy_raw(row['input'],decimal=row.get('decimal','.'))
                    self.assertEqual(raised.exception.byte_offset,row['byte_offset'])
                    if 'grammar_byte_offset'in row:self.assertEqual(raised.exception.grammar_byte_offset,row['grammar_byte_offset'])

    def test_previously_sorted_hash_members_match_unchanged_ruby_fixture_order(self):
        selected = ['sqrt(x)', '((a,b),(c,d))']
        rows = json.loads((Path(__file__).parent/'raw-cases.json').read_text())
        matched = [row for row in rows if row['input'] in selected and row['ok']]
        self.assertEqual(len(matched), len(selected))
        for row in matched:
            with self.subTest(input=row['input']):
                result = stage.parse_legacy_raw(row['input'], decimal=row.get('decimal','.'))
                self.assertEqual(ordered(result.tree), ordered(row['tree']))


class PlurimathIndexBoundaryTests(unittest.TestCase):
    """Frozen testsuite 0d50db7 rejections.yaml records error.index 2,4,4,7: characters in
    Plurimath's preprocessed text. This package does no AsciiMath preprocessing, so the same
    failing '/' is reported at UTF-8 byte offsets of the unchanged input. Old corpus offsets
    are not rewritten."""
    def test_multibyte_plurimath_preprocessing_cases(self):
        for text,byte,plurimath_text,plurimath_index in [
            ('{:a/',3,'ℒa/',2),('{:x:}a/',6,'ℒxℛa/',4),
            ('(:x:)y/',6,'ᑕxᑐy/',4),('{:a:}(:b:)c/',11,'ℒaℛᑕbᑐc/',7)]:
            with self.subTest(text=text):
                with self.assertRaises(stage.ParseError)as raised:stage.parse_legacy_raw(text)
                error=raised.exception
                self.assertEqual((error.byte_offset,error.char_offset),(byte,byte))
                self.assertEqual((error.grammar_byte_offset,error.grammar_char_offset),(byte,byte))
                self.assertEqual(text.encode()[byte:byte+1],b'/')
                self.assertEqual(plurimath_text[plurimath_index],'/')
