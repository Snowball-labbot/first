"""Use installed Word for PDF conversion, then packaged DOCX renderer for PNG QA.

The packaged LibreOffice conversion is unavailable on this Windows host.
No skill files are modified. Word opens a separate hidden application instance.
"""
from pathlib import Path
import argparse
import importlib.util
import json


def main():
    p=argparse.ArgumentParser()
    p.add_argument('input',type=Path)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--renderer',type=Path,default=Path.home()/'.codex/plugins/cache/openai-primary-runtime/documents/26.909.12148/skills/documents/render_docx.py')
    p.add_argument('--dpi',type=int,default=130)
    args=p.parse_args()
    spec=importlib.util.spec_from_file_location('packaged_renderer',args.renderer)
    renderer=importlib.util.module_from_spec(spec);spec.loader.exec_module(renderer)
    info={}
    def word_pdf(doc_path,user_profile,output_dir,stem,verbose=False):
        import win32com.client
        app=win32com.client.DispatchEx('Word.Application')
        app.Visible=False;app.DisplayAlerts=0
        doc=None
        try:
            app.AutomationSecurity=3
            doc=app.Documents.Open(str(Path(doc_path).resolve()),ReadOnly=True,AddToRecentFiles=False)
            doc.Repaginate()
            info['word_version']=app.Version
            info['pages']=doc.ComputeStatistics(2)
            dest=Path(output_dir)/(stem+'.pdf')
            doc.ExportAsFixedFormat(str(dest.resolve()),17)
            return str(dest),'Microsoft Word native PDF export'
        finally:
            if doc is not None:doc.Close(False)
            app.Quit()
    renderer.convert_to_pdf=word_pdf
    args.out.mkdir(parents=True,exist_ok=True)
    paths=renderer.rasterize(str(args.input.resolve()),str(args.out.resolve()),args.dpi,False,True)
    info.update({'backend':'Microsoft Word COM + packaged render_docx.rasterize','page_images':len(paths)})
    (args.out/'render_audit.json').write_text(json.dumps(info,indent=2),encoding='utf-8')
    print(json.dumps(info))


if __name__=='__main__':main()
