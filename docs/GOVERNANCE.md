# Governance

This document describes how the QualCoder project is run, who makes decisions and how people can take on responsibility. It is deliberately short. QualCoder is a volunteer project and the aim is to write down what already happens, not to add bureaucracy.

## Roles

### Project lead

Colin Curtain created QualCoder in 2019 and leads the project. The project lead:

- Reviews contributions, and merges them into the main repository.
- Publishes releases (or delegates this to another maintainer).
- Administers the GitHub repository (and the Codeberg mirror).

### Maintainers

Maintainers have write access to the repository. They review and merge pull requests, triage issues, answer questions in Discussions and take part in decisions about the roadmap. You can view the list of current maintainers on [this page](https://qualcoder.org/about).

### Contributors

Anyone who submits code, documentation, translations, bug reports, tests or support to other users. Contributors do not need write access. Contributions are made under the project licence (LGPL v3), as described in CONTRIBUTING.md.

### Translators

Translations are maintained through the `.po`/`.ts` files in `other_languages` and the `rebuild_lang.py` script. Translators are credited in the release notes. You can view the list of translation coordinators  on [this page](https://qualcoder.org/about).

## How decisions are made

- Day-to-day decisions (bug fixes, small improvements, documentation) are made by whichever maintainer handles the issue or pull request.
- Larger changes (new modules, changes to the database structure, changes to the project file format, new dependencies, licence changes) are discussed publicly in a GitHub issue or Discussion before work starts. Maintainers aim for consensus; if there is no consensus, the project lead decides.
- The roadmap is kept in `ROADMAP.md`, with each item linked to an issue where the discussion can be read.
- Decisions that affect users (removed features, changed behaviour, new minimum versions) are recorded in the release notes.

## Becoming a maintainer

A contributor may be invited to become a maintainer when they have:

- Contributed regularly over several months (code, translations, documentation or testing).
- Shown they can review other people's work constructively.
- Followed the Code of Conduct.

Any maintainer can propose a new maintainer. The proposal is discussed among the maintainers and accepted if no maintainer objects. The new maintainer is added to the table above and given repository access.

## Stepping down or inactivity

Maintainers may step down at any time by telling the other maintainers. A maintainer who has been inactive for twelve months may be moved to emeritus status after being contacted; access is removed and they are kept in the project credits. Emeritus maintainers can return by asking.

## Releases

Releases are published on GitHub (with a mirror on Codeberg) by the project lead or a maintainer the lead designates. Each release includes release notes, source code and binaries for Windows, macOS and Linux where the team can build them. QualCoder does not endorse binaries distributed elsewhere.

## Conflicts of interest and affiliations

Maintainers are affiliated with universities and research institutes, listed in the README. No maintainer is paid by a vendor to work on QualCoder. If a maintainer has a personal or commercial interest in a decision (for example, paid training or a service built on QualCoder), they say so in the discussion and let the other maintainers decide.

## Continuity

The repository lives under the project lead's GitHub account. To reduce the risk of the project depending on a single person:

- All maintainers have write access to the repository and to the Codeberg mirror.
- At least two maintainers hold the credentials for the project website and the CI secrets. [TO CONFIRM]
- If the project lead takes an extended break, the other maintainers can keep handling issues, reviewing contributions and publishing releases in the meantime.

## Changing this document

Changes to this document are proposed as pull requests and need agreement from the maintainers, following the same process as any larger change.

## Code of Conduct

All participation in the project is subject to the Code of Conduct in `CODE_OF_CONDUCT.md`. Reports are handled by the maintainers.
