"""Static frontend integrity/syntax checks, not a rendered-browser test."""
from html.parser import HTMLParser
from pathlib import Path
import re
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parent.parent


class Inspect(HTMLParser):
    def __init__(self):
        super().__init__();self.ids=[];self.links=[];self.labels=[];self.options=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if 'id' in a:self.ids.append(a['id'])
        if tag=='a' and a.get('href','').startswith('#'):self.links.append(a['href'])
        if tag=='label' and 'for' in a:self.labels.append(a['for'])
        if tag=='option':self.options.append(a)


def check():
    text=(ROOT/'web/index.html').read_text()
    page=Inspect();page.feed(text)
    assert len(page.ids)==len(set(page.ids)), 'Duplicate frontend IDs'
    for target in page.labels:assert target in page.ids, 'Missing input label target'
    for link in page.links:
        view,*section=link[1:].split('/')
        assert view in page.ids, 'Missing view target'
        if section:assert 'doc-'+section[0] in page.ids, 'Missing documentation target'
    assert {'corpus','answer-mode','question','endpoint-notice','doc-generation','serving-suite','suite-result','doc-serving-suite'}<=set(page.ids)
    assert any(o.get('value')=='endpoint' and 'disabled' in o for o in page.options)
    assert '.innerHTML' not in text and 'eval(' not in text, 'Untrusted text must not execute as HTML/code'
    scripts=re.findall(r'<script>(.*?)</script>',text,re.S)
    assert len(scripts)==1
    with tempfile.TemporaryDirectory() as d:
        script=Path(d)/'frontend.js';script.write_text(scripts[0])
        subprocess.run(['node','--check',str(script)],check=True)
    print('Static frontend IDs, links, labels, default mode and JavaScript syntax: PASS. Rendering not assessed.')


if __name__=='__main__':check()
