"""
Generate a self-contained LaTeX benchmark report.

Reads JSON result files and the generated plots, then emits a .tex file
that can be compiled with pdflatex (or latexmk) into a full PDF report.

Usage:
    python -m weaviate_benchmarks.report          # generate report.tex
    python -m weaviate_benchmarks.report --compile # also compile to PDF
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import Any

from . import config as cfg
from .utils import ensure_dirs

REPORT_DIR = os.path.join(os.path.dirname(__file__), "report")


def _load_results(filename: str) -> list[dict]:
    path = os.path.join(cfg.RESULTS_DIR, filename)
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)


def _plots_relpath() -> str:
    """Return the relative path from REPORT_DIR to PLOTS_DIR for LaTeX includes."""
    return os.path.relpath(cfg.PLOTS_DIR, REPORT_DIR)


def _plot_exists(name: str) -> bool:
    return os.path.exists(os.path.join(cfg.PLOTS_DIR, f"{name}.png"))


# ── Table helpers ────────────────────────────────────────────────────────────

def _fmt(v: Any, decimals: int = 2) -> str:
    if isinstance(v, float):
        return f"{v:.{decimals}f}"
    if isinstance(v, int):
        return str(v)
    return str(v) if v is not None else "--"


def _fullness_table(results: list[dict], op_name: str, label: str, caption: str, tput_key: str = "throughput_chunks_sec") -> str:
    """Build a LaTeX table for fullness-sweep benchmarks."""
    from collections import defaultdict
    groups = defaultdict(list)
    for r in results:
        if r["operation"] == op_name and "fullness" in r:
            groups[r["fullness"]].append(r)
    if not groups:
        return ""

    rows = []
    for fullness in sorted(groups.keys()):
        items = groups[fullness]
        mean = sum(r.get("mean_ms", r.get("total_time_ms", 0)) for r in items) / len(items)
        median = sum(r.get("median_ms", 0) for r in items) / len(items)
        p90 = sum(r.get("p90_ms", 0) for r in items) / len(items)
        p99 = sum(r.get("p99_ms", 0) for r in items) / len(items)
        tput = sum(r.get(tput_key, 0) for r in items) / len(items)
        rows.append(f"{fullness} & {_fmt(mean)} & {_fmt(median)} & {_fmt(p90)} & {_fmt(p99)} & {_fmt(tput)} \\\\")

    body = "\n        ".join(rows)
    return rf"""
\begin{{table}}[htbp]
\centering
\caption{{{caption}}}
\label{{tab:{label}}}
\begin{{tabular}}{{rrrrrr}}
\toprule
\textbf{{Fullness}} & \textbf{{Mean (ms)}} & \textbf{{Median (ms)}} & \textbf{{P90 (ms)}} & \textbf{{P99 (ms)}} & \textbf{{Throughput (chunks/s)}} \\
\midrule
        {body}
\bottomrule
\end{{tabular}}
\end{{table}}
"""


# ── Figure helper ────────────────────────────────────────────────────────────


def _figure(name: str, caption: str, label: str, width: str = "0.95") -> str:
    if not _plot_exists(name):
        return ""
    rel = _plots_relpath()
    return rf"""
\begin{{figure}}[htbp]
\centering
\includegraphics[width={width}\textwidth]{{{rel}/{name}.png}}
\caption{{{caption}}}
\label{{fig:{label}}}
\end{{figure}}
"""


# ── Report sections ─────────────────────────────────────────────────────────


def _section_intro() -> str:
    return r"""
\section{Introduction}
\label{sec:intro}

This report presents focused performance benchmarks of the Weaviate vector
database, measuring operations on \textbf{Tag} references attached to
document \textbf{Chunks}.

The benchmarks measure:
\begin{itemize}
    \item \textbf{Read throughput} --- loading chunks with their tag references,
    using concurrent single-object reads and batched \texttt{contains\_any}
    ID-filter reads.
    \item \textbf{Reference addition} --- attaching tag references to chunks,
    comparing concurrent single-operation addition against batch
    \texttt{reference\_add\_many}.
    \item \textbf{Reference removal} --- detaching tag references from chunks
    via read-modify-write, both concurrently and in a sequential batch sweep.
\end{itemize}

Each operation is measured at multiple \emph{fullness levels} (number of
pre-existing tag references per chunk) and across multiple concurrency levels.

Throughput is reported in \textbf{chunks per second}, summing all concurrent
operations together.
"""


def _section_setup() -> str:
    return r"""
\section{Experimental Setup}
\label{sec:setup}

\subsection{Environment}
\begin{itemize}
    \item \textbf{Weaviate}: Instance on \texttt{""" + cfg.WEAVIATE_HOST + r"""}, REST port \texttt{""" + str(cfg.WEAVIATE_REST_PORT) + r"""}, gRPC port \texttt{""" + str(cfg.WEAVIATE_GRPC_PORT) + r"""}.
    \item \textbf{Collections}: Chunks = \texttt{""" + cfg.CHUNKS_COLLECTION + r"""}, Tags = \texttt{""" + cfg.TAG_COLLECTION + r"""}.
    \item \textbf{Client}: Python \texttt{weaviate-client} v4.x (async).
    \item \textbf{Operation count}: """ + str(cfg.OPERATION_COUNT) + r""" refs inserted/deleted per measurement.
    \item \textbf{Chunk sample size}: """ + str(cfg.CHUNK_SAMPLE_SIZE) + r""" (shuffled to avoid order bias).
    \item \textbf{Concurrency levels}: """ + ", ".join(str(c) for c in cfg.CONCURRENCY_LEVELS) + r""".
    \item \textbf{Fullness levels}: """ + ", ".join(str(f) for f in cfg.FULLNESS_LEVELS) + r""".
    \item \textbf{Read batch size}: """ + str(cfg.READ_BATCH_SIZE) + r""".
\end{itemize}

\subsection{Methodology}
For each fullness level the test:
\begin{enumerate}
    \item Incrementally adds tag references (batch) to reach the target fullness.
    \item Runs concurrent read tests across all affected chunks.
    \item Runs batch read tests (batches of """ + str(cfg.READ_BATCH_SIZE) + r""" chunks).
    \item For each concurrency level: adds then removes """ + str(cfg.OPERATION_COUNT) + r""" tag references concurrently.
    \item Adds then removes """ + str(cfg.OPERATION_COUNT) + r""" tag references using batch operations.
\end{enumerate}

All benchmark tags use the prefix \texttt{""" + cfg.BENCH_PREFIX + r"""} and are
cleaned up at the end. Throughput is wall-clock-based and counts all concurrent
operations, giving true aggregate throughput.
"""


def _section_reads(results: list[dict]) -> str:
    if not results:
        return ""
    s = r"""
\section{Read Performance}
\label{sec:reads}

Chunk reads fetch each object together with its tag references. Two strategies
are tested: concurrent single-object reads (via \texttt{fetch\_object\_by\_id})
and batch reads using a \texttt{contains\_any} ID filter.
"""
    s += _fullness_table(results, "read_concurrent", "read_conc_fullness",
                         "Concurrent read latency and throughput at varying fullness levels (averaged across concurrency).")
    s += _fullness_table(results, "read_batch", "read_batch_fullness",
                         "Batch read latency and throughput at varying fullness levels.")
    s += _figure("read_throughput_vs_fullness",
                 "Read throughput vs.\\ fullness level for concurrent and batch strategies.",
                 "read_tput_fullness")
    s += _figure("read_latency_vs_fullness",
                 "Read latency vs.\\ fullness level.",
                 "read_lat_fullness")
    s += _figure("read_throughput_vs_concurrency",
                 "Read throughput vs.\\ concurrency level at each fullness.",
                 "read_tput_conc")
    return s


def _section_ref_add(results: list[dict]) -> str:
    if not results:
        return ""
    s = r"""
\section{Reference Addition}
\label{sec:ref_add}

Adding a tag reference to a chunk uses either \texttt{reference\_add} (one at a
time, run concurrently) or \texttt{reference\_add\_many} (batch, one tag across
all chunks in a single call).
"""
    s += _fullness_table(results, "ref_add_concurrent", "ref_add_conc_fullness",
                         "Concurrent ref-add latency and throughput at varying fullness (averaged across concurrency).")
    s += _fullness_table(results, "ref_add_batch", "ref_add_batch_fullness",
                         "Batch ref-add throughput at varying fullness.")
    s += _figure("ref_add_throughput_vs_fullness",
                 "Ref-add throughput vs.\\ fullness for concurrent and batch strategies.",
                 "ref_add_tput_fullness")
    s += _figure("ref_add_latency_vs_fullness",
                 "Ref-add latency vs.\\ fullness level.",
                 "ref_add_lat_fullness")
    s += _figure("ref_add_throughput_vs_concurrency",
                 "Ref-add throughput vs.\\ concurrency level at each fullness.",
                 "ref_add_tput_conc")
    return s


def _section_ref_remove(results: list[dict]) -> str:
    if not results:
        return ""
    s = r"""
\section{Reference Removal}
\label{sec:ref_remove}

Removing a tag reference uses a read-modify-write pattern: fetch current
references, filter out the target, and replace the list. This is inherently
more expensive than addition.
"""
    s += _fullness_table(results, "ref_remove_concurrent", "ref_remove_conc_fullness",
                         "Concurrent ref-remove latency and throughput at varying fullness.")
    s += _fullness_table(results, "ref_remove_batch", "ref_remove_batch_fullness",
                         "Batch ref-remove throughput at varying fullness.")
    s += _figure("ref_remove_throughput_vs_fullness",
                 "Ref-remove throughput vs.\\ fullness for concurrent and batch strategies.",
                 "ref_remove_tput_fullness")
    s += _figure("ref_remove_latency_vs_fullness",
                 "Ref-remove latency vs.\\ fullness.",
                 "ref_remove_lat_fullness")
    s += _figure("ref_remove_throughput_vs_concurrency",
                 "Ref-remove throughput vs.\\ concurrency level at each fullness.",
                 "ref_remove_tput_conc")
    return s


def _section_summary(results: list[dict]) -> str:
    if not results:
        return ""
    s = r"""
\section{Summary}
\label{sec:summary}
"""
    s += _figure("operation_summary",
                 "Mean latency comparison of all operation types at fullness=0.",
                 "op_summary")
    s += r"""
\subsection{Key Findings}

\begin{enumerate}
    \item \textbf{Batch operations} provide the highest throughput for both
    reference addition and reads. \texttt{reference\_add\_many} amortises
    network round-trip overhead.
    \item \textbf{Concurrent single-op access} improves throughput over
    sequential execution but per-operation latency rises with concurrency
    due to server-side contention.
    \item \textbf{Fullness degrades performance} for reference operations.
    The impact is most pronounced for reference removal, which reads the
    full reference list before each update.
    \item \textbf{Reference removal is more expensive} than addition at all
    fullness levels because it requires a read-modify-write cycle.
\end{enumerate}
"""
    return s


# ── Main document assembly ──────────────────────────────────────────────────


def generate_report():
    """Generate the complete LaTeX report."""
    results = _load_results("tag_benchmarks.json")

    os.makedirs(REPORT_DIR, exist_ok=True)

    doc = r"""\documentclass[11pt,a4paper]{article}

% ── Packages ──
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage[margin=2.5cm]{geometry}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{hyperref}
\usepackage{xcolor}
\usepackage{float}
\usepackage{caption}

\hypersetup{
    colorlinks=true,
    linkcolor=blue!60!black,
    urlcolor=blue!60!black,
    citecolor=blue!60!black,
}

\title{Weaviate Tag Reference Benchmark Report}
\author{Automated Benchmark Suite}
\date{\today}

\begin{document}
\maketitle
\tableofcontents
\clearpage
"""

    doc += _section_intro()
    doc += _section_setup()
    doc += _section_reads(results)
    doc += _section_ref_add(results)
    doc += _section_ref_remove(results)
    doc += _section_summary(results)

    doc += r"""
\end{document}
"""

    tex_path = os.path.join(REPORT_DIR, "benchmark_report.tex")
    with open(tex_path, "w") as f:
        f.write(doc)
    print(f"LaTeX report written to {tex_path}")
    return tex_path


def compile_report(tex_path: str):
    """Compile the LaTeX report to PDF using latexmk."""
    report_dir = os.path.dirname(tex_path)
    try:
        subprocess.run(
            ["latexmk", "-pdf", "-interaction=nonstopmode",
             "-output-directory=" + report_dir, tex_path],
            check=True,
            capture_output=True,
            text=True,
        )
        pdf_path = tex_path.replace(".tex", ".pdf")
        print(f"PDF report compiled: {pdf_path}")
    except FileNotFoundError:
        print("latexmk not found. Install texlive-full or run manually:")
        print(f"  cd {report_dir} && latexmk -pdf benchmark_report.tex")
    except subprocess.CalledProcessError as e:
        print(f"LaTeX compilation failed:\n{e.stderr[-2000:]}")
        print(f"You can inspect the .tex file at: {tex_path}")


def main():
    parser = argparse.ArgumentParser(description="Generate LaTeX benchmark report")
    parser.add_argument("--compile", action="store_true", help="Also compile to PDF")
    args = parser.parse_args()

    tex_path = generate_report()
    if args.compile:
        compile_report(tex_path)


if __name__ == "__main__":
    main()
