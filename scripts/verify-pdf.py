#!/usr/bin/env python3
"""Render a controlled two-page fixture with the real PDF tools and zero models.

The output is a local renderer check, not a mathematical report approval or a
target Ubuntu E2E certificate. Inspect both generated PNGs after running it.
"""
import argparse
import hashlib
import json
import platform
import sys
from pathlib import Path

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--out',type=Path,required=True)
p.add_argument('--runtime-root',type=Path,default=Path(__file__).resolve().parents[1],
               help='Source root or installed package directory to verify')
a=p.parse_args()
root=a.runtime_root.resolve();sys.path.insert(0,str(root))
from research_studio import render

assert Path(render.__file__).resolve().is_relative_to(root),'Unexpected runtime import'
out=a.out.absolute();out.mkdir(parents=True,exist_ok=False)
body=r'''\section{Local PDF rendering check}
This controlled fixture checks the actual offline compiler and every rendered
page. No research model is called and no research claim is certified.

\subsection{Mathematical notation}
Let $x\in\mathbb{R}$. The symbols below exercise common report notation.
\begin{align*}
\int_0^1 x^2\,dx &= \frac{1}{3}, &
\sum_{n=1}^{\infty}\frac{1}{n^2} &= \frac{\pi^2}{6}, \\
\nabla\cdot\mathbf{v} &= 0, &
\lVert u\rVert_{L^2}^2 &= \int_{\Omega}|u|^2\,dx.
\end{align*}
\begin{theorem}
For a real number $x$, one has $x^2\geq 0$.
\end{theorem}
\begin{proof}
If $x\geq 0$, the product $x\cdot x$ is nonnegative. If $x<0$, then
$x^2=(-x)^2$ and $-x>0$.
\end{proof}
\textbf{Scope:} A successful compile does not approve a research report.

\newpage
\section{Layout and extraction check}
This second page exercises page counting, table layout and text extraction.

\begin{center}
\begin{tabular}{ll}
\toprule
Check & Expected result \\
\midrule
Paid research model calls & Zero \\
Network downloads & Zero \\
Rendered pages & Two \\
Mathematical authority & Unchanged \\
\bottomrule
\end{tabular}
\end{center}

\subsection{Review boundary}
The research target remains open until the project's own evidence and review
requirements are met. This document tests PDF infrastructure only.

\begin{itemize}
\item Text and mathematical glyphs must remain legible.
\item Tables must not overlap or extend beyond the margins.
\item Both page images must be inspected before visual acceptance.
\end{itemize}
'''.encode()
(out/'fixture.tex').write_bytes(body)
record={'kind':'LOCAL_RENDERER_CHECK','runtime_file':str(Path(render.__file__).resolve()),
        'runtime_sha256':hashlib.sha256(Path(render.__file__).read_bytes()).hexdigest(),
        'platform':platform.platform(),'python':sys.version,'doctor':render.doctor(),
        'paid_model_calls':0,'target_ubuntu':'NOT_RUN_ON_TARGET_UBUNTU',
        'visual_inspection':'PENDING','mathematical_report_approved':False}
try:
    result=render.Renderer()(body)
    assert len(result['pages'])==2,'Expected two actual pages'
    assert result['synthetic'] is False,'Mock renders are not accepted'
    for key in ('offline','namespace_isolated','all_pages_rendered'):assert result['environment'][key] is True
    (out/'render-check.pdf').write_bytes(result['pdf']);(out/'render-check.tex').write_bytes(result['tex'])
    for i,page in enumerate(result['pages'],1):(out/f'page-{i}.png').write_bytes(page)
    record.update(status='PASS',pages=len(result['pages']),semantic_environment=result['semantic_environment'],environment=result['environment'])
except Exception as error:
    record.update(status='FAIL',error=str(error))
record['files']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir()) if p.is_file()}
(out/'RESULT.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in record.items() if k in ('status','pages','error','paid_model_calls','visual_inspection')},indent=2))
sys.exit(0 if record['status']=='PASS' else 1)
