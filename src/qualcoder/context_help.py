"""
This file is part of QualCoder.

QualCoder is free software: you can redistribute it and/or modify it under the
terms of the GNU Lesser General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later version.

QualCoder is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the GNU General Public License for more details.

You should have received a copy of the GNU Lesser General Public License along with QualCoder.
If not, see <https://www.gnu.org/licenses/>.

Author: Colin Curtain C, Kai Dröge, Justin Missaghieh--Poncet, Lorenzo Salomón
https://github.com/ccbogel/QualCoder
https://qualcoder-org.github.io
https://qualcoder.wordpress.com/
https://qualcoder.org/
"""

import logging

logger = logging.getLogger(__name__)

# Help pages on qualcoder.org/doc, keyed by module class name.
# Anchors are the fixed heading ids ({ #id }) shared by every language of the docs.
MODULE_HELP_PAGES = {
    # Manage
    "DialogManageFiles": "3.2.-Files/",
    "DialogManageLinks": "3.2.-Files/#manage-bad-links-to-files",
    "DialogCases": "3.3.-Cases/",
    "DialogManageAttributes": "3.4.-Attributes/",
    "DialogReferenceManager": "3.5.-References/",
    "DialogImportSurvey": "6.2.-Survey-Imports/",
    # Coding
    "DialogCodeText": "4.1.-Coding-Text/",
    "DialogCodePdf": "4.3.-Coding-Text-on-PDFs/",
    "DialogCodeImage": "4.4.-Coding-Images/",
    "DialogCodeAV": "4.5.-Coding-Audio-and-Video/",
    "CodeOrganiser": "4.6.-Code-Organiser/",
    "DialogCodeColorScheme": "4.7.-Codes-Tree/#accessibility-and-code-colours",
    # Analysis menu
    "DialogReportCodes": "5.3.-Analysis/#code-retrieval",
    "DialogReportCooccurrence": "5.3.-Analysis/#code-co-occurrence-report",
    "DialogReportRelations": "5.3.-Analysis/#code-relations-report",
    "DialogReportExactTextMatches": "5.3.-Analysis/#code-text-by-exact-matches-report",
    "DialogCodesBySegments": "5.3.-Analysis/#codes-by-text-segments-report",
    "ViewGraph": "5.5.-Graph/",
    # Reports menu
    "DialogReportCoderComparisons": "5.4.-Reports/#coding-comparison-report",
    "DialogCompareCoderByFile": "5.4.-Reports/#coding-comparison-by-file-report",
    "DialogReportComparisonTable": "5.4.-Reports/",
    "DialogReportCodeFrequencies": "5.4.-Reports/#code-frequencies-report",
    "DialogReportFileSummary": "5.4.-Reports/#file-summary-report",
    "DialogReportCodeSummary": "5.4.-Reports/#code-summary-report",
    "ViewCharts": "5.4.-Reports/#charts",
    "DialogSQL": "5.4.-Reports/#database-queries",
    # AI
    "DialogAIChat": "5.1.-AI-chat-based-analysis/",
    # Pop-up windows that keep their own Help button
    "DialogJournals": "5.2.-Journals/",
    "DialogSpeakers": "4.1.-Coding-Text/#auto-speaker-codings",
    "DialogViewAV": "3.2.-Files/#transcribing-audio-and-video",
}

# Inner tabs of a module that have their own page, keyed by tab index
INNER_TAB_HELP_PAGES = {
    "DialogCodeText": {1: "4.2.-AI-Assisted-Coding/"},
}


def module_help_page(module):
    """Help page for a module and its inner tab in view, or None."""

    name = type(module).__name__
    inner_pages = INNER_TAB_HELP_PAGES.get(name)
    if inner_pages:
        tab_widget = getattr(getattr(module, "ui", None), "tabWidget", None)
        if tab_widget is not None and tab_widget.currentIndex() in inner_pages:
            return inner_pages[tab_widget.currentIndex()]
    return MODULE_HELP_PAGES.get(name)


def open_module_help(app, module):
    """Open the help page of a module, used by its Ctrl+0 shortcut or Help button."""

    app.help_wiki(module_help_page(module) or "")


class ContextHelp:
    """Opens the help page for the main window tab in view.

    Host: the main window, with ui.tabWidget, the ui.tab_* pages and tab_placeholders.
    """

    def __init__(self, main_window):
        self.main_window = main_window
        ui = main_window.ui
        # Fallback pages when a tab shows no module
        self.tab_pages = {
            ui.tab_action_log: "3.1.-Creating-a-New-Project/",
            ui.tab_manage: "3.2.-Files/",
            ui.tab_coding: "4.1.-Coding-Text/",
            ui.tab_reports: "5.3.-Analysis/",
            ui.tab_ai_agent: "5.1.-AI-chat-based-analysis/",
        }

    def open_current(self):
        """Open the help page of the module or tab in view."""

        app = self.main_window.app
        tab = self.main_window.ui.tabWidget.currentWidget()
        module = self.current_module(tab)
        if module is not None:
            page = module_help_page(module)
            if page:
                app.help_wiki(page)
                return
            if callable(getattr(module, "help", None)):
                module.help()
                return
        app.help_wiki(self.tab_pages.get(tab, ""))

    def current_module(self, tab):
        """The module loaded in a tab (coding, report or manage window), or None."""

        layout = tab.layout() if tab is not None else None
        if layout is None or tab is self.main_window.ui.tab_action_log:
            return None
        placeholder = getattr(self.main_window, "tab_placeholders", {}).get(tab)
        for i in reversed(range(layout.count())):
            widget = layout.itemAt(i).widget()
            if widget is not None and widget is not placeholder and widget.isVisibleTo(tab):
                return widget
        return None
