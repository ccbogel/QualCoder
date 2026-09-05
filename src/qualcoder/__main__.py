#!/usr/bin/python
# -*- coding: utf-8 -*-

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

import base64
import datetime
import gettext
import json  # To get the latest GitHub release information
import logging
from logging.handlers import RotatingFileHandler
import multiprocessing
import os
from pathlib import Path
import platform
import shutil
import sqlite3
import sys
from typing import Optional
import urllib.request
import webbrowser

# Hugging Face tokenizers otherwise creates a native Rayon thread pool which can
# outlive the Qt window in frozen macOS builds and crash during QApplication teardown.
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from PyQt6 import QtCore, QtGui, QtWidgets
import qtawesome as qta
from qualcoder.ai_chat import DialogAIChat
from qualcoder.ai_prompt_library import DialogAiEditPrompts
from qualcoder.app import App
from qualcoder.error_dlg import qt_exception_hook
from qualcoder.attributes import DialogManageAttributes
from qualcoder.cases import DialogCases
from qualcoder.code_av import DialogCodeAV
from qualcoder.code_color_scheme import DialogCodeColorScheme
from qualcoder.code_organiser import CodeOrganiser
from qualcoder.code_text import DialogCodeText
from qualcoder.code_pdf import DialogCodePdf
from qualcoder.codebook import Codebook
from qualcoder.GUI.base64_droidsansmono_helper import DroidSansMono
from qualcoder.GUI.base64_notosans_helper import NotoSans
from qualcoder.GUI.ui_main import Ui_MainWindow
from qualcoder.helpers import get_default_user_directory, Message, ImportPlainTextCodes
from qualcoder.import_survey import DialogImportSurvey
from qualcoder.information import DialogInformation, menu_shortcuts_display, coding_shortcuts_display
from qualcoder.information import manage_tab_info, coding_tab_info, reports_tab_info, render_tab_info_markdown
from qualcoder.journals import DialogJournals
from qualcoder.manage_files import DialogManageFiles
from qualcoder.manage_links import DialogManageLinks
from qualcoder.manage_references import DialogReferenceManager
from qualcoder.memo import DialogMemo
from qualcoder.refi import RefiExport, RefiImport
from qualcoder.reports import DialogReportCoderComparisons, DialogReportCodeFrequencies
from qualcoder.report_code_summary import DialogReportCodeSummary
from qualcoder.report_compare_coder_file import DialogCompareCoderByFile
from qualcoder.report_comparison_table import DialogReportComparisonTable
from qualcoder.report_codes import DialogReportCodes
from qualcoder.report_codes_by_segments import DialogCodesBySegments
from qualcoder.report_cooccurrence import DialogReportCooccurrence
from qualcoder.report_file_summary import DialogReportFileSummary
from qualcoder.report_exact_matches import DialogReportExactTextMatches
from qualcoder.report_relations import DialogReportRelations
from qualcoder.report_sql import DialogSQL
from qualcoder.rqda import RqdaImport
from qualcoder.settings import DialogSettings
from qualcoder.special_functions import DialogSpecialFunctions
from qualcoder.taguette_import import TaguetteImport
from qualcoder.view_charts import ViewCharts
from qualcoder.view_graph import ViewGraph
from qualcoder.view_image import DialogCodeImage

# Check if VLC installed, for warning message for code_av
vlc = None
try:
    import vlc
except Exception as e:  # python-vlc missing: Qt backend takes over, no console noise
    logging.getLogger(__name__).debug(f"python-vlc unavailable: {e}")

qc_config_folder = Path('~').expanduser() / '.qualcoder'

if not qc_config_folder.exists():
    try:
        qc_config_folder.mkdir(exist_ok=True)
    except Exception as e:
        print(f"Cannot create .qualcoder folder.\n{e}")
        raise
logfile = qc_config_folder / 'QualCoder.log'
log_maxBytes = 500000  # 500 KB: max length of the logfile before old entries are discarded
# Hack for Windows 10 PermissionError that stops the rotating file handler, will produce massive files.
try:
    log_file = open(logfile, "r")
    data = log_file.read()
    log_file.close()
    if len(data) > log_maxBytes:
        logfile.unlink()
        log_file = open(logfile, "w")
        log_file.write(data[len(data) - (log_maxBytes // 2):])  # frees up half of log_maxBytes
        log_file.close()
except Exception as e:
    print(e)
logging.basicConfig(format='%(asctime)s %(levelname)s %(name)s.%(funcName)s %(message)s',
                    datefmt='%Y/%m/%d %H:%M:%S', filename=logfile)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
# The rotating file handler does not work on Windows
handler = RotatingFileHandler(logfile, maxBytes=log_maxBytes, backupCount=2)
logger.addHandler(handler)

BUILTIN_LANGUAGE_LABELS = [
    ("de", "Deutsch"),
    ("en", "English"),
    ("es", "Español"),
    ("fr", "Français")
]


class MainWindow(QtWidgets.QMainWindow):
    """ Main GUI window.
    Project data is stored in a directory with .qda suffix
    core data is stored in data.qda sqlite file.
    Journal and coding dialogs can be shown non-modally - multiple dialogs open.
    There is a risk of a clash if two coding windows are open with the same file text or
    two journals open with the same journal entry.

    Note: App.settings does not contain projectName, conn or path (to database)
    app.project_name and app.project_path contain these.
    """

    @staticmethod
    def _find_ai_model_index_by_name(ai_models: list, model_name: str) -> int:
        """Return the index of a named AI profile, or -1 if it is not present."""

        target_name = str(model_name).strip()
        for idx, model in enumerate(ai_models):
            if str(model.get('name', '')).strip() == target_name:
                return idx
        return -1

    def _show_pending_ai_model_upgrade_offer(self) -> None:
        """Show one deferred AI-profile upgrade offer after the main window is visible."""

        if self.app.settings.get('ai_enable', 'False') != 'True':
            return

        offer = getattr(self.app, 'pending_ai_model_upgrade_offer', None)
        if not isinstance(offer, dict) or len(offer) == 0:
            return

        current_model_name = str(offer.get('current_model_name', '')).strip()
        suggested_model_name = str(offer.get('suggested_model_name', '')).strip()
        current_index = self._find_ai_model_index_by_name(self.app.ai_models, current_model_name)
        suggested_index = self._find_ai_model_index_by_name(self.app.ai_models, suggested_model_name)
        try:
            selected_index = int(self.app.settings.get('ai_model_index', -1))
        except (TypeError, ValueError):
            selected_index = -1
        if current_index < 0 or suggested_index < 0 or current_index == suggested_index or \
                selected_index != current_index:
            self.app.pending_ai_model_upgrade_offer = None
            self.app.settings['ai_model_upgrade_offer_pending'] = ''
            self.app.write_config_ini(self.app.settings, self.app.ai_models)
            return

        seen_value = str(self.app.settings.get('ai_model_upgrade_offers_seen', '')).strip()
        seen_offers = {item for item in seen_value.split('||') if item != ''}
        if suggested_model_name in seen_offers:
            self.app.pending_ai_model_upgrade_offer = None
            self.app.settings['ai_model_upgrade_offer_pending'] = ''
            self.app.write_config_ini(self.app.settings, self.app.ai_models)
            return

        current_model = self.app.ai_models[current_index]
        suggested_model = self.app.ai_models[suggested_index]
        msg = _(
            'A newer default AI profile is now available for this provider.\n\n'
            'Current profile: {current}\n'
            'New profile: {new}\n\n'
            'Do you want to switch to the new profile now?\n'
            'Your existing API-key (if available) will be copied to the new profile for convenience.'
        ).format(
            current=str(current_model.get('name', '')).strip(),
            new=str(suggested_model.get('name', '')).strip(),
        )
        msg_box = Message(self.app, _('AI Setup'), msg, 'Information')
        switch_button = msg_box.addButton(_('Switch to new profile'), QtWidgets.QMessageBox.ButtonRole.YesRole)
        keep_button = msg_box.addButton(_('Keep current profile'), QtWidgets.QMessageBox.ButtonRole.NoRole)
        msg_box.setDefaultButton(keep_button)
        msg_box.exec()

        seen_offers.add(suggested_model_name)
        self.app.settings['ai_model_upgrade_offers_seen'] = '||'.join(sorted(seen_offers))
        if msg_box.clickedButton() == switch_button:
            suggested_model['api_key'] = current_model.get('api_key', '')
            self.app.settings['ai_model_index'] = suggested_index
        self.app.settings['ai_model_upgrade_offer_pending'] = ''
        self.app.write_config_ini(self.app.settings, self.app.ai_models)
        self.app.pending_ai_model_upgrade_offer = None

    def __init__(self, app, force_quit=False):
        """ Set up user interface from ui_main.py file. """
        self.app = app
        self.force_quit = force_quit
        self.journal_display = None
        self.ai_chat_window = None
        self.ai_chat_sidebar_mode = False
        self.ai_chat_tab_label = None
        self.ai_chat_tab_sidebar_button = None
        self.last_non_ai_chat_tab = None
        self.project = {"databaseversion": "", "date": "", "memo": "", "about": ""}
        self.recent_projects = []  # a list of recent projects for the qmenu

        if platform.system() == "Windows" and self.app.settings['stylesheet'] == "native":
            # Make 'Fusion' the standard native style on Windows https://www.qt.io/blog/dark-mode-on-windows-11-with-qt-6.5
            # The default 'Windows' style seems partially broken at the moment, in combination with the native dark mode.
            # On macOS, 'Fusion' is the default style anyways (automatically chosen by Qt).
            QtWidgets.QApplication.instance().setStyle("Fusion")

        QtWidgets.QMainWindow.__init__(self)
        self.ai_sidebar_splitter_save_timer = QtCore.QTimer(self)
        self.ai_sidebar_splitter_save_timer.setSingleShot(True)
        self.ai_sidebar_splitter_save_timer.timeout.connect(self.persist_ai_sidebar_splitter_setting)
        self.ai_sidebar_splitter_is_restoring = False
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.init_placeholder_tab_layouts()
        # Test of macOS menu bar
        if self.app.settings['stylesheet'] == "native":
            self.ui.menubar.setNativeMenuBar(True)
        else:
            self.ui.menubar.setNativeMenuBar(False)
        self.get_latest_github_release()
        try:
            # Restore main window geometry (size, position, maximized state) from config
            geometry_hex = self.app.settings.get('mainwindow_geometry', '')
            if geometry_hex:
                self.restoreGeometry(QtCore.QByteArray.fromHex(geometry_hex.encode('utf-8')))
        except KeyError:
            pass
        self.hide_menu_options()
        font = f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";'
        self.setStyleSheet(font)
        self.init_ui()
        self.ui.tabWidget.setCurrentIndex(0)
        self.show()
        QtWidgets.QApplication.processEvents() 
        QtCore.QTimer.singleShot(0, self._restore_ai_splitters_after_show)
        self._show_pending_ai_model_upgrade_offer()
        # Setup AI
        try:
            global AiLLM
            from qualcoder.ai_llm import AiLLM  # import after showing the UI because this takes several seconds
            self.app.ai = AiLLM(self.app, self.ui.textEdit)
            # First start? Ask if user wants to enable ai integration or not
            if self.app.settings['ai_first_startup'] == 'True' and self.app.settings['ai_enable'] == 'False':
                msg = _('Welcome\n\n\
The new AI enhanced functions in QualCoder need some additional setup. \
Do you want to enable the AI and start the setup? \
You can also do this later by starting the AI Setup Wizard from the AI menu in the main window. \
Click "Yes" to start now.')
                msg_box = QtWidgets.QMessageBox(self)
                msg_box.setWindowTitle(_('AI Integration'))
                msg_box.setText(msg)
                msg_box.setStyleSheet(f"* {{font-size:{self.app.settings['fontsize']}pt}} ")
                msg_box.addButton(QtWidgets.QMessageBox.StandardButton.Yes)
                msg_box.addButton(QtWidgets.QMessageBox.StandardButton.No)
                msg_box.addButton(QtWidgets.QMessageBox.StandardButton.Help)
                reply = None
                while reply is None or reply == QtWidgets.QMessageBox.StandardButton.Help:
                    reply = msg_box.exec()
                    if reply == QtWidgets.QMessageBox.StandardButton.Help:
                        self.app.help_wiki("2.3.-AI-Setup")                
                if reply == QtWidgets.QMessageBox.StandardButton.Yes:
                    self.ai_setup_wizard()  # (will also init the llm)
            else:
                self.app.ai.init_llm(self)      
            self.app.settings['ai_first_startup'] = 'False'
            self.app.write_config_ini(self.app.settings, self.app.ai_models)
        except Exception as err:
            type_e = type(err)
            value = err
            tb_obj = err.__traceback__
            # log the exception and show error msg
            qt_exception_hook.exception_hook(type_e, value, tb_obj)

    def init_placeholder_tab_layouts(self):
        """Put the startup placeholder browsers into real tab layouts."""

        self.tab_placeholders = {
            self.ui.tab_manage: self.ui.textBrowser_manage,
            self.ui.tab_coding: self.ui.textBrowser_coding,
            self.ui.tab_reports: self.ui.textBrowser_reports,
        }
        for tab_widget, placeholder in self.tab_placeholders.items():
            layout = tab_widget.layout()
            if layout is None:
                layout = QtWidgets.QVBoxLayout(tab_widget)
                layout.setContentsMargins(9, 9, 9, 9)
            if layout.indexOf(placeholder) == -1:
                layout.addWidget(placeholder)
            placeholder.setOpenExternalLinks(False)
            placeholder.setOpenLinks(False)
            placeholder.anchorClicked.connect(self.handle_placeholder_link)
            placeholder.show()
        self.update_placeholder_tab_styles()

    @staticmethod
    def _object_name_aliases(object_name):
        """Return case-insensitive aliases for a menu or action objectName."""

        if not object_name:
            return set()
        aliases = {object_name.casefold()}
        for prefix in ("menu", "action"):
            if object_name.startswith(prefix) and len(object_name) > len(prefix):
                aliases.add(object_name[len(prefix):].casefold())
        return aliases

    def _matches_object_name(self, segment, obj):
        """Check whether a URI segment matches an object by name."""

        return segment.casefold() in self._object_name_aliases(obj.objectName())

    def _top_level_menus(self):
        """Return all top-level menus from the menubar."""

        return [action.menu() for action in self.ui.menubar.actions() if action.menu() is not None]

    def _resolve_placeholder_menu_link(self, url):
        """Resolve a qualcoder://menu/... link to a QMenu or QAction."""

        if url.host().casefold() != "menu":
            raise ValueError(_("Unsupported QualCoder link target: ") + url.host())
        path_segments = [segment for segment in url.path().split("/") if segment]
        if not path_segments:
            raise ValueError(_("Menu link has no target path."))

        current_menu = next(
            (menu for menu in self._top_level_menus() if self._matches_object_name(path_segments[0], menu)),
            None,
        )
        if current_menu is None:
            raise ValueError(_("Menu not found: ") + path_segments[0])

        menu_chain = [current_menu]
        for index, segment in enumerate(path_segments[1:], start=1):
            match = None
            for action in current_menu.actions():
                if action.isSeparator():
                    continue
                submenu = action.menu()
                if submenu is not None and self._matches_object_name(segment, submenu):
                    match = submenu
                    menu_chain.append(submenu)
                    break
                if self._matches_object_name(segment, action):
                    match = action
                    break
            if match is None:
                raise ValueError(_("Menu entry not found: ") + segment)
            if isinstance(match, QtWidgets.QMenu):
                current_menu = match
                continue
            if index != len(path_segments) - 1:
                raise ValueError(_("Action cannot contain subentries: ") + segment)
            return match, menu_chain
        return current_menu, menu_chain

    def _iter_actions_with_menu_chain(self, menu=None, menu_chain=None):
        """Yield actions together with the chain of menus containing them."""

        if menu is None:
            for top_menu in self._top_level_menus():
                yield from self._iter_actions_with_menu_chain(top_menu, [top_menu])
            return
        if menu_chain is None:
            menu_chain = [menu]
        for action in menu.actions():
            if action.isSeparator():
                continue
            yield action, list(menu_chain)
            submenu = action.menu()
            if submenu is not None:
                yield from self._iter_actions_with_menu_chain(submenu, menu_chain + [submenu])

    def _resolve_placeholder_action_link(self, url):
        """Resolve a qualcoder://action/... link to a QAction."""

        if url.host().casefold() != "action":
            raise ValueError(_("Unsupported QualCoder link target: ") + url.host())
        path_segments = [segment for segment in url.path().split("/") if segment]
        if not path_segments:
            raise ValueError(_("Action link has no target path."))
        if len(path_segments) == 1:
            matches = [
                (action, menu_chain)
                for action, menu_chain in self._iter_actions_with_menu_chain()
                if self._matches_object_name(path_segments[0], action)
            ]
            if not matches:
                raise ValueError(_("Action not found: ") + path_segments[0])
            if len(matches) > 1:
                raise ValueError(_("Action name is ambiguous: ") + path_segments[0])
            return matches[0]

        resolved, menu_chain = self._resolve_placeholder_menu_link(
            QtCore.QUrl(f"qualcoder://menu/{'/'.join(path_segments)}")
        )
        if isinstance(resolved, QtWidgets.QMenu):
            raise ValueError(_("Action link must end with a menu action."))
        return resolved, menu_chain

    def _popup_menu_chain(self, menu_chain, active_action=None):
        """Display a top-level menu and any nested submenu chain."""

        if not menu_chain:
            return
        top_menu = menu_chain[0]
        menu_bar_action = next(
            (action for action in self.ui.menubar.actions() if action.menu() == top_menu),
            None,
        )
        if menu_bar_action is not None:
            rect = self.ui.menubar.actionGeometry(menu_bar_action)
            popup_pos = self.ui.menubar.mapToGlobal(rect.bottomLeft())
        else:
            popup_pos = QtGui.QCursor.pos()
        top_menu.popup(popup_pos)
        if len(menu_chain) > 1:
            top_menu.setActiveAction(menu_chain[1].menuAction())
        elif active_action is not None:
            top_menu.setActiveAction(active_action)

        parent_menu = top_menu
        for submenu in menu_chain[1:]:
            QtWidgets.QApplication.processEvents()
            rect = parent_menu.actionGeometry(submenu.menuAction())
            submenu.popup(parent_menu.mapToGlobal(rect.topRight()))
            submenu_index = menu_chain.index(submenu)
            next_menu = menu_chain[submenu_index + 1] if submenu_index + 1 < len(menu_chain) else None
            if next_menu is not None:
                submenu.setActiveAction(next_menu.menuAction())
            elif active_action is not None:
                submenu.setActiveAction(active_action)
            parent_menu = submenu

    def _show_placeholder_link_error(self, url_text, details):
        """Show a visible error for an invalid placeholder link."""

        msg = _("Cannot open link: ") + url_text + "\n\n" + details
        logger.warning(msg)
        Message(self.app, _("Link error"), msg, "warning").exec()

    def _use_placeholder_menu_links_as_actions(self):
        """Return True when native menus cannot be shown reliably in the window."""

        return platform.system() == "Darwin" and self.ui.menubar.isNativeMenuBar()

    def handle_placeholder_link(self, url):
        """Open external links or dispatch custom qualcoder:// menu links."""

        url_text = url.toString()
        scheme = url.scheme().casefold()
        if scheme in ("http", "https"):
            webbrowser.open(url_text)
            return
        if scheme != "qualcoder":
            self._show_placeholder_link_error(url_text, _("Unsupported link scheme."))
            return
        try:
            host = url.host().casefold()
            if host == "help":
                page_path = url.path().lstrip("/")
                self.app.help_wiki(page_path)
                return
            if host == "menu":
                target, menu_chain = self._resolve_placeholder_menu_link(url)
                if self._use_placeholder_menu_links_as_actions():
                    if isinstance(target, QtWidgets.QMenu):
                        raise ValueError(_("This menu is in the macOS menu bar. Please use the menu bar at the top of the screen."))
                    if not target.isEnabled():
                        raise ValueError(_("Menu action is currently disabled."))
                    target.trigger()
                    return
                if isinstance(target, QtWidgets.QMenu):
                    self._popup_menu_chain(menu_chain)
                    return
                self._popup_menu_chain(menu_chain, active_action=target)
                return
            if host == "action":
                target, menu_chain = self._resolve_placeholder_action_link(url)
                if not target.isEnabled():
                    raise ValueError(_("Menu action is currently disabled."))
                target.trigger()
                return
            raise ValueError(_("Unsupported QualCoder link target: ") + url.host())
        except ValueError as err:
            self._show_placeholder_link_error(url_text, str(err))

    def update_placeholder_tab_styles(self):
        """Match placeholder browser colors and link styling to the application theme."""

        action_log_background = self.ui.textEdit.viewport().palette().color(
            QtGui.QPalette.ColorRole.Base
        ).name()
        text_color = self.ui.textEdit.viewport().palette().color(QtGui.QPalette.ColorRole.Text).name()
        browser_style = f"""
            QTextBrowser {{
                background-color: {action_log_background};
                border: none;
            }}
            QTextBrowser:focus {{
                background-color: {action_log_background};
                border: none;
            }}
        """
        for tab_widget, placeholder in self.tab_placeholders.items():
            placeholder.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
            placeholder.setFrameShadow(QtWidgets.QFrame.Shadow.Plain)
            placeholder.viewport().setStyleSheet(
                f"background-color: {action_log_background}; border: none;"
            )
            placeholder.setStyleSheet(browser_style)
            placeholder.document().setDefaultStyleSheet(
                f"a {{ color: {text_color}; }} "
                f"a:visited {{ color: {text_color}; }}"
            )
        self.refresh_placeholder_tab_content()

    def refresh_placeholder_tab_content(self):
        """Render placeholder tab Markdown with the current theme colors."""

        for tab_widget in self.tab_placeholders:
            self.refresh_placeholder_browser(tab_widget)

    def refresh_placeholder_browser(self, tab_widget):
        """Render one placeholder browser with the current theme colors."""

        placeholder = self.tab_placeholders.get(tab_widget)
        if placeholder is None:
            return
        highlight_color = self.app.highlight_color()
        text_color = self.ui.textEdit.viewport().palette().color(QtGui.QPalette.ColorRole.Text).name()
        doc_font_size = self.app.settings["docfontsize"]
        doc_font_family = self.app.settings.get("docfont", self.app.settings["font"])
        placeholder_map = {
            self.ui.tab_manage: (manage_tab_info, "mdi6.file-outline"),
            self.ui.tab_coding: (coding_tab_info, "mdi6.tag-text-outline"),
            self.ui.tab_reports: (reports_tab_info, "mdi6.format-list-group"),
        }
        markdown_text_func, heading_icon_name = placeholder_map[tab_widget]
        placeholder.setHtml(
            render_tab_info_markdown(
                markdown_text_func(),
                highlight_color,
                text_color,
                doc_font_size,
                doc_font_family,
                heading_icon_name=heading_icon_name,
                link_text_color=text_color,
            )
        )

    def clear_tab_widgets(self, tab_widget, show_placeholder=True):
        """Remove loaded tab content and optionally show the placeholder browser."""

        layout = tab_widget.layout()
        if layout is None:
            return
        placeholder = self.tab_placeholders.get(tab_widget)
        for i in reversed(range(layout.count())):
            widget = layout.itemAt(i).widget()
            if widget is None or widget == placeholder:
                continue
            widget.close()
            widget.setParent(None)
        if placeholder is not None:
            if layout.indexOf(placeholder) == -1:
                layout.addWidget(placeholder)
            if show_placeholder:
                # Re-render the placeholder when it is restored so project switches
                # and tab resets never leave a previously cleared browser blank.
                self.refresh_placeholder_browser(tab_widget)
            placeholder.setVisible(show_placeholder)
    
    def init_ui(self):
        """ Set up menu triggers """

        # Project menu
        self.ui.actionCreate_New_Project.triggered.connect(self.new_project)
        self.ui.actionCreate_New_Project.setShortcut('Ctrl+N')
        self.ui.actionOpen_Project.triggered.connect(self.open_project)
        self.ui.actionOpen_Project.setShortcut('Ctrl+O')
        self.fill_recent_projects_menu_actions()
        self.ui.actionProject_Memo.triggered.connect(self.project_memo)
        self.ui.actionProject_Memo.setShortcut('Ctrl+M')
        self.ui.actionClose_Project.triggered.connect(self.close_project)
        self.ui.actionClose_Project.setShortcut('Alt+X')
        self.ui.actionSettings.triggered.connect(self.change_settings)
        self.ui.actionSettings.setShortcut('Alt+S')
        self.ui.actionProject_summary.triggered.connect(self.project_summary_report)
        self.ui.actionProject_Exchange_Export.triggered.connect(self.refi_project_export)
        self.ui.actionREFI_Codebook_export.triggered.connect(self.refi_codebook_export)
        self.ui.actionREFI_Codebook_import.triggered.connect(self.refi_codebook_import)
        self.ui.actionREFI_QDA_Project_import.triggered.connect(self.refi_project_import)
        self.ui.actionRQDA_Project_import.triggered.connect(self.rqda_project_import)
        self.ui.actionTaguette_import.triggered.connect(self.taguette_project_import)
        self.ui.actionExport_codebook.triggered.connect(self.codebook)
        self.ui.actionExport_codebook_with_memos.triggered.connect(self.codebook_with_memos)
        self.ui.actionExit.triggered.connect(self.close)
        self.ui.actionExit.setShortcut('Ctrl+Q')
        self.ui.actionImport_plain_text_codes_list.triggered.connect(self.import_plain_text_codes)
        # Manage menu
        self.ui.actionManage_files.setShortcut('Alt+F')
        self.ui.actionManage_files.triggered.connect(self.manage_files)
        self.ui.actionManage_journals.triggered.connect(self.journals)
        self.ui.actionManage_journals.setShortcut('Alt+J')
        self.ui.actionManage_cases.triggered.connect(self.manage_cases)
        self.ui.actionManage_cases.setShortcut('Alt+C')
        self.ui.actionManage_attributes.triggered.connect(self.manage_attributes)
        self.ui.actionManage_attributes.setShortcut('Alt+A')
        self.ui.actionImport_survey_2.triggered.connect(self.import_survey)
        self.ui.actionImport_survey_2.setShortcut('Ctrl+I')
        self.ui.actionManage_bad_links_to_files.triggered.connect(self.manage_bad_file_links)
        self.ui.actionManage_references.setShortcut('Alt+R')
        self.ui.actionManage_references.triggered.connect(self.manage_references)
        # Coding menu
        self.ui.actionCodes.triggered.connect(self.text_coding)
        self.ui.actionCodes.setShortcut('Alt+T')
        self.ui.actionAI_assisted_coding.triggered.connect(self.ai_go_search)
        self.ui.actionCode_image.triggered.connect(self.image_coding)
        self.ui.actionCode_image.setShortcut('Alt+I')
        self.ui.actionCode_audio_video.triggered.connect(self.av_coding)
        self.ui.actionCode_audio_video.setShortcut('Alt+V')
        self.ui.actionCode_pdf.triggered.connect(self.pdf_coding)
        self.ui.actionColour_scheme.setShortcut('Alt+E')
        self.ui.actionColour_scheme.triggered.connect(self.code_color_scheme)
        self.ui.actionCode_organiser.triggered.connect(self.code_organiser)
        # Analysis menu
        self.ui.actionCoding_reports.setShortcut('Alt+K')
        self.ui.actionCoding_reports.triggered.connect(self.report_coding)
        self.ui.actionCode_co_occurrence.triggered.connect(self.co_occurence)
        self.ui.actionCode_relations.setShortcut('Alt+Q')
        self.ui.actionCode_relations.triggered.connect(self.report_code_relations)
        self.ui.actionCode_text_exact_matches.triggered.connect(self.report_exact_text_matches)
        self.ui.actionText_segments_by_codes.triggered.connect(self.text_segments_codes_table)
        self.ui.actionView_Graph.setShortcut('Alt+G')
        self.ui.actionView_Graph.triggered.connect(self.view_graph_original)
        self.ui.actionAI_topic_exploration.triggered.connect(self.ai_go_analysis)
        self.ui.actionAI_text_analysis.triggered.connect(self.ai_go_analysis)
        self.ui.actionAI_code_analysis.triggered.connect(self.ai_go_analysis)
        # Reports menu
        self.ui.actionCoding_comparison.setShortcut('Alt+L')
        self.ui.actionCoding_comparison.triggered.connect(self.report_coding_comparison)
        self.ui.actionCoding_comparison_by_file.setShortcut('Alt+M')
        self.ui.actionCoding_comparison_by_file.triggered.connect(self.report_compare_coders_by_file)
        self.ui.actionCode_comparison_table.triggered.connect(self.report_comparison_table)
        self.ui.actionCode_frequencies.setShortcut('Alt+N')
        self.ui.actionCode_frequencies.triggered.connect(self.report_code_frequencies)
        self.ui.actionFile_summary.setShortcut('Alt+O')
        self.ui.actionFile_summary.triggered.connect(self.report_file_summary)
        self.ui.actionCode_summary.setShortcut('Alt+P')
        self.ui.actionCode_summary.triggered.connect(self.report_code_summary)

        self.ui.actionCharts.setShortcut('Alt+U')
        self.ui.actionCharts.triggered.connect(self.view_charts)
        self.ui.actionSQL_statements.setShortcut('Alt+D')
        self.ui.actionSQL_statements.triggered.connect(self.report_sql)
        # AI menu
        self.ui.actionAI_Setup_wizard.triggered.connect(self.ai_setup_wizard)
        self.ui.actionAI_Configuration.triggered.connect(self.ai_settings)
        self.ui.actionAI_Rebuild_internal_memory.triggered.connect(self.ai_rebuild_memory)
        self.ui.actionAI_Edit_Project_Memo.triggered.connect(self.project_memo)
        self.ui.actionAI_Prompts.triggered.connect(self.ai_prompts)
        self.ui.actionAI_Agent.triggered.connect(self.ai_go_chat)
        self.ui.actionAI_Agent_Sidebar.setCheckable(True)
        self.ui.actionAI_Agent_Sidebar.toggled.connect(self.toggle_ai_chat_sidebar)
        self.ui.actionAI_Search_and_Coding.triggered.connect(self.ai_go_search)
        self.ui.actionCheck_project_AI_readiness.triggered.connect(self.ai_check_project_readiness)
        self.ui.tabWidget.currentChanged.connect(self.remember_last_non_ai_chat_tab)
        # Help menu
        self.ui.actionContents.setShortcut('Alt+H')
        self.ui.actionContents.triggered.connect(self.help)
        self.ui.actionAsk_the_AI_Agent.triggered.connect(self.ai_go_help_support)
        self.ui.actionAbout.setShortcut('Alt+Y')
        self.ui.actionAbout.triggered.connect(self.about)
        self.ui.actionSpecial_functions.setShortcut('Alt+Z')
        self.ui.actionSpecial_functions.triggered.connect(self.special_functions)
        self.ui.actionMenu_Key_Shortcuts.triggered.connect(self.display_menu_key_shortcuts)
        # Ensure the action_log always scrolls to the very bottom once new log entries are added:
        self.ui.textEdit.verticalScrollBar().rangeChanged.connect(self.action_log_scroll_bottom)
        self.ui.textEdit.setReadOnly(True)
        self.ui.splitter.setChildrenCollapsible(False)
        self.ui.splitter.setCollapsible(1, False)
        self.ui.sidebar.setMinimumWidth(0)
        self.ui.splitter.splitterMoved.connect(self.on_main_splitter_moved)
        self.settings_report()
        
        self.ui.tabWidget.setCurrentIndex(0)
        self.last_non_ai_chat_tab = self.ui.tab_action_log
        self.ai_chat()

        self.refresh_placeholder_tab_content()

        # Add tab widget icons
        try:
            self.ui.tabWidget.setTabIcon(0, qta.icon('mdi6.cog', color=self.app.highlight_color()))  # Action Log
            self.ui.tabWidget.setTabIcon(1, qta.icon('mdi6.file-outline', color=self.app.highlight_color()))  # Manage
            self.ui.tabWidget.setTabIcon(2, qta.icon('mdi6.tag-text-outline', color=self.app.highlight_color()))  # Coding
            self.ui.tabWidget.setTabIcon(3, qta.icon('mdi6.format-list-group', color=self.app.highlight_color()))  # Reports
            self.ui.tabWidget.setTabIcon(4, qta.icon('mdi6.message-processing-outline', color=self.app.highlight_color()))  # Ai Chat
        except Exception as e_:
            logger.log(e_)
        self._setup_ai_chat_tab_sidebar_button()
        self.update_ai_menu_options()
        
    def fill_recent_projects_menu_actions(self):
        """ Get the recent projects from the .qualcoder txt file.
        Add up to five recent projects to the menu. """

        self.recent_projects = self.app.read_previous_project_paths()
        if len(self.recent_projects) == 0:
            return
        # Removes the qtdesigner default action. Also clears the section when a project is closed
        # so that the options for recent projects can be updated
        self.ui.menuOpen_Recent_Project.clear()
        for i, r in enumerate(self.recent_projects):
            display_name = r
            if len(r.split("|")) == 2:
                display_name = r.split("|")[1]
            if i == 0:
                action0 = QtGui.QAction(display_name, self)
                self.ui.menuOpen_Recent_Project.addAction(action0)
                action0.triggered.connect(self.project0)
            if i == 1:
                action1 = QtGui.QAction(display_name, self)
                self.ui.menuOpen_Recent_Project.addAction(action1)
                action1.triggered.connect(self.project1)
            if i == 2:
                action2 = QtGui.QAction(display_name, self)
                self.ui.menuOpen_Recent_Project.addAction(action2)
                action2.triggered.connect(self.project2)
            if i == 3:
                action3 = QtGui.QAction(display_name, self)
                self.ui.menuOpen_Recent_Project.addAction(action3)
                action3.triggered.connect(self.project3)
            if i == 4:
                action4 = QtGui.QAction(display_name, self)
                self.ui.menuOpen_Recent_Project.addAction(action4)
                action4.triggered.connect(self.project4)
            if i == 5:
                action5 = QtGui.QAction(display_name, self)
                self.ui.menuOpen_Recent_Project.addAction(action5)
                action5.triggered.connect(self.project5)

    def project0(self):
        self.open_project(self.recent_projects[0])

    def project1(self):
        self.open_project(self.recent_projects[1])

    def project2(self):
        self.open_project(self.recent_projects[2])

    def project3(self):
        self.open_project(self.recent_projects[3])

    def project4(self):
        self.open_project(self.recent_projects[4])

    def project5(self):
        self.open_project(self.recent_projects[5])

    def hide_menu_options(self):
        """ No project opened, hide most menu options.
         Enable project import options.
         Called by init and by close_project. """

        # Project menu
        self.ui.actionClose_Project.setEnabled(False)
        self.ui.actionProject_Memo.setEnabled(False)
        self.ui.actionProject_Exchange_Export.setEnabled(False)
        self.ui.actionREFI_Codebook_export.setEnabled(False)
        self.ui.actionREFI_Codebook_import.setEnabled(False)
        self.ui.actionREFI_QDA_Project_import.setEnabled(True)
        self.ui.actionRQDA_Project_import.setEnabled(True)
        self.ui.actionTaguette_import.setEnabled(True)
        self.ui.actionExport_codebook.setEnabled(False)
        self.ui.actionImport_plain_text_codes_list.setEnabled(False)
        # Manage menu
        self.ui.actionManage_files.setEnabled(False)
        self.ui.actionManage_journals.setEnabled(False)
        self.ui.actionManage_cases.setEnabled(False)
        self.ui.actionManage_attributes.setEnabled(False)
        self.ui.actionImport_survey_2.setEnabled(False)
        self.ui.actionManage_bad_links_to_files.setEnabled(False)
        self.ui.actionManage_references.setEnabled(False)
        # Coding menu
        self.ui.actionCodes.setEnabled(False)
        self.ui.actionCode_image.setEnabled(False)
        self.ui.actionCode_audio_video.setEnabled(False)
        self.ui.actionCode_pdf.setEnabled(False)
        self.ui.actionColour_scheme.setEnabled(False)
        self.ui.actionCode_organiser.setEnabled(False)
        # Analysis menu
        self.ui.actionCoding_reports.setEnabled(False)
        self.ui.actionCode_co_occurrence.setEnabled(False)
        self.ui.actionCode_relations.setEnabled(False)
        self.ui.actionText_segments_by_codes.setEnabled(False)
        self.ui.actionView_Graph.setEnabled(False)
        # Reports menu
        self.ui.actionCoding_comparison.setEnabled(False)
        self.ui.actionCoding_comparison_by_file.setEnabled(False)
        self.ui.actionCode_frequencies.setEnabled(False)
        self.ui.actionCode_text_exact_matches.setEnabled(False)
        self.ui.actionCode_comparison_table.setEnabled(False)
        self.ui.actionSQL_statements.setEnabled(False)
        self.ui.actionFile_summary.setEnabled(False)
        self.ui.actionCode_summary.setEnabled(False)
        self.ui.actionCategories.setEnabled(False)
        self.ui.actionCharts.setEnabled(False)
        # Help menu
        self.ui.actionSpecial_functions.setEnabled(False)
        self.update_ai_menu_options()

    def show_menu_options(self):
        """ Project opened, show most menu options.
         Disable project import options. """

        # Project menu
        self.ui.actionClose_Project.setEnabled(True)
        self.ui.actionProject_Memo.setEnabled(True)
        self.ui.actionProject_Exchange_Export.setEnabled(True)
        self.ui.actionREFI_Codebook_export.setEnabled(True)
        self.ui.actionREFI_Codebook_import.setEnabled(True)
        self.ui.actionREFI_QDA_Project_import.setEnabled(True)
        self.ui.actionRQDA_Project_import.setEnabled(True)
        self.ui.actionExport_codebook.setEnabled(True)
        self.ui.actionImport_plain_text_codes_list.setEnabled(True)
        # Manage menu
        self.ui.actionManage_files.setEnabled(True)
        self.ui.actionManage_journals.setEnabled(True)
        self.ui.actionManage_cases.setEnabled(True)
        self.ui.actionManage_attributes.setEnabled(True)
        self.ui.actionImport_survey_2.setEnabled(True)
        self.ui.actionManage_references.setEnabled(True)
        # Coding menu
        self.ui.actionCodes.setEnabled(True)
        self.ui.actionCode_image.setEnabled(True)
        self.ui.actionCode_audio_video.setEnabled(True)
        self.ui.actionCode_pdf.setEnabled(True)
        self.ui.actionColour_scheme.setEnabled(True)
        self.ui.actionCode_organiser.setEnabled(True)
        # Analysis menu
        self.ui.actionCoding_reports.setEnabled(True)
        self.ui.actionCode_co_occurrence.setEnabled(True)
        self.ui.actionCode_relations.setEnabled(True)
        self.ui.actionCode_text_exact_matches.setEnabled(True)
        self.ui.actionText_segments_by_codes.setEnabled(True)
        self.ui.actionView_Graph.setEnabled(True)
        # Reports menu
        self.ui.actionCoding_comparison.setEnabled(True)
        self.ui.actionCoding_comparison_by_file.setEnabled(True)
        self.ui.actionCode_comparison_table.setEnabled(True)
        self.ui.actionCode_frequencies.setEnabled(True)
        self.ui.actionSQL_statements.setEnabled(True)
        self.ui.actionFile_summary.setEnabled(True)
        self.ui.actionCode_summary.setEnabled(True)
        self.ui.actionCategories.setEnabled(True)
        self.ui.actionCharts.setEnabled(True)
        # Help menu
        self.ui.actionSpecial_functions.setEnabled(True)
        self.update_ai_menu_options()

    def update_ai_menu_options(self):
        """Refresh all AI-related menu and widget enablement from current app state."""

        project_open = str(getattr(self.app, 'project_name', '')).strip() != ''
        ai_enabled = self.app.settings.get('ai_enable', 'False') == 'True'
        ai_actions_enabled = project_open and ai_enabled

        self.ui.actionAI_Edit_Project_Memo.setEnabled(project_open)
        self.ui.actionAI_Rebuild_internal_memory.setEnabled(ai_actions_enabled)
        self.ui.actionAI_Agent.setEnabled(ai_actions_enabled)
        self.ui.actionAI_Agent_Sidebar.setEnabled(ai_actions_enabled)
        self.ui.actionAI_Search_and_Coding.setEnabled(ai_actions_enabled)
        self.ui.actionAI_assisted_coding.setEnabled(ai_actions_enabled)
        self.ui.actionAI_topic_exploration.setEnabled(ai_actions_enabled)
        self.ui.actionAI_text_analysis.setEnabled(ai_actions_enabled)
        self.ui.actionAI_code_analysis.setEnabled(ai_actions_enabled)
        self.ui.actionCheck_project_AI_readiness.setEnabled(ai_actions_enabled)
        self.ui.actionAsk_the_AI_Agent.setEnabled(ai_actions_enabled)

        if self.ai_chat_tab_sidebar_button is not None:
            self.ai_chat_tab_sidebar_button.setEnabled(ai_actions_enabled)

        for widget in self.findChildren(QtWidgets.QWidget):
            updater = getattr(widget, "update_ai_menu_options", None)
            if callable(updater):
                updater()

    def keyPressEvent(self, event):
        """ Used to open top level menus. """

        key = event.key()
        mods = QtWidgets.QApplication.keyboardModifiers()
        if mods & QtCore.Qt.KeyboardModifier.AltModifier and key == QtCore.Qt.Key.Key_1:
            self.ui.menuProject.popup(QtGui.QCursor.pos())
        if mods & QtCore.Qt.KeyboardModifier.AltModifier and key == QtCore.Qt.Key.Key_2:
            self.ui.menuFiles_and_Cases.popup(QtGui.QCursor.pos())
        if mods & QtCore.Qt.KeyboardModifier.AltModifier and key == QtCore.Qt.Key.Key_3:
            self.ui.menuCoding.popup(QtGui.QCursor.pos())
        if mods & QtCore.Qt.KeyboardModifier.AltModifier and key == QtCore.Qt.Key.Key_4:
            self.ui.menuReports.popup(QtGui.QCursor.pos())
        if mods & QtCore.Qt.KeyboardModifier.AltModifier and key == QtCore.Qt.Key.Key_5:
            self.ui.menuHelp.popup(QtGui.QCursor.pos())

    def settings_report(self, swith_to_action_log: bool = True):
        """ Display general settings and project summary """

        self.ui.textEdit.append("<h1>" + _("Settings") + "</h1>")
        msg = "<p>" + _("Coder") + f": {self.app.settings['codername']}<br />"
        msg += _("Font") + f": {self.app.settings['font']} {self.app.settings['fontsize']} | "
        msg += _("Tree font size") + f": {self.app.settings['treefontsize']}<br />"
        msg += _("Working directory") + f": {self.app.settings['directory']}<br />"
        msg += _("Language") + f": {self.app.settings['language']} | "
        msg += _("Show IDs") + f": {self.app.settings['showids']}<br />"
        msg += _("Timestamp format") + f": {self.app.settings['timestampformat']} | "
        msg += _("Speaker name format") + f": {self.app.settings['speakernameformat']}<br />"
        msg += _("Report text context characters: ") + f"{self.app.settings['report_text_context_characters']}<br /> "
        msg += _("Style") + f": {self.app.settings['stylesheet']}<br />"
        msg += _("Backup on open") + f": {self.app.settings['backup_on_open']} | "
        msg += _("Backup AV files") + f": {self.app.settings['backup_av_files']}<br />"
        if self.app.settings['ai_enable'] == 'True':
            msg += _("AI integration is enabled")
        else:
            msg += _("AI integration is disabled")
        ai_permissions = self.app.settings.get('ai_permissions', 1)
        ai_permissions_labels = {
            0: 'Read-only',
            1: 'Sandboxed',
            2: 'Full access'
        }
        msg += " | " + _("AI permissions") + f": {ai_permissions_labels.get(ai_permissions, ai_permissions)}</p>"
        self.ui.textEdit.append(msg)
        if platform.system() == "Windows":
            self.ui.textEdit.append("<p>" + _("Folder paths / represents \\") + "</p>")
        self.ui.textEdit.append("<p></p>")
        self.ui.textEdit.textCursor().movePosition(QtGui.QTextCursor.MoveOperation.End)
        if swith_to_action_log:
            self.ui.tabWidget.setCurrentWidget(self.ui.tab_action_log)

    def text_segments_codes_table(self):
        """ Show table of text segments (rows) by codes (columns). """

        self.ui.textBrowser_reports.hide()
        ui = DialogCodesBySegments(self.app, self.ui.textEdit)
        self.tab_layout_helper(self.ui.tab_reports, ui)

    def report_sql(self):
        """ Run SQL statements on database. """

        self.ui.textBrowser_reports.hide()
        ui = DialogSQL(self.app, self.ui.textEdit)
        self.tab_layout_helper(self.ui.tab_reports, ui)

    def report_coding_comparison(self):
        """ Compare two or more coders across all text files using Cohens Kappa. """

        self.ui.textBrowser_reports.hide()
        ui = DialogReportCoderComparisons(self.app, self.ui.textEdit)
        self.tab_layout_helper(self.ui.tab_reports, ui)

    def report_comparison_table(self):
        self.ui.textBrowser_reports.hide()
        ui = DialogReportComparisonTable(self.app, self.ui.textEdit)
        self.tab_layout_helper(self.ui.tab_reports, ui)

    def report_compare_coders_by_file(self):
        """ Compare two coders selection by file - text, A/V or image. """

        self.ui.textBrowser_reports.hide()
        ui = DialogCompareCoderByFile(self.app, self.ui.textEdit)
        self.tab_layout_helper(self.ui.tab_reports, ui)

    def report_code_frequencies(self):
        """ Show code frequencies overall and by coder. """

        self.ui.textBrowser_reports.hide()
        ui = DialogReportCodeFrequencies(self.app, self.ui.textEdit)
        self.tab_layout_helper(self.ui.tab_reports, ui)

    def report_code_relations(self):
        """ Show code relations in text files. """

        self.ui.textBrowser_reports.hide()
        ui = DialogReportRelations(self.app, self.ui.textEdit)
        self.tab_layout_helper(self.ui.tab_reports, ui)

    def co_occurence(self):
        """ Show overlapping codes in text files. """

        self.ui.textBrowser_reports.hide()
        ui = DialogReportCooccurrence(self.app, self.ui.textEdit)
        self.tab_layout_helper(self.ui.tab_reports, ui)

    def report_exact_text_matches(self):
        """ Show exact text coding matches in text files. """

        self.ui.textBrowser_reports.hide()
        ui = DialogReportExactTextMatches(self.app, self.ui.textEdit)
        self.tab_layout_helper(self.ui.tab_reports, ui)

    def report_coding(self):
        """ Report on coding and categories. """

        self.ui.textBrowser_reports.hide()
        ui = DialogReportCodes(self.app, self.ui.textEdit, self.ui.tab_coding)
        self.tab_layout_helper(self.ui.tab_reports, ui)

    def report_file_summary(self):
        """ Report on file details. """

        self.ui.textBrowser_reports.hide()
        ui = DialogReportFileSummary(self.app, self.ui.textEdit)
        self.tab_layout_helper(self.ui.tab_reports, ui)

    def report_code_summary(self):
        """ Report on code details. """

        self.ui.textBrowser_reports.hide()
        ui = DialogReportCodeSummary(self.app, self.ui.textEdit)
        self.tab_layout_helper(self.ui.tab_reports, ui)

    def view_graph_original(self):
        """ Show list or acyclic graph of codes and categories. """

        self.ui.textBrowser_reports.hide()
        ui = ViewGraph(self.app)
        ui.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.tab_layout_helper(self.ui.tab_reports, ui)

    def view_charts(self):
        """ Show charts of codes and categories. """

        self.ui.textBrowser_reports.hide()
        ui = ViewCharts(self.app)
        ui.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.tab_layout_helper(self.ui.tab_reports, ui)

    def help(self):
        """ Display manual in browser. """

        self.app.help_wiki("")

    def display_menu_key_shortcuts(self):
        self.ui.textEdit.append(menu_shortcuts_display)
        self.ui.textEdit.append(coding_shortcuts_display)
        self.ui.tabWidget.setCurrentWidget(self.ui.tab_action_log)
        
    def action_log_scroll_bottom(self):
        """Scrolls the action log to the very bottom, malking new entries visible."""
        self.ui.textEdit.verticalScrollBar().setValue(self.ui.textEdit.verticalScrollBar().maximum())

    def about(self):
        """ About dialog. """

        ui = DialogInformation(self.app, "About", "")
        ui.exec()

    def special_functions(self):
        """ User requested special functions dialog. """

        ui = DialogSpecialFunctions(self.app, self.ui.textEdit, self.ui.tab_coding)
        ui.exec()
        if ui.projects_merged:
            self.tab_layout_helper(self.ui.tab_manage, None)
            self.tab_layout_helper(self.ui.tab_coding, None)
            self.tab_layout_helper(self.ui.tab_reports, None)
            self.project_summary_report()

    def manage_attributes(self):
        """ Create, edit, delete, rename attributes. """

        self.ui.textBrowser_manage.hide()
        ui = DialogManageAttributes(self.app, self.ui.textEdit)
        self.tab_layout_helper(self.ui.tab_manage, ui)

    def manage_references(self):
        """ Manage references. Import references. Edit references.
        Link/unlink references to files. """

        ui = DialogReferenceManager(self.app, self.ui.textEdit)
        self.tab_layout_helper(self.ui.tab_manage, ui)

    def import_plain_text_codes(self):
        """ Import a list of plain text codes codebook.
        The codebook is a plain text file or csv file.
        In plain text file, Tab separates the codename from the code description.
        The >> symbol is used to assign code to category:  code>>category
        """

        ImportPlainTextCodes(self.app, self.ui.textEdit)

    def import_survey(self):
        """ Import survey flat sheet: csv file or xlsx.
        Create cases and assign attributes to cases.
        Identify qualitative questions and assign these data to the source table for
        coding and review. Modal dialog. """

        self.ui.textBrowser_manage.hide()
        ui = DialogImportSurvey(self.app, self.ui.textEdit)
        self.tab_layout_helper(self.ui.tab_manage, ui)

    def manage_cases(self):
        """ Create, edit, delete, rename cases, add cases to files or parts of
        files, add memos to cases. """

        self.ui.textBrowser_manage.hide()
        ui = DialogCases(self.app, self.ui.textEdit)
        self.tab_layout_helper(self.ui.tab_manage, ui)

    def manage_files(self):
        """ Create text files or import files from odt, docx, html and
        plain text. Rename, delete and add memos to files.
        """

        self.ui.textBrowser_manage.hide()
        ui = DialogManageFiles(self.app, self.ui.textEdit, self.ui.tab_coding, self.ui.tab_reports, self)
        self.tab_layout_helper(self.ui.tab_manage, ui)

    def manage_bad_file_links(self):
        """ Fix any bad links to files.
        File names must match but paths can be different. """

        self.ui.textBrowser_manage.hide()
        ui = DialogManageLinks(self.app, self.ui.textEdit, self.ui.tab_coding)
        self.tab_layout_helper(self.ui.tab_manage, ui)
        bad_links = self.app.check_bad_file_links()
        if not bad_links:
            self.ui.actionManage_bad_links_to_files.setEnabled(False)

    def journals(self):
        """ Create and edit journals.
        From version 3.4 in a non-modal window. """

        ui = DialogJournals(self.app, self.ui.textEdit)
        ui.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.journal_display = ui
        ui.show()

    def text_coding(self, task: str = 'documents', doc_id: Optional[int] = None,
                    doc_sel_start: int = 0, doc_sel_end: int = 0,
                    doc_ids: Optional[list[int]] = None) -> None:
        """Show text coding, reusing the open dialog to preserve its context.

        Args:
            task: "documents": The default, shows the tab with the text documents
                  "ai_search": Shows the tab "AI Search"
            doc_id: If not None and task = "documents", this document will be loaded in the coding window
            doc_sel_start: The character-position of the beginning of the selection in the coding window
            doc_sel_end: The end of the selection
            doc_ids: Optional list of file ids; with task = "mark_speakers" they become
                the preselected files in the Mark speakers dialog (multi-selection from
                Manage files).
        """

        files = self.app.get_text_filenames()
        # Central redirection: if the referred document is a PDF, open the PDF coding
        # view. Covers all callers at once: mark speakers from Manage files, AI chat
        # internal references and qualcoder:// links (PDFs no longer load in code_text).
        if doc_id is not None:
            cur = self.app.conn.cursor()
            cur.execute("select mediapath from source where id=?", [int(doc_id)])
            res_mp = cur.fetchone()
            if res_mp is not None and res_mp[0] is not None and res_mp[0].lower().endswith(".pdf"):
                self.pdf_coding(task=task, doc_id=doc_id,
                                doc_sel_start=doc_sel_start, doc_sel_end=doc_sel_end)
                return
        if len(files) > 0:
            self.ui.textBrowser_coding.hide()
            ui = None
            contents = self.ui.tab_coding.layout()
            if contents is not None:
                for i in range(contents.count()):
                    widget = contents.itemAt(i).widget()
                    if not isinstance(widget, DialogCodeText):
                        continue
                    try:
                        widget.objectName()  # Detect a deleted C++ object.
                    except RuntimeError:
                        continue
                    ui = widget
                    break
            if ui is None:
                ui = DialogCodeText(self.app, self.ui.textEdit, self.ui.tab_reports)
                ui.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
                self.tab_layout_helper(self.ui.tab_coding, ui)
            else:
                self.ui.tabWidget.setCurrentWidget(self.ui.tab_coding)
            if task == 'documents':
                ui.ui.tabWidget.setCurrentWidget(ui.ui.tab_docs)
                if doc_id is not None:
                    ui.open_doc_selection(doc_id, doc_sel_start, doc_sel_end)
            elif task == 'ai_search':
                ui.ui.tabWidget.setCurrentWidget(ui.ui.tab_ai)
            elif task == 'mark_speakers':
                ui.ui.tabWidget.setCurrentWidget(ui.ui.tab_docs)
                if doc_id is not None:
                    ui.open_doc_selection(doc_id, doc_sel_start, doc_sel_end)
                    ui.mark_speakers(preselected_ids=doc_ids)                               
        else:
            msg = _("This project contains no text files.")
            Message(self.app, _('No text files'), msg).exec()

    def pdf_coding(self, task='documents', doc_id=None, doc_sel_start=0, doc_sel_end=0):
        """ Create edit and delete codes. Apply and remove codes  to the pdf
        text in imported pdf files.
        Signature equivalent to text_coding, to receive its redirections when the
        referred document is a PDF (mark speakers, AI chat references,
        qualcoder:// links).
        Args:
            task: "documents": the default. "mark_speakers": opens the Mark Speakers
                  dialog for doc_id after loading it.
            doc_id: If not None, this document will be loaded in the pdf coding window
            doc_sel_start: The character-position of the beginning of the selection
            doc_sel_end: The end of the selection
        """

        files = self.app.get_pdf_filenames()
        if len(files) > 0:
            existing = None
            contents = self.ui.tab_coding.layout()
            if contents is not None:
                for i in range(contents.count()):
                    widget = contents.itemAt(i).widget()
                    if isinstance(widget, DialogCodePdf):
                        try:
                            widget.ui.treeWidget.objectName()  # Detects a deleted C++ object.
                        except RuntimeError:
                            continue
                        existing = widget
                        break
            if existing is not None:
                self.ui.tabWidget.setCurrentWidget(self.ui.tab_coding)
                if doc_id is not None:
                    existing.open_doc_selection(doc_id, doc_sel_start, doc_sel_end)
                    if task == 'mark_speakers':
                        existing.mark_speakers()
                return
            self.ui.textBrowser_coding.hide()
            ui = DialogCodePdf(self.app, self.ui.textEdit, self.ui.tab_reports)
            ui.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
            self.tab_layout_helper(self.ui.tab_coding, ui)
            if doc_id is not None:
                ui.open_doc_selection(doc_id, doc_sel_start, doc_sel_end)
                if task == 'mark_speakers':
                    # DialogSpeakers works on the DB; it only requires file_ loaded.
                    ui.mark_speakers()
        else:
            msg = _("This project contains no pdf files.")
            Message(self.app, _('No pdf files'), msg).exec()

    def image_coding(self):
        """ Create edit and delete codes. Apply and remove codes to the image (or regions)
        """

        image_files = self.app.get_image_filenames()
        pdf_files = self.app.get_pdf_filenames()

        if len(image_files) + len(pdf_files) > 0:
            self.ui.textBrowser_coding.hide()
            ui = DialogCodeImage(self.app, self.ui.textEdit, self.ui.tab_reports)
            ui.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
            self.tab_layout_helper(self.ui.tab_coding, ui)
        else:
            msg = _("This project contains no image files.")
            Message(self.app, _('No image files'), msg).exec()

    def av_coding(self):
        """ Create edit and delete codes. Apply and remove codes to segments of the
        audio or video file. Added try block in case VLC bindings do not work. """

        files = self.app.get_av_filenames()
        if len(files) == 0:
            msg = _("This project contains no audio/video files.")
            Message(self.app, _('No a/v files'), msg).exec()
            return
        if not vlc and self.app.settings.get('av_player', 'vlc') != 'qt':
            # Without python-vlc the Qt Multimedia backend still works: switch to
            # it instead of blocking A/V coding.
            self.app.settings['av_player'] = 'qt'
            self.app.write_config_ini(self.app.settings, self.app.ai_models)
        self.ui.textBrowser_coding.hide()
        try:
            ui = DialogCodeAV(self.app, self.ui.textEdit, self.ui.tab_reports)
            ui.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
            self.tab_layout_helper(self.ui.tab_coding, ui)
        except Exception as err:
            logger.debug(str(err))
            Message(self.app, _("A/V Coding"), str(err), "warning").exec()

    def code_color_scheme(self):
        """ Edit code color scheme. """

        ui = DialogCodeColorScheme(self.app, self.ui.textEdit)
        ui.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.tab_layout_helper(self.ui.tab_coding, ui)

    def code_organiser(self):
        """ Organise codes structure. """

        ui = CodeOrganiser(self.app, self.ui.textEdit)
        ui.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.tab_layout_helper(self.ui.tab_reports, None)
        self.tab_layout_helper(self.ui.tab_coding, ui)

    def ai_chat(self):
        """Initialize AI chat and place it in tab or sidebar based on settings."""

        self.ai_chat_window = DialogAIChat(self.app, self.ui.textEdit, self)
        sidebar_mode = self.app.settings.get('ai_chat_sidebar', 'False') == 'True'
        self.set_ai_chat_sidebar_mode(sidebar_mode, persist=False)

    def _setup_ai_chat_tab_sidebar_button(self):
        """Add a small button in the AI chat tab to move the chat into sidebar view."""

        tab_index = self.ui.tabWidget.indexOf(self.ui.tab_ai_agent)
        if tab_index < 0:
            return
        tab_bar = self.ui.tabWidget.tabBar()
        tab_label = QtWidgets.QWidget(tab_bar)
        tab_label.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        tab_label.setStyleSheet("QWidget {background-color: transparent; border: none;}")
        tab_label_layout = QtWidgets.QHBoxLayout(tab_label)
        tab_label_layout.setContentsMargins(0, 0, 0, 0)
        tab_label_layout.setSpacing(4)
        icon_label = QtWidgets.QLabel(tab_label)
        icon_label.setStyleSheet("background-color: transparent; border: none;")
        icon = tab_bar.tabIcon(tab_index)
        if not icon.isNull():
            icon_label.setPixmap(icon.pixmap(16, 16))
            tab_label_layout.addWidget(icon_label)
        text_label = QtWidgets.QLabel(_('AI Agent'), tab_label)
        text_label.setStyleSheet("background-color: transparent; border: none;")
        tab_label_layout.addWidget(text_label)
        tab_label_layout.addStretch()
        tab_bar.setTabText(tab_index, "")
        tab_bar.setTabIcon(tab_index, QtGui.QIcon())
        tab_bar.setTabToolTip(tab_index, _('AI Agent'))
        tab_bar.setTabButton(
            tab_index, QtWidgets.QTabBar.ButtonPosition.LeftSide, tab_label
        )
        self.ai_chat_tab_label = tab_label
        button = QtWidgets.QToolButton(tab_bar)
        button.setAutoRaise(True)
        button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        button.setToolTip(_('Move AI Agent to sidebar view'))
        button.setFixedSize(16, 16)
        button.setStyleSheet(
            "QToolButton {background-color: transparent; border: none; padding: 0px;}"
            "QToolButton:hover {background-color: transparent; border: 1px solid #8a8a8a;}"
            "QToolButton:pressed {background-color: transparent; border: 1px solid #707070;}"
        )
        icon_color = tab_bar.tabTextColor(tab_index)
        if not icon_color.isValid():
            icon_color = tab_bar.palette().color(QtGui.QPalette.ColorRole.WindowText)
        try:
            button.setIcon(qta.icon('mdi6.arrow-right-bold-outline', color=icon_color))
            button.setIconSize(QtCore.QSize(12, 12))
        except Exception:
            button.setText(">")
        button.clicked.connect(self.open_ai_chat_sidebar_from_tab_button)

        self.ai_chat_tab_sidebar_button = button
        tab_bar.setTabButton(
            tab_index, QtWidgets.QTabBar.ButtonPosition.RightSide, button
        )
        self._sync_ai_chat_tab_widget_visibility()

    def _sync_ai_chat_tab_widget_visibility(self):
        """Keep custom AI tab widgets hidden when the AI tab is hidden."""

        tab_visible = not bool(self.ai_chat_sidebar_mode)
        if self.ai_chat_tab_label is not None:
            self.ai_chat_tab_label.setVisible(tab_visible)
        if self.ai_chat_tab_sidebar_button is not None:
            self.ai_chat_tab_sidebar_button.setVisible(tab_visible)

    def open_ai_chat_sidebar_from_tab_button(self):
        """Switch AI chat to sidebar mode from the tab button."""

        if self.app.settings['ai_enable'] != 'True':
            msg = _('Please enable the AI first and set it up in Settings.')
            Message(self.app, _('AI Agent'), msg).exec()
            return
        self.ui.actionAI_Agent_Sidebar.setChecked(True)

    def _ensure_widget_layout(self, widget):
        """Ensure a widget has a layout so child widgets can be hosted in it."""

        layout = widget.layout()
        if layout is None:
            layout = QtWidgets.QVBoxLayout()
            layout.setContentsMargins(0, 0, 0, 0)
            widget.setLayout(layout)
        return layout

    def _ai_chat_sidebar_host_widget(self):
        """Return the widget that should host AI chat in sidebar mode."""

        return self.ui.sidebar_frame

    def _move_ai_chat_to_host(self, host_widget):
        """Reparent the AI chat widget without closing or recreating it."""

        if self.ai_chat_window is None:
            return
        current_parent = self.ai_chat_window.parentWidget()
        if current_parent is not None:
            current_layout = current_parent.layout()
            if current_layout is not None:
                current_layout.removeWidget(self.ai_chat_window)
        target_layout = self._ensure_widget_layout(host_widget)
        if target_layout.indexOf(self.ai_chat_window) == -1:
            target_layout.addWidget(self.ai_chat_window)
        self.ai_chat_window.setParent(host_widget)
        self.ai_chat_window.show()

    def _get_saved_ai_sidebar_width(self, fallback_total=1000):
        """Return configured sidebar width without imposing artificial minima."""

        try:
            width = int(self.app.settings.get('ai_chat_sidebar_width', 320))
        except (TypeError, ValueError):
            width = 320
        total = max(2, int(fallback_total))
        return max(1, min(width, total - 1))

    def _remember_ai_sidebar_width(self):
        """Read current splitter sidebar width and keep it in settings (in-memory)."""

        if self.ui.sidebar.isVisible():
            sizes = self.ui.splitter.sizes()
            if len(sizes) >= 2 and sizes[1] > 0:
                self.app.settings['ai_chat_sidebar_width'] = int(sizes[1])

    def persist_ai_sidebar_splitter_setting(self):
        """Write the AI sidebar splitter width to config.ini after drag operations settle."""

        try:
            self.app.write_config_ini(self.app.settings, self.app.ai_models)
        except Exception as e_:
            logger.debug(f"Could not persist ai sidebar splitter setting: {e_}")

    def _apply_ai_sidebar_splitter_sizes(self):
        """Apply main/sidebar splitter sizes from the stored sidebar width."""

        sizes = self.ui.splitter.sizes()
        total = sum(sizes) if sum(sizes) > 0 else 1000
        sidebar_width = self._get_saved_ai_sidebar_width(fallback_total=total)
        main_width = max(1, total - sidebar_width)
        self.ai_sidebar_splitter_is_restoring = True
        try:
            with QtCore.QSignalBlocker(self.ui.splitter):
                self.ui.splitter.setSizes([main_width, sidebar_width])
        finally:
            self.ai_sidebar_splitter_is_restoring = False

    def _sync_ai_chat_sidebar_action(self):
        """Keep the AI sidebar menu action aligned with the active sidebar mode."""

        with QtCore.QSignalBlocker(self.ui.actionAI_Agent_Sidebar):
            self.ui.actionAI_Agent_Sidebar.setChecked(bool(self.ai_chat_sidebar_mode))

    def _restore_ai_splitters_after_show(self):
        """Re-apply saved splitter positions once window geometry is finalized."""

        if self.ai_chat_window is not None:
            self.ai_chat_window.schedule_ai_output_splitter_restore()
        if self.ai_chat_sidebar_mode:
            self._apply_ai_sidebar_splitter_sizes()
            QtCore.QTimer.singleShot(30, self._apply_ai_sidebar_splitter_sizes)

    def remember_last_non_ai_chat_tab(self, index):
        """Store the most recent visible main tab other than AI Agent."""

        widget = self.ui.tabWidget.widget(index)
        if widget == self.ui.tab_ai_agent and self.ai_chat_window is not None:
            self.ai_chat_window.schedule_ai_output_splitter_restore()
            return
        if widget is None or widget == self.ui.tab_ai_agent:
            return
        if not self.ui.tabWidget.isTabVisible(index):
            return
        self.last_non_ai_chat_tab = widget

    def get_tab_after_ai_chat_sidebar_switch(self):
        """Choose which main tab to show when AI chat moves into the sidebar."""

        current_widget = self.ui.tabWidget.currentWidget()
        current_index = self.ui.tabWidget.indexOf(current_widget)
        if (
            current_widget is not None
            and current_widget != self.ui.tab_ai_agent
            and current_index >= 0
            and self.ui.tabWidget.isTabVisible(current_index)
        ):
            return current_widget
        if self.last_non_ai_chat_tab is not None:
            return self.last_non_ai_chat_tab
        return self.ui.tab_action_log

    def set_ai_chat_sidebar_mode(self, enabled, persist=True, target_tab=None):
        """Switch AI chat between main tab view and sidebar view."""

        if self.ai_chat_window is None:
            self._sync_ai_chat_sidebar_action()
            return
        sidebar_target_tab = None
        if bool(enabled):
            sidebar_target_tab = target_tab if target_tab is not None else self.get_tab_after_ai_chat_sidebar_switch()
        ai_output_anchor = self.ai_chat_window.capture_ai_output_top_anchor()

        def restore_ai_output_anchor():
            if self.ai_chat_window is not None:
                self.ai_chat_window.restore_ai_output_top_anchor(ai_output_anchor)

        if self.ai_chat_sidebar_mode and not bool(enabled):
            self._remember_ai_sidebar_width()
        enabled = bool(enabled)
        self.ai_chat_sidebar_mode = enabled

        if enabled:
            self._move_ai_chat_to_host(self._ai_chat_sidebar_host_widget())
        else:
            self._move_ai_chat_to_host(self.ui.tab_ai_agent)

        self.ai_chat_window.set_sidebar_mode(enabled)
        ai_tab_index = self.ui.tabWidget.indexOf(self.ui.tab_ai_agent)
        self.ui.tabWidget.setTabVisible(ai_tab_index, not enabled)
        self._sync_ai_chat_tab_widget_visibility()
        self.ui.sidebar.setVisible(enabled)

        if enabled:
            self.ui.sidebar.setMinimumWidth(0)
            self.ai_chat_window.setMinimumWidth(0)
            self.ui.tabWidget.setCurrentWidget(sidebar_target_tab)
            self._apply_ai_sidebar_splitter_sizes()
            QtCore.QTimer.singleShot(0, self._apply_ai_sidebar_splitter_sizes)
            QtCore.QTimer.singleShot(30, self._apply_ai_sidebar_splitter_sizes)
        else:
            sizes = self.ui.splitter.sizes()
            total = sum(sizes) if sum(sizes) > 0 else 1000
            self.ui.splitter.setSizes([total, 0])
        restore_ai_output_anchor()
        QtCore.QTimer.singleShot(0, restore_ai_output_anchor)
        QtCore.QTimer.singleShot(30, restore_ai_output_anchor)
        QtCore.QTimer.singleShot(90, restore_ai_output_anchor)

        self._sync_ai_chat_sidebar_action()

        if persist:
            if enabled:
                self._remember_ai_sidebar_width()
            self.app.settings['ai_chat_sidebar'] = 'True' if enabled else 'False'
            self.app.write_config_ini(self.app.settings, self.app.ai_models)

    def toggle_ai_chat_sidebar(self, checked):
        """Handle menu toggle for AI chat sidebar mode."""

        self.set_ai_chat_sidebar_mode(checked)
        if bool(self.ai_chat_sidebar_mode) != bool(checked):
            self._sync_ai_chat_sidebar_action()
            return
        if not self.ai_chat_sidebar_mode:
            self.ui.tabWidget.setCurrentWidget(self.ui.tab_ai_agent)

    def close_ai_chat_sidebar(self):
        """Return AI chat from sidebar back into the main AI tab."""

        self.set_ai_chat_sidebar_mode(False)
        self.ui.tabWidget.setCurrentWidget(self.ui.tab_ai_agent)

    def on_main_splitter_moved(self, pos, index):  # pos/index are Qt callback args
        """Track current AI sidebar width while user drags splitter."""

        if getattr(self, 'ai_sidebar_splitter_is_restoring', False):
            return
        if self.ai_chat_sidebar_mode:
            self._remember_ai_sidebar_width()
            self.ai_sidebar_splitter_save_timer.start(400)

    def tab_layout_helper(self, tab_widget, ui):
        """ Used when loading a coding, report or manage dialog  in to a tab widget.
         Add widget if no layout.
         If there is a layout, then remove all widgets from it and add the new widget. """

        self.ui.tabWidget.setCurrentWidget(tab_widget)
        contents = tab_widget.layout()
        if contents is None:
            contents = QtWidgets.QVBoxLayout(tab_widget)
            contents.setContentsMargins(9, 9, 9, 9)
        self.clear_tab_widgets(tab_widget, show_placeholder=ui is None)
        if ui is not None:
            contents.addWidget(ui)

    def refresh_open_code_display_settings(self):
        """Apply saved code stripe and highlight settings to open code text and PDF dialogs."""

        for tab_widget in (self.ui.tab_coding, self.ui.tab_reports, self.ui.tab_manage):
            layout = tab_widget.layout()
            if layout is None:
                continue
            for i in range(layout.count()):
                widget = layout.itemAt(i).widget()
                if isinstance(widget, (DialogCodeText, DialogCodePdf)):
                    widget.apply_margin_stripe_setting()
                    widget.apply_highlight_style_setting()

    def codebook(self):
        """ Export a text file code book of categories and codes. """

        Codebook(self.app, self.ui.textEdit)

    def codebook_with_memos(self):
        """ Export a text file code book of categories and codes with their memos.
        """

        Codebook(self.app, self.ui.textEdit, memos=True)

    def refi_project_export(self):
        """ Export the project as a qpdx zipped folder.
         Follows the REFI Project Exchange standards.
         NEED TO TEST RELATIVE EXPORTS, TIMESTAMPS AND TRANSCRIPTION
        """

        RefiExport(self.app, self.ui.textEdit, "project")

    def refi_codebook_export(self):
        """ Export the codebook as .qdc
        Follows the REFI standard version 1.0. https://www.qdasoftware.org/
        """
        #
        RefiExport(self.app, self.ui.textEdit, "codebook")

    def refi_codebook_import(self):
        """ Import a codebook .qdc into an opened project.
        Follows the REFI-QDA standard version 1.0. https://www.qdasoftware.org/
         """

        RefiImport(self.app, self.ui.textEdit, "qdc")

    def refi_project_import(self):
        """ Import a qpdx QDA project into a new project space.
        Follows the REFI standard.
        CURRENTLY IN TESTING AND NOT COMPLETE NOR VALIDATED.
         NEED TO TEST RELATIVE EXPORTS, TIMESTAMPS AND TRANSCRIPTION
        """

        self.close_project()
        self.ui.textEdit.append(_("IMPORTING REFI-QDA PROJECT"))
        msg = _(
            "Step 1: You will be asked for a new QualCoder project name.\nStep 2: You will be asked for the QDPX file.")
        Message(self.app, _('REFI-QDA import steps'), msg).exec()
        self.new_project()
        # Check project created successfully
        if self.app.project_name == "":
            Message(self.app, _("Project creation"), _("REFI-QDA Project not successfully created"), "warning").exec()
            return
        RefiImport(self.app, self.ui.textEdit, "qdpx")
        if self.app.settings['ai_enable'] == 'True':
            self.app.ai.init_llm(self, rebuild_vectorstore=True)
        self.project_summary_report()

    def taguette_project_import(self):
        """ Import a Taguette project into a new project space. """

        self.close_project()
        msg = _(
            "Step 1: You will be asked for a new QualCoder project name.\nStep 2: You will be asked for the Taguette.sqlite3 file.")
        Message(self.app, _('RQDA import steps'), msg).exec()
        self.new_project()
        # Check project created successfully
        if self.app.project_name == "":
            Message(self.app, _('Project creation'), _("Project not successfully created"), "critical").exec()
            return
        TaguetteImport(self.app, self.ui.textEdit)
        self.project_summary_report()

    def rqda_project_import(self):
        """ Import an RQDA format project into a new project space. """

        self.close_project()
        self.ui.textEdit.append(_("IMPORTING RQDA PROJECT"))
        msg = _(
            "Step 1: You will be asked for a new QualCoder project name.\nStep 2: You will be asked for the RQDA file.")
        Message(self.app, _('RQDA import steps'), msg).exec()
        self.new_project()
        # Check project created successfully
        if self.app.project_name == "":
            Message(self.app, _('Project creation'), _("Project not successfully created"), "critical").exec()
            return
        RqdaImport(self.app, self.ui.textEdit)
        self.project_summary_report()

    def closeEvent(self, event):
        """ Override the QWindow close event.
        Close all dialogs and database connection.
        Close project will also delete a backup if a backup was made and no changes occurred.
        """

        if not self.force_quit:
            reply = QtWidgets.QMessageBox.question(
                self, 'Message', _("Are you sure you want to quit?"),
                QtWidgets.QMessageBox.StandardButton.Yes,
                QtWidgets.QMessageBox.StandardButton.No
            )
            if reply != QtWidgets.QMessageBox.StandardButton.Yes:
                event.ignore()
                return

        if self.ai_chat_sidebar_mode:
            self._remember_ai_sidebar_width()
        self.ai_sidebar_splitter_save_timer.stop()

        self.close_project()

        self.app.settings['mainwindow_geometry'] = (
            self.saveGeometry().toHex().data().decode('utf-8')
        )
        self.app.write_config_ini(self.app.settings, self.app.ai_models)

        if self.app.conn is not None:
            try:
                self.app.conn.commit()
                self.app.conn.close()
            except Exception as err:
                print("closeEvent", err)
                logger.warning("close event " + str(err))

        # Accept the event and let Qt handle quitting
        event.accept()

        # Let pending deleteLaters run before loop exits
        QtCore.QTimer.singleShot(0, QtCore.QCoreApplication.processEvents)

    def new_project(self):
        """ Create a new project folder with data.qda (sqlite) and folders for documents,
        images, audio and video.
        Note the database does not keep a table specifically for users (coders), instead
        usernames can be freely entered through the settings dialog and are collated from
        coded text, images and a/v.
        v2 has added column in code_text table to link to avid in code_av table.
        v3 has added columns in code_text, code_image, code_av for important - to mark particular important codings.
        v4 has added column ctid (autonumber) in code_text.
        v5 had added column for codername in project. added column for av_text_id in source to link A/V with text file.
            And a stored_sql table.
        v6 has tables for storage of graph items.
        v7 has memo links from graph items (text/image/av to coding memos).
        v8 has table for ris bibliography data.
        v9 has project.recently_used_codes text')  # code ids list split by a space
        v10 has code_image.pdf_page integer added
        v11 has gr_pix_item.pdf_page integer added
        v12 has manage_files_display table added. For Table display profile.
        v13 creates table files_filter?
        v14 has coder_names table added to store codernames and their visibility status
        """

        self.close_project()
        self.journal_display = None
        previous_app = self.app
        self.app = App()
        if self.app.settings['directory'] == "":
            self.app.settings['directory'] = get_default_user_directory()
        self.app.ai = AiLLM(self.app, self.ui.textEdit)
        project_path, ok = QtWidgets.QFileDialog.getSaveFileName(self,
                                                             _("Enter project name"), self.app.settings['directory'])
        if project_path == "":
            self.app = previous_app
            Message(self.app, _("Project"), _("No project created."), "critical").exec()
            return

        # Add suffix to project name if it already exists
        counter = 0
        extension = ""
        while Path(f"{project_path}{extension}.qda").exists():
            if counter > 0:
                extension = f"_{counter}"
            counter += 1
        self.app.project_path = project_path + extension + ".qda"
        try:
            Path(self.app.project_path).mkdir()
            i = Path(self.app.project_path) / "images"
            i.mkdir()
            a = Path(self.app.project_path) / "audio"
            a.mkdir()
            v = Path(self.app.project_path) / "video"
            v.mkdir()
            d = Path(self.app.project_path) / "documents"
            d.mkdir()
        except Exception as err:
            logger.critical(_("Project creation error ") + str(err))
            Message(self.app, _("Project"), self.app.project_path + _(" not successfully created"), "critical").exec()
            self.app = App()
            self.app.ai = AiLLM(self.app, self.ui.textEdit)
            return
        self.app.project_name = self.app.project_path.rpartition('/')[2]
        self.app.settings['directory'] = self.app.project_path.rpartition('/')[0]
        self.app.create_connection(self.app.project_path)
        cur = self.app.conn.cursor()
        cur.execute(
            "CREATE TABLE project (databaseversion text, date text, memo text,about text, bookmarkfile integer, "
            "bookmarkpos integer, codername text, recently_used_codes text, avbookmarkfile integer, avbookmarkmsec integer, avbookmarktextpos integer)")
        cur.execute(
            "CREATE TABLE source (id integer primary key, name text, fulltext text, mediapath text, memo text, "
            "owner text, date text, av_text_id integer, risid integer, unique(name))")
        cur.execute(
            "CREATE TABLE code_image (imid integer primary key,id integer,x1 integer, y1 integer, width integer, "
            "height integer, cid integer, memo text, date text, owner text, important integer, pdf_page integer)")
        cur.execute(
            "CREATE TABLE code_av (avid integer primary key,id integer,pos0 integer, pos1 integer, cid integer, "
            "memo text, date text, owner text, important integer)")
        cur.execute(
            "CREATE TABLE annotation (anid integer primary key, fid integer,pos0 integer, pos1 integer, memo text, "
            "owner text, date text, unique(fid,pos0,pos1,owner))")
        cur.execute(
            "CREATE TABLE attribute_type (name text primary key, date text, owner text, memo text, caseOrFile text, "
            "valuetype text)")
        # Database version v6 - unique constraint for attribute (name, attr_type, id)
        cur.execute(
            "CREATE TABLE attribute (attrid integer primary key, name text, attr_type text, value text, id integer, "
            "date text, owner text, unique(name,attr_type,id))")
        cur.execute(
            "CREATE TABLE case_text (id integer primary key, caseid integer, fid integer, pos0 integer, pos1 integer, "
            "owner text, date text, memo text)")
        cur.execute(
            "CREATE TABLE cases (caseid integer primary key, name text, memo text, owner text,date text, "
            "constraint ucm unique(name))")
        cur.execute(
            "CREATE TABLE code_cat (catid integer primary key, name text, owner text, date text, memo text, "
            "supercatid integer, unique(name))")
        cur.execute(
            "CREATE TABLE code_text (ctid integer primary key, cid integer, fid integer,seltext text, pos0 integer, "
            "pos1 integer, owner text, date text, memo text, avid integer, important integer, "
            "unique(cid,fid,pos0,pos1, owner))")
        cur.execute(
            "CREATE TABLE code_name (cid integer primary key, name text, memo text, catid integer, owner text,"
            "date text, color text, supercid integer, unique(name))")  # supercid: sub-code (parent code)
        # Database version v6 - unique name for journal
        cur.execute("CREATE TABLE journal (jid integer primary key, name text, jentry text, date text, owner text, "
                    "unique(name))")
        cur.execute("CREATE TABLE stored_sql (title text, description text, grouper text, ssql text, unique(title))")
        # Tables to store graph. sqlite 0 is False 1 is True
        cur.execute("CREATE TABLE graph (grid integer primary key, name text, description text, "
                    "date text, scene_width integer, scene_height integer, unique(name));")
        cur.execute("CREATE TABLE gr_cdct_text_item (gtextid integer primary key, grid integer, x integer, y integer, "
                    "supercatid integer, catid integer, cid integer, font_size integer, bold integer, "
                    "isvisible integer, displaytext text);")
        cur.execute("CREATE TABLE gr_case_text_item (gcaseid integer primary key, grid integer, x integer, "
                    "y integer, caseid integer, font_size integer, bold integer, color text, displaytext text);")
        cur.execute("CREATE TABLE gr_file_text_item (gfileid integer primary key, grid integer, x integer, "
                    "y integer, fid integer, font_size integer, bold integer, color text, displaytext text);")
        cur.execute("CREATE TABLE gr_free_text_item (gfreeid integer primary key, grid integer, freetextid integer,"
                    "x integer, y integer, free_text text, font_size integer, bold integer, color text,"
                    "tooltip text, ctid integer,memo_ctid integer, memo_imid integer, memo_avid integer);")
        # Database version v17. Label and arrow_mode columns on line items
        cur.execute("CREATE TABLE gr_cdct_line_item (glineid integer primary key, grid integer, "
                    "fromcatid integer, fromcid integer, tocatid integer, tocid integer, color text, "
                    "linewidth real, linetype text, isvisible integer, label text, arrow_mode text);")
        cur.execute("CREATE TABLE gr_free_line_item (gflineid integer primary key, grid integer, "
                    "fromfreetextid integer, fromcatid integer, fromcid integer, fromcaseid integer,"
                    "fromfileid integer, fromimid integer, fromavid integer, tofreetextid integer, tocatid integer, "
                    "tocid integer, tocaseid integer, tofileid integer, toimid integer, toavid integer, color text,"
                    "linewidth real, linetype text, label text, arrow_mode text);")
        # Database version v17. Memo nodes on graphs
        cur.execute("CREATE TABLE gr_memo_item (gmemoid integer primary key, grid integer, "
                    "memo_source_type text, memo_source_id integer, x integer, y integer, "
                    "color text, font_size integer);")
        cur.execute("CREATE TABLE gr_pix_item (grpixid integer primary key, grid integer, imid integer,"
                    "x integer, y integer, px integer, py integer, w integer, h integer, filepath text,"
                    "tooltip text, pdf_page integer);")
        cur.execute("CREATE TABLE gr_av_item (gr_avid integer primary key, grid integer, avid integer,"
                    "x integer, y integer, pos0 integer, pos1 integer, filepath text, tooltip text, color text);")
        cur.execute("CREATE TABLE ris (risid integer, tag text, longtag text, value text);")
        cur.execute("CREATE TABLE manage_files_display (mfid integer primary key, name text, tblrows text, tblcolumns text, owner text);")
        cur.execute("CREATE TABLE files_filter (filterid integer primary key, name text, filter text, owner text);")
        self.app.update_coder_names()  # Create table coder_names, add current coder, create views, etc.
        cur.execute("INSERT INTO project VALUES(?,?,?,?,?,?,?,?,null,null,null)",
                    ('v17', datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"), '', self.app.version, 0,
                     0, self.app.settings['codername'], ""))
        self.app.conn.commit()
        try:
            # Get and display some project details
            self.ui.textEdit.append("\n" + _("New project: ") + self.app.project_path + _(" created."))
            self.ui.textEdit.append(_("Opening: ") + self.app.project_path)
            self.setWindowTitle("QualCoder " + self.app.project_name)
            cur.execute('select sqlite_version()')
            self.ui.textEdit.append(f"SQLite version: {cur.fetchone()}")
            cur.execute("select databaseversion, date, memo, about from project")
            result = cur.fetchone()
            self.project['databaseversion'] = result[0]
            self.project['date'] = result[1]
            self.project['memo'] = result[2]
            self.project['about'] = result[3]
            self.ui.textEdit.append(_("New Project Created") + "\n" + "▔" * 20 + "\n"  # U2594
                                    + _("DB Version:") + f"{self.project['databaseversion']}\n"
                                    + _("Date: ") + f"{self.project['date']}\n"
                                    + _("About: ") + f"{self.project['about']}\n"
                                    + _("Coder:") + f"{self.app.settings['codername']}\n"
                                    + "▔" * 20)
        except Exception as err:
            msg = _("Problem creating database ")
            logger.warning(f"{msg}{self.app.project_path} Exception: {err}")
            self.ui.textEdit.append(f"\n{msg}\n{self.app.project_path}")
            self.ui.textEdit.append(str(err))
            print(err)
            self.close_project()
            return
        # New project, so tell open project NOT to back up, as there will be nothing in there to back up
        self.open_project(self.app.project_path, "yes")
        self.ui.tabWidget.setCurrentWidget(self.ui.tab_action_log)
        for tab_widget in (self.ui.tab_reports, self.ui.tab_coding, self.ui.tab_manage):
            self.clear_tab_widgets(tab_widget, show_placeholder=True)

    def change_settings(self, section=None, enable_ai=False):
        """ Change default settings - the coder name, font, font size.
        Language, Backup options.
        As this dialog affects all others if the coder name changes, on exit of the dialog,
        all other opened dialogs are destroyed.
        
        section = 'AI' moves to the AI settings at the bottom of the dialog
        enable_ai = if True, the AI will be enabled in settings
        """
        current_coder = self.app.settings['codername']
        ui = DialogSettings(self.app, section=section, enable_ai=enable_ai)
        ret = ui.exec()
        if ret == QtWidgets.QDialog.DialogCode.Rejected:  # Dialog has been canceled
            return

        self.app.settings, self.app.ai_models = self.app.load_settings()
        self.settings_report(swith_to_action_log=False)
        font = f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";'
        self.setStyleSheet(font)
        self.update_placeholder_tab_styles()
        self.ai_chat_window.init_styles()
        self.refresh_open_code_display_settings()
        
        if self.app.settings['ai_enable'] == 'True':
            self.app.ai.init_llm(self, rebuild_vectorstore=False)
        else:  
            self.app.ai.close()
        self._show_pending_ai_model_upgrade_offer()
        self.update_ai_menu_options()
        self.ai_chat_window.refresh_placeholder_if_visible()
            
        # Change in coder names: Close all opened dialogs as coder names needs to change everywhere
        if ui.coder_names_changes:
            if current_coder != self.app.settings['codername']:
                self.ui.textEdit.append(_("Coder name changed to: ") + self.app.settings['codername'])
            for tab_widget in (self.ui.tab_reports, self.ui.tab_coding, self.ui.tab_manage):
                self.clear_tab_widgets(tab_widget, show_placeholder=True)
                    
    def project_memo(self):
        """ Give the entire project a memo. """
        memo = self.app.get_project_memo()
        # If the memo is empty, add a template that defines all the necessary information for the AI  
        if memo is None or memo == '':
            memo = _('**Research topic, questions and objectives:** \n\n'
                     '**Methodology:** \n\n'
                     '**Participants and data collected:** \n\n'
                     '#####\n'
                     '(Everything below this mark is a personal note and will never be sent to the AI.)')
        ui = DialogMemo(self.app, _("Memo for project ") + self.app.project_name,
                        memo, entity_type="project")
        ui.exec()
        if memo != ui.memo:
            cur = self.app.conn.cursor()
            cur.execute('update project set memo=?', (ui.memo,))
            self.app.conn.commit()
            self.ui.textEdit.append(_("Project memo entered."))
            self.app.delete_backup = False

    def open_project(self, path_:str="", newproject:str="no"):
        """ Open an existing project.
        if set, also save a backup datetime stamped copy at the same time.
        Do not back up on a newly created project, as it will not contain data.
        A backup is created if settings backup is True.
        The backup is deleted, if no changes.
        Backups are created using the date and 24 hour suffix: _BKUP_yyyymmdd_hh
        Backups are not replaced within the same hour.
        Update older databases to current version mainly by adding columns and tables.
        Table constraints are not updated (code_text duplicated codings).
        Args:
            path_: if path is "" then get the path from a dialog, otherwise use the supplied path
            newproject: yes or no  if yes then do not make an initial backup
        """

        self.journal_display = None
        default_directory = self.app.settings['directory']
        if path_ == "" or path_ is False:
            if default_directory == "":
                default_directory = get_default_user_directory()
            path_ = QtWidgets.QFileDialog.getExistingDirectory(self,
                                                               _('Open project directory'), default_directory)
        if path_ == "" or path_ is False:
            return
        msg = ""
        # New path variable from recent_projects.txt contains time | path
        # Older variable only listed the project path
        path_split = path_.split("|")
        proj_path = ""
        if len(path_split) == 1:
            proj_path = path_split[0]
        if len(path_split) == 2:
            proj_path = path_split[1]
        if len(proj_path) > 3 and proj_path[-4:] == ".qda":
            # Close the current project first: stale tab dialogs show old data and can
            # write its ids into the new database (newproject flow already closed it)
            if newproject == "no" and (self.app.project_name != "" or self.app.conn is not None):
                self.close_project()
            try:
                self.app.create_connection(proj_path)
            except Exception as err:
                self.app.conn = None
                msg += " " + str(err)
                logger.debug(msg)
        if self.app.conn is None:
            msg += f"\n{proj_path}"
            Message(self.app, _("Cannot open file"), msg, "critical").exec()
            self.app.project_path = ""
            self.app.project_name = ""
            return
        # Check that the connection is to a valid QualCoder database
        cur = self.app.conn.cursor()
        try:
            cur.execute("select databaseversion, date, memo, about from project")
            res = cur.fetchone()
            if "QualCoder" not in res[3]:
                logger.debug("This is not a QualCoder database")
                self.close_project()
                return
        except Exception as err:
            logger.debug("This in not a QualCoder database " + str(err))
            self.close_project()
            return

        # Potential design flaw to have the current coders name in the config.ini file (early versions of QC).
        # as it would change to this coder when opening different projects
        # Check that the coder name from setting ini file is in the project
        # If not then user is asked if they want to switch.
        # Database version 5 (QualCoder 2.8 and newer) stores the current coder in the project table
        last_project_coder = self.app.get_last_project_coder()
        if last_project_coder != "" and last_project_coder != self.app.settings['codername']:
            msg = _('Your current coder name ("{}") differs from the one last used in the project ("{}"). Do you want to keep your current name or switch to the one from the project?'.format(
                self.app.settings['codername'], last_project_coder)
            )
            msg_box = Message(self.app, _('Coder name'), msg, 'warning')
            msg_box.setStandardButtons(QtWidgets.QMessageBox.StandardButton.NoButton)  # Clear default buttons
            keep_button = msg_box.addButton(_('Keep'), QtWidgets.QMessageBox.ButtonRole.YesRole)
            switch_button = msg_box.addButton(_('Switch'), QtWidgets.QMessageBox.ButtonRole.NoRole)
            cancel_button = msg_box.addButton(_('Cancel'), QtWidgets.QMessageBox.ButtonRole.RejectRole)
            msg_box.setDefaultButton(keep_button) 
            msg_box.exec()
            res = msg_box.clickedButton()
            if res == keep_button:
                pass                
            elif res == switch_button:
                self.app.settings['codername'] = last_project_coder
                self.app.write_config_ini(self.app.settings, self.app.ai_models)
                self.ui.textEdit.append(_("Default coder name changed to: ") + last_project_coder)                
            else:  # Cancel or closed
                self.close_project()                
                return

        # Display some project details
        self.app.append_recent_project(self.app.project_path)
        self.fill_recent_projects_menu_actions()
        self.setWindowTitle("QualCoder " + self.app.project_name)

        # Check avid column in code_text table, Database version v2
        cur = self.app.conn.cursor()
        try:
            cur.execute("select avid from code_text")
        except sqlite3.OperationalError:
            try:
                cur.execute("ALTER TABLE code_text ADD avid integer")
                self.app.conn.commit()
            except Exception as err:
                logger.debug(str(err))
        try:
            cur.execute("select bookmarkfile from project")
        except sqlite3.OperationalError:
            try:
                cur.execute("ALTER TABLE project ADD bookmarkfile integer")
                self.app.conn.commit()
                cur.execute("ALTER TABLE project ADD bookmarkpos integer")
                self.app.conn.commit()
                self.ui.textEdit.append(_("Updating database to version") + " v2")
            except Exception as err:
                logger.debug(str(err))
        # Database version v3
        cur = self.app.conn.cursor()
        try:
            cur.execute("select important from code_text")
        except sqlite3.OperationalError:
            try:
                cur.execute("ALTER TABLE code_text ADD important integer")
                self.app.conn.commit()
            except Exception as err:
                logger.debug(str(err))
                cur = self.app.conn.cursor()
        try:
            cur.execute("select important from code_av")
        except sqlite3.OperationalError:
            try:
                cur.execute("ALTER TABLE code_av ADD important integer")
                self.app.conn.commit()
            except Exception as err:
                logger.debug(str(err))
        cur = self.app.conn.cursor()
        try:
            cur.execute("select important from code_image")
        except sqlite3.OperationalError:
            try:
                cur.execute("ALTER TABLE code_image ADD important integer")
                self.app.conn.commit()
                self.ui.textEdit.append(_("Updating database to version") + " v3")
            except Exception as err:
                logger.debug(str(err))
        # Database version v4
        try:
            cur.execute("select ctid from code_text")
        except sqlite3.OperationalError:
            cur.execute(
                "CREATE TABLE code_text2 (ctid integer primary key, cid integer, fid integer,seltext text, "
                "pos0 integer, pos1 integer, owner text, date text, memo text, avid integer, important integer, "
                "unique(cid,fid,pos0,pos1, owner))")
            self.app.conn.commit()
            sql = "insert into code_text2 (cid, fid, seltext, pos0, pos1, owner, date, memo, avid, important) "
            sql += "select cid, fid, seltext, pos0, pos1, owner, date, memo, avid, important from code_text"
            cur.execute(sql)
            self.app.conn.commit()
            cur.execute("drop table code_text")
            cur.execute("alter table code_text2 rename to code_text")
            cur.execute('update project set databaseversion="v4", about=?', [self.app.version])
            self.app.conn.commit()
            self.ui.textEdit.append(_("Updating database to version") + " v4")
        # Database version v5
        # Add codername to project, add av_text_id to source, add stored sql table
        try:
            cur.execute("select codername from project")
        except sqlite3.OperationalError:
            print(self.app.settings['codername'])
            cur.execute("ALTER TABLE project ADD codername text")
            self.app.conn.commit()
            cur.execute('update project set databaseversion="v5", about=?, codername=?',
                        [self.app.version, self.app.settings['codername']])
            self.app.conn.commit()
        try:
            cur.execute("select av_text_id from source")
        except sqlite3.OperationalError:
            cur.execute('ALTER TABLE source ADD av_text_id integer')
            self.app.conn.commit()
            # Add id link from AV file to text file.
            av_files = self.app.get_av_filenames()  # id, name, memo
            text_files = self.app.get_text_filenames()  # id, name, memo
            for av in av_files:
                for t in text_files:
                    if av['name'] + ".transcribed" == t['name']:
                        cur.execute('update source set av_text_id =? where id=?', [t['id'], av['id']])
                        self.app.conn.commit()
            self.ui.textEdit.append(_("Updating database to version") + " v5")
        try:
            cur.execute("select title from stored_sql")
        except sqlite3.OperationalError:
            cur.execute(
                "CREATE TABLE stored_sql (title text, description text, grouper text, ssql text, unique(title));")
            self.app.conn.commit()
        # Database version 6  - add Graph tables
        try:
            cur.execute("select name, description, date from graph")
        except sqlite3.OperationalError:
            cur.execute("CREATE TABLE graph (grid integer primary key, name text, description text, "
                        "date text, scene_width integer, scene_height integer, unique(name));")
            self.app.conn.commit()
        try:
            cur.execute("select gtextid from gr_cdct_text_item")
        except sqlite3.OperationalError:
            cur.execute(
                "CREATE TABLE gr_cdct_text_item (gtextid integer primary key, grid integer, x integer, y integer, "
                "supercatid integer, catid integer, cid integer, font_size integer, bold integer, "
                "isvisible integer, displaytext text);")
            self.app.conn.commit()
        try:
            cur.execute("select gcaseid from gr_case_text_item")
        except sqlite3.OperationalError:
            cur.execute("CREATE TABLE gr_case_text_item (gcaseid integer primary key, grid integer, x integer, "
                        "y integer, caseid integer, font_size integer, bold integer, color text, displaytext text);")
            self.app.conn.commit()
        try:
            cur.execute("select gfileid from gr_file_text_item")
        except sqlite3.OperationalError:
            cur.execute("CREATE TABLE gr_file_text_item (gfileid integer primary key, grid integer, x integer, "
                        "y integer, fid integer, font_size integer, bold integer, color text, displaytext text);")
            self.app.conn.commit()
        try:
            cur.execute("select gfreeid from gr_free_text_item")
        except sqlite3.OperationalError:
            cur.execute("CREATE TABLE gr_free_text_item (gfreeid integer primary key, grid integer, freetextid integer,"
                        "x integer, y integer, free_text text, font_size integer, bold integer, color text,"
                        "tooltip text, ctid integer);")
            self.app.conn.commit()
        try:
            cur.execute("select glineid from gr_cdct_line_item")
        except sqlite3.OperationalError:
            cur.execute("CREATE TABLE gr_cdct_line_item (glineid integer primary key, grid integer, "
                        "fromcatid integer, fromcid integer, tocatid integer, tocid integer, color text, "
                        "linewidth real, linetype text, isvisible integer);")
            self.app.conn.commit()
        try:
            cur.execute("select gflineid from gr_free_line_item")
        except sqlite3.OperationalError:
            cur.execute("CREATE TABLE gr_free_line_item (gflineid integer primary key, grid integer, "
                        "fromfreetextid integer, fromcatid integer, fromcid integer, fromcaseid integer,"
                        "fromfileid integer, fromimid integer, fromavid integer, tofreetextid integer, tocatid integer,"
                        "tocid integer, tocaseid integer, tofileid integer, toimid integer, toavid integer, color text,"
                        " linewidth real, linetype text);")
            self.app.conn.commit()
        try:
            cur.execute("select grpixid from gr_pix_item")
        except sqlite3.OperationalError:
            cur.execute("CREATE TABLE gr_pix_item (grpixid integer primary key, grid integer, imid integer,"
                        "x integer, y integer, px integer, py integer, w integer, h integer, filepath text,"
                        "tooltip text);")
            self.app.conn.commit()
        try:
            cur.execute("select gr_avid from gr_av_item")
        except sqlite3.OperationalError:
            cur.execute("CREATE TABLE gr_av_item (gr_avid integer primary key, grid integer, avid integer,"
                        "x integer, y integer, pos0 integer, pos1 integer, filepath text, tooltip text, color text);")
            self.app.conn.commit()
            cur.execute('update project set databaseversion="v6", about=?', [self.app.version])
            self.ui.textEdit.append(_("Updating database to version") + " v6")
        # Database version v7
        db7_update = False
        try:
            cur.execute("select memo_ctid from gr_free_text_item")
        except sqlite3.OperationalError:
            cur.execute('ALTER TABLE gr_free_text_item ADD memo_ctid integer')
            self.app.conn.commit()
            db7_update = True
        try:
            cur.execute("select memo_imid from gr_free_text_item")
        except sqlite3.OperationalError:
            cur.execute('ALTER TABLE gr_free_text_item ADD memo_imid integer')
            self.app.conn.commit()
            db7_update = True
        try:
            cur.execute("select memo_avid from gr_free_text_item")
        except sqlite3.OperationalError:
            cur.execute('ALTER TABLE gr_free_text_item ADD memo_avid integer')
            self.app.conn.commit()
            db7_update = True
        if db7_update:
            cur.execute('update project set databaseversion="v7", about=?', [self.app.version])
            self.app.conn.commit()
            self.ui.textEdit.append(_("Updating database to version") + " v7")
        # Database version v8
        try:
            cur.execute("select risid from ris")
        except sqlite3.OperationalError:
            cur.execute("CREATE TABLE ris (risid integer, tag text, longtag text, value text);")
            cur.execute('update project set databaseversion="v8", about=?', [self.app.version])
            self.app.conn.commit()
            self.ui.textEdit.append(_("Updating database to version") + " v8")
        try:
            cur.execute("select risid from source")
        except sqlite3.OperationalError:
            cur.execute('ALTER TABLE source ADD risid integer')
        # Database version v9
        try:
            cur.execute("select recently_used_codes from project")
        except sqlite3.OperationalError:
            cur.execute('ALTER TABLE project ADD recently_used_codes text')  # code ids list split by a space
            cur.execute('update project set databaseversion="v9", about=?', [self.app.version])
            self.app.conn.commit()
            self.ui.textEdit.append(_("Updating database to version") + " v9")
        # Database version v10
        try:
            cur.execute("select pdf_page from code_image")
        except sqlite3.OperationalError:
            cur.execute('ALTER TABLE code_image ADD pdf_page integer')  #
            cur.execute('update project set databaseversion="v10", about=?', [self.app.version])
            self.app.conn.commit()
            self.ui.textEdit.append(_("Updating database to version") + " v10")
        # Database version v11
        try:
            cur.execute("select pdf_page from gr_pix_item")
        except sqlite3.OperationalError:
            cur.execute('ALTER TABLE gr_pix_item ADD pdf_page integer')  #
            cur.execute('update project set databaseversion="v11", about=?', [self.app.version])
            self.app.conn.commit()
            self.ui.textEdit.append(_("Updating database to version") + " v11")

        # Database version v12
        try:
            cur.execute("select name from manage_files_display")
        except sqlite3.OperationalError:
            cur.execute("CREATE TABLE manage_files_display (mfid integer primary key, name text, tblrows text, tblcolumns text, owner text);")
            cur.execute('update project set databaseversion="v12", about=?', [self.app.version])
            self.app.conn.commit()
            self.ui.textEdit.append(_("Updating database to version") + " v12")
        # Database version v13
        try:
            cur.execute("select name from files_filter")
        except sqlite3.OperationalError:
            cur.execute("CREATE TABLE files_filter (filterid integer primary key, name text, filter text, owner text);")
            cur.execute('update project set databaseversion="v13", about=?', [self.app.version])
            self.app.conn.commit()
            self.ui.textEdit.append(_("Updating database to version") + " v13")
        # Database version v14
        try:
            cur.execute("select name from coder_names")
        except sqlite3.OperationalError:
            self.app.update_coder_names()  # Create table coder_names, add current coder, create views, etc.
            cur.execute('update project set databaseversion="v14", about=?', [self.app.version])
            self.app.conn.commit()
            self.ui.textEdit.append(_("Updating database to version") + " v14")
        # Database version v15
        try:
            cur.execute("select avbookmarkfile from project")
        except sqlite3.OperationalError:
            cur.execute("alter table project add avbookmarkfile integer")
            cur.execute("alter table project add avbookmarkmsec integer")
            cur.execute('update project set databaseversion="v15", about=?', [self.app.version])
            self.app.conn.commit()
            self.ui.textEdit.append(_("Updating database to version") + " v15")
        # Repair: projects created with the DDL typo 'avbookmarktext' instead of
        # 'avbookmarktextpos'. The v15 block never fixes them because avbookmarkfile exists.
        try:
            cur.execute("select avbookmarktextpos from project")
        except sqlite3.OperationalError:
            try:
                # Rename keeps any stored bookmark position
                cur.execute("alter table project rename column avbookmarktext to avbookmarktextpos")
            except sqlite3.OperationalError:
                cur.execute("alter table project add avbookmarktextpos integer")
            self.app.conn.commit()
            self.ui.textEdit.append(_("Repaired project table column avbookmarktextpos"))
        # Database version v16 - sub-codes: a code can be nested under another code (supercid)
        try:
            cur.execute("select supercid from code_name")
        except sqlite3.OperationalError:
            cur.execute("alter table code_name add supercid integer")
            cur.execute('update project set databaseversion="v16", about=?', [self.app.version])
            self.app.conn.commit()
            self.ui.textEdit.append(_("Updating database to version") + " v16")
        # Database version v17. Graph memo nodes and relation line label/arrow persistence
        try:
            cur.execute("select label, arrow_mode from gr_cdct_line_item")
        except sqlite3.OperationalError:
            cur.execute("alter table gr_cdct_line_item add label text")
            cur.execute("alter table gr_cdct_line_item add arrow_mode text")
            cur.execute("alter table gr_free_line_item add label text")
            cur.execute("alter table gr_free_line_item add arrow_mode text")
            cur.execute("CREATE TABLE IF NOT EXISTS gr_memo_item (gmemoid integer primary key, grid integer, "
                        "memo_source_type text, memo_source_id integer, x integer, y integer, "
                        "color text, font_size integer);")
            cur.execute('update project set databaseversion="v17", about=?', [self.app.version])
            self.app.conn.commit()
            self.ui.textEdit.append(_("Updating database to version") + " v17")
        # Delete codings (fid, id) that do not have a matching source id
        sql = "select fid from code_text where fid not in (select source.id from source)"
        cur.execute(sql)
        res = cur.fetchall()
        if res:
            self.ui.textEdit.append(_("Deleting code_text coding to deleted files: ") + str(res))
        for r in res:
            cur.execute("delete from code_text where fid=?", [r[0]])
        sql = "select code_image.id from code_image where code_image.id not in (select source.id from source)"
        cur.execute(sql)
        res = cur.fetchall()
        if res:
            self.ui.textEdit.append(_("Deleting code_image coding to deleted files: ") + str(res))
        for r in res:
            cur.execute("delete from code_image where id=?", [r[0]])
        sql = "select code_av.id from code_av where code_av.id not in (select source.id from source)"
        cur.execute(sql)
        res = cur.fetchall()
        if res:
            self.ui.textEdit.append(_("Deleting code_av coding to deleted files: ") + str(res))
        for r in res:
            cur.execute("delete from code_av where id=?", [r[0]])
        self.app.conn.commit()

        # Fix 'lost' categories if present.
        sql = "update code_cat set supercatid=null where supercatid is not null and supercatid not in "
        sql += "(select catid from code_cat)"
        cur.execute(sql)
        self.app.conn.commit()
        # Fix 'lost' sub-codes if present (parent code deleted but supercid not cleared).
        sql = "update code_name set supercid=null where supercid is not null and supercid not in "
        sql += "(select cid from code_name)"
        cur.execute(sql)
        # Mutual exclusivity: if a code somehow has both catid and supercid, supercid wins.
        cur.execute("update code_name set catid=null where supercid is not null and catid is not null")
        self.app.conn.commit()
        # Break hierarchy cycles (a corrupted project could make a branch disappear).
        # Categories: code_cat.supercatid
        cur.execute("select catid, supercatid from code_cat")
        cat_parent = {row[0]: row[1] for row in cur.fetchall()}
        cat_changed = False
        for start in list(cat_parent.keys()):
            seen = set()
            node = start
            while node is not None and node in cat_parent:
                if node in seen:
                    cur.execute("update code_cat set supercatid=null where catid=?", [node])
                    cat_parent[node] = None
                    cat_changed = True
                    break
                seen.add(node)
                node = cat_parent[node]
        # Codes: code_name.supercid
        cur.execute("select cid, supercid from code_name")
        code_parent = {row[0]: row[1] for row in cur.fetchall()}
        code_changed = False
        for start in list(code_parent.keys()):
            seen = set()
            node = start
            while node is not None and node in code_parent:
                if node in seen:
                    cur.execute("update code_name set supercid=null where cid=?", [node])
                    code_parent[node] = None
                    code_changed = True
                    break
                seen.add(node)
                node = code_parent[node]
        if cat_changed or code_changed:
            self.app.conn.commit()
            self.ui.textEdit.append(_("Repaired a cyclic code/category hierarchy."))
        # Vacuum database
        cur.execute("vacuum")
        self.app.conn.commit()
        
        # Update coder_names table and current coder in project
        self.app.update_coder_names()
        cur.execute('update project set codername=?', [self.app.settings['codername']])
        self.app.conn.commit()
        
        # Fix missing folders within QualCoder project. Otherwise, will cause import errors.
        span = '<span style="color:red">'
        end_span = "</span>"
        documents_folder = Path(self.app.project_path) / "documents"
        documents_folder.mkdir(exist_ok=True)
        audio_folder = Path(self.app.project_path) / "audio"
        audio_folder.mkdir(exist_ok=True)
        images_folder = Path(self.app.project_path) / "images"
        images_folder.mkdir(exist_ok=True)
        video_folder = Path(self.app.project_path) / "video"
        video_folder.mkdir(exist_ok=True)

        # Save a date and 24 hour stamped backup
        if self.app.settings['backup_on_open'] == 'True' and newproject == "no":
            msg, backup_name = self.app.save_backup()
            self.ui.textEdit.append(msg)
        # AI: init llm and update vectorstore after backup to avoid locked sqlite sidecar files.
        self.app.ai.init_llm(self)
        self.ai_chat_window.init_ai_chat(self.app)
        msg = f"{_('Project Opened: ')}{self.app.project_name}"
        self.ui.textEdit.append(msg)
        self.project_summary_report()
        self.show_menu_options()

    def project_summary_report(self):
        """ Add a summary of the project to the text edit.
         Display project memo, and code, attribute, journal, files frequencies.
         Also detect and display bad links to linked files. """

        if self.app.conn is None:
            return
        cur = self.app.conn.cursor()
        cur.execute("select databaseversion, date, memo, about, bookmarkfile,bookmarkpos,avbookmarkfile,avbookmarkmsec,avbookmarktextpos from project")
        result = cur.fetchall()[-1]
        self.project['databaseversion'] = result[0]
        self.project['date'] = result[1]
        self.project['memo'] = result[2]
        self.ui.textEdit.append("<br />")
        self.ui.textEdit.append("<h1>" + _("Project summary") + "</h1>")
        msg = f"<p>{self.app.project_name}<br />"
        msg += f'{_("Project path: ")}{self.app.project_path}<br />'
        msg += f"{_('Project date: ')}{self.project['date']}<br />"
        sql = "select memo from project"
        cur.execute(sql)
        memo_res = cur.fetchone()
        if memo_res[0] != "":
            msg += _("Project memo: ") + f"<br /><i>{memo_res[0]}</i><br />▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔<br />"
        sql = "select count(id) from source"
        cur.execute(sql)
        files_res = cur.fetchone()
        text_res = self.app.get_text_filenames()
        image_res = self.app.get_image_filenames()
        av_res = self.app.get_av_filenames()
        msg += _("Files: ") + f"{files_res[0]} | Text files: {len(text_res)} | Image files: {len(image_res)} | AV files: {len(av_res)}<br />"
        sql = "select count(caseid) from cases"
        cur.execute(sql)
        res = cur.fetchone()
        msg += f"{_('Cases: ')}{res[0]} | "
        sql = "select count(catid) from code_cat"
        cur.execute(sql)
        res = cur.fetchone()
        msg += f"{_('Code categories: ')}{res[0]} | "
        sql = "select count(cid) from code_name"
        cur.execute(sql)
        res = cur.fetchone()
        msg += f"{_('Codes: ')}{res[0]}<br />"
        sql = "select count(name) from attribute_type"
        cur.execute(sql)
        res = cur.fetchone()
        msg += f"{_('Attributes: ')}{res[0]} | "
        sql = "select count(jid) from journal"
        cur.execute(sql)
        res = cur.fetchone()
        msg += f"{_('Journals: ')}{res[0]}<br />"
        cur.execute("select name from source where id=?", [result[4]])
        bookmark_filename = cur.fetchone()
        if bookmark_filename is not None and result[5] is not None:
            msg += f"Text Bookmark: {bookmark_filename[0]}, position: {result[5]}<br />"
        cur.execute("select name from source where id=?", [result[6]])
        avbookmark_filename = cur.fetchone()
        if avbookmark_filename is not None and result[6] is not None:
            msg += f"A/V Bookmark: {avbookmark_filename[0]}, Milliseconds: {result[7]}, Text position: {result[8]}<br />"
        bad_links = self.app.check_bad_file_links()
        if bad_links:
            span = '<span style="color:red">'
            #self.ui.textEdit.append(span + _("Bad links to files") + "</span>")
            msg += span + _("Bad links to files") + "</span><br />"
            for lnk in bad_links:
                #self.ui.textEdit.append(span + lnk['name'] + "   " + lnk['mediapath'] + '</span><br />')
                msg += span + lnk['name'] + "   " + lnk['mediapath'] + '</span><br />'
            self.ui.actionManage_bad_links_to_files.setEnabled(True)
        else:
            self.ui.actionManage_bad_links_to_files.setEnabled(False)
        msg += "▔" * 20 + "</p>"
        self.ui.textEdit.append(msg)
        self.ui.tabWidget.setCurrentWidget(self.ui.tab_action_log)
        self.ui.textEdit.verticalScrollBar().setValue(self.ui.textEdit.verticalScrollBar().maximum())

    def close_project(self):
        """ Close an open project.
        Remove widgets from tabs, clear dialog list. Close app connection.
        Delete old backups. Hide menu options. """

        self.journal_display = None
        for tab_widget in (self.ui.tab_reports, self.ui.tab_coding, self.ui.tab_manage):
            self.clear_tab_widgets(tab_widget, show_placeholder=True)
        # Added if statement for the first opening of QualCoder. Looks odd closing a project that is not there.
        if self.app.project_name != "":
            self.ui.textEdit.append(_("Closing project: ") + self.app.project_name +"\n" + "▔" * 20 + "\n")
            self.app.append_recent_project(self.app.project_path)
        # AI
        self.ai_chat_window.close()
        self.app.ai.close()
        
        if self.app.conn is not None:
            try:
                self.app.conn.commit()
                self.app.conn.close()
            except Exception as e_:  # TODO add specific exception
                print(e_)
                logger.warning(e_)
                self.app.conn = None
        self.delete_backup_folders()
        self.fill_recent_projects_menu_actions()
        self.app.conn = None
        self.app.project_path = ""
        self.app.project_name = ""
        self.app.delete_backup_path_name = ""
        self.app.delete_backup = True
        self.project = {"databaseversion": "", "date": "", "memo": "", "about": ""}
        self.hide_menu_options()
        self.setWindowTitle("QualCoder")
        self.app.write_config_ini(self.app.settings, self.app.ai_models)
        self.ui.tabWidget.setCurrentWidget(self.ui.tab_action_log)
        self.ui.textEdit.verticalScrollBar().setValue(self.ui.textEdit.verticalScrollBar().maximum())

    def delete_backup_folders(self):
        """ Delete the most current backup created on opening a project,
        providing the project was not changed in any way.
        Delete the oldest backups if more than BACKUP_NUM are created.
        Backup name format: directories/projectname_BKUP_yyyymmdd_hh.qda
        Requires: self.settings['backup_num'] """

        if self.app.project_path == "" or not Path(self.app.project_path).exists():
            return
        if self.app.delete_backup_path_name != "" and self.app.delete_backup:
            try:
                shutil.rmtree(self.app.delete_backup_path_name)
            except Exception as err:
                print(str(err))
                logger.warning(str(err))
        # Get a list of backup folders for current project
        parts = self.app.project_path.split('/')
        project_name_and_suffix = parts[-1]
        directory = self.app.project_path[0:-len(project_name_and_suffix)]
        project_name = project_name_and_suffix[:-4]
        project_name_and_bkup = project_name + "_BKUP_"
        lenname = len(project_name_and_bkup)
        files_folders = os.listdir(directory)
        backups = []
        for f_ in files_folders:
            if f_[0:lenname] == project_name_and_bkup and f_[-4:] == ".qda":
                backups.append(f_)
        # Sort newest to oldest, and remove any that are more than BACKUP_NUM position in the list
        backups.sort(reverse=True)
        to_remove = []
        if len(backups) > self.app.settings['backup_num']:
            to_remove = backups[self.app.settings['backup_num']:]
        if not to_remove:
            return
        for f_ in to_remove:
            try:
                shutil.rmtree(directory + f_)
                self.ui.textEdit.append(_("Deleting: ") + directory + f_)
            except Exception as err:
                print(str(err))
                logger.warning(str(err))

    # AI Menu Actions
    def ai_setup_wizard(self):
        """Action triggered by AI Setup Wizard menu item or at the first start of QualCoder."""
        if self.app.settings['ai_enable'] == 'True':
            msg = _('The AI is setup and enabled, so there is nothing to do here. '
                    'Go to AI > settings to change the current model or other settings.')
            Message(self.app, _('AI Setup Wizard'), msg).exec() 
            return
        self.ui.textEdit.append(_('AI: Setup Wizard'))
        QtWidgets.QApplication.processEvents()  # update ui
        self.app.ai.init_llm(self, rebuild_vectorstore=False, enable_ai=True)
        self._show_pending_ai_model_upgrade_offer()
        self.update_ai_menu_options()
        self.ai_chat_window.refresh_placeholder_if_visible()
        self.ui.textEdit.append(_('AI: Setup Wizard finished'))
        if self.app.settings['ai_enable'] == 'True':
            ai_status = self.app.ai.get_status()
            if ai_status == 'reading data':
                msg = _('The AI setup is complete. The AI is now reading your project data in the background.')
            elif ai_status == 'ready':
                msg = _('The AI setup is complete and the AI is ready to use.')
            else:
                msg = _('The AI setup is complete.')
            Message(self.app, _('AI Setup Wizard'), msg).exec()
        
    def ai_settings(self):
        """ Action triggered by AI Settings menu item."""
        self.change_settings(section='AI')

    def ai_rebuild_memory(self):
        """ Action triggered by AI Rebuild Internal Memory menu item."""
        if self.app.settings['ai_enable'] != 'True':
            msg = _('Please enable the AI first and set it in Settings.')
            Message(self.app, _('Rebuild AI Memory'), msg).exec() 
            return
        if not self.app.ai.is_ready():
            msg = _('The AI is busy or not set up correctly.')
            Message(self.app, _('Rebuild AI Memory'), msg).exec()
            return 
        
        msg = _('This will re-read all of your empirical documents, which may take some time. Do you want to continue?')
        mb = QtWidgets.QMessageBox(self)
        mb.setWindowTitle(_('Rebuild AI Memory'))
        mb.setText(msg)
        mb.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Ok |
                            QtWidgets.QMessageBox.StandardButton.Abort)
        mb.setStyleSheet(f'* {{font-size: {self.app.settings["fontsize"]}pt}}')
        if mb.exec() == QtWidgets.QMessageBox.StandardButton.Ok: 
            self.ui.tabWidget.setCurrentIndex(0)  # Show action log
            self.app.ai.sources_vectorstore.init_vectorstore(rebuild=True)
    
    def ai_prompts(self, initial_prompt_name: str = "", initial_prompt_scope: str = ""):
        """ Action triggered by AI Prompts menu item."""
        DialogAiEditPrompts(
            self.app,
            initial_prompt_name=initial_prompt_name,
            initial_prompt_scope=initial_prompt_scope,
        ).exec()

    def ai_go_chat(self):
        """Action triggered by AI Agent menu item."""
        if self.app.settings['ai_enable'] != 'True':
            msg = _('Please enable the AI first and set it up in Settings.')
            Message(self.app, _('AI Agent'), msg).exec()
            return
        if self.ai_chat_sidebar_mode:
            self.set_ai_chat_sidebar_mode(True, persist=False)
        else:
            self.set_ai_chat_sidebar_mode(False, persist=False)
            self.ui.tabWidget.setCurrentWidget(self.ui.tab_ai_agent)

    def ai_go_analysis(self) -> None:
        """Start the AI analysis selected in the Analysis menu."""

        if self.ai_chat_window is None:
            return
        handlers = {
            self.ui.actionAI_topic_exploration: (self.ai_chat_window.new_topic_exploration, True),
            self.ui.actionAI_text_analysis: (self.ai_chat_window.new_text_analysis, False),
            self.ui.actionAI_code_analysis: (self.ai_chat_window.new_code_analysis, True),
        }
        selected_handler = handlers.get(self.sender())
        if selected_handler is None:
            logger.warning("Unknown AI analysis menu action")
            return
        handler, show_ai_agent = selected_handler
        if show_ai_agent:
            self.set_ai_chat_sidebar_mode(False, persist=False)
            self.ui.tabWidget.setCurrentWidget(self.ui.tab_ai_agent)
        handler()

    def ai_check_project_readiness(self) -> None:
        """Start an AI Agent chat that assesses the current project."""

        if self.ai_chat_window is None:
            return
        self.set_ai_chat_sidebar_mode(False, persist=False)
        self.ui.tabWidget.setCurrentWidget(self.ui.tab_ai_agent)
        self.ai_chat_window.new_project_ai_readiness_chat()

    def ai_go_help_support(self):
        """Action triggered by Help > Ask the AI Agent."""

        if self.app.settings['ai_enable'] != 'True':
            msg = _('Please enable the AI first and set it up in Settings.')
            Message(self.app, _('AI Agent'), msg).exec()
            return
        if self.ai_chat_sidebar_mode:
            self.set_ai_chat_sidebar_mode(True, persist=False)
        else:
            self.set_ai_chat_sidebar_mode(False, persist=False)
            self.ui.tabWidget.setCurrentWidget(self.ui.tab_ai_agent)
        self.ai_chat_window.new_help_support_chat()

    def ai_go_search(self):
        """ Action triggered by AI Search and Coding menu item."""
        if self.app.settings['ai_enable'] != 'True':
            msg = _('Please enable the AI first and set it up in Settings.')
            Message(self.app, _('Rebuild AI Memory'), msg).exec() 
            return
        self.text_coding(task='ai_search')

    def get_latest_github_release(self):
        """ Get latest github release. Some issues on some platforms, so in try except. """

        self.ui.textEdit.append(_("This version: ") + self.app.version)
        if "beta" in self.app.version.lower():
            self.ui.textEdit.append(self.app.citation.split('Retrieved')[0])
            return
        try:
            _json = json.loads(urllib.request.urlopen(urllib.request.Request(
                'https://api.github.com/repos/ccbogel/QualCoder/releases/latest',
                headers={'Accept': 'application/vnd.github.v3+json'},
            )).read())
            release_version_number = _json['name'].split()[1]
            tmp_release_num = release_version_number.split('.', 1)
            release_num = float(tmp_release_num[0] + '.' + tmp_release_num[1].replace('.', ''))
            temp_this_version = self.app.version.replace("QualCoder", "")
            tmp_this_version_num = temp_this_version.split('.', 1)
            this_version_num = float(tmp_this_version_num[0] + '.' + tmp_this_version_num[1].replace('.', ''))
            if release_num > this_version_num:
                html = '<span style="color:red">' + _("Newer release available: ") + _json['name'] + '</span>'
                self.ui.textEdit.append(html)
                html = f'<span style="color:red">{_json["html_url"]}</span><br />'
                self.ui.textEdit.append(html)
            elif str(release_num) == str(this_version_num):
                self.ui.textEdit.append(_("Latest Release: ") + _json['name'])
                self.ui.textEdit.append(_json['html_url'] + "\n")
            else:
                self.ui.textEdit.append(_("This version may be a pre-release version."))
        except Exception as err:
            print(err)
            logger.warning(str(err))
        self.ui.textEdit.append(self.app.citation)

def gui():
    # print("Qt version: " + str(QtCore.qVersion()))
    # Return WM_CLASS as the same default from the standart .desktop on repo if the system is linux (i.e "QualCoder")
    if sys.platform in ["linux", "bsd"]: 
        QtWidgets.QApplication.setDesktopFileName("QualCoder")
    qual_app = App()
    settings = qual_app.settings
    ai_models = qual_app.ai_models
    project_path = qual_app.get_most_recent_projectpath()
    if platform.system() == "Windows" and settings.get('stylesheet') == "native":
        # Avoid early native Windows style initialization crashes in Qt before our later Fusion fallback runs.
        os.environ.setdefault("QT_STYLE_OVERRIDE", "Fusion")
    # Native video frame must not force sibling widgets native
    QtWidgets.QApplication.setAttribute(
        QtCore.Qt.ApplicationAttribute.AA_DontCreateNativeWidgetSiblings)
    app = QtWidgets.QApplication(sys.argv)
    app._qc_installed_translators = []
    # Noto Sans - for general application
    install_noto_sans()
    QtGui.QFontDatabase.addApplicationFont(str(qc_config_folder / "NotoSans-Regular.ttf"))
    # DroidSandMono - for wordcloud
    install_droid_sans_mono()
    stylesheet = qual_app.merge_settings_with_default_stylesheet(settings)
    app.setStyleSheet(stylesheet)
    qta.reset_cache()
    qta.set_defaults(
        color=qual_app.qtawesome_icon_color,
        color_disabled=qual_app.qtawesome_icon_color_disabled
    )
    if sys.platform != 'darwin':
        qualcoder32_icon = b'iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAIAAAD8GO2jAAAHlHpUWHRSYXcgcHJvZmlsZSB0eXBlIGV4aWYAAHja7ZdZkuS2DkX/uQovQRzAYTkkQUZ4B2/5PqAys7Kq2u52vP50KlKiOIDgvZjk1v/+3O4PfkHy5ZKUmlvOF7/UUgudRr3uXzt3f6VzP7/wGOL9U797DQS6Is94v5b+mN/pl48Fzz38+Nzv6mMk1Iegx8BTYLSdbTd9V5L+cPf79BDU1t3IrZZ3VcdD1fmYeFR5/GO5T/gUYu/uvSMVUFJhVgxhRR+vc6+3BtH+Pnb+dr9iZh5zTrs5HgGJtyYA8ul4z+d1vQP0CeRny31F/9X6An7oj/74Bcv8wIjGDwe8/Bj8A/HbxvGlUfg8MNuL4W8g761173WfrqcMovlhUZd7omNrmDiAPJ5lmavwF9rlXO2yTfo1IUeveQ2u6ZsPIL6dT15999uv85x+omIKKxSeIUyIsr4aS2hhRuMp2eV3KLFFjRWyZlguRrrDSxd/9m1nv+krO6tnavAI8yz528v90+C/udze0yDyV31hhV7BLBc1jDm7MwtC/H7wJgfg5/Wg/3qzH0wVBuXAXDlgv8YtYoj/sK14eI7ME563V3hX9CEAiNhbUAYXSP7KPorP/iohFO/BsUJQR/MQUxgw4EWComRIEW9xJdRge7Om+DM3SMjBuolNECExxwI3LXbISkmwn5IqNtQlShKRLEWqkyY9x5yy5JxLtiDXSyypSMmllFpa6TXWVKXmWmqtrfYWWiQGSsuttNpa6z24zkYdWZ35nZ4RRhxpyMijjDra6BPzmWnKzLPMOtvsGjQqYUKzFq3atC/vFpFipSUrr7LqaqtvbG3HnbbsvMuuu+3+Yu3B6rfrX7DmH6yFw5TNKy/W6HWlPEV4CydinMFYSB7GizGAQQfj7Ko+pWDMGWdXCziFBJQU48apN8agMC0fZPsXdx/M/RJvTuov8RZ+xpwz6n4Hcw7qvvP2A9bU8tw8jN1eaJheEe9jTg/V8b8ubv/v8z9Bv1MQpNbL7ITGmISkmaxjdS7e3KQO6cYhS8b0637BKAaXRJMTl/a+WhiLnL5zshk9r9ZkFZVZNI+rO5lb02o91rIxUsV8pE8WxIzkLtkvZcKu61q689hotTo+ERrOsQcmFzE4wkjGFWREpJckoaSOYMGQZfe2ppexZZlj9hFxF5a1Varfa5d1FZT2MqOW7IbMESqpOPZy0b2TeNyyUetY4/r0xPpjsoPtFtZnGAF7DOHkVjvuZt27z96yQZMmo2CBzwjD6zqLaIWhAcSVFyXugGV2XaQQLHeKukLLo2rfKfe1JY62lKbu7hvHpqoUEGx75E0i311L86t4GwlCFlER3wf+ymHJzEp9kI7CA9LYvKxhqjRKj5WIWnOWoSqDmAyg2XhZXZzpNaVrMr0GmUoOGK3NddCZdiYsh6riUL/9sLO9zrj61YfKIoskOFl9foEWYWlYq7ShZTYvhAstfjB9+3a2A3dwqRDstyMMqo3lpKTO3qd+SCtxyBL+q0nqg8AnkXDpVRKhfM0FeuvCWnITl4lwpZcStae1PBEPWzOLaokQCjRpt8mCbk6ChXLACKQISD3mqy+hE7ycbz2lZub5UnY0+6xQAw1dtVqK/2pR357uoBBAYWDwBSunRjNxt1iPWYsdpnAO2elHcjiMrOhYTqGAJ8C1TpztWqN7zJIjatglrtLMLKu5ntzGQw2iPW7VPQu1qV9g6dYUo7umVTAQw3ssMgTGx7vtstDmMnuo9Y2qVWRfttds6D0KRyttSz4qmgnIwqezxQ6VDL4RIBsGM74BIzsGBEUkRozYXaWGt502SJyG2k69/BO+n8S6/VjPY4d5oI/6FPx3T2xPJoZ32FDzQnUAQKTbxfpSMHsmGuqtOlOUQoSK+mxQ9UNzvGmz8FbButzPNn+trQMLS1rC0cOXD6lUEbM7xZXZL1cpyXzu4V8EPW+c5Vt/k4iZQRPkMz51P60I/REqDg3n09/kgmpjjgi7yP4fdrkWR4HP0lQt+nyH246Gv5Y2NTdfS/RD+Rac+6QBi5CzElSxz7hyxlKADm0tkMZACNQ+ic+EIncdt8QCKy4thnagSprDLMrqEZCZ8tlpKkqZLxkhVDEcb3h1IEE0fXed1iz+tDv+tHkgqfrNcBRELtsq2Qwhi+T8Ja12DpDHpOCivovNjoa2jehDQJ/hJIhE1CaW6MxxdpPuSGlJxyC6gEgpTdR2J3KUllUnVVabo9U7tiaqVfqxwPbOph3WTQs6LwDUwhHdpIBzTCWPPbPYSdRoWvqo5Vtp4E4DTE9OOImeNEeu33VaeCd0rkkNGU+uGAVoOsUgOZivxJFXv0HD+4mAJ21Qa2TcRy00Dr4ww7DdSduEaQQTc3IIY1Oj5novtvr5w/JfLlKiiIb75BEUKtxZLJiH35ksQ1LDCgTa+8Y8y5i3tV68OOoAJaTY+sBa8yYDKVnamcfF9NimP/KuYfKwjXkgnOQTA1UKrHEjx2r2aVAHNyI+SVQvy9RrUenkSIWRlaObv0KYeSWFOoWWWFBOw5PDh4u7NlzrZCvzCMjlRiQlkVE6PXIqH9o/Kevcbykg/xP0i4IiXz6NCPcXkG3wBnlTA/kAAAGFaUNDUElDQyBwcm9maWxlAAB4nH2RPUjDQBzFX1Nr/ag4WFDEIUN1siAq4qhVKEKFUCu06mBy6YfQpCFJcXEUXAsOfixWHVycdXVwFQTBDxA3NydFFynxf0mhRawHx/14d+9x9w4QqkWmWW1jgKbbZjIeE9OZFTH4im4E0I9OtMvMMmYlKYGW4+sePr7eRXlW63N/jh41azHAJxLPMMO0ideJpzZtg/M+cZgVZJX4nHjUpAsSP3Jd8fiNc95lgWeGzVRyjjhMLOabWGliVjA14kniiKrplC+kPVY5b3HWimVWvyd/YSirLy9xneYQ4ljAIiSIUFDGBoqwEaVVJ8VCkvZjLfyDrl8il0KuDTByzKMEDbLrB/+D391auYlxLykUAwIvjvMxDAR3gVrFcb6PHad2AvifgSu94S9VgelP0isNLXIE9G4DF9cNTdkDLneAgSdDNmVX8tMUcjng/Yy+KQP03QJdq15v9X2cPgAp6ipxAxwcAiN5yl5r8e6O5t7+PVPv7wfz2XJ065JIMgAAF41pVFh0WE1MOmNvbS5hZG9iZS54bXAAAAAAADw/eHBhY2tldCBiZWdpbj0i77u/IiBpZD0iVzVNME1wQ2VoaUh6cmVTek5UY3prYzlkIj8+Cjx4OnhtcG1ldGEgeG1sbnM6eD0iYWRvYmU6bnM6bWV0YS8iIHg6eG1wdGs9IlhNUCBDb3JlIDQuNC4wLUV4aXYyIj4KIDxyZGY6UkRGIHhtbG5zOnJkZj0iaHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyI+CiAgPHJkZjpEZXNjcmlwdGlvbiByZGY6YWJvdXQ9IiIKICAgIHhtbG5zOmlwdGNFeHQ9Imh0dHA6Ly9pcHRjLm9yZy9zdGQvSXB0YzR4bXBFeHQvMjAwOC0wMi0yOS8iCiAgICB4bWxuczp4bXBNTT0iaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wL21tLyIKICAgIHhtbG5zOnN0RXZ0PSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvc1R5cGUvUmVzb3VyY2VFdmVudCMiCiAgICB4bWxuczpzdFJlZj0iaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wL3NUeXBlL1Jlc291cmNlUmVmIyIKICAgIHhtbG5zOnBsdXM9Imh0dHA6Ly9ucy51c2VwbHVzLm9yZy9sZGYveG1wLzEuMC8iCiAgICB4bWxuczpHSU1QPSJodHRwOi8vd3d3LmdpbXAub3JnL3htcC8iCiAgICB4bWxuczpkYz0iaHR0cDovL3B1cmwub3JnL2RjL2VsZW1lbnRzLzEuMS8iCiAgICB4bWxuczpleGlmPSJodHRwOi8vbnMuYWRvYmUuY29tL2V4aWYvMS4wLyIKICAgIHhtbG5zOnBob3Rvc2hvcD0iaHR0cDovL25zLmFkb2JlLmNvbS9waG90b3Nob3AvMS4wLyIKICAgIHhtbG5zOnRpZmY9Imh0dHA6Ly9ucy5hZG9iZS5jb20vdGlmZi8xLjAvIgogICAgeG1sbnM6eG1wPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvIgogICB4bXBNTTpEb2N1bWVudElEPSJhZG9iZTpkb2NpZDpwaG90b3Nob3A6ZWU1YjRlNWUtNGU1MS02NzRkLTk1ZDItNTIwMzA3YWQ0MWFhIgogICB4bXBNTTpJbnN0YW5jZUlEPSJ4bXAuaWlkOmJjMTRjZDA2LTQzYzItNDBhOS1iOGExLWY3NjZjMGI0NzVkMSIKICAgeG1wTU06T3JpZ2luYWxEb2N1bWVudElEPSJ4bXAuZGlkOmE1ZTMzYzY4LTAyNGEtNzk0MS05N2VmLWZhN2NjODExODdlOSIKICAgR0lNUDpBUEk9IjIuMCIKICAgR0lNUDpQbGF0Zm9ybT0iTGludXgiCiAgIEdJTVA6VGltZVN0YW1wPSIxNjM2MTUzNzY5NTY3OTIyIgogICBHSU1QOlZlcnNpb249IjIuMTAuMTgiCiAgIGRjOkZvcm1hdD0iaW1hZ2UvcG5nIgogICBleGlmOlBpeGVsWERpbWVuc2lvbj0iNTEyIgogICBleGlmOlBpeGVsWURpbWVuc2lvbj0iNTEyIgogICBwaG90b3Nob3A6Q29sb3JNb2RlPSIzIgogICB0aWZmOk9yaWVudGF0aW9uPSIxIgogICB0aWZmOlJlc29sdXRpb25Vbml0PSIyIgogICB0aWZmOlhSZXNvbHV0aW9uPSI3MjAwMDAvMTAwMDAiCiAgIHRpZmY6WVJlc29sdXRpb249IjcyMDAwMC8xMDAwMCIKICAgeG1wOkNyZWF0ZURhdGU9IjIwMjEtMTEtMDVUMTE6MzU6NDkrMDE6MDAiCiAgIHhtcDpDcmVhdG9yVG9vbD0iR0lNUCAyLjEwIgogICB4bXA6TWV0YWRhdGFEYXRlPSIyMDIxLTExLTA1VDEyOjM0OjMxKzAxOjAwIgogICB4bXA6TW9kaWZ5RGF0ZT0iMjAyMS0xMS0wNVQxMjozNDozMSswMTowMCI+CiAgIDxpcHRjRXh0OkxvY2F0aW9uQ3JlYXRlZD4KICAgIDxyZGY6QmFnLz4KICAgPC9pcHRjRXh0OkxvY2F0aW9uQ3JlYXRlZD4KICAgPGlwdGNFeHQ6TG9jYXRpb25TaG93bj4KICAgIDxyZGY6QmFnLz4KICAgPC9pcHRjRXh0OkxvY2F0aW9uU2hvd24+CiAgIDxpcHRjRXh0OkFydHdvcmtPck9iamVjdD4KICAgIDxyZGY6QmFnLz4KICAgPC9pcHRjRXh0OkFydHdvcmtPck9iamVjdD4KICAgPGlwdGNFeHQ6UmVnaXN0cnlJZD4KICAgIDxyZGY6QmFnLz4KICAgPC9pcHRjRXh0OlJlZ2lzdHJ5SWQ+CiAgIDx4bXBNTTpIaXN0b3J5PgogICAgPHJkZjpTZXE+CiAgICAgPHJkZjpsaQogICAgICBzdEV2dDphY3Rpb249ImNyZWF0ZWQiCiAgICAgIHN0RXZ0Omluc3RhbmNlSUQ9InhtcC5paWQ6YTVlMzNjNjgtMDI0YS03OTQxLTk3ZWYtZmE3Y2M4MTE4N2U5IgogICAgICBzdEV2dDpzb2Z0d2FyZUFnZW50PSJBZG9iZSBQaG90b3Nob3AgQ0MgKFdpbmRvd3MpIgogICAgICBzdEV2dDp3aGVuPSIyMDIxLTExLTA1VDExOjM1OjQ5KzAxOjAwIi8+CiAgICAgPHJkZjpsaQogICAgICBzdEV2dDphY3Rpb249ImNvbnZlcnRlZCIKICAgICAgc3RFdnQ6cGFyYW1ldGVycz0iZnJvbSBpbWFnZS9wbmcgdG8gYXBwbGljYXRpb24vdm5kLmFkb2JlLnBob3Rvc2hvcCIvPgogICAgIDxyZGY6bGkKICAgICAgc3RFdnQ6YWN0aW9uPSJzYXZlZCIKICAgICAgc3RFdnQ6Y2hhbmdlZD0iLyIKICAgICAgc3RFdnQ6aW5zdGFuY2VJRD0ieG1wLmlpZDo0NTJhODhhNi1iYWVjLTgzNDktODZjNy0xMWM0NWVmY2IyNDEiCiAgICAgIHN0RXZ0OnNvZnR3YXJlQWdlbnQ9IkFkb2JlIFBob3Rvc2hvcCBDQyAoV2luZG93cykiCiAgICAgIHN0RXZ0OndoZW49IjIwMjEtMTEtMDVUMTI6MjQ6MTMrMDE6MDAiLz4KICAgICA8cmRmOmxpCiAgICAgIHN0RXZ0OmFjdGlvbj0ic2F2ZWQiCiAgICAgIHN0RXZ0OmNoYW5nZWQ9Ii8iCiAgICAgIHN0RXZ0Omluc3RhbmNlSUQ9InhtcC5paWQ6MDU3OGM4ZTMtYjllNC03ZjRiLWEyOGMtYWExNmYzOGJmZjA5IgogICAgICBzdEV2dDpzb2Z0d2FyZUFnZW50PSJBZG9iZSBQaG90b3Nob3AgQ0MgKFdpbmRvd3MpIgogICAgICBzdEV2dDp3aGVuPSIyMDIxLTExLTA1VDEyOjM0OjMxKzAxOjAwIi8+CiAgICAgPHJkZjpsaQogICAgICBzdEV2dDphY3Rpb249ImNvbnZlcnRlZCIKICAgICAgc3RFdnQ6cGFyYW1ldGVycz0iZnJvbSBhcHBsaWNhdGlvbi92bmQuYWRvYmUucGhvdG9zaG9wIHRvIGltYWdlL3BuZyIvPgogICAgIDxyZGY6bGkKICAgICAgc3RFdnQ6YWN0aW9uPSJkZXJpdmVkIgogICAgICBzdEV2dDpwYXJhbWV0ZXJzPSJjb252ZXJ0ZWQgZnJvbSBhcHBsaWNhdGlvbi92bmQuYWRvYmUucGhvdG9zaG9wIHRvIGltYWdlL3BuZyIvPgogICAgIDxyZGY6bGkKICAgICAgc3RFdnQ6YWN0aW9uPSJzYXZlZCIKICAgICAgc3RFdnQ6Y2hhbmdlZD0iLyIKICAgICAgc3RFdnQ6aW5zdGFuY2VJRD0ieG1wLmlpZDo1ZGM3ZDg0Ny1kNGRhLTk1NGUtYTQ0NC00NzhmOGVhZjY3MDEiCiAgICAgIHN0RXZ0OnNvZnR3YXJlQWdlbnQ9IkFkb2JlIFBob3Rvc2hvcCBDQyAoV2luZG93cykiCiAgICAgIHN0RXZ0OndoZW49IjIwMjEtMTEtMDVUMTI6MzQ6MzErMDE6MDAiLz4KICAgICA8cmRmOmxpCiAgICAgIHN0RXZ0OmFjdGlvbj0ic2F2ZWQiCiAgICAgIHN0RXZ0OmNoYW5nZWQ9Ii8iCiAgICAgIHN0RXZ0Omluc3RhbmNlSUQ9InhtcC5paWQ6YzJlMmQyMmEtZWUyNy00MTEzLTg0OTQtYTRhZDYzMjhkOTBmIgogICAgICBzdEV2dDpzb2Z0d2FyZUFnZW50PSJHaW1wIDIuMTAgKExpbnV4KSIKICAgICAgc3RFdnQ6d2hlbj0iKzExOjAwIi8+CiAgICA8L3JkZjpTZXE+CiAgIDwveG1wTU06SGlzdG9yeT4KICAgPHhtcE1NOkRlcml2ZWRGcm9tCiAgICBzdFJlZjpkb2N1bWVudElEPSJhZG9iZTpkb2NpZDpwaG90b3Nob3A6N2YxMDM5N2ItZTBmZi05NzRlLThkMjktY2VmZDU3MGFiNDFiIgogICAgc3RSZWY6aW5zdGFuY2VJRD0ieG1wLmlpZDowNTc4YzhlMy1iOWU0LTdmNGItYTI4Yy1hYTE2ZjM4YmZmMDkiCiAgICBzdFJlZjpvcmlnaW5hbERvY3VtZW50SUQ9InhtcC5kaWQ6YTVlMzNjNjgtMDI0YS03OTQxLTk3ZWYtZmE3Y2M4MTE4N2U5Ii8+CiAgIDxwbHVzOkltYWdlU3VwcGxpZXI+CiAgICA8cmRmOlNlcS8+CiAgIDwvcGx1czpJbWFnZVN1cHBsaWVyPgogICA8cGx1czpJbWFnZUNyZWF0b3I+CiAgICA8cmRmOlNlcS8+CiAgIDwvcGx1czpJbWFnZUNyZWF0b3I+CiAgIDxwbHVzOkNvcHlyaWdodE93bmVyPgogICAgPHJkZjpTZXEvPgogICA8L3BsdXM6Q29weXJpZ2h0T3duZXI+CiAgIDxwbHVzOkxpY2Vuc29yPgogICAgPHJkZjpTZXEvPgogICA8L3BsdXM6TGljZW5zb3I+CiAgPC9yZGY6RGVzY3JpcHRpb24+CiA8L3JkZjpSREY+CjwveDp4bXBtZXRhPgogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAKICAgICAgICAgICAgICAgICAgICAgICAgICAgCjw/eHBhY2tldCBlbmQ9InciPz7mcyShAAAACXBIWXMAAAsTAAALEwEAmpwYAAAAB3RJTUUH5QsFFwkdYf6D1wAAA2NJREFUSMftVl9IU1EYP7fd1VX8y8r/yMAtcoWDwGES5EAoTGeUkFGSrD0k+rKRCQ7qRV+ESkEMQXQPqSAo+K8xZuGQ8s9Q9CpqugkhUyduNtfm5p07PUyOh+t0+iC9+OM83Hu+7/f9zvnu+b5zCQghOE9cAueMC4H/L0AGnTWZTLOzszMzM16vFwDA5XLFYnFGRoZAICAIwu/bt61s2pY3HSvbft8+ACCKHxubdvXa9UQuxWWFIljH1GQyNTQ0NDY2BhVWKBQvH7/wfLV71z1HrZwoMu2ZKE164xLJCS4wODiYn58fctfK269z+Hc5RPD0Rt6MkbzJoSLD2AJ9fX2FhYXILzMzUy6XJycnEwSxtrbW0dFhMBiQtUL86lFOQVx2EhnG9fv8mxNr7mUnsoYLI7PVuVciKAAAgBBCCBcXF/FVaDSa3d1diGFvb0+r1eI+BoMBd9iYt+jLewaedATG6KdvgXkAIfT5fAqFAjF7enrgMZicnERuEonE7XbjVve2C9ewTP8+EJibm0M0lUrl9/vh8Whvb0fOQ0NDLKt1wYIERmp1BwLNzc2IMzU1BU+E3W5HzlVVVTAUAIRQLpcjjtPpDMnB8xnSmQQAtLa2IoLD4TAajVarlWEYiqIEAkF6ejpFUfjnjY+PR882m43H452hklNSUlgzEomkpqZGKpWSJIlWfVhHBBGiaiCExcXFIYtLrVbv7OwEdi2TyU6fIgAhbGpqQgSRSFRXV9fV1dXZ2alSqXCNkpKS9fX1hYUFNFNZWXkqgenpacSprq7GzVtbW/X19Xi6SktL0ater2eF+2Ox//wwFBhTmh8HAgzD4Fnq7e1l0fr7+48mLSsri1VoXpdnWD2A6mBl5NeBAIRwfn4eJ7e0tLhcLpys0+lYAuPj47iDc9NheDeIon9/2+fzMhDCw2bX3d1dVFSE+Hw+X6lU8vl8DodjsVja2trGxsZwgfLyctmDgoSkhPC/lx3Ltg3t6mHfjiTv1OZGJ8Wy2zWroZ4SXx5+jqGiDw9+NFfyXhqbygtyZcpksqWlpYqKiuNilZWVDQ8Pn3CsE/NS733MQ9GD3GgBmM1mmqZpmvZ4PPiVKRQKAQAMw9A0bRydMC+ZV/Xm5/efxgkSeKL4hFvJEXFRIa7Mi9+WC4Gz4x8imSOgwBMa1AAAAABJRU5ErkJggg=='
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(qualcoder32_icon), "png")
        app.setWindowIcon(QtGui.QIcon(pm))

    lang = settings.get('language', 'en')
    translator = gettext.NullTranslations()
    startup_language_error = None
    if lang != 'en':
        zip_sync_error = None
        try:
            qual_app.sync_current_language_zip(lang)
        except Exception as err:
            print(err)
            logger.error(err)
            zip_sync_error = err
        qm_path = qual_app.get_language_file_path(lang, 'qm')
        mo_path = qual_app.get_language_file_path(lang, 'mo')
        try:
            if qm_path is None or mo_path is None:
                raise FileNotFoundError(f"Missing translation files for language '{lang}'")
            qt_translator = QtCore.QTranslator()
            if not qt_translator.load(qm_path):
                raise RuntimeError(f"Could not load Qt translation file: {qm_path}")
            with open(mo_path, 'rb') as file_:
                translator = gettext.GNUTranslations(file_)
            app.installTranslator(qt_translator)
            app._qc_installed_translators.append(qt_translator)

            qt_translations_path = QtCore.QLibraryInfo.path(QtCore.QLibraryInfo.LibraryPath.TranslationsPath)
            qt_base_candidates = [f"qtbase_{lang}"]
            locale_name = QtCore.QLocale(lang).name()
            if locale_name:
                qt_base_candidates.append(f"qtbase_{locale_name}")
            qt_base_candidates = list(dict.fromkeys(qt_base_candidates))
            qt_base_translator = QtCore.QTranslator()
            qt_base_loaded = False
            for candidate in qt_base_candidates:
                if qt_base_translator.load(candidate, qt_translations_path):
                    app.installTranslator(qt_base_translator)
                    app._qc_installed_translators.append(qt_base_translator)
                    qt_base_loaded = True
                    break
            if not qt_base_loaded:
                logger.warning(
                    f"No Qt base translation found for language '{lang}' in '{qt_translations_path}'"
                )
        except Exception as err:
            print(err)
            logger.error(err)
            translator = gettext.NullTranslations()
            details = f'{type(err).__name__}: {err}'
            if zip_sync_error is not None:
                details = f'{type(zip_sync_error).__name__}: {zip_sync_error}\n{details}'
            startup_language_error = (
                f'The configured language "{lang}" could not be loaded.\n'
                'QualCoder will start in English.\n\n'
                f'{details}'
            )

    translator.install()
    if startup_language_error is not None:
        Message(qual_app, "Translation error", startup_language_error, "warning").exec()

    ex = MainWindow(qual_app)
    try:
        if project_path:
            split_ = project_path.split("|")
            proj_path = ""
            # Only the path - legacy format
            if len(split_) == 1:
                proj_path = split_[0]
            # Newer datetime | path
            if len(split_) == 2:
                proj_path = split_[1]
            ex.open_project(path_=proj_path)
    except Exception as err:
        type_e = type(err)
        value = err
        tb_obj = err.__traceback__
        # log the exception and show error msg
        qt_exception_hook.exception_hook(type_e, value, tb_obj)

    exit_code = app.exec()
    app.processEvents()
    QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
    app.processEvents()
    return exit_code


def install_droid_sans_mono():
    """ Install DroidSansMono ttf font for wordclouds into .qualcoder folder """

    qc_folder = qc_config_folder / 'DroidSansMono.ttf'
    with open(qc_folder, 'wb') as file_:
        decoded_data = base64.decodebytes(DroidSansMono)
        file_.write(decoded_data)


def install_noto_sans():
    """ Install NotoSans ttf font for general application into .qualcoder folder """

    qc_folder = qc_config_folder / 'NotoSans-Regular.ttf'
    with open(qc_folder, 'wb') as file_:
        decoded_data = base64.decodebytes(NotoSans)
        file_.write(decoded_data)


if __name__ == "__main__":
    # Pyinstaller fix
    multiprocessing.freeze_support()
    sys.exit(gui())
