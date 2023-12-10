# -*- coding: utf-8 -*-

"""
Copyright (c) 2023 Colin Curtain

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
"""

from copy import deepcopy
import logging
import os
from PIL import Image  # Pillow
from PIL import ImageColor  # pillow
from PIL import ImageDraw
from PIL import ImageFilter
from PIL import ImageFont
from random import randint
import sys
import traceback

from PyQt6 import QtCore, QtGui, QtWidgets


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


class Wordcloud:
    font_path = home = os.path.join(os.path.expanduser('~'), ".qualcoder", "DroidSansMono.ttf")
    stopwords = {"i", "i,ve", "me", "my", "myself", "we", "our", "ours", "ourselves", "you", "your", "you're", "yours",
                 "yourself", "it's", "that's",
                 "yourselves", "he", "him", "his", "himself", "she", "her", "hers", "herself", "it", "its", "itself",
                 "they",
                 "them", "their", "theirs", "themselves", "what", "which", "who", "whom", "this", "that", "these",
                 "those", "am",
                 "is", "are", "was", "were", "be", "been", "being", "have", "has", "had", "having", "do", "does", "did",
                 "doing", "a",
                 "an", "the", "and", "but", "if", "or", "because", "as", "until", "while", "of", "at", "by", "for",
                 "with", "about",
                 "against", "between", "into", "through", "during", "before", "after", "above", "below", "to", "from",
                 "up",
                 "down", "in", "out", "on", "off", "over", "under", "again", "further", "then", "once", "here", "there",
                 "when",
                 "where", "why", "how", "all", "any", "both", "each", "few", "more", "most", "other", "some", "such",
                 "no",
                 "nor", "not", "only", "own", "same", "so", "than", "too", "very", "can", "can't", "will", "just",
                 "don't",
                 "should", "now"}

    def __init__(self, app, fulltext, width=800, height=600):

        sys.excepthook = exception_handler
        self.app = app
        self.width = width
        self.height = height
        self.max_font_size = int(self.height / 5)
        self.min_font_size = 4
        self.font_path = os.path.join(os.path.expanduser('~'), ".qualcoder", "DroidSansMono.ttf")

        # Remove punctuation. Convert to lower case
        chars = ""
        for c in range(0, len(fulltext)):
            if fulltext[c].isalpha() or fulltext[c] == "'":
                chars += fulltext[c]
            else:
                chars += " "
        chars = chars.lower()
        word_list = []
        word_list_temp = chars.split()
        for word in word_list_temp:
            if word not in self.stopwords:
                word_list.append(word)
        print("Words: " + f"{len(word_list):,d}")
        # Word frequency
        d = {}
        for word in word_list:
            d[word] = d.get(word, 0) + 1  # get(key, value if not present)
        # https://codeburst.io/python-basics-11-word-count-filter-out-punctuation-dictionary-manipulation-and-sorting-lists-3f6c55420855
        self.words = []
        for key, value in d.items():
            self.words.append({"text": key, "frequency": value, "x": 0, "y": 0})
        self.words = sorted(self.words, key=lambda x: x["frequency"], reverse=True)

        print("Unique words: " + str(len(self.words)))
        # Top 150 words
        max_count = len(self.words)
        if len(self.words) > 200:
            self.words = self.words[:200]
        print("Word frequency list")
        total_frequency = 0
        for word in self.words:
            total_frequency += word["frequency"]
            #print(f"{word[0]}   {word[1]}")
        self.font_scale = self.max_font_size / self.words[0]['frequency']
        for word in self.words:
            word['font_size'] = int(self.font_scale * word['frequency'])
            if word['font_size'] < self.min_font_size:
                word['font_size'] = self.min_font_size
            font = ImageFont.truetype(self.font_path, size=word['font_size'])
            left, upper, right, lower = font.getbbox(word['text'])
            word['width'] = right - left
            word['height'] = lower - upper

            #print(left, upper, right, lower, "::", right-left)

        self.find_draw_space()

        print("Word frequency list")
        total_frequency = 0
        for word in self.words:
            print(word["text"], word["frequency"], word['font_size'], word['width'], word['height'], word['x'], word['y'])

        self.create_image()

    def create_image(self):

        # create image
        img = Image.new("RGB", (self.width, self.height), "black")
        draw = ImageDraw.Draw(img)

        font_sizes, positions, orientations, colors = [], [], [], []
        for word in self.words:
            self.text(draw, word, "yellow")
        img.save(os.path.expanduser("~") + "/Downloads/img.png")

    def text(self, draw, word, fill="black"):
        font = ImageFont.truetype(self.font_path, size=word['font_size'])
        #x = randint(0, self.width - 10 - word['width'])
        #y = randint(0, self.height -10 - word['height'])
        draw.text((word['x'], word['y']), word["text"], font=font, fill=fill)


if __name__ == "__main__":
    txt = "Hello, everyone! This is the LONGEST TEXT EVER! I was inspired by the various other longest texts ever on the internet, and I wanted to make my own. So here it is! This is going to be a WORLD RECORD! This is actually my third attempt at doing this. The first time, I didn't save it. The second time, the Neocities editor crashed. Now I'm writing this in Notepad, then copying it into the Neocities editor instead of typing it directly in the Neocities editor to avoid crashing. It sucks that my past two attempts are gone now. Those actually got pretty long. Not the longest, but still pretty long. I hope this one won't get lost somehow. Anyways, let's talk about WAFFLES! I like waffles. Waffles are cool. Waffles is a funny word. There's a Teen Titans Go episode called Waffles where the word Waffles is said a hundred-something times. It's pretty annoying. There's also a Teen Titans Go episode about Pig Latin. Don't know what Pig Latin is? It's a language where you take all the consonants before the first vowel, move them to the end, and add '-ay' to the end. If the word begins with a vowel, you just add '-way' to the end. For example, Waffles becomes Afflesway. I've been speaking Pig Latin fluently since the fourth grade, so it surprised me when I saw the episode for the first time. I speak Pig Latin with my sister sometimes. It's pretty fun. I like speaking it in public so that everyone around us gets confused. That's never actually happened before, but if it ever does, 'twill be pretty funny. By the way, 'twill is a word I invented recently, and it's a contraction of it will. I really hope it gains popularity in the near future, because 'twill is WAY more fun than saying it'll. It'll is too boring. Nobody likes boring. This is nowhere near being the longest text ever, but eventually it will be! I might still be writing this a decade later, who knows? But right now, it's not very long. But I'll just keep writing until it is the longest! Have you ever heard the song Dau Dau by Awesome Scampis? It's an amazing song. Look it up on YouTube! I play that song all the time around my sister! It drives her crazy, and I love it. Another way I like driving my sister crazy is by speaking my own made up language to her. She hates the languages I make! The only language that we both speak besides English is Pig Latin. I think you already knew that. Whatever. I think I'm gonna go for now. Bye! Hi, I'm back now. I'm gonna contribute more to this soon-to-be giant wall of text. I just realised I have a giant stuffed frog on my bed. I forgot his name. I'm pretty sure it was something stupid though. I think it was FROG in Morse Code or something. Morse Code is cool. I know a bit of it, but I'm not very good at it. I'm also not very good at French. I barely know anything in French, and my pronunciation probably sucks. But I'm learning it, at least. I'm also learning Esperanto. It's this language that was made up by some guy a long time ago to be the universal language. A lot of people speak it. I am such a language nerd. Half of this text is probably gonna be about languages. But hey, as long as it's long! Ha, get it? As LONG as it's LONG? I'm so funny, right? No, I'm not. I should probably get some sleep. Goodnight! Hello, I'm back again. I basically have only two interests nowadays: languages and furries. What? Oh, sorry, I thought you knew I was a furry. Haha, oops. Anyway, yeah, I'm a furry, but since I'm a young furry, I can't really do as much as I would like to do in the fandom. When I'm older, I would like to have a fursuit, go to furry conventions, all that stuff. But for now I can only dream of that. Sorry you had to deal with me talking about furries, but I'm honestly very desperate for this to be the longest text ever. Last night I was watching nothing but fursuit unboxings. I think I need help. This one time, me and my mom were going to go to a furry Christmas party, but we didn't end up going because of the fact that there was alcohol on the premises, and that she didn't wanna have to be a mom dragging her son through a crowd of furries. Both of those reasons were understandable. Okay, hopefully I won't have to talk about furries anymore. I don't care if you're a furry reading this right now, I just don't wanna have to torture everyone else. I will no longer say the F word throughout the rest of this entire text. Of course, by the F word, I mean the one that I just used six times, not the one that you're probably thinking of which I have not used throughout this entire text. I just realised that next year will be 2020. That's crazy! It just feels so futuristic! It's also crazy that the 2010s decade is almost over. That decade brought be a lot of memories. In fact, it brought be almost all of my memories. It'll be sad to see it go. I'm gonna work on a series of video lessons for Toki Pona. I'll expain what Toki Pona is after I come back. Bye! I'm back now, and I decided not to do it on Toki Pona, since many other people have done Toki Pona video lessons already. I decided to do it on Viesa, my English code. Now, I shall explain what Toki Pona is. Toki Pona is a minimalist constructed language that has only ~120 words! That means you can learn it very quickly. I reccomend you learn it! It's pretty fun and easy! Anyway, yeah, I might finish my video about Viesa later. But for now, I'm gonna add more to this giant wall of text, because I want it to be the longest! It would be pretty cool to have a world record for the longest text ever. Not sure how famous I'll get from it, but it'll be cool nonetheless. Nonetheless. That's an interesting word. It's a combination of three entire words. That's pretty neat. Also, remember when I said that I said the F word six times throughout this text? I actually messed up there. I actually said it ten times (including the plural form). I'm such a liar! I struggled to spell the word liar there. I tried spelling it lyer, then lier. Then I remembered that it's liar. At least I'm better at spelling than my sister. She's younger than me, so I guess it's understandable. Understandable is a pretty long word. Hey, I wonder what the most common word I've used so far in this text is. I checked, and appearantly it's I, with 59 uses! The word I makes up 5% of the words this text! I would've thought the would be the most common, but the is only the second most used word, with 43 uses. It is the third most common, followed by a and to. Congrats to those five words! If you're wondering what the least common word is, well, it's actually a tie between a bunch of words that are only used once, and I don't wanna have to list them all here. Remember when I talked about waffles near the beginning of this text? Well, I just put some waffles in the toaster, and I got reminded of the very beginnings of this longest text ever. Okay, that was literally yesterday, but I don't care. You can't see me right now, but I'm typing with my nose! Okay, I was not able to type the exclamation point with just my nose. I had to use my finger. But still, I typed all of that sentence with my nose! I'm not typing with my nose right now, because it takes too long, and I wanna get this text as long as possible quickly. I'm gonna take a break for now! Bye! Hi, I'm back again. My sister is beside me, watching me write in this endless wall of text. My sister has a new thing where she just says the word poop nonstop. I don't really like it. She also eats her own boogers. I'm not joking. She's gross like that. Also, remember when I said I put waffles in the toaster? Well, I forgot about those and I only ate them just now. Now my sister is just saying random numbers. Now she's saying that they're not random, they're the numbers being displayed on the microwave. Still, I don't know why she's doing that. Now she's making annoying clicking noises. Now she's saying that she's gonna watch Friends on three different devices. Why!?!?! Hi its me his sister. I'd like to say that all of that is not true. Max wants to make his own video but i wont let him because i need my phone for my alarm.POOP POOP POOP POOP LOL IM FUNNY. kjnbhhisdnhidfhdfhjsdjksdnjhdfhdfghdfghdfbhdfbcbhnidjsduhchyduhyduhdhcduhduhdcdhcdhjdnjdnhjsdjxnj Hey, I'm back. Sorry about my sister. I had to seize control of the LTE from her because she was doing keymash. Keymash is just effortless. She just went back to school. She comes home from school for her lunch break. I think I'm gonna go again. Bye! Hello, I'm back. Let's compare LTE's. This one is only 8593 characters long so far. Kenneth Iman's LTE is 21425 characters long. The Flaming-Chicken LTE (the original) is a whopping 203941 characters long! I think I'll be able to surpass Kenneth Iman's not long from now. But my goal is to surpass the Flaming-Chicken LTE. Actually, I just figured out that there's an LTE longer than the Flaming-Chicken LTE. It's Hermnerps LTE, which is only slightly longer than the Flaming-Chicken LTE, at 230634 characters. My goal is to surpass THAT. Then I'll be the world record holder, I think. But I'll still be writing this even after I achieve the world record, of course. One time, I printed an entire copy of the Bee Movie script for no reason. I heard someone else say they had three copies of the Bee Movie script in their backpack, and I got inspired. But I only made one copy because I didn't want to waste THAT much paper. I still wasted quite a bit of paper, though. Now I wanna see how this LTE compares to the Bee Movie script. Okay, I checked, and the Bee Movie script is 50753 characters long. Not as long as some of the LTEs I mentioned, but still longer than mine and Kenneth Iman's combined. This LTE is getting close to 10000 characters! That means it'll be half the length of Kenneth Iman's LTE. That's pretty exciting. Also, going back to the topic of the Bee Movie Script, I tried to write the entire thing out by hand once. But I never finished it, especially since I'm focusing on this thing now. Maybe I should write this LTE out by hand. Nah, I don't think I will. Yay, we're at 10000 characters! Let's celebrate by talking about MUSIC! Music is cool. That concludes our celebratory discussion about music. Thank you, and have a good rest of your day. Hi, I'm back now, and I got a book! It's a dictionary for a language called Elefen. It's like Esperanto, but better. Now I can learn Elefen even without internet! That's pretty cool. I will now write something in Elefen. See if you can understand it! Here goes: Si tu pote leje esta, tu es merveliosa! Elefen es un lingua multe fresca! Did you understand that? Maybe you can't speak Elefen, but you still understood that because of your knowledge of other languages. Elefen is cool because it's an actual language, not an English code like Pig Latin or Viesa. Oh, I forgot to mention that my sister is back from school. She's blasting Rhett and Link songs right now. Have you seen that picture of Rhett and Link standing with a bunch of *******? Sorry, I almost said the F word there. That would've broken my rule of not saying the F word. I wrote something in Elefen, so I will also write something in Toki Pona. See if you can understand it now! sina sona e toki mi la sina pona mute a! I can speak Toki Pona fluently, by the way. It's also a pretty cool language. My sister is still playing annoying songs. It's hindering my focus right now. But it's fiiiiine. Okay, luckily she's run out of songs to play. At least for now. She's trying to think of another annoying song to play. Now she's playing a song by Green Day. Not NEARLY as bad as the other songs she just played. I should go for now. Goodbye! Hello, I'm back once again. I don't know why I feel obligated to say that every time I come back. But I'll keep doing it anyway. My sister stopped blasting annoying songs, so that's good. She's cooking something in the microwave. I'll go check to see what it is right now. Nevermind, it's already done cooking. Right, I remember! It's mac and cheese! Now she just started singing I have a tongue, you don't, because I cut it off yesterday. I don't know what goes on in her mind when she does stuff like that. I've been messing around with my Elefen dictionary for a while, looking up whatever random words I can think of. By the way, the whole reason I'm doing this longest text ever is because of pointlesssites.com. That's how I found the Flaming-Chicken LTE, which inspired me to start writing this LTE. So thanks, pointlesssites.com! I check that website every day to see what new pointless websites they add. You know, I could double every letter I type so that this text would be twice as long as it normally would be. But nah, that's kinda cheating. So I won't. Also, SUBSCRIBE TO PEWDIEPIE! There, I did my part. Not that anyone will read this, but still. 'Twould be nice if you subscribed to PewDiePie. That's another word I invented. Actually, I looked it up, and I didn't invent it. Someone came up with it before I did. That's pretty sad. Also, LEARN VIESA TODAY! IT WILL CURE YOUR DEPRESSION! Seriously though, learn Viesa. It won't actually cure your depression, but I'm desperate for speakers. I only have one other person to speak it with. I should go now. Goodbye. Hi, I’m back. I just came up with an idea: SIMPLIFIED ENGLISH! Or, in Simplified Engish: Simifid Enis. It’s where every group of consonant letters is reduced to the first consonant in that group of consonants, and same goes with the vowels. If a word ends up being just a single consonant with no vowel, put ‘a’ at the end. So “I like eating my waffles” becomes “I like etin ma wafes”. Isn’t it the most amazing thing ever? Nah, it’s not quite as amazing as Viesa. Actually, Viesa isn’t a real language, so it’s less amazing then Elefen and Toki Pona, both of which are cool languages. I kinda figured that half of this text would be about languages. Oh well. I just really want this to be the longest text ever, without using copy and paste, keymash, etc. If you remember, my sister did a little bit of keymash in this text a while ago. I would’ve deleted it, but nah, I didn’t feel like it. And besides, it’s not like it took up half this text. I have an estimate for how long it’ll take me to be the world record holder: about one month. I think I can manage one month of writing this. You know what? I’m just gonna break my rule of not saying the word “furry”. There, I said it. Now I’m allowing myself to write “furry” whenever I want. So with that out of the way, let’s talk about how I first became a furry. For some reason, I have the exact date when I became a furry memorized. It’s May 4, 2018. At that time, I discovered that I was a furry by watching some furry YouTube videos. I knew about the existence of furries years before this, but I didn’t know much about it until this time. I said to myself, “You know what? I’m a furry now,” and that’s what started it all. And I’ve been slowly learning more about the fandom ever since. I would like to participate more in the fandom when I’m older, but I’m too young for most of it right now. Guess I’ll just have to wait. But in the meantime, I can write about it in this text. I should sleep now. Goodnight. Hello, I'm back once again. Happy Pi Day! I memorized a bunch of digits of Pi once, not sure how many I still remember... I have literally nothing to write about now. I've been trying to come up with something for the past 10 minutes, and I still have no idea. Literally nothing is happening right now. It's pretty boring. My sister is watching Friends, as usual. Okay, since there's nothing for me to write about, I should go now. Bye! Wow, it has been a while since I last added to this. It is now July 10, 2019. Last time I edited this page was Pi Day, which was March 14. Those 4 months of this thing being untouched end today! Wait... 4 months? That means I was supposed to get this past the world record three months ago. Oh well. I have put many things into this text. A lot of them were cringy, like how I keep mentioning furry-related things. You know, I should stop putting things in here when I know I'm gonna cringe at them later. I'll try not to do that from here on out. I just know I'll fail though. I'd hate to be aware of someone reading this entire thing... like, if I had to sit and watch a family member or something read this entire text, I would cringe so hard. I would not want that to happen. I am currently pasting the entirety of the FlamingChicken LTE onto a page on OurWorldOfText. The frustrating thing about pasting stuff there is that it pastes one letter at a time, so it takes forever to paste long text. And when the tab isn't open, I'm pretty sure it just stops pasting, so you have to keep the tab open if you want it to continue. Why am I even doing this? No idea. I might not even paste the whole thing. I probably won't. Hey, I just had a thought. What if, in the future, students are reading this for a class assignment? What if this LTE becomes part of the school curriculum? If so, hi future student! I hope you're enjoying reading my CRINGE. What is my life coming to? That's enough writing for now. Goodbye. Hey again. Might as well continue writing in here for a bit. Hey, have you ever heard of 3D Movie Maker? It's a program from the 90s (that still works on modern computers) where you can make 3D animated movies. It's pretty cool. I've made a few movies with it myself, and many other people use it to make interesting stuff. In case you want to try it for yourself, I'm sure if you google 3dmm download or something like that, it will take you somewhere where you can download the program. It's kinda aimed at younger children, but hopefully that doesn't stop you from making absolute masterpieces with this program. I have a keyboard in my room (the musical kind, not the one you type words on), and I don't really know how to play it properly, but I do it anyways. I can play a few songs on the piano (albeit with weird fingering because like I just said, I have no idea what I'm doing), including HOME - Resonance and PilotRedSun - Bodybuilder. You might not know one or both of those songs. If you don't know one of them, why not google it? You will have discovered some new music, and it will all be because of me. Why are you reading this, anyways? How did you even find it? Were you like me, and you were browsing pointlesssites.com, eventually finding the FlamingChicken LTE and going down a rabbit hole of discovering random LTEs? Literally the only reason I'm writing this right now is because that happened. I just discovered a new LTE: the RainbowFluffySheep LTE. I'm gonna see how many characters long it is. 75,957 characters. Pretty long, but not as long as the top two LTEs (FlamingChicken and Hermnerps, both with around 200,000 characters). I wanna write as much as possible into this text today. I'm gonna see how much LTE-writing I can do in one day. Hopefully it's a lot, because I wanna hold a world record! Imagine having a world record. Well, would it really be a world record? Because I don't know of any world record books that have Longest Text Ever as a record. Oh well, I just hope this LTE passes exactly 230,634 characters. That's all my goal is. I'm not even a tenth of the way there yet, but give it a month and I'm sure I'll get there. Hey, remember last time I said it would only take a month? That was four months ago. I should just stop promising things all together at this point. Forget I said anything about that. Did you know my sister has an LTE? That's right! It's not very long, though, and you can't read it because it's on her phone. She made it while bored at the library. That library was where I used to have web design classes. Those were fun, but I don't do them anymore. Now all I do it sit at home and write stuff in here. Well, I'm exaggerating. I go to the convenience store with my sister sometimes. But that's pretty much it outside of being bored on a computer. I should be a less boring human being. One day, I should translate this entire LTE into Viesa. That would be a big waste of time, even bigger than writing the LTE itself. But I could still do it. I don't think I ever will. This text is simply too long, and it'll be even longer than that by the time I pass 230,634 characters. By the way, if you think I'm gonna stop writing this once I pass 230,634 characters, you're wrong! Because I'll keep writing this even after I pass that point. It'll feel nice to be way ahead the record. My sister's alarm clock has been going off for half an hour and I haven't turned it off. Why? Because LAZYNESS! Actually, I really should turn it off now. There, I turned it off. First when I tried to turn it off, it started playing the radio. Then I tried again, and it turned off completely. Then I hurt myself on the door while walking out. So that was quite the adventure. I'm gonna go sleep now. Goodnight! Hey, I'm back again. My computer BSOD'd while writing this, so I have to start this section over again. That's why you save your work, kids! Before I had to start over again, I was talking about languages. Yes, I decided to bring that topic back after a while. But I no longer want to talk about it. Why? Because it'll probably bore you to death. That is assuming you're reading this at all. Who knows, maybe absolutely zero people will read this within the span of the universe's existence. But I doubt that. There's gotta be someone who'll find this text and dedicate their time to reading it, even if it takes thousands of years for that to happen. What will happen to this LTE in a thousand years? Will the entire internet dissapear within that time? In that case, will this text dissapear with it? Or will it, along with the rest of what used to be the internet, be preserved somewhere? I'm thinking out loud right now. Well, not really out loud because I'm typing this, and you can't technically be loud through text. THE CLOSEST THING IS TYPING IN ALL CAPS. Imagine if I typed this entire text like that. That would be painful. I decided to actually save my work this time, in case of another crash. I already had my two past attempts at an LTE vanish from existance. I mean, most of this LTE is already stored on Neocities, so I probably won't need to worry about anything. I think I might change the LTE page a little. I want the actual text area to be larger. I'm gonna make it a very basic HTML page with just a header and text. Maybe with some CSS coloring. I don't know. Screw it, I'm gonna do it. There, now the text area is larger. It really does show how small this LTE is so far compared to FlamingChicken or Hermnerps. But at least I made the background a nice Alice Blue. That's the name of the CSS color I used. It's pretty light. We're getting pretty close to the 1/10 mark! That's the point where we're one tenth of the way to making this the longest text ever, meaning all I have to do is write the equivalent of everything I've already written so far nine more times! Not gonna make any promises, though. How come every time I try to type though, it comes out as thought? Why do I always type the extra T? It's so annoying that I have to delete the T every time. Okay, only mildly annoying. Not as annoying as I previously described. I apologize for my exaggeration of the annoyance level of me typing thought instead of though. I just realized that most of the games I play are games that"
    Wordcloud(None, txt)

