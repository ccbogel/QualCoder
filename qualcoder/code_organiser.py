# -*- coding: utf-8 -*-

"""
Copyright (c) 2024 Colin Curtain

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.

Author: Colin Curtain (ccbogel)
https://github.com/ccbogel/QualCoder
https://qualcoder.wordpress.com/
"""
import sqlite3
from copy import deepcopy
import datetime
import os
import qtawesome as qta  # see: https://pictogrammers.com/library/mdi/
from random import randint

from PyQt6 import QtCore, QtWidgets, QtGui
from PyQt6.QtWidgets import QDialog

from .add_item_name import DialogAddItemName
from .code_in_all_files import DialogCodeInAllFiles
from .color_selector import TextColor
from .GUI.ui_dialog_organiser import Ui_DialogOrganiser
from .helpers import ExportDirectoryPathDialog, Message
from .memo import DialogMemo
from .select_items import DialogSelectItems

path = os.path.abspath(os.path.dirname(__file__))
# logger = logging.getLogger(__name__)

# Easier to modify these variables across classes
model = []
update_graphics_item_models = False


class CodeOrganiser(QDialog):
    """ Dialog to organise code and categories in an acyclic graph.
    Add new categories, move codes and categories to other categories.
    Merge codes and categories
    Delete categories
    """

    app = None
    parent_text_edit = None
    conn = None
    settings = None
    scene = None
    font_size = 9

    def __init__(self, app, text_edit):
        """ Set up the dialog and graphics scene. """

        QDialog.__init__(self)
        self.app = app
        self.parent_text_edit = text_edit
        self.settings = app.settings
        self.conn = app.conn
        # Set up the user interface from Designer.
        self.ui = Ui_DialogOrganiser()
        self.ui.setupUi(self)
        font = f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";'
        self.setStyleSheet(font)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        self.ui.pushButton_export.setIcon(qta.icon('mdi6.export'))
        self.ui.pushButton_export.pressed.connect(self.export_image)
        self.ui.label_zoom.setPixmap(qta.icon('mdi6.magnify').pixmap(26, 26))
        self.ui.pushButton_selectbranch.setIcon(qta.icon('mdi6.file-tree'))
        self.ui.pushButton_selectbranch.pressed.connect(self.select_tree_branch)
        self.ui.pushButton_create_category.setIcon(qta.icon('mdi6.pencil-plus-outline'))
        self.ui.pushButton_create_category.pressed.connect(self.create_category)
        self.ui.pushButton_apply.setEnabled(False)
        self.ui.pushButton_apply.pressed.connect(self.apply_model_changes)

        # Set the scene
        self.scene = GraphicsScene()
        self.ui.graphicsView.setScene(self.scene)
        self.ui.graphicsView.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.graphicsView.customContextMenuRequested.connect(self.graphicsview_menu)
        self.ui.graphicsView.viewport().installEventFilter(self)
        global update_graphics_item_models
        update_graphics_item_models = False
        global model
        model = []
        text_ = _("BACK UP PROJECT before applying changes to the codes tree.\n"
                  "The Code organiser is used mainly with grounded theory to help you develop and organise"
                  " the coding concepts and their hierarchy.\n"
                  "Select a code branch or All, then right click to:\n"
                  "Add categories, rename codes and categories, update memos, merge codes, "
                  "merge categories, delete categories.\n"
                  "\n"
                  "Potential for unexpected errors could occur.\n"
                  "THERE IS NO UNDO OPTION AFTER APPLYING CHANGES WITH THE APPLY BUTTON.")
        Message(self.app, "Code organiser", text_).exec()

    def create_category(self):
        """ Create a new category, via push button. """

        cat_ids_list = []
        categories = []
        for item in model:
            if item['cid'] is None:
                cat_ids_list.append(item['catid'])
                categories.append(item)
        ui = DialogAddItemName(self.app, categories, _("Category"), _("Category name"))
        ui.exec()
        new_category_name = ui.get_new_name()
        if new_category_name is None:
            return

        temp_cat_id = randint(-1000, -1)
        while temp_cat_id in cat_ids_list:
            temp_cat_id = randint(-1000, -1)
        now_date = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        new_category = {'name': new_category_name, 'catid': temp_cat_id, 'owner': self.settings['codername'],
                        'date': now_date, 'memo': '', 'supercatid': None,
                        'x': 10 + randint(0, 6), 'y': 10 + randint(0, 6), 'color': "#FFFFFF",
                        'cid': None, 'original_cid': None, 'original_catid': temp_cat_id,
                        'original_memo': '', 'child_names': []}
        model.append(new_category)
        self.scene.addItem(TextGraphicsItem(self.app, new_category))

    def select_tree_branch(self):
        """ Selected tree branch for model of codes and categories.
        Called by pushButton_selectbranch.
        Only one branch selection can be organised at a time.
        e.g. a specific selected branch, or All for all codes and categories.
        """

        selection_list = [{'name': 'All'}]
        codes, categories = self.app.get_codes_categories()
        for category in categories:
            # Use top level categories only
            if category['supercatid'] is None:
                selection_list.append({'name': category['name']})
        ui = DialogSelectItems(self.app, selection_list, _("Select code tree branch"), "multi")
        ok = ui.exec()
        if not ok:
            return
        selected = ui.get_selected()
        if not selected:
            node_text = "All"
        else:
            node_text = selected[0]['name']
        self.create_initial_model()
        self.get_refined_model(node_text)
        self.list_graph()
        self.ui.pushButton_selectbranch.setEnabled(False)
        self.ui.pushButton_selectbranch.setToolTip(_("Branch has been selected"))
        self.ui.pushButton_apply.setEnabled(True)

    def create_initial_model(self):
        """ Create initial model of all codes and categories.
        model contains categories and codes combined.

        return: categories : List of Dictionaries of categories
        """

        codes, categories = self.app.get_codes_categories()
        code_name_equals_category_name = False
        for code in codes:
            code['original_cid'] = code['cid']
            code['original_catid'] = code['catid']
            code['original_memo'] = code['memo']
            code['x'] = None
            code['y'] = None
            code['delete'] = False
            code['supercatid'] = code['catid']

            """ This causes hierarchy to not work correctly.
            Solution, add space after the code_name to separate it out. 
            Trim on database update """
            for cat in categories:
                if code['name'] == cat['name']:
                    code['name'] = code['name'] + " "
            code['original_name'] = code['name']

        for category in categories:
            category['original_cid'] = None
            category['original_catid'] = category['catid']
            category['original_supercatid'] = category['supercatid']
            category['original_name'] = category['name']
            category['original_memo'] = category['memo']
            category['x'] = None
            category['y'] = None
            category['cid'] = None
            category['color'] = '#FFFFFF'
            category['delete'] = False  # True if merged
        global model
        model = categories + codes

    def get_refined_model(self, top_node_text):
        """ The initial model contains all categories and codes.
        The refined model is based on a selected category.
        Update the global model.

        param: top_node_text : String name of the top category
        """

        categories = []
        global model
        for item in model:
            if item['cid'] is None:
                categories.append(item)
        # Determine top node, or all
        top_node = None
        if top_node_text == "All":
            top_node = None
        else:
            for category in categories:
                if category['name'] == top_node_text:
                    top_node = category
                    top_node['supercatid'] = None  # Must set this to None
        # Create a refined model from the top node and all its children.
        if top_node is None:
            return
        refined_model = [top_node]
        i = 0  # Ensure an exit from while loop
        model_changed = True
        while model != [] and model_changed and i < 20:
            model_changed = False
            append_list = []
            for n in refined_model:
                for m in model:
                    if m['supercatid'] == n['catid']:
                        append_list.append(m)
            for n in append_list:
                refined_model.append(n)
                model.remove(n)
                model_changed = True
            i += 1
        model = refined_model

    def named_children_of_node(self, node):
        """ Get child categories and codes of this category node.
        Only keep the category or code name. Used to reposition TextGraphicsItems on moving a category.

        param: node : Dictionary of category

        return: child_names : List
        """

        if node['cid'] is not None:
            return []
        child_names = []
        codes_, categories_ = self.app.get_codes_categories()
        """ qdpx import quirk, but category names and code names can match. (MAXQDA, Nvivo)
        This causes hierarchy to not work correctly (eg when moving a category).
        Solution, add spaces after the code_name to separate it out. """
        for code in codes_:
            for cat in categories_:
                if code['name'] == cat['name']:
                    code['name'] = code['name'] + " "

        """ Create a list of this category (node) and all its category children.
        Maximum depth of 200. """
        selected_categories = [node]
        i = 0  # Ensure an exit from loop
        new_model_changed = True
        while categories_ != [] and new_model_changed and i < 200:
            new_model_changed = False
            append_list = []
            for n in selected_categories:
                for m in categories_:
                    if m['supercatid'] == n['catid']:
                        append_list.append(m)
                        child_names.append(m['name'])
            for n in append_list:
                selected_categories.append(n)
                categories_.remove(n)
                new_model_changed = True
            i += 1
        categories_ = selected_categories
        # Remove codes that are not associated with these categories
        selected_codes = []
        for cat in categories_:
            for code in codes_:
                if code['catid'] == cat['catid']:
                    selected_codes.append(code)
        codes_ = selected_codes
        for c in codes_:
            child_names.append(c['name'])
        return child_names

    def list_graph(self):
        """ Create a list graph with the categories on the left and codes on the right.

        param: global model : List of Dictionaries of categories and codes
        """

        global model
        # Order the model by supercatid, subcats, codes
        ordered_model = []
        # Top level categories
        for code_or_cat in model:
            if code_or_cat['x'] is None and code_or_cat['supercatid'] is None:
                code_or_cat['x'] = 10
                ordered_model.append(code_or_cat)
        for om in ordered_model:
            model.remove(om)

        # Sub-categories and codes
        i = 0
        while i < 1000 and len(model) > 0:
            for om in ordered_model:
                for sub_cat in model:
                    # subordinate categories
                    if sub_cat['supercatid'] == om['catid'] and sub_cat['x'] is None:
                        sub_cat['x'] = om['x'] + 120
                        ordered_model.insert(ordered_model.index(om), sub_cat)
            i += 1

        for item in range(0, len(ordered_model)):
            ordered_model[item]['y'] = item * self.font_size * 3
        model = ordered_model

        # Add text items to the scene, providing they are not already in the scene.
        for code_or_cat in model:
            code_or_cat['child_names'] = self.named_children_of_node(code_or_cat)
            add_to_scene = True
            for scene_item in self.scene.items():
                if isinstance(scene_item, TextGraphicsItem):
                    if scene_item.code_or_cat['name'] == code_or_cat['name'] and \
                            scene_item.code_or_cat['catid'] == code_or_cat['catid'] and \
                            scene_item.code_or_cat['cid'] == code_or_cat['cid']:
                        add_to_scene = False
            if add_to_scene:
                self.scene.addItem(TextGraphicsItem(self.app, code_or_cat))

                # Expand scene width and height if needed
        max_x, max_y = self.scene.suggested_scene_size()
        self.scene.set_width(max_x)
        self.scene.set_height(max_y)

    def keyPressEvent(self, event):
        """ Plus, W to zoom in and Minus, Q to zoom out.
        M to print Model
        Needs focus on the QGraphicsView widget. """

        key = event.key()
        # mod = event.modifiers()
        if key == QtCore.Qt.Key.Key_Plus or key == QtCore.Qt.Key.Key_W:
            if self.ui.graphicsView.transform().isScaling() and self.ui.graphicsView.transform().determinant() > 10:
                return
            self.ui.graphicsView.scale(1.1, 1.1)
        if key == QtCore.Qt.Key.Key_Minus or key == QtCore.Qt.Key.Key_Q:
            if self.ui.graphicsView.transform().isScaling() and self.ui.graphicsView.transform().determinant() < 0.1:
                return
            self.ui.graphicsView.scale(0.9, 0.9)
        if key == QtCore.Qt.Key.Key_I:
            for i in self.scene.items():
                print(i.__class__, i.pos())
        if key == QtCore.Qt.Key.Key_M:  # and mod == QtCore.Qt.KeyboardModifier.ControlModifier:
            # Display model
            global model
            print("^^^^ MODEL ^^^^")
            for m in model:
                print(m)
            print("^^^^^^^ CATS ^^^^^^^^^")
            for category in model:
                if category['cid'] is None:
                    print(category)
            print("^^^^^^^ CODES ^^^^^^^^^")
            for code in model:
                if code['cid'] is not None:
                    print(code)
            print("^^^^^^^^^^^^^^^^")

    def reject(self):

        super(CodeOrganiser, self).reject()

    def accept(self):

        super(CodeOrganiser, self).accept()

    def eventFilter(self, obj, event):
        """ https://stackoverflow.com/questions/71993533/
        how-to-initiate-context-menu-event-in-qgraphicsitem-from-qgraphicsview-context-m/72002453#72002453
        This is required to forward context menu event to graphics view items.
        I dont understand how it works yet! """

        if obj == self.ui.graphicsView.viewport() and event.type() == event.Type.ContextMenu:
            self.ui.graphicsView.contextMenuEvent(event)
            return event.isAccepted()
        return super().eventFilter(obj, event)

    def graphicsview_menu(self, position):
        item = self.ui.graphicsView.itemAt(position)
        if item is not None:
            print(item, type(item))
            self.scene.sendEvent(item)
            return
        # Menu for blank graphics view area
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        #action_print_items = menu.addAction(_("Print items"))
        action_add_category = menu.addAction(_("Add category"))
        action = menu.exec(self.ui.graphicsView.mapToGlobal(position))
        '''if action == action_print_items:
            print("\nPrint graphics items\n========")
            for i in self.scene.items():
                if isinstance(i, TextGraphicsItem):
                    print(f"Graphics item: {i.code_or_cat['name']} cid:{i.code_or_cat['cid']} "
                          f"ocid:{i.code_or_cat['original_cid']}"
                          f" catid:{i.code_or_cat['catid']} ocatid:{i.code_or_cat['original_catid']} "
                          f"supercatid:{i.code_or_cat['supercatid']} child names{i.code_or_cat['child_names']}")'''
        if action == action_add_category:
            global model
            cat_ids_list = []
            categories_ = []
            for item in model:
                if item['cid'] is None:
                    cat_ids_list.append(item['catid'])
            ui = DialogAddItemName(self.app, categories_, _("Category"), _("Category name"))
            ui.exec()
            new_category_name = ui.get_new_name()
            if new_category_name is None:
                return

            temp_cat_id = randint(-1000, -1)
            while temp_cat_id in cat_ids_list:
                temp_cat_id = randint(-1000, -1)
            now_date = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
            # No original_name, original_catid, original_supercatid, orignal-memo
            new_category = {'name': new_category_name, 'original_name': '', 'catid': temp_cat_id,
                            'owner': self.settings['codername'], 'date': now_date, 'memo': '', 'original_memo': '',
                            'supercatid': None, 'original_supercatid': None, 'x': 10 + randint(0, 6),
                            'y': 10 + randint(0, 6), 'color': "#FFFFFF", 'cid': None, 'child_names': [],
                            'original_cid': None,  'original_catid': temp_cat_id}
            model.append(new_category)
            self.scene.addItem(TextGraphicsItem(self.app, new_category))  # codes, categories))

    def export_image(self):
        """ Export the QGraphicsScene as a png image with transparent background.
        Called by QButton_export.
        """

        filename = "Graph.png"
        e_dir = ExportDirectoryPathDialog(self.app, filename)
        filepath = e_dir.filepath
        if filepath is None:
            return
        # Scene size is too big.
        max_x, max_y = self.scene.suggested_scene_size()
        rect_area = QtCore.QRectF(0.0, 0.0, max_x + 10, max_y + 10)  # Source area
        image = QtGui.QImage(int(max_x + 10), int(max_y + 10), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
        painter = QtGui.QPainter(image)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        # Render method requires QRectF NOT QRect. painter, target area, source area
        self.scene.render(painter, QtCore.QRectF(image.rect()), rect_area)
        painter.end()
        image.save(filepath)
        Message(self.app, _("Image exported"), filepath).exec()

    def apply_model_changes(self):
        """ Apply changes to database from model. """

        test = False
        global model
        if test:
            print("MODEL")
            for item in model:
                print(item)
            print("==========")
        # Merged new categories are not used. They are nameless. Remove from model.
        merged_new_categories = []
        for item in model:
            if item['catid'] is not None and item['catid'] < 0 and item['cid'] is None and item['name'] == "":
                merged_new_categories.append(item)
        for item in merged_new_categories:
            if test:
                print(f"Unused new merged CAT {item['catid']}")
            model.remove(item)
        # New categories to insert into database
        new_categories = []
        for item in model:
            if item['catid'] is not None and item['catid'] < 0 and item['cid'] is None:
                # Categories with '' as name are new categories that have been merged into other categories
                new_categories.append(item)
        cur = self.app.conn.cursor()
        # Insert new categories, update links to codes and pre-existing categories
        for category in new_categories:
            model.remove(category)
            try:
                cur.execute("insert into code_cat (name, memo, owner, date, supercatid) values(?,?,?,?,?)",
                            (category['name'], category['memo'], category['owner'], category['date'],
                             category['supercatid']))
                self.app.conn.commit()
            except sqlite3.IntegrityError as e_:
                print(e_, category['name'])
            cur.execute("select last_insert_rowid()")
            category['insert_id'] = cur.fetchone()[0]
            if test:
                print(f"NEW CAT INSERT {category['name']} {category['catid']} -> {category['insert_id']}")

            # Update remaining model code catids and pre-existing category supercatids
            for model_item in model:
                if model_item['catid'] == category['catid']:
                    model_item['catid'] = category['insert_id']
                if model_item['supercatid'] == category['catid']:
                    model_item['supercatid'] = category['insert_id']
        '''Test print("1 after insert new categories")
        cur.execute("select * from code_cat")
        res = cur.fetchall()
        for r in res:
            print(r)'''

        # Delete pre-existing categories from database, if they have been merged into other categories
        categories_to_delete = []
        for item in model:
            if item['delete'] is True and item['cid'] is None:
                categories_to_delete.append(item)
        for item in categories_to_delete:
            model.remove(item)
        for item in categories_to_delete:
            if test:
                print(f"CAT to DEL {item['name']} {item['original_name']} {item['catid']}")
            cur.execute("delete from code_cat where catid=?", [item['catid']])
            self.app.conn.commit()

        # Get inserted new categories where supercatid is < 0 and update these with insert_id
        cur.execute("select catid, supercatid, name from code_cat where supercatid < 0")
        res = cur.fetchall()
        for category_to_update in res:
            if test:
                print("Db cat to update (catid, supercatid)", category_to_update)
            for new_category in new_categories:
                if category_to_update[1] == new_category['catid']:
                    cur.execute("update code_cat set supercatid=? where catid=?", [new_category['insert_id'],
                                                                                   category_to_update[0]])
                    self.app.conn.commit()
        '''Test print("2 after  new category supercatid updates")
        cur.execute("select * from code_cat")
        res = cur.fetchall()
        for r in res:
            print(r)'''

        # Update codes and categories in model - catid, supercatid, name, memo
        for item in model:
            # Update pre-existing categories
            if item['catid'] is not None and item['cid'] is None:
                cur.execute("update code_cat set name=?, memo=?, supercatid=? where catid=?",
                            [item['name'], item['memo'], item['supercatid'], item['catid']])
                self.app.conn.commit()
            # Update codes, but avoid merged codes which are nameless
            if item['cid'] is not None and item['name'] != "":
                # A space was added to differentiate matching code - category names
                code_name = item['name']
                if item['name'][-1] == " ":
                    code_name = item['name'][:-1]
                cur.execute("update code_name set name=?, memo=?, catid=? where cid=?",
                            [code_name, item['memo'], item['catid'], item['cid']])
                self.app.conn.commit()
        '''Test print("3 after existing category and code updates")
        cur.execute("select * from code_cat")
        res = cur.fetchall()
        for r in res:
            print(r)'''

        # Update merged codes: coded text, images and A/V. Using new cid and original_cid
        for item in model:
            if item['cid'] is not None and item['name'] == "":
                if test:
                    print(f"Merging code: {item['original_name']} into {item['cid']}")
                self.update_merged_coded_segments(item['original_cid'], item['cid'])
        # Wrap up
        self.app.delete_backup = False
        self.parent_text_edit.append(_("Code tree re-organised."))
        self.hide()
        Message(self.app, "Code organiser", "Changes applied to the codes tree").exec()

    def update_merged_coded_segments(self, old_cid, new_cid):
        """ Update cid for each coded segment in text, A/V, image.
        Delete where there is a duplicate Integrity error.
        """

        cur = self.app.conn.cursor()
        ct_sql = "select ctid from code_text where cid=?"
        cur.execute(ct_sql, [old_cid])
        ct_res = cur.fetchall()
        for ct in ct_res:
            try:
                cur.execute("update code_text set cid=? where ctid=?", [new_cid, ct[0]])
            except sqlite3.IntegrityError as e_:
                # print(ct, e_)
                cur.execute("delete from code_text where ctid=?", [ct[0]])
        av_sql = "select avid from code_av where cid=?"
        cur.execute(av_sql, [old_cid])
        av_res = cur.fetchall()
        for av in av_res:
            try:
                cur.execute("update code_av set cid=? where avid=?", [new_cid, av[0]])
            except sqlite3.IntegrityError as e_:
                # print(e_)
                cur.execute("delete from code_av where avid=?", [av[0]])
        img_sql = "select imid from code_image where cid=?"
        cur.execute(img_sql, [old_cid])
        img_res = cur.fetchall()
        for img in img_res:
            try:
                cur.execute("update code_image set cid=? where imid=?", [new_cid, img[0]])
            except sqlite3.IntegrityError as e_:
                # print(e_)
                cur.execute("delete from code_image where imid=?", [img[0]])
        cur.execute("delete from code_name where cid=?", [old_cid, ])
        self.app.conn.commit()


class GraphicsScene(QtWidgets.QGraphicsScene):
    """ set the scene for the graphics objects and re-draw events. """

    scene_width = 990
    scene_height = 650
    parent = None

    def __init__(self, parent=None):
        super(GraphicsScene, self).__init__(parent)
        self.parent = parent
        self.setSceneRect(QtCore.QRectF(0, 0, self.scene_width, self.scene_height))

    def set_width(self, width):
        """ Resize scene width. """

        self.scene_width = width
        self.setSceneRect(QtCore.QRectF(0, 0, self.scene_width, self.scene_height))

    def set_height(self, height):
        """ Resize scene height. """

        self.scene_height = height
        self.setSceneRect(QtCore.QRectF(0, 0, self.scene_width, self.scene_height))

    def get_width(self):
        """ Return scene width. """

        return self.scene_width

    def get_height(self):
        """ Return scene height. """

        return self.scene_height

    def named_children_of_node(self, node):
        """ Get names of child categories and codes of this category node.
        Only keep the category or code name. Used to reposition TextGraphicsItems on moving a category.
        All category and code names are unique.

        param: node : Dictionary of category

        return: child_names : List
        """

        if node['cid'] is not None:
            return []
        child_names = []
        codes_ = []
        categories_ = []
        global model
        model_copy = deepcopy(model)
        for item in model_copy:
            if item['cid'] is None:
                categories_.append(item)
            else:
                codes_.append(item)

        """ Create a list of this category (node) and all its category children.
        Maximum depth of 200. """
        selected_categories = [node]
        i = 0  # Ensure an exit from loop
        new_model_changed = True
        while categories_ != [] and new_model_changed and i < 200:
            new_model_changed = False
            append_list = []
            for sel_category in selected_categories:
                for m in categories_:
                    if m['supercatid'] == sel_category['catid']:
                        append_list.append(m)
                        child_names.append(m['name'])
            for append_item in append_list:
                selected_categories.append(append_item)
                categories_.remove(append_item)
                new_model_changed = True
            i += 1
        categories_ = selected_categories
        # Remove codes that are not associated with these categories
        selected_codes = []
        for category in categories_:
            for code in codes_:
                if code['catid'] == category['catid']:
                    selected_codes.append(code)
        codes_ = selected_codes
        for code_ in codes_:
            child_names.append(code_['name'])
        return child_names

    def mouseMoveEvent(self, mouse_event):
        """ On mouse move, an item might be repositioned so need to redraw all the link_items.
        This slows re-drawing down, but is dynamic.
        """

        super(GraphicsScene, self).mousePressEvent(mouse_event)

        x_diff = 0
        y_diff = 0
        child_names = []
        # Garbage items for removal
        for item in self.items():
            if isinstance(item, TextGraphicsItem) and item.code_or_cat['name'] == "":
                self.removeItem(item)
        # Update code.catid or category.supercatid if a category has been merged into another category
        global model
        global update_graphics_item_models
        if update_graphics_item_models:
            for m_item in model:
                if m_item['original_cid'] is None:
                    m_item['child_names'] = self.named_children_of_node(m_item)
            for gr_item in self.items():
                if isinstance(gr_item, TextGraphicsItem):
                    for m_item in model:
                        # Update graphics codes items
                        if gr_item.code_or_cat['original_cid'] is not None and \
                                gr_item.code_or_cat['original_cid'] == m_item['original_cid']:
                            gr_item.code_or_cat = m_item
                            gr_item.set_text()
                        # Update graphics categories items
                        if gr_item.code_or_cat['original_cid'] is None and \
                                gr_item.code_or_cat['original_catid'] == m_item['original_catid']:
                            gr_item.set_text()

        # Check and update stored positions
        for item in self.items():
            if isinstance(item, TextGraphicsItem):
                if item.code_or_cat['x'] != item.pos().x() or item.code_or_cat['y'] != item.pos().y():
                    x_diff = item.pos().x() - item.code_or_cat['x']
                    item.code_or_cat['x'] = item.pos().x()
                    y_diff = item.pos().y() - item.code_or_cat['y']
                    item.code_or_cat['y'] = item.pos().y()
                    item.setPos(item.code_or_cat['x'], item.code_or_cat['y'])
                    child_names = item.code_or_cat['child_names']
                    break
        # Move child items of category
        if x_diff != 0 or y_diff != 0:
            for item in self.items():
                if isinstance(item, TextGraphicsItem) and item.code_or_cat['name'] in child_names:
                    item.code_or_cat['x'] += x_diff
                    item.code_or_cat['y'] += y_diff
                    item.setPos(item.code_or_cat['x'], item.code_or_cat['y'])

        self.remove_links()
        self.create_links()
        self.adjust_for_negative_positions()
        self.suggested_scene_size()
        self.update()

    '''def mousePressEvent(self, mouseEvent):
    super(GraphicsScene, self).mousePressEvent(mouseEvent)
    #position = QtCore.QPointF(event.scenePos())
    #logger.debug("pressed here: " + str(position.x()) + ", " + str(position.y()))
    for item in self.items(): # item is QGraphicsProxyWidget
        if isinstance(item, LinkItem):
            item.redraw()
    self.update(self.sceneRect())'''

    """def mouseReleaseEvent(self, mouseEvent):
        ''' On mouse release, an item might be repositioned so need to redraw all the
        link_items '''

        super(GraphicsScene, self).mouseReleaseEvent(mouseEvent)
        for item in self.items():
            if isinstance(item, LinkGraphicsItem):
                item.redraw()
        self.update(self.sceneRect())"""

    def remove_links(self):
        """ Clean up by removing all links and points. """

        for scene_item in self.items():
            if isinstance(scene_item, LinkGraphicsItem) or isinstance(scene_item, PointGraphicsItem):
                self.removeItem(scene_item)

    def create_links(self):
        """ Add links from Codes to Categories. And Categories to categories. """

        # Link from code to category
        for cat_item in self.items():
            if isinstance(cat_item, TextGraphicsItem):
                for code_item in self.items():
                    if isinstance(code_item, TextGraphicsItem) and code_item.code_or_cat['cid'] is not None and \
                            cat_item.code_or_cat['cid'] is None and \
                            cat_item.code_or_cat['catid'] == code_item.code_or_cat['catid']:
                        link_item = LinkGraphicsItem(cat_item, code_item)
                        self.addItem(link_item)
                        point_item = PointGraphicsItem(link_item.pointer_x, link_item.pointer_y)
                        self.addItem(point_item)

        # Link from Category to Category
        for item1 in self.items():
            if isinstance(item1, TextGraphicsItem):
                for item2 in self.items():
                    if isinstance(item2, TextGraphicsItem) and item1.code_or_cat['supercatid'] is not None and \
                            item1.code_or_cat['supercatid'] == item2.code_or_cat['catid'] and \
                            (item1.code_or_cat['cid'] is None and item2.code_or_cat['cid'] is None):
                        item = LinkGraphicsItem(item2, item1)
                        if item1.isVisible() and item2.isVisible():
                            self.addItem(item)
                            point_item = PointGraphicsItem(item.pointer_x, item.pointer_y)
                            self.addItem(point_item)

    def adjust_for_negative_positions(self):
        """ Move all items if negative positions. """

        min_adjust_x = 0
        min_adjust_y = 0
        for i in self.items():
            if i.pos().x() < min_adjust_x:
                min_adjust_x = i.pos().x()
            if i.pos().y() < min_adjust_x:
                min_adjust_y = i.pos().y()
        if min_adjust_x < 0 or min_adjust_y < 0:
            for i in self.items():
                if not isinstance(i, LinkGraphicsItem):
                    i.setPos(i.pos().x() - min_adjust_x, i.pos().y() - min_adjust_y)

    def suggested_scene_size(self):
        """ Calculate the maximum width and height from the current Items. """

        max_x = 0
        max_y = 0
        for i in self.items():
            if isinstance(i, TextGraphicsItem):
                if i.pos().x() + i.boundingRect().width() > max_x:
                    max_x = i.pos().x() + i.boundingRect().width()
                if i.pos().y() + i.boundingRect().height() > max_y:
                    max_y = i.pos().y() + i.boundingRect().height()
        self.setSceneRect(0, 0, max_x, max_y)
        return max_x, max_y


class TextGraphicsItem(QtWidgets.QGraphicsTextItem):
    """ The item show the name and color of the code or category
    Categories are shown white. A custom context menu
    allows selection of a code/category memo and displaying the information.
    """

    code_or_cat = None
    border_rect = None
    app = None
    settings = None

    def __init__(self, app, code_or_cat):
        """ Show name and colour of text. Has context menu for various options.
         :param: app  : the main App class
         :param: code_or_cat  : Dictionary of the code details: name, memo, color etc
         """

        super(TextGraphicsItem, self).__init__(None)
        self.app = app
        self.conn = app.conn
        self.settings = app.settings
        self.project_path = app.project_path
        self.code_or_cat = code_or_cat
        self.setPos(self.code_or_cat['x'], self.code_or_cat['y'])
        self.setFlags(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        # self.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextEditable)
        self.setDefaultTextColor(QtGui.QColor(TextColor(self.code_or_cat['color']).recommendation))
        self.setFont(QtGui.QFont(self.settings['font'], 9, QtGui.QFont.Weight.Normal))
        self.setToolTip(self.code_or_cat['memo'])
        self.set_text()

    def set_text(self):
        """ Set viewable text """

        text_ = self.code_or_cat['name']
        if self.app.settings['showids']:
            text_ += "\n"
            if self.code_or_cat['cid'] is not None:
                text_ += f"catid[{self.code_or_cat['catid']}] cid[{self.code_or_cat['cid']}]"
            if self.code_or_cat['cid'] is None:
                text_ += f"catid[{self.code_or_cat['catid']}]"
                text_ += f" supercatid[{self.code_or_cat['supercatid']}]"
        self.setPlainText(text_)

    def paint(self, painter, option, widget):
        """  """

        painter.save()
        color = QtGui.QColor(self.code_or_cat['color'])
        painter.setBrush(QtGui.QBrush(color, style=QtCore.Qt.BrushStyle.SolidPattern))
        painter.drawRect(self.boundingRect())
        painter.restore()
        super().paint(painter, option, widget)

    def contextMenuEvent(self, event):
        """
        # https://riverbankcomputing.com/pipermail/pyqt/2010-July/027094.html
        I was not able to mapToGlobal position so, the menu maps to scene position plus
        the Dialog screen position.
        """

        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        coded_action = None
        case_action = None
        link_code_to_category_action = None
        merge_code_into_code_action = None
        remove_code_from_category_action = None
        link_category_under_category_action = None
        merge_category_into_category_action = None
        remove_category_from_category_action = None
        if self.code_or_cat['cid'] is not None:
            link_code_to_category_action = menu.addAction(_('Link code to category'))
            merge_code_into_code_action = menu.addAction(_('Merge code into code'))
            if self.code_or_cat['catid'] is not None:
                remove_code_from_category_action = menu.addAction(_('Remove code from category'))
            coded_action = menu.addAction(_('Coded text and media'))
            case_action = menu.addAction(_('Case text and media'))
        if self.code_or_cat['cid'] is None:
            link_category_under_category_action = menu.addAction(_('Link category under category'))
            merge_category_into_category_action = menu.addAction(_('Merge category into category'))
            if self.code_or_cat['supercatid'] is not None:
                remove_category_from_category_action = menu.addAction(_('Remove category from category'))
        memo_action = menu.addAction(_('Memo'))
        rename_action = menu.addAction(_('Rename'))
        action = menu.exec(QtGui.QCursor.pos())
        if action is None:
            return
        if action == memo_action:
            self.update_memo()
        if action == rename_action:
            self.update_name()
        # Codes
        if action == coded_action:
            self.coded_media()
        if action == case_action:
            self.case_media()
        if action == link_code_to_category_action:
            self.link_code_to_category()
        if action == merge_code_into_code_action:
            self.merge_code_into_code()
        if action == remove_code_from_category_action:
            self.remove_code_from_category()
        # Categories
        if action == link_category_under_category_action:
            self.link_category_under_category()
        if action == merge_category_into_category_action:
            self.merge_category_into_category()
        if action == remove_category_from_category_action:
            self.remove_category_from_category()

    def update_name(self):
        """ Update name of code or category.
        Do not use allow use of any existing names, as these are also used for determining
         sub_categories, sub_codes of a node. """

        existing_names = []
        global model
        for item in model:
            existing_names.append({'name': item['name']})

        ui = DialogAddItemName(self.app, existing_names, _("Update name"), _("Name"))
        ok = ui.exec()
        if not ok:
            return
        name = ui.get_new_name()
        if name is None:
            return False
        self.code_or_cat['name'] = name
        self.set_text()
        for item in model:
            if item['cid'] == self.code_or_cat['cid'] and item['catid'] == self.code_or_cat['catid']:
                item['name'] = name
                break
        global update_graphics_item_models
        update_graphics_item_models = True

    def update_memo(self):
        """ Add or edit memos for codes and categories. """

        ui = DialogMemo(self.app, "Memo for Code " + self.code_or_cat['name'], self.code_or_cat['memo'])
        ok = ui.exec()
        if not ok:
            return
        self.code_or_cat['memo'] = ui.memo
        self.setToolTip(ui.memo)
        for item in model:
            if item['cid'] == self.code_or_cat['cid'] and item['catid'] == self.code_or_cat['catid']:
                item['memo'] = ui.memo
                break
        global update_graphics_item_models
        update_graphics_item_models = True

    def link_code_to_category(self):
        """ Link selected code to selected category. """

        categories_ = []
        global model
        for item in model:
            if item['cid'] is None and item['name'] != "":
                categories_.append(item)
        ui = DialogSelectItems(self.app, categories_, _('Link code: Select category'), 'single')
        ok = ui.exec()
        if not ok:
            return
        category = ui.get_selected()
        if not category:
            return
        for item in model:
            if item['cid'] == self.code_or_cat['cid']:
                item['catid'] = category['catid']
                break
        global update_graphics_item_models
        update_graphics_item_models = True
        self.code_or_cat['catid'] = category['catid']

    def merge_code_into_code(self):
        """ Merge code into another code.
         Keep nameless code in model. """

        unsorted_codes = []
        global model
        for item in model:
            if item['cid'] is not None and item['cid'] != self.code_or_cat['cid'] and item['name'] != "":
                unsorted_codes.append(item)
        # Sort codes alphabetically
        codes = sorted(unsorted_codes, key=lambda d: d['name'])
        ui = DialogSelectItems(self.app, codes, _('Merge into: Select code'), 'single')
        ok = ui.exec()
        if not ok:
            return
        merge_code = ui.get_selected()
        if not merge_code:
            return
        placeholder_cid = self.code_or_cat['cid']
        # Multiple codes can be affected.
        # e.g. code1 merged into code2. Then code2 merged into code3/
        for item in model:
            if item['cid'] == placeholder_cid: #self.code_or_cat['cid']:
                item['cid'] = merge_code['cid']
                item['name'] = ""

        self.code_or_cat['cid'] = merge_code['cid']
        self.code_or_cat['name'] = ""
        self.hide()
        global update_graphics_item_models
        update_graphics_item_models = True

    def remove_code_from_category(self):
        """ Remove code from category as top level item. """

        self.code_or_cat['catid'] = None
        global model
        for item in model:
            if item['cid'] == self.code_or_cat['cid']:
                item['catid'] = None
                break
        global update_graphics_item_models
        update_graphics_item_models = True

    def case_media(self, ):
        """ Display all coded text and media for this code.
        Codings come from ALL files and ALL coders.
        TODO Will not be current if codes are merged in. """

        DialogCodeInAllFiles(self.app, self.code_or_cat, "Case")

    def coded_media(self, ):
        """ Display all coded media for this code.
        Coded media comes from ALL files and current coder.
        TODO Will not be current of codes are merged it. """

        DialogCodeInAllFiles(self.app, self.code_or_cat)

    def link_category_under_category(self):
        """ Link category under another category.
         Use child_names list to prevent circular linkages. """

        categories_ = []
        global model
        for item in model:
            if item['catid'] != self.code_or_cat['catid'] and item['name'] != "" and item['cid'] is None and \
                    item['name'] not in self.code_or_cat['child_names']:
                categories_.append(item)

        ui = DialogSelectItems(self.app, categories_, _('Link under: Select category'), 'single')
        ok = ui.exec()
        if not ok:
            return
        category = ui.get_selected()
        if not category:
            return
        self.code_or_cat['supercatid'] = category['catid']
        for item in model:
            if item['catid'] == self.code_or_cat['catid']:
                item['supercatid'] = category['catid']
        global update_graphics_item_models
        update_graphics_item_models = True

    def merge_category_into_category(self):
        """ Merge category into another category.
         Use child_names list to prevent circular linkages. """

        categories = []
        global model
        for item in model:
            if item['catid'] != self.code_or_cat['catid'] and item['name'] != "" and item['cid'] is None and \
                    item['name'] not in self.code_or_cat['child_names']:
                categories.append(item)
        ui = DialogSelectItems(self.app, categories, _('Merge into: Select category'), 'single')
        ok = ui.exec()
        if not ok:
            return
        merge_category = ui.get_selected()
        if not merge_category:
            return
        # Update subcategories and codes of this category
        for item in model:
            if item['supercatid'] == self.code_or_cat['catid']:
                item['supercatid'] = merge_category['catid']
            if item['catid'] == self.code_or_cat['catid'] and item['cid'] is not None:
                item['catid'] = merge_category['catid']

        # Update this item in model
        for item in model:
            if item['catid'] == self.code_or_cat['catid'] and item['cid'] is None:
                item['name'] = ""
                item['delete'] = True  # Flag to delete from database, if pre-exisitng category
                break
        self.code_or_cat['name'] = ""
        self.hide()
        global update_graphics_item_models
        update_graphics_item_models = True

    def remove_category_from_category(self):
        """ Remove category from category as top level item. """

        self.code_or_cat['supercatid'] = None
        for item in model:
            if item['catid'] == self.code_or_cat['catid']:
                item['supercatid'] = None
        global update_graphics_item_models
        update_graphics_item_models = True


class LinkGraphicsItem(QtWidgets.QGraphicsLineItem):
    """ Takes the coordinate from the two TextGraphicsItems. """

    from_widget = None
    from_pos = None
    to_widget = None
    to_pos = None
    pointer_x = 0
    pointer_y = 0

    def __init__(self, from_widget, to_widget):
        """ Links codes and categories. Called when codes or categories of categories are inserted.
         param: from_widget  : TextGraphicsItem
         param: to_widget : TextGraphicsItem
        """
        super(LinkGraphicsItem, self).__init__(None)

        self.from_widget = from_widget
        self.to_widget = to_widget
        # self.setFlags(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.calculate_points_and_draw()
        self.redraw()

    def redraw(self):
        """ Called from mouse move and release events. """

        self.calculate_points_and_draw()

    def calculate_points_and_draw(self):
        """ Calculate the to x and y and from x and y points. Draw line between the
        widgets. Join the line to appropriate side of widget. """

        to_x = self.to_widget.pos().x()
        to_y = self.to_widget.pos().y()
        from_x = self.from_widget.pos().x()
        from_y = self.from_widget.pos().y()

        x_overlap = False
        # Fix from_x value to middle of from widget if to_widget overlaps in x position
        if from_x < to_x < from_x + self.from_widget.boundingRect().width():
            from_x = from_x + self.from_widget.boundingRect().width() / 2
            x_overlap = True
        # Fix to_x value to middle of to widget if from_widget overlaps in x position
        if to_x < from_x < to_x + self.to_widget.boundingRect().width():
            to_x = to_x + self.to_widget.boundingRect().width() / 2
            x_overlap = True
        # Fix from_x value to right-hand side of from widget if to_widget on the right of the from_widget
        if not x_overlap and to_x > from_x + self.from_widget.boundingRect().width():
            from_x = from_x + self.from_widget.boundingRect().width()
        # Fix to_x value to right-hand side if from_widget on the right of the to widget
        elif not x_overlap and from_x > to_x + self.to_widget.boundingRect().width():
            to_x = to_x + self.to_widget.boundingRect().width()

        y_overlap = False
        # Fix from_y value to middle of from widget if to_widget overlaps in y position
        if from_y < to_y < from_y + self.from_widget.boundingRect().height():
            from_y = from_y + self.from_widget.boundingRect().height() / 2
            y_overlap = True
        # Fix from_y value to middle of to widget if from_widget overlaps in y position
        if to_y < from_y < to_y + self.to_widget.boundingRect().height():
            to_y = to_y + self.to_widget.boundingRect().height() / 2
            y_overlap = True
        # Fix from_y value if to_widget is above the from_widget
        if not y_overlap and to_y > from_y:
            from_y = from_y + self.from_widget.boundingRect().height()
        # Fix to_y value if from_widget is below the to widget
        elif not y_overlap and from_y > to_y:
            to_y = to_y + self.to_widget.boundingRect().height()
        self.setPen(QtGui.QPen(QtCore.Qt.GlobalColor.black, 1, QtCore.Qt.PenStyle.SolidLine))
        self.setLine(from_x, from_y, to_x, to_y)
        # Positions for drawing PointGraphicItem position
        self.pointer_x = from_x
        self.pointer_y = from_y


class PointGraphicsItem(QtWidgets.QGraphicsRectItem):
    """ Show a rectangle pointer at one end of a link line. """

    def __init__(self, x, y):
        """
         param: x  : Integer
         param: y : Integer
        """

        super(PointGraphicsItem, self).__init__(None)

        self.x = x
        self.y = y
        # self.setFlags(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.calculate_point_and_draw()
        self.redraw()

    def redraw(self):
        """ Called from mouse move and release events. """

        self.calculate_point_and_draw()

    def calculate_point_and_draw(self):
        """ Calculate the to x and y and from x and y points. Draw line between the
        widgets. Join the line to appropriate side of widget. """

        self.setPen(QtGui.QPen(QtCore.Qt.GlobalColor.darkGray, 2, QtCore.Qt.PenStyle.SolidLine))
        self.setRect(self.x - 1, self.y - 1, 2, 2)
