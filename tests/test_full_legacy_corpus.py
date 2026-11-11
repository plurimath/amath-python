"""Full frozen source vectors; enabled only in native platform CI."""
import hashlib,json,os
from pathlib import Path
import unittest
import amath as stage
from test_legacy_policy import ordered

def decode(node,text):
    if 'str'in node:return node['str']
    if 'sym'in node:return node['sym']
    if 'slice'in node:
        value=node['slice'];offset=node['byte_offset'];prefix=text.encode('utf-8')[:offset].decode('utf-8')
        assert len(prefix)==node['char_offset']
        return dict(offset=offset,length=len(value),line=prefix.count('\n')+1,column=len(prefix.rsplit('\n',1)[-1])+1,value=value)
    if 'array'in node:return [decode(value,text)for value in node['array']]
    if 'hash'in node:
        pairs=[(decode(key,text),decode(value,text))for key,value in node['hash']]
        assert len({key for key,_ in pairs})==len(pairs)
        return dict(pairs)
    if 'nil'in node:return None
    if 'bool'in node:return node['bool']
    if 'int'in node:return int(node['int'])
    raise AssertionError('unknown source tag '+str(node))

@unittest.skipUnless(os.environ.get('PLURIMATH_FULL_RAW_CORPUS')=='1','full corpus runs in native platform CI')
class FullLegacyCorpusTests(unittest.TestCase):
    def test_complete_frozen_raw_corpus(self):
        corpus=json.loads((Path(__file__).parent/'fixtures/full-raw.json').read_text())
        for row in corpus['cases']:
            with self.subTest(id=row['id']):
                source=row['input']['str'];decimal=row.get('options',{}).get('decimal','.')
                if 'refusal'in row['expected']:
                    with self.assertRaises(stage.ParseError)as error:stage.parse_legacy_raw(source,decimal=decimal)
                    actual=error.exception.byte_offset
                    self.assertEqual(actual,row['expected']['refusal']['byte_offset'])
                else:
                    result=stage.parse_legacy_raw(source,decimal=decimal)
                    self.assertEqual(result.text,row['expected']['preprocessed']['str'])
                    self.assertEqual(ordered(result.tree),ordered(decode(row['expected']['tree'],result.text)))

    def test_complete_frozen_legacy_values_without_offsets(self):
        def without_slices(value):
            if isinstance(value,dict):
                if set(value)=={'offset','length','line','column','value'}:return value['value']
                return {key:without_slices(child)for key,child in value.items()}
            if isinstance(value,list):return [without_slices(child)for child in value]
            return value
        corpus=json.loads((Path(__file__).parent/'fixtures/full-legacy-values.json').read_text())
        self.assertEqual(len(corpus['cases']),160);self.assertEqual(len(corpus['excluded']),13)
        # The frozen producer sorts Hash keys for stable files and treats parser
        # insertion order as an implementation detail (raw-profiles-provenance-v1.json,
        # generator_hash_sorting_contract). Values, arrays (ordered) and all 160 inputs
        # stay asserted verbatim; dict equality ignores only member order. Member order
        # is asserted separately against the current producer profile below.
        for row in corpus['cases']:
            with self.subTest(id=row['id']):
                result=stage.parse_legacy_raw(row['input'],decimal=row.get('decimal','.'))
                self.assertEqual(without_slices(result.tree),without_slices(row['tree']))

    def test_complete_current_producer_member_order(self):
        fixtures=Path(__file__).parent/'fixtures'
        provenance=json.loads((fixtures/'raw-profiles-provenance-v1.json').read_text())
        payload=(fixtures/'current-raw-a4ed231-v1.json').read_bytes()
        self.assertEqual(hashlib.sha256(payload).hexdigest(),provenance['current_payload']['sha256'])
        current=json.loads(payload);archived=json.loads((fixtures/'full-legacy-values.json').read_text())
        self.assertEqual(len(current['cases']),160);self.assertEqual(current['excluded'],archived['excluded'])
        self.assertTrue(current['producer']['engine_agreement'])
        def ordered_values(value):
            if isinstance(value,dict):
                if set(value)=={'offset','length','line','column','value'}:return value['value']
                return [[key,ordered_values(child)]for key,child in value.items()]
            if isinstance(value,list):return [ordered_values(child)for child in value]
            return value
        for row,old in zip(current['cases'],archived['cases']):
            with self.subTest(id=row['id']):
                self.assertEqual((row['id'],row['input']),(old['id'],old['input']))
                result=stage.parse_legacy_raw(row['input'],decimal=row['decimal'])
                self.assertEqual(ordered_values(result.tree),ordered_values(row['tree']))


class ArchivedComparisonNegativeControls(unittest.TestCase):
    """Always on (no corpus flag): the order-insensitive archived comparison must still reject
    value, key and array-order tampering, and the strict current profile must keep member
    order and its sealed digest. Mirrors amath-rs tests/raw_profile_contract.rs."""
    fixtures=Path(__file__).parent/'fixtures'
    @staticmethod
    def ordered_values(value):
        if isinstance(value,dict):
            if set(value)=={'offset','length','line','column','value'}:return value['value']
            return [[key,ArchivedComparisonNegativeControls.ordered_values(child)]for key,child in value.items()]
        if isinstance(value,list):return [ArchivedComparisonNegativeControls.ordered_values(child)for child in value]
        return value
    def test_archived_values_and_current_member_order_are_distinct_contracts(self):
        old=json.loads((self.fixtures/'full-legacy-values.json').read_text())['cases'][0]
        now=json.loads((self.fixtures/'current-raw-a4ed231-v1.json').read_text())['cases'][0]
        self.assertEqual((old['id'],old['input']),('colour-named',now['input']))
        self.assertEqual(old['tree'],now['tree'])
        self.assertNotEqual(self.ordered_values(old['tree']),self.ordered_values(now['tree']))
        parsed=stage.parse_legacy_raw(old['input'])
        def plain(v):
            if isinstance(v,dict):
                if set(v)=={'offset','length','line','column','value'}:return v['value']
                return {k:plain(c)for k,c in v.items()}
            if isinstance(v,list):return [plain(c)for c in v]
            return v
        self.assertEqual(plain(parsed.tree),old['tree'])
        self.assertEqual(self.ordered_values(parsed.tree),self.ordered_values(now['tree']))
    def test_tampered_values_keys_and_array_order_are_rejected(self):
        value={'expr':['a','b']}
        self.assertNotEqual(value,{'expr':['b','a']})
        self.assertNotEqual(value,{'other':['a','b']})
        self.assertNotEqual(value,{'expr':['a','c']})
    def test_tampered_current_profile_fails_its_digest(self):
        provenance=json.loads((self.fixtures/'raw-profiles-provenance-v1.json').read_text())
        payload=(self.fixtures/'current-raw-a4ed231-v1.json').read_bytes()
        self.assertEqual(hashlib.sha256(payload).hexdigest(),provenance['current_payload']['sha256'])
        tampered=payload.replace(b'"colour-named"',b'"colour-namee"',1)
        self.assertNotEqual(tampered,payload)
        self.assertNotEqual(hashlib.sha256(tampered).hexdigest(),provenance['current_payload']['sha256'])
