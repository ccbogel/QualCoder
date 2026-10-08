# Security Policy

QualCoder is a desktop application for qualitative data analysis. It runs locally and stores project data in an SQLite database inside the project folder chosen by the user. It does not run a server, does not create user accounts and does not send project data anywhere unless the user enables an optional feature that does so (see "Scope" below).

## Supported versions

Security fixes are applied to the current release only. Older releases do not receive patches; please upgrade.

| Version | Supported |
|---------|-----------|
| 4.x (current release) | Yes |
| 3.8.2 and earlier | No |

Development code on the `master` branch is not a release and may contain unfinished work.

## Reporting a vulnerability

Please do not open a public issue for security problems.

Report privately through GitHub: open the repository's **Security** tab and choose **Report a vulnerability**. This creates a private advisory that only the maintainers can see.

If you cannot use GitHub, email [email@email.com].

Include, where possible:

- QualCoder version and operating system
- How you installed it (binary from the Releases page, or from source)
- Steps to reproduce
- What the impact is (for example, data exposure, code execution, denial of service)

## What to expect

- Acknowledgement within 7 days.
- An assessment of severity and a plan within 30 days. The maintainers are volunteers, so timelines may vary.
- A fix in a new release, with credit to the reporter in the release notes unless they prefer to stay anonymous.
- Public disclosure after the fix is available. We ask reporters to wait until then.

## Scope

The following are in scope:

- The QualCoder application code in this repository (`src/qualcoder`).
- Project import and export (REFI-QDA, RIS, survey files, text and PDF imports, Taguette import).
- The built-in MCP server and the external MCP bridge used with desktop AI clients.
- The release binaries published on the GitHub Releases page.

The following are out of scope:

- Vulnerabilities in third-party dependencies (Python, PyQt6, VLC, LLM providers, etc.). Please report these upstream. We will update the dependency when a fix is available.
- Issues that require physical access to the user's computer or an already compromised machine.
- Executables downloaded from sites other than GitHub or Codeberg. We do not endorse or verify them.

## Data handling notes relevant to security review

- All project data stays on the user's machine unless the user enables the AI features.
- AI features are disabled by default. When enabled, the text the user selects for analysis is sent to the LLM provider the user configured (for example OpenAI, Anthropic, Google, Blablador or a local Ollama model). The provider's own privacy terms apply. API keys are stored in the local QualCoder configuration file.
- Local semantic search uses a model downloaded once to the user's machine; the resulting embeddings are stored in the project's `ai_data` folder.
- A pseudonymisation tool is available to replace names before documents are imported.
- Windows and macOS binaries are currently unsigned, so operating systems show an "unknown publisher" warning. Checksums for each binary are listed on the release page so downloads can be verified.

## Dependency updates

Dependencies are listed in `requirements.txt`. Automated dependency alerts are enabled on the repository. Updates to dependencies with known vulnerabilities are prioritised for the next release.
