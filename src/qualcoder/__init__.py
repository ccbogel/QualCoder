import builtins
import gettext

# Ensure _() always exists, even before translator.install() during startup/tests.
if not callable(getattr(builtins, "_", None)):
    builtins._ = gettext.gettext
