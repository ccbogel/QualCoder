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

Author: Colin Curtain (ccbogel)
https://github.com/ccbogel/QualCoder
https://qualcoder-org.github.io
https://qualcoder.wordpress.com/
https://qualcoder.org/
"""

import json
import logging
import os

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt
import qtawesome as qta
from .GUI.ui_dialog_node_relations import Ui_Dialog_node_relations

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

import builtins
if not hasattr(builtins, '_'):
    def _(txt):
        return txt

# DEFAULT RELATION FRAMEWORKS
DEFAULT_FRAMEWORKS = {
    "Grounded Theory (Strauss & Corbin)": {
        "description": "Relations derived from Strauss & Corbin's axial coding paradigm model. "
                       "Used during open, axial, and selective coding to articulate the structure "
                       "around a central phenomenon.",
        "relations": [
            {"name": "(No label)",
             "definition": "Connection without a named relation type.",
             "comments": ""},
            {"name": "is condition for",
             "definition": "A causal, intervening, or contextual condition that influences the phenomenon.",
             "comments": "Axial coding: conditions → phenomenon."},
            {"name": "is strategy for",
             "definition": "An action/interaction strategy used in response to or to manage the phenomenon.",
             "comments": "Axial coding: phenomenon → strategies."},
            {"name": "is consequence of",
             "definition": "A result or outcome that follows from action/interaction strategies.",
             "comments": "Axial coding: strategies → consequences."},
            {"name": "is context for",
             "definition": "The set of conditions within which strategies are enacted.",
             "comments": "Narrow situational conditions."},
            {"name": "intervenes in",
             "definition": "A broader structural condition that facilitates or constrains strategies.",
             "comments": "Intervening conditions in paradigm model."},
            {"name": "is central phenomenon",
             "definition": "The core category or central idea to which all other categories relate.",
             "comments": "Identified during selective coding."},
            {"name": "is dimension of",
             "definition": "A property varies along this continuum or range.",
             "comments": "Properties and dimensions of categories."},
            {"name": "is subcategory of",
             "definition": "One category is subsumed under or elaborates a higher-order category.",
             "comments": "Hierarchical abstraction."},
            {"name": "is associated with",
             "definition": "Two concepts co-occur without specified directionality.",
             "comments": "Open coding: provisional link."},
            {"name": "leads to",
             "definition": "A processual or temporal link between phases.",
             "comments": "Process coding: sequential stages."},
        ]
    },
    "Qualitative Content Analysis (Mayring)": {
        "description": "Relations for structuring deductive and inductive category systems "
                       "following Mayring's systematic approach to qualitative content analysis.",
        "relations": [
            {"name": "(No label)",
             "definition": "Connection without a named relation type.",
             "comments": ""},
            {"name": "is main category of",
             "definition": "A superordinate category that organizes subcategories.",
             "comments": "Deductive: from theory. Inductive: from data."},
            {"name": "is subcategory of",
             "definition": "A subordinate category under a main category.",
             "comments": "Hierarchical nesting."},
            {"name": "is anchor example for",
             "definition": "A prototypical text passage that defines a category.",
             "comments": "Anchor examples fix category meaning."},
            {"name": "is coding rule for",
             "definition": "A decision rule that resolves ambiguity between categories.",
             "comments": "Delineates category boundaries."},
            {"name": "overlaps with",
             "definition": "Two categories share some coded segments or meaning.",
             "comments": "Signals need for coding rule refinement."},
            {"name": "refines",
             "definition": "One category is a more precise version of another after revision.",
             "comments": "Used during iterative category revision."},
            {"name": "contradicts",
             "definition": "Two categories or findings are in tension.",
             "comments": "Analytically productive tensions."},
            {"name": "summarizes",
             "definition": "One category captures the gist of several lower-level categories.",
             "comments": "Summarizing content analysis."},
            {"name": "explicates",
             "definition": "One category clarifies the meaning of another through context.",
             "comments": "Explicating content analysis."},
            {"name": "structures",
             "definition": "One category provides the organizing frame for others.",
             "comments": "Structuring content analysis."},
        ]
    },
    "Phenomenology (Moustakas / van Manen)": {
        "description": "Relations for articulating the structure of lived experience, "
                       "following Moustakas' transcendental phenomenology and van Manen's "
                       "hermeneutic phenomenology.",
        "relations": [
            {"name": "(No label)",
             "definition": "Connection without a named relation type.",
             "comments": ""},
            {"name": "is textural description of",
             "definition": "Describes WHAT was experienced (the noema).",
             "comments": "Moustakas: textural = content of experience."},
            {"name": "is structural description of",
             "definition": "Describes HOW the experience was lived (the noesis).",
             "comments": "Moustakas: structural = conditions/context."},
            {"name": "is essence of",
             "definition": "The invariant meaning that persists across individual experiences.",
             "comments": "Composite textural-structural description."},
            {"name": "is horizon of",
             "definition": "A meaning unit that bounds or delimits the experience.",
             "comments": "Horizonalization: each statement has equal value."},
            {"name": "is theme of",
             "definition": "An experiential structure that recurs across participants.",
             "comments": "van Manen: existential themes."},
            {"name": "is embodied in",
             "definition": "The experience manifests through bodily sensation or corporeal presence.",
             "comments": "Lived body (corporeality)."},
            {"name": "is situated in",
             "definition": "The experience occurs within a specific spatial context.",
             "comments": "Lived space (spatiality)."},
            {"name": "is temporalized as",
             "definition": "The experience unfolds within subjective time.",
             "comments": "Lived time (temporality)."},
            {"name": "is relational to",
             "definition": "The experience involves connection with others.",
             "comments": "Lived relation (relationality)."},
            {"name": "constitutes",
             "definition": "One meaning unit participates in constructing a broader theme.",
             "comments": "Phenomenological constitution."},
        ]
    },
    "Thematic Analysis (Braun & Clarke)": {
        "description": "Relations for reflexive thematic analysis following Braun & Clarke's "
                       "six-phase approach. Emphasizes researcher reflexivity and the active "
                       "role of the researcher in generating themes.",
        "relations": [
            {"name": "(No label)",
             "definition": "Connection without a named relation type.",
             "comments": ""},
            {"name": "is initial code for",
             "definition": "A data-driven or theory-driven label assigned to a data segment.",
             "comments": "Phase 2: generating initial codes."},
            {"name": "is candidate theme for",
             "definition": "A provisional theme that groups related codes.",
             "comments": "Phase 3: searching for themes."},
            {"name": "is subtheme of",
             "definition": "A theme nested within a broader overarching theme.",
             "comments": "Hierarchical thematic structure."},
            {"name": "overlaps with",
             "definition": "Two themes share codes or meaning territory.",
             "comments": "May signal need to merge or split."},
            {"name": "refines",
             "definition": "A revised version of a theme after review.",
             "comments": "Phase 4: reviewing themes."},
            {"name": "defines",
             "definition": "The 'essence' or core meaning of a theme.",
             "comments": "Phase 5: defining and naming themes."},
            {"name": "illustrates",
             "definition": "A vivid data extract that captures the theme.",
             "comments": "Phase 6: producing the report."},
            {"name": "is context for",
             "definition": "One theme provides the situational backdrop for another.",
             "comments": "Contextual or framing relation."},
            {"name": "contradicts",
             "definition": "Two themes or codes are in tension.",
             "comments": "Analytically productive contradiction."},
            {"name": "is associated with",
             "definition": "Co-occurrence or conceptual affinity.",
             "comments": "Provisional semantic link."},
        ]
    },
    "Discourse Analysis": {
        "description": "Relations for Critical Discourse Analysis (Fairclough) and Foucauldian "
                       "discourse analysis. Focus on how language constructs social reality, "
                       "power relations, and subject positions.",
        "relations": [
            {"name": "(No label)",
             "definition": "Connection without a named relation type.",
             "comments": ""},
            {"name": "constructs",
             "definition": "A discursive practice that produces a social object or subject position.",
             "comments": "Constitutive function of discourse."},
            {"name": "legitimizes",
             "definition": "One discourse provides justification or authority to another.",
             "comments": "Power/knowledge nexus."},
            {"name": "resists",
             "definition": "A counter-discourse that challenges or subverts a dominant discourse.",
             "comments": "Counter-hegemonic practice."},
            {"name": "naturalizes",
             "definition": "A discourse that makes a social construction appear self-evident.",
             "comments": "Ideological function."},
            {"name": "is intertextual with",
             "definition": "One text draws on, references, or transforms another text.",
             "comments": "Intertextuality (Fairclough)."},
            {"name": "positions subject as",
             "definition": "The discourse assigns an identity or role to social actors.",
             "comments": "Subject positioning."},
            {"name": "is register of",
             "definition": "The linguistic variety associated with a social context.",
             "comments": "Field, tenor, mode (Halliday)."},
            {"name": "is modality of",
             "definition": "The degree of certainty, obligation, or commitment expressed.",
             "comments": "Epistemic and deontic modality."},
            {"name": "presupposes",
             "definition": "One statement takes another as given or assumed.",
             "comments": "Pragmatic presupposition."},
            {"name": "is metaphor for",
             "definition": "One concept is understood through the frame of another.",
             "comments": "Conceptual metaphor (Lakoff & Johnson)."},
        ]
    },
    "User": {
        "description": "User-defined relation types. Add your own relations here.",
        "relations": [
            {"name": "(No label)",
             "definition": "Connection without a named relation type.",
             "comments": ""},
        ]
    },
}


# Poedit / xgettext extraction block
# This block is NEVER executed. It exists so that poedit and xgettext can find
# every translatable string in the source. All calls use _() directly
if False:  # noqa: SIM108  — intentional dead code for string extraction
    # Framework names
    _("Grounded Theory (Strauss & Corbin)")
    _("Qualitative Content Analysis (Mayring)")
    _("Phenomenology (Moustakas / van Manen)")
    _("Thematic Analysis (Braun & Clarke)")
    _("Discourse Analysis")
    _("User")

    # Framework descriptions
    _("Relations derived from Strauss & Corbin's axial coding paradigm model. "
      "Used during open, axial, and selective coding to articulate the structure "
      "around a central phenomenon.")
    _("Relations for structuring deductive and inductive category systems "
      "following Mayring's systematic approach to qualitative content analysis.")
    _("Relations for articulating the structure of lived experience, "
      "following Moustakas' transcendental phenomenology and van Manen's "
      "hermeneutic phenomenology.")
    _("Relations for reflexive thematic analysis following Braun & Clarke's "
      "six-phase approach. Emphasizes researcher reflexivity and the active "
      "role of the researcher in generating themes.")
    _("Relations for Critical Discourse Analysis (Fairclough) and Foucauldian "
      "discourse analysis. Focus on how language constructs social reality, "
      "power relations, and subject positions.")
    _("User-defined relation types. Add your own relations here.")

    # Relation names
    _("(No label)")
    _("is associated with")
    _("is cause of")
    _("is part of")
    _("is a")
    _("is property of")
    _("contradicts")
    _("supports")
    _("is context for")
    _("precedes")
    _("justifies")
    _("is condition for")
    _("is strategy for")
    _("is consequence of")
    _("intervenes in")
    _("is central phenomenon")
    _("is dimension of")
    _("is subcategory of")
    _("leads to")
    _("is main category of")
    _("is anchor example for")
    _("is coding rule for")
    _("overlaps with")
    _("refines")
    _("summarizes")
    _("explicates")
    _("structures")
    _("is textural description of")
    _("is structural description of")
    _("is essence of")
    _("is horizon of")
    _("is theme of")
    _("is embodied in")
    _("is situated in")
    _("is temporalized as")
    _("is relational to")
    _("constitutes")
    _("is initial code for")
    _("is candidate theme for")
    _("is subtheme of")
    _("defines")
    _("illustrates")
    _("constructs")
    _("legitimizes")
    _("resists")
    _("naturalizes")
    _("is intertextual with")
    _("positions subject as")
    _("is register of")
    _("is modality of")
    _("presupposes")
    _("is metaphor for")

    # Relation definitions
    _("Connection without a named relation type.")
    _("Two concepts co-occur or are linked but without a specified causal or hierarchical direction.")
    _("One concept produces, generates, or leads to another.")
    _("One concept is a component, dimension, or facet of another.")
    _("Subsumption: one concept is a type or instance of another.")
    _("One concept describes an attribute or quality of another.")
    _("Two concepts are in tension, opposition, or mutual exclusion.")
    _("One concept provides evidence, confirmation, or reinforcement for another.")
    _("One concept provides the situational backdrop for another.")
    _("One concept occurs before another in time or sequence.")
    _("One concept provides the rationale or legitimation for another.")
    _("A causal, intervening, or contextual condition that influences the phenomenon.")
    _("An action/interaction strategy used in response to or to manage the phenomenon.")
    _("A result or outcome that follows from action/interaction strategies.")
    _("The set of conditions within which strategies are enacted.")
    _("A broader structural condition that facilitates or constrains strategies.")
    _("The core category or central idea to which all other categories relate.")
    _("A property varies along this continuum or range.")
    _("One category is subsumed under or elaborates a higher-order category.")
    _("Two concepts co-occur without specified directionality.")
    _("A processual or temporal link between phases.")
    _("A superordinate category that organizes subcategories.")
    _("A subordinate category under a main category.")
    _("A prototypical text passage that defines a category.")
    _("A decision rule that resolves ambiguity between categories.")
    _("Two categories share some coded segments or meaning.")
    _("One category is a more precise version of another after revision.")
    _("Two categories or findings are in tension.")
    _("One category captures the gist of several lower-level categories.")
    _("One category clarifies the meaning of another through context.")
    _("One category provides the organizing frame for others.")
    _("Describes WHAT was experienced (the noema).")
    _("Describes HOW the experience was lived (the noesis).")
    _("The invariant meaning that persists across individual experiences.")
    _("A meaning unit that bounds or delimits the experience.")
    _("An experiential structure that recurs across participants.")
    _("The experience manifests through bodily sensation or corporeal presence.")
    _("The experience occurs within a specific spatial context.")
    _("The experience unfolds within subjective time.")
    _("The experience involves connection with others.")
    _("One meaning unit participates in constructing a broader theme.")
    _("A data-driven or theory-driven label assigned to a data segment.")
    _("A provisional theme that groups related codes.")
    _("A theme nested within a broader overarching theme.")
    _("Two themes share codes or meaning territory.")
    _("A revised version of a theme after review.")
    _("The 'essence' or core meaning of a theme.")
    _("A vivid data extract that captures the theme.")
    _("One theme provides the situational backdrop for another.")
    _("Two themes or codes are in tension.")
    _("Co-occurrence or conceptual affinity.")
    _("A discursive practice that produces a social object or subject position.")
    _("One discourse provides justification or authority to another.")
    _("A counter-discourse that challenges or subverts a dominant discourse.")
    _("A discourse that makes a social construction appear self-evident.")
    _("One text draws on, references, or transforms another text.")
    _("The discourse assigns an identity or role to social actors.")
    _("The linguistic variety associated with a social context.")
    _("The degree of certainty, obligation, or commitment expressed.")
    _("One statement takes another as given or assumed.")
    _("One concept is understood through the frame of another.")

    # Relation comments
    _("Use for simple visual links between codes.")
    _("Symmetric relation. Most common default.")
    _("Asymmetric: A causes B ≠ B causes A.")
    _("Mereological relation (part-whole).")
    _("Taxonomic / ISA hierarchy.")
    _("Property-bearer relation.")
    _("Useful for mapping analytical tensions.")
    _("Evidential or corroborative link.")
    _("Contextual framing relation.")
    _("Temporal or processual ordering.")
    _("Argumentative or normative link.")
    _("Axial coding: conditions → phenomenon.")
    _("Axial coding: phenomenon → strategies.")
    _("Axial coding: strategies → consequences.")
    _("Narrow situational conditions.")
    _("Intervening conditions in paradigm model.")
    _("Identified during selective coding.")
    _("Properties and dimensions of categories.")
    _("Hierarchical abstraction.")
    _("Open coding: provisional link.")
    _("Process coding: sequential stages.")
    _("Deductive: from theory. Inductive: from data.")
    _("Hierarchical nesting.")
    _("Anchor examples fix category meaning.")
    _("Delineates category boundaries.")
    _("Signals need for coding rule refinement.")
    _("Used during iterative category revision.")
    _("Analytically productive tensions.")
    _("Summarizing content analysis.")
    _("Explicating content analysis.")
    _("Structuring content analysis.")
    _("Moustakas: textural = content of experience.")
    _("Moustakas: structural = conditions/context.")
    _("Composite textural-structural description.")
    _("Horizonalization: each statement has equal value.")
    _("van Manen: existential themes.")
    _("Lived body (corporeality).")
    _("Lived space (spatiality).")
    _("Lived time (temporality).")
    _("Lived relation (relationality).")
    _("Phenomenological constitution.")
    _("Phase 2: generating initial codes.")
    _("Phase 3: searching for themes.")
    _("Hierarchical thematic structure.")
    _("May signal need to merge or split.")
    _("Phase 4: reviewing themes.")
    _("Phase 5: defining and naming themes.")
    _("Phase 6: producing the report.")
    _("Contextual or framing relation.")
    _("Analytically productive contradiction.")
    _("Provisional semantic link.")
    _("Constitutive function of discourse.")
    _("Power/knowledge nexus.")
    _("Counter-hegemonic practice.")
    _("Ideological function.")
    _("Intertextuality (Fairclough).")
    _("Subject positioning.")
    _("Field, tenor, mode (Halliday).")
    _("Epistemic and deontic modality.")
    _("Pragmatic presupposition.")
    _("Conceptual metaphor (Lakoff & Johnson).")

    # Color names
    _("Gray")
    _("Blue")
    _("Green")
    _("Red")
    _("Cyan")
    _("Magenta")
    _("Yellow")
    _("Orange")

    # Line type names
    _("Dotted with arrow")
    _("Solid with arrow")
    _("Dotted without arrow")
    _("Solid without arrow")
    _("Dotted with bidirectional arrow")
    _("Solid with bidirectional arrow")

    # UI labels and messages
    _("Framework:")
    _("Search relations...")
    _("Custom label:")
    _("Override with a custom label...")
    _("Color:")
    _("Line type:")
    _("Add")
    _("Edit")
    _("Delete")
    _("Import")
    _("Export")
    _("Connect")
    _("Cancel")
    _("Duplicate relation")
    _("A relation with this name already exists in the User framework.")
    _("Another relation with this name already exists in the User framework.")
    _("Saved to User")
    _("The edited relation has been saved as a new entry in the User framework. "
      "The original system relation remains unchanged.")
    _("System relations cannot be deleted. They are part of the academic reference frameworks. "
      "Only relations in the User framework can be removed.")
    _("Auto-saved from custom label.")
    _("Import user relations")
    _("Export user relations")
    _("Import error")
    _("Export error")
    _("Could not read JSON file:\n")
    _("Could not write JSON file:\n")
    _("Invalid format")
    _("The file does not contain a valid User-framework structure. "
      "Expected JSON with a top-level 'User' key.")
    _("The 'User' framework in the file does not contain a valid 'relations' list.")
    _("Import complete")
    _("Export complete")
    _("Imported: ")
    _("Skipped (duplicates or invalid): ")
    _("User relations exported to:\n")


# JSON PERSISTENCE
def _get_relations_filepath(settings):
    """
    Return path to node_relations.json in ~/.qualcoder/.
    """
    qualcoder_dir = os.path.join(os.path.expanduser("~"), ".qualcoder")
    if not os.path.exists(qualcoder_dir):
        try:
            os.makedirs(qualcoder_dir, exist_ok=True)
        except OSError:
            qualcoder_dir = os.path.expanduser("~")
    return os.path.join(qualcoder_dir, "node_relations.json")


def load_relations(settings):
    """
    Load combined relation frameworks.

    System frameworks come from DEFAULT_FRAMEWORKS (hardcoded, translatable).
    Only the 'User' framework is persisted in node_relations.json.

    Returns: dict of all frameworks (system + user).
    """
    data = json.loads(json.dumps(DEFAULT_FRAMEWORKS))  # deep copy

    filepath = _get_relations_filepath(settings)
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                user_data = json.load(f)
            if "User" in user_data:
                user_relations = user_data["User"].get("relations", [])
                # Ensure "(No label)" is always present as first entry
                if not any(r.get("name") == "(No label)" for r in user_relations):
                    user_relations.insert(0, {
                        "name": "(No label)",
                        "definition": "Connection without a named relation type.",
                        "comments": ""
                    })
                data["User"]["relations"] = user_relations
        except (json.JSONDecodeError, IOError) as e:
            logger.warning("Could not read node_relations.json: %s. Using defaults.", e)

    return data


def save_relations(settings, data):
    """
    Save only the 'User' framework to JSON file.

    System frameworks are never persisted - they come from DEFAULT_FRAMEWORKS.
    """
    filepath = _get_relations_filepath(settings)
    try:
        user_only = {"User": data.get("User", DEFAULT_FRAMEWORKS["User"])}
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(user_only, f, ensure_ascii=False, indent=2)
    except IOError as e:
        logger.error("Could not write node_relations.json: %s", e)


# AUXILIARY DIALOGS
class DialogRelationDetail(QtWidgets.QDialog):
    """
    Pop-up showing full information for one relation (read-only).

    Opened on double-click in the relations list.
    """

    def __init__(self, relation_dict, framework_name="", parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("Relation detail"))
        self.setMinimumSize(440, 320)
        layout = QtWidgets.QVBoxLayout(self)

        if framework_name:
            fw_label = QtWidgets.QLabel(_("Framework: ") + _(framework_name))
            fw_label.setStyleSheet("color: #555; font-style: italic;")
            layout.addWidget(fw_label)

        # Name
        lbl = QtWidgets.QLabel(_("Relation name:"))
        lbl.setStyleSheet("font-weight: bold; margin-top: 8px;")
        layout.addWidget(lbl)
        val = QtWidgets.QLabel(_(relation_dict.get("name", "")))
        val.setWordWrap(True)
        val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(val)

        # Definition
        lbl = QtWidgets.QLabel(_("Definition:"))
        lbl.setStyleSheet("font-weight: bold; margin-top: 8px;")
        layout.addWidget(lbl)
        val = QtWidgets.QLabel(_(relation_dict.get("definition", "")))
        val.setWordWrap(True)
        val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(val)

        # Comments
        lbl = QtWidgets.QLabel(_("Comments:"))
        lbl.setStyleSheet("font-weight: bold; margin-top: 8px;")
        layout.addWidget(lbl)
        comments_text = relation_dict.get("comments", "")
        val = QtWidgets.QLabel(_(comments_text) if comments_text else _("(none)"))
        val.setWordWrap(True)
        val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(val)

        layout.addStretch()

        btn_close = QtWidgets.QPushButton(_("Close"))
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)


class DialogAddEditRelation(QtWidgets.QDialog):
    """
    Dialog to add a new relation or edit an existing one.

    Fields: name, definition, comments.
    """

    def __init__(self, relation_dict=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("Add relation") if relation_dict is None else _("Edit relation"))
        self.setMinimumSize(420, 280)
        layout = QtWidgets.QFormLayout(self)

        self.lineEdit_name = QtWidgets.QLineEdit()
        self.lineEdit_name.setPlaceholderText(_("e.g., is consequence of"))
        layout.addRow(_("Relation name:"), self.lineEdit_name)

        self.textEdit_definition = QtWidgets.QPlainTextEdit()
        self.textEdit_definition.setPlaceholderText(_("Brief definition of the relation..."))
        self.textEdit_definition.setMaximumHeight(80)
        layout.addRow(_("Definition:"), self.textEdit_definition)

        self.textEdit_comments = QtWidgets.QPlainTextEdit()
        self.textEdit_comments.setPlaceholderText(_("Methodological notes, references, usage tips..."))
        self.textEdit_comments.setMaximumHeight(80)
        layout.addRow(_("Comments:"), self.textEdit_comments)

        if relation_dict:
            self.lineEdit_name.setText(relation_dict.get("name", ""))
            self.textEdit_definition.setPlainText(relation_dict.get("definition", ""))
            self.textEdit_comments.setPlainText(relation_dict.get("comments", ""))

        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()
        btn_ok = QtWidgets.QPushButton(_("OK"))
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self._validate_and_accept)
        btn_layout.addWidget(btn_ok)
        btn_cancel = QtWidgets.QPushButton(_("Cancel"))
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)
        layout.addRow(btn_layout)

        self.result_dict = None

    def _validate_and_accept(self):
        name = self.lineEdit_name.text().strip()
        if not name:
            QtWidgets.QMessageBox.warning(self, _("Validation"),
                                          _("Relation name cannot be empty."))
            return
        self.result_dict = {
            "name": name,
            "definition": self.textEdit_definition.toPlainText().strip(),
            "comments": self.textEdit_comments.toPlainText().strip(),
        }
        self.accept()


# MAIN DIALOG
class DialogNodeRelations(QtWidgets.QDialog):
    """
    Simplified dialog for selecting a semantic relation when connecting two nodes.

    Primary flow (always visible):
      1. Pick a theoretical framework (combobox).
      2. Optionally type in the search field to filter.
      3. Click a relation in the list — its definition appears below (if UI has the label).
      4. Configure color, line type, or custom labels.
      5. Press Connect.
    """

    _last_framework_name = None  # remember last used framework across dialog instances

    COLOR_ITEMS = [
        {"name": "Gray",    "key": "gray",    "hex": "#808080"},
        {"name": "Blue",    "key": "blue",    "hex": "#6495ED"},
        {"name": "Green",   "key": "green",   "hex": "#00AA00"},
        {"name": "Red",     "key": "red",     "hex": "#FF0000"},
        {"name": "Cyan",    "key": "cyan",    "hex": "#00FFFF"},
        {"name": "Magenta", "key": "magenta", "hex": "#FF00FF"},
        {"name": "Yellow",  "key": "yellow",  "hex": "#FFD700"},
        {"name": "Orange",  "key": "orange",  "hex": "#FFA500"},
    ]

    LINE_TYPE_ITEMS = [
        {"glyph": "--->",  "name": "Dotted with arrow",                "key": "dotted_arrow"},
        {"glyph": "───>",  "name": "Solid with arrow",                 "key": "solid_arrow"},
        {"glyph": "----",  "name": "Dotted without arrow",             "key": "dotted_no_arrow"},
        {"glyph": "────",  "name": "Solid without arrow",              "key": "solid_no_arrow"},
        {"glyph": "<-->",  "name": "Dotted with bidirectional arrow",  "key": "dotted_bidirectional"},
        {"glyph": "<──>",  "name": "Solid with bidirectional arrow",   "key": "solid_bidirectional"},
    ]

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.ui = Ui_Dialog_node_relations()
        self.ui.setupUi(self)

        # Apply app font
        font = f"font: {self.app.settings['fontsize']}pt "
        font += f'"{self.app.settings["font"]}";'
        self.setStyleSheet(font)

        # Outputs
        self.selected_relation = ""
        self.selected_color = "gray"
        self.selected_line_type = "solid_arrow"

        # Load frameworks
        self.frameworks_data = load_relations(self.app.settings)

        # Shorthand widget refs
        u = self.ui
        self.comboBox_framework = u.comboBox_framework
        self.lineEdit_search = u.lineEdit_search
        self.listWidget_relations = u.listWidget_relations
        self.frame_advanced = u.frame_advanced
        self.lineEdit_custom = u.lineEdit_custom
        self.comboBox_color = u.comboBox_color
        self.comboBox_line_type = u.comboBox_line_type
        self.pushButton_add_relation = u.pushButton_add_relation
        self.pushButton_edit_relation = u.pushButton_edit_relation
        self.pushButton_delete_relation = u.pushButton_delete_relation
        self.pushButton_import_relations = u.pushButton_import_relations
        self.pushButton_export_relations = u.pushButton_export_relations
        self.pushButton_connect = u.pushButton_connect
        self.pushButton_cancel = u.pushButton_cancel

        # Manejador seguro para el label_definition en caso de que lo vuelvas a añadir
        self.label_definition = getattr(u, 'label_definition', None)

        # Populate framework combobox
        self._framework_keys = list(self.frameworks_data.keys())
        for key in self._framework_keys:
            self.comboBox_framework.addItem(_(key))
        last_fw = DialogNodeRelations._last_framework_name
        if last_fw and last_fw in self._framework_keys:
            self.comboBox_framework.setCurrentIndex(self._framework_keys.index(last_fw))
        else:
            self.comboBox_framework.setCurrentIndex(0)

        # Populate color combobox with colored swatch + name
        for c in self.COLOR_ITEMS:
            pix = QtGui.QPixmap(14, 14)
            pix.fill(QtGui.QColor(c["hex"]))
            self.comboBox_color.addItem(QtGui.QIcon(pix), _(c["name"]))
        self.comboBox_color.setCurrentIndex(0)

        # Populate line-type combobox with glyph + descriptive name
        for lt in self.LINE_TYPE_ITEMS:
            self.comboBox_line_type.addItem(f"{lt['glyph']}   {_(lt['name'])}")
        self.comboBox_line_type.setCurrentIndex(1)  # default "Solid with arrow"

        # Icons on advanced buttons (defensive: qta failures should never break dialog)
        try:
            self.pushButton_add_relation.setIcon(
                qta.icon('mdi6.plus-circle-outline', options=[{'scale_factor': 1.2}]))
            self.pushButton_edit_relation.setIcon(
                qta.icon('mdi6.pencil-outline', options=[{'scale_factor': 1.2}]))
            self.pushButton_delete_relation.setIcon(
                qta.icon('mdi6.delete-outline', options=[{'scale_factor': 1.2}]))
            self.pushButton_import_relations.setIcon(
                qta.icon('mdi6.file-import-outline', options=[{'scale_factor': 1.2}]))
            self.pushButton_export_relations.setIcon(
                qta.icon('mdi6.file-export-outline', options=[{'scale_factor': 1.2}]))
        except Exception as e:
            logger.warning("Could not assign qtawesome icons: %s", e)

        # Signals
        self.comboBox_framework.currentIndexChanged.connect(self._on_framework_changed)
        self.lineEdit_search.textChanged.connect(self._on_search_changed)
        self.listWidget_relations.currentRowChanged.connect(self._on_relation_changed)
        self.listWidget_relations.itemDoubleClicked.connect(self._on_relation_double_clicked)
        self.pushButton_add_relation.clicked.connect(self._add_relation)
        self.pushButton_edit_relation.clicked.connect(self._edit_relation)
        self.pushButton_delete_relation.clicked.connect(self._delete_relation)
        self.pushButton_import_relations.clicked.connect(self._import_relations)
        self.pushButton_export_relations.clicked.connect(self._export_relations)
        self.pushButton_connect.clicked.connect(self._do_accept)
        self.pushButton_cancel.clicked.connect(self.reject)
        self.lineEdit_custom.textChanged.connect(self._on_custom_text_changed)

        # Initial state
        self._populate_relations_list()

    # FRAMEWORK / LIST POPULATION

    def _current_framework_key(self):
        idx = self.comboBox_framework.currentIndex()
        if 0 <= idx < len(self._framework_keys):
            return self._framework_keys[idx]
        return "Grounded Theory (Strauss & Corbin)"

    def _current_relations(self):
        return self.frameworks_data.get(self._current_framework_key(), {}).get("relations", [])

    def _is_user_framework(self):
        return self._current_framework_key() == "User"

    def _populate_relations_list(self):
        """
        Fill the list with relations from the current framework, applying the
        search filter if non-empty.
        """
        search = self.lineEdit_search.text().strip().lower()
        self.listWidget_relations.clear()
        relations = self._current_relations()

        for rel in relations:
            raw_name = rel.get("name", "")
            translated_name = _(raw_name)
            if search and search not in translated_name.lower():
                # Also match against definition for broader discoverability
                if search not in _(rel.get("definition", "")).lower():
                    continue
            item = QtWidgets.QListWidgetItem(translated_name)
            item.setData(Qt.ItemDataRole.UserRole, raw_name)
            tooltip = _(rel.get("definition", ""))
            if tooltip:
                item.setToolTip(tooltip)
            self.listWidget_relations.addItem(item)

        if self.listWidget_relations.count() > 0:
            self.listWidget_relations.setCurrentRow(0)
        else:
            if self.label_definition:
                self.label_definition.setText("")

    def _on_framework_changed(self, _idx):
        self.lineEdit_search.clear()  # reset search on framework switch
        self._populate_relations_list()

    def _on_search_changed(self, _text):
        self._populate_relations_list()

    def _on_relation_changed(self, row):
        if not self.label_definition:
            return
        if row < 0:
            self.label_definition.setText("")
            return
        item = self.listWidget_relations.item(row)
        if item is None:
            return
        raw_name = item.data(Qt.ItemDataRole.UserRole)
        # find the relation dict to display its definition
        for rel in self._current_relations():
            if rel.get("name") == raw_name:
                self.label_definition.setText(_(rel.get("definition", "")))
                return
        self.label_definition.setText("")

    def _on_relation_double_clicked(self, item):
        raw_name = item.data(Qt.ItemDataRole.UserRole)
        for rel in self._current_relations():
            if rel.get("name") == raw_name:
                dlg = DialogRelationDetail(rel, self._current_framework_key(), self)
                dlg.exec()
                return

    # CUSTOM LABEL

    def _on_custom_text_changed(self, text):
        if text.strip():
            self.listWidget_relations.clearSelection()
            if self.label_definition:
                self.label_definition.setText("")

    # USER-FRAMEWORK HELPERS

    def _normalize_relation_name(self, name):
        return (name or "").strip().lower()

    def _is_duplicate_in_user(self, name):
        normalized = self._normalize_relation_name(name)
        if not normalized:
            return False
        user_relations = self.frameworks_data.get("User", {}).get("relations", [])
        for r in user_relations:
            if self._normalize_relation_name(r.get("name", "")) == normalized:
                return True
        return False

    def _switch_to_user_framework(self):
        if "User" in self._framework_keys:
            idx = self._framework_keys.index("User")
            if self.comboBox_framework.currentIndex() != idx:
                self.comboBox_framework.setCurrentIndex(idx)

    def _selected_relation_index_in_full_list(self):
        """
        Return the index of the currently-selected list item within the full
        (unfiltered) relations list of the current framework, or -1.
        """
        row = self.listWidget_relations.currentRow()
        if row < 0:
            return -1
        item = self.listWidget_relations.item(row)
        if item is None:
            return -1
        raw_name = item.data(Qt.ItemDataRole.UserRole)
        for i, rel in enumerate(self._current_relations()):
            if rel.get("name") == raw_name:
                return i
        return -1

    # ADD / EDIT / DELETE

    def _add_relation(self):
        """
        New relations always go to the User framework.
        """
        dlg = DialogAddEditRelation(parent=self)
        if not dlg.exec() or not dlg.result_dict:
            return
        new_name = dlg.result_dict.get("name", "")
        if self._is_duplicate_in_user(new_name):
            QtWidgets.QMessageBox.warning(
                self, _("Duplicate relation"),
                _("A relation with this name already exists in the User framework."))
            return
        user_relations = self.frameworks_data.setdefault("User", {
            "description": _("User-defined relation types. Add your own relations here."),
            "relations": []}).setdefault("relations", [])
        user_relations.append(dlg.result_dict)
        save_relations(self.app.settings, self.frameworks_data)
        self._switch_to_user_framework()
        self._populate_relations_list()
        # Select the newly added relation
        for i in range(self.listWidget_relations.count()):
            if self.listWidget_relations.item(i).data(Qt.ItemDataRole.UserRole) == new_name:
                self.listWidget_relations.setCurrentRow(i)
                break

    def _edit_relation(self):
        """
        Editing a system relation creates a modified copy in User;
        editing a User relation modifies it in place.
        """
        idx = self._selected_relation_index_in_full_list()
        relations = self._current_relations()
        if idx < 0:
            return
        rel = relations[idx]
        if rel.get("name") == "(No label)":
            QtWidgets.QMessageBox.information(
                self, _("Info"), _("The '(No label)' entry cannot be edited."))
            return
        dlg = DialogAddEditRelation(rel, parent=self)
        if not dlg.exec() or not dlg.result_dict:
            return
        edited_name = dlg.result_dict.get("name", "")

        if self._is_user_framework():
            for i, r in enumerate(relations):
                if i == idx:
                    continue
                if self._normalize_relation_name(r.get("name", "")) == self._normalize_relation_name(edited_name):
                    QtWidgets.QMessageBox.warning(
                        self, _("Duplicate relation"),
                        _("Another relation with this name already exists in the User framework."))
                    return
            relations[idx] = dlg.result_dict
            save_relations(self.app.settings, self.frameworks_data)
            self._populate_relations_list()
        else:
            if self._is_duplicate_in_user(edited_name):
                QtWidgets.QMessageBox.warning(
                    self, _("Duplicate relation"),
                    _("A relation with this name already exists in the User framework."))
                return
            user_relations = self.frameworks_data.setdefault("User", {
                "description": _("User-defined relation types. Add your own relations here."),
                "relations": []}).setdefault("relations", [])
            user_relations.append(dlg.result_dict)
            save_relations(self.app.settings, self.frameworks_data)
            QtWidgets.QMessageBox.information(
                self, _("Saved to User"),
                _("The edited relation has been saved as a new entry in the User framework. "
                  "The original system relation remains unchanged."))
            self._switch_to_user_framework()
            self._populate_relations_list()

    def _delete_relation(self):
        """
        Only User-framework relations can be deleted.
        """
        idx = self._selected_relation_index_in_full_list()
        relations = self._current_relations()
        if idx < 0:
            return
        rel = relations[idx]
        if rel.get("name") == "(No label)":
            QtWidgets.QMessageBox.information(
                self, _("Info"), _("The '(No label)' entry cannot be deleted."))
            return
        if not self._is_user_framework():
            QtWidgets.QMessageBox.information(
                self, _("Info"),
                _("System relations cannot be deleted. They are part of the academic reference frameworks. "
                  "Only relations in the User framework can be removed."))
            return
        reply = QtWidgets.QMessageBox.question(
            self, _("Delete relation"),
            _("Delete relation '") + _(rel.get("name", "")) + _("'?"),
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No)
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            relations.pop(idx)
            save_relations(self.app.settings, self.frameworks_data)
            self._populate_relations_list()

    # IMPORT / EXPORT

    def _import_relations(self):
        """
        Import a JSON file (same structure as save_relations) into the User
        framework, skipping duplicates.
        """
        filepath, _filter = QtWidgets.QFileDialog.getOpenFileName(
            self, _("Import user relations"), os.path.expanduser("~"),
            "JSON Files (*.json);;All Files (*)")
        if not filepath:
            return
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                imported_data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            QtWidgets.QMessageBox.critical(
                self, _("Import error"),
                _("Could not read JSON file:\n") + str(e))
            return
        if not isinstance(imported_data, dict) or "User" not in imported_data:
            QtWidgets.QMessageBox.warning(
                self, _("Invalid format"),
                _("The file does not contain a valid User-framework structure. "
                  "Expected JSON with a top-level 'User' key."))
            return
        imported_relations = imported_data["User"].get("relations", [])
        if not isinstance(imported_relations, list):
            QtWidgets.QMessageBox.warning(
                self, _("Invalid format"),
                _("The 'User' framework in the file does not contain a valid 'relations' list."))
            return

        user_block = self.frameworks_data.setdefault("User", {
            "description": _("User-defined relation types. Add your own relations here."),
            "relations": []})
        existing_relations = user_block.setdefault("relations", [])
        added = 0
        skipped = 0
        for rel in imported_relations:
            if not isinstance(rel, dict):
                skipped += 1
                continue
            rel_name = rel.get("name", "").strip()
            if not rel_name or rel_name == "(No label)":
                skipped += 1
                continue
            if self._is_duplicate_in_user(rel_name):
                skipped += 1
                continue
            existing_relations.append({
                "name": rel_name,
                "definition": rel.get("definition", "") or "",
                "comments": rel.get("comments", "") or "",
            })
            added += 1
        try:
            save_relations(self.app.settings, self.frameworks_data)
        except Exception as e:
            logger.error("Could not save merged relations: %s", e)
        self._switch_to_user_framework()
        self._populate_relations_list()
        QtWidgets.QMessageBox.information(
            self, _("Import complete"),
            _("Imported: ") + str(added) + "\n" +
            _("Skipped (duplicates or invalid): ") + str(skipped))

    def _export_relations(self):
        """
        Export the User framework to a JSON file.
        """
        filepath, _filter = QtWidgets.QFileDialog.getSaveFileName(
            self, _("Export user relations"),
            os.path.join(os.path.expanduser("~"), "qualcoder_user_relations.json"),
            "JSON Files (*.json);;All Files (*)")
        if not filepath:
            return
        if not filepath.lower().endswith(".json"):
            filepath += ".json"
        user_block = self.frameworks_data.get("User", {
            "description": _("User-defined relation types. Add your own relations here."),
            "relations": []})
        export_data = {"User": user_block}
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
            QtWidgets.QMessageBox.information(
                self, _("Export complete"),
                _("User relations exported to:\n") + filepath)
        except IOError as e:
            QtWidgets.QMessageBox.critical(
                self, _("Export error"),
                _("Could not write JSON file:\n") + str(e))

    # ACCEPT

    def _do_accept(self):
        """
        Collect selected relation, color and line type, then close.
        Custom labels typed by the user are auto-persisted into the User framework.
        """
        # Relation name: custom label takes precedence
        custom_text = self.lineEdit_custom.text().strip()
        if custom_text:
            self.selected_relation = custom_text
            if not self._is_duplicate_in_user(custom_text):
                user_block = self.frameworks_data.setdefault("User", {
                    "description": _("User-defined relation types. Add your own relations here."),
                    "relations": []})
                user_relations = user_block.setdefault("relations", [])
                user_relations.append({
                    "name": custom_text,
                    "definition": "",
                    "comments": _("Auto-saved from custom label."),
                })
                try:
                    save_relations(self.app.settings, self.frameworks_data)
                except Exception as e:
                    logger.warning("Could not persist custom label to User framework: %s", e)
        else:
            row = self.listWidget_relations.currentRow()
            if row >= 0:
                item = self.listWidget_relations.item(row)
                raw_name = item.data(Qt.ItemDataRole.UserRole) if item else ""
                self.selected_relation = "" if raw_name == "(No label)" else raw_name
            else:
                self.selected_relation = ""

        # Color
        color_idx = self.comboBox_color.currentIndex()
        if 0 <= color_idx < len(self.COLOR_ITEMS):
            self.selected_color = self.COLOR_ITEMS[color_idx]["key"]
        else:
            self.selected_color = "gray"

        # Line type
        line_idx = self.comboBox_line_type.currentIndex()
        if 0 <= line_idx < len(self.LINE_TYPE_ITEMS):
            self.selected_line_type = self.LINE_TYPE_ITEMS[line_idx]["key"]
        else:
            self.selected_line_type = "solid_arrow"

        DialogNodeRelations._last_framework_name = self._current_framework_key()
        self.accept()