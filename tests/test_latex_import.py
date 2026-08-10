from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from qualcoder.latex_import import LatexImportError, latex_to_plain_text, tex_file_to_plain_text


class TestLatexImport(TestCase):
    def test_latex_to_plain_text_preserves_title_page_text_without_tikz_artifacts(self):
        raw_tex = r"""\documentclass[12pt,a4paper]{article}

\begin{document}

\begin{titlepage}

  \centering

\begin{tikzpicture}[remember picture, overlay]
  \node[anchor=north east, xshift=-1.5cm, yshift=-1.2cm]
  at (current page.north east)
  {\includegraphics[width=0.4\textwidth]{images/example-logo.png}};
\end{tikzpicture}

\vspace*{1.5cm}

    {\Large\textsc{Example Programme}}\\[0.2cm]
    {\large Example Research Project}\\[0.2cm]
    {\normalsize Fach: History \& Language}\\[0.8]

    \rule{0.80\textwidth}{0.5pt}\\[1.0cm]

    {\Huge\bfseries
    Example Main Title\\[0.25cm]
    Second Title Line
    }\\[0.8cm]

    {\Large
    Example Subtitle
    }\\[0.9cm]

    \rule{0.80\textwidth}{0.5pt}\\[2.5cm]

    \begin{tabular}{@{}ll}
        	textbf{Supervisors:} & Teacher 1, \\
                                 & Teacher 2 \\[6pt]


        	textbf{Autoren:} & Person 1, \\
                             & Person 2 \\[6pt]

        \vspace{0.5cm} \\
        	textbf{Klasse:} & Test \\[6pt]
        	textbf{Schule:} & Example Schule \\[6pt]
        	textbf{Datum:} & \today \\
    \end{tabular}

\end{titlepage}

\end{document}
"""

        text = latex_to_plain_text(raw_tex)

        self.assertNotIn("remember picture", text)
        self.assertNotIn("overlay", text)
        self.assertNotIn("anchor", text)
        self.assertNotIn("xshift", text)
        self.assertNotIn("yshift", text)
        self.assertNotIn("current page.north east", text)
        self.assertNotIn("<graphics>", text)
        self.assertNotIn("0.800.5pt", text)
        self.assertNotIn("0.600.4pt", text)
        self.assertIn("Example Programme", text)
        self.assertIn("Example Research Project", text)
        self.assertIn("Fach: History & Language", text)
        self.assertIn("Example Main Title", text)
        self.assertIn("Second Title Line", text)
        self.assertIn("Example Subtitle", text)
        self.assertIn("Supervisors:", text)
        self.assertIn("Teacher 1", text)
        self.assertIn("Teacher 2", text)
        self.assertIn("Autoren:", text)
        self.assertIn("Person 1", text)
        self.assertIn("Person 2", text)
        self.assertIn("Klasse:", text)
        self.assertIn("Test", text)
        self.assertIn("Schule:", text)
        self.assertIn("Example Schule", text)
        self.assertIn("Datum:", text)

    def test_latex_to_plain_text_without_tikz_stays_readable(self):
        raw_tex = r"""\section{Interview}

This is \textbf{important} and \emph{quoted} text.

\begin{itemize}
\item First answer
\item Second answer
\end{itemize}
"""

        text = latex_to_plain_text(raw_tex)

        self.assertEqual(
            "Interview\n\nThis is important and quoted text.\n\n  * First answer\n\n  * Second answer",
            text,
        )

    def test_latex_to_plain_text_handles_common_markup(self):
        raw_tex = r"""\section{Interview}

This is \textbf{important} and \emph{quoted} text.

\begin{itemize}
\item First answer
\item Second answer
\end{itemize}

Cafe \'{e} and $x^2$.

\input{ignored}
"""

        text = latex_to_plain_text(raw_tex)

        self.assertIn("Interview", text)
        self.assertIn("important", text)
        self.assertIn("quoted", text)
        self.assertIn("First answer", text)
        self.assertIn("Second answer", text)
        self.assertIn("Cafe é", text)
        self.assertIn("x^2", text)
        self.assertNotIn("ignored", text)

    def test_tex_file_to_plain_text_reads_file(self):
        with TemporaryDirectory() as temp_dir:
            tex_path = Path(temp_dir) / "sample.tex"
            tex_path.write_text(r"""\subsection{Notes}
A short line.
""", encoding="utf-8")

            text = tex_file_to_plain_text(tex_path)

        self.assertIn("Notes", text)
        self.assertIn("A short line.", text)

    def test_tex_file_to_plain_text_raises_on_missing_file(self):
        with TemporaryDirectory() as temp_dir:
            tex_path = Path(temp_dir) / "missing.tex"

            with self.assertRaises(LatexImportError):
                tex_file_to_plain_text(tex_path)
