from pathlib import Path
import ctypes,dataclasses,hashlib,importlib.util,json,os,random,shutil,subprocess,sys,tempfile,time,unittest
from threading import Event
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'manager'))
from evilkey_manager.models import *
from evilkey_manager.backend import execute,error_public,AUTH_JOBS,MUTATIONS
from evilkey_manager.project import *
from evilkey_manager.jobs import JobRunner
from fake_api import FakeAPI,CtapError

class ModelTests(unittest.TestCase):
    def test_default_wire(self):
        s=DisplaySettings();self.assertEqual(len(s.encode()),32);self.assertEqual(s,DisplaySettings.decode(s.encode()));self.assertEqual(s.encode()[:8],b'PFM1\x01\x5a\x08\x01')
    def test_manager_drive_wire_default_writable(self):
        d=ManagerDriveSettings();self.assertFalse(d.read_only);self.assertEqual(d,ManagerDriveSettings.decode(d.encode()));self.assertEqual(d.encode(),b"PFM2\x01\x00\x00\x00")
    def test_manager_drive_wire_rejects_reserved(self):
        w=bytearray(ManagerDriveSettings(True).encode());w[7]=1
        with self.assertRaises(UserError):ManagerDriveSettings.decode(bytes(w))
    def test_invalid_brightness(self):
        for v in (-1,0,7,256,True,'90'):
            with self.subTest(v=v),self.assertRaises(UserError):dataclasses.replace(DisplaySettings(),brightness=v).validate()
    def test_invalid_times(self):
        for key,v in [('dim_seconds',1),('off_seconds',4),('off_seconds',3601),('presence_seconds',0),('uv_seconds',14),('uv_seconds',121)]:
            with self.subTest(key=key,v=v),self.assertRaises(UserError):dataclasses.replace(DisplaySettings(),**{key:v}).validate()
    def test_disabling_screen_timers(self):self.assertEqual(DisplaySettings(dim_seconds=0,off_seconds=0).validate().dim_seconds,0)
    def test_dark_accent_and_dim_bounds(self):
        for changes in ({'accent_rgb':0},{'dim_brightness':33},{'brightness':8,'dim_brightness':9}):
            with self.assertRaises(UserError):dataclasses.replace(DisplaySettings(),**changes).validate()
    def test_reserved_and_flags(self):
        for position in [0,4,7,24,31]:
            wire=bytearray(DisplaySettings().encode());wire[position]=255
            with self.subTest(position=position),self.assertRaises(UserError):DisplaySettings.decode(bytes(wire))
    def test_import_uses_current_revision(self):
        old=DisplaySettings(revision=100).export();self.assertEqual(DisplaySettings.import_for_revision(old,7).revision,7)
    def test_import_rejects_extra_fields(self):
        v=DisplaySettings().export();v['settings']['pin']='1234'
        with self.assertRaises(UserError):DisplaySettings.import_for_revision(v,1)
    def test_numeric_pin_only(self):
        for pin in ('123','123a','１２３４','1234\n','1'*64):
            with self.subTest(pin=pin),self.assertRaises(UserError):validate_new_pin(pin)
        validate_new_pin('0'*63);validate_existing_pin('oldPin!')
    def test_minimum_pin(self):
        with self.assertRaises(UserError):validate_new_pin('1234',8)
    def test_rp_validation(self):
        self.assertEqual(rp_ids(['EXAMPLE.com'],1),['example.com'])
        for rps in [['https://example.com'],['bad..test'],['example.test','EXAMPLE.test'],['-bad.test']]:
            with self.assertRaises(UserError):rp_ids(rps,120)
    def test_paths_roundtrip(self):
        for p in ['device path',b'\x00\xff\x42']:self.assertEqual(path_unpack(path_pack(p)),p)

class BackendTests(unittest.TestCase):
    def setUp(self):
        self.admin_mock=patch('evilkey_manager.backend.admin_access_available',return_value=True);self.admin_mock.start();self.addCleanup(self.admin_mock.stop)
        self.api=FakeAPI();self.args={'device':descriptor_public(self.api.descriptor),'owner_confirmed':True,'auth':{'method':'panel'},'protocol':2}
        self.args['identity']=device_identity(self.args['device'],bytes(self.api.info.aaguid).hex())
    def runop(self,op,**args):return execute(op,self.args|args,Event(),lambda _:None,self.api)
    def count(self,name):return sum(c[0]==name for c in self.api.calls)
    def test_admin_gate_does_not_touch_USB(self):
        with patch('evilkey_manager.backend.admin_access_available',return_value=False):
            with self.assertRaises(UserError):self.runop('info')
        self.assertEqual(self.count('INIT'),0)
    def test_scan_never_inits(self):self.runop('scan');self.assertEqual(self.count('INIT'),0)
    def test_info_no_token_or_mutation(self):
        data=self.runop('info');self.assertEqual(data['pin_retries'],8);self.assertEqual(self.count('UV_TOKEN'),0);self.assertEqual(self.api.closed,1)
    def test_changed_hid_rejected_before_init(self):
        self.api.hid_change=True
        with self.assertRaises(UserError):self.runop('info')
        self.assertEqual(self.count('INIT'),0)
    def test_changed_identity_rejected(self):
        with self.assertRaises(UserError):self.runop('metadata',identity='other')
        self.assertEqual(self.count('UV_TOKEN'),0);self.assertEqual(self.api.closed,1)
    def test_owner_required(self):
        with self.assertRaises(UserError):self.runop('metadata',owner_confirmed=False)
        self.assertEqual(self.count('UV_TOKEN'),0)
    def test_protocol_never_falls_back(self):
        self.api.info.pin_uv_protocols=[1]
        with self.assertRaises(UserError):self.runop('metadata')
        self.assertEqual(self.count('UV_TOKEN'),0)
    def test_zero_uv_retries_no_attempt(self):
        self.api.uv_retries=0
        with self.assertRaises(UserError):self.runop('metadata')
        self.assertEqual(self.count('UV_TOKEN'),0)
    def test_host_pin_powercycle_no_attempt(self):
        self.api.power=True
        with self.assertRaises(UserError):self.runop('metadata',auth={'method':'host','pin':'123456'})
        self.assertEqual(self.count('PIN_TOKEN'),0)
    def test_credential_metadata_scoped(self):
        self.assertEqual(self.runop('metadata')['existing'],1);self.assertIn(('UV_TOKEN',4),self.api.calls)
    def test_credential_list_excludes_secrets(self):
        rows=self.runop('credentials')['credentials'];encoded=json.dumps(rows)
        self.assertEqual(len(rows),1);self.assertNotIn('SECRET',encoded);self.assertNotIn('large',encoded.lower());self.assertNotIn('token',encoded)
    def test_bad_rp_hash_aborts_full_list(self):
        self.api.rph=b'X'*32
        with self.assertRaises(UserError):self.runop('credentials')
    def test_duplicate_credential_aborts(self):
        self.api.rows.append(self.api.rows[0])
        with self.assertRaises(UserError):self.runop('credentials')
    def test_delete_requires_exact_confirmation(self):
        row=self.runop('credentials')['credentials'][0]
        with self.assertRaises(UserError):self.runop('delete_credential',credential=row,confirmation='DELETE')
        self.assertEqual(self.count('DELETE'),0)
    def test_delete_rechecks_selected_credential(self):
        row=self.runop('credentials')['credentials'][0];self.api.rows[0][6]['id']=b'OTHER'
        with self.assertRaises(UserError):self.runop('delete_credential',credential=row,confirmation='DELETE:'+row['credential_id'])
        self.assertEqual(self.count('DELETE'),0)
    def test_delete_once(self):
        row=self.runop('credentials')['credentials'][0]
        self.runop('delete_credential',credential=row,confirmation='DELETE:'+row['credential_id']);self.assertEqual(self.count('DELETE'),1)
    def test_rename_preserves_user_id(self):
        row=self.runop('credentials')['credentials'][0];self.runop('rename_credential',credential=row,confirmation='RENAME:'+row['credential_id'],name='new',display_name='New')
        self.assertEqual(self.api.rows[0][6]['id'],bytes.fromhex(row['user_id']));self.assertEqual(self.count('RENAME'),1)
    def test_m1_read_signing_and_scope(self):
        result=self.runop('display_read');self.assertEqual(result['settings']['off_seconds'],60);self.assertIn(('UV_TOKEN',32),self.api.calls)
    def test_m1_write_revision(self):
        s=DisplaySettings(brightness=140)
        result=self.runop('display_write',settings=asdict(s),display_confirmed=True)
        self.assertEqual(result['settings']['revision'],1);self.assertEqual(self.count('CONFIG'),1)
    def test_m1_stale_revision_not_retried(self):
        self.api.settings=dataclasses.replace(self.api.settings,revision=7)
        with self.assertRaises(CtapError):self.runop('display_write',settings=asdict(DisplaySettings()),display_confirmed=True)
        self.assertEqual(self.count('CONFIG'),1)
    def test_manager_drive_read_default_writable(self):
        result=self.runop('drive_read');self.assertFalse(result['settings']['read_only']);self.assertTrue(result['compiled']);self.assertTrue(result['enabled']);self.assertIn(('UV_TOKEN',32),self.api.calls)
    def test_manager_drive_write_read_only(self):
        result=self.runop('drive_write',read_only=True,drive_confirmed=True);self.assertTrue(result['settings']['read_only']);self.assertTrue(self.api.drive.read_only);self.assertEqual(self.count('CONFIG'),1)
    def test_manager_drive_write_requires_confirmation(self):
        with self.assertRaises(UserError):self.runop('drive_write',read_only=True)
    def test_manager_drive_write_rejects_non_boolean_mode(self):
        with self.assertRaises(UserError):self.runop('drive_write',read_only='false',drive_confirmed=True)
        self.assertEqual(self.count('UV_TOKEN'),0);self.assertEqual(self.count('CONFIG'),0)
    def test_m1_invalid_form_before_token(self):
        s=asdict(DisplaySettings());s['brightness']=0
        with self.assertRaises(UserError):self.runop('display_write',settings=s,display_confirmed=True)
        self.assertEqual(self.count('UV_TOKEN'),0);self.assertEqual(self.count('CONFIG'),0)
    def test_auth_failure_no_retry(self):
        self.api.fail=CtapError(0x31)
        with self.assertRaises(CtapError):self.runop('metadata')
        self.assertEqual(self.count('UV_TOKEN'),1)
    def test_always_uv_no_double_toggle(self):
        self.runop('always_uv',enabled=False,policy_confirmed=True);self.assertEqual(self.count('ALWAYS_UV'),0)
        self.runop('always_uv',enabled=True,policy_confirmed=True);self.assertEqual(self.count('ALWAYS_UV'),1)
        self.runop('always_uv',enabled=True,policy_confirmed=True);self.assertEqual(self.count('ALWAYS_UV'),1)
    def test_minimum_never_lowered(self):
        self.api.info.min_pin_length=8
        with self.assertRaises(UserError):self.runop('pin_policy',minimum=4,rp_ids=[],force_change=False,replace_rp_list=True,policy_confirmed=True)
        self.assertEqual(self.count('POLICY'),0)
    def test_minimum_rp_replacement_explicit(self):
        with self.assertRaises(UserError):self.runop('pin_policy',minimum=8,rp_ids=[],force_change=False,policy_confirmed=True)
        self.assertEqual(self.count('UV_TOKEN'),0)
    def test_minimum_policy_sent(self):
        self.runop('pin_policy',minimum=8,rp_ids=['example.com'],force_change=True,replace_rp_list=True,policy_confirmed=True)
        self.assertIn(('POLICY',8,['example.com'],True),self.api.calls)
    def test_new_pin_alphanumeric_refused(self):
        with self.assertRaises(UserError):self.runop('change_pin',old_pin='oldPin!',new_pin='newPin!',pin_confirmed=True)
        self.assertEqual(self.count('CHANGE_PIN'),0)
    def test_pin_set_existing_state_rejected(self):
        with self.assertRaises(UserError):self.runop('set_pin',new_pin='123456',pin_confirmed=True)
        self.assertEqual(self.count('SET_PIN'),0)
    def test_numeric_pin_change(self):self.runop('change_pin',old_pin='oldPin!',new_pin='938473',pin_confirmed=True);self.assertEqual(self.count('CHANGE_PIN'),1)
    def test_reset_requires_exact_phrase(self):
        with self.assertRaises(UserError):self.runop('reset',confirmation='RESET')
        self.assertEqual(self.count('RESET'),0)
    def test_reset_once(self):self.runop('reset',confirmation='RESET EVILKEY');self.assertEqual(self.count('RESET'),1)
    def test_vendor_rk(self):
        self.runop('resident_keys',enabled=False,policy_confirmed=True);self.assertFalse(self.api.info.options['rk']);self.assertEqual(self.count('CONFIG'),1)
    def test_vendor_uv_conflict(self):
        self.api.info.options['alwaysUv']=True
        with self.assertRaises(UserError):self.runop('makecred_uv',enabled=True,policy_confirmed=True)
        self.assertEqual(self.count('CONFIG'),0)
    def test_error_never_raw_exception(self):
        err=error_public(ValueError('PIN=do_not_log'),True);self.assertNotIn('do_not_log',json.dumps(err));self.assertIn('may already have been applied',err['message'])
    def test_ctap_error_preserves_code_not_message(self):
        err=error_public(CtapError(0x31));self.assertEqual(err['ctap'],0x31);self.assertNotIn('sensitive',json.dumps(err))
    def test_closed_even_after_usb_failure(self):
        self.api.fail=OSError('private raw detail')
        with self.assertRaises(OSError):self.runop('metadata')
        self.assertEqual(self.api.closed,1)

class ProjectTests(unittest.TestCase):
    def test_header_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'FidoConfig.h';path.write_text(render_header(DEFAULTS));self.assertEqual(read_header(path),DEFAULTS)
    def test_expression_never_evaluated(self):
        with self.assertRaises(UserError):parse_value('__import__("os").system("echo bad")')
    def test_string_comment_markers_roundtrip(self):
        self.assertEqual(parse_value('"OEM // lab" // actual comment'),'OEM // lab')
    def test_numeric_suffix(self):self.assertEqual(parse_value('0x4DE3C1UL // comment'),0x4DE3C1)
    @unittest.skipUnless((ROOT/'firmware/EvilKeyV1/FidoConfig.h').is_file(), 'Firmware source is distributed separately')
    def test_current_header_supported(self):self.assertEqual(read_header(ROOT/'firmware/EvilKeyV1/FidoConfig.h'),DEFAULTS)
    def test_no_physical_confirmation_rejected(self):
        with self.assertRaises(UserError):validate_config(DEFAULTS|{'FIDO_V1_LOCAL_UV':0,'FIDO_V1_TOUCH_CONFIRM':0,'FIDO_V1_BOOT_CONFIRM_FALLBACK':0})
    def test_no_display_with_uv_rejected(self):
        with self.assertRaises(UserError):validate_config(DEFAULTS|{'FIDO_V1_DISPLAY':0})
    def test_manager_drive_defaults_and_identity_roundtrip(self):
        cfg=validate_config(dict(DEFAULTS))
        self.assertEqual(cfg['FIDO_V1_MANAGER_DRIVE'],1)
        self.assertEqual(cfg['FIDO_V1_MANAGER_DRIVE_DEFAULT'],0)
        self.assertEqual(cfg['FIDO_V1_MANAGER_DRIVE_READ_ONLY_DEFAULT'],0)
        self.assertEqual(cfg['FIDO_V1_MANAGER_DRIVE_VID'],0xFEFF)
        self.assertEqual(cfg['FIDO_V1_MANAGER_DRIVE_PID'],0xFCFC)
        self.assertEqual(cfg['FIDO_V1_MANAGER_DRIVE_SD_HZ'],20000000)
    def test_manager_drive_default_on_requires_feature(self):
        with self.assertRaises(UserError):
            validate_config(DEFAULTS|{'FIDO_V1_MANAGER_DRIVE':0,'FIDO_V1_MANAGER_DRIVE_DEFAULT':1})
    def test_manager_drive_rejects_invalid_sd_clock(self):
        with self.assertRaises(UserError):
            validate_config(DEFAULTS|{'FIDO_V1_MANAGER_DRIVE_SD_HZ':26000000})
    def test_usb_tool_defaults_and_identity_roundtrip(self):
        cfg=validate_config(dict(DEFAULTS))
        self.assertEqual(cfg['FIDO_V1_USB_TOOL'],1)
        self.assertEqual(cfg['FIDO_V1_USB_TOOL_DEFAULT'],0)
        self.assertEqual(cfg['FIDO_V1_USB_TOOL_LAYOUT_DEFAULT'],0)
        self.assertEqual(cfg['FIDO_V1_USB_TOOL_VID'],0xFEFF)
        self.assertEqual(cfg['FIDO_V1_USB_TOOL_PID'],0xFCFB)
        self.assertEqual(cfg['FIDO_V1_USB_TOOL_SD_HZ'],20000000)
        self.assertEqual(cfg['FIDO_V1_USB_TOOL_MAX_PAYLOAD'],262144)
    def test_usb_tool_default_on_requires_feature(self):
        with self.assertRaises(UserError):
            validate_config(DEFAULTS|{'FIDO_V1_USB_TOOL':0,'FIDO_V1_USB_TOOL_DEFAULT':1})
    def test_usb_tool_rejects_invalid_layout_and_conflicting_default_role(self):
        with self.assertRaises(UserError):
            validate_config(DEFAULTS|{'FIDO_V1_USB_TOOL_LAYOUT_DEFAULT':5})
        with self.assertRaises(UserError):
            validate_config(DEFAULTS|{'FIDO_V1_USB_TOOL_DEFAULT':1,'FIDO_V1_MANAGER_DRIVE_DEFAULT':1})
    def test_existing_folder_never_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'keep').write_text('unchanged')
            with self.assertRaises(UserError):export_project(ROOT/'firmware',p,DEFAULTS)
            self.assertEqual((p/'keep').read_text(),'unchanged')
    @unittest.skipUnless((ROOT/'firmware/prepare_arduino.py').is_file(), 'Firmware source is distributed separately')
    def test_full_export_creates_project_not_patch(self):
        with tempfile.TemporaryDirectory() as d:
            dest=Path(d)/'new';export_project(ROOT/'firmware',dest,DEFAULTS)
            for p in ['prepare_arduino.py','templates/port/ws_settings_store.c','templates/port/ws_usb_tool_state.c','EvilKeyV1/FidoConfig.h','EvilKeyV1/partitions.csv','EvilKeyV1/src/PicoFidoArduino.cpp','EvilKeyV1/src/UsbTool.cpp','EvilKeyV1/src/PfUsbMsc.cpp','EvilKeyV1/src/PfUsbMsc.h']:
                self.assertTrue((dest/p).is_file(),p)
            self.assertEqual(read_header(dest/'EvilKeyV1/FidoConfig.h'),DEFAULTS)
            rendered=(dest/'EvilKeyV1/FidoConfig.h').read_text()
            self.assertIn('FIDO_V1_USB_TOOL',rendered)
            self.assertIn('FIDO_V1_USB_TOOL_LAYOUT_DEFAULT',rendered)
            for name,value in AIR_MOUSE_USB_DEFINITIONS.items():
                self.assertIn(f'#define {name} {value}',rendered)
            metadata=json.loads((dest/'MANAGER_EXPORT.json').read_text())
            self.assertFalse(metadata['device_write_performed'])
            self.assertEqual(metadata['source_release'],'0.7.4')
            self.assertEqual(metadata['manager_release'],'1.1.6')

    def test_export_excludes_app_packages_and_build_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);source=base/'source';destination=base/'export'
            (source/'EvilKeyV1/src/apps').mkdir(parents=True)
            (source/'prepare_arduino.py').write_text('# synthetic source\n')
            (source/'EvilKeyV1/src/apps/ek_vm.c').write_text('/* interpreter */\n')
            (source/'EvilKeyV1/private.ekapp').write_bytes(b'private app')
            (source/'build-arduino/apps-tests').mkdir(parents=True)
            (source/'build-arduino/apps-tests/guest.wasm').write_bytes(b'guest')
            (source/'release').mkdir()
            (source/'release/private.ekapp').write_bytes(b'private app')
            export_project(source,destination,DEFAULTS)
            self.assertTrue((destination/'EvilKeyV1/src/apps/ek_vm.c').is_file())
            self.assertFalse((destination/'EvilKeyV1/private.ekapp').exists())
            self.assertFalse((destination/'build-arduino').exists())
            self.assertFalse((destination/'release').exists())
    def test_frozen_manager_finds_separate_firmware_next_to_exe(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'manager').mkdir()
            (root/'firmware'/'EvilKeyV1').mkdir(parents=True)
            (root/'firmware'/'prepare_arduino.py').touch()
            (root/'firmware'/'EvilKeyV1'/'FidoConfig.h').touch()
            with patch.object(sys,'frozen',True,create=True), patch.object(sys,'executable',str(root/'manager'/'EvilKeyManager.exe')):
                self.assertEqual(find_firmware_source(),root/'firmware')
    def test_manager_exe_does_not_embed_firmware_source(self):
        spec=(ROOT/'packaging'/'manager.spec').read_text(encoding='utf-8')
        self.assertNotIn("(str(ROOT / 'firmware'), 'firmware')",spec)

@unittest.skipUnless((ROOT/'firmware/prepare_arduino.py').is_file(), 'Firmware source is distributed separately')
class IntegrationTests(unittest.TestCase):
    def test_usb_tool_auto_detach_requires_idle_and_post_write_flush(self):
        text=(ROOT/'firmware/EvilKeyV1/src/UsbTool.cpp').read_text()
        adapter=(ROOT/'firmware/EvilKeyV1/src/PicoFidoArduino.cpp').read_text()
        msc=(ROOT/'firmware/EvilKeyV1/src/PfUsbMsc.cpp').read_text()
        self.assertIn('PF_STORAGE_AUTO_DETACH_IDLE_MS 10000U',text)
        self.assertIn('pf_usb_tool_storage_arm_auto_detach();',text)
        self.assertIn('PF_USB_TOOL_AUTO_DETACH_WAIT_SYNC',text)
        self.assertIn('Completed - waiting for flush/eject',text)
        self.assertIn('Completed - storage detached',text)
        self.assertIn('s_tool_storage_host_write_seen=true;',adapter)
        self.assertIn('s_tool_storage_sync_after_last_write=false;',adapter)
        self.assertIn('tool_storage_scsi_complete',adapter)
        self.assertIn('PF_SCSI_SYNCHRONIZE_CACHE_10 = 0x35U',msc)
        self.assertIn('tud_msc_scsi_complete_cb',msc)
        self.assertIn('Eject DUCKY before %s',text)
        self.assertIn('if(!prepare_local_sd_access("RUN"))return false;',text)
        self.assertIn('if(s_script_running || !s_storage_was_exposed || pf_usb_tool_storage_present())return;',text)
        self.assertIn('prepare_local_sd_access("post-eject refresh")',text)
        self.assertIn('ulTaskNotifyTake(pdTRUE,pdMS_TO_TICKS(100U))',text)
        self.assertIn('handle_storage_auto_detach();',text)
        self.assertIn('handle_storage_eject();',text)
        self.assertNotIn('ducky_run(script,len,&io,&cfg);\n    stage8_cleanup();\n    if(s_attackmode!=1U',text)

    def test_harvest_exposes_storage_after_worker_is_armed(self):
        base=ROOT/'microSD_EVILKEY_EXAMPLES/duckyscripts/library/credentials/Harvest'
        payload=(base/'payload.txt').read_text(encoding='utf-8-sig')
        script=(base/'sy_cred.ps1').read_text(encoding='utf-8-sig')
        helper=(ROOT/'microSD_EVILKEY_EXAMPLES/duckyscripts/helpers/SafeEject.ps1').read_text(encoding='utf-8-sig')
        self.assertTrue(payload.startswith('ATTACKMODE HID\n'))
        self.assertLess(payload.index('PicoFidoWindow'),payload.rindex('ATTACKMODE HID STORAGE'))
        self.assertNotIn('DELAY 30000',payload)
        self.assertNotIn('DELAY 300000',payload)
        self.assertIn('WAIT_FOR_SCROLL_CHANGE',payload)
        self.assertIn('RESTORE_HOST_KEYBOARD_LOCK_STATE',payload)
        self.assertIn("duckyscripts\\helpers\\SafeEject.ps1",script)
        self.assertIn('-SignalScrollLock',script)
        self.assertNotIn('class PicoFidoStorage',script)
        self.assertIn('Write-VolumeCache -DriveLetter',helper)
        self.assertIn('FSCTL_LOCK_VOLUME = 0x00090018',helper)
        self.assertIn('FSCTL_DISMOUNT_VOLUME = 0x00090020',helper)
        self.assertIn('IOCTL_STORAGE_EJECT_MEDIA = 0x002D4808',helper)
        self.assertIn('[PicoFidoSafeRemovalR36]::Eject',helper)
        self.assertIn('[PicoFidoSafeRemovalR36]::SignalScrollLock()',helper)
        self.assertNotIn('Set-MpPreference',script)
        self.assertNotIn('Add-MpPreference',script)
        self.assertNotIn('$defenderDisabled',script)
        self.assertIn('Get-MpComputerStatus -ErrorAction Stop',script)
        self.assertIn('Remove-MpPreference -ExclusionPath $legacyExclusion',script)
        self.assertNotIn('Write-PayloadLog',script[script.index('$safeEject ='):])

    def test_source_hook_placement(self):
        spec=importlib.util.spec_from_file_location('m1_source',ROOT/'firmware/tools/manager_source.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        # Literal anchor fixture from pinned cbor_config.c, not a full parser test.
        fixture='''#include "pico_time.h"
    uint8_t *verify_payload = (uint8_t *) calloc(1, 32 + 1 + 1 + raw_subpara_len);
    memcpy(verify_payload + 34, raw_subpara, raw_subpara_len);
    error = verify();
    if (!(paut.permissions & CTAP_PERMISSION_ACFG)) {
        CBOR_ERROR(CTAP2_ERR_PIN_AUTH_INVALID);
    }
'''
        out=mod.config_source(fixture);self.assertGreater(out.index('#include "ws_manager_config.h"'),out.index('error = verify'))
        self.assertGreater(out.index('#include "ws_manager_config.h"'),out.index('paut.permissions & CTAP_PERMISSION_ACFG'))
        self.assertIn('if (!verify_payload)',out)
        with self.assertRaises(RuntimeError):mod.config_source(out)
        with self.assertRaises(RuntimeError):mod.config_source('unknown source')
    def test_button_uses_runtime_timeout(self):
        spec=importlib.util.spec_from_file_location('m1',ROOT/'firmware/tools/manager_source.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        out=mod.button_source('#include "ws_board.h"\n(uint32_t)FIDO_V1_PRESENCE_TIMEOUT_SECONDS * 1000u');self.assertIn('ws_settings_presence_timeout_ms()',out)
    def test_new_sources_in_generation(self):
        text=(ROOT/'firmware/prepare_arduino.py').read_text()
        for part in ['ws_settings_codec.c','ws_settings_store.c','glob("*.inc")','"0.7.4"',"card_worker.c.inc"]:self.assertIn(part,text)
    def test_fido_worker_stack_is_static_and_launch_failure_is_reported(self):
        usb=(ROOT/'firmware/EvilKeyV1/src/engine/sdk/src/usb/usb.c').read_text()
        header=(ROOT/'firmware/EvilKeyV1/src/engine/sdk/src/usb/usb.h').read_text()
        hid=(ROOT/'firmware/EvilKeyV1/src/engine/sdk/src/usb/hid/hid.c').read_text()
        template=(ROOT/'firmware/templates/card_worker.c.inc').read_text()
        for text in (usb,template):
            self.assertIn('PF_CARD_WORKER_STACK_BYTES 16384U',text)
            self.assertIn('static StackType_t s_card_worker_stack[PF_CARD_WORKER_STACK_BYTES]',text)
            self.assertIn('xTaskCreateStaticPinnedToCore(',text)
            self.assertIn('while (true)',text)
            self.assertIn('xTaskNotifyGive(hcore1)',text)
        self.assertIn('extern bool card_start(',header)
        self.assertEqual(hid.count('if (!card_start(ITF_HID,'),2)
        self.assertNotIn('hcore1 = NULL;',usb[usb.index('void card_exit(void)'):usb.index('extern void hid_task(void)')])
    def test_ducky_worker_stack_is_static_and_persistent(self):
        source=(ROOT/'firmware/EvilKeyV1/src/UsbTool.cpp').read_text()
        self.assertIn('PF_DUCKY_WORKER_STACK_BYTES 8192U',source)
        self.assertIn('static StackType_t s_worker_stack[PF_DUCKY_WORKER_STACK_BYTES]',source)
        self.assertIn('xTaskCreateStaticPinnedToCore(',source)
        self.assertIn('while(true)',source)
        self.assertIn('xTaskNotifyGive(s_worker)',source)
        self.assertNotIn('xTaskCreatePinnedToCore(run_task,"ducky",8192',source)
        self.assertNotIn('s_task=nullptr;vTaskDelete(nullptr)',source)
    def test_usb_tool_cold_tables_are_explicitly_allocated_in_psram(self):
        source=(ROOT/'firmware/EvilKeyV1/src/UsbTool.cpp').read_text()
        self.assertIn('static char **s_scripts;',source)
        self.assertIn('static pf_language_entry_t *s_languages;',source)
        self.assertIn('static pf_loot_segment_t *s_loot_segments;',source)
        self.assertIn('const uint32_t caps=MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT;',source)
        self.assertEqual(source.count('heap_caps_calloc('),3)
        self.assertIn('if(!ensure_psram_tables())',source)
        self.assertIn('Cannot allocate USB Tool PSRAM',source)
        self.assertNotIn('static char *s_scripts[MAX_SCRIPTS]',source)
        self.assertNotIn('static pf_language_entry_t s_languages[MAX_LANGUAGES]',source)
        self.assertNotIn('static pf_loot_segment_t s_loot_segments[PF_LOOT_INDEX_MAX_SEGMENTS]',source)
    @unittest.skipUnless(shutil.which('cc') and os.name!='nt','Native Unix C compiler unavailable')
    def test_wire_python_C_interop(self):
        with tempfile.TemporaryDirectory() as d:
            wrap=Path(d)/'codec.c';so=Path(d)/'codec.so'
            wrap.write_text('#include "ws_settings.h"\nint roundtrip(const unsigned char*p,unsigned n,unsigned char*out){ws_settings_t s;if(!ws_settings_decode(p,n,&s))return 0;ws_settings_encode(&s,out);return 1;}')
            subprocess.run(['cc','-shared','-fPIC','-I',str(ROOT/'firmware/templates/port'),str(wrap),str(ROOT/'firmware/templates/port/ws_settings_codec.c'),'-o',str(so)],check=True)
            lib=ctypes.CDLL(str(so));lib.roundtrip.argtypes=[ctypes.c_char_p,ctypes.c_uint,ctypes.c_void_p];lib.roundtrip.restype=ctypes.c_int
            rng=random.Random(20260916)
            for _ in range(200):
                bright=rng.randint(32,255);s=DisplaySettings(brightness=bright,dim_brightness=rng.randint(1,32),dim_seconds=rng.randint(5,3600),off_seconds=rng.randint(5,3600),presence_seconds=rng.randint(1,120),uv_seconds=rng.randint(15,120),revision=rng.randint(0,2**32-1))
                data=s.encode();out=ctypes.create_string_buffer(32);self.assertEqual(lib.roundtrip(data,32,out),1);self.assertEqual(out.raw,data)
            self.assertEqual(lib.roundtrip(b'X'*32,32,out),0)
class ManagerWorkerTests(unittest.TestCase):
    def test_worker_has_no_library_fallback_or_secret_error(self):
        request=json.dumps({'operation':'info','args':{'pin':'DO_NOT_PRINT_SECRET'}})+'\n'
        result=subprocess.run([sys.executable,str(ROOT/'manager/run_manager.py'),'--worker'],input=request,text=True,capture_output=True,timeout=10)
        self.assertNotIn('DO_NOT_PRINT_SECRET',result.stdout+result.stderr)
        parsed=json.loads(result.stdout.strip().splitlines()[-1]);self.assertEqual(parsed['type'],'error')
    def test_job_result_pipe(self):
        with tempfile.TemporaryDirectory() as d:
            child=Path(d)/'child.py';child.write_text('import sys,json\nreq=json.loads(sys.stdin.readline())\nprint(json.dumps({"type":"result","data":{"ok":True}}),flush=True)\n')
            done=[];runner=JobRunner(child,lambda _:None,lambda op,r:done.append(r));runner.start('info',{})
            deadline=time.monotonic()+5
            while runner.busy and time.monotonic()<deadline:runner.pump();time.sleep(.02)
            self.assertFalse(runner.busy);self.assertTrue(done[0]['data']['ok'])
    def test_job_refuses_queue_and_kills_only_worker(self):
        with tempfile.TemporaryDirectory() as d:
            child=Path(d)/'child.py';child.write_text('import time,sys\nsys.stdin.readline()\ntime.sleep(30)\n')
            done=[];runner=JobRunner(child,lambda _:None,lambda op,r:done.append(r));runner.start('display_write',{})
            with self.assertRaises(UserError):runner.start('reset',{})
            runner.cancel();runner.cancel_at=time.monotonic()-4
            deadline=time.monotonic()+5
            while runner.busy and time.monotonic()<deadline:runner.pump();time.sleep(.02)
            self.assertFalse(runner.busy);self.assertEqual(done[0]['type'],'error');self.assertIn('may already have been applied',done[0]['error']['message'])

if __name__=='__main__':unittest.main(verbosity=2)
