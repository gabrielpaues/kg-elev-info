# kg-elev-info

Veckorapporter för ett barns skola (Kungsholmens gymnasium / Stockholms musikgymnasium). Personspecifik konfiguration ligger i `data/elev.local` (gitignored) och skapas av skillen vid första körningen.

- `skill/` — opencode-skill (symlinkad från `~/.config/opencode/skills/kg-elev-info`)
- `rapporter/` — veckorapporter per vecka
- `raw/` — skrapad rådata (gitignored — personuppgifter)
- `data/` — terminsdatum, event-JSON för kalendersync (iCloud-kalendern skapas ENGÅNGS manuellt under iCloud-rubriken i Cal.app — AppleScript kan ej välja konto; namnet kommer från elev.local)
- `chrome-profile/` — debug-Chrome-profil (gitignored — innehåller sessionscookies)

Körning: opencode → "veckorapport skolana" (.triggers i skill/SKILL.md).
