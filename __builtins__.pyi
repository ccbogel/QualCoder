"""
__builtins__.py

Stub declarations for names injected into the builtins namespace at runtime
by gettext.install(). Declared here so static type checkers (ty, mypy) can
resolve them without executing the application.

These names are NOT builtins by default; they become globally available only
after gettext.install(...) has been called at application startup.
--------------------------------------------------------
This file is part of QualCoder.

QualCoder is free software: you can redistribute it and/or modify it under the
terms of the GNU Lesser General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later version.

QualCoder is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the GNU General Public License for more details.

You should have received a copy of the GNU Lesser General Public License along with QualCoder.
If not, see <https://www.gnu.org/licenses/>.

Author: Alberto Antonio Rebonatto Neto (BetoNetu)
https://github.com/ccbogel/QualCoder
https://qualcoder-org.github.io
https://qualcoder.wordpress.com/
https://qualcoder.org/
"""
from collections.abc import Callable

_: Callable[[str], str]
"""
Alias for gettext.gettext().
Return the localized translation of *message*, based on the current
global domain, language, and locale directory. If no translation is
found, *message* itself is returned unchanged.
This alias is what pygettext/xgettext extract by default when scanning
Python sources, so any user-facing string passed here becomes a
translatable entry in the message catalog.
"""


def ngettext(singular: str, plural: str, n: int) -> str:
    """
    Alias for gettext.ngettext().

    Return the appropriate localized plural form of *singular* or *plural*
    depending on the value of *n*, using the plural rules of the current
    language. Equivalent to gettext.gettext() but plural-aware.
    """

def pgettext(context: str, message: str) -> str:
    """
    Alias for gettext.pgettext().

    Like gettext(), but disambiguates identical source strings that need
    different translations depending on *context* (e.g. "May" the month vs
    "May" the modal verb). Falls back to translating *message* alone if no
    context-specific entry exists.
    """

def npgettext(context: str, singular: str, plural: str, n: int,) -> str:
    """
    Alias for gettext.npgettext().

    Plural-aware variant of pgettext(). Combines the context disambiguation
    of pgettext() with the plural selection of ngettext().
    """
