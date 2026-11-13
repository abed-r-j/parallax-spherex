"""Regenerate paper/main.tex from paper/paper.html so the two never drift apart.

paper.html is the edited source (it also produces ParallaX_IEEE.pdf through build_pdf.mjs).
This script converts its text, tables, figure captions and citations to LaTeX for the
IEEEtran conference class. Equations and table headers are written here by hand (they are
MathML / HTML layout in paper.html); change them in both places.

Run:  python paper/html_to_tex.py        (any Python 3.10+, no packages needed)

SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
"""
from __future__ import annotations

import re
from pathlib import Path

HERE = Path(__file__).resolve().parent

# reference number in paper.html -> BibTeX key in refs.bib (same order as the HTML list)
KEYS = [
    "spaceapps2026", "kuchner2017", "caselden2018", "meisner2018coadds", "bock2026",
    "akeson2026", "expsupp2026", "alard1998", "zackay2016", "holman2018", "rice2020",
    "batygin2016", "brown2021", "fortney2016", "luhman2014search", "meisner2018p9",
    "phan2025", "spherexdr1", "spherexqr3", "gaia2023", "marocco2021", "berthier2016",
    "horizons", "astropy2022", "luhman2014wise0855",
]

EQUATIONS = [
    r"K_i=\exp\!\left(-\Delta_i^2/2h^2\right)\ \ \text{for}\ |\Delta_i|<3h,\qquad h=s\,b_t(p),",
    r"T_t(p)=\hat a,\qquad(\hat a,\hat c)=\operatorname*{arg\,min}_{a,c}\sum_i w_i\,"
    r"(y_i-a-c\Delta_i)^2,",
    r"\ell_i=\frac{w_i\,(S_2-S_1\Delta_i)}{S_0S_2-S_1^2},\qquad S_k=\sum_i w_i\Delta_i^k,",
    r"\sigma_T^2=\sum_i \ell_i^2 v_i,\qquad n_{\mathrm{eff}}=1\Big/\sum_i \ell_i^2 .",
    r"m^2=\begin{cases} s_{\mathrm{w}}^2-\bar v, & s_{\mathrm{w}}^2>\bar v\,"
    r"\bigl(1+1.5\sqrt{2/\nu}\bigr),\\ 0, & \text{otherwise.}\end{cases}",
    r"\sigma_t^2=\alpha_t^2\,(v_t+\sigma_T^2)+\max\!\bigl[(g_dC_t)^2,\;"
    r"m^2\,(1+1/n_{\mathrm{eff}})\bigr],",
]

TEXT = {  # HTML entity -> LaTeX in text mode
    "&nbsp;": "~", "&mdash;": "---", "&ndash;": "--", "&ldquo;": "``", "&rdquo;": "''",
    "&times;": r"$\times$", "&deg;": r"$^\circ$", "&plusmn;": r"$\pm$", "&minus;": "$-$",
    "&asymp;": r"$\approx$", "&lt;": "$<$", "&gt;": "$>$", "&le;": r"$\le$",
    "&mu;": r"$\mu$", "&sigma;": r"$\sigma$", "&nu;": r"$\nu$", "&pi;": r"$\pi$",
    "&alpha;": r"$\alpha$", "&lambda;": r"$\lambda$", "&Delta;": r"$\Delta$",
    "&ell;": r"$\ell$", "&sum;": r"$\sum$", "&prime;": "$'$", "&thinsp;": r"\,",
    "&sim;": r"$\sim$", "&amp;": r"\&",
}
MATH = {k: v.strip("$") for k, v in TEXT.items()}
MATH.update({"&nbsp;": "~", "&minus;": "-", "&thinsp;": r"\,", "&ndash;": "-"})


def _entities(s: str, table: dict) -> str:
    return re.sub(r"&[A-Za-z]+;", lambda m: table[m.group(0)], s)


def _script(m: re.Match) -> str:
    body = re.sub(r"<[^>]+>", "", m.group(2))
    body = _entities(body, MATH)
    if re.fullmatch(r"[A-Za-z]{2,}", body):
        body = r"\mathrm{%s}" % body
    return "$%s{%s}$" % ("_" if m.group(1) == "sub" else "^", body)


def _italic(m: re.Match) -> str:
    body = m.group(1)
    plain = re.sub(r"\$[^$]*\$|&[A-Za-z]+;", "", body)
    if len(plain) <= 2:  # a symbol: goes to math mode
        return "$" + _entities(body, MATH).replace("$", "") + "$"
    return r"\emph{%s}" % body


def _cite(m: re.Match) -> str:
    return r"\cite{%s}" % ",".join(KEYS[int(n) - 1] for n in re.findall(r"\d+", m.group(0)))


def inline(s: str) -> str:
    """One run of HTML inline markup -> LaTeX."""
    s = " ".join(s.split())
    s = re.sub(r"\[\d+\](?:(?:,&nbsp;|&ndash;)\[\d+\])*", _cite, s)
    s = s.replace("<i>v&#772;</i>", r"$\bar{v}$").replace("%", r"\%").replace("|", "$|$")
    s = re.sub(r"(https?://[^\s<;]*[^\s<;.,])", r"\\url{\1}", s)
    s = re.sub(r"<(sub|sup)>(.*?)</\1>", _script, s)
    s = re.sub(r"<i(?: class=\"ell\")?>(.*?)</i>", _italic, s)
    s = re.sub(r"<b>(.*?)</b>", r"\\textbf{\1}", s)
    s = re.sub(r"</?span[^>]*>", "", s)
    s = _entities(s, TEXT)
    s = s.replace("$$", "")  # merge adjacent math runs: $S$$_{0}$ -> $S_{0}$
    assert "<" not in s.replace("$<$", "") and "&" not in s.replace(r"\&", ""), s
    return s


def rows(html: str) -> list[tuple[str, list[str]]]:
    body = re.search(r"<tbody>(.*?)</tbody>", html, re.S).group(1)
    out = []
    for cls, tr in re.findall(r"<tr(?: class=\"(\w+)\")?>(.*?)</tr>", body, re.S):
        out.append((cls, [inline(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]))
    return out


def table(html: str, number: int) -> str:
    title = inline(re.search(r'<span class="ttl">(.*?)</span>', html, re.S).group(1))
    note = re.search(r'<p class="tnote">(.*?)</p>', html, re.S)
    body = "\n".join(("\\addlinespace\n" if cls == "grp" else "") + " & ".join(c) + r" \\"
                     for cls, c in rows(html))
    if number == 1:
        env, spec, label = "table", "@{}lcccl@{}", "tab:fields"
        head = r"Field & Images & Passes & Size & Target core saturated \\"
    elif number == 2:
        env, spec, label = "table*", "@{}llcccccc@{}", "tab:ledger"
        head = (r"Field & Method & Usable & Depth & False detections & Same, statistical & "
                r"$f_{50}$, blank sky & $f_{50}$, next to a star \\" "\n"
                r" & & frames (\%) & ($\mu$Jy) & per frame & noise only & ($\mu$Jy) & "
                r"($\mu$Jy) \\")
    else:
        env, spec, label = "table*", r"@{}p{0.13\textwidth}p{0.57\textwidth}p{0.26\textwidth}@{}", \
            "tab:targets"
        head = r"Target & Measured with ParallaX & Reference \\"
    out = [r"\begin{%s}[t]" % env, r"\caption{%s}" % title, r"\label{%s}" % label,
           r"\centering", r"\footnotesize", r"\begin{tabular}{%s}" % spec, r"\toprule", head,
           r"\midrule", body, r"\bottomrule", r"\end{tabular}"]
    if note:
        out += [r"\par\vspace{3pt}", r"\parbox{\linewidth}{\scriptsize %s}" % inline(note.group(1))]
    out.append(r"\end{%s}" % env)
    return "\n".join(out)


def figure(html: str) -> str:
    src = re.search(r'<img src="([^"]+)"', html).group(1)
    assert (HERE / src).is_file(), src
    cap = inline(re.search(r"<figcaption>(.*?)</figcaption>", html, re.S).group(1))
    num, cap = re.match(r"Fig\. (\d)\. (.*)", cap, re.S).groups()
    wide = 'class="wide"' in html
    env = "figure*" if wide else "figure"
    width = {"3": r"0.72\textwidth", "4": r"0.9\textwidth"}.get(num, r"\linewidth")
    return "\n".join([r"\begin{%s}[t]" % env, r"\centering",
                      r"\includegraphics[width=%s]{%s}" % (width, src),
                      r"\caption{%s}" % cap, r"\label{fig:%s}" % num, r"\end{%s}" % env])


PREAMBLE = r"""% ParallaX paper, IEEE conference format. GENERATED from paper.html by html_to_tex.py:
% edit paper.html and re-run the script, or edit both files together.
% Compile (for example on Overleaf): pdflatex main, bibtex main, pdflatex main, pdflatex main.
% SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
\documentclass[conference]{IEEEtran}
\IEEEoverridecommandlockouts
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{cite}
\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{url}

\begin{document}

\title{@TITLE@\thanks{@TEAM@}}

\author{\IEEEauthorblockN{Abed El Rahmane Jaafir}
\IEEEauthorblockA{\textit{Saint Joseph University of Beirut}\\
Beirut, Lebanon}
\and
\IEEEauthorblockN{Mohamad Alayli}
\IEEEauthorblockA{\textit{Lebanese American University}\\
Beirut, Lebanon}}

\maketitle
"""


def main() -> None:
    html = (HERE / "paper.html").read_text(encoding="utf-8")
    title = inline(re.search(r"<h1>(.*?)</h1>", html, re.S).group(1))
    team = inline(re.search(r'<div class="team">(.*?)</div>', html, re.S).group(1))
    assert "Abed El Rahmane Jaafir" in html and "Mohamad Alayli" in html
    body = html[html.index('<div class="cols">'):html.index("<h2>References</h2>")]
    n_refs = len(re.findall(r"<li><span>\[\d+\]</span>", html))
    assert n_refs == len(KEYS), (n_refs, len(KEYS))
    out = [PREAMBLE.replace("@TITLE@", title).replace("@TEAM@", team)]
    block = re.compile(
        r'<div class="eq">.*?</div>|<div class="(?:wide )?tabwrap">.*?</div>|'
        r"<figure.*?</figure>|<ul>.*?</ul>|<h2>.*?</h2>|<h3>.*?</h3>|<p[^>]*>.*?</p>", re.S)
    n_eq = n_tab = 0
    for m in block.finditer(body):
        b = m.group(0)
        if b.startswith('<div class="eq"'):
            out.append("\\begin{equation}\n%s\n\\end{equation}" % EQUATIONS[n_eq])
            n_eq += 1
        elif b.startswith("<div"):
            n_tab += 1
            out.append(table(b, n_tab))
        elif b.startswith("<figure"):
            out.append(figure(b))
        elif b.startswith("<ul"):
            items = re.findall(r"<li>(.*?)</li>", b, re.S)
            out.append("\\begin{itemize}\n%s\n\\end{itemize}"
                       % "\n".join(r"\item " + inline(i) for i in items))
        elif b.startswith("<h2"):
            name = re.sub(r"<[^>]+>", "", b)
            numbered = re.match(r"[IVX]+\. (.*)", name)
            out.append(r"\section{%s}" % numbered.group(1) if numbered
                       else r"\section*{%s}" % name)
        elif b.startswith("<h3"):
            out.append(r"\subsection{%s}" % re.sub(r"^[A-Z]\. ", "", re.sub(r"<[^>]+>", "", b)))
        else:
            attrs, text = re.match(r"<p([^>]*)>(.*)</p>", b, re.S).groups()
            text = inline(text)
            if "abstract" in attrs:
                out.append("\\begin{abstract}\n%s\n\\end{abstract}"
                           % text.replace(r"\emph{Abstract}---", ""))
            elif "terms" in attrs:
                out.append("\\begin{IEEEkeywords}\n%s\n\\end{IEEEkeywords}"
                           % text.replace(r"\emph{Index Terms}---", ""))
            elif "text-indent:0" in attrs:
                out.append(r"\noindent " + text)
            else:
                out.append(text)
    assert n_eq == len(EQUATIONS) and n_tab == 3, (n_eq, n_tab)
    out.append("\\bibliographystyle{IEEEtran}\n\\bibliography{refs}\n\n\\end{document}")
    tex = "\n\n".join(out) + "\n"
    tex.encode("ascii")  # the file must stay plain ASCII
    bib = (HERE / "refs.bib").read_text(encoding="utf-8")
    have = set(re.findall(r"@\w+\{([^,\s]+),", bib))
    cited = {k for grp in re.findall(r"\\cite\{([^}]*)\}", tex) for k in grp.split(",")}
    assert cited <= have, cited - have
    assert cited == set(KEYS), set(KEYS) - cited
    order = []
    for grp in re.findall(r"\\cite\{([^}]*)\}", tex):
        order += [k for k in grp.split(",") if k not in order]
    assert order == KEYS, "citation order differs from the HTML reference list"
    for env in set(re.findall(r"\\begin\{([^}]+)\}", tex)):
        assert tex.count(r"\begin{%s}" % env) == tex.count(r"\end{%s}" % env), env
    assert tex.count("{") == tex.count("}"), "unbalanced braces"
    for line in tex.splitlines():
        assert len(re.findall(r"(?<!\\)\$", line)) % 2 == 0, "odd number of $ in: " + line[:90]
    (HERE / "main.tex").write_text(tex, encoding="ascii", newline="\n")
    print("main.tex written:", len(tex.split()), "words,", len(cited), "references cited,",
          tex.count(r"\includegraphics"), "figures,", n_tab, "tables,", n_eq, "equations")


if __name__ == "__main__":
    main()
