"""Full-image calibration with a persistent movable/resizable suggestion."""
from dataclasses import asdict
import tkinter as tk
from tkinter import ttk,messagebox
from PIL import Image,ImageTk
from recognition import Calibration,fit_image
from pixel_ocr import RapidReader


def suggested_box(width,height):
    return (round(width*.74),round(height*.61),round(width*.995),round(height*.835))


def move_box(box,dx,dy,width,height):
    left,top,right,bottom=box
    dx=max(-left,min(width-right,round(dx)))
    dy=max(-top,min(height-bottom,round(dy)))
    return left+dx,top+dy,right+dx,bottom+dy


class CalibrationDialog:
    def __init__(self,parent,image,cal,on_save,profile=None,map_label=''):
        self.image=image
        self.cal=Calibration(**asdict(cal))
        self.on_save=on_save
        self.profile=profile
        self.map_label=map_label
        self.drag_start=self.draft=self.start_box=self.drag_canvas=None
        self.mode=None
        self.scale,self.offset_x,self.offset_y=1,0,0
        self.has_saved_region=bool(self.cal.region)
        if not self.cal.region:
            self.cal.select(suggested_box(image.width,image.height)[:2],suggested_box(image.width,image.height)[2:])
        self.window=tk.Toplevel(parent)
        self.window.title('校准 · 拖动框内移动，拖动边角缩放')
        w,h=parent.winfo_screenwidth(),parent.winfo_screenheight()
        self.window.geometry(f'{min(1180,w-60)}x{min(850,h-80)}')
        self.window.minsize(640,450)
        ttk.Label(self.window,text='框内按住左键移动，拖动边角调整大小；框外拖动可重画。保留完整经验文字及上方滚动空间。',wraplength=1050).pack(padx=10,pady=6)
        self.selection_info=tk.StringVar()
        ttk.Label(self.window,textvariable=self.selection_info,wraplength=1050).pack(anchor='w',padx=10)
        bottom=ttk.Frame(self.window);bottom.pack(side='bottom',fill='x',padx=10,pady=6)
        row=ttk.Frame(bottom);row.pack(fill='x')
        ttk.Button(row,text='恢复建议框',command=self.restore).pack(side='left')
        ttk.Button(row,text='试读当前图片',command=self.inspect).pack(side='left',padx=6)
        ttk.Label(row,text=f'地图：{map_label}' if map_label else 'RapidOCR · 地图尚未确认').pack(side='left')
        ttk.Button(row,text='保存选框',command=self.save).pack(side='right')
        self.result=tk.Text(bottom,height=5,font=('Microsoft YaHei UI',10),wrap='word')
        self.result.pack(fill='x',pady=(5,0))
        self.result.insert('end','已沿用上次保存的选框。' if self.has_saved_region else '已给出建议框，可先拖到经验提示位置，再点击试读。')
        self.canvas=tk.Canvas(self.window,bg='#151922',highlightthickness=0,cursor='crosshair')
        self.canvas.pack(fill='both',expand=True,padx=10,pady=5)
        self.canvas.bind('<Configure>',self.resize_preview)
        self.canvas.bind('<ButtonPress-1>',self.begin_drag)
        self.canvas.bind('<B1-Motion>',self.move_drag)
        self.canvas.bind('<ButtonRelease-1>',self.end_drag)
        self.canvas.bind('<Motion>',self.hover)
        self.describe()

    def describe(self):
        l,t,r,b=self.cal.box()
        self.selection_info.set(f'完整客户区 {self.image.width}×{self.image.height}；选框 ({l}, {t}, {r}, {b})，{r-l}×{b-t} 像素。')

    def resize_preview(self,event):
        if event.width<2 or event.height<2:return
        self.scale,self.offset_x,self.offset_y=fit_image(self.image.width,self.image.height,event.width,event.height)
        shown=self.image.resize((max(1,round(self.image.width*self.scale)),max(1,round(self.image.height*self.scale))),Image.Resampling.LANCZOS)
        self.photo=ImageTk.PhotoImage(shown)
        self.canvas.delete('photo')
        self.canvas.create_image(self.offset_x,self.offset_y,anchor='nw',image=self.photo,tags='photo')
        self.canvas.tag_lower('photo');self.draw()

    def image_point(self,x,y):
        return (max(0,min(self.image.width,(x-self.offset_x)/self.scale)),
                max(0,min(self.image.height,(y-self.offset_y)/self.scale)))

    def hit_test(self,x,y):
        l,t,r,b=self.cal.box()
        pad=8/self.scale
        west,east=abs(x-l)<=pad,abs(x-r)<=pad
        north,south=abs(y-t)<=pad,abs(y-b)<=pad
        if l-pad<=x<=r+pad and t-pad<=y<=b+pad:
            edge=('n' if north else 's' if south else '')+('w' if west else 'e' if east else '')
            if edge:return edge
        return 'move' if l<x<r and t<y<b else 'new'

    def hover(self,event):
        if self.drag_start:return
        mode=self.hit_test(*self.image_point(event.x,event.y))
        self.canvas.configure(cursor='fleur' if mode=='move' else 'sizing' if mode!='new' else 'crosshair')

    def begin_drag(self,event):
        if not (self.offset_x<=event.x<=self.offset_x+self.image.width*self.scale and
                self.offset_y<=event.y<=self.offset_y+self.image.height*self.scale):return
        self.drag_start=self.image_point(event.x,event.y)
        self.drag_canvas=(event.x,event.y)
        self.start_box=self.cal.box()
        self.mode=self.hit_test(*self.drag_start)
        self.draft=None

    def move_drag(self,event):
        if self.drag_start is None:return
        if abs(event.x-self.drag_canvas[0])+abs(event.y-self.drag_canvas[1])<6:return
        x,y=self.image_point(event.x,event.y)
        if self.mode=='move':
            self.draft=move_box(self.start_box,x-self.drag_start[0],y-self.drag_start[1],self.image.width,self.image.height)
        elif self.mode=='new':
            self.draft=(min(x,self.drag_start[0]),min(y,self.drag_start[1]),max(x,self.drag_start[0]),max(y,self.drag_start[1]))
        else:
            l,t,r,b=self.start_box
            if 'w' in self.mode:l=min(x,r-60)
            if 'e' in self.mode:r=max(x,l+60)
            if 'n' in self.mode:t=min(y,b-12)
            if 's' in self.mode:b=max(y,t+12)
            self.draft=(l,t,r,b)
        self.draw()

    def end_drag(self,event):
        self.move_drag(event)
        if self.draft is not None:
            try:
                self.cal.select(self.draft[:2],self.draft[2:])
                self.describe()
            except ValueError as exc:self.selection_info.set(str(exc))
        self.drag_start=self.drag_canvas=self.draft=None
        self.draw()

    def draw(self):
        self.canvas.delete('guide')
        l,t,r,b=self.draft or self.cal.box()
        l,r=l*self.scale+self.offset_x,r*self.scale+self.offset_x
        t,b=t*self.scale+self.offset_y,b*self.scale+self.offset_y
        self.canvas.create_rectangle(l,t,r,b,outline='#20d99b',width=2,tags='guide')
        for x,y in ((l,t),(r,t),(l,b),(r,b),((l+r)/2,t),((l+r)/2,b),(l,(t+b)/2),(r,(t+b)/2)):
            self.canvas.create_rectangle(x-4,y-4,x+4,y+4,fill='#20d99b',outline='#102a21',tags='guide')

    def restore(self):
        box=suggested_box(self.image.width,self.image.height)
        self.cal.select(box[:2],box[2:]);self.describe();self.draw()

    def inspect(self):
        self.result.delete('1.0','end');self.result.insert('end','正在离线识别……');self.window.update_idletasks()
        try:
            lines=RapidReader(self.profile).inspect(self.image.crop(self.cal.box()))
            output=[]
            for line in lines:
                parsed=line['said']
                status=f"{parsed[0]} +{parsed[1]}，{line['color']}" if parsed else '未匹配经验/金币提示'
                if parsed and line['score']<.8:
                    status+='（分数低，暂不计数）'
                if parsed:
                    if line.get('map_reread_used'):
                        status+='；经地图候选辅助重读'
                    if line.get('map_verified') is False:
                        status+='；当前地图无此基础经验，未确定'
                    elif line.get('map_matches'):
                        status+='；地图候选：'+' / '.join(line['map_matches'])
                    if line.get('digit_verified'):
                        status+='；数字校验通过'
                    else:
                        status+=f"；未确定、不计数（局部读取 {line.get('digit_reads',[])}，数字最低分 {line.get('digit_min_score',0):.2f}）"
                output.append(f"{line['text']}\n→ {status}；OCR 分数 {line['score']:.2f}")
            self.result.delete('1.0','end')
            self.result.insert('end','\n'.join(output) if output else '没有检测到文字。把框移到有经验提示的位置，或重新截取有提示的画面。')
        except Exception as exc:
            self.result.delete('1.0','end');self.result.insert('end',f'识别失败：{exc}')

    def save(self):
        try:
            self.on_save(self.cal);self.window.destroy()
        except Exception as exc:messagebox.showerror('保存选框',str(exc),parent=self.window)
