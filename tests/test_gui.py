"""Real Tk controls and isolated in-memory device simulation. No physical USB."""
from pathlib import Path
import os,sys,time,unittest
from unittest.mock import patch
from dataclasses import asdict,replace
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'manager'))
import tkinter as tk
from evilkey_manager.gui import Application
from evilkey_manager.models import DisplaySettings,UserError
from evilkey_manager.widgets import PercentEntry,Slider,setup

@unittest.skipUnless(os.name=='nt' or os.environ.get('DISPLAY'),'Needs Windows desktop or Xvfb')
class GuiTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk();self.errors=[]
        self.root.report_callback_exception=lambda t,v,b:self.errors.append(str(v))
        self.app=Application(self.root,demo=True)
        self.root.update();self.until(lambda:bool(self.app.devices) and not self.app.runner.busy)
        self.dialog=patch('evilkey_manager.gui.messagebox.showerror');self.msg=self.dialog.start();self.addCleanup(self.dialog.stop)
    def tearDown(self):
        errors=list(self.errors)
        self.app.shutdown_ui();self.root.destroy();self.assertEqual(errors,[])
    def until(self,condition,timeout=5):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            self.root.update()
            if condition():return
            time.sleep(.01)
        self.fail('GUI operation did not finish')
    def runop(self,op,extra=None):
        self.app.submit(op,extra);self.until(lambda:not self.app.runner.busy)
        self.assertFalse(self.msg.called)
    def connect(self):self.runop('info');self.app.owner.set(True);self.root.update()
    def screen(self):self.connect();self.runop('display_read')
    def drive(self):self.connect();self.runop('drive_read')
    def test_initial_state_no_authorization(self):
        self.assertIsNone(self.app.info);self.assertFalse(self.app.owner.get());self.assertEqual(self.app.save_btn.cget('state'),'disabled')
    def test_static_header_and_animated_logo_replaces_overview_badge(self):
        header=self.app.logo_header;mark=self.app.logo_overview
        self.assertFalse(hasattr(header,'sheet'));self.assertEqual((header.image.width(),header.image.height()),(62,62))
        self.assertIsNotNone(mark.sheet)
        self.assertEqual((mark.sheet.width(),mark.sheet.height()),(1536,1536))
        self.assertEqual((mark.winfo_width(),mark.winfo_height()),(96,96))
        self.assertLess(mark.winfo_rootx(),mark.master.winfo_children()[1].winfo_rootx())
        self.assertFalse(hasattr(self.app,'logo_hero'))
        before=self.app._logo_phase
        self.until(lambda:self.app._logo_phase!=before,timeout=1)
        self.assertTrue(header.winfo_ismapped());self.assertTrue(mark.winfo_ismapped())
        self.app.book.select(1);self.root.update()
        self.assertFalse(mark.winfo_ismapped())
        self.assertTrue(header.winfo_ismapped())
    def test_preview_never_claims_usb_connection(self):
        self.connect();self.assertIn('Demo mode',self.app.connection.get());self.assertNotIn('Device connected',self.app.connection.get())
    def test_info_requires_explicit_owner(self):
        self.runop('info');self.assertFalse(self.app.owner.get());self.assertFalse(self.app.has_auth())
    def test_busy_locks_inputs_and_device_choice(self):
        self.connect();self.app.submit('display_read')
        self.assertTrue(self.app.runner.busy);self.assertEqual(str(self.app.device_combo.cget('state')),'disabled');self.assertEqual(str(self.app.percent_entries[0].cget('state')),'disabled')
        self.app.submit('info');self.assertTrue(self.app.runner.busy)
        self.until(lambda:not self.app.runner.busy);self.assertEqual(str(self.app.percent_entries[0].cget('state')),'normal')
    def test_read_clean_then_edit_dirty(self):
        self.screen();self.assertFalse(self.app.display_dirty());self.app.screen_vars['brightness'].set('130');self.assertTrue(self.app.display_dirty());self.assertEqual(self.app.save_btn.cget('state'),'normal')
    def test_write_readback_revision(self):
        self.screen();self.app.screen_vars['brightness'].set('130');s=self.app.get_display();self.runop('display_write',{'settings':asdict(s),'display_confirmed':True})
        self.assertEqual(self.app.display_record['settings']['brightness'],130);self.assertEqual(self.app.display_record['settings']['revision'],1);self.assertFalse(self.app.display_dirty())
    def test_percent_edit_not_committed_is_dirty(self):
        self.screen();e=self.app.percent_entries[0];e.display.set('90');self.assertTrue(self.app.display_dirty());self.assertEqual(self.app.get_display().brightness,230)
    def test_invalid_percent_blocks_save(self):
        self.screen();self.app.percent_entries[0].display.set('abc')
        with self.assertRaises(UserError):self.app.get_display()
        self.assertFalse(self.app.runner.busy)
    def test_dark_accent_rejected(self):
        self.screen();self.app.screen_vars['accent_rgb'].set('#000000')
        with self.assertRaises(UserError):self.app.get_display()
    def test_defaults_change_form_only(self):
        self.screen();self.app.screen_vars['brightness'].set('180');self.app.restore_defaults()
        self.assertEqual(self.app.get_display().brightness,90);self.assertFalse(self.app.runner.busy);self.assertEqual(self.app.display_record['settings']['revision'],0)
    def test_fixed_touch_wake_not_fake_toggle(self):
        self.assertEqual(set(self.app.screen_vars),{'brightness','dim_brightness','animation','dim_seconds','off_seconds','presence_seconds','uv_seconds','accent_rgb'})
    def test_off_is_additional_time(self):
        self.assertIn('90 s total',self.app.preview_text.get());self.assertIn('60 s later',self.app.preview_text.get())
    def test_no_dim_means_no_off(self):
        self.app.screen_vars['dim_seconds'].set('0');self.assertIn('disabled',self.app.preview_text.get())
    def test_key_selection_invalidates_session(self):
        self.screen();self.app.selected_device();self.assertIsNone(self.app.info);self.assertIsNone(self.app.display_record);self.assertFalse(self.app.owner.get())
    def test_credentials_filter_binds_to_actual_row(self):
        self.connect();self.runop('credentials');self.app.credential_table.selection_set('0');self.root.update();self.assertEqual(self.app.selected_credential()['rp'],'example.test')
        self.app.filter.set('does-not-exist');self.assertIsNone(self.app.selected_credential())
    def test_all_tabs_render(self):
        for i in range(7):self.app.book.select(i);self.root.update();self.assertGreater(self.app.pages[i].winfo_width(),900)
    def test_small_window_stacks_preview(self):
        self.root.geometry('1050x700');self.app.book.select(3);self.root.update();self.app.reflow();self.root.update();self.assertEqual(self.app.display_right.grid_info()['row'],1)
        self.assertLessEqual(self.app.display_left.winfo_width(),self.app.pages[3].winfo_width())
    def test_source_configuration_roundtrip(self):
        from evilkey_manager.project import DEFAULTS
        self.assertEqual(self.app.project_values(),DEFAULTS)
        self.app.project_vars['FIDO_V1_USB_PROFILE'].set('FIDO compatibility')
        self.app.project_vars['FIDO_V1_USB_TOOL_LAYOUT_DEFAULT'].set('Polish (PL)')
        selected=self.app.project_values()
        self.assertEqual(selected['FIDO_V1_USB_PROFILE'],1)
        self.assertEqual(selected['FIDO_V1_USB_TOOL_LAYOUT_DEFAULT'],1)
    def test_log_uses_public_operation_names(self):
        self.screen();log=' '.join(self.app.public_log);self.assertNotIn('display_read',log);self.assertNotIn('token',log.lower());self.assertNotIn('auth',log.lower())
    def test_cancel_does_not_acknowledge_settings(self):
        self.connect();self.app.submit('display_read');self.app.runner.cancel();self.until(lambda:not self.app.runner.busy);self.assertIsNone(self.app.display_record)
    def test_device_failure_disables_write(self):
        self.screen();self.app.done('display_write',{'type':'error','error':{'message':'Connection interrupted','connection_lost':True}})
        self.assertIsNone(self.app.display_record);self.assertIsNone(self.app.info);self.assertEqual(self.app.save_btn.cget('state'),'disabled')
    def test_manager_drive_read_defaults_to_writable(self):
        self.drive();self.assertFalse(self.app.drive_read_only.get());self.assertFalse(self.app.drive_loaded);self.assertFalse(self.app.drive_dirty());self.assertIn('read and write',self.app.drive_status.get())
    def test_manager_drive_write_read_only_roundtrip(self):
        self.drive();self.app.drive_read_only.set(True);self.root.update();self.assertTrue(self.app.drive_dirty())
        self.runop('drive_write',{'read_only':True,'drive_confirmed':True});self.assertTrue(self.app.drive_read_only.get());self.assertTrue(self.app.drive_loaded);self.assertFalse(self.app.drive_dirty());self.assertIn('read only',self.app.drive_status.get())

@unittest.skipUnless(os.name=='nt' or os.environ.get('DISPLAY'),'Needs Windows desktop or Xvfb')
class WidgetTests(unittest.TestCase):
    def setUp(self):self.root=tk.Tk();setup(self.root)
    def tearDown(self):self.root.destroy()
    def test_all_brightness_values_roundtrip(self):
        v=tk.StringVar(value='90');e=PercentEntry(self.root,v,8,255)
        for raw in range(8,256):v.set(str(raw));e.commit();self.assertEqual(int(v.get()),raw)
    def test_percent_bounds(self):
        v=tk.StringVar(value='90');e=PercentEntry(self.root,v,8,255)
        for value in ('100.01','-1','nan','inf','0','text'):
            e.display.set(value)
            with self.assertRaises(UserError):e.commit()
    def test_timer_slider_uses_useful_steps(self):
        v=tk.StringVar(value='0');s=Slider(self.root,v,0,3600,steps=[0,5,10,30,60,3600]);s.nudge(1);self.assertEqual(v.get(),'5');s.nudge(-1);self.assertEqual(v.get(),'0')
    def test_disabled_slider_cannot_change(self):
        v=tk.StringVar(value='90');s=Slider(self.root,v,8,255);s.configure(state='disabled');s.nudge(1);self.assertEqual(v.get(),'90')

if __name__=='__main__':unittest.main(verbosity=2)
