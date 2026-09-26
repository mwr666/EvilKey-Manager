from pathlib import Path
import csv
import hashlib
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'manager'))

from evilkey_manager.loot import (VARIABLE_MODE, REFLECTION_MODE, INDEXED_MODE,
    KIND_VARIABLE, KIND_REFLECTION, KIND_LEGACY, decode_rows, describe,
    export_csv, read_loot, read_loot_index)
from evilkey_manager.models import UserError


class LootDecoderTests(unittest.TestCase):
    @staticmethod
    def write_index(bin_path: Path, data: bytes, segments: list[tuple[int, int, int]]) -> Path:
        header=bytearray(64);header[:8]=b'PFLOOTI1';header[8]=1;header[9]=64;header[10]=12
        header[12:16]=len(data).to_bytes(4,'little');header[16:18]=len(segments).to_bytes(2,'little')
        header[20:52]=hashlib.sha256(data).digest()
        records=bytearray()
        for offset,length,kind in segments:
            record=bytearray(12);record[:4]=offset.to_bytes(4,'little')
            record[4:8]=length.to_bytes(4,'little');record[8]=kind;records.extend(record)
        path=bin_path.with_suffix('.idx');path.write_bytes(header+records);return path

    def test_variable_exfil_is_explicit_little_endian(self):
        rows=decode_rows(bytes([0x34,0x12,0xFF,0xFF,0x00,0x00]),VARIABLE_MODE)
        self.assertEqual([row['value'] for row in rows],[0x1234,65535,0])
        self.assertEqual(rows[0]['hex'],'34 12')

    def test_variable_exfil_rejects_truncated_record(self):
        with self.assertRaises(UserError):decode_rows(b'\x01',VARIABLE_MODE)

    def test_reflection_preserves_raw_bytes(self):
        rows=decode_rows(b'A\x00\xff',REFLECTION_MODE)
        self.assertEqual([row['value'] for row in rows],[65,0,255])
        self.assertEqual([row['ascii'] for row in rows],['A','.','.'])

    def test_description_and_csv_are_inspectable(self):
        data=b'\x01\x00\x00\x01'
        self.assertIn('2 16-bit records',describe(data,VARIABLE_MODE))
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'loot.csv'
            export_csv(path,decode_rows(data,VARIABLE_MODE),VARIABLE_MODE)
            with path.open(encoding='utf-8-sig',newline='') as handle:rows=list(csv.reader(handle))
            self.assertEqual(rows[0],['index','offset','raw_hex','uint16_le'])
            self.assertEqual(rows[2],['1','2','00 01','256'])

    def test_read_loot_is_local_and_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'loot.bin';path.write_bytes(b'ok')
            self.assertEqual(read_loot(path),b'ok')

    def test_missing_sidecar_keeps_manual_modes_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'capture.bin';data=b'\x01\x00'
            path.write_bytes(data)
            self.assertIsNone(read_loot_index(path,data))

    def test_matching_sidecar_decodes_mixed_segments_in_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'mixed.bin';data=b'\x01\x00\x02\x01A\x00\xff'
            path.write_bytes(data)
            self.write_index(path,data,[(0,4,KIND_VARIABLE),(4,3,KIND_REFLECTION)])
            index=read_loot_index(path,data)
            self.assertIsNotNone(index)
            rows=decode_rows(data,INDEXED_MODE,index)
            self.assertEqual([row['value'] for row in rows],[1,258,65,0,255])
            self.assertEqual([row['segment'] for row in rows],[1,1,2,2,2])
            self.assertEqual(rows[2]['offset'],4)
            self.assertIn('2 segments from mixed.idx',describe(data,INDEXED_MODE,index))

    def test_legacy_segment_is_preserved_as_unknown_raw_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'legacy.bin';data=b'\x01\x00A'
            path.write_bytes(data)
            self.write_index(path,data,[(0,len(data),KIND_LEGACY)])
            index=read_loot_index(path,data);rows=decode_rows(data,INDEXED_MODE,index)
            self.assertEqual([row['value'] for row in rows],[1,0,65])
            self.assertEqual({row['format'] for row in rows},{'Legacy or unknown format'})

    def test_sidecar_rejects_wrong_digest_and_noncontiguous_ranges(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'loot.bin';data=b'AB';path.write_bytes(data)
            idx=self.write_index(path,data,[(0,2,KIND_REFLECTION)])
            raw=bytearray(idx.read_bytes());raw[20]^=0xff;idx.write_bytes(raw)
            with self.assertRaisesRegex(UserError,'does not match'):read_loot_index(path,data)
            self.write_index(path,data,[(1,1,KIND_REFLECTION)])
            with self.assertRaisesRegex(UserError,'invalid range'):read_loot_index(path,data)

    def test_indexed_csv_keeps_segment_and_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'loot.bin';data=b'\x34\x12Z';source.write_bytes(data)
            self.write_index(source,data,[(0,2,KIND_VARIABLE),(2,1,KIND_REFLECTION)])
            index=read_loot_index(source,data);rows=decode_rows(data,INDEXED_MODE,index)
            output=Path(tmp)/'mixed.csv';export_csv(output,rows,INDEXED_MODE)
            with output.open(encoding='utf-8-sig',newline='') as handle:csv_rows=list(csv.reader(handle))
            self.assertEqual(csv_rows[0],['index','segment','format','offset','raw_hex','value','ascii'])
            self.assertEqual(csv_rows[1][1:4],['1','Variable values','0'])
            self.assertEqual(csv_rows[2][1:4],['2','Return data','2'])


if __name__=='__main__':unittest.main(verbosity=2)
