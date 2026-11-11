"""Compact, resizable Tk sidebar. Presentation only; no game integration."""
import math
import re
import tkinter as tk
from tkinter import ttk
import windows_capture as capture
from catalog import ALL_MAPS
from modern_sidebar import build_sidebar, apply_appearance, apply_layout
from settings_view import build_settings

def build_interface(ui):
    root = ui.root
    scale = float(root.tk.call('tk', 'scaling')) / (96 / 72)
    px = lambda value: round(value * scale)
    style = ttk.Style(root)
    style.theme_use('clam')
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
    ui.coin_display = tk.StringVar()
    ui.wallet_hint = tk.StringVar()
    ui.stats = tk.StringVar()
    ui.exp_summary = tk.StringVar()
    ui.exp_detail = tk.StringVar()
    ui.hud_status = tk.StringVar(value='经验条自动读取与对账；做任务或组队时关闭补计。')
    ui.profile_info = tk.StringVar()

    build_sidebar(ui, scale, lambda: open_settings(ui), lambda: apply_topmost(ui, persist=True))

    # Secondary controls remain alive while hidden, preserving the existing pipeline.
    build_settings(ui, lambda: close_settings(ui))
    # Query only our own native handles, so capture workers can reject self-occlusion.
    for window in (root, ui.settings_window):
        hwnd = capture.root_window(window.winfo_id())
        capture.register_overlay(hwnd)
        window.bind('<Destroy>', lambda event, win=window, handle=hwnd:
                    capture.unregister_overlay(handle) if event.widget is win else None, add='+')
    apply_appearance(ui)
    apply_layout(ui,initial=True)
    apply_topmost(ui)
    update_dashboard(ui)


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
    coin_rate=s.coin_rate()
    speed=f'{coin_rate:,}' if coin_rate is not None else '—'
    ui.coin_display.set(f'金币／小时 {speed}　·　已拾取 {s.coin_total:,}')
    if s.wallet_checks:
        check=s.wallet_checks[-1]
        if check.end:
            total, uncertain=check.total, check.uncertain
            delta=check.end[1]-check.start[1]
            ui.wallet_hint.set(f'钱包 {delta:+,} · 提示 {total:,} · 差 {delta-total:+,} · 待确认 {uncertain} 笔')
        elif check.start:
            action='关包开始刷怪' if check.phase=='close' else '结束时再打开背包'
            ui.wallet_hint.set(f'起始 {check.start[1]:,} · {action}')
        else:
            ui.wallet_hint.set('切回游戏，打开背包并保持余额可见')
    else:
        ui.wallet_hint.set('')
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
