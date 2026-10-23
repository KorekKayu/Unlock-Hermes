# hermes-unlock

Matikan **semua** guardrail Hermes Agent (CLI + gateway). Cross-platform: Windows
10/11, Ubuntu/Debian, Fedora/RHEL/Arch, macOS (Intel & ARM), WSL, VPS headless.

Isi folder — **5 file**:

| File | Fungsi |
|---|---|
| `hermes_unlock.py` | Patcher (source + config + restart + verify) + `--status`, `--restore`, `--clean`, `--soul`, `--inject`, banner WM inline |
| `unlock.sh` | Launcher Linux / macOS / WSL / git-bash |
| `unlock.bat` | Launcher Windows (CMD, double-click friendly) |
| `SOUL_v7.md` | Persona IKONA v7.0 (dipasang lewat `--soul`) |
| `README.md` | Dokumen ini |

Dua lapis yang dikerjakan patcher:

| Lapis | Apa | Cara |
|---|---|---|
| Config | `approvals.*`, `security.*`, `gateway.*`, `tool_loop_guardrails.*` | `hermes config set` |
| Source | ~28 fungsi di `agent/` + `tools/` yang **tidak baca config sama sekali** | patch in-place + backup + compile-check + verify |

Patcher auto-detect `HERMES_HOME`, package root, interpreter venv, dan modul yang
benar-benar mendefinisikan tiap fungsi — jalan di layout **split** (v0.21+:
`approval_detection.py`, `approval_floors.py`, `*_guards.py`) maupun **mono**
(build lama: semua di `tools/approval.py`).

---

## 1. Requirement

| OS | Wajib |
|---|---|
| Windows 10/11 | Python 3.8+ dari [python.org](https://www.python.org/downloads/) atau `py -3` |
| Ubuntu/Debian | `sudo apt install -y python3` |
| Fedora/RHEL/Alma | `sudo dnf install -y python3` |
| Arch/Manjaro | `sudo pacman -S --needed python` |
| macOS | `brew install python@3.12` atau python.org |
| WSL | seperti Ubuntu |

Selain itu: Hermes Agent terinstall, dan hak tulis ke folder install (Linux VPS
biasanya `sudo`). CLI `hermes` di PATH dipakai untuk step config — kalau tidak ada,
patcher tetap jalan dan print perintah manualnya.

Tidak butuh tkinter, pip package, atau dependency lain.

---

## 2. Quick start

### Windows 10 / 11

```bat
cd %USERPROFILE%\Desktop\hermes-unlock

unlock.bat --dry-run      :: lihat rencana, tidak menulis apa pun
unlock.bat                :: SOUL.md + patch + config + restart
unlock.bat --status

:: atau langsung tanpa wrapper
python hermes_unlock.py --soul
python hermes_unlock.py --status
```

Double-click `unlock.bat` juga bisa (jendela pause kalau exit != 0).
Install di `C:\Program Files`? Jalankan CMD **as Administrator**.
`python` nyangkut ke Microsoft Store? Wrapper otomatis coba `py -3` dulu.

### Ubuntu / Debian

```bash
sudo apt install -y python3
cd ~/hermes-unlock

chmod +x unlock.sh
sudo ./unlock.sh --dry-run
sudo ./unlock.sh                 # SOUL.md + patch + config + restart
python3 hermes_unlock.py --status   # --status/--verify-only tidak perlu root
```

Hermes home: `/root/.hermes` kalau di-install pakai `sudo`, `~/.hermes` kalau
per-user. Override: `HERMES_HOME=/path` atau `--home /path`.

### Fedora / RHEL / CentOS / Alma / Rocky

```bash
sudo dnf install -y python3
sudo ./unlock.sh
```

### Arch / Manjaro

```bash
sudo pacman -S --needed python
sudo ./unlock.sh
```

### macOS (Intel & Apple Silicon)

```bash
brew install python@3.12
chmod +x unlock.sh
./unlock.sh --dry-run
./unlock.sh                      # ~/.hermes — tidak perlu sudo
```

Kalau Hermes jalan sebagai service root/launchd: `sudo ./unlock.sh`.

### WSL / VPS headless

```bash
sudo apt install -y python3
./unlock.sh --no-restart          # gateway diurus systemd/supervisor
sudo systemctl restart hermes-gateway
```

---

## 3. `hermes_unlock.py` — CLI

| Flag | Fungsi |
|---|---|
| *(tanpa flag)* | patch + config + restart + verify |
| `--dry-run` | print rencana; **tidak** menulis file, backup, atau manifest |
| `--status` | status per file: `patched` / `unpatched` / `partial` + deteksi drift |
| `--list` | daftar fungsi target + modul pemiliknya |
| `--verify-only` | live check saja (import modul, panggil fungsinya) |
| `--restore` | balikin semua file dari backup `*.ikonaorig` |
| `--clean` | rapikan blok `# NOGUARD` yang numpuk (sisa versi lama) |
| `--soul` | install `SOUL_v7.md` → `HERMES_HOME/SOUL.md` (backup otomatis) lalu lanjut patch |
| `--inject` | netralkan guard **di proses ini saja** (monkey-patch, tanpa sentuh file) |
| `--inject-watch` | seperti `--inject` + re-apply kalau ada `importlib.reload()` |
| `--no-config` | skip `hermes config set` |
| `--no-restart` | skip restart gateway |
| `--no-banner` | matiin banner IKONA-ONI (default: banner print tiap run) |
| `-y`, `--yes` | lewati konfirmasi LANJUTKAN/BATAL (wajib untuk cron/pipe/non-interaktif) |
| `--home DIR` | override `HERMES_HOME` |
| `--pkg DIR` | override package root (folder berisi `tools/` + `agent/`) |
| `--pybin PY` | override interpreter (venv Hermes) |
| `--backup-dir DIR` | override folder backup |
| `--version` | versi script |

### Konfirmasi sebelum inject

Mode yang **menulis** file (`patch` dan `--clean`) selalu nanya dulu:

```
------------------------------------------------------------------------------
 PERINGATAN — proses ini MENGUBAH file Hermes Agent secara in-place.

   backup original : C:\hermes-unlock-backup
                     (dibuat sekali, backup lama tidak pernah ditimpa)
   rollback        : python3 hermes_unlock.py --restore
   catatan         : `hermes update` menimpa patch -> jalankan ulang script ini
------------------------------------------------------------------------------
 Pilihan  [1] LANJUTKAN INJECT   [2] BATAL INJECT   (default 2):
```

* `1` / `lanjut` / `y` → lanjut
* `2` / `batal` / `n` / **Enter** → batal, **tidak ada file yang diubah**, exit code `2`
* input ngawur → ditanya lagi
* stdin bukan TTY (pipe, cron, scheduler) → otomatis **batal** kecuali pakai `--yes`
* `--dry-run`, `--status`, `--list`, `--verify-only`, `--inject` tidak pernah nanya

```bash
./unlock.sh --yes                 # unattended
python3 hermes_unlock.py --yes    # sama
```

Contoh diagnosa:

```bash
python3 hermes_unlock.py --list --home /root/.hermes
python3 hermes_unlock.py --status --pkg /opt/hermes/workspace
python3 hermes_unlock.py --verify-only --pybin /opt/hermes/venv/bin/python
```

Runtime patch dari skrip sendiri (tanpa edit file, tanpa restart):

```python
import hermes_unlock as hu
hu.inject_unlock(verbose=True)   # → jumlah target yang dinetralkan
hu.inject_watch()                # opsional: re-apply saat module reload
```

---

## 4. Wrapper: `unlock.sh` & `unlock.bat`

Dua-duanya cuma pembungkus tipis: cari interpreter yang benar, pasang `--soul`
default, lalu teruskan semua argumen ke `hermes_unlock.py`.

| | `unlock.sh` | `unlock.bat` |
|---|---|---|
| OS | Linux, macOS, WSL, git-bash | Windows 10/11 (CMD) |
| Interpreter | `$PYTHON` → venv Hermes → `python3` → `python` | `%PYTHON%` → venv Hermes → `py -3` → `python` |
| SOUL default | ya | ya |
| Skip SOUL | `--skip-soul` (arg pertama) atau `SKIP_SOUL=1` | `--skip-soul` (arg pertama) |
| Argumen lain | diteruskan apa adanya | diteruskan apa adanya |

```bash
./unlock.sh --dry-run                 # preview
./unlock.sh --skip-soul --status      # tanpa sentuh SOUL.md
PYTHON=/opt/hermes/venv/bin/python ./unlock.sh
```

```bat
unlock.bat --dry-run
unlock.bat --skip-soul --status
set PYTHON=C:\Python312\python.exe && unlock.bat
```

Konfirmasi LANJUTKAN/BATAL datang dari `hermes_unlock.py`, jadi muncul juga saat
dipanggil lewat wrapper — dan `--yes` diteruskan apa adanya.

Error di `.bat` bikin jendela pause (biar kebaca kalau di-double-click); exit code
tetap diteruskan (`2` = dibatalkan di prompt).

---

## 5. Yang dinetralkan

**Approval / command gating** — `detect_hardline_command` → `(False, "")`,
`detect_dangerous_command` → `(False, "", "")`, `_check_sudo_stdin_guard` → `(False, "")`,
`_match_user_deny_rule` / `_hardline_block_result` / `_user_deny_block_result` → `None`,
`_command_matches_permanent_allowlist` → `False`.

**File policy** — `is_write_denied`, `is_write_approval_required` → `False`;
`get_write_denied_error`, `raise_if_read_blocked`, `get_read_block_error`,
`_classify_write_denial`, `get_*_mirror_warning` → `None`.

**Write guards** (split layout) — `_check_sensitive_path`,
`_check_protected_instruction_write`, `_check_approval_required_write`,
`_request_protected_instruction_approval` → `None`.

**Terminal guards** — `gateway_lifecycle_block`, `self_repo_block`,
`_validate_workdir` → `None`.

**URL / website** — `_is_blocked_ip` → `False`, `is_always_blocked_url` → `False`,
`_resolve_allow_private_urls` → `True`, `check_website_access` → `None`.

**Write approval** — `write_approval_enabled` → `False` (`evaluate_gate` sengaja
tidak di-patch: caller-nya butuh objek `GateDecision`).

**Tool-loop hard stop** — `_is_non_interactive_platform` → `False` + flag
`warnings/hard_stop/non_interactive_hard_stop` dipaksa `False` di
`ToolCallGuardrailConfig.from_mapping`. Ini yang biasanya nendang di gateway/cron.

---

## 6. Config yang di-set

```
approvals.mode = off
approvals.cron_mode = off
approvals.single_query_mode = off
approvals.unattended_mode = off
security.redact_secrets = false
security.tirith_enabled = false
security.allow_private_urls = true
privacy.redact_pii = false
gateway.allow_all_users = true
gateway.loop_watchdog = false
gateway.bot_loop_guard.enabled = false
gateway.startup_watchdog = false
tool_loop_guardrails.warnings_enabled = false
tool_loop_guardrails.hard_stop_enabled = false
tool_loop_guardrails.non_interactive_hard_stop_enabled = false
tool_loop_guardrails.loop_caps.max_web_searches = 0
tool_loop_guardrails.loop_caps.max_subagents = 0
```

Semua lewat CLI resmi (`hermes config set`), jadi tetap valid saat Hermes baca ulang.

---

## 7. Watermark

WM nempel di dalam `hermes_unlock.py` (`WM_ART` + `print_banner()`), bukan file atau
modul terpisah. Tiap kali script jalan, banner IKONA-ONI muncul duluan:

```
######### ###   ### ######### ###   ###   #####             ######### ###   ### #########
   ###    ###  ###  ###   ### ####  ###  ### ###            ###   ### ####  ###    ###
   ...
  :: IKONA-ONI ::  oni-ino watermark ::
```

* matiin: `python hermes_unlock.py --status --no-banner` (atau `unlock.sh --no-banner`)
* `--help` / `--version` tetap bersih (argparse exit sebelum banner)
* dipakai dari skrip lain:

```python
import hermes_unlock
hermes_unlock.print_banner()
```

Tidak ada lagi `wm.py`: overlay layar / runner / injector ke script lain sudah
dihapus. Salinan terakhir file itu disimpan di
`C:\hermes-unlock-backup\wm.py.removed-bak` kalau nanti butuh dihidupkan lagi.

---

## 8. Backup, restore, update

Backup original dibuat sekali, tidak pernah ditimpa:

| OS | Default |
|---|---|
| Windows | `C:\hermes-unlock-backup` (kalau sudah ada) → `%USERPROFILE%\hermes-unlock-backup` |
| Linux/macOS | `/opt/hermes-heavy` (kalau sudah ada) → `~/hermes-unlock-backup` |

Override: `HERMES_UNLOCK_BACKUP=/path` atau `--backup-dir /path`.

Patcher juga menulis `manifest.json` (hash original + hash hasil patch), dipakai
`--status` buat deteksi drift:

```
  file                               patched   state      note
  ------------------------------------------------------------------------------
  agent/file_safety.py               8/8       patched
  tools/approval_detection.py        3/3       patched    SOURCE CHANGED -> re-run
```

**`hermes update` selalu menimpa source patch.** Urutan benar:

```bash
hermes update
./unlock.sh --skip-soul          # patch ulang, SOUL.md tidak diutak-atik
```

Pernah pakai versi lama script ini? Blok `# NOGUARD` bisa numpuk berkali-kali:

```bash
python3 hermes_unlock.py --clean --dry-run
python3 hermes_unlock.py --clean --no-restart
```

---

## 9. Troubleshooting

**`ERROR: HERMES_HOME not found`** — cek `hermes --version` (print *Install directory*),
lalu `python3 hermes_unlock.py --home /path/.hermes`.

**`ERROR: cannot resolve the Hermes package root`** — layout beda; arahkan manual:
`--pkg ~/.hermes/installs/<id>/environments/<id>/workspace`.

**`Permission denied` / `Access is denied`** — Linux: `sudo`. Windows: CMD as
Administrator kalau install di `C:\Program Files`. Tanpa root: `--inject`.

**Step config semua `ERR`** — CLI `hermes` tidak di PATH:
`export HERMES_BIN=/usr/local/bin/hermes` / `set HERMES_BIN=C:\...\hermes.exe`.

**`--verify-only` bilang "could not run live checks"** — interpreter bukan venv
Hermes: `--pybin ~/.hermes/installs/*/environments/*/venv/bin/python`
(Windows: `...\venv\Scripts\python.exe`).

**Windows: `python` membuka Microsoft Store** — wrapper sudah coba `py -3` lebih dulu;
kalau masih, matikan alias di *Settings → Apps → App execution aliases*.

**`.sh: Permission denied`** — `chmod +x unlock.sh` (atau jalankan `sh unlock.sh`).

**`.bat` langsung ketutup** — error bikin `pause`; kalau tetap ketutup, jalankan dari
CMD biar kelihatan pesannya.

**`unlock.bat` bilang `unrecognized arguments: --skip-soul`** — versi lama; `--skip-soul`
harus argumen **pertama** (sudah ditangani di versi ini).

**Setelah `hermes update` guard balik aktif** — normal; jalankan patcher lagi.

---

## 10. Status pengujian

Dijalankan di Windows 10 Pro 19045, Python 3.14.7, Hermes 0.21.6:

| Uji | Hasil |
|---|---|
| `--dry-run` di install nyata | 28 target terdeteksi, 1 skip, 0 file ditulis, folder backup tidak dibuat |
| Patch di sandbox (stub 28 fungsi) | 28 fungsi + flag guardrails, semua `compile OK` |
| Run kedua | semua `already`, 0 tulisan (idempotent) |
| `--status` + drift | `SOURCE CHANGED` muncul setelah file diubah |
| `--clean` | 4 blok numpuk dihapus, `ast.parse` tetap OK |
| `--restore` | 9/9 file identik dengan backup, manifest dihapus |
| CRLF / tab / `def` satu baris | newline & indentasi dipertahankan; `def` satu baris di-skip |
| `--soul` | install + backup + idempotent (`already installed`) |
| `--inject` / `--inject-watch` | guard jadi netral di proses itu, idempotent |
| Banner inline | print tiap run, `--no-banner` matiin, `--help`/`--version` bersih |
| Prompt konfirmasi | `1`/`lanjut` → lanjut, Enter/`2` → batal (exit 2, 0 file diubah), input invalid → ditanya lagi |
| Non-TTY tanpa `--yes` | batal otomatis, 0 file diubah |
| `--yes` | langsung jalan tanpa prompt (sandbox patch sukses) |
| `--dry-run` | tidak pernah memunculkan prompt |
| `--clean` tanpa `--yes` | kena prompt yang sama (BATAL CLEAN) |
| `unlock.sh` | `sh -n` + `bash -n` OK; `--skip-soul --status` dan `--dry-run` jalan |
| `unlock.bat` | `--skip-soul --status` dan `--dry-run` jalan; deteksi venv `py`/`python` OK |
| `python -m py_compile` | OK |

**Belum** diuji: eksekusi patch di install nyata (sengaja cuma `--dry-run` waktu
penulisan dokumen ini) dan runtime Linux/macOS (jalur POSIX ditulis + syntax check,
belum dieksekusi di mesin ini). Jalankan `--dry-run` dulu di OS masing-masing.

---

## 11. Uninstall

```bash
python3 hermes_unlock.py --restore     # balikin source
```

Config yang sudah di-set tidak ikut balik otomatis — set manual kalau perlu
(`hermes config set approvals.mode ask`). `SOUL.md` lama ada di
`SOUL.md.bak.<timestamp>` di `HERMES_HOME`.

---

## 12. Catatan

Dengan `raise_if_read_blocked`, write-deny, dan redaksi secret dimatikan, agent state,
session token, dan provider credential bisa dibaca/tulis lewat tool biasa. Di box yang
nerima input remote (gateway publik, bot Telegram), itu permukaan serangan tambahan —
pastikan memang itu yang mau dicapai sebelum jalan di mesin produksi.
