"""CW Counter prototype. Starts idle. Captures only after explicit user action."""
import bootstrap
import json
import time
import tkinter as tk
from tkinter import messagebox, filedialog
from dataclasses import asdict
from PIL import Image, ImageTk
from counter import CounterSession
from catalog import Catalog, ALL_MAPS, BUILTIN, CUSTOM, settings_profile
from recognition import Calibration
from pixel_ocr import RapidReader
from map_reader import MapMonitor,title_box
from auto_calibration import AutoRegion,valid_box
from character_reader import CharacterMonitor,character_box
from diagnostics import DiagnosticRecorder
from hud_exp import HudReader,ExpLedger,HudSampler,search_box as hud_search_box
import windows_capture as capture
from sidebar_ui import build_interface, update_dashboard

CONFIG = bootstrap.ROOT / 'settings.json'
OUTPUT = bootstrap.ROOT / 'sessions'
VERSION = '0.20'


class App:
    def __init__(self, root):
        self.root = root
        root.title(f'CW Counter · {VERSION}')
        self.running = False
        self.diagnostic=None
        self.tick_job = None
        self.session = CounterSession()
        self.calibration = None
        self.reader = None
        self.hwnd = None
        self.last_frame = None
        self.last_tick = None
        self.was_valid = False
        self.last_status = ''
        self.settings = {}
        try:
            self.settings = json.loads(CONFIG.read_text('utf-8'))
        except (OSError, ValueError):
            pass
        self.catalog = Catalog()
        self.custom_text = self.settings.get('monsters', '')
        self.mode = tk.StringVar(value=self.settings.get('catalog_mode', BUILTIN))
        self.multiplier = tk.StringVar(value=self.settings.get('exp_multiplier', '1'))
        self.auto_map = tk.BooleanVar(value=self.settings.get('auto_map',True))
        self.map_monitor = None
        self.active_map = None
        self.auto_region = None
        self.needs_resume = True
        self.geometry_key = None
        self.geometry_since = 0.0
        self.last_geometry = None
        self.last_header_box = None
        self.bound_title = ''
        self.character_monitor = None
        self.hud_reader=HudReader();self.exp_ledger=ExpLedger()
        self.hud_sampler=None
        self.hud_missing_since=None
        self.hud_log_at=-100.;self.hud_log_reading=None;self.hud_sample_count=0
        self.hud_topup=tk.BooleanVar(value=True)
        self.reconnect_at = -100.0
        self.last_health = -100.0
        self.error_streak = 0
        self.health_window=dict(frames=0,total_ms=0,max_ms=0,cache_hits=0,exp_ocr_runs=0)
        build_interface(self)
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.refresh_windows()
        root.update_idletasks()

    def arm_diagnostic(self):
        if not self.running:
            self.diagnostic_status.set('请先开始新会话，再点击诊断。');return
        self.diagnostic=DiagnosticRecorder(bootstrap.ROOT/'diagnostics')
        self.diagnostic_button.configure(state='disabled')
        self.diagnostic_status.set('已准备；切回 CW，正常打怪约20秒。保存提示区和经验条小图。')

    def close_diagnostic(self):
        if self.diagnostic:
            self.diagnostic.close()
            self.diagnostic_status.set(f'诊断已保存：{self.diagnostic.path or "无可见采集帧"}')
            self.diagnostic_button.configure(state='normal')

    def filter_maps(self, event=None):
        query = self.map_name.get().strip().casefold()
        self.map_entry['values'] = [ALL_MAPS] + [name for name in self.catalog.maps if query in name.casefold()]
        self.show_profile()

    def profile_settings(self):
        return dict(catalog_mode=self.mode.get(), map=self.map_name.get(), exp_multiplier=self.multiplier.get(),
                    monsters=self.custom_text,auto_map=self.auto_map.get())

    def show_profile(self):
        if self.display_mode == CUSTOM:
            self.custom_text = self.monsters.get('1.0', 'end-1c')
        self.monsters.configure(state='normal')
        self.monsters.delete('1.0', 'end')
        self.display_mode = self.mode.get()
        if self.mode.get() == CUSTOM:
            self.monsters.insert('1.0', self.custom_text)
            self.profile_info.set('自定义实测表：每行「名称,单只白色提示经验」；此模式使用你填的数值，倍率仅作用于内置库。')
            return
        try:
            profile = settings_profile(self.profile_settings(), self.catalog)
            self.monsters.insert('1.0', '\n'.join(f'{name},{exp}' for name, exp in profile.items()))
            self.profile_info.set(f'内置库已自动加载 {len(profile)} 个候选，不用手填。选地图可减少同经验歧义；普通单人测试倍率用 1。')
        except ValueError as exc:
            self.profile_info.set(str(exc))
        self.monsters.configure(state='disabled')

    def refresh_windows(self):
        previous=None
        if hasattr(self,'window_choices'):
            index=self.windows.current()
            if 0<=index<len(self.window_choices): previous=self.window_choices[index][0]
        choices=capture.enumerate_windows()
        bound=getattr(self,'hwnd',None)
        if self.running and capture.window_exists(bound) and not any(h==bound for h,title in choices):
            choices.append((bound,self.bound_title or 'CW（等待恢复）'))
        self.window_choices=choices
        self.windows['values']=[f'{title}  [窗口 {hwnd}]' for hwnd,title in choices]
        target=previous if any(h==previous for h,t in choices) else bound
        index=next((i for i,(h,t) in enumerate(choices) if h==target),None)
        if index is None:
            index=next((i for i,(h,t) in enumerate(choices) if t.casefold()=='maplestory'),0 if choices else None)
        if index is not None:self.windows.current(index)
        else:self.window_var.set('')
        if self.running and not capture.window_exists(bound):self.try_reconnect(force=True)

    def selected_window(self):
        index=self.windows.current()
        if index<0 or index>=len(self.window_choices):raise ValueError('请选择 CW 游戏窗口')
        return self.window_choices[index][0]

    def window_selected(self,event=None):
        if self.running:
            hwnd=self.selected_window()
            if hwnd!=self.hwnd:self.bind_window(hwnd)

    def bind_window(self,hwnd):
        self.hwnd=hwnd
        self.bound_title=next((title for h,title in self.window_choices if h==hwnd),self.bound_title)
        self.geometry_key=None
        self.last_geometry=None
        self.pause_capture('正在重新连接游戏窗口')
        self.session.note('window_bound',json.dumps(dict(hwnd=hwnd,title=self.bound_title),ensure_ascii=False))

    def try_reconnect(self,force=False):
        now=time.monotonic()
        if not force and now-self.reconnect_at<2:return False
        self.reconnect_at=now
        choices=capture.enumerate_windows()
        matches=[(h,t) for h,t in choices if t.casefold()==self.bound_title.casefold()]
        if len(matches)!=1:return False
        hwnd,title=matches[0]
        self.window_choices=choices
        self.windows['values']=[f'{t}  [窗口 {h}]' for h,t in choices]
        self.windows.current(next(i for i,(h,t) in enumerate(choices) if h==hwnd))
        self.bind_window(hwnd)
        return True

    def save_settings(self):
        if not self.layout_compact:
            self.full_geometry=f'{self.root.winfo_width()}x{self.root.winfo_height()}'
        if self.mode.get() == CUSTOM:
            self.custom_text = self.monsters.get('1.0', 'end-1c')
        self.settings.update(self.profile_settings(), character=self.character.get(),
                             always_on_top=self.topmost.get(),
                             appearance=self.appearance.get(),accent=self.accent_name.get(),opacity=self.opacity.get(),
                             mini_mode=self.mini_mode.get(),
                             visible_sections={key:value.get() for key,value in self.visible_sections.items()},
                             full_geometry=self.full_geometry,
                             sidebar_geometry=f'{self.root.winfo_width()}x{self.root.winfo_height()}')
        if self.calibration:
            self.settings['calibration'] = asdict(self.calibration)
        if self.auto_region and self.auto_region.phase=='ready':
            self.settings['auto_region']=self.auto_region.settings()
        CONFIG.write_text(json.dumps(self.settings, ensure_ascii=False, indent=2), 'utf-8')

    def set_controls(self, running):
        if running:
            self.start_button.grid_remove();self.stop_button.grid()
        else:
            self.stop_button.grid_remove();self.start_button.grid()
        for widget in (self.start_button,):
            widget.configure(state='disabled' if running else 'normal')
        self.windows.configure(state='readonly')
        self.monsters.configure(state='normal' if not running and self.mode.get() == CUSTOM else 'disabled')
        self.char_entry.configure(state='normal')
        self.map_entry.configure(state='disabled' if running else 'normal')
        self.mode_entry.configure(state='disabled' if running else 'readonly')
        self.multiplier_entry.configure(state='disabled' if running else 'normal')
        self.auto_map_button.configure(state='disabled' if running else 'normal')
        self.stop_button.configure(state='normal' if running else 'disabled')

    def start(self):
        try:
            self.hwnd=self.selected_window()
            self.bound_title=next(title for hwnd,title in self.window_choices if hwnd==self.hwnd)
            self.save_settings()
            automated=self.auto_map.get() and self.mode.get()==BUILTIN
            monsters = {} if automated else settings_profile(self.settings, self.catalog)
            self.session.close()
            self.session = CounterSession(monsters, self.character.get(), '等待读图确认' if automated else self.map_name.get())
            self.session.open_log(OUTPUT)
            self.session.note('app_version', VERSION)
            self.session.note('reference', f'模式={self.mode.get()}; 倍率={self.multiplier.get()}; 来源={self.catalog.metadata}')
            self.session.note('reader', 'RapidOCR 1.4.4 / English PP-OCRv3 / CPU; 两帧+双路数字一致; 数字最低分>=0.7；整行低于0.8时要求数字>=0.85；分数不是正确率')
            self.reader = RapidReader(monsters)
            self.reset_hud()
            self.active_map=None if automated else self.map_name.get()
            self.map_monitor=MapMonitor(self.catalog) if automated else None
            self.character_monitor=CharacterMonitor() if not self.character.get().strip() else None
            self.character_hint.set('已填写' if self.character.get().strip() else '识别中；也可手填')
            if automated:
                self.session.map_name='等待读图确认'
            self.auto_region=None
            self.geometry_key=None
            self.last_geometry=None
            self.last_header_box=None
            self.needs_resume=True
            self.last_health=-100
            self.error_streak=0
            self.health_window=dict(frames=0,total_ms=0,max_ms=0,cache_hits=0,exp_ocr_runs=0)
            self.running = True
            self.was_valid = False
            self.last_tick = None
            self.last_status = ''
            self.set_controls(True)
            self.append_log(f'新会话：{self.session.path.name}')
            self.tick()
        except Exception as exc:
            self.session.close()
            self.running=False
            self.set_controls(False)
            messagebox.showerror('无法开始', str(exc))

    def notice(self, text):
        self.status.set(text)
        if text != self.last_status:
            self.session.note('capture_state', text)
            self.last_status = text

    def apply_detected_map(self,map_name):
        if map_name==self.active_map:
            return
        profile=self.catalog.profile(map_name,self.multiplier.get())
        if self.active_map is not None:
            self.flush_observed()
            self.session.note('map_end','地图改变，后续记录使用新文件')
            summary=self.session.path.with_name(self.session.path.name.replace('-events.csv','-summary.csv'))
            self.session.export_summary(summary)
            self.session.close()
            self.session=CounterSession(profile,self.character.get(),map_name)
            self.session.open_log(OUTPUT)
            self.session.note('app_version', VERSION)
        else:
            self.session.monsters=dict(profile)
            self.session.map_name=map_name
        self.active_map=map_name
        self.map_name.set(map_name)
        self.show_profile()
        self.save_settings()
        self.reader.set_profile(profile)
        self.reset_hud()
        self.was_valid=False
        self.last_tick=None
        self.session.note('map_confirmed',f'地图={map_name}; 候选={profile}; 来源={self.catalog.metadata}')
        self.append_log(f'已确认地图：{map_name}；候选经验：{sorted(set(profile.values()))}')
        self.update_stats()

    def pause_capture(self,reason):
        if not self.needs_resume:
            self.flush_observed()
            self.reset_hud()
            self.session.hud_credits.clear();self.session.notification_evidence.clear()
            if self.reader:self.reader.reset()
            if self.map_monitor:self.map_monitor.invalidate()
            if self.auto_region:self.auto_region.resume()
        self.needs_resume=True
        self.was_valid=False
        self.last_tick=None
        self.last_frame=None
        self.preview.configure(image='',text='已暂停；切回 CW 并保持提示可见后自动恢复。')
        self.notice('已暂停 · '+reason+'；条件恢复后自动继续，无需手动校准。')
        self.update_stats()

    def prepare_geometry(self,rect,now):
        x,y,width,height=rect
        geometry=(self.hwnd,width,height)
        if tuple(rect)!=self.last_geometry:
            self.session.note('window_geometry',json.dumps(dict(hwnd=self.hwnd,client=rect),ensure_ascii=False))
            self.last_geometry=tuple(rect)
        if geometry!=self.geometry_key:
            self.geometry_key=geometry;self.geometry_since=now
            self.auto_region=AutoRegion(width,height,self.settings.get('auto_region'))
            self.calibration=Calibration(width,height,region=list(self.auto_region.box))
            self.last_header_box=None
            self.pause_capture('正在自动适配窗口尺寸')
            return False
        if now-self.geometry_since<.2:return False
        if self.needs_resume:
            self.reader.reset()
            if self.map_monitor:self.map_monitor.invalidate()
            self.auto_region.resume()
            self.needs_resume=False
            self.session.note('capture_resumed',json.dumps(dict(hwnd=self.hwnd,client=rect,region=self.auto_region.box)))
        return True

    def change_region(self,old,new,reason):
        if old!=new:self.reader.rebase(old,new)
        self.auto_region.box=tuple(new)
        self.calibration.region=list(new)
        self.session.note('auto_region',json.dumps(dict(reason=reason,region=new,phase=self.auto_region.phase)))

    def probe_character(self,rect,monitors):
        monitor=self.character_monitor
        if monitor is None or monitor.done:return
        desired=character_box(rect[2],rect[3])
        visible=capture.visible_region(rect,desired,monitors)
        if visible!=desired:
            monitor.done=True
            self.character_hint.set('名字区不可见，可手填')
            return
        # Startup only; bounded attempts, shared model, never a per-frame task.
        image=capture.grab_region(self.hwnd,desired,mask_overlay=True)
        if not self.view_unchanged(rect):return
        name=monitor.observe(image)
        if name:
            self.character.set(name);self.session.character=name
            self.character_hint.set('已从画面确认')
            self.session.note('character_confirmed',name)
            self.save_settings()
        elif monitor.done:self.character_hint.set('未读到名字，可手填')

    def character_edited(self,event=None):
        name=self.character.get().strip()
        self.character_monitor=None
        self.session.character=name
        self.character_hint.set('手填已保存' if name else '可手填，或下轮自动识别')
        self.save_settings()
        if self.running:self.session.note('character_label',name or '未填写')

    def health(self,state,rect,started,events=0):
        now=time.monotonic()
        duration=round((now-started)*1000)
        stats=self.health_window
        stats['frames']+=1;stats['total_ms']+=duration;stats['max_ms']=max(stats['max_ms'],duration)
        cache_hit=bool(getattr(self.reader,'last_diagnostics',{}).get('ocr_cache_hit'))
        if state=='reading':
            stats['cache_hits']+=int(cache_hit)
            stats['exp_ocr_runs']+=int(not cache_hit)
        if now-self.last_health<5:return
        self.last_health=now
        lines=getattr(self.reader,'last_lines',[])
        self.session.note('capture_health',json.dumps(dict(state=state,client=rect,
            region=self.auto_region.box if self.auto_region else None,
            region_phase=self.auto_region.phase if self.auto_region else None,
            header_region=self.last_header_box,map=self.active_map,
            ocr_lines=len(lines),notifications=sum(bool(row.get('said')) for row in lines),
            verified=sum(bool(row.get('digit_verified')) and row.get('map_verified',True) for row in lines),
            emitted=events,tracking=getattr(self.reader,'last_diagnostics',{}),
            sample_lines=[dict(text=row['text'],score=round(row['score'],3),
                               said=row.get('said'),color=row.get('color'),
                               digit_reads=row.get('digit_reads'),digit_min_score=row.get('digit_min_score'),
                               digit_verified=row.get('digit_verified'),map_verified=row.get('map_verified'),
                               candidate_comparison=row.get('candidate_comparison'),
                               box=[round(v,1) for v in row['box']]) for row in lines[:8]],
            interval_stats=dict(stats,average_ms=round(stats['total_ms']/stats['frames']),
                                map_ocr_total=getattr(self.map_monitor,'ocr_reads',0)),
            processing_ms=round((now-started)*1000)),ensure_ascii=False))
        self.health_window=dict(frames=0,total_ms=0,max_ms=0,cache_hits=0,exp_ocr_runs=0)

    def view_unchanged(self,rect):
        return capture.foreground(self.hwnd) and capture.client_rect(self.hwnd)==rect

    def flush_observed(self):
        """Settle already captured evidence; never capture a background window."""
        if not getattr(self,'running',False):return
        if self.reader and hasattr(self.reader,'finish'):
            for event in self.reader.finish():self.session.accept(**event)
        if self.hud_sampler:
            self.hud_sampler.stop()
            samples,dropped=self.hud_sampler.drain()
            if not dropped:
                for timestamp,reading,cost,cached,view_valid in samples:
                    if not view_valid:break
                    self.apply_hud_reading(reading,timestamp,self.hud_sampler.box,cost,cached)
            else:self.session.note('hud_gap',f'结束时队列丢失{dropped}帧，未跨缺口补计')
        self.accept_hud_events(self.exp_ledger.finish(time.monotonic(),
            allow_topup=self.hud_topup.get() and self.session.party_exp==0,force=True))
        self.update_stats()

    def accept_hud_events(self,events):
        added=0
        for event in events:
            row=self.session.accept(**event)
            if row and row['status']=='estimated_candidate':
                added+=1;self.append_log(event['note'])
        return added

    def reset_hud(self):
        if getattr(self,'hud_sampler',None):self.hud_sampler.stop()
        if getattr(self,'running',False) and getattr(self,'session',None):
            self.accept_hud_events(self.exp_ledger.finish(time.monotonic(),
                allow_topup=self.hud_topup.get() and self.session.party_exp==0,force=True))
        if getattr(self,'session',None):self.session.exp_progress.break_interval()
        self.hud_sampler=None
        self.hud_missing_since=None
        self.hud_reader=HudReader();self.exp_ledger=ExpLedger()
        self.hud_log_at=-100.;self.hud_log_reading=None;self.hud_sample_count=0
        if hasattr(self,'hud_status'):self.hud_status.set(self.exp_ledger.status)

    def probe_hud(self,rect,monitors):
        now=time.monotonic()
        if self.hud_sampler:
            if self.hud_sampler.rect!=rect:self.reset_hud();return
            samples,dropped=self.hud_sampler.drain()
            if dropped:
                self.session.exp_progress.break_interval()
                self.exp_ledger.reset();self.session.note('hud_gap',f'读取队列丢失{dropped}帧，重建基线')
                return
            for timestamp,reading,cost,cached,view_valid in samples:
                if not view_valid:
                    self.reset_hud();return
                self.apply_hud_reading(reading,timestamp,self.hud_sampler.box,cost,cached)
                if reading is not None:self.hud_missing_since=None
                elif self.hud_missing_since is None:self.hud_missing_since=timestamp
            if self.hud_missing_since is not None and now-self.hud_missing_since>=2:
                self.reset_hud()
            return
        if now<self.hud_reader.next_read:return
        if self.hud_reader.box and capture.overlay_occludes(self.hwnd,rect,self.hud_reader.box):
            self.reset_hud()
            self.hud_status.set('经验条文字被面板挡住，暂停对账；地图和右侧提示继续读取')
            return
        box=self.hud_reader.box or hud_search_box(rect[2],rect[3])
        visible=capture.visible_region(rect,box,monitors)
        if visible!=box:
            self.session.exp_progress.break_interval()
            self.exp_ledger.reset();self.hud_status.set('经验条：底部区域不完整可见，暂停对账')
            self.hud_reader.next_read=now+2;return
        image=capture.grab_region(self.hwnd,box,mask_overlay=self.hud_reader.box is None)
        if not self.view_unchanged(rect):self.reset_hud();return
        try:
            reading=self.hud_reader.read(image,box,now)
        except Exception as exc:
            self.reset_hud();self.hud_reader.next_read=now+5
            self.session.note('hud_error',str(exc));self.hud_status.set('经验条：读取暂时失败，提示计数继续');return
        self.apply_hud_reading(reading,now,box)
        if reading and self.hud_reader.box:
            self.hud_sampler=HudSampler(self.hwnd,rect,self.hud_reader.box,capture)
            self.hud_sampler.start()

    def apply_hud_reading(self,reading,now,box,cost=None,cached=False):
        self.session.exp_progress.observe(reading,now)
        events=self.exp_ledger.observe(reading,now,self.session.monsters,
            party=self.session.party_exp>0,allow_topup=self.hud_topup.get())
        added=self.accept_hud_events(events)
        self.hud_status.set(self.exp_ledger.status)
        self.hud_sample_count+=1
        if events or reading!=self.hud_log_reading or now-self.hud_log_at>=5:
            self.session.note('hud_exp',json.dumps(dict(reading=asdict(reading) if reading else None,
                status=self.exp_ledger.status,box=box,topups=added,paired=len(events)-added,sample_time=now,
                samples=self.hud_sample_count,processing_ms=round(cost,1) if cost is not None else None,cached=cached,
                exp_progress=self.session.exp_progress.snapshot()),ensure_ascii=False))
            self.hud_log_at=now;self.hud_log_reading=reading

    def capture_step(self,started):
        if not capture.window_exists(self.hwnd):
            if not self.try_reconnect():
                self.pause_capture('游戏窗口已关闭，等待重新连接');return
        rect=capture.client_rect(self.hwnd)
        if rect is None:
            self.pause_capture('游戏窗口已最小化或暂时不可用');return
        if not capture.foreground(self.hwnd):
            self.pause_capture('CW 不在前台，请切回游戏');return
        now=time.monotonic()
        if not self.prepare_geometry(rect,now):return
        expanded=self.auto_region.expand_if_idle(now)
        if expanded:self.change_region(*expanded,'等待提示时扩大自动搜索区域')
        monitors=capture.monitor_rectangles()
        self.probe_character(rect,monitors)
        if not self.view_unchanged(rect):
            self.pause_capture('窗口正在移动或切换，等待画面稳定');return
        visible=capture.visible_region(rect,self.auto_region.box,monitors)
        if not visible or not valid_box(visible,rect[2],rect[3]) or visible[2]<rect[2]:
            self.pause_capture('右侧经验提示区域已移出屏幕，请将游戏移回可见位置');return
        if visible!=self.auto_region.box:
            old=self.auto_region.box
            self.change_region(old,visible,'适配屏幕可见范围')
            self.auto_region.phase='verifying'
        if self.map_monitor is not None:
            desired=title_box(rect[2],rect[3])
            header_box=capture.visible_region(rect,desired,monitors)
            if not header_box or header_box[2]-header_box[0]<100 or header_box[3]-header_box[1]<30:
                self.pause_capture('地图标题已移出屏幕，请将左上角小地图移回可见位置');return
            if self.last_header_box is not None and header_box!=self.last_header_box:
                self.map_monitor.invalidate();self.reader.reset()
                self.was_valid=False;self.last_tick=None
            self.last_header_box=header_box
            header=capture.grab_region(self.hwnd,header_box,mask_overlay=True)
            if not self.view_unchanged(rect):
                self.pause_capture('窗口正在移动或切换，等待画面稳定');return
            detected=self.map_monitor.observe(header,time.monotonic())
            if detected is None:
                if self.hud_sampler:self.reset_hud()
                if self.was_valid:self.reader.reset()
                self.was_valid=False;self.last_tick=None
                detail='地图标题部分在屏幕外' if header_box!=desired else '请保持左上角小地图展开且标题文字可见'
                self.notice('自动恢复中 · 地图确认中，'+detail+'。确认后自动继续。')
                self.health('waiting_map',rect,started);return
            self.apply_detected_map(detected)
        box=self.auto_region.box
        image=capture.grab_region(self.hwnd,box,mask_overlay=True)
        signature=tuple((l+box[0],t+box[1],r+box[0],b+box[1])
                        for l,t,r,b in image.info.get('overlay_masks',()))
        if signature!=getattr(self,'notification_mask',None):
            if getattr(self,'notification_mask',None) is not None:
                self.reader.reset();self.was_valid=False;self.last_tick=None
            self.notification_mask=signature
        if not self.view_unchanged(rect):
            self.pause_capture('窗口正在移动或切换，等待画面稳定');return
        now=time.monotonic()
        events,gap=self.reader.read(image,now)
        if self.diagnostic and not self.diagnostic.done:
            hud=self.hud_sampler.snapshot() if self.hud_sampler else None
            self.diagnostic.add(image,now,box,getattr(self.reader,'last_lines',[]),events,hud=hud)
            if self.diagnostic.done:self.close_diagnostic()
        if self.was_valid and self.last_tick is not None and now-self.last_tick<=2:
            self.session.active_seconds+=now-self.last_tick
        self.last_tick=now;self.was_valid=True
        if gap:self.session.note('capture_gap','采样超过2秒，已自动重建基线；不补计缺口')
        prior_phase=self.auto_region.phase
        relocation=self.auto_region.observe(getattr(self.reader,'last_lines',[]),now)
        if relocation:self.change_region(*relocation,self.auto_region.change_reason)
        if self.auto_region.phase=='ready' and prior_phase!='ready' and self.auto_region.change_reason.startswith('提示文字'):
            self.save_settings()
            self.session.note('auto_calibration_ready',json.dumps(self.auto_region.settings()))
        for event in events:
            row=self.session.accept(**event)
            if row:
                label={'matched_candidate':'已计入','estimated_candidate':'估计计入','uncertain':'待确认，未计入',
                       'uncertain_color':'颜色待确认，未计入'}.get(row['status'],row['status'])
                reason=f"；{row['note']}" if row['status'].startswith('uncertain') else ''
                self.append_log(f"{row['type']} +{row['exp']} {row['color']} → {row['monster'] or '无法匹配怪物'} [{label}]{reason}")
        if self.view_unchanged(rect):self.probe_hud(rect,monitors)
        lines=getattr(self.reader,'last_lines',[])
        parsed=sum(bool(row.get('said')) for row in lines)
        verified=sum(bool(row.get('said')) and bool(row.get('digit_verified')) and row.get('map_verified',True) for row in lines)
        if not lines:
            state='等待提示 · 自动搜索/验证经验区域'
        elif not parsed:
            state=f'正在读取 · 检测到 {len(lines)} 行文字，经验数字尚未确认'
        elif not verified:
            state=f'正在读取 · 看见 {parsed} 条提示，数字/地图校验尚未通过'
        else:
            state=f'统计中 · 已读取 {parsed} 条提示，新确认 {len(events)} 条'
        self.notice(state+' · '+str(self.active_map or '手动范围'))
        self.health('reading',rect,started,len(events))
        self.last_frame=image
        if int(now*2)!=getattr(self,'preview_tick',-1):
            self.preview_tick=int(now*2)
            shown=image.copy();shown.thumbnail((520,130))
            self.preview_image=ImageTk.PhotoImage(shown)
            self.preview.configure(image=self.preview_image,text='')
        self.update_stats()

    def tick(self):
        self.tick_job=None
        if not self.running:return
        began=time.monotonic()
        try:
            self.capture_step(began)
            self.error_streak=0
        except Exception as exc:
            self.error_streak+=1
            if self.last_status!='已暂停 · 读取暂时失败：'+str(exc)+'；条件恢复后自动继续，无需手动校准。':
                self.session.note('capture_error',str(exc))
            self.pause_capture('读取暂时失败：'+str(exc))
        if self.running:
            delay=max(50,int(300-(time.monotonic()-began)*1000))
            if self.error_streak:delay=max(delay,min(2000,300*2**min(self.error_streak,3)))
            self.tick_job=self.root.after(delay,self.tick)

    def update_stats(self):
        s = self.session
        title,detail=s.exp_progress.display(self.running)
        self.exp_summary.set(title);self.exp_detail.set(detail)
        self.stats.set(f'候选击杀 {sum(s.counts.values())}（含估计 {sum(s.estimated_counts.values())}）· 已读经验 {s.personal_exp:,} · 未确定事件 {s.unresolved}')
        wanted={name for name in s.monsters if s.counts[name]>0}
        for item in self.table.get_children():
            if item not in wanted:self.table.delete(item)
        for name in s.monsters:
            count = s.counts[name]
            if count<=0:continue
            rate = count * 3600 / s.active_seconds if s.active_seconds else 0
            values=(name,count,f'{rate:.0f}')
            if self.table.exists(name):self.table.item(name,values=values)
            else:self.table.insert('', 'end',iid=name,values=values)
        update_dashboard(self)

    def append_log(self, text):
        self.log.configure(state='normal')
        self.log.insert('end', text + '\n')
        if int(self.log.index('end-1c').split('.')[0]) > 150:
            self.log.delete('1.0','30.0')
        self.log.see('end'); self.log.configure(state='disabled')

    def stop(self):
        self.flush_observed()
        if self.hud_sampler:self.hud_sampler.stop();self.hud_sampler=None
        self.close_diagnostic()
        if self.tick_job is not None:
            self.root.after_cancel(self.tick_job)
            self.tick_job = None
        if self.running:
            self.running = False
            if self.reader and hasattr(self.reader,'finish'):
                for event in self.reader.finish():self.session.accept(**event)
            self.session.note('session_end', '用户结束或采集异常；未确定事件未强行分类')
            summary = self.session.path.with_name(self.session.path.name.replace('-events.csv','-summary.csv'))
            self.session.export_summary(summary)
            self.session.close()
            self.save_settings()
            self.set_controls(False)
            self.status.set(f'已保存：{summary.name}')
            self.update_stats()

    def export(self):
        path = filedialog.asksaveasfilename(defaultextension='.csv', initialfile='cw-summary.csv', filetypes=[('CSV','*.csv')])
        if path:
            self.session.export_summary(path)

    def open_output(self):
        import os
        OUTPUT.mkdir(exist_ok=True)
        os.startfile(str(OUTPUT))

    def close(self):
        self.stop()
        self.save_settings()
        self.root.destroy()



def main():
    import sys
    capture.enable_dpi()
    root = tk.Tk()
    if '--smoke-test' in sys.argv:
        root.withdraw()
        app = App(root)
        root.update_idletasks()
        assert not app.running and app.last_frame is None
        app.close()
        print('GUI smoke test passed; capture remained idle.')
        return
    App(root)
    root.mainloop()


if __name__ == '__main__':
    main()
