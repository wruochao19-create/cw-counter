"""Build a clean source zip using an allowlist, not a copy of the working folder."""
from pathlib import Path
import hashlib
import zipfile

ROOT=Path(__file__).resolve().parents[1]
NAMES={'README.md','AGENT_SETUP.md','THIRD_PARTY_NOTICES.md','requirements.txt','.gitignore',
       'Start CW Counter.cmd','Setup CW Counter.cmd'}


def source_files():
    candidates=list(ROOT.iterdir())
    for directory in ('assets','vendor','tests','scripts','.github'):
        candidates.extend((ROOT/directory).rglob('*'))
    for path in sorted(candidates):
        relative=path.relative_to(ROOT)
        if not path.is_file() or any(part.startswith('.') and part!='.github' for part in relative.parts[:-1]):continue
        if len(relative.parts)==1 and (path.suffix=='.py' or path.name in NAMES):yield path
        elif relative.parts[0] in ('assets','vendor','tests','scripts','.github'):
            if '__pycache__' not in relative.parts and (path.suffix in ('.py','.md','.txt','.json','.onnx','.npz','.png','.yml') or path.name=='LICENSE.msgwatch'):
                yield path


def main():
    output=ROOT/'dist';output.mkdir(exist_ok=True)
    archive=output/'cw-counter-0.19-source.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for path in source_files():z.write(path,Path('cw-counter')/path.relative_to(ROOT))
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(f'{digest}  {archive.name}\n',encoding='ascii')
    print(f'{archive.name}: {archive.stat().st_size:,} bytes; SHA256 {digest}')


if __name__=='__main__':main()
