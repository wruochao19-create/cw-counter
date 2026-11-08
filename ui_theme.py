"""Shared colors and Tk widget styles for both windows."""
import ctypes
from ctypes import wintypes
from PIL import Image, ImageColor, ImageDraw, ImageTk
from windows_capture import root_window

SURFACE = ('#ffffff', '#202630')
BACK = ('#edf1f7', '#151a22')
TEXT = ('#263246', '#eef2f8')
MUTED = ('#68758a', '#a5b0c2')
LINE = ('#e9edf4', '#343d4b')
SOFT = ('#f3f6fb', '#2a3341')
ACCENTS = {'雾蓝': ('#5474c5', '#91aaff'), '松绿': ('#327b70', '#7dc7b8'), '鸢紫': ('#8060ae', '#c1a2ed')}


def mix(base, overlay, fraction):
    channels = (round(int(base[n:n+2], 16) * (1-fraction) + int(overlay[n:n+2], 16) * fraction)
                for n in (1, 3, 5))
    return '#' + ''.join(f'{c:02x}' for c in channels)


def rounded_control(ui, style, name, colors, background):
    """Stretch the center of a small rounded background; retain native tab/space focus."""
    skins = ui.__dict__.setdefault('settings_skins', {})
    px = ui.px
    size = px(24)
    for state, color in colors.items():
        canvas = Image.new('RGB', (size*3, size*3), background)
        ImageDraw.Draw(canvas).rounded_rectangle((0, 0, size*3-1, size*3-1), radius=px(7)*3,
                                                  fill=ImageColor.getrgb(color))
        image = canvas.resize((size, size), Image.Resampling.LANCZOS)
        key = (name, state)
        if key in skins:
            skins[key].paste(image)
        else:
            skins[key] = ImageTk.PhotoImage(image, master=ui.root)
    element = name + '.pill'
    if element not in style.element_names():
        style.element_create(element, 'image', skins[name, 'normal'],
                             ('selected', skins[name, 'selected']), ('active', skins[name, 'active']),
                             border=px(8), sticky='nswe')
        style.layout(name, [(element, {'sticky':'nswe', 'children':[
            ('Radiobutton.padding', {'sticky':'nswe', 'children':[
                ('Radiobutton.focus', {'sticky':'nswe', 'children':[
                    ('Radiobutton.label', {'sticky':'nswe'})]})]})]})])


def theme_settings(ui, style, i, fill, accent):
    surface, text, muted, soft = SURFACE[i], TEXT[i], MUTED[i], SOFT[i]
    tint = mix(surface, accent, .16)
    hover = mix(fill, '#000000', .14)
    edge = ('#bbc5d3', '#526176')[i]
    ui.settings_window.configure(background=BACK[i])
    # Only the two title bars belonging to this application.
    dark_caption = wintypes.BOOL(i)
    for window in (ui.root, ui.settings_window):
        hwnd = wintypes.HWND(root_window(window.winfo_id()))
        for attribute in (20, 19):
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attribute, ctypes.byref(dark_caption), ctypes.sizeof(dark_caption)) == 0:
                break
    style.configure('Muted.TLabel', foreground=muted)
    style.configure('Title.TLabel', font=('Microsoft YaHei UI', 15, 'bold'))
    style.configure('Section.TLabel', font=('Microsoft YaHei UI', 10, 'bold'))
    style.configure('TSeparator', background=LINE[i])
    style.configure('TButton', background=soft, foreground=text, bordercolor=edge, lightcolor=soft,
                    darkcolor=soft, relief='flat', padding=(10, 5), focuscolor=accent)
    style.map('TButton', background=[('active', tint)], foreground=[('disabled', muted)],
              bordercolor=[('focus', accent), ('active', accent)])
    # Clam has separate readonly/disabled field maps which override the default.
    for name in ('TEntry', 'TCombobox', 'TSpinbox'):
        style.configure(name, fieldbackground=soft, foreground=text, background=soft, bordercolor=edge,
                        lightcolor=soft, darkcolor=soft, arrowcolor=text, insertcolor=text, padding=(6, 4),
                        selectbackground=fill, selectforeground='white')
        style.map(name, fieldbackground=[('disabled', surface), ('readonly', soft)],
                  foreground=[('disabled', muted), ('readonly', text)], background=[('active', tint)],
                  bordercolor=[('focus', accent), ('active', accent)], arrowcolor=[('disabled', muted)])
    # A posted combobox uses a separate classic Tk listbox, even in a ttk window.
    options = dict(background=soft, foreground=text, selectbackground=fill, selectforeground='white')
    for key, value in options.items():
        ui.root.option_add(f'*TCombobox*Listbox.{key}', value)
    for combo in (ui.windows, ui.mode_entry, ui.map_entry):
        popup = combo.tk.call('ttk::combobox::PopdownWindow', combo)
        combo.tk.call(f'{popup}.f.l', 'configure', *(v for item in options.items() for v in ('-'+item[0], item[1])))
    for widget in (ui.monsters, ui.log):
        widget.configure(background=soft, foreground=text, insertbackground=text,
                         selectbackground=fill, selectforeground='white')
    variants = [('Nav.TRadiobutton', BACK[i], accent), ('Choice.TRadiobutton', soft, accent)]
    for index, pair in enumerate(ACCENTS.values()):
        variants.append((f'Swatch{index}.TRadiobutton', mix(surface, pair[i], .11), pair[i]))
    for name, bg, ink in variants:
        selected = fill if name != 'Nav.TRadiobutton' else tint
        is_swatch = name.startswith('Swatch')
        parent_color = BACK[i] if name.startswith('Nav') else surface
        readable_ink = ink if i else mix(ink, '#000000', .17)
        rounded_control(ui, style, name, dict(normal=bg, selected=selected, active=mix(surface, ink, .21)), parent_color)
        style.configure(name, background=parent_color,
                        foreground=readable_ink if is_swatch else text, padding=(12, 8), focuscolor=accent,
                        anchor='w' if name.startswith('Nav') else 'center')
        style.map(name, foreground=[('selected', readable_ink if name.startswith('Nav') else 'white'),
                                    ('active', readable_ink if is_swatch else text)])
    style.configure('Vertical.TScrollbar', troughcolor=surface, background=edge, arrowcolor=text,
                    lightcolor=edge, darkcolor=edge, bordercolor=surface)
    for widget in ui.settings_switches:
        widget.configure(progress_color=fill)
    ui.opacity_slider.configure(progress_color=accent, button_color=accent, button_hover_color=fill)
    return tint, hover
