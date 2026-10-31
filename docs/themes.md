# Application themes

All three themes use Qt Fusion to draw standard controls. Their geometry, focus
indicators, hover states and button shapes are shared; colors come from QPalette.

- `native` uses Qt's system palette, including light/dark appearance and accent colors.
- `original` uses a fixed light palette with neutral gray surfaces and the original bright orange accent.
  Selections have a black background with white text, independently of the accent.
- `dark` uses a fixed dark palette with neutral gray surfaces and a bright orange accent.
  Selections have a white background with dark text, independently of the accent.

`src/qualcoder/themes.py` contains the supported names, migration mapping and palette
roles. The two columns in `THEME_COLORS` are the original and dark colors. Selection
colors also cover inactive views; disabled text and icons use muted foregrounds.
Links, visited links, placeholders, tooltips and alternating rows have explicit colors.
Application QSS only sets shared font sizes. Avoid adding global control borders,
backgrounds or indicator rules: these can replace Fusion rendering.

When settings are loaded, retired themes are migrated and saved automatically:

| Previous theme | Replacement |
| --- | --- |
| rainbow | dark |
| blue, green, orange, purple, yellow | original |
| Unknown or legacy numeric value | native |

Theme changes continue to require an application restart. Native palette updates
refresh row stripes and tooltip colors. Custom content should read palette roles
or inspect the actual background, rather than infer brightness from a theme name.

`tests/test_themes.py` checks migration persistence, enabled text contrast, palette
isolation and Fusion control metrics.
