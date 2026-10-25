"""Native project export, using synthetic public sources only; no USB."""
from pathlib import Path
import json,sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'manager'))
from evilkey_manager.project import export_project,DEFAULTS,read_header
from evilkey_manager.models import UserError

class NativeProjectExport(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name)
        self.root=self.base/'public';self.fw=self.root/'firmware'
        (self.fw/'EvilKeyV1').mkdir(parents=True)
        self.files={'EvilKey.cmd':b'@echo off\n','SOURCE_CURRENT.json':b'{}',
            'firmware/prepare_arduino.py':b'# synthetic\n',
            'firmware/EvilKeyV1/FidoConfig.h':b'#pragma once\n',
            'firmware/native/0.9.1/verification/partitions.bin':b'fixture'}
        for n,b in self.files.items():
            p=self.root/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
        self.manifest={'schema':'evilkey-public-project-export/1','files':list(self.files)}
        self.save()
    def tearDown(self):self.tmp.cleanup()
    def save(self):
        (self.root/'PUBLIC_EXPORT_FILES.json').write_text(json.dumps(self.manifest),encoding='utf-8')
    def test_complete_launcher_source_and_public_fixtures(self):
        (self.root/'.env').write_text('synthetic secret')
        out=export_project(self.fw,self.base/'out',DEFAULTS)
        for n,b in self.files.items():
            if n.endswith('FidoConfig.h'):continue
            self.assertEqual((out/n).read_bytes(),b)
        self.assertEqual(read_header(out/'firmware/EvilKeyV1/FidoConfig.h'),DEFAULTS)
        self.assertFalse((out/'.env').exists())
    def test_unsafe_members_refused_and_no_partial_output(self):
        for name in ('../outside','C:/outside','firmware/../../outside','.env',
            '.evilkey/settings.json','firmware/native/local-build.json',
            'firmware/signing-key.pem','firmware/key.ekbackup','manager/file.py'):
            with self.subTest(name=name):
                self.manifest['files']=list(self.files)+[name];self.save()
                with self.assertRaises(UserError):export_project(self.fw,self.base/'out',DEFAULTS)
                self.assertFalse((self.base/'out').exists())
    def test_missing_source_and_duplicate_members_refused(self):
        for names in (list(self.files)+['firmware/missing.py'],list(self.files)+['EvilKey.cmd']):
            self.manifest['files']=names;self.save()
            with self.assertRaises(UserError):export_project(self.fw,self.base/'out',DEFAULTS)
    def test_optional_dependency_hash_is_checked(self):
        self.manifest['optional_files']={'firmware/native/0.9.1/dependencies.zip':'0'*64};self.save()
        export_project(self.fw,self.base/'no-bundle',DEFAULTS)
        p=self.fw/'native/0.9.1/dependencies.zip';p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'wrong')
        with self.assertRaises(UserError):export_project(self.fw,self.base/'out',DEFAULTS)
    def test_destination_inside_complete_source_is_refused(self):
        with self.assertRaises(UserError):export_project(self.fw,self.root/'out',DEFAULTS)

if __name__=='__main__':unittest.main()
