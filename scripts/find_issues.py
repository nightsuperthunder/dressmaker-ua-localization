"""Пошук смислових помилок у перекладі: три етапи поспіль.

1) backtranslate.py          — модель перекладає український текст назад англійською;
2) backtranslate.py --judge  — сильніша модель порівнює оригінал і зворотний переклад;
3) context_review.py         — вона ж перевіряє підозрілі рядки з контекстом сусідніх реплік.

  python scripts/find_issues.py                       # діалоги
  python scripts/find_issues.py --file dialogue --file content

Результат: work/context_review.csv — перегляньте, зайві рядки видаліть, решту застосуйте:
  python scripts/review.py import --csv work/context_review.csv

Не дає Windows заснути, поки працює.
"""
import argparse
import ctypes
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
JUDGE = "gemma4:26b-a4b-it-q4_K_M"


def run(script, *extra):
    print(f"\n######## {script} {' '.join(extra)}", flush=True)
    rc = subprocess.call([sys.executable, "-u", str(HERE / script), *extra])
    if rc != 0:
        print(f"!!! крок завершився з кодом {rc}", flush=True)
    return rc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", action="append", default=None)
    ap.add_argument("--judge-model", default=JUDGE)
    ap.add_argument("--top", type=int, default=1500, help="скільки підозрілих рядків віддати рецензенту")
    args = ap.parse_args()
    files = []
    for f in (args.file or ["dialogue"]):
        files += ["--file", f]

    try:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    except Exception:
        pass

    t0 = time.time()
    run("backtranslate.py", *files)
    run("backtranslate.py", "--judge", "--judge-model", args.judge_model, "--no-think",
        "--top", str(args.top), *files)
    run("context_review.py", "--only-keys", str(HERE.parent / "work" / "suspects.txt"),
        "--model", args.judge_model, "--no-think", "--restart", *files)
    print(f"\n######## ГОТОВО за {(time.time() - t0) / 3600:.1f} год", flush=True)
    print("Перегляньте work/context_review.csv, потім:")
    print("  python scripts/review.py import --csv work/context_review.csv")


if __name__ == "__main__":
    main()
