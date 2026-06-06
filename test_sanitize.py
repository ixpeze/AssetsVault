import html
import unicodedata
import re

def _sanitize_filename(raw: str, max_length: int = 200) -> str:
    name = html.unescape(raw)
    name = unicodedata.normalize('NFKD', name)
    name = name.replace('\u2013', '-').replace('\u2014', '-')
    name = name.replace('\u2018', '\'').replace('\u2019', '\'')
    name = name.replace('\u201c', '').replace('\u201d', '')
    name = ''.join(c for c in name if not unicodedata.combining(c))
    name = re.sub(r'[\\/:*?\"<>|\x00-\x1f]', '_', name)
    name = re.sub(r'[^\w .\-]', '_', name, flags=re.ASCII)
    name = re.sub(r'[_\s]+', '_', name)
    name = name.strip('_. ')
    if len(name) > max_length:
        name = name[:max_length].rstrip('_. ')
    return name or 'download'

print(_sanitize_filename('Coffee Table and Armchair Sets &#8211; 3D Models &#8211; Cafe Interior 3D Scenes &#8211; 028 &#8211; CORONA Render'))
