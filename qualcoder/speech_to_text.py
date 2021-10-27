# -*- coding: utf-8 -*-

"""
Copyright (c) 2021 Colin Curtain

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

# https://medium.com/@shauryashivam38/how-to-make-a-wordcloud-in-python-feat-stylecloud-88cdae5fc8c9

import os
# sudo python3 -m pip install pydub
import pydub
# sudo python3 -m pip install SpeechRecognition
# works with wav and flac files, wav can be multiple formats, so convert all to flac
# need to have ffmpeg or avconv installed (tricky instillation on Windows)
import speech_recognition
import subprocess
import sys
import logging
import traceback

from PyQt5 import QtCore, QtWidgets

from .helpers import Message, msecs_to_mins_and_secs
from .GUI.ui_speech_to_text import Ui_DialogSpeechToText

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)

def exception_handler(exception_type, value, tb_obj):
    """ Global exception handler useful in GUIs.
    tb_obj: exception.__traceback__ """
    tb = '\n'.join(traceback.format_tb(tb_obj))
    text = 'Traceback (most recent call last):\n' + tb + '\n' + exception_type.__name__ + ': ' + str(value)
    print(text)
    logger.error(_("Uncaught exception: ") + text)
    QtWidgets.QMessageBox.critical(None, _('Uncaught Exception'), text)


class SpeechToText(QtWidgets.QDialog):
    """ Converts audio or video audio track to text using online services.
     Process involves converting the audio track to flac, then chunk.
     Each chunk is stored as temp.was in the .qualcoder folder and chunk by chunk
     converted to text. Each text chunk is preceeded with a time stamp.

     https://github.com/Uberi/speech_recognition/blob/master/reference/library-reference.rst
     """

    app = None
    text = ""
    filepath = None
    flac_filepath = None
    # IBM an RFC5646 language tag
    # Bing BCP-47 language tag
    # Google IETF language tag
    language = "en-US"  # default
    strings = []
    service = "google" # wit.ai, azure, bing, houndify, ibm
    # dont use google_cloud, requires a file
    # "INSERT WIT.AI API KEY HERE"  # Wit.ai keys are 32-character uppercase alphanumeric strings
    key_wit_ai = ""
    # "INSERT AZURE SPEECH API KEY "  # Microsoft Speech API keys 32-character lowercase hexadecimal strings
    key_azure = ""
    # "INSERT BING API KEY "  # Microsoft Bing Voice Recognition API keys 32-character lowercase hexadecimal strings
    key_bing = ""
    # "INSERT HOUNDIFY CLIENT ID "  # Houndify client IDs are Base64-encoded strings
    # "INSERT HOUNDIFY CLIENT KEY "  # Houndify client keys are Base64-encoded strings
    key_houndify = ""
    id_houndify = ""
    # "INSERT IBM SPEECH TO TEXT USERNAME "  # IBM Speech to Text usernames are strings of the form XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX
    # "INSERT IBM SPEECH TO TEXT PASSWORD "  # IBM Speech to Text passwords are mixed-case alphanumeric strings
    username_ibm = ""
    password_ibm = ""
    chunksize = 60000  # 60 seconds

    def __init__(self, app, av_filepath):

        sys.excepthook = exception_handler
        self.app = app
        self.text = ""
        # Initialize the speech recognition class
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_DialogSpeechToText()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        self.filepath = av_filepath

        '''self.convert_to_flac()
        #print("FFP", self.flac_filepath)
        if self.flac_filepath is not None:
            self.convert_to_text()
        else:
            Message(self.app, _("Processing error"), _("Cannot process file")).exec_()
        for s in self.strings:
            text += s
        print("TEXT\n", text)'''

    def convert_to_text(self):
        """
        based on:
        https://stackoverflow.com/questions/39232150/python-speech-recognition-error-converting-mp3-file
        """

        # Load flac file
        audio_file = pydub.AudioSegment.from_file(self.flac_filepath, "flac")
        # Split file into 30 or 60 second chunks
        def divide_chunks(audio_file, chunksize):
            # looping till length l
            for i in range(0, len(audio_file), self.chunksize):
                yield audio_file[i:i + chunksize]
        # Specify that a silent chunk must be at least 1 second long
        # Consider a chunk silent if it's quieter than -16 dBFS. May adjust these values.
        # split on silence does not work well
        #chunks = pydub.silence.split_on_silence(audio_file, min_silence_len=500, silence_thresh=-16)
        chunks = list(divide_chunks(audio_file, self.chunksize))
        print(f"{len(chunks)} chunks of {self.chunksize / 1000}s each")
        qc_dir = os.path.expanduser('~') + '/.qualcoder'
        r = speech_recognition.Recognizer()
        # For each chunk, save as wav, then read and run through recognize_google()
        self.strings = []
        for i, chunk in enumerate(chunks):
            chunk.export(qc_dir + "/tmp.wav", format='wav')
            with speech_recognition.AudioFile(qc_dir + "/tmp.wav") as source:
                audio = r.record(source)
            # Google limited to 50 requests per day
            if self.service == "google":
                try:
                    s = r.recognize_google(audio, language=self.language)
                except speech_recognition.UnknownValueError:
                    s = "UNINTELLIGIBLE AUDIO"
                except speech_recognition.RequestError as e:
                    s = "NO SERVICE RESULTS; {0}".format(e)
            if self.service == "wit.ai":
                # Language is configured in the wit account
                try:
                    s = r.recognize_wit(audio, key=self.key_wit_ai)
                except speech_recognition.UnknownValueError:
                    s = "UNINTELLIGIBLE AUDIO"
                except speech_recognition.RequestError as e:
                    s = "NO SERVICE RESULTS; {0}".format(e)
            if self.service == "azure":
                try:
                    s = r.recognize_azure(audio, key=self.key_azure)
                except speech_recognition.UnknownValueError:
                    s = "UNINTELLIGIBLE AUDIO"
                except speech_recognition.RequestError as e:
                    s = "NO SERVICE RESULTS; {0}".format(e)
            if self.service == "bing":
                try:
                    s = r.recognize_bing(audio, key=self.key_bing, language=self.language)
                except speech_recognition.UnknownValueError:
                    s = "UNINTELLIGIBLE AUDIO"
                except speech_recognition.RequestError as e:
                    s = "NO SERVICE RESULTS; {0}".format(e)
            if self.service == "houndify":
                # English only
                try:
                    s = r.recognize_houndify(audio, client_id=self.id_houndify, client_key=self.key_houndify)
                except speech_recognition.UnknownValueError:
                    s = "UNINTELLIGIBLE AUDIO"
                except speech_recognition.RequestError as e:
                    s = "NO SERVICE RESULTS; {0}".format(e)
            if self.service == "ibm":
                try:
                    s = r.recognize_ibm(audio, username=self.username_ibm, password=self.password_ibm, language=self.language)
                except speech_recognition.UnknownValueError:
                    s = "UNINTELLIGIBLE AUDIO"
                except speech_recognition.RequestError as e:
                    s = "NO SERVICE RESULTS; {0}".format(e)
            print(i, "/", len(chunks))
            ts = self.timestamp(i * chunksize)
            self.strings.append(ts + s)

    '''GOOGLE_CLOUD_SPEECH_CREDENTIALS = r"""INSERT THE CONTENTS OF THE GOOGLE CLOUD SPEECH JSON CREDENTIALS FILE HERE"""
    print("Google Cloud Speech thinks you said " + r.recognize_google_cloud(audio,
                                                                                credentials_json=GOOGLE_CLOUD_SPEECH_CREDENTIALS))
    '''

    '''# tmp method, revert to helpers. ...
    def msecs_to_mins_and_secs(self, msecs):
        """ Convert milliseconds to minutes and seconds.
        msecs is an integer. Minutes and seconds output is a string."""

        secs = int(msecs / 1000)
        mins = int(secs / 60)
        remainder_secs = str(secs - mins * 60)
        if len(remainder_secs) == 1:
            remainder_secs = "0" + remainder_secs
        return str(mins) + "." + remainder_secs'''

    def timestamp(self, time_msecs):
        """ timestamp using current format.
        Format options:
        [mm.ss], [mm:ss], [hh.mm.ss], [hh:mm:ss],
        {hh.mm.ss}, #hh:mm:ss.sss#
        """

        # tmp testing format
        fmt =  "[mm.ss]"  # self.app.settings['timestampformat']
        #time_msecs = self.mediaplayer.get_time()  # tmp
        mins_secs = self.msecs_to_mins_and_secs(time_msecs)  # String
        delimiter = ":"
        if "." in mins_secs:
            delimiter = "."

        mins = int(mins_secs.split(delimiter)[0])
        secs = mins_secs.split(delimiter)[1]
        hours = int(mins / 60)
        remainder_mins = str(mins - hours * 60)
        if len(remainder_mins) == 1:
            remainder_mins = "0" + remainder_mins
        hours = str(hours)
        if len(hours) == 1:
            hours = '0' + hours
        ts = "\n"
        if fmt == "[mm.ss]":
            ts += '[' + str(mins) + '.' + secs + ']'
        if fmt == "[mm:ss]":
            ts += '[' + str(mins) + ':' + secs + ']'
        if fmt == "[hh.mm.ss]":
            ts += '[' + str(hours) + '.' + remainder_mins + '.' + secs + ']'
        if fmt == "[hh:mm:ss]":
            ts += '[' + str(hours) + ':' + remainder_mins + ':' + secs + ']'
        if fmt == "{hh:mm:ss}":
            ts += '{' + str(hours) + ':' + remainder_mins + ':' + secs + '}'
        if fmt == "#hh:mm:ss.sss#":
            msecs = "000"
            tms_str = str(time_msecs)
            if len(tms_str) > 2:
                msecs = tms_str[-3:]
            ts += '#' + str(hours) + ':' + remainder_mins + ':' + secs + '.' + msecs + '#'
        return "\n" + ts+ " "

    def convert_to_flac(self):
        if len(self.filepath) < 5:
            return
        if self.filepath[-5:] in (".flac", ".FLAC"):
            self.flac_filepath = self.filepath
            return
        if self.filepath[-4:].lower() not in (".mp3", ".wav", ".m4a",  ".mp4", ".mov", ".ogg"):
            return
        audio = None
        if self.filepath[-4:].lower() == ".wav":
            audio = pydub.AudioSegment.from_wav(self.filepath)
        if self.filepath[-4:].lower() == ".mp3":
            audio = pydub.AudioSegment.from_mp3(self.filepath)
        if self.filepath[-4:].lower() == ".ogg":
            audio = pydub.AudioSegment.from_ogg(self.filepath)
        if self.filepath[-4:].lower() == ".mp4":
            audio = pydub.AudioSegment.from_file(self.filepath, "mp4")
        if self.filepath[-4:].lower() == ".mp4":
            audio = pydub.AudioSegment.from_file(self.filepath, "mov")
        if self.filepath[-4:].lower() == ".mp4":
            audio = pydub.AudioSegment.from_file(self.filepath, "m4a")
        if audio is not None:
            self.flac_filepath = self.filepath[:-4] + ".flac"
            audio.export(self.flac_filepath, format="flac")


if __name__ == "__main__":
    SpeechToText()






