# __builtins__.pyi

#   Stub declarations for names injected into the builtins namespace at runtime
#   by gettext.install(). Declared here so static type checkers (ty, mypy) can
#   resolve them without executing the application.

# These names are NOT builtins by default; they become globally available only
# after gettext.install(...) has been called at application startup.


def _(message: str) -> str:
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
