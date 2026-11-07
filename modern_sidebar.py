"""Rounded CustomTkinter presentation; native window movement and resize retained."""
import tkinter as tk
from tkinter import ttk
from ui_runtime import ctk, cleanup_callbacks

SURFACE = ('#ffffff', '#202630')
BACK = ('#edf1f7', '#151a22')
TEXT = ('#263246', '#eef2f8')
MUTED = ('#68758a', '#a5b0c2')
LINE = ('#e9edf4', '#343d4b')
SOFT = ('#f3f6fb', '#2a3341')
ACCENTS = {'雾蓝': ('#5474c5', '#91aaff'), '松绿': ('#327b70', '#7dc7b8'), '鸢紫': ('#8060ae', '#c1a2ed')}
SECTIONS = {'context':'地图与角色', 'eta':'预计升级时间', 'progress':'等级进度',
            'kills':'击杀与经验合计', 'monsters':'怪物击杀列表'}


def build_sidebar(ui, scale, open_settings, toggle_topmost):
    ctk.deactivate_automatic_dpi_awareness()  # The host already initializes Windows DPI.
    ctk.set_widget_scaling(scale)
    ui.appearance = tk.StringVar(value=ui.settings.get('appearance', '浅色'))
    ui.accent_name = tk.StringVar(value=ui.settings.get('accent', '雾蓝'))
    if ui.appearance.get() not in ('浅色', '深色'): ui.appearance.set('浅色')
    if ui.accent_name.get() not in ACCENTS: ui.accent_name.set('雾蓝')
    try: opacity = max(75, min(100, float(ui.settings.get('opacity', 100))))
    except (ValueError, TypeError): opacity = 100
    ui.opacity = tk.DoubleVar(value=opacity)
    ui.opacity_label = tk.StringVar()
    ctk.set_appearance_mode('Dark' if ui.appearance.get() == '深色' else 'Light')
    ui.accent_controls = []
    ui.px = lambda n: round(n * scale)
    ui.mini_mode = tk.BooleanVar(value=bool(ui.settings.get('mini_mode',False)))
    saved_sections=ui.settings.get('visible_sections',{})
    if not isinstance(saved_sections,dict):saved_sections={}
    ui.visible_sections={key:tk.BooleanVar(value=bool(saved_sections.get(key,True))) for key in SECTIONS}
    ui.section_widgets={key:[] for key in SECTIONS}
    ui.layout_compact=False
    ui.full_geometry=ui.settings.get('full_geometry','')
    font = lambda size=13, bold=False: ('Microsoft YaHei UI', size, 'bold' if bold else 'normal')
    def label(parent, text='', variable=None, size=13, bold=False, color=TEXT, **kwargs):
        return ctk.CTkLabel(parent, text=text, textvariable=variable, font=font(size,bold),
                            text_color=color, height=20, anchor=kwargs.pop('anchor','w'), **kwargs)
    def frame(parent): return ctk.CTkFrame(parent, fg_color='transparent', corner_radius=0)
    def divider(parent): return ctk.CTkFrame(parent, fg_color=LINE, height=1, corner_radius=0)

    # An opaque rounded surface sits inside the native resizable window.
    ui.surface = ctk.CTkFrame(ui.root, fg_color=SURFACE, corner_radius=16, border_width=1, border_color=LINE)
    ui.surface.pack(fill='both', expand=True, padx=ui.px(7), pady=ui.px(7))
    ui.surface.columnconfigure(0, weight=1)
    ui.surface.rowconfigure(2, weight=1)
    head=frame(ui.surface);head.grid(row=0,column=0,sticky='ew',padx=20,pady=(12,10))
    label(head,'CW Counter',size=16,bold=True).pack(side='left')
    ctk.CTkButton(head,text='设置',width=46,height=28,corner_radius=8,fg_color=SOFT,
                   hover_color=LINE,text_color=TEXT,font=font(12),command=open_settings).pack(side='right')
    ui.mini_button=ctk.CTkButton(head,text='小窗',width=42,height=28,corner_radius=8,fg_color=SOFT,
                   hover_color=LINE,text_color=TEXT,font=font(12),command=lambda:toggle_mini(ui))
    ui.mini_button.pack(side='right',padx=6)
    ui.pin_button=ctk.CTkSwitch(head,text='置顶',variable=ui.topmost,command=toggle_topmost,
                                width=58,height=22,switch_width=28,switch_height=16,
                                font=font(11),text_color=MUTED,progress_color=ACCENTS[ui.accent_name.get()][0])
    ui.pin_button.pack(side='right',padx=(0,9))
    ui.accent_controls.append((ui.pin_button,'progress_color'))

    body=frame(ui.surface);body.grid(row=1,column=0,sticky='ew',padx=22)
    body.columnconfigure(0,weight=1)
    context_line=divider(body);context_line.grid(row=0,column=0,sticky='ew',pady=(0,12))
    ui.map_label=label(body,variable=ui.map_name,size=16,bold=True)
    ui.map_label.grid(row=1,column=0,sticky='ew')
    context=frame(body);context.grid(row=2,column=0,sticky='ew',pady=(3,10))
    label(context,variable=ui.character_display,size=12,color=MUTED).pack(side='left')
    ui.state_badge=ctk.CTkLabel(context,textvariable=ui.state_text,height=22,corner_radius=7,
                               fg_color=SOFT,text_color=MUTED,font=font(10))
    ui.state_badge.pack(side='right')
    ui.section_widgets['context']=[context_line,ui.map_label,context]
    hero=frame(body);hero.grid(row=3,column=0,sticky='ew')
    hero.columnconfigure(0,weight=1)
    label(hero,'EXP / 小时',size=12,color=MUTED).grid(row=0,column=0,sticky='w')
    ui.hero_value=label(hero,variable=ui.rate_display,size=43,bold=True,color=TEXT)
    ui.hero_value.grid(row=1,column=0,sticky='w',pady=(0,4))
    clock=frame(hero);clock.grid(row=0,column=1,rowspan=2,sticky='e')
    label(clock,'本图用时',size=10,color=MUTED).pack(anchor='e')
    label(clock,variable=ui.time_display,size=13,color=MUTED).pack(anchor='e')
    ui.clock=clock
    ui.mini_state=label(hero,variable=ui.state_text,size=10,color=MUTED)
    ui.mini_state.grid(row=0,column=1,sticky='e');ui.mini_state.grid_remove()
    eta_line=divider(body);eta_line.grid(row=4,column=0,sticky='ew',pady=(0,10))
    eta_title=label(body,'预计升级还需',size=12,color=MUTED);eta_title.grid(row=5,column=0,sticky='w')
    eta_value=label(body,variable=ui.eta_display,size=23,bold=True);eta_value.grid(row=6,column=0,sticky='w',pady=(2,10))
    ui.section_widgets['eta']=[eta_line,eta_title,eta_value]
    row=frame(body);row.grid(row=7,column=0,sticky='ew')
    label(row,'等级进度',size=11,color=MUTED).pack(side='left')
    label(row,variable=ui.percent_display,size=11,color=MUTED).pack(side='right')
    ui.exp_bar=ctk.CTkProgressBar(body,height=7,corner_radius=4,fg_color=LINE,
                                 progress_color=ACCENTS[ui.accent_name.get()][0])
    ui.exp_bar.grid(row=8,column=0,sticky='ew',pady=(6,12));ui.exp_bar.set(0)
    ui.accent_controls.append((ui.exp_bar,'progress_color'))
    ui.section_widgets['progress']=[row,ui.exp_bar]
    totals=frame(body);totals.grid(row=9,column=0,sticky='ew',pady=(0,8))
    label(totals,'本次击杀  ',size=12,color=MUTED).pack(side='left')
    label(totals,variable=ui.kill_display,size=14,bold=True).pack(side='left')
    label(totals,variable=ui.gain_display,size=14,bold=True).pack(side='right')
    label(totals,'经验  ',size=12,color=MUTED).pack(side='right')
    ui.section_widgets['kills']=[totals]

    # Keep the mature Treeview model/keyboard behavior; remove its bevels and chrome.
    ui.list_frame=frame(ui.surface)
    ui.list_frame.grid(row=2,column=0,sticky='nsew',padx=22)
    ui.section_widgets['monsters']=[ui.list_frame]
    ui.table=ttk.Treeview(ui.list_frame,columns=('mob','count','rate'),show='headings',height=8,style='Modern.Treeview')
    for key,title in [('mob','怪物'),('count','击杀'),('rate','只 / 小时')]:
        ui.table.heading(key,text=title,anchor='w' if key=='mob' else 'e')
    ui.table.column('mob',width=ui.px(170),minwidth=ui.px(105),stretch=True)
    ui.table.column('count',width=ui.px(45),minwidth=ui.px(40),stretch=False,anchor='e')
    ui.table.column('rate',width=ui.px(74),minwidth=ui.px(65),stretch=False,anchor='e')
    ui.table_scroll=ctk.CTkScrollbar(ui.list_frame,command=ui.table.yview,width=9,
                                    fg_color='transparent',button_color=('#c4cddd','#4d596d'),button_hover_color=MUTED)
    ui.table_scroll.pack(side='right',fill='y',padx=(7,0))
    ui.table.configure(yscrollcommand=ui.table_scroll.set)
    ui.table.pack(side='left',fill='both',expand=True)
    ui.empty_label=label(ui.list_frame,'开始统计后\n这里会显示击杀过的怪物',size=12,color=MUTED,justify='center',anchor='center')
    ui.empty_label.place(relx=.5,rely=.55,anchor='center')

    foot=frame(ui.surface);foot.grid(row=3,column=0,sticky='ew',padx=22,pady=(8,12))
    foot.columnconfigure(0,weight=1)
    ui.estimate_label=label(foot,variable=ui.estimate_display,size=10,color=MUTED)
    ui.estimate_label.grid(row=0,column=0,sticky='w',pady=(0,6))
    controls=frame(foot);controls.grid(row=1,column=0,sticky='ew');controls.columnconfigure(0,weight=1)
    for attr,text,command in [('start_button','开始新会话',ui.start),('stop_button','结束并保存',ui.stop)]:
        button=ctk.CTkButton(controls,text=text,height=40,corner_radius=10,font=font(13,True),
                             fg_color=ACCENTS[ui.accent_name.get()][0],hover_color='#405b9d',text_color='white',command=command)
        button.grid(row=0,column=0,sticky='ew');setattr(ui,attr,button)
        ui.accent_controls.append((button,'fg_color'))
    ui.stop_button.grid_remove();ui.stop_button.configure(state='disabled')
    ui.status_label=label(foot,variable=ui.status,size=10,color=MUTED,justify='left')
    ui.status_label.grid(row=2,column=0,sticky='ew',pady=(10,0))
    def resize(event):
        if event.widget is ui.surface:
            width=max(200,event.width/scale-44)
            for item in (ui.map_label,ui.estimate_label,ui.status_label):item.configure(wraplength=width)
    ui.surface.bind('<Configure>',resize,add='+')
    ui.root.bind('<Destroy>',lambda event:cleanup_callbacks(ui.root) if event.widget is ui.root else None,add='+')


def add_appearance_settings(ui):
    container=ttk.Frame(ui.tabs)
    ui.tabs.insert(1,container,text='外观')
    page=ctk.CTkFrame(container,fg_color=SURFACE,corner_radius=0)
    page.pack(fill='both',expand=True,padx=18,pady=18)
    def title(text):
        ctk.CTkLabel(page,text=text,font=('Microsoft YaHei UI',14,'bold'),text_color=TEXT).pack(anchor='w',pady=(16,8))
    title('显示风格')
    ctk.CTkSegmentedButton(page,values=['浅色','深色'],variable=ui.appearance,
                           command=lambda _:apply_appearance(ui,persist=True)).pack(fill='x')
    title('强调色')
    ctk.CTkSegmentedButton(page,values=list(ACCENTS),variable=ui.accent_name,
                           command=lambda _:apply_appearance(ui,persist=True)).pack(fill='x')
    title('窗口不透明度')
    ui.opacity_slider=ctk.CTkSlider(page,from_=75,to=100,number_of_steps=25,variable=ui.opacity,
                                    command=lambda _:apply_opacity(ui))
    ui.opacity_slider.pack(fill='x',pady=8)
    ctk.CTkLabel(page,textvariable=ui.opacity_label,font=('Microsoft YaHei UI',13),text_color=TEXT).pack(anchor='w')
    ctk.CTkLabel(page,text='100% 完全不透明；降低后可透出后面的游戏画面。\n透明度会同时作用于背景和文字；设置窗口保持不透明。',
                  font=('Microsoft YaHei UI',12),text_color=MUTED,justify='left').pack(anchor='w',pady=12)
    ctk.CTkButton(page,text='恢复默认外观',corner_radius=9,command=lambda:reset_appearance(ui)).pack(anchor='w',pady=16)
    add_layout_settings(ui)
    apply_appearance(ui)
    apply_layout(ui,initial=True)


def add_layout_settings(ui):
    container=ttk.Frame(ui.tabs)
    ui.tabs.insert(2,container,text='显示内容')
    page=ctk.CTkFrame(container,fg_color=SURFACE,corner_radius=0)
    page.pack(fill='both',expand=True,padx=18,pady=18)
    ctk.CTkLabel(page,text='按需显示，EXP / 小时始终保留',font=('Microsoft YaHei UI',16,'bold'),text_color=TEXT).pack(anchor='w',pady=(12,18))
    ctk.CTkSwitch(page,text='小窗模式 · 仅看 EXP / 小时',variable=ui.mini_mode,
                  command=lambda:apply_layout(ui,persist=True)).pack(anchor='w',pady=(0,18))
    for key,title in SECTIONS.items():
        ctk.CTkCheckBox(page,text=title,variable=ui.visible_sections[key],text_color=TEXT,
                        command=lambda:apply_layout(ui,persist=True)).pack(anchor='w',pady=9)
    ctk.CTkLabel(page,text='小窗临时隐藏上述内容；退出后恢复你的勾选。\n隐藏内容仍继续统计，随时可以重新显示。',
                  font=('Microsoft YaHei UI',12),text_color=MUTED,justify='left').pack(anchor='w',pady=20)


def toggle_mini(ui):
    ui.mini_mode.set(not ui.mini_mode.get())
    apply_layout(ui,persist=True)


def apply_layout(ui,persist=False,initial=False):
    """Change presentation only. Preserve session, table rows and scroll position."""
    mini=ui.mini_mode.get()
    shown={key:not mini and value.get() for key,value in ui.visible_sections.items()}
    compact=not shown['monsters']
    if compact and not ui.layout_compact and not initial:
        ui.full_geometry=f'{ui.root.winfo_width()}x{ui.root.winfo_height()}'
    for key,widgets in ui.section_widgets.items():
        for widget in widgets:
            if shown[key]:widget.grid()
            else:widget.grid_remove()
    for widget in (ui.clock,ui.status_label):
        if mini:widget.grid_remove()
        else:widget.grid()
    if shown['kills'] or shown['monsters']:ui.estimate_label.grid()
    else:ui.estimate_label.grid_remove()
    if mini:
        ui.mini_state.grid();ui.pin_button.pack_forget()
    else:
        ui.mini_state.grid_remove()
        if not ui.pin_button.winfo_manager():ui.pin_button.pack(side='right',padx=(0,9))
    ui.surface.rowconfigure(2,weight=1 if shown['monsters'] else 0)
    ui.mini_button.configure(text='展开' if mini else '小窗')
    ui.root.update_idletasks()
    # Visible optional rows determine the minimum. Mini mode leaves the primary
    # start/stop action available, so no hidden control can trap an active session.
    minimum=ui.px(220) if mini else ui.px(260)
    needed=ui.surface.winfo_reqheight()+ui.px(14)
    if shown['monsters']:
        needed-=ui.table.winfo_reqheight()-ui.px(115)
    minimum=max(minimum,needed)
    ui.root.minsize(ui.px(340 if mini else 390),minimum)
    if compact:
        width=ui.px(340) if mini else max(ui.px(390),ui.root.winfo_width())
        ui.root.geometry(f'{width}x{minimum}')
    elif ui.layout_compact:
        import re
        match=re.fullmatch(r'(\d+)x(\d+)',ui.full_geometry)
        width,height=(int(match[1]),int(match[2])) if match else (ui.px(420),ui.px(720))
        ui.root.geometry(f'{max(ui.px(390),width)}x{max(minimum,height)}')
    ui.layout_compact=compact
    if persist:ui.save_settings()


def reset_appearance(ui):
    ui.appearance.set('浅色');ui.accent_name.set('雾蓝');ui.opacity.set(100)
    apply_appearance(ui,persist=True)


def apply_opacity(ui):
    value=max(75,min(100,ui.opacity.get()))
    ui.root.attributes('-alpha',value/100)
    ui.opacity_label.set(f'{value:.0f}%'+(' · 完全不透明' if value==100 else ' · 透出背景'))


def apply_appearance(ui,persist=False):
    dark=ui.appearance.get()=='深色';i=int(dark)
    ctk.set_appearance_mode('Dark' if dark else 'Light')
    ui.root.configure(background=BACK[i])
    style=ttk.Style(ui.root)
    style.configure('.',background=SURFACE[i],foreground=TEXT[i],font=('Microsoft YaHei UI',10))
    for name in ('TFrame','TLabel','TCheckbutton','TNotebook'):
        style.configure(name,background=SURFACE[i],foreground=TEXT[i])
    style.configure('Muted.TLabel',foreground=MUTED[i])
    style.configure('TNotebook.Tab',background=SOFT[i],foreground=MUTED[i],borderwidth=0)
    style.map('TNotebook.Tab',background=[('selected',SURFACE[i]),('active',SOFT[i])],
               foreground=[('selected',TEXT[i]),('active',TEXT[i])])
    style.layout('Modern.Treeview',[('Treeview.treearea',{'sticky':'nswe'})])
    style.configure('Modern.Treeview',background=SURFACE[i],fieldbackground=SURFACE[i],foreground=TEXT[i],
                     borderwidth=0,relief='flat',font=('Microsoft YaHei UI',10),rowheight=ui.px(33))
    style.configure('Modern.Treeview.Heading',background=SURFACE[i],foreground=MUTED[i],borderwidth=0,
                     relief='flat',font=('Microsoft YaHei UI',9),padding=(0,ui.px(6)))
    style.map('Modern.Treeview',background=[('selected',SOFT[i])],foreground=[('selected',TEXT[i])])
    style.map('Modern.Treeview.Heading',background=[('active',SOFT[i])])
    # Always use the darker accent on filled buttons, keeping white text legible.
    accent=ACCENTS[ui.accent_name.get()][0]
    for widget,property_name in ui.accent_controls:widget.configure(**{property_name:accent})
    for button in (ui.start_button,ui.stop_button):button.configure(hover_color=accent)
    apply_opacity(ui)
    if persist:ui.save_settings()
