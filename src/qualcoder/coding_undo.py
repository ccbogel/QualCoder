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

Authors: Colin Curtain C, Kai Dröge, Justin Missaghieh--Poncet, Lorenzo Salomón
https://github.com/ccbogel/QualCoder
https://qualcoder.wordpress.com/
https://qualcoder-org.github.io
https://qualcoder.org/

Undo and redo for codings and for the code tree (tables code_text, code_image,
code_av, code_name, code_cat and the saved graph items that point at codes).

One QUndoStack per open project lives in App.coding_undo. A dialog keeps its own
SQL untouched and only brackets it:

    token = self.app.coding_undo.begin(_("Code 'x'"), "code_text", file_id)
    ... existing inserts, updates, deletes and commit ...
    self.app.coding_undo.end(token)

begin() snapshots the rows of the tables (only one file, or only some codes,
when the caller knows the scope) and end() compares them with the rows found
afterwards. Whatever changed in between becomes one undoable step, so deleting
a code with its codings or merging two codes is still a single Ctrl+Z.

Undo and redo rewrite rows by primary key inside one transaction, deleting
children first, then inserting parents first, then updating. Before writing,
the current rows are compared with what the step expects, and rows going back
in must still point to an existing code, category and file. If anything
differs, nothing is written and the whole history is cleared with a message,
so a stale step can never overwrite work done in a module that does not report
to this stack.
"""

import logging
import sqlite3
import sys

from PyQt6 import QtCore, QtGui

logger = logging.getLogger(__name__)

# Tracked tables in insert order (parents first). Each entry gives the primary
# key, the column holding the source file id, and the column holding the code id
# used to narrow a snapshot. None means the table is always snapshotted whole.
TRACKED_TABLES = {
    "code_cat": ("catid", None, None),
    "code_name": ("cid", None, None),
    "code_av": ("avid", "id", "cid"),
    "code_image": ("imid", "id", "cid"),
    "code_text": ("ctid", "fid", "cid"),
    "gr_cdct_text_item": ("gtextid", None, None),
    "gr_cdct_line_item": ("glineid", None, None),
    "gr_free_line_item": ("gflineid", None, None),
}
CODING_TABLES = ("code_av", "code_image", "code_text")
# Tables touched by delete and merge operations of the code tree
CODE_TREE_TABLES = tuple(TRACKED_TABLES)
# Tables touched by create, rename, memo, color and move operations of the tree
TREE_TABLES = ("code_cat", "code_name")
# Rows going back in must still point somewhere: (column, table, key, may be null)
REFERENCES = {
    "code_cat": (("supercatid", "code_cat", "catid", True),),
    "code_name": (("catid", "code_cat", "catid", True), ("supercid", "code_name", "cid", True)),
    "code_av": (("cid", "code_name", "cid", False), ("id", "source", "id", False)),
    "code_image": (("cid", "code_name", "cid", False), ("id", "source", "id", False)),
    "code_text": (("cid", "code_name", "cid", False), ("fid", "source", "id", False)),
}
UNDO_LIMIT = 200


def undo_label(action, code_name=None, file_name=None):
    """Build a history entry such as: Code 'fear' (interview1.txt)."""

    text = action
    if code_name:
        text += f" '{code_name}'"
    if file_name:
        text += f" ({file_name})"
    return text


def missing_reference_message(ref_table):
    """Message for a row that cannot go back in because its parent row is gone."""

    if ref_table == "code_cat":
        return _("A category used in the coding history no longer exists. The history has been cleared.")
    if ref_table == "source":
        return _("A file used in the coding history no longer exists. The history has been cleared.")
    return _("A code used in the coding history no longer exists. The history has been cleared.")


class CodingUndoError(Exception):
    """Raised when a step no longer matches the database and must not be applied."""


class _Token:
    """Snapshot taken by begin(), consumed by end()."""

    def __init__(self, text, snapshots, merge_key=None, nested=False):
        self.text = text
        self.snapshots = snapshots  # [(table, scope, columns, {pk: row})]
        self.merge_key = merge_key
        self.nested = nested  # opened while an outer step was already recording
        self.frame = None  # caller frame, to tell a live outer step from a stale one


class CodingUndoCommand(QtGui.QUndoCommand):
    """One undoable step: rows of some tables before and after a change."""

    def __init__(self, manager, text, changes, merge_id=-1):
        super().__init__(text)
        self._manager = manager
        self._changes = changes  # [(table, columns, before, after)]
        self._merge_id = merge_id
        self._already_applied = True  # the dialog ran the SQL before the push

    def id(self):
        return self._merge_id

    def mergeWith(self, other):
        """Fold a consecutive step with the same merge key into this one."""

        if not isinstance(other, CodingUndoCommand) or other._merge_id != self._merge_id:
            return False
        merged = {table: [columns, dict(before), dict(after)] for table, columns, before, after in self._changes}
        for table, columns, before, after in other._changes:
            entry = merged.setdefault(table, [columns, {}, {}])
            for key, row in before.items():
                entry[1].setdefault(key, row)
            entry[2].update(after)
        self._changes = [(table, columns, before, after) for table, (columns, before, after) in merged.items()]
        return True

    def redo(self):
        if self._already_applied:
            self._already_applied = False
            return
        self._manager.apply_changes(self._changes, forward=True)

    def undo(self):
        self._manager.apply_changes(self._changes, forward=False)


class CodingUndoManager(QtCore.QObject):
    """Project-wide undo stack for coding changes. Created once in App."""

    # Emitted after the history had to be discarded; carries a message for the user
    invalidated = QtCore.pyqtSignal(str)

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.stack = QtGui.QUndoStack(self)
        self.stack.setUndoLimit(UNDO_LIMIT)
        self._pending_invalidation = None
        self._merge_ids = {}
        self._active = None  # outermost token currently recording

    # Recording

    def begin(self, text, tables, file_id=None, code_ids=None, merge_key=None):
        """Snapshot tables before a change. Returns a token for end(), or None.

        A begin() reached while an outer begin() of the same call chain is still
        recording returns a nested token, so helper functions can bracket their own
        SQL and still fold into the caller's single step.

        Args:
            text: Description shown in the Edit menu.
            tables: Table name or list of names from TRACKED_TABLES.
            file_id: Restrict coding tables to one file when the change is file-local.
                A dict {table: file_id} scopes each table separately.
            code_ids: Restrict coding tables to these codes, e.g. a delete or merge.
            merge_key: Consecutive steps with the same hashable key collapse into one,
                e.g. repeated keyboard resizes of the same coding.
        """

        if self.app.conn is None:
            return None
        if self._active is not None and self._frame_is_live(self._active.frame):
            return _Token(text, [], nested=True)
        self._active = None
        if isinstance(tables, str):
            tables = [tables]
        snapshots = []
        for table in tables:
            table_file = file_id.get(table) if isinstance(file_id, dict) else file_id
            scope = (table_file, tuple(code_ids) if code_ids else None)
            try:
                columns, rows = self._snapshot(table, scope)
            except sqlite3.OperationalError as err:
                logger.warning("Coding undo skipped table %s: %s", table, err)
                continue
            except (sqlite3.Error, KeyError) as err:
                logger.warning("Coding undo snapshot skipped: %s", err)
                return None
            snapshots.append((table, scope, columns, rows))
        if not snapshots:
            return None
        token = _Token(text, snapshots, merge_key)
        token.frame = sys._getframe(1)
        self._active = token
        return token

    def end(self, token, text=None):
        """Diff against the token snapshot and push one step if rows changed.

        Returns True when a step was pushed.
        """

        if token is None or token.nested or self.app.conn is None:
            return False
        if self._active is token:
            self._active = None
        changes = []
        try:
            for table, scope, columns, before in token.snapshots:
                columns_now, after = self._snapshot(table, scope)
                if columns_now != columns:
                    logger.warning("Coding undo skipped, columns of %s changed", table)
                    return False
                diff_before, diff_after = self._diff(before, after)
                if diff_before or diff_after:
                    changes.append((table, columns, diff_before, diff_after))
        except sqlite3.Error as err:
            logger.warning("Coding undo diff skipped: %s", err)
            return False
        if not changes:
            return False
        merge_id = -1
        if token.merge_key is not None:
            merge_id = self._merge_ids.setdefault(token.merge_key, len(self._merge_ids) + 1)
        self.stack.push(CodingUndoCommand(self, text or token.text, changes, merge_id))
        return True

    def clear(self):
        """Discard the whole history, e.g. when a project is closed or the coder changes."""

        self.stack.clear()
        self._merge_ids = {}
        self._active = None

    # Applying steps

    def apply_changes(self, changes, forward):
        """Write the before or after rows of a step. Called by the command only."""

        conn = self.app.conn
        if conn is None:
            self._schedule_invalidation(_("No project is open."))
            return
        cur = conn.cursor()
        try:
            for table, columns, before, after in changes:
                expected = before if forward else after
                self._verify(cur, table, columns, expected)
            self._write_all(cur, changes, forward)
            conn.commit()
        except CodingUndoError as err:
            conn.rollback()
            self._schedule_invalidation(str(err))
            return
        except sqlite3.Error as err:
            conn.rollback()
            logger.exception("Coding undo failed")
            self._schedule_invalidation(str(err))
            return
        self.app.delete_backup = False
        tables = [change[0] for change in changes]
        self.app.project_events.emit_table_changes(tables, source=self)

    # Helpers

    @staticmethod
    def _frame_is_live(frame):
        """True while the function that called begin() is still on the call stack."""

        current = sys._getframe(2)
        while current is not None:
            if current is frame:
                return True
            current = current.f_back
        return False

    def _snapshot(self, table, scope):
        """Return (columns, {pk: row tuple}) for a table, narrowed by file or codes when possible."""

        pk_column, file_column, code_column = TRACKED_TABLES[table]
        file_id, code_ids = scope
        conditions, values = [], []
        if file_id is not None and file_column is not None:
            conditions.append(f"{file_column}=?")
            values.append(file_id)
        if code_ids and code_column is not None:
            conditions.append(f"{code_column} in ({','.join('?' * len(code_ids))})")
            values.extend(code_ids)
        sql = f"select * from {table}"
        if conditions:
            sql += " where " + " and ".join(conditions)
        cur = self.app.conn.cursor()
        cur.execute(sql, values)
        columns = [d[0] for d in cur.description]
        pk_index = columns.index(pk_column)
        rows = {row[pk_index]: tuple(row) for row in cur.fetchall()}
        return columns, rows

    @staticmethod
    def _diff(before, after):
        """Rows that differ between two snapshots; a missing row is None."""

        diff_before = {}
        diff_after = {}
        for key in set(before) | set(after):
            row_before = before.get(key)
            row_after = after.get(key)
            if row_before != row_after:
                diff_before[key] = row_before
                diff_after[key] = row_after
        return diff_before, diff_after

    def _verify(self, cur, table, columns, expected):
        """Raise CodingUndoError unless every expected row is exactly as stored now."""

        pk_column = TRACKED_TABLES[table][0]
        column_list = ",".join(columns)
        for key, row in expected.items():
            cur.execute(f"select {column_list} from {table} where {pk_column}=?", [key])
            current = cur.fetchone()
            current = tuple(current) if current is not None else None
            if current != row:
                raise CodingUndoError(
                    _("The codings were changed by another part of QualCoder, so the coding history "
                      "no longer matches the project. The history has been cleared."))

    def _write_all(self, cur, changes, forward):
        """Deletes children first, then inserts parents first, then updates."""

        order = list(TRACKED_TABLES)
        deletes, updates, inserts = [], [], []
        for table, columns, before, after in changes:
            src, dst = (before, after) if forward else (after, before)
            for key in set(src) | set(dst):
                row_dst = dst.get(key)
                row_src = src.get(key)
                if row_dst is None:
                    deletes.append((table, key))
                elif row_src is None:
                    inserts.append((table, columns, row_dst))
                else:
                    updates.append((table, columns, key, row_dst))
        deletes.sort(key=lambda item: order.index(item[0]), reverse=True)
        for table, key in deletes:
            pk_column = TRACKED_TABLES[table][0]
            cur.execute(f"delete from {table} where {pk_column}=?", [key])
        inserts.sort(key=lambda item: order.index(item[0]))
        for table, columns, row in inserts:
            self._check_references(cur, table, columns, row)
            placeholders = ",".join("?" * len(columns))
            cur.execute(f"insert into {table} ({','.join(columns)}) values ({placeholders})", row)
        updates.sort(key=lambda item: order.index(item[0]))
        for table, columns, key, row in updates:
            self._check_references(cur, table, columns, row)
            pk_column = TRACKED_TABLES[table][0]
            assignments = ", ".join(f"{c}=?" for c in columns if c != pk_column)
            values = [v for c, v in zip(columns, row) if c != pk_column] + [key]
            cur.execute(f"update {table} set {assignments} where {pk_column}=?", values)

    def _check_references(self, cur, table, columns, row):
        """Raise CodingUndoError if the row points to a deleted code, category or file."""

        values = dict(zip(columns, row))
        for column, ref_table, ref_key, nullable in REFERENCES.get(table, ()):
            value = values.get(column)
            if value is None and nullable:
                continue
            cur.execute(f"select 1 from {ref_table} where {ref_key}=?", [value])
            if cur.fetchone() is None:
                raise CodingUndoError(missing_reference_message(ref_table))

    def _schedule_invalidation(self, message):
        """Clear the stack after the running command returns; clearing inside it is unsafe."""

        if self._pending_invalidation is not None:
            return
        self._pending_invalidation = message
        QtCore.QTimer.singleShot(0, self._run_invalidation)

    @QtCore.pyqtSlot()
    def _run_invalidation(self):
        message = self._pending_invalidation
        self._pending_invalidation = None
        self.stack.clear()
        logger.warning("Coding history cleared: %s", message)
        self.invalidated.emit(message)
