"""A small, positive TeX body language; the host owns every definition.

This is deliberately not a full TeX parser. With fixed catcodes, no definitions,
no expansion primitives and an explicit command/environment vocabulary, accepted
bodies cannot introduce a new executable command. Compilation still takes place
in a separate, network-free, resource-bounded filesystem sandbox.
"""
from __future__ import annotations

import json
import re

from .util import ResearchStudioError, sha256_bytes

GRAMMAR_VERSION = "pmrs-restricted-tex-body/1"
MAX_BODY_BYTES = 2 * 1024 * 1024
MAX_DEPTH = 96
MAX_COMMANDS = 100000

# Argument-bearing operations here are formatting/math, never definitions,
# catcode changes, file access, package loading or expansion/dispatch primitives.
COMMANDS = frozenset("""
section subsection subsubsection paragraph subparagraph
textbf textit texttt textrm textsf emph underline textnormal
text mathrm mathbf mathit mathsf mathtt mathcal mathscr mathfrak mathbb
operatorname operatornamewithlimits boldsymbol pmod mod bmod pod
frac dfrac tfrac cfrac binom dbinom tbinom sqrt overline underline widehat
widetilde hat tilde bar vec dot ddot acute grave breve check boxed
left right middle big Big bigg Bigg bigl bigr Bigl Bigr biggl biggr Biggl Biggr
displaystyle textstyle scriptstyle scriptscriptstyle
alpha beta gamma delta epsilon varepsilon zeta eta theta vartheta iota kappa
lambda mu nu xi omicron pi varpi rho varrho sigma varsigma tau upsilon phi
varphi chi psi omega Gamma Delta Theta Lambda Xi Pi Sigma Upsilon Phi Psi Omega
sum prod coprod int iint iiint oint oiint lim liminf limsup inf sup max min
sin cos tan cot sec csc sinh cosh tanh coth arcsin arccos arctan log ln exp
det gcd hom ker dim deg Pr arg tr rank
in notin ni subset supset subseteq supseteq subsetneq supsetneq subsetneqq
supsetneqq setminus smallsetminus cup cap bigcup bigcap sqcup sqcap bigsqcup
vee wedge bigvee bigwedge oplus otimes odot bigoplus bigotimes
times div cdot ast star circ bullet pm mp +
le leq ge geq neq ne equiv sim simeq approx asymp cong propto ll gg
leqslant geqslant lesssim gtrsim prec succ preceq succeq
to mapsto rightarrow leftarrow leftrightarrow Rightarrow Leftarrow Leftrightarrow
longrightarrow longleftarrow longleftrightarrow Longrightarrow Longleftarrow
Longleftrightarrow hookrightarrow hookleftarrow twoheadrightarrow
uparrow downarrow updownarrow Uparrow Downarrow Updownarrow
forall exists nexists neg land lor implies iff
emptyset varnothing infty partial nabla ell hbar Re Im aleph beth
angle triangle triangleleft triangleright parallel perp mid nmid vert Vert
langle rangle lceil rceil lfloor rfloor lvert rvert lVert rVert
ldots cdots vdots ddots dots dotsc dotsb dotsm dotsi dotso
quad qquad space thinspace enspace hfill smallskip medskip bigskip
item newline linebreak newpage par noindent
toprule midrule bottomrule hline cline multicolumn
label ref eqref pageref cite bibitem footnote tag notag nonumber
mathop mathrel mathbin mathord mathopen mathclose mathpunct mathinner
limits nolimits not mbox stackrel overset underset substack
qed qedhere square blacksquare Box diamond Diamond
textbackslash textasciitilde textasciicircum textless textgreater
LaTeX TeX today
""".split()) - {"+", "today"}

ENVIRONMENTS = frozenset("""
theorem lemma proposition corollary definition remark example conjecture claim
proof equation equation* align align* aligned gathered gather gather* split
multline multline* cases matrix pmatrix bmatrix Bmatrix vmatrix Vmatrix smallmatrix
itemize enumerate description quote quotation center flushleft flushright
tabular longtable thebibliography
""".split())
CONTROL_SYMBOLS = frozenset("{}%$&#_ ,;!:|/\\()[]")
IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9:._-]{0,80}\Z")

HOST_MATH_DEFINITIONS = r"""\DeclareMathOperator{\rank}{rank}
\DeclareMathOperator{\tr}{tr}
\newtheorem{theorem}{Theorem}
\newtheorem{lemma}[theorem]{Lemma}
\newtheorem{proposition}[theorem]{Proposition}
\newtheorem{corollary}[theorem]{Corollary}
\newtheorem{claim}[theorem]{Claim}
\newtheorem{conjecture}[theorem]{Conjecture}
\theoremstyle{definition}
\newtheorem{definition}[theorem]{Definition}
\newtheorem{example}[theorem]{Example}
\theoremstyle{remark}
\newtheorem{remark}[theorem]{Remark}
"""


def tex_semantic_identity() -> str:
    """Math vocabulary/definitions, independent of font/compiler/layout identity."""
    policy = {"grammar": GRAMMAR_VERSION, "commands": sorted(COMMANDS),
              "environments": sorted(ENVIRONMENTS), "control_symbols": sorted(CONTROL_SYMBOLS),
              "identifier": IDENTIFIER.pattern, "host_math_definitions": HOST_MATH_DEFINITIONS,
              "limits": [MAX_BODY_BYTES, MAX_DEPTH, MAX_COMMANDS]}
    return sha256_bytes(json.dumps(policy, sort_keys=True).encode())


def _fail(reason: str) -> None:
    raise ResearchStudioError("PDF_TEX_UNSUPPORTED", reason)


def validate_tex(body: str) -> str:
    """Validate the complete restricted body and return its unchanged bytes/text.

    Placeholders must be expanded before this call. Citation and cross-reference
    identifiers have a separate plain-identifier grammar. Raw comments, TeX's
    superscript character-code notation and parameter tokens are not in this
    language. No command provided by a body can shadow trusted notation.
    """
    if not isinstance(body, str) or not body.strip():
        _fail("TeX body must be nonempty text")
    if len(body.encode("utf-8")) > MAX_BODY_BYTES:
        _fail("TeX body exceeds the bounded input size")
    if "^^" in body or "{{statement:" in body or "{{notation}}" in body:
        _fail("Encoded TeX characters or unresolved placeholders are not supported")
    i = 0
    depth = 0
    commands = 0
    environments: list[str] = []
    math: list[str] = []

    def argument(position: int) -> tuple[str, int]:
        while position < len(body) and body[position].isspace():
            position += 1
        if position >= len(body) or body[position] != "{":
            _fail("Expected a braced plain identifier")
        end = body.find("}", position + 1)
        if end < 0 or "{" in body[position + 1:end] or "\\" in body[position + 1:end]:
            _fail("Only plain identifiers are permitted here")
        return body[position + 1:end], end + 1

    while i < len(body):
        ch = body[i]
        if (ord(ch) < 32 and ch not in "\n\r\t") or ord(ch) == 127:
            _fail("Control characters are not supported")
        if ch in "%#":
            _fail("Use escaped percent/number signs; raw TeX tokens are not supported")
        if ch == "{":
            depth += 1
            if depth > MAX_DEPTH:
                _fail("TeX grouping depth exceeds the limit")
            i += 1
            continue
        if ch == "}":
            depth -= 1
            if depth < 0:
                _fail("Unbalanced TeX groups")
            i += 1
            continue
        if ch == "$":
            token = "$$" if body[i:i + 2] == "$$" else "$"
            if math and math[-1] == token:
                math.pop()
            elif math:
                _fail("Mismatched math delimiters")
            else:
                math.append(token)
            i += len(token)
            continue
        if ch != "\\":
            i += 1
            continue
        commands += 1
        if commands > MAX_COMMANDS:
            _fail("Too many TeX commands")
        i += 1
        if i == len(body):
            _fail("Incomplete control sequence")
        if not body[i].isascii() or not body[i].isalpha():
            symbol = body[i]
            if symbol not in CONTROL_SYMBOLS:
                _fail("Unsupported TeX control symbol")
            if symbol in "([":
                if math:
                    _fail("Nested math delimiters")
                math.append(symbol)
            elif symbol in ")]":
                if not math or math.pop() != {"": "", ")": "(", "]": "["}[symbol]:
                    _fail("Mismatched math delimiters")
            i += 1
            continue
        start = i
        while i < len(body) and body[i].isascii() and body[i].isalpha():
            i += 1
        command = body[start:i]
        if command in {"begin", "end"}:
            environment, i = argument(i)
            if environment not in ENVIRONMENTS:
                _fail("Unsupported TeX environment: " + environment)
            if command == "begin":
                environments.append(environment)
                if len(environments) > MAX_DEPTH:
                    _fail("Too many nested TeX environments")
            elif not environments or environments.pop() != environment:
                _fail("Mismatched TeX environments")
            continue
        if command not in COMMANDS:
            _fail("Unsupported TeX command: \\" + command)
        if command in {"label", "ref", "eqref", "pageref", "cite", "bibitem"}:
            # Citations and bibliography labels may have a plain optional note.
            while i < len(body) and body[i].isspace():
                i += 1
            if command in {"cite", "bibitem"} and i < len(body) and body[i] == "[":
                end = body.find("]", i + 1)
                if end < 0 or len(body[i + 1:end]) > 160 or any(c in body[i + 1:end] for c in "\\{}%#$[\n"):
                    _fail("Citation notes must be bounded plain text")
                i = end + 1
            identifiers, i = argument(i)
            parts = identifiers.split(",") if command == "cite" else [identifiers]
            if not parts or any(not IDENTIFIER.fullmatch(part) for part in parts):
                _fail("Invalid citation/cross-reference identifier")
    if depth or environments or math:
        _fail("Unclosed TeX group, environment or math delimiter")
    return body
