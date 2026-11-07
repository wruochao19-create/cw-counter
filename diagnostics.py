"""Explicit, bounded recording of already captured notification crops only."""
import io
import json
from datetime import datetime
from pathlib import Path


class DiagnosticRecorder:
    def __init__(self,root,max_bytes=8*1024*1024,max_frames=80,duration=20):
        self.root=Path(root);self.path=None;self.start=None;self.done=False
        self.max_bytes=max_bytes;self.max_frames=max_frames;self.duration=duration
        self.bytes=0;self.frames=0

    def add(self,image,now,box,lines,events,hud=None):
        if self.done:return
        if self.start is None:self.start=now
        if now-self.start>=self.duration or self.frames>=self.max_frames:
            self.close();return
        buffer=io.BytesIO();image.save(buffer,format='PNG');pixels=buffer.getvalue()
        hud_pixels=b'';hud_details=None
        if hud:
            hud_image,hud_details=hud
            buffer=io.BytesIO();hud_image.save(buffer,format='PNG');hud_pixels=buffer.getvalue()
        record=json.dumps(dict(frame=self.frames,t=now-self.start,box=box,lines=lines,events=events,
                               hud=hud_details),ensure_ascii=False)+'\n'
        metadata=record.encode('utf-8')
        if self.bytes+len(pixels)+len(metadata)+len(hud_pixels)>self.max_bytes:
            self.close();return
        if self.path is None:
            self.path=self.root/datetime.now().strftime('%Y%m%d-%H%M%S-%f')
            self.path.mkdir(parents=True)
        (self.path/f'{self.frames:03d}.png').write_bytes(pixels)
        if hud_pixels:(self.path/f'{self.frames:03d}-hud.png').write_bytes(hud_pixels)
        with (self.path/'frames.jsonl').open('ab') as handle:handle.write(metadata)
        self.bytes+=len(pixels)+len(metadata)+len(hud_pixels);self.frames+=1

    def close(self):
        self.done=True
