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
https://qualcoder.wordpress.com/
https://qualcoder-org.github.io/
"""

import datetime
import html
import logging
import os
import re
import sqlite3

from PyQt6 import QtWidgets

from .helpers import Message

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


class TaguetteImport:
    """ Import from a Taguette.sqlite3 database into a new QualCoder database.
    Thanks to Lornzo Salomón for creating the intial code for this. """

    def __init__(self, app, parent_textedit):
        super(TaguetteImport, self).__init__()

        self.app = app
        self.parent_textEdit = parent_textedit
        response = QtWidgets.QFileDialog.getOpenFileName(None, _('Select Taguette file'),
                                                         self.app.settings['directory'], "*.sqlite3")
        # options=QtWidgets.QFileDialog.Option.DontUseNativeDialog)
        if response[0] == "":
            return
        self.file_path = response[0]
        self.conn_tag = sqlite3.connect(self.file_path)
        self.parent_textEdit.append(_("Beginning import from Taguette.sqlite3"))
        self.parent_textEdit.append(self.file_path)
        is_taguette = self.check_is_taguette()
        if is_taguette:
            project = self.select_project()  # For now assume one project in sqlite
            if project is not None:
                self.import_data(project)
                 # Update vectorstore
                if self.app.settings['ai_enable'] == 'True':
                    self.app.ai.sources_vectorstore.update_vectorstore()
            else:
                msg = _("No project selected") + _(" from: ") + self.file_path
                self.parent_textEdit.append(msg)
        else:
            msg = _("Cannot import from ") + f"{self.file_path}\n"
            msg += _("Expected Taguette sqlite. Required database tables are missing.")
            self.parent_textEdit.append(msg)

    def select_project(self):
        """ Taguette sqlite can contain multiple projects.
        Only have access to a test database with one project.
        For now, assume only one project will be in the sqlite database.
        Select one for import. Datetime format: yyyy-mm-dd hh:mm:ss.000000
        Return:
            Selected project Dictionary
        """

        cur_tag = self.conn_tag.cursor()
        cur_tag.execute("select id, name, description, substr(created,1,19) from projects")
        results = cur_tag.fetchall()
        keys = 'id','name','description', 'created'
        projects = []
        for row in results:
            projects.append(dict(zip(keys, row)))
        # print(results)
        return projects[0]
        # Until more real databases to test, assume only one project in Taguete.sqlite3
        '''if len(projects) == 1:
            return projects[0]
        ui = DialogSelectItems(self.app, projects, _("Select project to import"), "single")
        ok = ui.exec()
        if not ok:
            return
        selected = ui.get_selected()
        return selected'''

    def check_is_taguette(self):
        """ Check anticipated tables are present. """

        cur_tag = self.conn_tag.cursor()
        cur_tag.execute("select name from sqlite_master where type='table'")
        res = cur_tag.fetchall()
        tables = []
        for r in res:
            tables.append(r[0])
        # print(tables)
        if 'project_members' in tables and 'projects' in tables and 'documents' in tables and 'tags' in tables and \
            'highlights' in tables and 'highlight_tags' in tables and 'commands' in tables:
            return True
        else:
            return False

    # Import functions
    def html_to_plain_text(self, raw_html:str) -> str:
        """ Limpia las etiquetas HTML, decodifica entidades y arregla
        las 'sangrías fantasma' para que el texto sea plano y limpio.
        Clean HTML tags, decode entities and fix 'ghost indents' to make the text flat and clean.
        Args:
            raw_html : string
        Return:
            text : string
        """

        if not raw_html:
            return ""
        # 1. Normalizar saltos de línea de Windows a Unix. Normalise line breaks.
        text = raw_html.replace('\r\n', '\n')
        # 2. Reemplazar etiquetas de bloque principales con saltos de línea
        # Replace parent block tags with line breaks
        text = re.sub(r'</?(p|br|div|li|ul|ol|h[1-6])[^>]*>', '\n', text, flags=re.IGNORECASE)
        # 3. Eliminar todas las demás etiquetas HTML. Remove HTML tags.
        text = re.sub(r'<.*?>', '', text)
        # 4. Decodificar entidades HTML (ej. &nbsp; -> espacio, &aacute; -> á)
        text = html.unescape(text)
        # 5. Arreglar sangrías fantasma: eliminar espacios/tabs justo después de un salto de línea
        # Fix ghost indents: remove spaces/tabs right after a line break
        text = re.sub(r'\n[ \t]+', '\n', text)
        # 6. Eliminar múltiples saltos de línea vacíos excesivos (deja máximo 2)
        # Remove multiple excessive empty line breaks (leave maximum 2)
        text = re.sub(r'\n{3,}', '\n\n', text)
        # 7. Limpiar espacios al inicio y final del documento. Clear spaces at the beginning and end.
        return text.strip()

    def find_best_match(self, clean_doc, snippet_html, original_start, original_end):
        """
        Busca el fragmento codificado EXACTO dentro del texto limpio
        para encontrar sus nuevas coordenadas, evitando el desfasamiento.
        Find the EXACT encoded fragment within the clean text to find its new coordinates,
        avoiding phase shift.
        Args:
            clean_doc : String
            snippet_html : String of coded html snippet
            original_start : Integer start of html coding
            original_end : Integer end of html coding
        Return:
            safe_start : Integer : new start pos
            safe_end : Integer : new end pos
            clean_doc[safe_start:safe_end] : String : new (correct) text
        """
        # Limpiar el fragmento subrayado usando la misma lógica. Clean the html fragment.
        clean_snip = self.html_to_plain_text(snippet_html).strip()

        if not clean_snip:
            # Fallback de seguridad
            safe_start = min(max(0, original_start), len(clean_doc))
            safe_end = min(max(0, original_end), len(clean_doc))
            return safe_start, safe_end, clean_doc[safe_start:safe_end]

        # Buscar todas las apariciones de este texto exacto en el documento limpio
        # Find all occurrences of this exact text in the clean document
        matches = [m.start() for m in re.finditer(re.escape(clean_snip), clean_doc)]
        if matches:
            # Si el texto aparece varias veces en el documento,
            # elegimos el que esté más cerca de la posición original de Taguette
            # If the text appears multiple times in the document,choose the one that is closest to
            # Taguette's original position
            best_idx = min(matches, key=lambda x: abs(x - original_start))
            return best_idx, best_idx + len(clean_snip), clean_snip
        else:
            # Si no hay coincidencia exacta (por algún salto de línea perdido o espacio doble),
            # hacemos una búsqueda flexible ignorando los espacios en blanco.
            # If there is no exact match (due to a missing line break or double space),
            # Do a flexible search ignoring whitespace.
            words = clean_snip.split()
            if words:
                regex_snip = r'\s+'.join(re.escape(w) for w in words)
                try:
                    flex_matches = [(m.start(), m.end()) for m in re.finditer(regex_snip, clean_doc)]
                    if flex_matches:
                        best_m = min(flex_matches, key=lambda x: abs(x[0] - original_start))
                        return best_m[0], best_m[1], clean_doc[best_m[0]:best_m[1]]
                except Exception as e_:
                    print(e_)

            # Último recurso absoluto: usar posiciones originales limitadas al tamaño del texto
            # Absolute last resort: use original positions limited to text size
            safe_start = min(max(0, original_start), len(clean_doc))
            safe_end = min(max(0, original_end), len(clean_doc))
            return safe_start, safe_end, clean_doc[safe_start:safe_end]

    def import_data(self, project):
        """
        Args:
            project : Dict of id, name, description, creation date
         """

        cur_qc = self.app.conn.cursor()
        memo = f"Migrated from Taguette.\n {project['description']}"
        cur_qc.execute("update project set memo=?", [memo])
        self.parent_textEdit.append(_("Project memo imported"))
        self.app.conn.commit()

        cur_tag = self.conn_tag.cursor()
        # Obtenemos también el "snippet" (el texto resaltado) que nos servirá como ancla
        # Obtain the "snippet" (the highlighted text) that will serve as an anchor
        cur_tag.execute("""
                SELECT h.document_id, ht.tag_id, h.start_offset, h.end_offset, h.snippet 
                FROM highlights h
                JOIN highlight_tags ht ON h.id = ht.highlight_id
            """)
        raw_codings = cur_tag.fetchall()
        # Organise codings to documents
        codings_by_doc = {}
        for row in raw_codings:
            doc_id, tag_id, start, end, snippet = row
            if doc_id not in codings_by_doc:
                codings_by_doc[doc_id] = []
            codings_by_doc[doc_id].append((tag_id, start, end, snippet))
        # print("Migrando documentos y anclando fragmentos...")
        cur_tag.execute("select id, name, description, contents from documents")
        documents = cur_tag.fetchall()
        final_codings = []
        nowdate = datetime.datetime.now().astimezone().strftime("%Y%m%d_%H")
        owner = self.app.settings['codername']
        for doc in documents:
            doc_id, name, memo, html_contents = doc
            html_contents = html_contents if html_contents else ""
            memo = memo if memo else ""
            doc_codings = codings_by_doc.get(doc_id, [])
            # Formatear el texto completo sin sangrías molestas. Insert clean text documents.
            clean_text = self.html_to_plain_text(html_contents)
            try:
                cur_qc.execute("insert into source (id, name, fulltext,memo, owner, date, mediapath) values (?,?,?,?,?,?,?)",
                              [doc_id, name, clean_text, memo, owner, nowdate, None])
                self.app.conn.commit()
            except sqlite3.IntegrityError as err:
                print(err)
                logger.warning(err)
            # Buscar la coordenada exacta para cada codificación. Find the exact coordinate for each coding.
            for coding in doc_codings:
                tag_id, start, end, snippet_html = coding

                new_start, new_end, seltext = self.find_best_match(clean_text, snippet_html, start, end)
                final_codings.append((tag_id, doc_id, seltext, new_start, new_end))
        self.parent_textEdit.append(str(len(documents)) + _(" documents imported"))

        # Insert tags (codes)
        # print("Migrando etiquetas (códigos)")
        cur_tag.execute("select id, path, description from tags")
        tags = cur_tag.fetchall()
        for tag in tags:
            tag_id, name, memo = tag
            memo = memo if memo else ""
            code_color = "#DDE600"  # Strong yellow-green
            try:
                cur_qc.execute("insert into code_name (cid, catid,name, memo,color, owner, date) "
                               "values (?,null,?,?,?,?,?)",
                              [tag_id, name, memo, code_color, owner, nowdate])
            except sqlite3.IntegrityError as err:
                logger.warning(f"Codename: {name} : {err}")
        self.app.conn.commit()
        self.parent_textEdit.append(str(len(tags)) + _(" codes imported"))

        # print("Insertando fragmentos con coordenadas ancladas")
        i = 0
        for coding in final_codings:
            cid, doc_id, seltext, pos0, pos1 = coding
            try:
                cur_qc.execute(
                    "insert into code_text (cid, fid,seltext, pos0,pos1,memo, owner, date) values (?,?,?,?,?,?,?,?)",
                    [cid, doc_id, seltext, pos0, pos1, "", owner, nowdate])
                # Commit individually, to allow each entry to be final, and errors to be skipped
                self.app.conn.commit()
                i += 1
            except sqlite3.IntegrityError as err:
                msg = f"Not imported! cid:{cid}, fid{doc_id} pos0: {pos0} pos1:{pos1} Err: {err}"
                logger.warning(msg)
                self.parent_textEdit.append(msg)

        self.parent_textEdit.append(str(i) + _(" codings imported"))
        self.conn_tag.close()
        self.parent_textEdit.append(_("Taguette project imported"))
        Message(self.app, _("Taguette imported"), _("Taguette imported")).exec()
        self.app.write_config_ini(self.app.settings, self.app.ai_models)

        # print(f"\n¡Éxito! El proyecto se ha convertido y guardado como: {rqda_path}")
        '''# Keep a copy of the text sources in the QualCoder documents folder
        cur_qc.execute("select name, file from source")
        res = cur_qc.fetchall()
        for r in res:
            name = f"{r[0]}.txt"
            destination = f"{self.app.project_path}/documents/{name}"
            with open(destination, 'w', encoding='utf-8-sig') as file_:
                file_.write(r[1])
            logger.info(f"Text file exported to {destination}")'''


"""
Taguette database format - except users, alembic tables

CREATE TABLE projects (
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        name VARCHAR(200) NOT NULL,
        description TEXT NOT NULL,
        created DATETIME NOT NULL
);
CREATE TABLE sqlite_sequence(name,seq);
CREATE TABLE project_members (
        project_id INTEGER NOT NULL,
        user_login VARCHAR(30) NOT NULL,
        privileges VARCHAR(11) NOT NULL,
        CONSTRAINT pk_project_members PRIMARY KEY (project_id, user_login),
        CONSTRAINT fk_project_members_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE,
        CONSTRAINT fk_project_members_user_login_users FOREIGN KEY(user_login) REFERENCES users (login) ON DELETE CASCADE ON UPDATE CASCADE
);
CREATE INDEX ix_project_members_project_id ON project_members (project_id);
CREATE INDEX ix_project_members_user_login ON project_members (user_login);
CREATE TABLE documents (
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        name VARCHAR(200) NOT NULL,
        description TEXT NOT NULL,
        filename VARCHAR(200) NOT NULL,
        created DATETIME NOT NULL,
        project_id INTEGER NOT NULL,
        text_direction VARCHAR(13) NOT NULL,
        contents TEXT NOT NULL,
        CONSTRAINT fk_documents_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE
);
CREATE INDEX ix_documents_project_id ON documents (project_id);
CREATE TABLE commands (
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        date DATETIME NOT NULL,
        user_login VARCHAR(30) NOT NULL,
        project_id INTEGER NOT NULL,
        document_id INTEGER,
        payload TEXT NOT NULL,
        CONSTRAINT fk_commands_user_login_users FOREIGN KEY(user_login) REFERENCES users (login) ON UPDATE CASCADE,
        CONSTRAINT fk_commands_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE
);
CREATE INDEX idx_project_document ON commands (project_id, document_id);
CREATE INDEX ix_commands_document_id ON commands (document_id);
CREATE INDEX ix_commands_project_id ON commands (project_id);
CREATE INDEX ix_commands_date ON commands (date);
CREATE INDEX idx_project_id ON commands (project_id, id);
CREATE INDEX ix_commands_user_login ON commands (user_login);
CREATE TABLE tags (
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        path VARCHAR(200) NOT NULL,
        description TEXT NOT NULL,
        CONSTRAINT uq_tags_project_id UNIQUE (project_id, path),
        CONSTRAINT fk_tags_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE
);
CREATE INDEX ix_tags_path ON tags (path);
CREATE INDEX ix_tags_project_id ON tags (project_id);
CREATE TABLE highlights (
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        document_id INTEGER NOT NULL,
        start_offset INTEGER NOT NULL,
        end_offset INTEGER NOT NULL,
        snippet TEXT NOT NULL,
        CONSTRAINT fk_highlights_document_id_documents FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE
);
CREATE INDEX ix_highlights_document_id ON highlights (document_id);
CREATE TABLE highlight_tags (
        highlight_id INTEGER NOT NULL,
        tag_id INTEGER NOT NULL,
        CONSTRAINT pk_highlight_tags PRIMARY KEY (highlight_id, tag_id),
        CONSTRAINT fk_highlight_tags_highlight_id_highlights FOREIGN KEY(highlight_id) REFERENCES highlights (id) ON DELETE CASCADE,
        CONSTRAINT fk_highlight_tags_tag_id_tags FOREIGN KEY(tag_id) REFERENCES tags (id) ON DELETE CASCADE
);
CREATE INDEX ix_highlight_tags_highlight_id ON highlight_tags (highlight_id);
CREATE INDEX ix_highlight_tags_tag_id ON highlight_tags (tag_id);
CREATE TABLE alembic_version (
        version_num VARCHAR(32) NOT NULL,
        CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);
 """
