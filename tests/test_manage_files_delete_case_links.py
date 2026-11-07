import builtins
import sqlite3
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

builtins._ = getattr(builtins, "_", lambda s: s)  # gettext is normally installed by the app

from qualcoder.manage_files import DialogManageFiles


def _create_project_tables(cur):
    """ Minimal schema used by the delete paths. """

    cur.execute("CREATE TABLE source (id integer primary key, name text, fulltext text, mediapath text, memo text, "
                "owner text, date text, av_text_id integer, risid integer, unique(name))")
    cur.execute("CREATE TABLE cases (caseid integer primary key, name text, memo text, owner text, date text)")
    cur.execute("CREATE TABLE case_text (id integer primary key, caseid integer, fid integer, pos0 integer, "
                "pos1 integer, owner text, date text, memo text)")
    cur.execute("CREATE TABLE code_text (ctid integer primary key, cid integer, fid integer, seltext text, "
                "pos0 integer, pos1 integer, owner text, date text, memo text, avid integer, important integer)")
    cur.execute("CREATE TABLE code_image (imid integer primary key, id integer)")
    cur.execute("CREATE TABLE code_av (avid integer primary key, id integer)")
    cur.execute("CREATE TABLE annotation (anid integer primary key, fid integer, pos0 integer, pos1 integer)")
    cur.execute("CREATE TABLE attribute (attrid integer primary key, name text, attr_type text, value text, "
                "id integer)")


class TestDeleteMediaCaseLinks(TestCase):
    """ Deleting a media file must not leave case links for a reused source id. """

    def _dialog_for(self, conn, source_row):
        return SimpleNamespace(
            app=SimpleNamespace(conn=conn, project_path="/tmp/project", delete_backup=True),
            av_dialog_open=None,
            source=[source_row],
            files_renamed=[],
            visible_selected_rows=lambda: [0],
            set_cancel_as_default=Mock(),
            release_files_in_coding_dialogs=Mock(),
            _release_media_players_for=Mock(),
            _unlink_media_with_retry=Mock(),
            remove_waveform_png=Mock(),
            vectorstore_delete_document_safe=Mock(),
            update_files_in_dialogs=Mock(),
            check_attribute_placeholders=Mock(),
            parent_text_edit=Mock(),
            load_file_data=Mock(),
            _emit_project_table_changes=Mock(),
        )

    def test_next_import_does_not_inherit_case_of_deleted_media(self):
        for mediapath in ("/images/foto_A.png", "/audio/audio_A.mp3", "/video/video_A.mp4"):
            with self.subTest(mediapath=mediapath):
                conn = sqlite3.connect(":memory:")
                cur = conn.cursor()
                _create_project_tables(cur)
                cur.execute("insert into cases (name) values ('Participante A')")
                cur.execute("insert into source (name, mediapath) values ('entrevista.txt', '/docs/entrevista.txt')")
                text_id = cur.lastrowid
                cur.execute("insert into source (name, mediapath) values (?, ?)",
                            [mediapath.rsplit("/", 1)[1], mediapath])
                media_id = cur.lastrowid
                cur.execute("insert into case_text (caseid, fid, pos0, pos1) values (1, ?, 0, 10)", [text_id])
                cur.execute("insert into case_text (caseid, fid, pos0, pos1) values (1, ?, 0, 0)", [media_id])
                conn.commit()
                dialog = self._dialog_for(conn, {'id': media_id, 'name': "media", 'mediapath': mediapath})

                with patch("qualcoder.manage_files.DialogConfirmDelete") as confirm:
                    confirm.return_value.exec.return_value = True
                    DialogManageFiles.delete(dialog)

                cur.execute("select count(*) from case_text where fid=?", [media_id])
                self.assertEqual(cur.fetchone()[0], 0)
                # Links of other files are untouched
                cur.execute("select count(*) from case_text where fid=?", [text_id])
                self.assertEqual(cur.fetchone()[0], 1)
                # SQLite reuses the highest deleted id for the next import
                cur.execute("insert into source (name, mediapath) values ('foto_B.png', '/images/foto_B.png')")
                new_id = cur.lastrowid
                self.assertEqual(new_id, media_id)
                cur.execute("select count(*) from case_text where fid=?", [new_id])
                self.assertEqual(cur.fetchone()[0], 0)
                conn.close()
