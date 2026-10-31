#!/usr/bin/env python3
# =============================================================================
#  unlock.py  ·  IKONA-ONI  ·  satu perintah, tanpa flag
#
#      python unlock.py          # ini saja. semuanya.
#      python unlock.py --status # cek sudah kepasang atau belum
#
#  Yang dijalankan (semua sekaligus, tanpa nanya):
#    SOUL.md + HACKMODE contract + prefill injection
#    source patch (PLAN + auto-discovery) + compile check
#    config guardrail -> off  (approvals, security, tool_loop, skills)
#    gateway restart -> verify -> audit runtime (panggil tiap guard)
#    watchdog: re-patch otomatis tiap 30 menit
#
#  Semua flag lain diteruskan apa adanya ke hermes_unlock.py:
#      python unlock.py --dry-run
#      python unlock.py --restore
#      python unlock.py --audit
# =============================================================================
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

DEFAULT = ["--hackmode", "--yes", "--auto"]

HELP = """unlock.py — Hermes tanpa guard, satu perintah.

  python unlock.py               pasang semuanya (default)
  python unlock.py --status      cek status patch + HACKMODE
  python unlock.py --audit       bukti runtime: panggil tiap guard
  python unlock.py --dry-run     lihat rencana, tidak menulis apa pun
  python unlock.py --restore     balikin source asli
"""


def main() -> int:
    args = sys.argv[1:]
    if args and args[0] in ("-h", "--help", "help"):
        print(HELP)
        return 0
    # mode baca-saja / rollback: jangan tambahin --hackmode + --watch-install
    readonly = any(a in ("--status", "--list", "--audit", "--dry-run", "--restore",
                         "--verify-only", "--clean", "--discover", "--version",
                         "--prefill")
                   for a in args)
    try:
        import hermes_unlock as hu
    except Exception as exc:
        print("GAGAL import hermes_unlock.py di %s: %s" % (HERE, exc))
        return 1
    if readonly:
        return hu.main(args)
    return hu.main(DEFAULT + args)


if __name__ == "__main__":
    sys.exit(main())
