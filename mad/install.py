"""Проектная установка с предварительной проверкой конфликтов, без удаления данных."""
from pathlib import Path
from .core import ENGINE, MadError, load, safe, save, sha, write


def install(target, dry_run=False):
    target=Path(target).resolve()
    if target==ENGINE:
        raise MadError('В репозитории точки входа уже установлены')
    plan={}
    for folder in ('mad','agents','skills','knowledge','docs','schemas','.agents','.claude','.codex'):
        for source in (ENGINE/folder).rglob('*'):
            if source.is_file() and not source.is_symlink() and '__pycache__' not in source.parts:
                rel=source.relative_to(ENGINE).as_posix()
                plan[rel]=source.read_text(encoding='utf-8')
    for name in ('mad.py','AGENTS.md','CLAUDE.md','GEMINI.md','LICENSE','NOTICE.md'):
        plan[name]=(ENGINE/name).read_text(encoding='utf-8')
    manifest_path=safe(target,'.mad/install-manifest.json')
    old=load(manifest_path) if manifest_path.exists() else {}
    for rel,text in plan.items():
        dest=safe(target,rel)
        if dest.exists() and dest.read_text(encoding='utf-8')!=text and old.get(rel)!=sha(dest):
            raise MadError('Конфликт: '+rel+'. Пользовательский файл не изменён; используйте отдельную рабочую папку.')
    if not dry_run:
        for rel,text in plan.items():
            write(safe(target,rel),text)
        save(manifest_path,{rel:sha(safe(target,rel)) for rel in plan})
        ignore=safe(target,'.gitignore')
        prior=ignore.read_text() if ignore.exists() else ''
        needed=['mad.json','content/','analytics/','exports/','.mad/','.env','.env.*','__pycache__/']
        write(ignore,prior.rstrip()+'\n'+'\n'.join(x for x in needed if x not in prior.splitlines())+'\n')
    return {'dry_run':dry_run,'files':len(plan),'target':str(target),'network_called':False}
