"""Compact, resizable Tk sidebar. Presentation only; no game integration."""
import math
import re
import tkinter as tk
from tkinter import ttk
import windows_capture as capture
from catalog import ALL_MAPS, BUILTIN, CUSTOM
from modern_sidebar import build_sidebar, add_appearance_settings

BG = '#f7f9fc'
PANEL = '#ffffff'
INK = '#243047'
MUTED = '#647187'
LINE = '#e4e9f1'
ACCENT = '#4768bd'


def build_interface(ui):
    root = ui.root
    scale = float(root.tk.call('tk', 'scaling')) / (96 / 72)
    px = lambda value: round(value * scale)
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('.', font=('Microsoft YaHei UI', 10), background=BG, foreground=INK)
    style.configure('TFrame', background=BG)
    style.configure('TLabel', background=BG, foreground=INK)
    style.configure('Muted.TLabel', foreground=MUTED)
    style.configure('TButton', padding=(10, 7), background=PANEL, bordercolor=LINE)
    style.map('TButton', background=[('active', '#eaf0fb')])
    style.configure('Primary.TButton', background=ACCENT, foreground='white', borderwidth=0, padding=(12, 10))
    style.map('Primary.TButton', background=[('active', '#3655a4'), ('disabled', '#d6ddeb')],
              foreground=[('disabled', MUTED)])
    style.configure('Treeview', background=PANEL, fieldbackground=PANEL, foreground=INK,
                    font=('Microsoft YaHei UI', 10), rowheight=px(28), borderwidth=0)
    style.configure('Treeview.Heading', background=BG, foreground=MUTED,
                    font=('Microsoft YaHei UI', 9), padding=(4, 8), relief='flat')
    style.map('Treeview', background=[('selected', '#e4ebfc')], foreground=[('selected', '#284984')])
    style.configure('TNotebook', borderwidth=0)
    style.configure('TNotebook.Tab', padding=(12, 8))
    style.configure('EXP.Horizontal.TProgressbar', background=ACCENT, troughcolor=LINE,
                    borderwidth=0, thickness=px(7), lightcolor=ACCENT, darkcolor=ACCENT)
    root.configure(background=BG)
    root.resizable(True, True)
    root.minsize(px(390), px(600))
    geometry = ui.settings.get('full_geometry') or ui.settings.get('sidebar_geometry', '')
    # Restore size only. Never restore a position that might be off-screen.
    match = re.fullmatch(r'(\d+)x(\d+)', geometry) if isinstance(geometry, str) else None
    w, h = (int(match[1]), int(match[2])) if match else (px(420), px(720))
    root.geometry(f'{max(px(390),min(w,root.winfo_screenwidth()-40))}x{max(px(600),min(h,root.winfo_screenheight()-100))}')
    ui.topmost = tk.BooleanVar(value=bool(ui.settings.get('always_on_top', True)))
    ui.state_text = tk.StringVar(value='准备开始')
    ui.character = tk.StringVar(value=ui.settings.get('character', ''))
    ui.character_hint = tk.StringVar(value='已保存' if ui.character.get() else '开始后识别')
    ui.map_name = tk.StringVar(value=ui.settings.get('map') or ALL_MAPS)
    ui.character_display = tk.StringVar()
    ui.rate_display = tk.StringVar(value='—')
    ui.rate_note = tk.StringVar(value='底部经验条 · 等待读数')
    ui.eta_display = tk.StringVar(value='开始后估算')
    ui.time_display = tk.StringVar(value='00:00')
    ui.percent_display = tk.StringVar(value='—')
    ui.kill_display = tk.StringVar(value='0')
    ui.gain_display = tk.StringVar(value='+0')
    ui.estimate_display = tk.StringVar(value='仅显示已击杀的怪物')
    ui.status = tk.StringVar(value='点击开始，切回 CW 后自动识别。')
    ui.stats = tk.StringVar()
    ui.exp_summary = tk.StringVar()
    ui.exp_detail = tk.StringVar()
    ui.hud_status = tk.StringVar(value='经验条自动读取与对账；做任务或组队时关闭补计。')
    ui.profile_info = tk.StringVar()

    build_sidebar(ui, scale, lambda: open_settings(ui), lambda: apply_topmost(ui, persist=True))

    # Secondary controls remain alive while hidden, preserving the existing pipeline.
    ui.settings_window = tk.Toplevel(root)
    ui.settings_window.withdraw()
    ui.settings_window.title('CW Counter · 设置与详情')
    ui.settings_window.geometry(f'{px(650)}x{px(660)}')
    ui.settings_window.minsize(px(560), px(580))
    ui.settings_window.transient(root)
    ui.settings_window.protocol('WM_DELETE_WINDOW', lambda: close_settings(ui))
    ui.tabs = ttk.Notebook(ui.settings_window)
    ui.tabs.pack(fill='both', expand=True, padx=12, pady=12)
    connection = ttk.Frame(ui.tabs, padding=14)
    details = ttk.Frame(ui.tabs, padding=14)
    profile = ttk.Frame(ui.tabs, padding=14)
    for page, title in [(connection, '连接与设置'), (details, '识别详情'), (profile, '怪物经验表')]:
        ui.tabs.add(page, text=title)
    ttk.Label(connection, text='游戏窗口').pack(anchor='w')
    row = ttk.Frame(connection); row.pack(fill='x', pady=(5, 12))
    ui.window_var = tk.StringVar()
    ui.windows = ttk.Combobox(row, textvariable=ui.window_var, state='readonly')
    ui.windows.pack(side='left', fill='x', expand=True)
    ui.windows.bind('<<ComboboxSelected>>', ui.window_selected)
    ui.refresh_button = ttk.Button(row, text='刷新', command=ui.refresh_windows)
    ui.refresh_button.pack(side='right', padx=(8, 0))
    ttk.Label(connection, text='角色（自动识别，也可手填）').pack(anchor='w')
    ui.char_entry = ttk.Entry(connection, textvariable=ui.character)
    ui.char_entry.pack(fill='x', pady=(5, 0))
    for event in ('<FocusOut>', '<Return>'): ui.char_entry.bind(event, ui.character_edited)
    ttk.Label(connection, textvariable=ui.character_hint, style='Muted.TLabel').pack(anchor='w', pady=(0, 10))
    ttk.Label(connection, text='地图（输入英文筛选）').pack(anchor='w')
    ui.map_entry = ttk.Combobox(connection, textvariable=ui.map_name, values=[ALL_MAPS]+ui.catalog.maps)
    ui.map_entry.pack(fill='x', pady=(5, 12))
    ui.map_entry.bind('<KeyRelease>', ui.filter_maps)
    ui.map_entry.bind('<<ComboboxSelected>>', lambda _: ui.show_profile())
    ui.mode_entry = ttk.Combobox(connection, textvariable=ui.mode, values=[BUILTIN, CUSTOM], state='readonly')
    ui.mode_entry.pack(fill='x', pady=(0, 10))
    ui.mode_entry.bind('<<ComboboxSelected>>', lambda _: ui.show_profile())
    row = ttk.Frame(connection); row.pack(fill='x', pady=(0, 10))
    ttk.Label(row, text='经验倍率  ').pack(side='left')
    ui.multiplier_entry = ttk.Spinbox(row, textvariable=ui.multiplier, from_=.1, to=10, increment=.1, width=6, command=ui.show_profile)
    ui.multiplier_entry.pack(side='left')
    for event in ('<FocusOut>', '<Return>'): ui.multiplier_entry.bind(event, lambda _: ui.show_profile())
    ui.auto_map_button = ttk.Checkbutton(connection, text='自动读取地图', variable=ui.auto_map)
    ui.auto_map_button.pack(anchor='w', pady=3)
    ui.hud_button = ttk.Checkbutton(connection, text='经验条补计（仅单人打怪）', variable=ui.hud_topup, command=ui.reset_hud)
    ui.hud_button.pack(anchor='w', pady=3)
    ttk.Label(connection, text='置顶适用于窗口化 / 无边框全屏。\n拖动标题栏移动；拖动窗口边框调整大小。\n请避开小地图、底部经验条和右侧经验提示。', style='Muted.TLabel').pack(anchor='w', pady=15)
    row = ttk.Frame(connection); row.pack(fill='x')
    ttk.Button(row, text='导出当前汇总', command=ui.export).pack(side='left')
    ttk.Button(row, text='打开记录目录', command=ui.open_output).pack(side='left', padx=8)
    ttk.Label(connection, text='仅读取可见画面 · 默认不保存截图', style='Muted.TLabel').pack(anchor='w', pady=12)
    for variable in (ui.stats, ui.exp_summary, ui.exp_detail, ui.hud_status):
        ttk.Label(details, textvariable=variable, wraplength=570).pack(anchor='w', pady=3)
    ui.preview = ttk.Label(details, text='开始后显示提示区预览。', anchor='center')
    ui.preview.pack(fill='x', pady=8)
    ui.diagnostic_button = ttk.Button(details, text='保存 20 秒诊断（最多 8MB）', command=ui.arm_diagnostic)
    ui.diagnostic_button.pack(anchor='w')
    ui.diagnostic_status = tk.StringVar(value='仅点击后保存提示区、经验条小图和识别结果。')
    ttk.Label(details, textvariable=ui.diagnostic_status, wraplength=570, style='Muted.TLabel').pack(anchor='w', pady=5)
    ui.log = scrolled_text(details, height=5, state='disabled')
    ttk.Label(profile, textvariable=ui.profile_info, wraplength=570).pack(anchor='w', pady=(0, 8))
    ui.monsters = scrolled_text(profile, height=8, undo=True)
    ui.display_mode = None
    ui.show_profile()
    # Query only our own native handles, so capture workers can reject self-occlusion.
    for window in (root, ui.settings_window):
        hwnd = capture.root_window(window.winfo_id())
        capture.register_overlay(hwnd)
        window.bind('<Destroy>', lambda event, win=window, handle=hwnd:
                    capture.unregister_overlay(handle) if event.widget is win else None, add='+')
    add_appearance_settings(ui)
    apply_topmost(ui)
    update_dashboard(ui)


def scrolled_text(parent, **kwargs):
    frame = ttk.Frame(parent); frame.pack(fill='both', expand=True)
    text = tk.Text(frame, font=('Consolas', 10), wrap='word', background=PANEL,
                   foreground=INK, relief='flat', **kwargs)
    scroll = ttk.Scrollbar(frame, orient='vertical', command=text.yview)
    text.configure(yscrollcommand=scroll.set)
    scroll.pack(side='right', fill='y'); text.pack(fill='both', expand=True)
    return text


def open_settings(ui):
    ui.settings_window.deiconify()
    ui.settings_window.lift()


def close_settings(ui):
    ui.save_settings()
    ui.settings_window.withdraw()


def apply_topmost(ui, persist=False):
    ui.root.attributes('-topmost', ui.topmost.get())
    ui.settings_window.attributes('-topmost', ui.topmost.get())
    if persist: ui.save_settings()


def update_dashboard(ui,now=None):
    s = ui.session
    progress = s.exp_progress.snapshot(now=now)
    quality='paused' if ui.running and ui.needs_resume else progress['exp_reading_status']
    rate, eta = progress['exp_per_hour'], progress['level_eta_seconds']
    ui.rate_display.set(f'{rate:,.0f}' if rate is not None else '—')
    if eta is not None:
        minutes = max(1, math.ceil(eta / 60)); hours, minutes = divmod(minutes, 60)
        ui.eta_display.set((f'{hours}小时 ' if hours else '') + f'{minutes:02d}分')
    else:
        ui.eta_display.set('暂无经验增长' if rate == 0 else '收集经验数据中' if ui.running else '开始后估算')
    if ui.running and not ui.needs_resume and quality in ('stale','rejected','level_change_pending'):
        ui.eta_display.set('等待读数确认')
    state={'stale':'读数过期，保留上次均值','rejected':'数字冲突，正在校验',
           'level_change_pending':'正在确认升级','confirming':'正在验证数字',
           'paused':'读取暂停','waiting':'等待读数','live':'有效读数均值'}[quality]
    ui.rate_note.set('底部经验条 · '+state)
    seconds = int(s.map_clock.seconds)
    ui.time_display.set(f'{seconds//60:02d}:{seconds%60:02d}')
    percent = progress['current_hud_percent']
    ui.percent_display.set(f'{percent:.2f}%' if percent is not None else '—')
    ui.exp_bar.set((percent or 0)/100)
    ui.kill_display.set(f'{sum(s.counts.values()):,}')
    ui.gain_display.set(f"+{progress['hud_exp_gained']:,}")
    ui.character_display.set(ui.character.get().strip() or '角色：开始后自动识别')
    ui.estimate_display.set(f'含估计 {sum(s.estimated_counts.values())} 只 · 切窗自动暂停')
    if sum(s.counts.values()):ui.empty_label.place_forget()
    else:ui.empty_label.place(relx=.5,rely=.55,anchor='center')
    if ui.running:
        ui.state_text.set('已暂停' if ui.needs_resume else '读数过期' if quality=='stale' else
                          '校验中' if quality in ('rejected','level_change_pending') else
                          '统计中' if getattr(ui,'map_clock_active',ui.was_valid) else '识别中')
    else:
        ui.state_text.set('已结束' if s.counts and sum(s.counts.values()) else '准备开始')
