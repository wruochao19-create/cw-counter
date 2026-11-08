"""CW Counter settings. Keep widgets alive across navigation and palette changes."""
import tkinter as tk
from tkinter import ttk

from catalog import ALL_MAPS, BUILTIN, CUSTOM
from ui_theme import ACCENTS, BACK, LINE, SURFACE, TEXT
from modern_sidebar import (SECTIONS,
                            apply_appearance, apply_layout, apply_opacity, reset_appearance)
from ui_runtime import ctk


def build_settings(ui, close):
    win = ui.settings_window = tk.Toplevel(ui.root)
    win.withdraw()
    win.title('CW Counter · 设置')
    px = ui.px
    width = min(px(728), win.winfo_screenwidth() - 40)
    height = min(px(552), win.winfo_screenheight() - 100)
    win.geometry(f'{width}x{height}')
    win.minsize(min(width, px(600)), min(height, px(480)))
    win.transient(ui.root)
    win.protocol('WM_DELETE_WINDOW', close)

    nav = ctk.CTkFrame(win, fg_color=BACK, bg_color=BACK, corner_radius=0)
    nav.pack(side='left', fill='y', padx=(px(12), 0), pady=px(14))
    ctk.CTkLabel(nav, text='设置', text_color=TEXT, font=('Microsoft YaHei UI', 23, 'bold'),
                 anchor='w').pack(fill='x', padx=9, pady=(10, 19))
    surface = ctk.CTkFrame(win, fg_color=SURFACE, bg_color=BACK, corner_radius=16,
                           border_width=1, border_color=LINE)
    surface.pack(side='left', fill='both', expand=True, padx=px(12), pady=px(12))
    ui.settings_pages = {}
    ui.nav_value = tk.StringVar(value='连接与采集')
    ui.settings_switches = []
    for name in ('连接与采集', '外观', '显示内容', '识别详情', '怪物经验表'):
        page = ttk.Frame(surface)
        ui.settings_pages[name] = page
        ttk.Radiobutton(nav, text=name, value=name, variable=ui.nav_value, style='Nav.TRadiobutton',
                        command=lambda: select_page(ui), width=10).pack(fill='x', pady=px(2))
        ttk.Label(page, text=name, style='Title.TLabel').pack(anchor='w', pady=(0, px(12)))
    connection_page(ui)
    appearance_page(ui)
    layout_page(ui)
    details = ui.settings_pages['识别详情']
    for variable in (ui.stats, ui.exp_summary, ui.exp_detail, ui.hud_status):
        paragraph(details, variable=variable)
    ui.preview = ttk.Label(details, text='开始后显示提示区预览。', anchor='center')
    ui.preview.pack(fill='x', pady=5)
    ui.diagnostic_button = ttk.Button(details, text='保存 20 秒诊断', command=ui.arm_diagnostic)
    ui.diagnostic_button.pack(anchor='w')
    ui.diagnostic_status = tk.StringVar(value='最多 8 MB，包含提示区、经验条小图和识别结果。')
    paragraph(details, variable=ui.diagnostic_status)
    ui.log = scrolled_text(details, height=3, state='disabled')
    profile = ui.settings_pages['怪物经验表']
    paragraph(profile, variable=ui.profile_info)
    ui.monsters = scrolled_text(profile, height=8, undo=True)
    ui.display_mode = None
    ui.show_profile()
    select_page(ui)


def select_page(ui):
    for name, page in ui.settings_pages.items():
        if name == ui.nav_value.get():
            page.pack(fill='both', expand=True, padx=ui.px(20), pady=ui.px(18))
        else:
            page.pack_forget()


def paragraph(parent, text='', variable=None):
    label = ttk.Label(parent, text=text, textvariable=variable, style='Muted.TLabel', wraplength=340)
    label.pack(fill='x', pady=(2, 6))
    label.bind('<Configure>', lambda event: label.configure(wraplength=max(40, event.width - 2)))


def switch(ui, parent, text, variable, command=None):
    widget = ctk.CTkSwitch(parent, text=text, variable=variable, command=command,
                           text_color=TEXT, bg_color=SURFACE, fg_color=('#8290a3', '#535f72'),
                           button_color='white', button_hover_color='#e4eaf2',
                           switch_width=32, switch_height=18, font=('Microsoft YaHei UI', 13))
    ui.settings_switches.append(widget)
    return widget


def connection_page(ui):
    page = ui.settings_pages['连接与采集']
    form = ttk.Frame(page)
    form.pack(fill='x')
    form.columnconfigure(1, weight=1)

    def field(row, name, widget):
        ttk.Label(form, text=name).grid(row=row, column=0, sticky='w', padx=(0, ui.px(12)))
        widget.grid(row=row, column=1, sticky='ew', pady=ui.px(5))

    row = ttk.Frame(form)
    field(0, '游戏窗口', row)
    ui.window_var = tk.StringVar()
    ui.refresh_button = ttk.Button(row, text='刷新', command=ui.refresh_windows)
    ui.refresh_button.pack(side='right', padx=(6, 0))
    ui.windows = ttk.Combobox(row, textvariable=ui.window_var, state='readonly', width=12)
    ui.windows.pack(side='left', fill='x', expand=True)
    ui.windows.bind('<<ComboboxSelected>>', ui.window_selected)
    ui.char_entry = ttk.Entry(form, textvariable=ui.character)
    field(1, '角色', ui.char_entry)
    for event in ('<FocusOut>', '<Return>'):
        ui.char_entry.bind(event, ui.character_edited)
    ttk.Label(form, textvariable=ui.character_hint, style='Muted.TLabel').grid(row=2, column=1, sticky='w')
    ui.map_entry = ttk.Combobox(form, textvariable=ui.map_name, values=[ALL_MAPS] + ui.catalog.maps)
    field(3, '地图', ui.map_entry)
    ui.map_entry.bind('<KeyRelease>', ui.filter_maps)
    ui.map_entry.bind('<<ComboboxSelected>>', lambda _: ui.show_profile())
    ttk.Label(form, text='输入英文地图名可筛选', style='Muted.TLabel').grid(row=4, column=1, sticky='w')
    ui.mode_entry = ttk.Combobox(form, textvariable=ui.mode, values=[BUILTIN, CUSTOM], state='readonly')
    field(5, '经验表', ui.mode_entry)
    ui.mode_entry.bind('<<ComboboxSelected>>', lambda _: ui.show_profile())
    ui.multiplier_entry = ttk.Spinbox(form, textvariable=ui.multiplier, from_=.1, to=10, increment=.1,
                                      width=7, command=ui.show_profile)
    field(6, '经验倍率', ui.multiplier_entry)
    ui.multiplier_entry.grid_configure(sticky='w')
    for event in ('<FocusOut>', '<Return>'):
        ui.multiplier_entry.bind(event, lambda _: ui.show_profile())
    ttk.Separator(page).pack(fill='x', pady=ui.px(10))
    ui.auto_map_button = switch(ui, page, '自动读取地图', ui.auto_map)
    ui.auto_map_button.pack(anchor='w', pady=3)
    ui.hud_button = switch(ui, page, '经验条补计（仅单人打怪）', ui.hud_topup, ui.reset_hud)
    ui.hud_button.pack(anchor='w', pady=3)
    actions = ttk.Frame(page)
    actions.pack(side='bottom', fill='x', pady=(6, 0))
    ttk.Button(actions, text='打开记录目录', command=ui.open_output).pack(side='left')
    ttk.Button(actions, text='导出当前汇总', command=ui.export).pack(side='left', padx=8)


def appearance_page(ui):
    page = ui.settings_pages['外观']
    for title, variable, choices in [('显示模式', ui.appearance, ('浅色', '深色')),
                                      ('强调色', ui.accent_name, tuple(ACCENTS))]:
        ttk.Label(page, text=title, style='Section.TLabel').pack(anchor='w', pady=(4, 8))
        row = ttk.Frame(page)
        row.pack(fill='x', pady=(0, ui.px(18)))
        for index, value in enumerate(choices):
            swatch = value in ACCENTS
            ttk.Radiobutton(row, text=f'●  {value}' if swatch else value, value=value, variable=variable,
                            style=f'Swatch{index}.TRadiobutton' if swatch else 'Choice.TRadiobutton',
                            command=lambda: apply_appearance(ui, persist=True)).pack(
                                side='left', fill='x', expand=True, padx=(0, 5))
    ttk.Label(page, text='主窗口不透明度', style='Section.TLabel').pack(anchor='w', pady=(4, 5))
    ui.opacity_slider = ctk.CTkSlider(page, from_=75, to=100, number_of_steps=25, variable=ui.opacity,
                                      bg_color=SURFACE, fg_color=LINE, command=lambda _: apply_opacity(ui))
    ui.opacity_slider.pack(fill='x', pady=8)
    ttk.Label(page, textvariable=ui.opacity_label, style='Muted.TLabel').pack(anchor='w')
    ttk.Button(page, text='恢复默认外观', command=lambda: reset_appearance(ui)).pack(side='bottom', anchor='w')


def layout_page(ui):
    page = ui.settings_pages['显示内容']
    switch(ui, page, '小窗模式 · 只看 EXP / 小时', ui.mini_mode,
           lambda: apply_layout(ui, persist=True)).pack(anchor='w', pady=6)
    ttk.Separator(page).pack(fill='x', pady=ui.px(14))
    ttk.Label(page, text='完整窗口', style='Section.TLabel').pack(anchor='w', pady=(0, 6))
    for key, title in SECTIONS.items():
        switch(ui, page, title, ui.visible_sections[key], lambda: apply_layout(ui, persist=True)).pack(anchor='w', pady=5)


def scrolled_text(parent, **kwargs):
    frame = ttk.Frame(parent)
    frame.pack(fill='both', expand=True, pady=(6, 0))
    text = tk.Text(frame, font=('Consolas', 10), wrap='word', relief='flat', borderwidth=0,
                   padx=8, pady=8, **kwargs)
    scroll = ttk.Scrollbar(frame, orient='vertical', command=text.yview)
    text.configure(yscrollcommand=scroll.set)
    scroll.pack(side='right', fill='y')
    text.pack(fill='both', expand=True)
    return text
