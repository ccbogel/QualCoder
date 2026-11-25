import builtins
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

builtins._ = getattr(builtins, '_', lambda value: value)

from qualcoder.manage_files import DialogManageFiles
from qualcoder.text_decoding import decode_text_with_best_encoding


class TestBatchTranscriptions(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        self.conn.executescript('''
            create table source(id integer primary key, name text, fulltext text, mediapath text, av_text_id integer);
            create table code_text(fid integer);
            create table annotation(fid integer);
        ''')
        self.media = []
        self.dialog = SimpleNamespace(
            app=SimpleNamespace(conn=self.conn, project_path=self.directory, vectorstore_import_document=Mock()),
            load_pseudonyms=lambda: [{'original': 'Mary', 'pseudonym': 'Jane'}],
            decode_text_with_best_encoding=decode_text_with_best_encoding,
            load_file_data=Mock(), _emit_project_table_changes=Mock())
        self.dialog.read_transcription = lambda path, pseudonyms: DialogManageFiles.read_transcription(
            self.dialog, path, pseudonyms)

    def media_file(self, name, content=''):
        target = self.conn.execute('insert into source(name,fulltext) values(?,?)', (name + '.txt', content)).lastrowid
        id_ = self.conn.execute('insert into source(name,mediapath,av_text_id) values(?,?,?)',
                                (name, '/audio/' + name, target)).lastrowid
        self.media.append({'id': id_, 'name': name})
        return target

    def run_import(self, folder=None):
        with patch('qualcoder.manage_files.QtWidgets.QFileDialog.getExistingDirectory',
                   return_value=str(self.directory) if folder is None else folder), \
             patch('qualcoder.manage_files.Message') as message:
            DialogManageFiles.import_matching_transcriptions(self.dialog, self.media)
        return message

    def text(self, id_):
        return self.conn.execute('select fulltext from source where id=?', (id_,)).fetchone()[0]

    def test_import_multidot_exact_matches_preserve_links_and_use_project_pseudonyms(self):
        first = self.media_file('day.1.wav')
        second = self.media_file('day.2.mp4')
        (self.directory / 'day.1.txt').write_bytes(b'\xef\xbb\xbfMary spoke.\r\n')
        (self.directory / 'day.2.html').write_text('<html><body>Second interview</body></html>')
        self.run_import()
        self.assertEqual(self.text(first), 'Jane spoke.\n')
        self.assertIn('Second interview', self.text(second))
        self.assertEqual(self.conn.execute('select av_text_id from source where av_text_id is not null').fetchall(),
                         [(first,), (second,)])
        self.assertEqual(self.dialog.app.vectorstore_import_document.call_count, 2)
        (self.directory / 'day.1.txt').write_text('Overwritten sidecar')
        self.run_import()
        self.assertEqual(self.text(first), 'Jane spoke.\n')
        self.assertEqual(self.dialog.app.vectorstore_import_document.call_count, 2)

    def test_skip_conflicts_edited_sources_empty_inputs_and_missing_links(self):
        ambiguous_audio = [self.media_file('same.wav'), self.media_file('same.mp4')]
        ambiguous_files = self.media_file('two.wav')
        authored = self.media_file('draft.wav', 'human edit')
        coded = self.media_file('coded.wav')
        annotated = self.media_file('annotated.wav')
        empty = self.media_file('empty.wav')
        missing = self.media_file('missing.wav')
        shared = self.media_file('shared.wav')
        self.conn.execute('insert into source(name,mediapath,av_text_id) values(?,?,?)',
                          ('outside-selection.wav', '/audio/outside-selection.wav', shared))
        dangling = self.media_file('dangling.wav')
        self.conn.execute('delete from source where id=?', (dangling,))
        self.conn.execute('insert into code_text values (?)', (coded,))
        self.conn.execute('insert into annotation values (?)', (annotated,))
        for filename in ('same.txt', 'two.vtt', 'two.srt', 'draft.md', 'coded.txt', 'annotated.txt', 'dangling.txt', 'shared.txt'):
            (self.directory / filename).write_text('replacement')
        (self.directory / 'empty.txt').write_text(' \n')
        message = self.run_import()
        self.assertEqual(self.text(authored), 'human edit')
        for fid in [*ambiguous_audio, ambiguous_files, coded, annotated, empty, missing, shared]:
            self.assertEqual(self.text(fid), '')
        self.assertIn('Ambiguous match', message.return_value.setDetailedText.call_args.args[0])
        self.assertFalse(self.dialog.load_file_data.called)
        self.assertFalse(self.dialog.app.vectorstore_import_document.called)

    def test_cancel_does_not_read_or_write(self):
        fid = self.media_file('sample.mp3')
        (self.directory / 'sample.txt').write_text('new text')
        self.run_import('')
        self.assertEqual(self.text(fid), '')
        self.assertFalse(self.dialog._emit_project_table_changes.called)
