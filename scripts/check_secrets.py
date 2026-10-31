"""Pinned Gitleaks checks of full history and tracked files, with a dummy control."""
import argparse
import json
from pathlib import Path
import random
import shutil
import string
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--gitleaks',required=True,help='Checksum-verified official Gitleaks 8.30.1 executable')
args=parser.parse_args()
scanner=str(Path(args.gitleaks).resolve())
version=subprocess.check_output([scanner,'version'],text=True).strip()
if version!='8.30.1':raise SystemExit('Use the reviewed pinned Gitleaks version 8.30.1')

def scan(mode,target,extra=()):
    return subprocess.run([scanner,mode,str(target),'--redact','--no-banner','--exit-code','1',*extra],
                          cwd=ROOT,capture_output=True,text=True)

with tempfile.TemporaryDirectory(prefix='fieldwork-secret-check-') as directory:
    temp=Path(directory)
    control=temp/'control';control.mkdir()
    # Generated nonfunctional token-shaped fixture, never an account credential.
    rng=random.Random(1527)
    dummy='gh'+'p_'+''.join(rng.choice(string.ascii_letters+string.digits) for _ in range(36))
    (control/'fixture.txt').write_text('token = "'+dummy+'"\n')
    control_report=temp/'control-report.json'
    result=scan('dir',control,('--report-format=json','--report-path='+str(control_report)))
    findings=json.loads(control_report.read_text()) if control_report.exists() else []
    if result.returncode!=1 or not any(f.get('RuleID')=='github-pat' for f in findings):
        raise SystemExit('Scanner negative control did not detect the generated dummy token rule')
    print('Generated dummy leak was detected; its value is never printed.')
    snapshot=temp/'tracked';snapshot.mkdir()
    paths=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    for name in filter(None,paths):
        path=Path(name)
        if (path.is_absolute() or '..' in path.parts or (ROOT/path).is_symlink()
            or (path.name.startswith('.env') and path.name!='.env.example')
            or path.suffix in ('.pem','.key','.log','.zip')):
            raise SystemExit('Unexpected sensitive/artifact path tracked; inspect privately before publication')
        dest=snapshot/path;dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/path,dest)
    for result in (scan('dir',snapshot),scan('git',ROOT,('--log-opts=--all',))):
        print(result.stdout,end='');print(result.stderr,end='') # Scanner output is forced redacted.
        if result.returncode:raise SystemExit(result.returncode)
print('Pinned scanner passed tracked snapshot and full available history. Not a guarantee of all secret formats.')
