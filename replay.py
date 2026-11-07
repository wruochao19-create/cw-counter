"""Offline video replay. Never imports the window capture module."""
import bootstrap
import argparse
import json
import cv2
from PIL import Image
from counter import CounterSession
from catalog import settings_profile
from recognition import Calibration
from pixel_ocr import RapidReader


def main():
    parser = argparse.ArgumentParser(description='离线回放录像：只读取文件，输出候选击杀CSV')
    parser.add_argument('video')
    parser.add_argument('--settings', default=str(bootstrap.ROOT / 'settings.json'))
    parser.add_argument('--cropped', action='store_true', help='录像已裁成校准后的消息区域')
    parser.add_argument('--output', default=str(bootstrap.ROOT / 'replays'))
    args = parser.parse_args()
    settings = json.loads(open(args.settings, encoding='utf-8').read())
    cal = Calibration(**settings['calibration'])
    reader = RapidReader(settings_profile(settings))
    session = CounterSession(settings_profile(settings), settings.get('character',''), settings.get('map',''))
    video = cv2.VideoCapture(args.video)
    if not video.isOpened():
        parser.error('无法打开视频')
    fps = video.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        parser.error('无法读取视频帧率')
    session.open_log(args.output)
    frame_number, next_sample = 0, 0.0
    try:
        while True:
            ok, frame = video.read()
            if not ok:
                break
            timestamp = frame_number / fps
            frame_number += 1
            if timestamp < next_sample:
                continue
            next_sample = timestamp + 0.3
            if not args.cropped:
                if frame.shape[1::-1] != (cal.width, cal.height):
                    raise ValueError('视频必须只包含校准尺寸的游戏客户区，或使用 --cropped')
                left, top, right, bottom = cal.box()
                frame = frame[top:bottom,left:right]
            events, gap = reader.read(Image.fromarray(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)), timestamp)
            session.active_seconds = timestamp
            if gap:
                session.note('gap', '回放采样断档')
            for event in events:
                session.accept(**event)
        output = session.path.with_name(session.path.name.replace('-events.csv','-summary.csv'))
        session.export_summary(output)
        print(json.dumps({'counts':dict(session.counts),'uncertain':session.unresolved,'summary':str(output)},ensure_ascii=False))
    finally:
        video.release()
        session.close()


if __name__ == '__main__':
    main()
