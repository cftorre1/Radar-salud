from pathlib import Path
import subprocess,hashlib,json,ast
repo=Path('/workspace/work/codex-h/implementation');out=Path('/workspace/work/codex-h/ci-close/reviewer');base='68749a93d67e871ce9aaf7dc72b8f80458a17154'
def git(*args):return subprocess.check_output(['git','-C',str(repo),*args])
tracked=['scripts/export_public_sources.py','scripts/export_web_snapshot.py','src/radar_salud/public_source_catalog.py'];test='tests/test_public_source_catalog_cli.py'
patch=git('diff','--binary',base,'--',*tracked)
x=subprocess.run(['git','-C',str(repo),'diff','--no-index','--binary','--','/dev/null',test],capture_output=True)
assert x.returncode in (0,1);patch+=x.stdout
(out/'reviewed-code.diff').write_bytes(patch)
files={p:hashlib.sha256((repo/p).read_bytes()).hexdigest() for p in [*tracked,test]};signature=hashlib.sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode()).hexdigest()
old_catalog=ast.parse(git('show',base+':src/radar_salud/public_source_catalog.py').decode());new_catalog=ast.parse((repo/tracked[2]).read_text())
functions=lambda tree:{x.name:ast.dump(x,include_attributes=False) for x in tree.body if isinstance(x,ast.FunctionDef)}
old_functions=functions(old_catalog);new_functions=functions(new_catalog);assert all(new_functions[k]==v for k,v in old_functions.items())
checks=json.load(open(out/'independent-cli-checks.json'))
report={'verdict':'PASS_SCOPED_CLI_FIX_PENDING_FINAL_SHA_AND_REMOTE_CI','reviewer':'CodexH-IndependentReviewer','date':'2026-10-12','baseline_head':base,'code_sha':None,'reviewed_diff_sha256':hashlib.sha256(patch).hexdigest(),'code_files_manifest_sha256':signature,'code_files_sha256':files,'preserved_catalog_functions':list(old_functions),'independent_checks':checks,'independent_subprocess_tests':{'passed':2,'env':'PYTHONPATH removed; installed radar_salud package from editable venv','log':'independent-cli-tests.log'},'failed_run':'38258425687','scope':'Only CLI packaging/import fix, helper relocation and two subprocess regressions; no product/editorial/gate reassessment.','open_p0':[],'open_p1':[],'limits':['Final commit SHA still required; remote CI result not certified.','No suite integral rerun; Builder reports60focused PASS and independent Reviewer ran only2CLI regressions plus offline export.','No external original reading/capture, paid pipeline call or deployment/merge approval.','Prior editorial/source/statistical HOLD and P2 scope limits preserved.','Existing pytest path handling masked scripts namespace failure; regression now exercises actual subprocess import environment.'],'evidence':{p:hashlib.sha256((out/p).read_bytes()).hexdigest() for p in ['reviewed-code.diff','independent-cli.log','independent-cli-checks.json','independent-cli-tests.log']}}
(out/'REVIEW_CI_CLI_EXPORT_2026_10_12.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
md=f'''# Reviewer independiente · cierre focal CLI de PR33

**PASS_SCOPED del arreglo local del CLI. Sin nuevos P0/P1 encontrados en este delta. SHA final y CI remota pendientes.** No amplía el PASS técnico/editorial previo ni levanta HOLD; no certifica publicación, beta, producción o merge.

Base HEAD: `{base}`. Árbol mutable revisado: tres archivos modificados y un test nuevo. Diff exacto `reviewed-code.diff` SHA256 `{report['reviewed_diff_sha256']}`. Manifest de los cuatro contenidos SHA256 `{signature}`. Se conciliarán con el commit final antes de la siguiente CI.

## Hallazgo y resolución

El run `38258425687` falló en staging al ejecutar `python scripts/export_web_snapshot.py --offline`: importó `scripts.export_public_sources` pese a que el entrypoint pone `scripts/` en sys.path y el paquete instalado sólo expone `radar_salud`. El snapshot ya se había escrito y el fallo ocurre al emitir el catálogo público. El pytest interno no reproduce necesariamente ese entorno.

La función `export_public_sources` pasa sin cambios de cuerpo/defaults al módulo instalable `radar_salud.public_source_catalog`; ambos scripts importan desde el paquete. AST de la función movida coincide con la anterior. AST de eligible/build_catalog permanece idéntico; snapshot cambia sólo la ruta del import. Los gates editoriales, políticas estadísticas, allowlist/fechas del catálogo, workflows, datos y paid lineage quedan fuera del delta.

## Corroboración independiente

- Export offline del CLI ejecutado como subprocess con `PYTHONPATH` eliminado y paquete instalado: exit0,165 señales. Salida en directorio propio del Reviewer, sin escribir web/data o data vivos.
- Las165 señales coinciden con la salida generada antes del fallo. Fecha coincide; generated_at es metadato de ejecución y no se exige igual. Source_health copiado byte por byte desde el original.
- Catálogo emitido:14 fuentes, filas sólo id/name/group/url/description, Reuters bloqueado excluido. No nueva captura ni llamada pagada.
- Dos regresiones subprocess ejecutadas por Reviewer:2PASS (`independent-cli-tests.log`). Standalone desde cwd temporal conserva input y excluye fuente bloqueada. No suite integral. Builder informa60tests focalesPASS, que se mantienen atribuidos al Builder.

|Archivo|SHA256 del contenido revisado|
|---|---|
'''
for p,h in files.items():md+=f'|{p}|`{h}`|\n'
md+='''
## Límites y siguiente comprobación

Receipt vinculado al diff del árbol actual; el commit final debe preservar los cuatro hashes o volver a revisar su delta. La CI completa del nuevo SHA sigue pendiente y puede descubrir fallos ajenos a este arreglo. La ausencia de nuevos P0/P1 en el patch no equivale a CI verde. Permanecen HOLD/P2 del informe editorial anterior.

Reviewer sólo escribe en ci-close/reviewer. No reabre originales, modifica implementación, autoriza llamadas pagadas, cambia gates o repite suite integral. Evidencia/logs/hash en JSON acompañante.
'''
(out/'REVIEW_CI_CLI_EXPORT_2026_10_12.md').write_text(md)
print(json.dumps({'verdict':report['verdict'],'diff_sha256':report['reviewed_diff_sha256'],'files_manifest_sha256':signature,'report':str(out/'REVIEW_CI_CLI_EXPORT_2026_10_12.md')}))
