#!/usr/bin/env python3
"""popola_sito.py - riempie un sito clonato con i contenuti di un 'pacchetto' JSON, con un solo comando.

1. Cosa fa: legge automazioni/testi/pacchetto_<nome>.json e, con i moduli di `automazioni/`, (a) toglie i contenuti
   d'esempio ereditati (servizi, post, progetti: file spostati in _cestino/ dal motore, non cancellati), (b) riscrive
   i testi della home, (c) crea servizi, articoli e progetti, (d) un solo commit + push alla fine.
2. Su quale file agisce: la cartella del clone accanto a questa (Desktop\\<nome-repo>): _pages/home.md (solo le righe
   indicate), _servizi/, _posts/, _projects/. Nessun file di questo sito di partenza.
3. Locale + git (push con gh gia' loggato). Nessuna API anonima.
4. Origine: richiesta del 06/10/2026 (sito di test automatico dopo nuovo_sito.py).

Uso (dalla cartella del sito di partenza):
  python popola_sito.py <nome-repo> <pacchetto> [--dry-run] [--no-pulisci] [--no-push]
FORMATO del pacchetto (dati, non codice): {"home": {...come testi/home_*.json...}, "servizi": [{"titolo","gruppo",
"descrizione","testo","in_home"}], "post": [{"titolo","categoria","descrizione","testo"}], "progetti": [{"titolo",
"descrizione","testo","in_home"}]}. Il testo e' markdown su piu' righe, scritto in un file temporaneo.
Idempotente: crea solo cio' che non esiste gia' (controlla l'elenco), la home e' idempotente di suo.
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

QUI = Path(__file__).resolve().parent
TESTI = QUI / 'automazioni' / 'testi'


def auto(*args, sito):
    """Lancia un comando di automazioni sul clone. Ritorna (codice, output)."""
    r = subprocess.run([sys.executable, '-m', 'automazioni', *args, '--sito', sito], cwd=QUI,
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    return r.returncode, ((r.stdout or '') + (r.stderr or '')).strip()


def slug_di(titolo):
    s = re.sub(r'[^a-z0-9]+', '-', titolo.lower().replace("'", '')).strip('-')
    return s


def esistenti(modulo, sito):
    _, o = auto(modulo, 'elenco', sito=sito)
    return set(re.findall(r'\[([a-z0-9-]+)\]', o))


def testo_file(testo):
    f = tempfile.NamedTemporaryFile('w', suffix='.md', delete=False, encoding='utf-8', newline='\n')
    f.write(testo.strip() + '\n')
    f.close()
    return f.name


def main():
    ap = argparse.ArgumentParser(description='Popola un clone con un pacchetto di contenuti.')
    ap.add_argument('nome', help='nome repo/cartella del clone')
    ap.add_argument('pacchetto', help='nome del pacchetto: automazioni/testi/pacchetto_<nome>.json')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--no-pulisci', action='store_true', help='non spostare in _cestino i contenuti ereditati')
    ap.add_argument('--no-push', action='store_true')
    a = ap.parse_args()

    dest = QUI.parent / a.nome
    if not dest.exists():
        sys.exit(f'ERRORE: {dest} non esiste (prima: python nuovo_sito.py {a.nome})')
    pk_path = TESTI / f'pacchetto_{a.pacchetto}.json'
    if not pk_path.exists():
        sys.exit(f'ERRORE: manca {pk_path}')
    pk = json.loads(pk_path.read_text(encoding='utf-8'))
    dr = ['--dry-run'] if a.dry_run else []
    log = []

    def esegui(etichetta, *args):
        c, o = auto(*args, *dr, sito=a.nome)
        ultima = o.splitlines()[-1] if o else ''
        log.append(f'{"OK " if c == 0 else "ERR"} {etichetta}: {ultima[:110]}')
        if c != 0:
            print('\n'.join(log))
            sys.exit(f'STOP su {etichetta}:\n{o[:600]}')

    nuovi = {'servizi': {slug_di(x['titolo']) for x in pk.get('servizi', [])},
             'post': {slug_di(x['titolo']) for x in pk.get('post', [])},
             'progetti': {slug_di(x['titolo']) for x in pk.get('progetti', [])}}

    if not a.no_pulisci:
        for mod in ('servizi', 'post', 'progetti'):
            for s in sorted(esistenti(mod, a.nome) - nuovi[mod]):
                esegui(f'{mod} elimina {s}', mod, 'elimina', s, '--si')

    if 'home' in pk:
        home = dict(pk['home'])
        home['sito'] = a.nome
        tmp = Path(tempfile.gettempdir()) / f'home_{a.nome}.json'
        tmp.write_text(json.dumps(home, ensure_ascii=False, indent=1), encoding='utf-8')
        esegui('home testi', 'pagine', 'testi', str(tmp))

    for mod, chiave in (('servizi', 'servizi'), ('post', 'post'), ('progetti', 'progetti')):
        gia = esistenti(mod, a.nome)
        for x in pk.get(chiave, []):
            s = slug_di(x['titolo'])
            if s in gia:
                log.append(f'-- {mod} {s}: gia\' presente')
                continue
            args = [mod, 'crea', '--titolo', x['titolo'], '--slug', s, '--testo-file', testo_file(x.get('testo', ''))]
            if x.get('descrizione'):
                args += ['--descrizione', x['descrizione']]
            if mod == 'servizi' and x.get('gruppo'):
                args += ['--gruppo', x['gruppo']]
            if mod == 'post' and x.get('categoria'):
                args += ['--categoria', x['categoria']]
            if x.get('in_home') and mod != 'post':
                args += ['--in-home']
            esegui(f'{mod} crea {s}', *args)

    print('\n'.join(log))
    if a.dry_run or a.no_push:
        print('Fine (nessun push).')
        return
    sh = lambda *c: subprocess.run(c, cwd=dest, capture_output=True, text=True, encoding='utf-8', errors='replace')
    sh('git', 'add', '-A')
    r = sh('git', 'commit', '-m', f'Contenuti di test: pacchetto {a.pacchetto}')
    print('commit:', (r.stdout or r.stderr).strip().splitlines()[0] if (r.stdout or r.stderr).strip() else '?')
    sh('git', 'pull', '--rebase', 'origin', 'main')
    sh('git', 'push', 'origin', 'main')
    print(sh('git', 'status', '-sb').stdout.strip().splitlines()[0])


if __name__ == '__main__':
    main()
