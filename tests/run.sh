#!/bin/bash
# Every suite, in the order a failure is most useful to read.
#
#   test-helper.py        behaviour, through the Helper's one seam
#   test-discovery.py     which endpoint is the mouse
#   test-qml-contracts.sh the agreements between QML, manifest and Helper
#
# Manifest correctness is checked by the Omarchy plugin validation CLI rather
# than by a test written here — that CLI is what mirrors the running shell, and
# reimplementing it would only drift from it. It is run last when available.
#
# Bytecode is kept out of the plugin folder: the shell hot-reloads plugin code
# whenever any file under the plugins directory is saved, so a __pycache__
# written by a test run would restart the Helper for every suite.
set -u
export PYTHONDONTWRITEBYTECODE=1
here="$(cd "$(dirname "$0")" && pwd)"
rc=0
for suite in test-helper.py test-discovery.py; do
  python3 "$here/$suite" || rc=1
done
bash "$here/test-qml-contracts.sh" || rc=1

if command -v omarchy-plugin-validate >/dev/null 2>&1; then
  if omarchy-plugin-validate "$here/.."; then
    echo "PASS manifest: passes the Omarchy plugin validation CLI"
  else
    echo "FAIL manifest: rejected by the Omarchy plugin validation CLI"
    rc=1
  fi
else
  echo "SKIP manifest: omarchy-plugin-validate is not on PATH"
fi
exit "$rc"
