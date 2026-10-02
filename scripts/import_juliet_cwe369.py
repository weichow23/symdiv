#!/usr/bin/env python3
"""Materialize the frozen 24-case subset directly from checksum-verified NIST data."""
import argparse
import hashlib
import json
import random
import re
import subprocess
import urllib.request
import zipfile
from pathlib import Path
from symdiv.extract import extract_sites

URL = 'https://samate.nist.gov/SARD/downloads/test-suites/2017-10-01-juliet-test-suite-for-c-cplusplus-v1-3.zip'
SHA256 = 'ada9d7e1c323d283446df3f55bdee0d00bda1fed786785fe98764d58688f38eb'
SELECTION = [('01','divide'),('03','modulo'),('06','divide'),('16','modulo'),('17','divide'),('31','modulo')]
HEADER = '''/* Minimal interface; RAND32/URAND31 copied exactly from NIST Juliet 1.3. */
#ifndef SYMDIV_JULIET_COMPAT_H
#define SYMDIV_JULIET_COMPAT_H
int rand(void);
void printIntLine(int value);
void printLine(const char *value);
#define URAND31() (((unsigned)rand()<<30) ^ ((unsigned)rand()<<15) ^ rand())
#define RAND32() ((int)(rand() & 1 ? URAND31() : -URAND31() - 1))
#endif
'''


def sha(data): return hashlib.sha256(data).hexdigest()
def write_json(path, value): path.write_text(json.dumps(value,indent=2)+'\n')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--archive',default='tmp/juliet-1.3.zip')
    parser.add_argument('--out',default='benchmarks/juliet')
    parser.add_argument('--clang',default='clang')
    parser.add_argument('--offline',action='store_true',help='regenerate from the committed verified subset')
    args=parser.parse_args()
    out=Path(args.out); upstream=out/'upstream'; sources=out/'sources'; compat=out/'compat'
    for d in (upstream,sources,compat): d.mkdir(parents=True,exist_ok=True)
    archive=Path(args.archive)
    if not args.offline:
        if not archive.exists():
            archive.parent.mkdir(parents=True,exist_ok=True)
            urllib.request.urlretrieve(URL,archive)
        if sha(archive.read_bytes()) != SHA256: raise RuntimeError('NIST archive checksum mismatch')
        data=zipfile.ZipFile(archive)
        for family in ('zero','rand'):
            for variant,sink in SELECTION:
                name='CWE369_Divide_by_Zero__int_{}_{}_{}.c'.format(family,sink,variant)
                matches=[n for n in data.namelist() if n.endswith('/'+name)]
                if len(matches)!=1: raise RuntimeError('upstream selection is not unique: '+name)
                (upstream/name).write_bytes(data.read(matches[0]))
        header=data.read('C/testcasesupport/std_testcase.h').decode()
        for line in HEADER.splitlines():
            if line.startswith('#define URAND31') or line.startswith('#define RAND32'):
                if line not in header: raise RuntimeError('compatibility macro differs from upstream')
        write_json(upstream/'checksums.json', {p.name:sha(p.read_bytes()) for p in sorted(upstream.glob('*.c'))})
    checksums=json.loads((upstream/'checksums.json').read_text())
    for name,value in checksums.items():
        if sha((upstream/name).read_bytes()) != value: raise RuntimeError('cached upstream source mismatch')
    (compat/'std_testcase.h').write_text(HEADER)
    subjects=[]
    for family in ('zero','rand'):
        for variant,sink in SELECTION:
            name='CWE369_Divide_by_Zero__int_{}_{}_{}.c'.format(family,sink,variant)
            for branch in ('bad','good'): subjects.append((family,variant,sink,name,branch))
    random.Random(6215).shuffle(subjects)
    cases=[]; provenance=[]
    for index,(family,variant,sink,name,branch) in enumerate(subjects,1):
        case_id='j{:03d}'.format(index)
        command=[args.clang,'-E','-P','-std=c11','-I',str(compat),
                 '-DOMITGOOD' if branch=='bad' else '-DOMITBAD',str(upstream/name)]
        process=subprocess.run(command,capture_output=True,text=True,check=True,timeout=30)
        source=process.stdout
        identifiers=sorted({x for x in re.findall(r'\b[A-Za-z_]\w*\b',source)
                            if re.search(r'bad|good|CWE|369',x,re.I)})
        renames={word:'fn_{:03d}'.format(i) for i,word in enumerate(identifiers,1)}
        source=re.sub(r'\b[A-Za-z_]\w*\b',lambda m:renames.get(m.group(),m.group()),source)
        # Diagnostic prose is irrelevant to the arithmetic and can reveal labels.
        source=re.sub(r'"(?:\\.|[^"\\])*"','"message"',source)
        source=source.strip()+'\n'
        if re.search(r'bad|good|CWE|369',source,re.I): raise RuntimeError('label-blinding check failed')
        path=sources/(case_id+'.c');path.write_text(source)
        sites=extract_sites(path,args.clang)
        if not sites: raise RuntimeError('derived subject has no integer sites')
        cases.append({'id':case_id,'file':'sources/'+case_id+'.c','expected_bug':branch=='bad',
                      'category':family+'-'+variant,'site_count':len(sites),'sha256':sha(path.read_bytes())})
        provenance.append({'id':case_id,'upstream_file':name,'upstream_archive_path':'C/testcases/CWE369_Divide_by_Zero/s02/'+name,
                           'upstream_sha256':checksums[name],'branch':branch,'source_family':family,
                           'flow_variant':variant,'sink':sink,'renames':renames,
                           'preprocessor_flags':['-E','-P','-std=c11','-DOMITGOOD' if branch=='bad' else '-DOMITBAD']})
    write_json(out/'manifest.json',{'schema_version':2,'name':'symdiv-juliet-24','language':'C11',
        'task':'integer division or remainder by zero','root':'.',
        'label_policy':'Upstream bad branch is positive; entire good branch (all helpers) is negative. File-level any-site warning. rand() results are independent integers in [0,2147483647]; 32-bit int and unsigned int.',
        'cases':cases})
    write_json(out/'provenance.json',{'suite_url':'https://samate.nist.gov/SARD/test-suites/112',
        'archive_url':URL,'archive_sha256':SHA256,'source':'verified official NIST archive',
        'license':'CC0-1.0 / public domain; see NOTICE.md','shuffle_seed':6215,
        'header_sha256':sha(HEADER.encode()),'cases':provenance})
    print('Materialized {} files, {} sites.'.format(len(cases),sum(c['site_count'] for c in cases)))


if __name__=='__main__': main()
