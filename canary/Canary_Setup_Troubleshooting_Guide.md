# Canary Setup Troubleshooting Guide

## 1. At a glance

- Most competitors who hit trouble will need one of three fixes: the Windows time zone, a clean install to C:, or a licence reset from Canary.
- This guide lists every problem we hit while setting up Canary 26.7 for the DSMLC F26 Datathon, with the fix for each.

## 2. Before installing checklist

Doing these before installing avoids almost every problem below. Canary only runs on Windows, so each team needs at least one Windows laptop.

| # | Check | How / where | Notes |
|---|---|---|---|
| 1 | Windows 10/11 laptop | Admin rights, about 10 GB free on C: | Canary is Windows-only |
| 2 | Smart App Control off | Windows Security → App & browser control → Smart App Control → Off | |
| 3 | Time zone set to Saskatchewan (Alberta only) | Settings → Time & language → Date & time → Set time zone automatically Off → Time zone (UTC-06:00) Saskatchewan | Same clock time, nothing else changes. The Historian won’t start without this. |
| 4 | Antivirus not blocking Canary | Pause it, or allow the Canary folders during install | |
| 5 | Default install paths on C: | Don’t change the install, data or ProgramData folders to another drive | |
| 6 | Licence activated for all four products | Canary Admin → Licenses → Add license through internet → Tick Historian, Axiom, Historian ODBC and Views → Get License | |
| 7 | All services Running | Canary Admin → Services | Wait 2 minutes after a reboot |
| 8 | API token made | Canary Admin → Identity → API Tokens → ADD | User = your own Windows account |
| 9 | Python ready | `pip install -r requirements.txt` in the Starter EDA folder | |


## 3. Top fixes

### a) Time zone (the root cause for us)

- Windows’ new “(UTC-06:00) Mountain Time (Alberta)” zone crashes the Historian and ODBC services.
- **FIX:** Switching to “(UTC-06:00) Saskatchewan” fixed it instantly.

### b) Clean install to C:

- Installing to another drive (we used F:) and reinstalling over old files left settings and registry entries behind.
- **FIX:** A full uninstall, then a reinstall with the default C: paths, gave us a clean base.

### c) Licence reset

- After a reinstall, only Views re-activated: the Historian, Axiom and ODBC licences were still tied to the old install.
- **FIX:** Contact the organizers. We’ll get Canary support to reset your licence.

## 4. Problems and fixes

Find the row that matches what you see on screen. The rows run roughly in the order teams will meet them: install, licence, services, then Python.

| Problem | Cause | Fix |
|---|---|---|
| Mac or Linux only | Canary needs Windows | Borrow a Windows laptop or use Databricks |
| Only the Views licence activates | Licence still tied to the old install | Contact the organizers. We’ll get Canary to reset it. |
| Canary files blocked during install | Smart App Control | Turn it off, reinstall |
| Historian and ODBC won’t start / Historian did not answer | Alberta time zone | Switch to Saskatchewan, restart |
| Reinstall still broken | Leftovers from the old install | Uninstall everything, remove leftover Canary folders, reinstall with default C: paths. |
| “Not connected to Localhost” | Services still starting | Wait 2 minutes |
| Python can’t reach Canary | Store & Forward stopped | Start it in Services |
| “Access denied” | No API token | Make a token, paste it into `CANARY_TOKEN` |
| “Token rejected” | Wrong or bad token | New token linked to your own user |
| `ModuleNotFoundError` | Missing package | `pip install -r requirements.txt` |
